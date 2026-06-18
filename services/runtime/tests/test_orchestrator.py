"""Conductor tests: the backtest worker drains the queue; the paper scheduler ticks
live deployments and routes proposed deltas to the injected single-writer applier."""

from __future__ import annotations

import datetime as dt

from doomberg_runtime import AlwaysOpen, BacktestWorker, PaperScheduler, RegularHoursCalendar

from conftest import seed_queued_run


def _make_live_paper(platform, tenant_id, spec):
    run_id = seed_queued_run(platform, tenant_id, spec, kind="paper")
    platform.runs.transition(tenant_id, run_id, "running", expect=1)
    platform.runs.transition(tenant_id, run_id, "promoted", expect=2)
    platform.runs.transition(tenant_id, run_id, "live", expect=3)
    return run_id


def _applier(platform):
    """A minimal single-writer applier double: re-prices the book to the proposal target."""
    def apply_delta(tenant_id, run_id, proposal):
        book = platform.books.ensure(tenant_id, run_id)
        updated = platform.books.apply(
            tenant_id, run_id,
            target_weights=proposal["targetWeights"], marks=proposal.get("marks"),
            expect=book["version"],
        )
        return {"applied": True, "book": updated}
    return apply_delta


# --- backtest worker --------------------------------------------------------------------

def test_backtest_worker_drains_queue_to_succeeded(platform, tenant_id, spec, core):
    """A queued backtest is executed end-to-end with NO manual run_backtest_job call."""
    run_id = seed_queued_run(platform, tenant_id, spec, kind="backtest")
    worker = BacktestWorker(platform, core)

    summary = worker.poll_once()

    assert summary["claimed"] == 1
    assert summary["succeeded"] == [run_id]
    assert platform.runs.get(tenant_id, run_id)["state"] == "succeeded"
    # The run carries a stored result + a gap-free trace ending in succeeded.
    assert platform.runs.get(tenant_id, run_id)["result"] is not None
    assert "run_transition" in platform.trace.types(run_id)


def test_backtest_worker_ignores_paper_runs(platform, tenant_id, spec, core):
    _make_live_paper(platform, tenant_id, spec)               # live paper, not queued
    seed_queued_run(platform, tenant_id, spec, kind="paper")  # queued but kind=paper
    worker = BacktestWorker(platform, core)
    summary = worker.poll_once()
    assert summary["claimed"] == 0


def test_backtest_worker_empty_queue_is_noop(platform, core):
    assert BacktestWorker(platform, core).poll_once() == {
        "claimed": 0, "succeeded": [], "skipped": []
    }


# --- paper scheduler --------------------------------------------------------------------

def test_paper_scheduler_ticks_live_and_applies_delta(platform, tenant_id, spec, core):
    run_id = _make_live_paper(platform, tenant_id, spec)
    sched = PaperScheduler(platform, core, _applier(platform), calendar=AlwaysOpen())

    results = sched.tick_once()

    assert len(results) == 1
    res = results[0]
    assert res["run_id"] == run_id
    assert res["proposal"]["action"] == "propose"
    assert res["applied"]["applied"] is True
    # The book was actually written (version bumped, weights set to the target).
    book = platform.books.get(tenant_id, run_id)
    assert book["version"] == 1
    assert book["weights"] == res["proposal"]["targetWeights"]


def test_paper_scheduler_skips_when_market_closed(platform, tenant_id, spec, core):
    _make_live_paper(platform, tenant_id, spec)
    # A Saturday -> RegularHoursCalendar reports closed -> no ticks at all.
    saturday = dt.datetime(2026, 6, 13, 15, 0, tzinfo=dt.timezone.utc)
    sched = PaperScheduler(platform, core, _applier(platform), calendar=RegularHoursCalendar())
    assert sched.tick_once(now=saturday) == []


def test_paper_scheduler_does_not_apply_on_stale_skip(platform, tenant_id, spec, core):
    run_id = _make_live_paper(platform, tenant_id, spec)
    calls: list = []

    def spy(tenant, rid, proposal):
        calls.append(rid)
        return {"applied": True}

    sched = PaperScheduler(platform, core, spy, calendar=AlwaysOpen(), max_staleness_s=1.0)
    far_future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=400)
    results = sched.tick_once(now=far_future)

    assert results[0]["proposal"]["action"] == "skip"
    assert results[0]["applied"] is None
    assert calls == []  # applier never invoked on a stale skip
    assert platform.books.get(tenant_id, run_id) is None  # no book written
