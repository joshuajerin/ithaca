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
from .adaptive_dashboard import (
    ANTHROPIC_HAIKU_MODEL,
    DEFAULT_OPENAI_COMPATIBLE_MODEL,
    AdaptiveDashboardWorker,
    AnthropicDashboardClient,
    AnthropicDashboardError,
    DashboardGenerationError,
    OpenAICompatibleDashboardClient,
    all_users_with_session_history,
    create_adaptive_dashboard_client,
    default_adaptive_dashboard_spec,
    recompute_user_profile,
    usage_signals_for_user,
    user_has_session_history,
)
from .live_runner import DEFAULT_MAX_STALENESS_S, run_paper_tick
from .notifications import NotificationDispatcher, webhook_signature
from .orchestrator import BacktestWorker, PaperScheduler, TriggerJobWorker


def __getattr__(name: str):
    if name in {"TriggerEngine", "HttpQuoteClient", "StaticQuoteClient", "TriggerEvaluationError"}:
        from .trigger_engine import HttpQuoteClient, StaticQuoteClient, TriggerEngine, TriggerEvaluationError

        exported = {
            "TriggerEngine": TriggerEngine,
            "HttpQuoteClient": HttpQuoteClient,
            "StaticQuoteClient": StaticQuoteClient,
            "TriggerEvaluationError": TriggerEvaluationError,
        }
        globals().update(exported)
        return exported[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "run_backtest_job",
    "run_paper_tick",
    "result_hash",
    "Deadline",
    "DeadlineExceeded",
    "ANTHROPIC_HAIKU_MODEL",
    "DEFAULT_OPENAI_COMPATIBLE_MODEL",
    "AdaptiveDashboardWorker",
    "AnthropicDashboardClient",
    "AnthropicDashboardError",
    "DashboardGenerationError",
    "OpenAICompatibleDashboardClient",
    "all_users_with_session_history",
    "create_adaptive_dashboard_client",
    "default_adaptive_dashboard_spec",
    "recompute_user_profile",
    "usage_signals_for_user",
    "user_has_session_history",
    "BACKTEST_BUDGET_MS",
    "DEFAULT_MAX_STALENESS_S",
    "BacktestWorker",
    "TriggerJobWorker",
    "PaperScheduler",
    "NotificationDispatcher",
    "webhook_signature",
    "TriggerEngine",
    "HttpQuoteClient",
    "StaticQuoteClient",
    "TriggerEvaluationError",
    "MarketCalendar",
    "RegularHoursCalendar",
    "AlwaysOpen",
]
