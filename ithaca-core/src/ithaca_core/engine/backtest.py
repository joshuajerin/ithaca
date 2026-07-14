"""Backtest core.

Runs a strategy over a close-price series with a simple per-trade cost and
returns an equity curve (vs a buy-and-hold benchmark), a drawdown series, a
trade log, and a full performance/risk stat block.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from . import stats
from . import strategies as _strategies
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


# ----------------------------- walk-forward validation -----------------------------
# A separate research-integrity mode (NOT a replacement for run_backtest). It
# answers "would this strategy have worked out-of-sample, or is the backtest
# overfit?" by (1) sweeping a realistic parameter grid, (2) re-selecting the
# best parameters on each anchored in-sample window and grading them on the
# next, untouched out-of-sample block, and (3) running the deflated Sharpe,
# multiple-testing haircut and PBO (CSCV) diagnostics over the full sweep.

# Minimum bars an out-of-sample block needs to produce a meaningful Sharpe.
_MIN_BLOCK_BARS = 15
# Minimum bars the first (training-only) block needs to fit a parameter set.
_MIN_TRAIN_BARS = 30


def _strategy_daily_returns(
    closes: np.ndarray,
    rets: np.ndarray,
    fn,
    params: dict,
    cost_rate: float,
) -> np.ndarray:
    """Full-series strategy daily returns for one parameter set (no lookahead)."""
    target = np.clip(np.asarray(fn(closes, params), dtype=float), -1.0, 1.0)
    held = np.zeros_like(closes)
    held[1:] = target[:-1]
    pos_change = np.zeros_like(closes)
    pos_change[1:] = np.abs(held[1:] - held[:-1])
    return held * rets - pos_change * cost_rate


def _stitched_curve(dates: List[str], rets: np.ndarray, rebase: float) -> List[dict]:
    """Equity curve (strategy vs buy-and-hold benchmark) for a return slice."""
    # `rets` here are strategy returns; the benchmark column is filled by the
    # caller, so this helper only renders the strategy equity.
    equity = rebase * np.cumprod(1.0 + rets)
    return [
        {"t": dates[i], "strategy": round(float(equity[i]), 2)}
        for i in range(len(dates))
    ]


def run_walk_forward(
    points: List[dict],
    strategy: str = "momentum",
    param_grid: Optional[List[dict]] = None,
    n_splits: int = 5,
    cost_bps: float = 5.0,
    rebase: float = 100.0,
    pbo_splits: int = 10,
) -> Dict:
    """Anchored walk-forward validation + overfitting diagnostics.

    Always returns a dict with a ``coverage`` block; when there is not enough
    real history to form at least two out-of-sample folds it sets
    ``coverage.usable = False`` and explains why rather than fabricating folds.
    Raises ValueError only when the series is too short to compute anything
    (< 3 bars), matching run_backtest so callers can fall back identically.
    """
    strat_key = normalize_strategy(strategy)
    fn = STRATEGIES[strat_key]
    grid = param_grid if param_grid is not None else _strategies.param_grid(strat_key)
    if not grid:
        grid = [{}]

    dates, closes = _extract(points)
    n = closes.size
    if n < 3:
        raise ValueError("insufficient price history for walk-forward validation")

    rets = np.zeros(n, dtype=float)
    rets[1:] = closes[1:] / closes[:-1] - 1.0
    cost_rate = max(0.0, float(cost_bps)) / 10000.0

    # Full-series strategy returns for every configuration in the grid. These
    # feed both the per-fold parameter selection and the overfitting matrix.
    grid_rets = [
        _strategy_daily_returns(closes, rets, fn, p, cost_rate) for p in grid
    ]

    # --- how many anchored folds can the real history honestly support? ---
    requested = max(2, int(n_splits))
    blocks = min(requested, max(0, n // _MIN_BLOCK_BARS - 1))
    usable = blocks >= 2 and n >= (_MIN_TRAIN_BARS + 2 * _MIN_BLOCK_BARS)

    # Full-sample best configuration: the "optimised backtest" a researcher
    # would show off. Selected by per-observation Sharpe over the whole series.
    full_sr = np.array([stats.sharpe_per_obs(r[1:]) for r in grid_rets])
    best_full = int(np.argmax(full_sr)) if full_sr.size else 0
    best_full_rets = grid_rets[best_full]
    is_equity = rebase * np.cumprod(1.0 + best_full_rets)
    bench_equity = rebase * np.cumprod(1.0 + rets)
    is_curve = [
        {
            "t": dates[i],
            "strategy": round(float(is_equity[i]), 2),
            "benchmark": round(float(bench_equity[i]), 2),
        }
        for i in range(n)
    ]
    is_stats = stats.performance_stats(is_equity, best_full_rets)

    # --- overfitting diagnostics over the whole sweep ---
    n_trials = len(grid)
    sr_variance = float(np.var(full_sr, ddof=0)) if full_sr.size > 1 else 0.0
    sr_hat = float(full_sr[best_full]) if full_sr.size else 0.0
    skew = stats.skewness(best_full_rets[1:])
    kurt = stats.kurtosis(best_full_rets[1:])
    dsr = stats.deflated_sharpe(sr_hat, n - 1, n_trials, sr_variance, skew, kurt)
    haircut = stats.multiple_testing_haircut(sr_hat, n - 1, n_trials, sr_variance)

    pbo = None
    if n_trials >= 2:
        matrix = np.column_stack([r[1:] for r in grid_rets])
        pbo = stats.pbo_cscv(matrix, n_splits=pbo_splits)

    # --- anchored walk-forward folds ---
    folds: List[dict] = []
    oos_rets_parts: List[np.ndarray] = []
    oos_dates: List[str] = []
    oos_bench_parts: List[np.ndarray] = []
    if usable:
        blk = n // (blocks + 1)
        for k in range(1, blocks + 1):
            is_end = k * blk
            oos_start = is_end
            oos_end = (k + 1) * blk if k < blocks else n
            if oos_end - oos_start < 2:
                continue
            # Re-select the best configuration on this anchored in-sample window.
            is_sr = np.array([
                stats.sharpe_per_obs(grid_rets[j][1:is_end]) for j in range(n_trials)
            ])
            choice = int(np.argmax(is_sr)) if is_sr.size else 0
            chosen_rets = grid_rets[choice]
            oos_slice = chosen_rets[oos_start:oos_end]
            oos_rets_parts.append(oos_slice)
            oos_dates.extend(dates[oos_start:oos_end])
            oos_bench_parts.append(rets[oos_start:oos_end])
            folds.append({
                "fold": k,
                "isStart": dates[0],
                "isEnd": dates[is_end - 1],
                "oosStart": dates[oos_start],
                "oosEnd": dates[oos_end - 1],
                "isBars": int(is_end),
                "oosBars": int(oos_end - oos_start),
                "param": grid[choice],
                "paramLabel": _strategies.param_label(grid[choice]),
                "isSharpe": round(stats.sharpe(grid_rets[choice][1:is_end]), 2),
                "oosSharpe": round(stats.sharpe(oos_slice), 2),
            })

    # --- stitched out-of-sample track record ---
    oos_curve: List[dict] = []
    oos_stats: Dict[str, float] = {}
    degradation_pct = 0.0
    if oos_rets_parts:
        oos_rets = np.concatenate(oos_rets_parts)
        oos_bench = np.concatenate(oos_bench_parts)
        oos_equity = rebase * np.cumprod(1.0 + oos_rets)
        oos_bench_eq = rebase * np.cumprod(1.0 + oos_bench)
        oos_curve = [
            {
                "t": oos_dates[i],
                "strategy": round(float(oos_equity[i]), 2),
                "benchmark": round(float(oos_bench_eq[i]), 2),
            }
            for i in range(len(oos_dates))
        ]
        oos_stats = stats.performance_stats(oos_equity, oos_rets)
        is_sh = is_stats.get("sharpe", 0.0)
        oos_sh = oos_stats.get("sharpe", 0.0)
        if abs(is_sh) > 1e-9:
            degradation_pct = round((is_sh - oos_sh) / abs(is_sh) * 100.0, 1)

    verdict = _overfitting_verdict(
        usable=usable,
        is_stats=is_stats,
        oos_stats=oos_stats,
        degradation_pct=degradation_pct,
        pbo=pbo,
        dsr=dsr,
        n_trials=n_trials,
    )

    coverage = {
        "usable": bool(usable and bool(folds)),
        "bars": int(n),
        "folds": len(folds),
        "neededBars": int(_MIN_TRAIN_BARS + 2 * _MIN_BLOCK_BARS),
        "note": (
            ""
            if (usable and folds)
            else (
                f"Only {n} bars of real history available — need at least "
                f"{_MIN_TRAIN_BARS + 2 * _MIN_BLOCK_BARS} to form two honest "
                "out-of-sample folds. Showing the full-sample fit and "
                "diagnostics only; out-of-sample validation is not reported."
            )
        ),
    }

    return {
        "strategy": strat_key,
        "barCount": int(n),
        "nSplits": len(folds),
        "paramGridSize": n_trials,
        "isCurve": is_curve,
        "oosCurve": oos_curve,
        "isStats": is_stats,
        "oosStats": oos_stats,
        "degradationPct": degradation_pct,
        "folds": folds,
        "deflatedSharpe": {
            "observed": haircut["observed"],
            "benchmark": haircut["benchmark"],
            "haircutSharpe": haircut["haircutSharpe"],
            "haircutPct": haircut["haircutPct"],
            "dsr": round(dsr["dsr"] * 100.0, 1),
            "sr0PerObs": round(dsr["sr0"], 4),
            "nTrials": n_trials,
            "skew": round(skew, 3),
            "kurtosis": round(kurt, 3),
        },
        "pbo": (
            {
                "pbo": round(pbo["pbo"] * 100.0, 1),
                "nTrials": pbo["nTrials"],
                "nSplits": pbo["nSplits"],
                "nCombos": pbo["nCombos"],
                "medianLogit": pbo["medianLogit"],
            }
            if pbo
            else None
        ),
        "verdict": verdict,
        "coverage": coverage,
        "bestFullParam": _strategies.param_label(grid[best_full]),
    }


def _overfitting_verdict(
    usable: bool,
    is_stats: Dict[str, float],
    oos_stats: Dict[str, float],
    degradation_pct: float,
    pbo: Optional[dict],
    dsr: dict,
    n_trials: int,
) -> Dict[str, str]:
    """Plain-language verdict combining the OOS degradation, PBO and DSR."""
    is_sh = is_stats.get("sharpe", 0.0)
    pbo_val = (pbo["pbo"] * 100.0) if pbo else None
    dsr_val = dsr.get("dsr", 0.0) * 100.0

    if not usable or not oos_stats:
        return {
            "label": "inconclusive",
            "summary": (
                "Not enough out-of-sample history to judge overfitting. The "
                "in-sample fit and statistical diagnostics are shown, but a "
                "walk-forward verdict needs more real price data."
            ),
        }

    oos_sh = oos_stats.get("sharpe", 0.0)
    bits: List[str] = []
    bits.append(
        f"In-sample Sharpe {is_sh:.2f} vs out-of-sample {oos_sh:.2f} "
        f"({degradation_pct:.0f}% degradation)."
    )
    if pbo_val is not None:
        bits.append(f"PBO {pbo_val:.0f}% across {n_trials} configurations.")
    bits.append(f"Deflated Sharpe confidence {dsr_val:.0f}%.")

    if is_sh > 0 and oos_sh <= 0:
        label = "severe_overfitting"
        head = (
            "Severe overfitting: the strategy makes money in-sample but loses "
            "it out-of-sample."
        )
    elif (degradation_pct >= 50.0) or (pbo_val is not None and pbo_val >= 50.0):
        label = "likely_overfit"
        head = "Likely overfit: out-of-sample performance breaks down badly."
    elif (degradation_pct >= 25.0) or (pbo_val is not None and pbo_val >= 30.0) or (dsr_val < 90.0):
        label = "some_overfitting"
        head = (
            "Some overfitting: out-of-sample results are weaker and the edge is "
            "not statistically convincing after the multiple-testing haircut."
        )
    else:
        label = "robust"
        head = (
            "Robust: the edge largely survives out-of-sample and the "
            "multiple-testing diagnostics."
        )
    return {"label": label, "summary": head + " " + " ".join(bits)}
