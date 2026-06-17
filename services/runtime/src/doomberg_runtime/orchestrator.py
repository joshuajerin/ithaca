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
from datetime import datetime
from typing import Any, Callable

from doomberg_core import Core

from .backtest_runner import DEFAULT_BUDGET_MS as BACKTEST_BUDGET_MS
from .backtest_runner import run_backtest_job
from .calendar import MarketCalendar
from .live_runner import DEFAULT_BUDGET_MS as PAPER_BUDGET_MS
from .live_runner import DEFAULT_MAX_STALENESS_S, run_paper_tick

__all__ = ["BacktestWorker", "PaperScheduler", "ApplyDelta"]

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

    def poll_once(self) -> dict[str, Any]:
        """Claim + run all currently-queued backtests. Returns a summary, never raises.

        A run that another worker already claimed (lost optimistic race) or that the job
        failed lands in ``skipped`` — the job itself has already audited a hard failure with
        an ``error`` trace, so the loop must not die on it.
        """
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

    def run_forever(self, *, interval_s: float = 1.0, stop: threading.Event | None = None) -> None:
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
