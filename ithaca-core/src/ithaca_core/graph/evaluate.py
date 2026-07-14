"""The graph evaluator: StrategySpec + price panel -> a feasible weight panel.

This is the single seam where a primitive's per-symbol signal becomes a sized, risk-gated
book. Today it runs one primitive + one construction scheme; the operator-DAG (post-launch)
will reuse this same evaluate() contract. No lookahead: weights at bar t use only data up
to t, and the backtest applies them to the t->t+1 return.
"""
from __future__ import annotations

import numpy as np

from ..registry import evaluate_primitive
from ..risk import RiskLimits, project_feasible

__all__ = ["evaluate", "rebalance_mask", "construct_row"]


def _trailing_vol(closes: np.ndarray, window: int = 20) -> np.ndarray:
    """Per-column trailing return vol (population), NaN until warmed up."""
    T, N = closes.shape
    out = np.full((T, N), np.nan, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        rets = np.full((T, N), np.nan, dtype=float)
        rets[1:] = np.where(closes[:-1] > 0, closes[1:] / closes[:-1] - 1.0, np.nan)
    for t in range(window, T):
        w = rets[t - window + 1 : t + 1]
        out[t] = np.nanstd(w, axis=0)
    return out


def construct_row(
    scores: np.ndarray,
    selected: np.ndarray,
    vols: np.ndarray,
    scheme: str,
    long_only: bool,
    gross: float,
) -> np.ndarray:
    """Turn one cross-section of (scores, selected, vols) into raw target weights."""
    n = scores.shape[0]
    w = np.zeros(n, dtype=float)
    idx = np.where(selected & np.isfinite(scores))[0]
    if idx.size == 0:
        return w

    if scheme == "equal_weight":
        w[idx] = 1.0
    elif scheme == "rank_weight":
        s = np.clip(scores[idx], 0.0, None)
        w[idx] = s if s.sum() > 0 else 1.0
    elif scheme == "vol_weight":
        v = vols[idx]
        inv = np.where(np.isfinite(v) & (v > 0), 1.0 / v, 0.0)
        w[idx] = inv if inv.sum() > 0 else 1.0
    else:  # defensive — spec enum forbids other values
        w[idx] = 1.0

    if long_only:
        np.clip(w, 0.0, None, out=w)

    total = np.sum(np.abs(w))
    if total > 0:
        w *= gross / total
    return w


def rebalance_mask(dates: list[str], cadence: str) -> np.ndarray:
    """Boolean per-bar mask: True where we rebalance to target (else hold last target).

    daily@close -> every bar; weekly@close -> first bar of each ISO week; monthly@close ->
    first bar of each calendar month. Dates are ISO 'YYYY-MM-DD' strings (sorted ascending).
    """
    import datetime as _dt

    T = len(dates)
    mask = np.zeros(T, dtype=bool)
    if T == 0:
        return mask
    if cadence == "daily@close":
        mask[:] = True
        return mask

    def key(d: str):
        y, m, day = (int(x) for x in d.split("-"))
        if cadence == "monthly@close":
            return (y, m)
        return _dt.date(y, m, day).isocalendar()[:2]  # (iso_year, iso_week)

    prev = None
    for t, d in enumerate(dates):
        k = key(d)
        if k != prev:
            mask[t] = True
            prev = k
    return mask


def evaluate(spec: dict, dates: list[str], closes: np.ndarray) -> dict:
    """Return {weights: (T,N), worstAttest: dict, anyRelaxed: bool}."""
    closes = np.asarray(closes, dtype=float)
    T, N = closes.shape
    strat = spec["strategy"]
    con = spec["construction"]
    limits = RiskLimits.from_spec(spec["risk"])

    scores, selected = evaluate_primitive(strat["id"], closes, strat.get("params"))
    vols = _trailing_vol(closes) if con["scheme"] == "vol_weight" else np.zeros((T, N))
    mask = rebalance_mask(dates, spec["execution"]["rebalance"])

    weights = np.zeros((T, N), dtype=float)
    last = np.zeros(N, dtype=float)
    worst: dict | None = None
    any_relaxed = False

    for t in range(T):
        if mask[t]:
            raw = construct_row(
                scores[t], selected[t], vols[t],
                con["scheme"], bool(con.get("long_only", True)), float(con["gross"]),
            )
            projected, att = project_feasible(raw, limits)
            if not att.ok or att.gross + 1e-9 < float(np.sum(np.abs(raw))):
                any_relaxed = True
            if worst is None or att.gross > worst["gross"]:
                worst = att.to_dict()
            last = projected
        weights[t] = last

    return {
        "weights": weights,
        "worstAttest": worst or {"ok": True, "gross": 0.0, "net": 0.0, "maxName": 0.0, "violations": []},
        "anyRelaxed": any_relaxed,
    }
