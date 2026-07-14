"""Declarative strategy primitives (the closed registry the StrategySpec.strategy.id maps to).

Each primitive is a pure ``(closes_panel, params) -> (scores, selected)`` function over a
price panel of shape ``(T, N)`` (T bars, N symbols). It uses only information up to and
including bar ``t`` (no lookahead) and returns:

  scores   : (T, N) float — higher = more preferred; NaN where undefined (warm-up).
  selected : (T, N) bool  — which names the strategy wants long at bar t.

Cross-sectional weighting is applied afterwards by ``graph.construct`` per the spec's
``construction`` block. This keeps signal (here) and sizing (there) separate — and means
there is no free-form code anywhere: a spec selects a primitive by id, never supplies one.
"""
from __future__ import annotations

import numpy as np

__all__ = ["PRIMITIVES", "evaluate_primitive", "default_params"]


# ---- panel helpers (column-wise, no lookahead) -----------------------------------------

def _sma_panel(closes: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window))
    T = closes.shape[0]
    out = np.full_like(closes, np.nan, dtype=float)
    if T == 0:
        return out
    csum = np.cumsum(closes, axis=0, dtype=float)
    for t in range(window - 1, T):
        total = csum[t] - (csum[t - window] if t - window >= 0 else 0.0)
        out[t] = total / window
    return out


def _trailing_return(closes: np.ndarray, lookback: int) -> np.ndarray:
    lookback = max(1, int(lookback))
    T = closes.shape[0]
    out = np.full_like(closes, np.nan, dtype=float)
    for t in range(lookback, T):
        base = closes[t - lookback]
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(base > 0, closes[t] / base - 1.0, np.nan)
        out[t] = r
    return out


def _rolling_z(closes: np.ndarray, lookback: int) -> np.ndarray:
    """Z-score of the latest close vs its trailing window (population std)."""
    lookback = max(2, int(lookback))
    T, N = closes.shape
    out = np.full((T, N), np.nan, dtype=float)
    for t in range(lookback - 1, T):
        window = closes[t - lookback + 1 : t + 1]
        mean = window.mean(axis=0)
        std = window.std(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[t] = np.where(std > 0, (closes[t] - mean) / std, np.nan)
    return out


# ---- primitives ------------------------------------------------------------------------

def _momentum(closes: np.ndarray, params: dict) -> tuple[np.ndarray, np.ndarray]:
    lookback = int(params.get("lookback", 90))
    scores = _trailing_return(closes, lookback)
    selected = np.isfinite(scores) & (scores > 0)
    return scores, selected


def _ma_cross(closes: np.ndarray, params: dict) -> tuple[np.ndarray, np.ndarray]:
    fast = max(1, int(params.get("fast", 20)))
    slow = max(fast + 1, int(params.get("slow", 50)))
    f = _sma_panel(closes, fast)
    s = _sma_panel(closes, slow)
    with np.errstate(divide="ignore", invalid="ignore"):
        scores = np.where(s > 0, (f - s) / s, np.nan)
    selected = np.isfinite(f) & np.isfinite(s) & (f > s)
    return scores, selected


def _mean_reversion(closes: np.ndarray, params: dict) -> tuple[np.ndarray, np.ndarray]:
    lookback = int(params.get("lookback", 20))
    threshold = float(params.get("threshold", 1.0))
    z = _rolling_z(closes, lookback)
    scores = -z  # oversold (z<0) => positive score
    selected = np.isfinite(z) & (z < -threshold)
    return scores, selected


def _rank_returns(closes: np.ndarray, params: dict) -> tuple[np.ndarray, np.ndarray]:
    lookback = int(params.get("lookback", 90))
    top = max(1, int(params.get("top", 3)))
    scores = _trailing_return(closes, lookback)
    T, N = scores.shape
    selected = np.zeros((T, N), dtype=bool)
    for t in range(T):
        finite = np.where(np.isfinite(scores[t]))[0]
        if finite.size == 0:
            continue
        order = finite[np.argsort(scores[t, finite])[::-1]]  # highest score first
        selected[t, order[: top]] = True
    return scores, selected


PRIMITIVES = {
    "momentum": _momentum,
    "ma_cross": _ma_cross,
    "mean_reversion": _mean_reversion,
    "rank_returns": _rank_returns,
}

_DEFAULT_PARAMS = {
    "momentum": {"lookback": 90},
    "ma_cross": {"fast": 20, "slow": 50},
    "mean_reversion": {"lookback": 20, "threshold": 1.0},
    "rank_returns": {"lookback": 90, "top": 3},
}


def default_params(primitive_id: str) -> dict:
    return dict(_DEFAULT_PARAMS.get(primitive_id, {}))


def evaluate_primitive(primitive_id: str, closes: np.ndarray, params: dict | None = None):
    if primitive_id not in PRIMITIVES:
        raise ValueError(f"unknown strategy primitive: {primitive_id!r} (have {sorted(PRIMITIVES)})")
    merged = default_params(primitive_id)
    merged.update(params or {})
    return PRIMITIVES[primitive_id](np.asarray(closes, dtype=float), merged)
