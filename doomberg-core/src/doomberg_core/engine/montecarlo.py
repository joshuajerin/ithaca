"""Monte Carlo forward simulation.

Projects forward price/equity paths from the characteristics of a real
historical daily-return series, using either a non-parametric historical
bootstrap or a parametric geometric Brownian motion (GBM). Reports a percentile
fan (p5/p25/median/p75/p95) over the horizon plus terminal-value summary
statistics (expected/median terminal, probability of loss, VaR/CVaR).
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from . import stats

_PCTS = [5, 25, 50, 75, 95]


def _clean_returns(returns) -> np.ndarray:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    return r


def monte_carlo(
    returns,
    start_value: float = 100.0,
    horizon: int = 252,
    n_paths: int = 1000,
    method: str = "bootstrap",
    seed: int = 12345,
    sample_paths: int = 12,
) -> Dict:
    """Simulate `n_paths` forward paths over `horizon` trading days.

    Returns a dict with: method, horizon, startValue, fan, samplePaths,
    summary. Raises ValueError when there is not enough history.
    """
    r = _clean_returns(returns)
    if r.size < 5:
        raise ValueError("insufficient return history for simulation")

    horizon = max(1, int(horizon))
    n_paths = max(100, int(n_paths))
    method = (method or "bootstrap").lower()
    if method not in ("bootstrap", "gbm"):
        method = "bootstrap"
    rng = np.random.default_rng(int(seed))

    if method == "gbm":
        # Fit drift/vol on log returns, then simulate GBM increments.
        log_r = np.log1p(r[r > -1.0])
        mu = float(log_r.mean()) if log_r.size else 0.0
        sigma = float(log_r.std(ddof=0)) if log_r.size else 0.0
        shocks = rng.standard_normal((n_paths, horizon))
        step_log = (mu - 0.5 * sigma ** 2) + sigma * shocks
        cum_log = np.cumsum(step_log, axis=1)
        paths = start_value * np.exp(cum_log)
    else:
        # Non-parametric: resample observed daily returns with replacement.
        idx = rng.integers(0, r.size, size=(n_paths, horizon))
        sampled = r[idx]
        growth = np.cumprod(1.0 + sampled, axis=1)
        paths = start_value * growth

    # Prepend the common starting value as step 0.
    start_col = np.full((n_paths, 1), float(start_value))
    full = np.concatenate([start_col, paths], axis=1)  # (n_paths, horizon+1)

    pct_arrays = {p: np.percentile(full, p, axis=0) for p in _PCTS}
    fan: List[dict] = []
    for step in range(horizon + 1):
        fan.append({
            "step": step,
            "p5": round(float(pct_arrays[5][step]), 2),
            "p25": round(float(pct_arrays[25][step]), 2),
            "p50": round(float(pct_arrays[50][step]), 2),
            "p75": round(float(pct_arrays[75][step]), 2),
            "p95": round(float(pct_arrays[95][step]), 2),
        })

    # A handful of representative individual paths for visual texture.
    sample_paths = max(0, min(int(sample_paths), n_paths))
    sample_idx = np.linspace(0, n_paths - 1, sample_paths).astype(int) if sample_paths else np.array([], dtype=int)
    # Order sampled paths by terminal value so the spread reads cleanly.
    terminals_all = full[:, -1]
    order = np.argsort(terminals_all)
    chosen = order[sample_idx] if sample_paths else np.array([], dtype=int)
    samples: List[dict] = []
    for j, pi in enumerate(chosen):
        samples.append({
            "id": j,
            "values": [round(float(v), 2) for v in full[pi]],
        })

    terminals = full[:, -1]
    terminal_returns = terminals / float(start_value) - 1.0
    prob_loss = float((terminals < float(start_value)).mean())

    summary = {
        "method": method,
        "startValue": round(float(start_value), 2),
        "horizon": horizon,
        "paths": int(n_paths),
        "expectedTerminal": round(float(terminals.mean()), 2),
        "medianTerminal": round(float(np.percentile(terminals, 50)), 2),
        "p5Terminal": round(float(np.percentile(terminals, 5)), 2),
        "p95Terminal": round(float(np.percentile(terminals, 95)), 2),
        "expectedReturn": round(float(terminal_returns.mean()) * 100.0, 2),
        "probLoss": round(prob_loss * 100.0, 2),
        "var95": round(stats.var_historical(terminal_returns, 0.95) * 100.0, 2),
        "cvar95": round(stats.cvar_historical(terminal_returns, 0.95) * 100.0, 2),
    }

    return {
        "method": method,
        "horizon": horizon,
        "startValue": round(float(start_value), 2),
        "fan": fan,
        "samplePaths": samples,
        "summary": summary,
    }
