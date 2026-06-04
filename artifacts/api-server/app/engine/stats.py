"""Performance & risk statistics computed from a real return series.

All functions take simple (arithmetic) daily returns and/or an equity curve and
return plain Python floats so the results serialize cleanly into panel data.
They are defensive against short/degenerate inputs (return 0.0 rather than NaN).
"""
from __future__ import annotations

from typing import Dict

import numpy as np

TRADING_DAYS = 252


def _clean(returns: np.ndarray) -> np.ndarray:
    r = np.asarray(returns, dtype=float)
    return r[np.isfinite(r)]


def cagr(equity: np.ndarray) -> float:
    """Compound annual growth rate implied by an equity curve."""
    e = np.asarray(equity, dtype=float)
    if e.size < 2 or e[0] <= 0 or e[-1] <= 0:
        return 0.0
    years = (e.size - 1) / TRADING_DAYS
    if years <= 0:
        return 0.0
    return float((e[-1] / e[0]) ** (1.0 / years) - 1.0)


def total_return(equity: np.ndarray) -> float:
    e = np.asarray(equity, dtype=float)
    if e.size < 2 or e[0] == 0:
        return 0.0
    return float(e[-1] / e[0] - 1.0)


def annualized_vol(returns: np.ndarray) -> float:
    r = _clean(returns)
    if r.size < 2:
        return 0.0
    return float(r.std(ddof=0) * np.sqrt(TRADING_DAYS))


def sharpe(returns: np.ndarray, rf: float = 0.0) -> float:
    """Annualized Sharpe ratio (rf is a per-annum risk-free rate)."""
    r = _clean(returns)
    if r.size < 2:
        return 0.0
    excess = r - rf / TRADING_DAYS
    sd = excess.std(ddof=0)
    if sd <= 0:
        return 0.0
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS))


def sortino(returns: np.ndarray, rf: float = 0.0) -> float:
    """Annualized Sortino ratio (downside deviation in the denominator)."""
    r = _clean(returns)
    if r.size < 2:
        return 0.0
    excess = r - rf / TRADING_DAYS
    downside = excess[excess < 0]
    if downside.size == 0:
        return 0.0
    dd = np.sqrt(np.mean(downside ** 2))
    if dd <= 0:
        return 0.0
    return float(excess.mean() / dd * np.sqrt(TRADING_DAYS))


def max_drawdown(equity: np.ndarray) -> float:
    """Worst peak-to-trough decline as a negative fraction (e.g. -0.23)."""
    e = np.asarray(equity, dtype=float)
    if e.size == 0:
        return 0.0
    peak = np.maximum.accumulate(e)
    safe_peak = np.where(peak == 0, np.nan, peak)
    dd = (e - peak) / safe_peak
    dd = dd[np.isfinite(dd)]
    if dd.size == 0:
        return 0.0
    return float(dd.min())


def win_rate(returns: np.ndarray) -> float:
    """Fraction of active (non-zero) bars that were positive."""
    r = _clean(returns)
    active = r[r != 0]
    if active.size == 0:
        return 0.0
    return float((active > 0).sum() / active.size)


def var_historical(returns: np.ndarray, level: float = 0.95) -> float:
    """Historical Value-at-Risk as a positive loss fraction at `level`."""
    r = _clean(returns)
    if r.size < 2:
        return 0.0
    q = np.percentile(r, (1.0 - level) * 100.0)
    return float(max(0.0, -q))


def cvar_historical(returns: np.ndarray, level: float = 0.95) -> float:
    """Conditional VaR (expected shortfall) as a positive loss fraction."""
    r = _clean(returns)
    if r.size < 2:
        return 0.0
    q = np.percentile(r, (1.0 - level) * 100.0)
    tail = r[r <= q]
    if tail.size == 0:
        return float(max(0.0, -q))
    return float(max(0.0, -tail.mean()))


def performance_stats(
    equity: np.ndarray,
    returns: np.ndarray,
    turnover: float = 0.0,
    rf: float = 0.0,
) -> Dict[str, float]:
    """Bundle the full stat block used by the backtest panel."""
    return {
        "sharpe": round(sharpe(returns, rf), 2),
        "sortino": round(sortino(returns, rf), 2),
        "cagr": round(cagr(equity) * 100.0, 2),
        "totalReturn": round(total_return(equity) * 100.0, 2),
        "vol": round(annualized_vol(returns) * 100.0, 2),
        "maxDD": round(max_drawdown(equity) * 100.0, 2),
        "winRate": round(win_rate(returns) * 100.0, 1),
        "turnover": round(float(turnover), 2),
        "var95": round(var_historical(returns, 0.95) * 100.0, 2),
        "cvar95": round(cvar_historical(returns, 0.95) * 100.0, 2),
    }
