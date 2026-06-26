"""Tests for run_backtest_job: result+succeeded, deadline->timeout, determinism, no-swallow."""

from __future__ import annotations

import hashlib
import urllib.parse
import uuid
from pathlib import Path

import pytest

from doomberg_runtime import result_hash, run_backtest_job
from doomberg_runtime.deadline import Deadline

from runtime_helpers import seed_queued_run


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


def test_backtest_records_canonical_artifact_bundle(durable_platform, tenant_id, spec, core, tmp_path, monkeypatch):
    monkeypatch.setenv("DOOMBERG_ARTIFACT_DIR", str(tmp_path))
    run_id = seed_queued_run(durable_platform, tenant_id, spec)
    job = durable_platform.jobs.create_for_run(
        tenant_id,
        run_id,
        kind="backtest",
        profile="backtest",
        payload={"spec": spec, "range": "1y"},
    )

    row = run_backtest_job(
        tenant_id,
        run_id,
        platform=durable_platform,
        core=core,
        job_id=job["job_id"],
        worker_id="worker-artifacts",
    )

    assert row["state"] == "succeeded"
    artifacts = durable_platform.artifacts.list_by_run(tenant_id, run_id)
    by_file = {artifact["metadata"]["filename"]: artifact for artifact in artifacts}
    assert set(by_file) == {
        "summary.json",
        "metrics.json",
        "equity_curve.json",
        "positions.json",
        "data_manifest.json",
        "environment_lock.json",
        "run_trace.json",
        "report.html",
    }
    assert row["result"]["artifacts"]
    assert {item["artifact_id"] for item in row["result"]["artifacts"]} == {
        artifact["artifact_id"] for artifact in artifacts
    }
    for artifact in artifacts:
        parsed = urllib.parse.urlparse(artifact["uri"])
        assert parsed.scheme == "file"
        path = Path(urllib.parse.unquote(parsed.path))
        content = path.read_bytes()
        assert path.is_file()
        assert len(content) == artifact["bytes"]
        assert hashlib.sha256(content).hexdigest() == artifact["metadata"]["sha256"]
        assert artifact["metadata"]["bundle"] == "backtest.v1"
        assert artifact["metadata"]["stored"] is True
    events = durable_platform.trace.events(tenant_id, run_id)
    assert [event["type"] for event in events].count("artifact_created") == len(artifacts)
    checkpoints = [event for event in events if event["type"] == "checkpoint_created"]
    assert [event["data"]["phase"] for event in checkpoints] == [
        "loading",
        "precompute",
        "postcompute",
        "persisted",
    ]
    done_job = durable_platform.jobs.get(tenant_id, job["job_id"])
    assert set(done_job["result"]["artifact_ids"]) == {artifact["artifact_id"] for artifact in artifacts}
    assert done_job["checkpoint_ref"].startswith(
        f"memory://checkpoints/{tenant_id}/{run_id}/{job['job_id']}/persisted.json"
    )


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
