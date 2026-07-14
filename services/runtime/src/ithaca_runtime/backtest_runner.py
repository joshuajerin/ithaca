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
import os
import platform as py_platform
import sys
from pathlib import Path
from typing import Any

from ithaca_core import Core, CoreContext

from ._trace import emit
from .artifact_storage import object_storage_configured, put_artifact
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


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _checkpoint_ref(
    *,
    tenant_id: str,
    run_id: str,
    job_id: str | None,
    phase: str,
    payload: dict[str, Any],
) -> str:
    digest = result_hash({"phase": phase, "payload": payload})
    job_part = job_id or "no-job"
    return f"memory://checkpoints/{tenant_id}/{run_id}/{job_part}/{phase}.json#sha256={digest}"


def _checkpoint(
    *,
    platform: Any,
    tenant_id: str,
    run_id: str,
    job_id: str | None,
    worker_id: str | None,
    phase: str,
    payload: dict[str, Any],
) -> str | None:
    jobs = getattr(platform, "jobs", None)
    if jobs is None or job_id is None:
        return None
    ref = _checkpoint_ref(
        tenant_id=tenant_id,
        run_id=run_id,
        job_id=job_id,
        phase=phase,
        payload=payload,
    )
    jobs.heartbeat(tenant_id, job_id, worker_id=worker_id, checkpoint_ref=ref)
    emit(
        platform.trace,
        tenant_id=tenant_id,
        run_id=run_id,
        type="checkpoint_created",
        data={"job_id": job_id, "phase": phase, "checkpoint_ref": ref},
    )
    return ref


def _artifact_uri(
    tenant_id: str,
    run_id: str,
    filename: str,
    content: bytes,
    sha256: str,
    media_type: str,
) -> tuple[str, bool]:
    if object_storage_configured():
        key = f"backtests/{tenant_id}/{run_id}/{filename}"
        return put_artifact(
            key=key,
            content=content,
            media_type=media_type,
            sha256=sha256,
        ), True
    root = os.environ.get("ITHACA_ARTIFACT_DIR", "").strip()
    if not root:
        return f"memory://backtests/{tenant_id}/{run_id}/{filename}#sha256={sha256}", False
    path = Path(root).expanduser().resolve() / tenant_id / run_id / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path.as_uri(), True


def _html_report(summary: dict[str, Any], metrics: dict[str, Any]) -> bytes:
    title = f"Ithaca backtest {summary['run_id']}"
    body = json.dumps({"summary": summary, "metrics": metrics}, sort_keys=True, indent=2, default=str)
    html = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head><body>"
        f"<h1>{title}</h1><pre>{body}</pre></body></html>"
    )
    return html.encode("utf-8")


def _backtest_artifact_payloads(
    *,
    tenant_id: str,
    run_id: str,
    job_id: str | None,
    worker_id: str | None,
    spec: dict[str, Any] | None,
    range_: str,
    as_of: Any,
    data: dict[str, Any],
    envelope: dict[str, Any],
    rhash: str,
) -> list[dict[str, Any]]:
    metrics = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    equity_curve = data.get("equityCurve") if isinstance(data.get("equityCurve"), list) else []
    final_weights = data.get("finalWeights") if isinstance(data.get("finalWeights"), dict) else {}
    positions = [
        {"symbol": str(symbol), "weight": float(weight)}
        for symbol, weight in sorted(final_weights.items())
    ]
    summary = {
        "tenant_id": tenant_id,
        "run_id": run_id,
        "job_id": job_id,
        "result_hash": rhash,
        "range": range_,
        "as_of": as_of,
        "bars": data.get("bars"),
        "symbols": data.get("symbols") or [],
        "partial": bool(envelope.get("partial")),
        "warning_count": len(envelope.get("warnings") or []),
    }
    data_manifest = {
        "range": range_,
        "as_of": as_of,
        "provenance": envelope.get("provenance") or [],
        "warnings": envelope.get("warnings") or [],
        "spec_hash": result_hash(spec or {}),
        "result_hash": rhash,
    }
    environment_lock = {
        "python": sys.version.split()[0],
        "platform": py_platform.platform(),
        "core_class": "ithaca_core.Core",
        "runtime": "ithaca_runtime.backtest_runner",
        "worker_id": worker_id,
    }
    run_trace = {
        "tenant_id": tenant_id,
        "run_id": run_id,
        "job_id": job_id,
        "worker_id": worker_id,
        "terminal_state": "succeeded",
        "result_hash": rhash,
    }
    artifacts = [
        {
            "filename": "summary.json",
            "kind": "summary",
            "media_type": "application/json",
            "content": _json_bytes(summary),
        },
        {
            "filename": "metrics.json",
            "kind": "metrics",
            "media_type": "application/json",
            "content": _json_bytes(metrics),
        },
        {
            "filename": "equity_curve.json",
            "kind": "equity_curve",
            "media_type": "application/json",
            "content": _json_bytes(equity_curve),
        },
        {
            "filename": "positions.json",
            "kind": "positions",
            "media_type": "application/json",
            "content": _json_bytes(positions),
        },
        {
            "filename": "data_manifest.json",
            "kind": "data_manifest",
            "media_type": "application/json",
            "content": _json_bytes(data_manifest),
        },
        {
            "filename": "environment_lock.json",
            "kind": "environment_lock",
            "media_type": "application/json",
            "content": _json_bytes(environment_lock),
        },
        {
            "filename": "run_trace.json",
            "kind": "run_trace",
            "media_type": "application/json",
            "content": _json_bytes(run_trace),
        },
        {
            "filename": "report.html",
            "kind": "report",
            "media_type": "text/html",
            "content": _html_report(summary, metrics),
        },
    ]
    return artifacts


