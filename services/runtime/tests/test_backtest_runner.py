"""Tests for run_backtest_job: result+succeeded, deadline->timeout, determinism, no-swallow."""

from __future__ import annotations

import uuid

import pytest

from doomberg_runtime import result_hash, run_backtest_job
from doomberg_runtime.deadline import Deadline

from conftest import Platform, seed_queued_run


def test_backtest_writes_result_and_succeeds(platform, tenant_id, spec, core):
    run_id = seed_queued_run(platform, tenant_id, spec)

    row = run_backtest_job(tenant_id, run_id, platform=platform, core=core)

    assert row["state"] == "succeeded"
    result = row["result"]
    assert result is not None
    assert "equityCurve" in result["data"]
    assert "stats" in result["data"]
    assert result["result_hash"]
    # Trace stream: running transition, progress events, succeeded transition.
    types = platform.trace.types(run_id)
    assert types[0] == "run_transition"
    assert "run_progress" in types
    assert types[-1] == "run_transition"
    assert platform.trace.events_by_run[run_id][-1]["data"]["to"] == "succeeded"


def test_backtest_is_deterministic_same_spec_seed_window(platform, tenant_id, spec, core):
    """Same spec+seed+window => identical result hash (reproducibility contract)."""
    r1 = seed_queued_run(platform, tenant_id, spec)
    r2 = seed_queued_run(platform, tenant_id, spec)

    row1 = run_backtest_job(tenant_id, r1, platform=platform, core=core)
    row2 = run_backtest_job(tenant_id, r2, platform=platform, core=core)

    assert row1["result"]["result_hash"] == row2["result"]["result_hash"]
    # And the hash is the canonical hash of the data payload.
    assert row1["result"]["result_hash"] == result_hash(row1["result"]["data"])


def test_deadline_breach_transitions_to_timeout(platform, tenant_id, spec, core):
    """An already-exhausted aggregate deadline -> timeout + error event, never succeeded."""
    # A clock that has already blown the budget the instant the job starts.
    clock = iter([0.0] + [100.0] * 50)
    dl = Deadline.from_ms(1_000, clock=lambda: next(clock))

    row = run_backtest_job(tenant_id, seed_queued_run(platform, tenant_id, spec),
                           platform=platform, core=core, deadline=dl)

    assert row["state"] == "timeout"
    assert row["result"]["timeout"] is True
    types = platform.trace.types(row["run_id"])
    assert "error" in types
    err = [e for e in platform.trace.events_by_run[row["run_id"]] if e["type"] == "error"][0]
    assert err["data"]["error"] == "deadline_exceeded"
    # Terminal trace transition is timeout, not succeeded.
    assert platform.trace.events_by_run[row["run_id"]][-1]["data"]["to"] == "timeout"


def test_backtest_failure_emits_error_and_reraises(platform, tenant_id, spec):
    """Core raising -> run goes failed, an error event is emitted, and we re-raise (no swallow)."""
    class _BoomCore:
        def backtest_run(self, args, ctx=None):
            raise RuntimeError("kaboom")

    run_id = seed_queued_run(platform, tenant_id, spec)
    with pytest.raises(RuntimeError, match="kaboom"):
        run_backtest_job(tenant_id, run_id, platform=platform, core=_BoomCore())

    row = platform.runs.get(tenant_id, run_id)
    assert row["state"] == "failed"
    types = platform.trace.types(run_id)
    assert "error" in types


def test_missing_run_emits_error_and_raises(platform, tenant_id, core):
    missing = str(uuid.uuid4())
    with pytest.raises(KeyError):
        run_backtest_job(tenant_id, missing, platform=platform, core=core)
    assert "error" in platform.trace.types(missing)


def test_tenant_isolation_other_tenant_cannot_see_run(platform, tenant_id, spec, core):
    run_id = seed_queued_run(platform, tenant_id, spec)
    run_backtest_job(tenant_id, run_id, platform=platform, core=core)
    other = str(uuid.uuid4())
    assert platform.runs.get(other, run_id) is None
