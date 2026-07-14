"""Conductor-only reads: create_research, claim_queued, list_by_state (cross-tenant)."""

from __future__ import annotations

import uuid

from ithaca_platform import RunStore


def _spec(name: str = "demo") -> dict:
    return {"name": name, "universe": {"symbols": ["AAA"], "source": "prices"}}


def _queue(store: RunStore, tenant: str, kind: str) -> str:
    run_id = store.create(tenant, kind, str(uuid.uuid4()), _spec())
    store.transition(tenant, run_id, "queued", expect=0)
    return run_id


def test_create_research_opens_running_research_run(run_store):
    t = str(uuid.uuid4())
    run_id = run_store.create_research(t)
    row = run_store.get(t, run_id)
    assert row["kind"] == "research"
    assert row["state"] == "running"
    assert row["version"] == 0
    # Closeable with the normal running -> succeeded transition.
    closed = run_store.transition(t, run_id, "succeeded", expect=0)
    assert closed["state"] == "succeeded"


def test_claim_queued_returns_queued_backtests_cross_tenant(run_store):
    ta, tb = str(uuid.uuid4()), str(uuid.uuid4())
    ra = _queue(run_store, ta, "backtest")
    rb = _queue(run_store, tb, "backtest")
    _queue(run_store, ta, "paper")  # different kind -> excluded by default

    claimed = run_store.claim_queued(("backtest",))
    ids = {r["run_id"] for r in claimed}
    assert ids == {ra, rb}
    # Each row carries its own tenant so the worker stays tenant-aware.
    assert {r["tenant_id"] for r in claimed} == {ta, tb}


def test_claim_queued_respects_limit_and_kinds(run_store):
    t = str(uuid.uuid4())
    for _ in range(3):
        _queue(run_store, t, "backtest")
    assert len(run_store.claim_queued(("backtest",), limit=2)) == 2
    # paper kind requested explicitly
    rp = _queue(run_store, t, "paper")
    paper = run_store.claim_queued(("paper",))
    assert [r["run_id"] for r in paper] == [rp]


def test_list_by_state_finds_live_paper_runs(run_store):
    t = str(uuid.uuid4())
    run_id = _queue(run_store, t, "paper")
    run_store.transition(t, run_id, "running", expect=1)
    run_store.transition(t, run_id, "promoted", expect=2)
    run_store.transition(t, run_id, "live", expect=3)

    live = run_store.list_by_state("live", kind="paper")
    assert [r["run_id"] for r in live] == [run_id]
    assert run_store.list_by_state("live", kind="backtest") == []
