from __future__ import annotations

from control_helpers import agent_headers, human_headers


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
