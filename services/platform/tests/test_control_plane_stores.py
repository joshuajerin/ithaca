"""Durable control-plane stores: jobs, artifacts, approvals, providers, execution."""

from __future__ import annotations

import uuid


def test_job_store_idempotent_enqueue_and_lease(platform):
    tenant = platform.auth.create_tenant("jobs")
    run_id = platform.runs.create(tenant, "backtest", None, {"name": "demo"})
    platform.runs.transition(tenant, run_id, "queued", expect=0)

    first = platform.jobs.create_for_run(
        tenant,
        run_id,
        kind="backtest",
        profile="backtest",
        payload={"x": 1},
        idempotency_key="same",
    )
    second = platform.jobs.create_for_run(
        tenant,
        run_id,
        kind="backtest",
        profile="backtest",
        payload={"x": 2},
        idempotency_key="same",
    )

    assert second["job_id"] == first["job_id"]
    claimed = platform.jobs.claim_available(
        profiles=("backtest",), kinds=("backtest",), worker_id="worker-1", limit=1
    )
    assert [j["job_id"] for j in claimed] == [first["job_id"]]
    assert claimed[0]["state"] == "leased"
    running = platform.jobs.heartbeat(tenant, first["job_id"], worker_id="worker-1")
    assert running["state"] == "running"
    done = platform.jobs.complete(tenant, first["job_id"], worker_id="worker-1", result={"ok": True})
    assert done["state"] == "succeeded"


def test_job_store_terminal_writes_require_lease_owner(platform):
    tenant = platform.auth.create_tenant("jobs")
    run_id = platform.runs.create(tenant, "backtest", None, {"name": "demo"})
    platform.runs.transition(tenant, run_id, "queued", expect=0)
    job = platform.jobs.create_for_run(tenant, run_id, kind="backtest", profile="backtest")
    platform.jobs.claim_available(
        profiles=("backtest",), kinds=("backtest",), worker_id="worker-1", limit=1
    )

    import pytest
    from doomberg_platform.job_store import JobConflict

    with pytest.raises(JobConflict):
        platform.jobs.complete(tenant, job["job_id"], worker_id="worker-2", result={"ok": True})
    with pytest.raises(JobConflict):
        platform.jobs.fail(tenant, job["job_id"], worker_id=None, error={"code": "bad"})

    assert platform.jobs.get(tenant, job["job_id"])["state"] == "leased"


def test_job_store_cancel_by_run(platform):
    tenant = platform.auth.create_tenant("jobs")
    run_id = platform.runs.create(tenant, "backtest", None, {})
    platform.runs.transition(tenant, run_id, "queued", expect=0)
    job = platform.jobs.create_for_run(tenant, run_id, kind="backtest", profile="backtest")

    cancelled = platform.jobs.cancel_by_run(tenant, run_id, reason="user")

    assert [j["job_id"] for j in cancelled] == [job["job_id"]]
    assert platform.jobs.get(tenant, job["job_id"])["state"] == "cancelled"


