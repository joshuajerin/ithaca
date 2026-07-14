from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from control_helpers import agent_headers, human_headers
import pytest

from ithaca_control.actions import ActionError
from ithaca_control.deps import Ctx
from ithaca_control.execution_gateway import (
    BROKER_IBKR,
    BROKER_PAPER,
    ExecutionGateway,
    ExecutionPolicy,
    IBKREngineBrokerAdapter,
    _SubmissionOutcomeUnknown,
)


def _run(platform, tenant_id: str) -> str:
    return platform.runs.create(tenant_id, "research", None, {"name": "manual execution"})


def _intent_payload() -> dict:
    return {
        "broker": "paper",
        "orders": [
            {
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 2,
                "order_type": "limit",
                "limit_price": 100,
                "time_in_force": "day",
            }
        ],
    }


def test_execution_gateway_agent_preview_requires_approval_and_human_submit_fills(
    client,
    platform,
    tenant_a,
):
    run_id = _run(platform, tenant_a)
    created = client.post(
        "/execution/intents",
        json={"run_id": run_id, "payload": _intent_payload(), "idempotency_key": "intent-1"},
        headers=agent_headers(tenant_a),
    )
    assert created.status_code == 201, created.text
    intent_id = created.json()["intent_id"]

    preview = client.post(
        f"/execution/intents/{intent_id}/preview",
        headers=agent_headers(tenant_a),
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["state"] == "approval_required"
    assert platform.approvals.list_pending(tenant_a)[0]["request"]["intent_id"] == intent_id

    agent_submit = client.post(
        f"/execution/intents/{intent_id}/submit",
        headers=agent_headers(tenant_a),
    )
    assert agent_submit.status_code == 403

    submitted = client.post(
        f"/execution/intents/{intent_id}/submit",
        headers=human_headers(tenant_a),
    )
    assert submitted.status_code == 200, submitted.text
    record = submitted.json()
    assert record["state"] == "filled"
    assert record["orders"][0]["broker"] == "paper"
    assert record["orders"][0]["state"] == "filled"
    assert record["fills"][0]["payload"]["notional_usd"] == 200

    again = client.post(
        f"/execution/intents/{intent_id}/submit",
        headers=human_headers(tenant_a),
    )
    assert again.status_code == 200, again.text
    assert len(again.json()["orders"]) == 1
    assert len(again.json()["fills"]) == 1

    events = platform.trace.events(tenant_a, run_id)
    assert [event["type"] for event in events].count("order_submitted") == 1
    assert [event["type"] for event in events].count("fill_reconciled") == 1


def test_execution_gateway_policy_denies_oversized_order(client, platform, tenant_a):
    run_id = _run(platform, tenant_a)
    created = client.post(
        "/execution/intents",
        json={
            "run_id": run_id,
            "payload": {
                "broker": "paper",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 2_000,
                "order_type": "limit",
                "limit_price": 100,
            },
        },
        headers=human_headers(tenant_a),
    )
    assert created.status_code == 201, created.text
    intent_id = created.json()["intent_id"]

    denied = client.post(
        f"/execution/intents/{intent_id}/submit",
        headers=human_headers(tenant_a),
    )
    assert denied.status_code == 409
    detail = denied.json()["detail"]
    assert detail["reason"] == "policy denied"
    assert "MAX_NOTIONAL_EXCEEDED" in detail["risk_decision"]["reasons"]
    assert platform.execution.get_intent(tenant_a, intent_id)["state"] == "policy_denied"


def test_execution_gateway_enforces_tenant_restricted_and_watch_lists(platform, tenant_a):
    platform.compliance_policies.set(
        tenant_a,
        limits={
            "maxPositionPct": 100.0,
            "maxNetPct": 1_000.0,
            "maxLeverage": 10.0,
            "maxConcentrationPct": 100.0,
        },
        limits_enforced=False,
        restricted=["TSLA"],
        watch=["AAPL"],
        action="Execution lists",
        actor_id="risk-officer",
        expect_version=0,
    )
    gateway = ExecutionGateway(platform)
    ctx = Ctx(tenant_a, "human", "trader-1")
    payload = _intent_payload()
    payload["orders"][0]["symbol"] = "TSLA"
    intent = gateway.create_intent(ctx, run_id=_run(platform, tenant_a), payload=payload)
    decision = gateway.evaluate(ctx, intent)
    assert decision["decision"] == "denied"
    assert "RESTRICTED_SYMBOL" in decision["reasons"]
    assert decision["compliance"]["restricted_hits"] == ["TSLA"]

    watched_payload = _intent_payload()
    watched = gateway.create_intent(
        ctx,
        run_id=_run(platform, tenant_a),
        payload=watched_payload,
    )
    watched_decision = gateway.evaluate(ctx, watched)
    assert watched_decision["decision"] == "approved"
    assert "WATCH_LIST_SYMBOL" in watched_decision["warnings"]
    assert watched_decision["compliance"]["watch_hits"] == ["AAPL"]


def test_execution_kill_switch_requires_human_and_blocks_submission(
    client, platform, tenant_a
):
    denied_toggle = client.post(
        "/execution/kill-switch",
        json={"enabled": True, "reason": "agent request", "expect_version": 0},
        headers=agent_headers(tenant_a),
    )
    assert denied_toggle.status_code == 403

    engaged = client.post(
        "/execution/kill-switch",
        json={"enabled": True, "reason": "operator halt", "expect_version": 0},
        headers=human_headers(tenant_a),
    )
    assert engaged.status_code == 200, engaged.text
    assert engaged.json()["source"] == "tenant"

    run_id = _run(platform, tenant_a)
    gateway = ExecutionGateway(platform)
    ctx = Ctx(tenant_a, "human", "trader-1")
    intent = gateway.create_intent(ctx, run_id=run_id, payload=_intent_payload())
    with pytest.raises(ActionError) as exc_info:
        gateway.submit(ctx, intent["intent_id"])
    assert exc_info.value.status == 409
    assert "EXECUTION_KILL_SWITCH_ACTIVE" in exc_info.value.detail["risk_decision"]["reasons"]
    assert platform.execution.get_record(tenant_a, intent["intent_id"])["orders"] == []


def test_execution_kill_switch_is_rechecked_after_durable_submission_claim(
    monkeypatch: pytest.MonkeyPatch, platform, tenant_a
):
    class _NeverCalledAdapter:
        broker = BROKER_PAPER

        def __init__(self) -> None:
            self.calls = 0

        def submit(self, **_kwargs: Any) -> dict[str, Any]:
            self.calls += 1
            raise AssertionError("broker must not be called after the kill switch changes")

    adapter = _NeverCalledAdapter()
    gateway = ExecutionGateway(platform, adapters={BROKER_PAPER: adapter})
    ctx = Ctx(tenant_a, "human", "trader-1")
    run_id = _run(platform, tenant_a)
    intent = gateway.create_intent(ctx, run_id=run_id, payload=_intent_payload())
    checks = 0

    def changing_control(_tenant_id: str) -> dict[str, Any]:
        nonlocal checks
        checks += 1
        enabled = checks > 1
        return {
            "enabled": enabled,
            "source": "tenant" if enabled else "none",
            "reason": "race halt" if enabled else None,
            "version": 1 if enabled else 0,
            "tenant_control": None,
            "global_control": None,
        }

    monkeypatch.setattr(gateway, "_execution_control", changing_control)
    with pytest.raises(ActionError) as exc_info:
        gateway.submit(ctx, intent["intent_id"])

    assert exc_info.value.status == 409
    record = platform.execution.get_record(tenant_a, intent["intent_id"])
    assert record["state"] == "policy_denied"
    assert record["orders"][0]["state"] == "cancelled"
    assert adapter.calls == 0


def test_execution_kill_switch_preserves_partial_execution_state(
    monkeypatch: pytest.MonkeyPatch, platform, tenant_a
):
    class _FirstFillAdapter:
        broker = BROKER_PAPER

        def __init__(self) -> None:
            self.calls = 0

        def submit(self, **kwargs: Any) -> dict[str, Any]:
            self.calls += 1
            assert self.calls == 1
            return {
                "broker_order_id": "paper-first",
                "state": "filled",
                "fills": [
                    {
                        "broker_fill_id": "paper-first-fill",
                        "payload": {"quantity": 1, "price": 100},
                    }
                ],
                "raw": {"client_order_id": kwargs["client_order_id"]},
            }

    adapter = _FirstFillAdapter()
    gateway = ExecutionGateway(platform, adapters={BROKER_PAPER: adapter})
    ctx = Ctx(tenant_a, "human", "trader-1")
    run_id = _run(platform, tenant_a)
    payload = _intent_payload()
    payload["orders"].append(
        {
            "symbol": "MSFT",
            "side": "buy",
            "quantity": 1,
            "order_type": "limit",
            "limit_price": 100,
            "time_in_force": "day",
        }
    )
    intent = gateway.create_intent(ctx, run_id=run_id, payload=payload)
    checks = 0

    def changing_control(_tenant_id: str) -> dict[str, Any]:
        nonlocal checks
        checks += 1
        enabled = checks > 2
        return {
            "enabled": enabled,
            "source": "tenant" if enabled else "none",
            "reason": "race halt" if enabled else None,
            "version": 1 if enabled else 0,
            "tenant_version": 1 if enabled else 0,
            "tenant_control": None,
            "global_control": None,
        }

    monkeypatch.setattr(gateway, "_execution_control", changing_control)
    with pytest.raises(ActionError) as exc_info:
        gateway.submit(ctx, intent["intent_id"])

    assert exc_info.value.status == 409
    record = platform.execution.get_record(tenant_a, intent["intent_id"])
    assert record["state"] == "partially_filled"
    assert [order["state"] for order in record["orders"]] == ["filled", "cancelled"]
    assert len(record["fills"]) == 1
    assert adapter.calls == 1


def test_execution_environment_kill_switch_fails_closed(
    monkeypatch: pytest.MonkeyPatch, platform, tenant_a
):
    monkeypatch.setenv("ITHACA_EXECUTION_KILL_SWITCH", "1")
    gateway = ExecutionGateway(platform)
    control = gateway.get_kill_switch(Ctx(tenant_a, "human", "trader-1"))
    assert control["enabled"] is True
    assert control["source"] == "environment"

    ctx = Ctx(tenant_a, "human", "trader-1")
    intent = gateway.create_intent(ctx, run_id=_run(platform, tenant_a), payload=_intent_payload())
    with pytest.raises(ActionError) as exc_info:
        gateway.submit(ctx, intent["intent_id"])
    assert exc_info.value.status == 409
    assert "EXECUTION_KILL_SWITCH_ACTIVE" in exc_info.value.detail["risk_decision"]["reasons"]
    assert platform.execution.get_record(tenant_a, intent["intent_id"])["orders"] == []


def test_execution_missing_control_store_fails_closed(platform, tenant_a):
    platform.execution_controls = None
    gateway = ExecutionGateway(platform)
    ctx = Ctx(tenant_a, "human", "trader-1")
    intent = gateway.create_intent(ctx, run_id=_run(platform, tenant_a), payload=_intent_payload())

    with pytest.raises(ActionError) as exc_info:
        gateway.submit(ctx, intent["intent_id"])

    assert exc_info.value.status == 409
    decision = exc_info.value.detail["risk_decision"]
    assert decision["execution_control"]["source"] == "missing_control_store"
    assert "EXECUTION_KILL_SWITCH_ACTIVE" in decision["reasons"]
    assert platform.execution.get_record(tenant_a, intent["intent_id"])["orders"] == []


def test_execution_missing_compliance_store_fails_closed(platform, tenant_a):
    platform.compliance_policies = None
    gateway = ExecutionGateway(platform)
    ctx = Ctx(tenant_a, "human", "trader-1")
    intent = gateway.create_intent(ctx, run_id=_run(platform, tenant_a), payload=_intent_payload())

    with pytest.raises(ActionError) as exc_info:
        gateway.submit(ctx, intent["intent_id"])

    assert exc_info.value.status == 409
    decision = exc_info.value.detail["risk_decision"]
    assert "COMPLIANCE_POLICY_UNAVAILABLE" in decision["reasons"]
    assert platform.execution.get_record(tenant_a, intent["intent_id"])["orders"] == []


def test_execution_kill_switch_get_and_payload_validation(client, tenant_a):
    initial = client.get("/execution/kill-switch", headers=human_headers(tenant_a))
    assert initial.status_code == 200
    assert initial.json()["enabled"] is False
    assert initial.json()["tenant_version"] == 0

    omitted = client.post(
        "/execution/kill-switch",
        json={"enabled": True},
        headers=human_headers(tenant_a),
    )
    assert omitted.status_code == 422

    negative = client.post(
        "/execution/kill-switch",
        json={"enabled": True, "expect_version": -1},
        headers=human_headers(tenant_a),
    )
    assert negative.status_code == 422


def test_submission_fence_serializes_tenant_halt_with_broker_send(platform, tenant_a):
    entered_broker = threading.Event()
    release_broker = threading.Event()
    halt_done = threading.Event()

    class _BlockingAdapter:
        broker = BROKER_PAPER

        def submit(self, **_kwargs: Any) -> dict[str, Any]:
            entered_broker.set()
            assert release_broker.wait(timeout=2)
            return {
                "broker_order_id": "paper-fenced-1",
                "state": "filled",
                "fills": [
                    {
                        "broker_fill_id": "paper-fenced-fill-1",
                        "payload": {"quantity": 2, "price": 100},
                    }
                ],
                "raw": {},
            }

    gateway = ExecutionGateway(platform, adapters={BROKER_PAPER: _BlockingAdapter()})
    ctx = Ctx(tenant_a, "human", "trader-1")
    intent = gateway.create_intent(
        ctx,
        run_id=_run(platform, tenant_a),
        payload=_intent_payload(),
    )
    submit_result: list[dict[str, Any]] = []

    submit_thread = threading.Thread(
        target=lambda: submit_result.append(gateway.submit(ctx, intent["intent_id"])),
        daemon=True,
    )
    submit_thread.start()
    assert entered_broker.wait(timeout=2)

    def engage_halt() -> None:
        platform.execution_controls.set_tenant(
            tenant_a,
            enabled=True,
            reason="serialized halt",
            actor_id="operator",
            expect_version=0,
        )
        halt_done.set()

    halt_thread = threading.Thread(target=engage_halt, daemon=True)
    halt_thread.start()
    assert not halt_done.wait(timeout=0.05)
    release_broker.set()
    submit_thread.join(timeout=2)
    halt_thread.join(timeout=2)

    assert submit_result[0]["state"] == "filled"
    assert halt_done.is_set()
    assert platform.execution_controls.get_effective(tenant_a)["enabled"] is True


def test_submission_fence_serializes_compliance_change_with_broker_send(platform, tenant_a):
    entered_broker = threading.Event()
    release_broker = threading.Event()
    policy_done = threading.Event()

    class _BlockingAdapter:
        broker = BROKER_PAPER

        def __init__(self) -> None:
            self.calls = 0

        def submit(self, **_kwargs: Any) -> dict[str, Any]:
            self.calls += 1
            entered_broker.set()
            assert release_broker.wait(timeout=2)
            return {
                "broker_order_id": "paper-policy-fenced",
                "state": "filled",
                "fills": [],
                "raw": {},
            }

    adapter = _BlockingAdapter()
    gateway = ExecutionGateway(platform, adapters={BROKER_PAPER: adapter})
    ctx = Ctx(tenant_a, "human", "trader-1")
    intent = gateway.create_intent(
        ctx,
        run_id=_run(platform, tenant_a),
        payload=_intent_payload(),
    )
    submit_result: list[dict[str, Any]] = []
    submit_thread = threading.Thread(
        target=lambda: submit_result.append(gateway.submit(ctx, intent["intent_id"])),
        daemon=True,
    )
    submit_thread.start()
    assert entered_broker.wait(timeout=2)

    def restrict_symbol() -> None:
        platform.compliance_policies.set(
            tenant_a,
            limits={
                "maxPositionPct": 15.0,
                "maxNetPct": 120.0,
                "maxLeverage": 2.0,
                "maxConcentrationPct": 50.0,
            },
            limits_enforced=False,
            restricted=["AAPL"],
            watch=[],
            action="Restrict AAPL",
            actor_id="risk-officer",
            expect_version=0,
        )
        policy_done.set()

    policy_thread = threading.Thread(target=restrict_symbol, daemon=True)
    policy_thread.start()
    assert not policy_done.wait(timeout=0.05)
    release_broker.set()
    submit_thread.join(timeout=2)
    policy_thread.join(timeout=2)
    assert submit_result[0]["state"] == "filled"
    assert policy_done.is_set()

    next_intent = gateway.create_intent(
        ctx,
        run_id=_run(platform, tenant_a),
        payload=_intent_payload(),
    )
    with pytest.raises(ActionError) as exc_info:
        gateway.submit(ctx, next_intent["intent_id"])
    assert exc_info.value.status == 409
    assert "RESTRICTED_SYMBOL" in exc_info.value.detail["risk_decision"]["reasons"]
    assert adapter.calls == 1


class _RecoveringAdapter:
    broker = BROKER_PAPER

    def __init__(self) -> None:
        self.calls: list[str] = []

    def submit(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs["client_order_id"])
        if len(self.calls) == 1:
            raise ActionError(503, "temporary broker outage")
        return {
            "broker_order_id": "paper-recovered-1",
            "state": "filled",
            "fills": [
                {
                    "broker_fill_id": "paper-recovered-fill-1",
                    "payload": {"quantity": 2, "price": 100},
                }
            ],
            "raw": {"recovered": True},
        }


def test_submit_persists_outbox_before_broker_call_and_retries_same_identity(
    platform, tenant_a
):
    adapter = _RecoveringAdapter()
    gateway = ExecutionGateway(platform, adapters={BROKER_PAPER: adapter})
    ctx = Ctx(tenant_a, "human", "trader-1")
    run_id = _run(platform, tenant_a)
    intent = gateway.create_intent(
        ctx,
        run_id=run_id,
        payload=_intent_payload(),
        idempotency_key="durable-submit",
    )

    with pytest.raises(ActionError, match="temporary broker outage"):
        gateway.submit(ctx, intent["intent_id"])

    interrupted = platform.execution.get_record(tenant_a, intent["intent_id"])
    assert len(interrupted["orders"]) == 1
    assert interrupted["orders"][0]["state"] == "pending_submission"
    client_order_id = interrupted["orders"][0]["client_order_id"]

    recovered = gateway.submit(ctx, intent["intent_id"])
    assert recovered["state"] == "filled"
    assert len(recovered["orders"]) == 1
    assert len(recovered["fills"]) == 1
    assert adapter.calls == [client_order_id, client_order_id]


class _UnknownOutcomeAdapter:
    broker = BROKER_PAPER

    def __init__(self) -> None:
        self.calls = 0
        self.snapshots: list[dict[str, Any]] = []

    def submit(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        raise _SubmissionOutcomeUnknown("response was lost after send")

    def snapshot(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return list(self.snapshots)


def test_unknown_submission_outcome_never_blindly_retries(platform, tenant_a):
    adapter = _UnknownOutcomeAdapter()
    gateway = ExecutionGateway(platform, adapters={BROKER_PAPER: adapter})
    ctx = Ctx(tenant_a, "human", "trader-1")
    run_id = _run(platform, tenant_a)
    intent = gateway.create_intent(ctx, run_id=run_id, payload=_intent_payload())

    with pytest.raises(ActionError, match="outcome is unknown"):
        gateway.submit(ctx, intent["intent_id"])
    unknown = platform.execution.get_record(tenant_a, intent["intent_id"])
    order = unknown["orders"][0]
    assert order["state"] == "submitting"
    assert order["payload"]["submission_outcome"] == "unknown"

    # A normal retry returns durable state and never sends the same order again.
    gateway.submit(ctx, intent["intent_id"])
    assert adapter.calls == 1

    adapter.snapshots = [
        {
            "broker_order_id": "paper-unknown-1",
            "client_order_id": order["client_order_id"],
            "state": "filled",
            "filled_quantity": 2,
            "avg_fill_price": 100,
            "fills": [],
            "raw": {"recovered": True},
        }
    ]
    recovered = gateway.reconcile_intent(ctx, intent["intent_id"])
    assert recovered["state"] == "filled"
    assert recovered["orders"][0]["broker_order_id"] == "paper-unknown-1"
    assert len(recovered["fills"]) == 1


class _SnapshotAdapter:
    broker = BROKER_IBKR

    def __init__(self) -> None:
        self.snapshots: list[dict[str, Any]] = []

    def configured(self) -> bool:
        return True

    def submit(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "broker_order_id": "ibkr-live-1",
            "state": "submitted",
            "fills": [],
            "raw": {"cOID": kwargs["client_order_id"]},
        }

    def snapshot(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return list(self.snapshots)


def test_reconciliation_deduplicates_cumulative_broker_fills(platform, tenant_a):
    adapter = _SnapshotAdapter()
    gateway = ExecutionGateway(
        platform,
        policy=ExecutionPolicy(live_enabled=True, require_connected_provider_for_live=False),
        adapters={BROKER_IBKR: adapter},
    )
    ctx = Ctx(tenant_a, "human", "trader-1")
    run_id = _run(platform, tenant_a)
    intent = gateway.create_intent(
        ctx,
        run_id=run_id,
        payload={**_intent_payload(), "broker": BROKER_IBKR, "live": True},
    )
    submitted = gateway.submit(ctx, intent["intent_id"])
    client_order_id = submitted["orders"][0]["client_order_id"]

    adapter.snapshots = [
        {
            "broker_order_id": "ibkr-live-1",
            "client_order_id": client_order_id,
            "state": "partially_filled",
            "filled_quantity": 1,
            "avg_fill_price": 100,
            "fills": [],
            "raw": {"status": "PartiallyFilled"},
        }
    ]
    first = gateway.reconcile_intent(ctx, intent["intent_id"])
    again = gateway.reconcile_intent(ctx, intent["intent_id"])
    assert first["state"] == "partially_filled"
    assert len(again["fills"]) == 1

    adapter.snapshots[0].update(state="filled", filled_quantity=2, avg_fill_price=110)
    final = gateway.reconcile_intent(ctx, intent["intent_id"])
    assert final["state"] == "filled"
    assert len(final["fills"]) == 2
    assert sum(fill["payload"]["quantity"] for fill in final["fills"]) == 2
    assert [fill["payload"]["price"] for fill in final["fills"]] == [100, 120]
    worker_result = gateway.reconcile_open_orders()
    assert worker_result["open_orders"] == 0


class _OrderServer:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                owner.requests.append({"path": self.path, "method": "GET"})
                raw = json.dumps(
                    {
                        "orders": [
                            {
                                "orderId": "ibkr-order-1",
                                "cOID": "client-1",
                                "status": "Filled",
                                "filledQuantity": 1,
                                "avgPrice": 100,
                            }
                        ]
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or "0")
                body = json.loads(self.rfile.read(length) or b"{}")
                owner.requests.append({"path": self.path, "body": body})
                raw = json.dumps({
                    "status": "partiallyfilled",
                    "order_id": "ibkr-order-1",
                    "fills": [{"broker_fill_id": "fill-1", "payload": {"price": 100, "quantity": 1}}],
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_args: Any) -> None:
                return

        self._handler = Handler
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url = ""

    def __enter__(self) -> "_OrderServer":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler)
        host, port = self._server.server_address
        self.url = f"http://{host}:{port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


def test_ibkr_adapter_uses_shared_engine_client_and_canonicalizes_state() -> None:
    with _OrderServer() as server:
        adapter = IBKREngineBrokerAdapter(base_url=server.url, order_path="/v1/orders")
        out = adapter.submit(
            tenant_id="tenant-1",
            intent_id="intent-1",
            client_order_id="client-1",
            order={"symbol": "AAPL", "side": "buy", "quantity": 1},
        )
        snapshots = adapter.snapshot(tenant_id="tenant-1", account_ref="DU12345")

    assert out["broker_order_id"] == "ibkr-order-1"
    assert out["state"] == "partially_filled"
    assert out["fills"][0]["broker_fill_id"] == "fill-1"
    assert snapshots[0]["broker_order_id"] == "ibkr-order-1"
    assert snapshots[0]["client_order_id"] == "client-1"
    assert snapshots[0]["state"] == "filled"
    assert server.requests[0]["path"] == "/v1/orders"
    assert server.requests[0]["body"]["client_order_id"] == "client-1"
    assert server.requests[1]["path"] == "/orders?account=DU12345"
