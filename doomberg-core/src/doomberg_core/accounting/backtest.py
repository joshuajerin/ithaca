"""Multi-asset, no-lookahead backtest — the shared money-path kernel.

The backtest and the (future) paper-live tick differ only in clock + data window; both use
THIS accounting so backtest-math == paper-math. Convention (matches v1): the weight row
decided at the close of bar t is applied to the t->t+1 asset return, so signals never see
the future. Transaction cost = turnover * cost_bps / 10_000 charged on rebalance.
"""
from __future__ import annotations

import numpy as np

from ..engine import stats as _stats
from ..graph import evaluate as _evaluate

__all__ = ["run_backtest"]


def _asset_returns(closes: np.ndarray) -> np.ndarray:
    T, N = closes.shape
    rets = np.zeros((T, N), dtype=float)
    if T >= 2:
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(closes[:-1] > 0, closes[1:] / closes[:-1] - 1.0, 0.0)
        rets[1:] = np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)
    return rets


def run_backtest(spec: dict, dates: list[str], closes: np.ndarray, symbols: list[str]) -> dict:
    """Run ``spec`` over the aligned (dates, closes[T,N], symbols) panel.

    Returns a JSON-able result: equity curve, the v1 performance stat block, turnover,
    final weights, and the risk-gate attestation (so a relaxed/violating book is visible).
    """
    closes = np.asarray(closes, dtype=float)
    T, N = closes.shape
    if T < 3:
        raise ValueError(f"need at least 3 bars to backtest, got {T}")

    graph = _evaluate(spec, dates, closes)
    weights = graph["weights"]              # (T, N) held over t -> t+1
    asset_ret = _asset_returns(closes)      # (T, N), asset_ret[t] is the t-1 -> t move

    cost_rate = float(spec["execution"]["cost_bps"]) / 10_000.0

    # Portfolio return at bar t (>=1) uses weights decided at t-1 (no lookahead).
    port_ret = np.zeros(T, dtype=float)
    turnover = np.zeros(T, dtype=float)
    for t in range(1, T):
        port_ret[t] = float(np.dot(weights[t - 1], asset_ret[t]))
        turnover[t] = float(np.sum(np.abs(weights[t - 1] - weights[t - 2]))) if t >= 2 else float(np.sum(np.abs(weights[t - 1])))
    net_ret = port_ret - turnover * cost_rate

    equity = np.cumprod(1.0 + net_ret)
    avg_turnover = float(np.mean(turnover[1:])) if T > 1 else 0.0
    stat_block = _stats.performance_stats(equity, net_ret[1:], avg_turnover)

    curve = [{"d": dates[t], "v": round(float(equity[t]), 6)} for t in range(T)]
    final = {symbols[i]: round(float(weights[-1, i]), 6) for i in range(N) if abs(weights[-1, i]) > 1e-9}

    return {
        "equityCurve": curve,
        "stats": stat_block,
        "finalWeights": final,
        "risk": graph["worstAttest"],
        "relaxed": graph["anyRelaxed"],
        "bars": T,
        "symbols": symbols,
    }