def test_artifacts_approvals_providers_and_execution(platform):
    tenant = platform.auth.create_tenant("control")
    run_id = platform.runs.create(tenant, "interactive", None, {})

    artifact = platform.artifacts.create(
        tenant,
        run_id,
        kind="summary",
        uri="spaces://doomberg-artifacts/runs/r1/summary.json",
        metadata={"sha256": "abc"},
    )
    assert platform.artifacts.get(tenant, artifact["artifact_id"])["metadata"]["sha256"] == "abc"
    assert platform.artifacts.list_by_run(tenant, run_id)[0]["artifact_id"] == artifact["artifact_id"]

    approval = platform.approvals.create(
        tenant,
        run_id,
        kind="order_intent",
        request={"notional": 1000},
        requested_by="agent",
    )
    assert platform.approvals.list_pending(tenant)[0]["approval_id"] == approval["approval_id"]
    decided = platform.approvals.decide(
        tenant, approval["approval_id"], decision="denied", decided_by="human", reason="risk"
    )
    assert decided["state"] == "denied"
    assert platform.approvals.list_pending(tenant) == []

    connection = platform.providers.upsert_connection(
        tenant,
        provider="alpaca",
        capabilities=["bars", "orders"],
        entitlements=[{"dataset": "equities", "freshness": "live"}],
        account_ref="acct",
    )
    assert connection["provider"] == "alpaca"
    assert platform.providers.list_connections(tenant)[0]["connection_id"] == connection["connection_id"]
    snapshot = platform.providers.create_snapshot(
        tenant,
        provider="community",
        dataset="prices",
        entitlement_class="public_delayed",
        as_of="2026-06-24T00:00:00Z",
        manifest={"symbols": ["AAPL"]},
    )
    assert snapshot["manifest"]["symbols"] == ["AAPL"]
    assert platform.providers.list_snapshots(tenant, dataset="prices")[0]["snapshot_id"] == snapshot["snapshot_id"]

    intent = platform.execution.create_order_intent(
        tenant,
        run_id,
        payload={"symbol": "AAPL", "qty": 1},
        idempotency_key="order-intent",
    )
    again = platform.execution.create_order_intent(
        tenant,
        run_id,
        payload={"symbol": "MSFT", "qty": 2},
        idempotency_key="order-intent",
    )
    assert again["intent_id"] == intent["intent_id"]
    assert platform.execution.list_intents(tenant, run_id=run_id)[0]["intent_id"] == intent["intent_id"]
    assert uuid.UUID(intent["intent_id"])
    approved = platform.execution.set_intent_state(
        tenant,
        intent["intent_id"],
        state="approved",
        risk_decision={"decision": "approved"},
    )
    assert approved["state"] == "approved"
    order = platform.execution.create_order(
        tenant,
        intent["intent_id"],
        broker="paper",
        client_order_id="dmbg-test-1",
        payload={"symbol": "AAPL", "quantity": 1},
        state="filled",
        broker_order_id="paper-1",
    )
    same_order = platform.execution.create_order(
        tenant,
        intent["intent_id"],
        broker="paper",
        client_order_id="dmbg-test-1",
        payload={"symbol": "MSFT", "quantity": 2},
    )
    assert same_order["order_id"] == order["order_id"]
    fill = platform.execution.create_fill(
        tenant,
        order["order_id"],
        broker_fill_id="fill-1",
        payload={"symbol": "AAPL", "quantity": 1, "price": 100},
        event_time="2026-06-24T00:00:00+00:00",
    )
    record = platform.execution.get_record(tenant, intent["intent_id"])
    assert record["orders"][0]["order_id"] == order["order_id"]
    assert record["fills"][0]["fill_id"] == fill["fill_id"]


def test_trigger_store_lifecycle(platform):
    tenant = platform.auth.create_tenant("triggers")
    trigger = platform.triggers.create(
        tenant,
        name="nvda-review",
        policy={
            "when": {"event": "price.threshold", "universe": ["NVDA"]},
            "condition": {"price": {"gte": 1000}},
            "action": {"run_skill": "market.quote", "mode": "propose"},
        },
    )

    assert trigger["state"] == "draft"
    assert platform.triggers.list(tenant)[0]["trigger_id"] == trigger["trigger_id"]
    active = platform.triggers.set_state(tenant, trigger["trigger_id"], " ACTIVE ")
    assert active["state"] == "active"
    assert platform.triggers.list(tenant, state="active")[0]["trigger_id"] == trigger["trigger_id"]
    assert platform.triggers.list(tenant, state="ACTIVE")[0]["trigger_id"] == trigger["trigger_id"]
    assert platform.triggers.list_active_all()[0]["trigger_id"] == trigger["trigger_id"]
    run_id = platform.runs.create(tenant, "trigger", None, {})
    firing = platform.triggers.record_firing(
        tenant,
        trigger["trigger_id"],
        run_id=run_id,
        dedupe_key="NVDA",
        event_time="2026-06-24T13:30:00+00:00",
        payload={"price": 1000},
    )
    assert firing["run_id"] == run_id
    assert platform.triggers.latest_firing(tenant, trigger["trigger_id"], dedupe_key="NVDA")[
        "firing_id"
    ] == firing["firing_id"]
    assert platform.triggers.count_firings_since(
        tenant,
        trigger["trigger_id"],
        "2026-06-24T00:00:00+00:00",
    ) == 1
    assert platform.triggers.list_firings(tenant)[0]["firing_id"] == firing["firing_id"]
