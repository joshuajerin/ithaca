"""The deploy-layer conductor: who actually pulls the queue and drives the loops.

The control plane only *enqueues* (lands a run in ``queued``) and *gates*; the runtime
workers are stateless jobs (:func:`run_backtest_job`, :func:`run_paper_tick`). Nothing in
either drives them on a cadence. This module is the conductor that closes that gap:

- :class:`BacktestWorker` polls the platform for ``queued`` backtest runs and executes each.
  Claiming is the optimistic ``queued -> running`` transition inside the job, so two workers
  never double-run a job — the loser just moves on.

- :class:`PaperScheduler` finds ``live`` paper deployments, runs one stateless paper tick
  per deployment, and hands any proposed book delta to an INJECTED ``apply_delta`` callable.
  The applier is the control plane's single-writer money path (``doomberg_control.money``);
  injecting it keeps the runtime decoupled from the control plane (runtime depends only on
  ``doomberg-core`` + ``doomberg-contracts``).

Both expose a single-shot method (``poll_once`` / ``tick_once``) for tests and CI, plus a
``run_forever`` loop with a stop-aware sleep for the local dev process / a DO worker pod.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Any, Callable

from doomberg_core import Core, CoreContext
from doomberg_core.skills import SKILLS, SkillSet

from ._trace import emit
from .backtest_runner import DEFAULT_BUDGET_MS as BACKTEST_BUDGET_MS
from .backtest_runner import run_backtest_job
from .calendar import MarketCalendar
from .live_runner import DEFAULT_BUDGET_MS as PAPER_BUDGET_MS
from .live_runner import DEFAULT_MAX_STALENESS_S, run_paper_tick

__all__ = ["BacktestWorker", "TriggerJobWorker", "PaperScheduler", "ApplyDelta"]

# (tenant_id, run_id, proposal) -> apply result dict. The control plane provides this.
ApplyDelta = Callable[[str, str, dict[str, Any]], dict[str, Any]]


class BacktestWorker:
    """Polls ``queued`` backtest runs and executes them via ``run_backtest_job``."""

    def __init__(
        self,
        platform: Any,
        core: Core,
        *,
        budget_ms: int = BACKTEST_BUDGET_MS,
        batch: int = 16,
    ) -> None:
        self.platform = platform
        self.core = core
        self.budget_ms = budget_ms
        self.batch = batch
        self.worker_id = f"backtest-{uuid.uuid4().hex[:12]}"

    def poll_once(self) -> dict[str, Any]:
        """Claim + run all currently-queued backtests. Returns a summary, never raises.

        A run that another worker already claimed (lost optimistic race) or that the job
        failed lands in ``skipped`` — the job itself has already audited a hard failure with
        an ``error`` trace, so the loop must not die on it.
        """
        jobs = getattr(self.platform, "jobs", None)
        if jobs is not None:
            exhausted = jobs.fail_exhausted(profiles=("backtest",), kinds=("backtest",))
            for job in exhausted:
                run = self.platform.runs.get(job["tenant_id"], job["run_id"])
                if run and run.get("state") in {"queued", "running"}:
                    self.platform.runs.transition(
                        job["tenant_id"], job["run_id"], "failed", expect=run["version"]
                    )
                    emit(
                        self.platform.trace,
                        tenant_id=job["tenant_id"],
                        run_id=job["run_id"],
                        type="error",
                        data={
                            "stage": "worker",
                            "error": "retry_exhausted",
                            "job_id": job["job_id"],
                        },
                    )
            claimed = jobs.claim_available(
                profiles=("backtest",),
                kinds=("backtest",),
                worker_id=self.worker_id,
                limit=self.batch,
            )
            result = self._run_claimed_jobs(claimed)
            result["exhausted"] = [job["job_id"] for job in exhausted]
            return result

        claimed = self.platform.runs.claim_queued(("backtest",), limit=self.batch)
        succeeded: list[str] = []
        skipped: list[dict[str, Any]] = []
        for row in claimed:
            tenant_id, run_id = row["tenant_id"], row["run_id"]
            try:
                run = run_backtest_job(
                    tenant_id, run_id,
                    platform=self.platform, core=self.core, budget_ms=self.budget_ms,
                )
                if run and run.get("state") == "succeeded":
                    succeeded.append(run_id)
                else:
                    skipped.append({"run_id": run_id, "state": run.get("state") if run else None})
            except Exception as exc:  # noqa: BLE001 — lost race / audited failure; keep looping.
                skipped.append({"run_id": run_id, "error": type(exc).__name__})
        return {"claimed": len(claimed), "succeeded": succeeded, "skipped": skipped}

    def _run_claimed_jobs(self, claimed: list[dict[str, Any]]) -> dict[str, Any]:
        succeeded: list[str] = []
        skipped: list[dict[str, Any]] = []
        for job in claimed:
            tenant_id, run_id = job["tenant_id"], job["run_id"]
            try:
                run = run_backtest_job(
                    tenant_id,
                    run_id,
                    platform=self.platform,
                    core=self.core,
                    budget_ms=self.budget_ms,
                    job_id=job["job_id"],
                    worker_id=self.worker_id,
                )
                if run and run.get("state") == "succeeded":
                    succeeded.append(run_id)
                else:
                    skipped.append({
                        "run_id": run_id,
                        "job_id": job["job_id"],
                        "state": run.get("state") if run else None,
                    })
            except Exception as exc:  # noqa: BLE001 — lost race / audited failure; keep looping.
                skipped.append({"run_id": run_id, "job_id": job["job_id"],
                                "error": type(exc).__name__})
        return {"claimed": len(claimed), "succeeded": succeeded, "skipped": skipped}

    def run_forever(self, *, interval_s: float = 1.0, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        while not stop.is_set():
            self.poll_once()
            stop.wait(interval_s)


class TriggerJobWorker:
    """Executes non-inline trigger analysis jobs.

    The trigger engine completes quote/snapshot actions inline because it already holds the
    live quote. Richer read/analysis actions are queued as ``kind=trigger`` and claimed here so
    they cannot sit forever. This worker never submits broker orders; execution remains an
    approval-gated gateway concern.
    """

    def __init__(
        self,
        platform: Any,
        core: Core,
        *,
        archive: Any | None = None,
        batch: int = 16,
    ) -> None:
        self.platform = platform
        self.core = core
        self.skills = SkillSet(archive)
        self.batch = batch
        self.worker_id = f"trigger-{uuid.uuid4().hex[:12]}"

    def poll_once(self) -> dict[str, Any]:
        jobs = getattr(self.platform, "jobs", None)
        if jobs is None:
            return {"claimed": 0, "succeeded": [], "failed": []}
        claimed = jobs.claim_available(
            profiles=("interactive",),
            kinds=("trigger",),
            worker_id=self.worker_id,
            limit=self.batch,
        )
        succeeded: list[str] = []
        failed: list[dict[str, Any]] = []
        for job in claimed:
            try:
                run = self._run_job(job)
                if run and run.get("state") == "succeeded":
                    succeeded.append(job["run_id"])
                else:
                    failed.append({
                        "run_id": job["run_id"],
                        "job_id": job["job_id"],
                        "state": run.get("state") if run else None,
                    })
            except Exception as exc:  # noqa: BLE001 - audited inside _run_job when possible.
                failed.append({
                    "run_id": job["run_id"],
                    "job_id": job["job_id"],
                    "error": type(exc).__name__,
                })
        return {"claimed": len(claimed), "succeeded": succeeded, "failed": failed}

    def _run_job(self, job: dict[str, Any]) -> dict[str, Any] | None:
        jobs = self.platform.jobs
        tenant_id = job["tenant_id"]
        run_id = job["run_id"]
        job_id = job["job_id"]
        jobs.mark_running(tenant_id, job_id, worker_id=self.worker_id)
        run = self.platform.runs.get(tenant_id, run_id)
        if run is None:
            jobs.fail(
                tenant_id,
                job_id,
                worker_id=self.worker_id,
                error={"code": "INVALID_SYMBOL", "detail": "run not found"},
            )
            return None

        running = run
        if run.get("state") == "queued":
            running = self.platform.runs.transition(
                tenant_id,
                run_id,
                "running",
                expect=run["version"],
            )
            emit(
                self.platform.trace,
                tenant_id=tenant_id,
                run_id=run_id,
                type="run_transition",
                actor={"kind": "system", "id": self.worker_id},
                data={"from": "queued", "to": "running", "job_id": job_id},
            )

        payload = job.get("payload") or {}
        action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        skill_id = str(action.get("run_skill") or "market.get_ohlcv")
        params = dict(action.get("input") or action.get("args") or {})
        symbol = context.get("symbol")
        if symbol:
            params.setdefault("symbol", symbol)
            params.setdefault("ticker", symbol)

        emit(
            self.platform.trace,
            tenant_id=tenant_id,
            run_id=run_id,
            type="tool_call",
            actor={"kind": "system", "id": self.worker_id},
            data={"name": skill_id, "args": params, "job_id": job_id},
        )

        try:
            result = self._call_skill(skill_id, params, tenant_id=tenant_id)
        except Exception as exc:  # noqa: BLE001 - materialized in run result + trace.
            err = {
                "code": "PROVIDER_DEGRADED",
                "message": f"{skill_id} failed: {type(exc).__name__}",
                "recovery_action": "Inspect the trigger run trace and retry after provider or input repair.",
                "details": {"detail": str(exc)[:500], "skill_id": skill_id},
            }
            self.platform.runs.set_result(tenant_id, run_id, {"error": err})
            jobs.fail(tenant_id, job_id, worker_id=self.worker_id, error=err)
            cur = self.platform.runs.get(tenant_id, run_id)
            if cur and cur.get("state") == "running":
                self.platform.runs.transition(tenant_id, run_id, "failed", expect=cur["version"])
            emit(
                self.platform.trace,
                tenant_id=tenant_id,
                run_id=run_id,
                type="error",
                actor={"kind": "system", "id": self.worker_id},
                data={"stage": "trigger_job", "error": type(exc).__name__, "detail": str(exc)[:500]},
            )
            emit(
                self.platform.trace,
                tenant_id=tenant_id,
                run_id=run_id,
                type="run_transition",
                actor={"kind": "system", "id": self.worker_id},
                data={"from": "running", "to": "failed", "job_id": job_id},
            )
            return self.platform.runs.get(tenant_id, run_id)

        self.platform.runs.set_result(tenant_id, run_id, result)
        jobs.complete(tenant_id, job_id, worker_id=self.worker_id, result={"skill_id": skill_id})
        self.platform.runs.transition(tenant_id, run_id, "succeeded", expect=running["version"])
        emit(
            self.platform.trace,
            tenant_id=tenant_id,
            run_id=run_id,
            type="tool_result",
            actor={"kind": "system", "id": self.worker_id},
            data={"name": skill_id, "job_id": job_id, "summary": self._summary(result)},
        )
        emit(
            self.platform.trace,
            tenant_id=tenant_id,
            run_id=run_id,
            type="run_transition",
            actor={"kind": "system", "id": self.worker_id},
            data={"from": "running", "to": "succeeded", "job_id": job_id},
        )
        return self.platform.runs.get(tenant_id, run_id)

    def _call_skill(self, skill_id: str, params: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
        if skill_id == "market.get_ohlcv":
            return self.core.run_tool(
                "market.get_ohlcv",
                params,
                CoreContext(tenant_id=tenant_id, actor_id=self.worker_id),
            )
        method = SKILLS.get(skill_id)
        if method is None:
            raise ValueError(f"unsupported trigger skill: {skill_id}")
        return getattr(self.skills, method)(params)

    @staticmethod
    def _summary(result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {"type": type(result).__name__}
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        return {
            "source": (result.get("provenance") or {}).get("source"),
            "keys": sorted(list(data.keys()))[:8] if isinstance(data, dict) else [],
            "warnings": len(result.get("warnings") or []),
        }

    def run_forever(self, *, interval_s: float = 2.0, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        while not stop.is_set():
            self.poll_once()
            stop.wait(interval_s)


class PaperScheduler:
    """Ticks every ``live`` paper deployment and applies proposed deltas via ``apply_delta``."""

    def __init__(
        self,
        platform: Any,
        core: Core,
        apply_delta: ApplyDelta,
        *,
        calendar: MarketCalendar | None = None,
        capital: float = 100_000.0,
        budget_ms: int = PAPER_BUDGET_MS,
        max_staleness_s: float = DEFAULT_MAX_STALENESS_S,
    ) -> None:
        self.platform = platform
        self.core = core
        self.apply_delta = apply_delta
        self.calendar = calendar
        self.capital = capital
        self.budget_ms = budget_ms
        self.max_staleness_s = max_staleness_s

    def tick_once(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Run one tick over all live paper runs. Returns a per-run result list.

        If a calendar is configured and the market is closed, returns ``[]`` (no ticks).
        A per-run failure is captured into that run's result, never aborting the others.
        """
        if self.calendar is not None and not self.calendar.is_open(now):
            return []

        live = self.platform.runs.list_by_state("live", kind="paper")
        results: list[dict[str, Any]] = []
        for row in live:
            tenant_id, run_id = row["tenant_id"], row["run_id"]
            try:
                # Read the current book for the delta basis, but do NOT materialize one — a
                # run that skips this tick (stale/no marks) should not leave a book behind.
                # The applier ensures the book on the first real apply.
                book = self.platform.books.get(tenant_id, run_id) or {
                    "capital": self.capital, "weights": {}
                }
                proposal = run_paper_tick(
                    tenant_id, run_id,
                    platform=self.platform, core=self.core,
                    book={"capital": book["capital"], "weights": book["weights"]},
                    now=now, budget_ms=self.budget_ms, max_staleness_s=self.max_staleness_s,
                )
                applied = None
                if proposal.get("action") == "propose":
                    applied = self.apply_delta(tenant_id, run_id, proposal)
                results.append({"run_id": run_id, "tenant_id": tenant_id,
                                "proposal": proposal, "applied": applied})
            except Exception as exc:  # noqa: BLE001 — one run's failure must not stop the rest.
                results.append({"run_id": run_id, "tenant_id": tenant_id,
                                "error": type(exc).__name__, "detail": str(exc)[:300]})
        return results

    def run_forever(self, *, interval_s: float = 60.0, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        while not stop.is_set():
            self.tick_once()
            stop.wait(interval_s)
