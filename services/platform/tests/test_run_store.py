"""RunStore: state machine, optimistic version guard, tenant isolation, results."""

from __future__ import annotations

import pytest
from helpers import new_uuid, strategy_spec

from doomberg_platform import RunNotFound, TransitionConflict, TransitionError


def test_create_starts_in_draft_at_version_zero(run_store):
    tenant = new_uuid()
    rid = run_store.create(tenant, "backtest", None, strategy_spec())
    row = run_store.get(tenant, rid)
    assert row["state"] == "draft"
    assert row["version"] == 0
    assert row["kind"] == "backtest"
    assert row["result"] is None
    assert row["spec"]["name"] == "Momentum 12-1"


def test_happy_path_backtest_lifecycle(run_store):
    tenant = new_uuid()
    rid = run_store.create(tenant, "backtest", None, None)
    assert run_store.transition(tenant, rid, "queued")["state"] == "queued"
    assert run_store.transition(tenant, rid, "running")["state"] == "running"
    out = run_store.transition(tenant, rid, "succeeded")
    assert out["state"] == "succeeded"
    assert out["version"] == 3


def test_paper_deployment_lifecycle(run_store):
    tenant = new_uuid()
    rid = run_store.create(tenant, "paper", None, None)
    run_store.transition(tenant, rid, "queued")
    run_store.transition(tenant, rid, "running")
    run_store.transition(tenant, rid, "promoted")
    run_store.transition(tenant, rid, "live")
    run_store.transition(tenant, rid, "paused")
    run_store.transition(tenant, rid, "live")
    out = run_store.transition(tenant, rid, "retired")
    assert out["state"] == "retired"


def test_illegal_transition_raises(run_store):
    tenant = new_uuid()
    rid = run_store.create(tenant, "backtest", None, None)
    with pytest.raises(TransitionError):
        run_store.transition(tenant, rid, "succeeded")  # draft -> succeeded illegal


def test_unknown_target_state_raises(run_store):
    tenant = new_uuid()
    rid = run_store.create(tenant, "backtest", None, None)
    with pytest.raises(TransitionError):
        run_store.transition(tenant, rid, "exploded")


def test_terminal_state_is_terminal(run_store):
    tenant = new_uuid()
    rid = run_store.create(tenant, "backtest", None, None)
    run_store.transition(tenant, rid, "queued")
    run_store.transition(tenant, rid, "running")
    run_store.transition(tenant, rid, "failed")
    with pytest.raises(TransitionError):
        run_store.transition(tenant, rid, "running")


def test_optimistic_version_guard_conflict(run_store):
    tenant = new_uuid()
    rid = run_store.create(tenant, "backtest", None, None)
    run_store.transition(tenant, rid, "queued")  # version now 1
    # A stale writer that read version 0 tries to transition with expect=0.
    with pytest.raises(TransitionConflict):
        run_store.transition(tenant, rid, "running", expect=0)


def test_optimistic_version_guard_success(run_store):
    tenant = new_uuid()
    rid = run_store.create(tenant, "backtest", None, None)
    out = run_store.transition(tenant, rid, "queued", expect=0)
    assert out["version"] == 1
    out = run_store.transition(tenant, rid, "running", expect=1)
    assert out["version"] == 2


def test_transition_missing_run_raises(run_store):
    tenant = new_uuid()
    with pytest.raises(RunNotFound):
        run_store.transition(tenant, new_uuid(), "queued")


def test_tenant_isolation_on_get_and_transition(run_store):
    tenant_a, tenant_b = new_uuid(), new_uuid()
    rid = run_store.create(tenant_a, "backtest", None, None)
    assert run_store.get(tenant_b, rid) is None
    assert run_store.get(tenant_a, rid) is not None
    # Tenant B cannot transition tenant A's run.
    with pytest.raises(RunNotFound):
        run_store.transition(tenant_b, rid, "queued")


def test_list_is_tenant_scoped_and_kind_filtered(run_store):
    tenant_a, tenant_b = new_uuid(), new_uuid()
    run_store.create(tenant_a, "backtest", None, None)
    run_store.create(tenant_a, "paper", None, None)
    run_store.create(tenant_b, "backtest", None, None)
    assert len(run_store.list(tenant_a)) == 2
    assert len(run_store.list(tenant_a, kind="backtest")) == 1
    assert len(run_store.list(tenant_b)) == 1


def test_set_result(run_store):
    tenant = new_uuid()
    rid = run_store.create(tenant, "backtest", None, None)
    run_store.set_result(tenant, rid, {"stats": {"sharpe": 1.2}})
    assert run_store.get(tenant, rid)["result"] == {"stats": {"sharpe": 1.2}}


def test_set_result_tenant_isolation(run_store):
    tenant_a, tenant_b = new_uuid(), new_uuid()
    rid = run_store.create(tenant_a, "backtest", None, None)
    with pytest.raises(RunNotFound):
        run_store.set_result(tenant_b, rid, {"x": 1})


def test_get_missing_returns_none(run_store):
    assert run_store.get(new_uuid(), new_uuid()) is None
