"""Strategy library.

Each strategy maps a close-price series to a target-position series (one value
per bar, in [-1, 1]) using only information available up to and including that
bar. The backtest engine then applies a bar's position to the *next* bar's
return, so signals are evaluated without lookahead bias.

Add a strategy by writing a `signal_*` function and registering it in
`STRATEGIES`; the engine core never needs to change.
"""
from __future__ import annotations

from typing import Callable, Dict, List

import numpy as np

# A strategy takes (closes, params) and returns a target-position array.
StrategyFn = Callable[[np.ndarray, dict], np.ndarray]


def _sma(values: np.ndarray, window: int) -> np.ndarray:
    """Trailing simple moving average; NaN until the window is filled."""
    window = max(1, int(window))
    n = len(values)
    out = np.full(n, np.nan, dtype=float)
    if n == 0:
        return out
    csum = np.cumsum(values, dtype=float)
    for i in range(n):
        if i + 1 >= window:
            total = csum[i] - (csum[i - window] if i - window >= 0 else 0.0)
            out[i] = total / window
    return out


def signal_buy_and_hold(closes: np.ndarray, params: dict) -> np.ndarray:
    """Always fully invested — the benchmark strategy."""
    return np.ones(len(closes), dtype=float)


def signal_ma_crossover(closes: np.ndarray, params: dict) -> np.ndarray:
    """Long when the fast SMA is above the slow SMA, flat otherwise."""
    fast = max(1, int(params.get("fast", params.get("fastWindow", 20))))
    slow = max(fast + 1, int(params.get("slow", params.get("slowWindow", 50))))
    f = _sma(closes, fast)
    s = _sma(closes, slow)
    pos = np.where((~np.isnan(f)) & (~np.isnan(s)) & (f > s), 1.0, 0.0)
    return pos


def signal_momentum(closes: np.ndarray, params: dict) -> np.ndarray:
    """Long when trailing return over `lookback` bars is positive, else flat."""
    lookback = max(1, int(params.get("lookback", 90)))
    n = len(closes)
    pos = np.zeros(n, dtype=float)
    for i in range(n):
        if i >= lookback and closes[i - lookback] > 0:
            ret = closes[i] / closes[i - lookback] - 1.0
            pos[i] = 1.0 if ret > 0 else 0.0
    return pos


def signal_mean_reversion(closes: np.ndarray, params: dict) -> np.ndarray:
    """Long when price is `threshold` std below its trailing mean (oversold)."""
    lookback = max(2, int(params.get("lookback", 20)))
    threshold = float(params.get("threshold", 1.0))
    n = len(closes)
    pos = np.zeros(n, dtype=float)
    for i in range(n):
        if i + 1 >= lookback:
            window = closes[i - lookback + 1 : i + 1]
            mean = float(window.mean())
            std = float(window.std())
            if std > 0:
                z = (closes[i] - mean) / std
                pos[i] = 1.0 if z < -threshold else 0.0
    return pos


STRATEGIES: Dict[str, StrategyFn] = {
    "buy_and_hold": signal_buy_and_hold,
    "ma_crossover": signal_ma_crossover,
    "momentum": signal_momentum,
    "mean_reversion": signal_mean_reversion,
}

# Forgiving natural-language aliases so the orchestrator's free-text strategy
# names resolve to a real implementation.
_ALIASES = {
    "buy and hold": "buy_and_hold",
    "buyandhold": "buy_and_hold",
    "hold": "buy_and_hold",
    "bh": "buy_and_hold",
    "benchmark": "buy_and_hold",
    "ma": "ma_crossover",
    "macross": "ma_crossover",
    "ma cross": "ma_crossover",
    "moving average": "ma_crossover",
    "moving average crossover": "ma_crossover",
    "crossover": "ma_crossover",
    "golden cross": "ma_crossover",
    "trend": "momentum",
    "trend following": "momentum",
    "mom": "momentum",
    "meanreversion": "mean_reversion",
    "mean reversion": "mean_reversion",
    "reversion": "mean_reversion",
    "revert": "mean_reversion",
    "contrarian": "mean_reversion",
}


def normalize_strategy(name: str) -> str:
    """Resolve a free-text strategy name to a registered key (default momentum)."""
    if not name:
        return "momentum"
    key = str(name).strip().lower().replace("-", "_")
    if key in STRATEGIES:
        return key
    spaced = key.replace("_", " ")
    if spaced in _ALIASES:
        return _ALIASES[spaced]
    if key in _ALIASES:
        return _ALIASES[key]
    return "momentum"


def available_strategies() -> List[str]:
    return list(STRATEGIES.keys())


# The tunable parameters (and their defaults) each strategy exposes. These
# defaults mirror the inline fallbacks in the ``signal_*`` functions, so a
# backtest run with these values reproduces the current out-of-the-box
# behavior exactly. ``buy_and_hold`` has no free parameters.
_DEFAULT_PARAMS: Dict[str, dict] = {
    "buy_and_hold": {},
    "momentum": {"lookback": 90},
    "mean_reversion": {"lookback": 20, "threshold": 1.0},
    "ma_crossover": {"fast": 20, "slow": 50},
}


def default_params(strategy: str) -> dict:
    """Return the default tunable parameters for a strategy (with defaults
    filled in). Unknown strategies resolve via ``normalize_strategy``."""
    return dict(_DEFAULT_PARAMS.get(normalize_strategy(strategy), {}))


def param_grid(strategy: str) -> List[dict]:
    """The configuration grid a researcher would realistically sweep for each
    strategy. These are the "trials" the multiple-testing / overfitting
    diagnostics correct for. ``buy_and_hold`` has no free parameters, so it
    returns a single empty configuration (no selection bias is possible)."""
    key = normalize_strategy(strategy)
    if key == "momentum":
        return [{"lookback": lb} for lb in (20, 40, 60, 90, 120, 150, 200, 252)]
    if key == "mean_reversion":
        return [
            {"lookback": lb, "threshold": th}
            for lb in (10, 15, 20, 30, 40)
            for th in (0.5, 1.0, 1.5, 2.0)
        ]
    if key == "ma_crossover":
        return [
            {"fast": f, "slow": s}
            for f in (5, 10, 20, 50)
            for s in (20, 50, 100, 200)
            if s > f
        ]
    return [{}]


def param_label(params: dict) -> str:
    """Compact human label for a parameter configuration."""
    if not params:
        return "(no parameters)"
    return ", ".join(f"{k}={v}" for k, v in params.items())