def _record_backtest_artifacts(
    *,
    platform: Any,
    trace: Any,
    tenant_id: str,
    run_id: str,
    job_id: str | None,
    worker_id: str | None,
    spec: dict[str, Any] | None,
    range_: str,
    as_of: Any,
    data: dict[str, Any],
    envelope: dict[str, Any],
    rhash: str,
) -> list[dict[str, Any]]:
    artifacts_store = getattr(platform, "artifacts", None)
    if artifacts_store is None:
        return []
    recorded: list[dict[str, Any]] = []
    for payload in _backtest_artifact_payloads(
        tenant_id=tenant_id,
        run_id=run_id,
        job_id=job_id,
        worker_id=worker_id,
        spec=spec if isinstance(spec, dict) else None,
        range_=range_,
        as_of=as_of,
        data=data,
        envelope=envelope,
        rhash=rhash,
    ):
        content = payload["content"]
        sha256 = _sha256_bytes(content)
        uri, stored = _artifact_uri(
            tenant_id,
            run_id,
            payload["filename"],
            content,
            sha256,
            payload["media_type"],
        )
        artifact = artifacts_store.create(
            tenant_id,
            run_id,
            job_id=job_id,
            kind=payload["kind"],
            uri=uri,
            media_type=payload["media_type"],
            bytes_=len(content),
            metadata={
                "bundle": "backtest.v1",
                "filename": payload["filename"],
                "sha256": sha256,
                "result_hash": rhash,
                "stored": stored,
            },
        )
        recorded.append(artifact)
        emit(
            trace,
            tenant_id=tenant_id,
            run_id=run_id,
            type="artifact_created",
            data={
                "artifact_id": artifact["artifact_id"],
                "kind": artifact["kind"],
                "filename": payload["filename"],
                "sha256": sha256,
                "bytes": len(content),
                "uri": uri,
            },
        )
    return recorded


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
        _checkpoint(
            platform=platform,
            tenant_id=tenant_id,
            run_id=run_id,
            job_id=job_id,
            worker_id=worker_id,
            phase="loading",
            payload={"range": range_, "as_of": as_of},
        )
        emit(
            trace, tenant_id=tenant_id, run_id=run_id, type="run_progress",
            data={"phase": "loading", "pct": 5, "remaining_ms": dl.remaining_ms()},
        )

        ctx = CoreContext(tenant_id=tenant_id, deadline_ms=dl.remaining_ms())
        if _cancel_if_requested("backtest:precompute"):
            return runs.get(tenant_id, run_id)
        _checkpoint(
            platform=platform,
            tenant_id=tenant_id,
            run_id=run_id,
            job_id=job_id,
            worker_id=worker_id,
            phase="precompute",
            payload={"range": range_, "as_of": as_of},
        )
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
        _checkpoint(
            platform=platform,
            tenant_id=tenant_id,
            run_id=run_id,
            job_id=job_id,
            worker_id=worker_id,
            phase="postcompute",
            payload={"result_hash": rhash},
        )
        artifacts = _record_backtest_artifacts(
            platform=platform,
            trace=trace,
            tenant_id=tenant_id,
            run_id=run_id,
            job_id=job_id,
            worker_id=worker_id,
            spec=spec if isinstance(spec, dict) else None,
            range_=range_,
            as_of=as_of,
            data=data,
            envelope=envelope,
            rhash=rhash,
        )
        stored = {
            "data": data,
            "provenance": envelope.get("provenance"),
            "partial": bool(envelope.get("partial")),
            "warnings": envelope.get("warnings") or [],
            "result_hash": rhash,
            "artifacts": [
                {
                    "artifact_id": artifact["artifact_id"],
                    "kind": artifact["kind"],
                    "uri": artifact["uri"],
                    "sha256": artifact["metadata"].get("sha256"),
                }
                for artifact in artifacts
            ],
        }
        _checkpoint(
            platform=platform,
            tenant_id=tenant_id,
            run_id=run_id,
            job_id=job_id,
            worker_id=worker_id,
            phase="persisted",
            payload={
                "result_hash": rhash,
                "artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
            },
        )
        emit(
            trace, tenant_id=tenant_id, run_id=run_id, type="run_progress",
            data={"phase": "persisting", "pct": 90, "remaining_ms": dl.remaining_ms()},
        )
        runs.set_result(tenant_id, run_id, stored)
        if jobs is not None and job_id is not None:
            jobs.complete(
                tenant_id,
                job_id,
                worker_id=worker_id,
                result={
                    "result_hash": rhash,
                    "artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
                },
            )
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
