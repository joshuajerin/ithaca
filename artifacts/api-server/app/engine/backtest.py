"""Backtest core.

Runs a strategy over a close-price series with a simple per-trade cost and
returns an equity curve (vs a buy-and-hold benchmark), a drawdown series, a
trade log, and a full performance/risk stat block.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from . import stats
from .strategies import STRATEGIES, normalize_strategy


def _extract(points: List[dict]) -> tuple[List[str], np.ndarray]:
    """Pull (dates, closes) from a list of {t, c, ...} points, dropping bad bars."""
    dates: List[str] = []
    closes: List[float] = []
    for p in points or []:
        c = p.get("c")
        if c is None:
            continue
        try:
            cf = float(c)
        except (TypeError, ValueError):
            continue
        if cf <= 0:
            continue
        dates.append(str(p.get("t")))
        closes.append(cf)
    return dates, np.asarray(closes, dtype=float)


def run_backtest(
    points: List[dict],
    strategy: str = "momentum",
    params: Optional[dict] = None,
    cost_bps: float = 5.0,
    rebase: float = 100.0,
) -> Dict:
    """Run `strategy` over the close series in `points` (oldest -> newest).

    Returns a dict with: strategy, curve, drawdown, tradeLog, stats, barCount.
    Raises ValueError when there is not enough usable history (< 3 bars).
    """
    params = params or {}
    strat_key = normalize_strategy(strategy)
    fn = STRATEGIES[strat_key]

    dates, closes = _extract(points)
    n = closes.size
    if n < 3:
        raise ValueError("insufficient price history for a backtest")

    # Daily simple returns, aligned so rets[i] is the return from bar i-1 -> i.
    rets = np.zeros(n, dtype=float)
    rets[1:] = closes[1:] / closes[:-1] - 1.0

    # Target positions decided using info up to each bar (no lookahead). The
    # position held *into* bar i is the signal from bar i-1.
    target = np.clip(np.asarray(fn(closes, params), dtype=float), -1.0, 1.0)
    held = np.zeros(n, dtype=float)
    held[1:] = target[:-1]

    cost_rate = max(0.0, float(cost_bps)) / 10000.0
    # Trade cost charged when the held position changes between bars.
    pos_change = np.zeros(n, dtype=float)
    pos_change[1:] = np.abs(held[1:] - held[:-1])
    trade_cost = pos_change * cost_rate

    strat_rets = held * rets - trade_cost
    bench_rets = rets  # buy-and-hold benchmark

    strat_equity = rebase * np.cumprod(1.0 + strat_rets)
    bench_equity = rebase * np.cumprod(1.0 + bench_rets)

    # Drawdown of the strategy equity, in percent.
    peak = np.maximum.accumulate(strat_equity)
    dd = np.where(peak > 0, (strat_equity - peak) / peak * 100.0, 0.0)

    curve = [
        {
            "t": dates[i],
            "strategy": round(float(strat_equity[i]), 2),
            "benchmark": round(float(bench_equity[i]), 2),
        }
        for i in range(n)
    ]
    drawdown = [{"t": dates[i], "dd": round(float(dd[i]), 3)} for i in range(n)]

    # Trade log: a row whenever the held position changes.
    trade_log: List[dict] = []
    for i in range(1, n):
        if pos_change[i] > 0:
            prev = held[i - 1]
            cur = held[i]
            action = "BUY" if cur > prev else "SELL" if cur < prev else "FLAT"
            trade_log.append({
                "t": dates[i],
                "action": action,
                "price": round(float(closes[i]), 2),
                "fromPos": round(float(prev), 2),
                "toPos": round(float(cur), 2),
            })

    years = max((n - 1) / stats.TRADING_DAYS, 1e-9)
    annual_turnover = float(pos_change.sum()) / years

    stat_block = stats.performance_stats(strat_equity, strat_rets, turnover=annual_turnover)

    return {
        "strategy": strat_key,
        "curve": curve,
        "drawdown": drawdown,
        "tradeLog": trade_log,
        "stats": stat_block,
        "barCount": n,
        "dailyReturns": strat_rets.tolist(),
    }
