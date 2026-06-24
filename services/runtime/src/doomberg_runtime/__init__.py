"""doomberg-runtime — DO workers: backtest_runner + live_runner.

Out-of-process by design (deny-all egress in prod). Imports ``doomberg-core`` for
the money-path kernel; receives the platform stores injected as ``platform`` so it
never couples to a concrete store implementation.

Public API (per INTERFACES.md):
    run_backtest_job(tenant_id, run_id, *, platform, core)
    run_paper_tick(tenant_id, run_id, *, platform, core)
"""

from .backtest_runner import DEFAULT_BUDGET_MS as BACKTEST_BUDGET_MS
from .backtest_runner import result_hash, run_backtest_job
from .calendar import AlwaysOpen, MarketCalendar, RegularHoursCalendar
from .deadline import Deadline, DeadlineExceeded
from .live_runner import DEFAULT_MAX_STALENESS_S, run_paper_tick
from .orchestrator import BacktestWorker, PaperScheduler, TriggerJobWorker
from .trigger_engine import HttpQuoteClient, StaticQuoteClient, TriggerEngine

__all__ = [
    "run_backtest_job",
    "run_paper_tick",
    "result_hash",
    "Deadline",
    "DeadlineExceeded",
    "BACKTEST_BUDGET_MS",
    "DEFAULT_MAX_STALENESS_S",
    "BacktestWorker",
    "TriggerJobWorker",
    "PaperScheduler",
    "TriggerEngine",
    "HttpQuoteClient",
    "StaticQuoteClient",
    "MarketCalendar",
    "RegularHoursCalendar",
    "AlwaysOpen",
]
