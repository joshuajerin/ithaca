"""Backtest worker: ``run_backtest_job``.

Pulls a queued run + its spec from the platform, transitions it to ``running``,
executes ``core.backtest_run`` under an AGGREGATE wall-clock deadline, streams a
few ``run_progress`` trace events, persists the result, and transitions to
``succeeded``. On a deadline breach it transitions to ``timeout`` (with whatever
partial info we have) and emits an ``error`` event; on any other exception it
transitions to ``failed`` and emits an ``error`` event. It NEVER swallows a
failure on the audited path.

Determinism: ``run_backtest`` is pure numpy seeded by ``spec.seed`` over a fixed
window, so the same (spec, seed, window) yields the same result. We compute a
stable ``result_hash`` over the canonical result JSON and stamp it into the stored
result + the terminal trace event so "reproduce this run" is a hash comparison.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from doomberg_core import Core, CoreContext

from ._trace import emit
from .deadline import Deadline, DeadlineExceeded

__all__ = ["run_backtest_job", "result_hash", "DEFAULT_BUDGET_MS"]

# Default aggregate wall-clock budget for a backtest job (override per-call).
DEFAULT_BUDGET_MS = 30_000


def result_hash(result: dict[str, Any]) -> str:
    """Stable content hash of a backtest result (canonical JSON, sorted keys).

    Determinism contract: identical (spec, seed, window) => identical result =>
    identical hash. Used to verify reproducibility.
    """
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_backtest_job(
    tenant_id: str,
    run_id: str,
    *,
    platform: Any,
    core: Core,
    budget_ms: int = DEFAULT_BUDGET_MS,
    deadline: Deadline | None = None,
    job_id: str | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    """Execute the backtest for ``run_id`` end-to-end. Returns the final run row.

    ``platform`` exposes ``.runs`` (RunStore) and ``.trace`` (TraceStore), both
    tenant-scoped. The run must be in ``queued`` (the control plane enqueues it).
    """
    tenant_id = str(tenant_id)
    run_id = str(run_id)
    runs = platform.runs
    trace = platform.trace
    jobs = getattr(platform, "jobs", None)
    dl = deadline or Deadline.from_ms(budget_ms)

    def _cancel_if_requested(stage: str) -> bool:
        if jobs is None or job_id is None:
            return False
        job = jobs.get(tenant_id, job_id)
        run_row = runs.get(tenant_id, run_id)
        if (job and job["state"] == "cancelled") or (run_row and run_row["state"] == "cancelled"):
            if run_row and run_row["state"] == "running":
                runs.cancel(tenant_id, run_id, expect=run_row["version"])
            emit(
                trace, tenant_id=tenant_id, run_id=run_id, type="run_transition",
                data={"from": run_row.get("state") if run_row else None, "to": "cancelled",
                      "stage": stage, "job_id": job_id},
            )
            return True
        return False

    if jobs is not None and job_id is not None:
        job = jobs.get(tenant_id, job_id)
        if job is not None and job["state"] == "cancelled":
            emit(
                trace, tenant_id=tenant_id, run_id=run_id, type="run_transition",
                data={"to": "cancelled", "job_id": job_id, "reason": "job cancelled before start"},
            )
            return runs.get(tenant_id, run_id)
        jobs.mark_running(tenant_id, job_id, worker_id=worker_id)

    run = runs.get(tenant_id, run_id)
    if run is None:
        # Nothing to transition; emit an error so the absence is audited, then raise.
        emit(
            trace, tenant_id=tenant_id, run_id=run_id, type="error",
            data={"stage": "load", "error": "run not found"},
        )
        raise KeyError(f"run not found: {run_id}")

    spec = run.get("spec")
    range_ = "1y"
    as_of = None
    if jobs is not None and job_id is not None:
        job = jobs.get(tenant_id, job_id)
        payload = job.get("payload") if job else None
        if isinstance(payload, dict):
            range_ = payload.get("range", range_) or range_
            as_of = payload.get("as_of", as_of)
            spec = payload.get("spec", spec)
    # Range/as_of may be carried on the spec wrapper; tolerate either shape.
    if isinstance(spec, dict):
        range_ = spec.get("range", spec.get("_range", range_)) or range_
        as_of = spec.get("as_of", spec.get("_as_of", as_of))

    # queued -> running (optimistic guard on the version we just read).
    if run["state"] == "cancelled":
        if jobs is not None and job_id is not None:
            jobs.cancel(tenant_id, job_id, reason="run cancelled before start")
        emit(
            trace, tenant_id=tenant_id, run_id=run_id, type="run_transition",
            data={"to": "cancelled", "reason": "run cancelled before start"},
        )
        return run

    running = runs.transition(tenant_id, run_id, "running", expect=run["version"])
    emit(
        trace, tenant_id=tenant_id, run_id=run_id, type="run_transition",
        data={"from": run["state"], "to": "running", "job_id": job_id},
    )

    try:
        dl.check("backtest:start")
        if _cancel_if_requested("backtest:start"):
            return runs.get(tenant_id, run_id)
        if jobs is not None and job_id is not None:
            jobs.heartbeat(tenant_id, job_id, worker_id=worker_id)
        emit(
            trace, tenant_id=tenant_id, run_id=run_id, type="run_progress",
            data={"phase": "loading", "pct": 5, "remaining_ms": dl.remaining_ms()},
        )

        ctx = CoreContext(tenant_id=tenant_id, deadline_ms=dl.remaining_ms())
        if _cancel_if_requested("backtest:precompute"):
            return runs.get(tenant_id, run_id)
        if jobs is not None and job_id is not None:
            jobs.heartbeat(tenant_id, job_id, worker_id=worker_id)
        emit(
            trace, tenant_id=tenant_id, run_id=run_id, type="run_progress",
            data={"phase": "computing", "pct": 40, "remaining_ms": dl.remaining_ms()},
        )

        envelope = core.backtest_run({"spec": spec, "range": range_, "as_of": as_of}, ctx)

        # Core finished — but if our aggregate budget blew during the call, honour it.
        dl.check("backtest:postcompute")
        if _cancel_if_requested("backtest:postcompute"):
            return runs.get(tenant_id, run_id)

        data = envelope.get("data")
        if data is None:
            # Core produced no result (e.g. insufficient data) — a real failure.
            warnings = envelope.get("warnings") or []
            runs.transition(tenant_id, run_id, "failed", expect=running["version"])
            if jobs is not None and job_id is not None:
                jobs.fail(
                    tenant_id,
                    job_id,
                    worker_id=worker_id,
                    error={"code": "NO_RESULT_DATA", "warnings": warnings},
                )
            emit(
                trace, tenant_id=tenant_id, run_id=run_id, type="error",
                data={"stage": "backtest", "error": "no result data", "warnings": warnings},
            )
            emit(
                trace, tenant_id=tenant_id, run_id=run_id, type="run_transition",
                data={"from": "running", "to": "failed"},
            )
            return runs.get(tenant_id, run_id)

        rhash = result_hash(data)
        stored = {
            "data": data,
            "provenance": envelope.get("provenance"),
            "partial": bool(envelope.get("partial")),
            "warnings": envelope.get("warnings") or [],
            "result_hash": rhash,
        }
        emit(
            trace, tenant_id=tenant_id, run_id=run_id, type="run_progress",
            data={"phase": "persisting", "pct": 90, "remaining_ms": dl.remaining_ms()},
        )
        runs.set_result(tenant_id, run_id, stored)
        if jobs is not None and job_id is not None:
            jobs.complete(tenant_id, job_id, worker_id=worker_id, result={"result_hash": rhash})
        runs.transition(tenant_id, run_id, "succeeded", expect=running["version"])
        emit(
            trace, tenant_id=tenant_id, run_id=run_id, type="run_transition",
            data={"from": "running", "to": "succeeded", "result_hash": rhash,
                  "job_id": job_id},
        )
        return runs.get(tenant_id, run_id)

    except DeadlineExceeded as exc:
        # Aggregate budget blown: transition -> timeout with partial info, emit error.
        partial = {"timeout": True, "elapsed_ms": dl.elapsed_s() * 1000.0, "budget_ms": budget_ms}
        try:
            runs.set_result(tenant_id, run_id, partial)
            if jobs is not None and job_id is not None:
                jobs.time_out(
                    tenant_id,
                    job_id,
                    worker_id=worker_id,
                    error={"code": "DEADLINE_EXCEEDED", "detail": str(exc)},
                )
        finally:
            cur = runs.get(tenant_id, run_id)
            runs.transition(tenant_id, run_id, "timeout", expect=cur["version"])
            emit(
                trace, tenant_id=tenant_id, run_id=run_id, type="error",
                data={"stage": "backtest", "error": "deadline_exceeded", "detail": str(exc)},
            )
            emit(
                trace, tenant_id=tenant_id, run_id=run_id, type="run_transition",
                data={"from": "running", "to": "timeout"},
            )
        return runs.get(tenant_id, run_id)

    except Exception as exc:  # noqa: BLE001 — audited: we re-emit + transition, never swallow.
        cur = runs.get(tenant_id, run_id)
        if cur is not None and cur["state"] == "running":
            runs.transition(tenant_id, run_id, "failed", expect=cur["version"])
            if jobs is not None and job_id is not None:
                jobs.fail(
                    tenant_id,
                    job_id,
                    worker_id=worker_id,
                    error={"code": type(exc).__name__, "detail": str(exc)[:500]},
                )
            emit(
                trace, tenant_id=tenant_id, run_id=run_id, type="error",
                data={"stage": "backtest", "error": type(exc).__name__, "detail": str(exc)[:500]},
            )
            emit(
                trace, tenant_id=tenant_id, run_id=run_id, type="run_transition",
                data={"from": "running", "to": "failed"},
            )
        else:
            emit(
                trace, tenant_id=tenant_id, run_id=run_id, type="error",
                data={"stage": "backtest", "error": type(exc).__name__, "detail": str(exc)[:500]},
            )
        raise
