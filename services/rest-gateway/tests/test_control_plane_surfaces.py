"""REST surfaces for durable control-plane primitives."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from rest_helpers import seed_run


def _h(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-Id": tenant_id}


class _QuoteServer:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                owner.requests.append({"path": self.path, "tenant": self.headers.get("X-Tenant-Id")})
                now = datetime.now(timezone.utc).isoformat()
                body = {
                    "quote": {
                        "symbol": "AAPL",
                        "last": 212.45,
                        "event_time": now,
                        "received_time": now,
                        "source": "doomberg-live-data",
                        "entitlement_class": "doomberg_live",
                    }
                }
                raw = json.dumps(body).encode("utf-8")
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

    def __enter__(self) -> "_QuoteServer":
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


def test_dev_tenant_header_must_be_uuid(client):
    response = client.get("/api/triggers", headers=_h("not-a-uuid"))

    assert response.status_code == 400
    assert response.json()["detail"] == "tenant_id must be a UUID"


def test_ops_status_reports_live_data_and_paper_execution(client, stores, tenant_a, monkeypatch):
    monkeypatch.setenv("DOOMBERG_ARCHIVE_URL", "postgresql://archive.example/db")
    monkeypatch.setenv("DOOMBERG_IBKR_ENGINE_URL", "https://ibkr.example")
    monkeypatch.setenv("DOOMBERG_IBKR_QUOTE_PATH", "/v1/quote/{symbol}")
    monkeypatch.setenv("DOOMBERG_IBKR_ORDER_PATH", "/v1/orders")
    monkeypatch.setenv("DOOMBERG_ENABLE_LIVE_EXECUTION", "1")
    run_id = seed_run(stores, tenant_a, kind="backtest")
    stores.jobs.create_for_run(tenant_a, run_id, kind="backtest", profile="backtest")
    stores.leases.acquire("trigger-engine", "worker-a", ttl_seconds=60)
    stores.providers.upsert_connection(
        tenant_a,
        provider="ibkr",
        capabilities=["quotes", "orders", "trading"],
        entitlements=[{"dataset": "equities-options", "entitlement_class": "doomberg_live"}],
        account_ref="ibkr-vps",
    )

    response = client.get("/api/ops/status", headers=_h(tenant_a))

    assert response.status_code == 200, response.text
    body = response.json()
    assert "ibkr" not in body
    assert body["live_data"]["engine_configured"] is True
    assert body["live_data"]["connected_quote_provider"] is True
    assert body["execution"]["live_enabled"] is True
    assert body["execution"]["paper_enabled"] is True
    assert body["execution"]["disabled"] is False
    assert body["jobs"]["queued"] == 1
    assert body["leases"][0]["lease_name"] == "trigger-engine"
    assert any(row["name"] == "Trading" and row["state"] == "succeeded"
               for row in body["readiness"])


def test_live_data_smoke_route_calls_read_only_quote_engine(client, tenant_a, monkeypatch):
    with _QuoteServer() as server:
        monkeypatch.setenv("DOOMBERG_IBKR_ENGINE_URL", server.url)
        monkeypatch.setenv("DOOMBERG_IBKR_QUOTE_PATH", "/v1/quote/{symbol}")

        response = client.get(
            "/api/ops/live-data-smoke?symbol=aapl&max_freshness_ms=10000",
            headers=_h(tenant_a),
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["quote"]["symbol"] == "AAPL"
    assert body["quote"]["price"] == 212.45
    assert "raw" not in body["quote"]
    assert server.requests == [{"path": "/v1/quote/AAPL", "tenant": tenant_a}]


def test_trigger_dry_run_route_has_no_side_effects(client, stores, tenant_a):
    now = datetime.now(timezone.utc).isoformat()
    policy = {
        "when": {"event": "market.quote", "universe": ["NVDA"]},
        "condition": {
            "all": [
                {"price": {"gte": 900}},
                {"data_freshness_seconds": {"lte": 10}},
            ]
        },
        "controls": {
            "dedupe_key": "${symbol}:price",
            "cooldown": "0s",
            "max_runs_per_day": 8,
            "require_connected_live_data": True,
        },
        "action": {"run_skill": "market.quote", "mode": "analyze"},
    }

    response = client.post(
        "/api/triggers/dry-run",
        headers=_h(tenant_a),
        json={
            "name": "nvda-test",
            "policy": policy,
            "quote": {
                "symbol": "NVDA",
                "price": 950,
                "event_time": now,
                "received_time": now,
                "source": "doomberg-live-data",
                "entitlement_class": "doomberg_live",
            },
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dry_run"] is True
    assert body["would_fire"] is True
    assert body["reason"] == "WOULD_FIRE"
    assert body["would_create"] == {
        "run": True,
        "job": False,
        "approval": False,
        "broker_order": False,
    }
    assert body["context"]["source"] == "doomberg-live-data"
    assert stores.runs.list(tenant_a) == []
    assert stores.jobs.list(tenant_a) == []
    assert stores.approvals.list(tenant_a) == []
    assert stores.triggers.list_firings(tenant_a) == []


def test_control_plane_rows_are_tenant_scoped_and_reachable(client, stores, tenant_a, tenant_b):
    run_id = seed_run(stores, tenant_a, kind="backtest")
    other_run_id = seed_run(stores, tenant_b, kind="backtest")
    job = stores.jobs.create_for_run(tenant_a, run_id, kind="backtest", profile="backtest")
    stores.jobs.create_for_run(tenant_b, other_run_id, kind="backtest", profile="backtest")

    artifact = stores.artifacts.create(
        tenant_a,
        run_id,
        kind="summary",
        uri="spaces://doomberg-artifacts/runs/demo/summary.json",
        metadata={"sha256": "abc"},
    )
    approval = stores.approvals.create(
        tenant_a,
        run_id,
        kind="order_intent",
        request={"symbol": "AAPL", "notional_usd": 1000},
        requested_by="agent",
    )
    connection = stores.providers.upsert_connection(
        tenant_a,
        provider="alpaca",
        capabilities=["bars", "orders"],
        entitlements=[{"dataset": "equities", "entitlement_class": "doomberg_live"}],
        credential_ref="secret://tenant-a/alpaca",
    )
    snapshot = stores.providers.create_snapshot(
        tenant_a,
        provider="community",
        dataset="prices",
        entitlement_class="public_delayed",
        as_of="2026-06-24T00:00:00Z",
        manifest={"symbols": ["AAPL"]},
    )
    intent = stores.execution.create_order_intent(
        tenant_a,
        run_id,
        payload={"symbol": "AAPL", "side": "buy", "qty": 1},
        idempotency_key="intent-1",
    )
    trigger = stores.triggers.create(
        tenant_a,
        name="price-review",
        policy={"when": {"event": "price.threshold"}, "action": {"run_skill": "market.quote"}},
    )

    assert client.get("/api/jobs", headers=_h(tenant_a)).json()["jobs"][0]["job_id"] == job["job_id"]
    assert client.get("/api/jobs", headers=_h(tenant_b)).json()["jobs"][0]["run_id"] == other_run_id

    artifact_body = client.get("/api/artifacts", headers=_h(tenant_a)).json()["artifacts"][0]
    assert artifact_body["artifact_id"] == artifact["artifact_id"]
    assert client.get(f"/api/artifacts/{artifact['artifact_id']}", headers=_h(tenant_a)).json()["uri"] == artifact["uri"]
    assert client.get(f"/api/artifacts/{artifact['artifact_id']}", headers=_h(tenant_b)).status_code == 404

    approvals = client.get("/api/approvals", headers=_h(tenant_a)).json()["approvals"]
    assert approvals[0]["approval_id"] == approval["approval_id"]
    decided = client.post(
        f"/api/approvals/{approval['approval_id']}/decide",
        json={"decision": "approved", "reason": "paper only"},
        headers=_h(tenant_a),
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["state"] == "approved"
    events = stores.trace.events(tenant_a, run_id)
    assert events[-1]["type"] == "approval_decided"

    providers = client.get("/api/providers", headers=_h(tenant_a)).json()
    assert providers["connections"][0]["connection_id"] == connection["connection_id"]
    assert providers["connections"][0]["credential_configured"] is True
    assert "credential_ref" not in json.dumps(providers)
    assert providers["snapshots"][0]["snapshot_id"] == snapshot["snapshot_id"]
    created_provider = client.post(
        "/api/providers",
        json={
            "provider": "doomberg-live-data",
            "capabilities": ["quote", "bars"],
            "entitlements": [
                {
                    "dataset": "us_equities",
                    "entitlement_class": "doomberg_live",
                    "freshness_class": "live",
                }
            ],
            "account_ref": "ibkr-paper",
            "credential_ref": "env:DOOMBERG_IBKR_ENGINE_TOKEN",
        },
        headers=_h(tenant_a),
    )
    assert created_provider.status_code == 201, created_provider.text
    created_provider_body = created_provider.json()
    assert created_provider_body["provider"] == "doomberg-live-data"
    assert created_provider_body["credential_configured"] is True
    assert "credential_ref" not in json.dumps(created_provider_body)
    assert "account_ref" not in json.dumps(created_provider_body)
    stored_provider = stores.providers.get_connection(tenant_a, created_provider_body["connection_id"])
    assert stored_provider["credential_ref"] == "env:DOOMBERG_IBKR_ENGINE_TOKEN"
    assert client.get("/api/dataset-snapshots", headers=_h(tenant_a)).json()["snapshots"][0]["dataset"] == "prices"

    listed_intents = client.get("/api/order-intents", headers=_h(tenant_a))
    assert listed_intents.status_code == 200, listed_intents.text
    assert listed_intents.json()["order_intents"][0]["intent_id"] == intent["intent_id"]
    created_intent = client.post(
        "/api/order-intents",
        json={
            "run_id": run_id,
            "payload": {
                "broker": "paper",
                "symbol": "MSFT",
                "side": "buy",
                "quantity": 1,
                "order_type": "limit",
                "limit_price": 250,
            },
            "idempotency_key": "rest-intent-1",
        },
        headers=_h(tenant_a),
    )
    assert created_intent.status_code == 201, created_intent.text
    created_intent_body = created_intent.json()
    assert created_intent_body["state"] == "proposed"
    assert client.get(f"/api/order-intents/{intent['intent_id']}", headers=_h(tenant_a)).status_code == 200
    previewed = client.post(f"/api/order-intents/{intent['intent_id']}/preview", headers=_h(tenant_a))
    assert previewed.status_code == 200, previewed.text
    assert previewed.json()["state"] == "approved"
    submitted = client.post(f"/api/order-intents/{created_intent_body['intent_id']}/submit", headers=_h(tenant_a))
    assert submitted.status_code == 200, submitted.text
    submitted_body = submitted.json()
    assert submitted_body["orders"][0]["broker"] == "paper"
    assert submitted_body["fills"][0]["payload"]["symbol"] == "MSFT"

    triggers = client.get("/api/triggers", headers=_h(tenant_a)).json()["triggers"]
    assert triggers[0]["trigger_id"] == trigger["trigger_id"]
    active = client.post(
        f"/api/triggers/{trigger['trigger_id']}/state",
        json={"state": "active"},
        headers=_h(tenant_a),
    )
    assert active.status_code == 200, active.text
    assert active.json()["state"] == "active"
    stores.triggers.record_firing(
        tenant_a,
        trigger["trigger_id"],
        run_id=run_id,
        dedupe_key="price-review:AAPL",
        event_time="2026-06-24T13:30:00+00:00",
        payload={"price": 212.0},
    )
    firings = client.get("/api/trigger-firings", headers=_h(tenant_a)).json()["firings"]
    assert firings[0]["trigger_id"] == trigger["trigger_id"]
