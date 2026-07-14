"""Durable control-plane stores: jobs, artifacts, approvals, providers, execution."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from ithaca_platform import (
    CompliancePolicyConflict,
    ExecutionControlConflict,
    LeaseConflict,
    UnknownJobProfile,
)


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
    assert claimed[0]["payload"]["admission"]["profile"] == "backtest"
    assert claimed[0]["payload"]["admission"]["limits"]["max_duration_seconds"] == 7200
    running = platform.jobs.heartbeat(tenant, first["job_id"], worker_id="worker-1")
    assert running["state"] == "running"
    done = platform.jobs.complete(tenant, first["job_id"], worker_id="worker-1", result={"ok": True})
    assert done["state"] == "succeeded"


def test_job_store_rejects_unknown_compute_profile(platform):
    tenant = platform.auth.create_tenant("jobs")
    run_id = platform.runs.create(tenant, "backtest", None, {"name": "demo"})
    platform.runs.transition(tenant, run_id, "queued", expect=0)

    with pytest.raises(UnknownJobProfile):
        platform.jobs.create_for_run(tenant, run_id, kind="backtest", profile="gpu-magic")


def test_job_store_terminal_writes_require_lease_owner(platform):
    tenant = platform.auth.create_tenant("jobs")
    run_id = platform.runs.create(tenant, "backtest", None, {"name": "demo"})
    platform.runs.transition(tenant, run_id, "queued", expect=0)
    job = platform.jobs.create_for_run(tenant, run_id, kind="backtest", profile="backtest")
    platform.jobs.claim_available(
        profiles=("backtest",), kinds=("backtest",), worker_id="worker-1", limit=1
    )

    from ithaca_platform.job_store import JobConflict

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


def test_lease_store_owner_renewal_expiry_and_release(platform):
    now = dt.datetime(2026, 6, 24, 12, 0, tzinfo=dt.timezone.utc)

    first = platform.leases.acquire("trigger-engine", "worker-a", ttl_seconds=30, now=now)
    assert first is not None
    assert first["owner_id"] == "worker-a"

    blocked = platform.leases.acquire(
        "trigger-engine",
        "worker-b",
        ttl_seconds=30,
        now=now + dt.timedelta(seconds=10),
    )
    assert blocked is None
    assert platform.leases.get("trigger-engine")["owner_id"] == "worker-a"

    renewed = platform.leases.acquire(
        "trigger-engine",
        "worker-a",
        ttl_seconds=30,
        now=now + dt.timedelta(seconds=20),
    )
    assert renewed is not None
    assert renewed["owner_id"] == "worker-a"
    assert renewed["version"] == first["version"] + 1

    taken = platform.leases.acquire(
        "trigger-engine",
        "worker-b",
        ttl_seconds=30,
        now=now + dt.timedelta(seconds=61),
    )
    assert taken is not None
    assert taken["owner_id"] == "worker-b"

    assert platform.leases.release("trigger-engine", "worker-a") is False
    assert platform.leases.release("trigger-engine", "worker-b") is True
    assert platform.leases.get("trigger-engine") is None


def test_lease_store_heartbeat_requires_current_owner(platform):
    platform.leases.acquire("paper-scheduler", "worker-a", ttl_seconds=30)

    try:
        platform.leases.heartbeat("paper-scheduler", "worker-b", ttl_seconds=30)
    except LeaseConflict:
        pass
    else:  # pragma: no cover - assertion message is clearer than pytest import for this small test.
        raise AssertionError("non-owner heartbeat should fail")

    assert platform.leases.heartbeat("paper-scheduler", "worker-a", ttl_seconds=30)["owner_id"] == "worker-a"


def test_execution_controls_are_durable_versioned_and_tenant_scoped(platform):
    tenant_a = platform.auth.create_tenant("controls-a")
    tenant_b = platform.auth.create_tenant("controls-b")

    assert platform.execution_controls.get_effective(tenant_a)["enabled"] is False
    engaged = platform.execution_controls.set_tenant(
        tenant_a,
        enabled=True,
        reason="operator halt",
        actor_id="user-a",
        expect_version=0,
    )
    assert engaged["version"] == 1
    assert platform.execution_controls.get_effective(tenant_a)["source"] == "tenant"
    assert platform.execution_controls.get_effective(tenant_b)["enabled"] is False

    with pytest.raises(ExecutionControlConflict, match="version is 1, expected 0"):
        platform.execution_controls.set_tenant(
            tenant_a,
            enabled=False,
            reason="stale release",
            actor_id="user-a",
            expect_version=0,
        )

    released = platform.execution_controls.set_tenant(
        tenant_a,
        enabled=False,
        reason="incident cleared",
        actor_id="user-a",
        expect_version=1,
    )
    effective_a = platform.execution_controls.get_effective(tenant_a)
    assert released["version"] == 2
    assert effective_a["enabled"] is False
    assert effective_a["tenant_version"] == 2

    reengaged = platform.execution_controls.set_tenant(
        tenant_a,
        enabled=True,
        reason="incident recurred",
        actor_id="user-a",
        expect_version=effective_a["tenant_version"],
    )
    assert reengaged["version"] == 3

    global_control = platform.execution_controls.set_global(
        enabled=True,
        reason="site incident",
        actor_id="site-admin",
        expect_version=0,
    )
    assert global_control["version"] == 1
    effective_b = platform.execution_controls.get_effective(tenant_b)
    assert effective_b["enabled"] is True
    assert effective_b["source"] == "global"
    assert effective_b["reason"] == "site incident"
    assert platform.execution_controls.list_events(tenant_a)[0]["reason"] == "incident recurred"


def test_execution_controls_global_release_reveals_existing_tenant_halt(platform):
    tenant = platform.auth.create_tenant("layered-controls")
    tenant_halt = platform.execution_controls.set_tenant(
        tenant,
        enabled=True,
        reason="tenant incident",
        actor_id="tenant-operator",
        expect_version=0,
    )
    global_halt = platform.execution_controls.set_global(
        enabled=True,
        reason="site incident",
        actor_id="site-operator",
        expect_version=0,
    )

    effective = platform.execution_controls.get_effective(tenant)
    assert effective["source"] == "global"
    assert effective["tenant_version"] == tenant_halt["version"]

    platform.execution_controls.set_global(
        enabled=False,
        reason="site recovered",
        actor_id="site-operator",
        expect_version=global_halt["version"],
    )
    fallback = platform.execution_controls.get_effective(tenant)
    assert fallback["enabled"] is True
    assert fallback["source"] == "tenant"
    assert fallback["reason"] == "tenant incident"
    assert fallback["tenant_version"] == tenant_halt["version"]


def test_compliance_policies_are_versioned_audited_and_tenant_scoped(platform):
    tenant_a = platform.auth.create_tenant("policy-a")
    tenant_b = platform.auth.create_tenant("policy-b")
    limits = {
        "maxPositionPct": 20.0,
        "maxNetPct": 100.0,
        "maxLeverage": 1.5,
        "maxConcentrationPct": 80.0,
    }
    first = platform.compliance_policies.set(
        tenant_a,
        limits=limits,
        limits_enforced=True,
        restricted=["GME", "TSLA"],
        watch=["NVDA"],
        action="Policy initialized",
        actor_id="risk-officer",
        expect_version=0,
    )
    assert first["version"] == 1
    assert first["restricted"] == ["GME", "TSLA"]
    assert platform.compliance_policies.get(tenant_b) is None

    with pytest.raises(CompliancePolicyConflict, match="version is 1, expected 0"):
        platform.compliance_policies.set(
            tenant_a,
            limits=limits,
            limits_enforced=True,
            restricted=["GME"],
            watch=[],
            action="Stale update",
            actor_id="risk-officer",
            expect_version=0,
        )

    second = platform.compliance_policies.set(
        tenant_a,
        limits=limits,
        limits_enforced=True,
        restricted=["GME"],
        watch=["NVDA", "AMD"],
        action="Lists updated",
        actor_id="risk-officer",
        expect_version=1,
    )
    assert second["version"] == 2
    events = platform.compliance_policies.list_events(tenant_a)
    assert [event["version"] for event in events] == [2, 1]
    assert events[0]["payload"]["watch"] == ["NVDA", "AMD"]


def test_artifacts_approvals_providers_and_execution(platform):
    tenant = platform.auth.create_tenant("control")
    run_id = platform.runs.create(tenant, "interactive", None, {})

    artifact = platform.artifacts.create(
        tenant,
        run_id,
        kind="summary",
        uri="spaces://ithaca-artifacts/runs/r1/summary.json",
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
        client_order_id="ith-test-1",
        payload={"symbol": "AAPL", "quantity": 1},
        state="filled",
        broker_order_id="paper-1",
    )
    same_order = platform.execution.create_order(
        tenant,
        intent["intent_id"],
        broker="paper",
        client_order_id="ith-test-1",
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
    same_fill = platform.execution.create_fill(
        tenant,
        order["order_id"],
        broker_fill_id="fill-1",
        payload={"symbol": "AAPL", "quantity": 1, "price": 100},
        event_time="2026-06-24T00:00:00+00:00",
    )
    assert same_fill["fill_id"] == fill["fill_id"]
    other_order = platform.execution.create_order(
        tenant,
        intent["intent_id"],
        broker="paper",
        client_order_id="ith-test-2",
        payload={"symbol": "MSFT", "quantity": 1},
    )
    with pytest.raises(ValueError, match="another order"):
        platform.execution.create_fill(
            tenant,
            other_order["order_id"],
            broker_fill_id="fill-1",
            payload={"symbol": "MSFT", "quantity": 1, "price": 50},
            event_time="2026-06-24T00:01:00+00:00",
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


def test_worker_heartbeats_preserve_start_and_mark_stop(platform):
    started = dt.datetime(2026, 7, 13, 12, 0, tzinfo=dt.timezone.utc)
    first = platform.worker_heartbeats.heartbeat(
        "worker-a",
        "backtest-worker",
        ttl_seconds=30,
        status="starting",
        metadata={"pid": 10},
        now=started,
    )
    renewed = platform.worker_heartbeats.heartbeat(
        "worker-a",
        "backtest-worker",
        ttl_seconds=60,
        metadata={"last_claimed": 2},
        now=started + dt.timedelta(seconds=10),
    )

    assert renewed["started_at"] == first["started_at"]
    assert renewed["heartbeat_at"] != first["heartbeat_at"]
    assert renewed["status"] == "healthy"
    assert renewed["metadata"] == {"last_claimed": 2}
    stopped = platform.worker_heartbeats.stop("worker-a", "backtest-worker")
    assert stopped["status"] == "stopped"
    assert len(platform.worker_heartbeats.list()) == 1


def test_worker_heartbeat_validation(platform):
    with pytest.raises(ValueError, match="worker_id and role"):
        platform.worker_heartbeats.heartbeat("", "backtest-worker")
    with pytest.raises(ValueError, match="invalid worker heartbeat status"):
        platform.worker_heartbeats.heartbeat("worker-a", "backtest-worker", status="unknown")
