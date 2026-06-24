from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from control_helpers import agent_headers, human_headers
from doomberg_control.execution_gateway import IBKREngineBrokerAdapter


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


class _OrderServer:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
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

    assert out["broker_order_id"] == "ibkr-order-1"
    assert out["state"] == "partially_filled"
    assert out["fills"][0]["broker_fill_id"] == "fill-1"
    assert server.requests[0]["path"] == "/v1/orders"
    assert server.requests[0]["body"]["client_order_id"] == "client-1"
