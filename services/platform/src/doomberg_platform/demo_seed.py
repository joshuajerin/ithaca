"""Seed a deterministic demo research session into a tenant.

The "first glimpse": when a brand-new Clerk user signs in, the platform seeds one
replayable ``research`` run into their tenant so the observability UI has something
to show immediately — an agent that researches a ticker, proposes a strategy, and
runs a backtest, with a gap-free trace the replay scrubber can play back seq-by-seq.

The trace is synthetic but shaped exactly like a real BYO-agent session: a
``session_open`` with the prompt, ``reasoning`` steps, paired ``tool_call`` /
``tool_result`` events (span-linked), a ``strategy_proposed`` note, and a final
``run_transition`` to ``succeeded``. Nothing here touches the money path or the
worker queue — it is observability seed data only.

Idempotent: a tenant is seeded at most once. The seed is keyed off the run list, so
re-calling on a tenant that already has a research run is a no-op.
"""

from __future__ import annotations

import datetime as _dt
import secrets
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .platform import Platform


# A short, deterministic script the replay walks through. Kept inline so the seeder
# has no external data dependency — the "first glimpse" works offline.
_PROMPT = "What does NVDA look like right now? Research the setup and propose a backtest."
_TITLE = "NVDA research + dual-momentum backtest"


def _ts(base: _dt.datetime, offset_ms: int) -> str:
    return (base + _dt.timedelta(milliseconds=offset_ms)).isoformat()


def _actor() -> dict[str, str]:
    return {"kind": "agent", "id": "demo-agent"}


def _span() -> str:
    return f"span-{secrets.token_hex(6)}"


def _tool_call(
    platform: "Platform", tenant_id: str, run_id: str, ts: str, span_id: str,
    parent: str | None, name: str, args: dict[str, Any],
) -> None:
    platform.trace.append({
        "run_id": run_id,
        "ts": ts,
        "type": "tool_call",
        "tenant_id": tenant_id,
        "session_id": run_id,
        "origin_session_id": run_id,
        "span_id": span_id,
        "parent_span_id": parent,
        "actor": _actor(),
        "data": {"name": name, "args": args},
    })


def _tool_result(
    platform: "Platform", tenant_id: str, run_id: str, ts: str, span_id: str,
    parent: str | None, name: str, summary: dict[str, Any], *,
    panel_type: str | None = None,
) -> None:
    data: dict[str, Any] = {"name": name, "summary": summary}
    if panel_type:
        data["panelType"] = panel_type
    platform.trace.append({
        "run_id": run_id,
        "ts": ts,
        "type": "tool_result",
        "tenant_id": tenant_id,
        "session_id": run_id,
        "origin_session_id": run_id,
        "span_id": span_id,
        "parent_span_id": parent,
        "actor": _actor(),
        "data": data,
    })


def _reasoning(
    platform: "Platform", tenant_id: str, run_id: str, ts: str, text: str,
) -> None:
    platform.trace.append({
        "run_id": run_id,
        "ts": ts,
        "type": "reasoning",
        "tenant_id": tenant_id,
        "session_id": run_id,
        "origin_session_id": run_id,
        "actor": _actor(),
        "data": {"kind": "plan", "text": text},
    })


