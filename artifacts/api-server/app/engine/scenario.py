"""Scenario / what-if forward projection.

Given a real daily-return series (a single asset or an equal-/weight-combined
basket), project a *baseline* forward path with the existing Monte Carlo engine
and a *scenario* path that layers an estimated incremental annualized drift from
the what-if assumptions on top. The baseline is grounded in genuine history; the
scenario delta is an explicit, clearly-labeled estimate, never silently mixed in.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from .montecarlo import monte_carlo
from .stats import TRADING_DAYS


def combine_returns(series_list: List, weights: Optional[List[float]] = None) -> np.ndarray:
    """Combine several daily-return arrays into one basket series.

    Each series is trimmed to the common (shortest) length so they align by
    most-recent bars, then blended by `weights` (equal-weight when omitted).
    """
    clean: List[np.ndarray] = []
    used_weights: List[float] = []
    for i, s in enumerate(series_list):
        a = np.asarray(s, dtype=float)
        a = a[np.isfinite(a)]
        if a.size:
            clean.append(a)
            if weights is not None and i < len(weights):
                used_weights.append(float(weights[i]))
            else:
                used_weights.append(1.0)
    if not clean:
        return np.asarray([], dtype=float)
    n = min(a.size for a in clean)
    if n <= 0:
        return np.asarray([], dtype=float)
    trimmed = np.vstack([a[-n:] for a in clean])
    w = np.asarray(used_weights, dtype=float)
    if w.sum() <= 0:
        w = np.full(len(clean), 1.0 / len(clean))
    else:
        w = w / w.sum()
    return (w[:, None] * trimmed).sum(axis=0)


def project_scenario(
    returns,
    scenario_drift_pct: float,
    horizon: int = 252,
    n_paths: int = 1000,
    method: str = "bootstrap",
    start_value: float = 100.0,
    seed: int = 4242,
) -> Dict:
    """Project a baseline vs. scenario forward path.

    `scenario_drift_pct` is the *incremental* annualized total-return impact the
    what-if assumptions are estimated to add (can be negative). The baseline fan
    comes straight from the Monte Carlo engine on the real return series; the
    scenario fan is that baseline geometrically re-drifted by the estimate.

    Returns a dict with: horizon, method, startValue, path, baseline, scenario.
    Raises ValueError when there is not enough history.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < 5:
        raise ValueError("insufficient return history for a scenario projection")
    horizon = max(1, int(horizon))

    base = monte_carlo(
        r, start_value=start_value, horizon=horizon,
        n_paths=n_paths, method=method, seed=seed,
    )
    base_fan = base["fan"]
    bs = base["summary"]

    # Translate the incremental annualized drift into a per-bar growth factor.
    drift = float(scenario_drift_pct) / 100.0
    per_bar = (1.0 + drift) ** (1.0 / TRADING_DAYS) if drift > -1.0 else 0.0

    path: List[dict] = []
    for pt in base_fan:
        step = pt["step"]
        factor = per_bar ** step
        path.append({
            "step": step,
            "baselineP50": pt["p50"],
            "baselineP5": pt["p5"],
            "baselineP95": pt["p95"],
            "scenarioP50": round(pt["p50"] * factor, 2),
            "scenarioP5": round(pt["p5"] * factor, 2),
            "scenarioP95": round(pt["p95"] * factor, 2),
        })

    end_factor = per_bar ** horizon
    base_end_ret = bs["expectedReturn"]
    scen_end_value = bs["expectedTerminal"] * end_factor
    scen_end_ret = round((scen_end_value / start_value - 1.0) * 100.0, 2)

    return {
        "horizon": horizon,
        "method": base["method"],
        "startValue": round(float(start_value), 2),
        "path": path,
        "baseline": {
            "expectedReturnPct": base_end_ret,
            "endValue": bs["expectedTerminal"],
            "p5Value": round(float(bs["p5Terminal"]), 2),
            "p95Value": round(float(bs["p95Terminal"]), 2),
            "p5Pct": round((bs["p5Terminal"] / start_value - 1.0) * 100.0, 2),
            "p95Pct": round((bs["p95Terminal"] / start_value - 1.0) * 100.0, 2),
            "probLossPct": bs["probLoss"],
        },
        "scenario": {
            "expectedReturnPct": scen_end_ret,
            "endValue": round(scen_end_value, 2),
            "p5Value": round(float(bs["p5Terminal"]) * end_factor, 2),
            "p95Value": round(float(bs["p95Terminal"]) * end_factor, 2),
            "p5Pct": round((bs["p5Terminal"] * end_factor / start_value - 1.0) * 100.0, 2),
            "p95Pct": round((bs["p95Terminal"] * end_factor / start_value - 1.0) * 100.0, 2),
            "deltaPct": round(scen_end_ret - base_end_ret, 2),
        },
    }
