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


def resolve_entry(
    points: List[dict],
    mode: str = "preset",
    date: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict:
    """Resolve where (and over what window) the money goes in, on a points list.

    Returns ``{entryIdx, endIdx, mode, note}`` where the usable backtest slice is
    ``points[entryIdx:endIdx + 1]``. Pure: no I/O. The caller owns fetching enough
    history; this just picks indices and reports an honest note when the requested
    entry can't be fully honored (e.g. a date earlier than any available bar).

    Modes:
    - ``peak``  : enter at the highest close in the available history.
    - ``date``  : enter on the first bar on/after ``date`` (clamped to range).
    - ``range`` : enter at the first bar on/after ``start`` and stop at the last
                  bar on/before ``end`` (either side optional).
    - ``preset``: use the whole supplied series (the existing range behavior).
    """
    dates = [str(p.get("t")) for p in (points or [])]
    n = len(dates)
    if n == 0:
        return {"entryIdx": 0, "endIdx": -1, "mode": mode, "note": None}

    mode = (mode or "preset").lower()
    end_idx = n - 1
    note: Optional[str] = None

    def _first_on_or_after(target: str) -> Optional[int]:
        for i, d in enumerate(dates):
            if d >= target:
                return i
        return None

    def _last_on_or_before(target: str) -> Optional[int]:
        found = None
        for i, d in enumerate(dates):
            if d <= target:
                found = i
        return found

    if mode == "peak":
        _, closes = _extract(points)
        entry_idx = int(np.argmax(closes)) if closes.size else 0
        if entry_idx >= n - 1:
            # Peak is the most recent bar -> step back so there is something to show.
            entry_idx = max(0, n - 2)
            note = "Highest close is the latest bar; showing from just before it."
    elif mode == "date":
        if not date:
            entry_idx = 0
        else:
            idx = _first_on_or_after(date)
            if idx is None:
                entry_idx = n - 1
                note = f"No bars on/after {date}; using the latest available bar."
            else:
                entry_idx = idx
                if dates[idx] != date and idx == 0 and dates[0] > date:
                    note = f"History starts {dates[0]}; entered at the earliest available bar."
                elif dates[idx] != date:
                    note = f"No bar on {date}; entered on the next trading day {dates[idx]}."
    elif mode == "range":
        s_idx = _first_on_or_after(start) if start else 0
        e_idx = _last_on_or_before(end) if end else n - 1
        if s_idx is None:
            s_idx = n - 1
            note = f"No bars on/after {start}; using the latest available bar."
        elif start and dates[s_idx] != start and dates[0] > start:
            note = f"History starts {dates[0]}; range entered at the earliest available bar."
        if e_idx is None or e_idx < s_idx:
            e_idx = n - 1
        entry_idx = s_idx
        end_idx = e_idx
    else:
        entry_idx = 0

    entry_idx = max(0, min(entry_idx, n - 1))
    end_idx = max(entry_idx, min(end_idx, n - 1))
    return {"entryIdx": entry_idx, "endIdx": end_idx, "mode": mode, "note": note}


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

    # Trade log: a row whenever the held position changes, with realized P&L
    # booked on the portion of the position each trade closes. A round-trip is
    # opened when exposure is added (entry price is weighted-averaged) and
    # realized when exposure is reduced, closed, or flipped. `pnl` is in points
    # on the rebased capital base (so on a 100 base it reads like dollars),
    # `pnlPct` is the percent return on the closed leg. Trades that only open or
    # add to a position carry pnl=0.0.
    trade_log: List[dict] = []
    entry_price = 0.0  # average entry price of the currently open position
    for i in range(1, n):
        if pos_change[i] <= 0:
            continue
        prev = float(held[i - 1])
        cur = float(held[i])
        price = float(closes[i])
        action = "BUY" if cur > prev else "SELL"

        realized = 0.0      # P&L in points on the `rebase` capital base
        realized_pct = 0.0  # percent return on the closed leg

        if prev == 0.0:
            # opening a fresh position
            entry_price = price
        elif (prev > 0 and cur > prev) or (prev < 0 and cur < prev):
            # adding in the same direction -> weighted-average the entry price
            added = abs(cur - prev)
            entry_price = (entry_price * abs(prev) + price * added) / abs(cur)
        else:
            # reducing, closing, or flipping -> realize on the closed portion
            sign = 1.0 if prev > 0 else -1.0
            same_side = (prev > 0 and cur >= 0) or (prev < 0 and cur <= 0)
            closed = (abs(prev) - abs(cur)) if same_side else abs(prev)
            if entry_price > 0:
                move = price / entry_price - 1.0
                realized_pct = move * sign * 100.0
                realized = closed * move * sign * rebase
            if not same_side:
                # flipped past flat -> the new opposite leg opens at this price
                entry_price = price
            elif cur == 0.0:
                entry_price = 0.0
            # else: partial reduce on the same side -> entry_price unchanged

        trade_log.append({
            "t": dates[i],
            "action": action,
            "price": round(price, 2),
            "fromPos": round(prev, 2),
            "toPos": round(cur, 2),
            "pnl": round(realized, 2),
            "pnlPct": round(realized_pct, 2),
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