def seed_demo_session(platform: "Platform", tenant_id: str) -> str | None:
    """Seed one demo research run for ``tenant_id`` if none exists yet.

    Returns the seeded ``run_id`` when a new session was created, or ``None`` when the
    tenant already had at least one research run (idempotent).
    """
    tenant_id = str(tenant_id)
    existing = platform.runs.list(tenant_id, kind="research")
    if existing:
        return None

    run_id = platform.runs.create_research(tenant_id)
    base = _dt.datetime.now(_dt.timezone.utc)

    # 0 — session open (carries the prompt the UI renders as the conversation root).
    platform.trace.append({
        "run_id": run_id,
        "ts": _ts(base, 0),
        "type": "session_open",
        "tenant_id": tenant_id,
        "session_id": run_id,
        "origin_session_id": run_id,
        "actor": {"kind": "user", "id": "operator"},
        "data": {"createdBy": "web", "title": _TITLE, "prompt": _PROMPT},
    })

    # 1 — the agent reasons about the plan.
    _reasoning(
        platform, tenant_id, run_id, _ts(base, 320),
        "Plan: pull NVDA price history, screen the peer set for momentum, then propose "
        "a dual-momentum strategy and request a backtest.",
    )

    # 2 — fetch NVDA history.
    s1 = _span()
    _tool_call(platform, tenant_id, run_id, _ts(base, 900), s1, None,
               "fetch_history", {"symbol": "NVDA", "range": "1y", "interval": "1d"})
    _tool_result(platform, tenant_id, run_id, _ts(base, 1400), s1, None,
                 "fetch_history",
                 {"symbol": "NVDA", "points": 252, "last_close": 178.42,
                  "source": "doomberg-archive", "as_of": base.date().isoformat()})

    # 3 — screen the peer set.
    s2 = _span()
    _tool_call(platform, tenant_id, run_id, _ts(base, 2100), s2, None,
               "screen_momentum",
               {"universe": ["NVDA", "AMD", "AVGO", "TSM", "SMCI"],
                "lookback": 60, "top": 2})
    _tool_result(platform, tenant_id, run_id, _ts(base, 2900), s2, None,
                 "screen_momentum",
                 {"ranked": [
                     {"symbol": "NVDA", "return_60d": 0.182},
                     {"symbol": "AVGO", "return_60d": 0.121},
                     {"symbol": "SMCI", "return_60d": 0.094},
                     {"symbol": "AMD", "return_60d": 0.041},
                     {"symbol": "TSM", "return_60d": 0.028},
                 ],
                  "selected": ["NVDA", "AVGO"]})

    # 4 — reasoning before the proposal.
    _reasoning(
        platform, tenant_id, run_id, _ts(base, 3300),
        "NVDA and AVGO lead the 60-day momentum screen. I'll propose an equal-weight "
        "dual-momentum strategy on the top-2, daily rebalance, with a 60% max-name cap.",
    )

    # 5 — propose the strategy (the lineage note the UI surfaces).
    strategy_id = "demo-dual-momentum"
    platform.trace.append({
        "run_id": run_id,
        "ts": _ts(base, 3900),
        "type": "strategy_proposed",
        "tenant_id": tenant_id,
        "session_id": run_id,
        "origin_session_id": run_id,
        "actor": _actor(),
        "data": {
            "name": "NVDA dual-momentum (top-2)",
            "strategy_id": strategy_id,
            "spec": {
                "spec_version": "1.0",
                "name": "demo-dual-momentum",
                "universe": {"symbols": ["NVDA", "AVGO"], "source": "prices"},
                "strategy": {"id": "rank_returns", "params": {"lookback": 60, "top": 2}},
                "construction": {"scheme": "equal_weight", "long_only": True, "gross": 1.0},
                "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.6},
                "execution": {"cost_bps": 5, "algo": "vwap", "rebalance": "daily@close"},
                "seed": 42,
            },
        },
    })

    # 6 — request a backtest (tool call into the deploy layer).
    s3 = _span()
    _tool_call(platform, tenant_id, run_id, _ts(base, 4500), s3, None,
               "request_backtest",
               {"strategy_id": strategy_id, "range": "1y"})
    _tool_result(platform, tenant_id, run_id, _ts(base, 5200), s3, None,
                 "request_backtest",
                 {"run_id": "demo-backtest", "state": "queued",
                  "summary": "Backtest enqueued; the conductor will pull and run it."},
                 panel_type="backtest")

    # 7 — progress + the backtest result summary (so the replay shows a finished arc).
    platform.trace.append({
        "run_id": run_id,
        "ts": _ts(base, 6100),
        "type": "run_progress",
        "tenant_id": tenant_id,
        "session_id": run_id,
        "origin_session_id": run_id,
        "actor": _actor(),
        "data": {"phase": "backtest", "pct": 100, "message": "backtest complete"},
    })

    # 8 — close the research session.
    platform.trace.append({
        "run_id": run_id,
        "ts": _ts(base, 6400),
        "type": "session_close",
        "tenant_id": tenant_id,
        "session_id": run_id,
        "origin_session_id": run_id,
        "actor": _actor(),
        "data": {"reason": "research complete"},
    })

    # 9 — transition the research run to succeeded (the state machine the UI reads).
    platform.runs.transition(tenant_id, run_id, "succeeded")
    platform.runs.set_result(tenant_id, run_id, {
        "kind": "research",
        "summary": "Researched NVDA, screened peers, proposed a dual-momentum strategy, "
                   "and requested a backtest.",
        "backtest": {
            "sharpe": 1.84,
            "cagr": 0.31,
            "max_drawdown": -0.14,
            "trades": 248,
        },
    })

    return run_id
