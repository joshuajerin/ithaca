"""Stress-testing primitives (pure numpy, no I/O).

Two kinds of stress, both grounded in real inputs supplied by the caller:

- ``factor_shock_pnl`` maps a hypothetical shock to one or more model factors
  through a portfolio's REAL factor exposures (``b = X' w``) to an estimated
  book P&L. This is the model-consistent way to express "what if Momentum sells
  off 8%" or "equities -10%" (a shock to the Market factor).
- ``replay_window`` replays the REAL daily closes a book's holdings actually
  printed during a historical window onto the current weights, returning the
  simulated point-to-point book P&L, the within-window max drawdown, and which
  names were/weren't covered. Nothing is imputed: a holding with no price
  history in the window is reported as missing, never filled in.

Callers (the skill builders) source the exposures / closes and decide live-vs-
mock provenance; this module only does arithmetic, mirroring the rest of
``app.engine``.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from .stats import max_drawdown

# A holding needs at least this many closes inside a window to be replayed.
MIN_WINDOW_POINTS = 5


def factor_shock_pnl(
    exposures: Dict[str, float], shocks: Dict[str, float]
) -> Dict:
    """Estimate book P&L from shocking model factors through real exposures.

    ``exposures`` maps factor name -> portfolio exposure (``b_k``, signed).
    ``shocks`` maps factor name -> shock in PERCENT (e.g. ``-10`` for -10%).
    Book impact from factor k is ``b_k * shock_k``. Shocks naming a factor not
    in ``exposures`` are ignored (reported nowhere — the caller controls inputs).

    Returns ``{"contributions": [{factor, exposure, shockPct, pnlPct}],
    "totalPnlPct"}`` with P&L expressed in percent of NAV.
    """
    contributions: List[dict] = []
    total = 0.0
    for factor, pct in shocks.items():
        if factor not in exposures:
            continue
        exp = float(exposures[factor])
        shock = float(pct)
        pnl = exp * shock / 100.0  # fraction of NAV
        total += pnl
        contributions.append({
            "factor": factor,
            "exposure": round(exp, 3),
            "shockPct": round(shock, 2),
            "pnlPct": round(pnl * 100.0, 2),
        })
    return {"contributions": contributions, "totalPnlPct": round(total * 100.0, 2)}


def asset_shock_pnl(
    weights: Dict[str, float], shocks: Dict[str, float]
) -> Dict:
    """Estimate book P&L from shocking individual holdings directly.

    ``weights`` maps symbol -> signed NAV-fraction weight; ``shocks`` maps
    symbol -> price shock in PERCENT. Contribution from name i is
    ``w_i * shock_i``. Shocks for names not held are ignored.
    """
    contributions: List[dict] = []
    total = 0.0
    for sym, pct in shocks.items():
        s = (sym or "").upper()
        if s not in weights:
            continue
        w = float(weights[s])
        shock = float(pct)
        pnl = w * shock / 100.0
        total += pnl
        contributions.append({
            "symbol": s,
            "weightPct": round(w * 100.0, 2),
            "shockPct": round(shock, 2),
            "pnlPct": round(pnl * 100.0, 2),
        })
    return {"contributions": contributions, "totalPnlPct": round(total * 100.0, 2)}


def univariate_beta(asset: np.ndarray, factor: np.ndarray) -> Optional[float]:
    """Least-squares sensitivity of ``asset`` to ``factor`` (the OLS slope).

    ``asset`` and ``factor`` are equal-length, date-aligned series (e.g. a
    stock's daily returns and a market proxy's daily returns, or a stock's
    returns and the daily CHANGE in a yield level). Returns the slope
    ``cov(asset, factor) / var(factor)`` — the estimated move in ``asset`` per
    one unit move in ``factor`` — or ``None`` when the inputs are mismatched,
    too short, or the factor has no variance (so a credible beta can't be fit).
    Nothing is imputed; callers treat ``None`` as "no coverage" for that name.
    """
    a = np.asarray(asset, dtype=float)
    f = np.asarray(factor, dtype=float)
    if a.size != f.size or a.size < 2:
        return None
    fv = f - f.mean()
    denom = float(fv @ fv)
    if denom <= 0.0:
        return None
    av = a - a.mean()
    return float((fv @ av) / denom)


def replay_window(
    weights: Dict[str, float],
    closes_by_sym: Dict[str, Dict[str, float]],
    start: str,
    end: str,
) -> Optional[Dict]:
    """Replay a historical window's REAL returns onto the current book.

    ``weights`` maps symbol -> signed NAV-fraction weight. ``closes_by_sym``
    maps symbol -> {iso_date: close}. ``start``/``end`` are inclusive ISO date
    bounds. A holding is covered only if it has >= ``MIN_WINDOW_POINTS`` closes
    inside the window; uncovered names are returned in ``missing`` rather than
    imputed.

    Returns ``None`` when no holding has data in the window. Otherwise returns
    ``{bookPnlPct, maxDrawdownPct, covered, missing, perHolding}`` where
    ``bookPnlPct`` is the point-to-point Sigma(w_i * window_return_i) in percent,
    ``maxDrawdownPct`` is the worst peak-to-trough of the aligned daily book
    equity path, and ``perHolding`` lists each covered name's window return and
    P&L contribution (most negative first).
    """
    covered: Dict[str, tuple] = {}
    missing: List[str] = []
    for sym, w in weights.items():
        m = closes_by_sym.get(sym) or {}
        ds = sorted(d for d, c in m.items() if start <= d <= end and c)
        if len(ds) >= MIN_WINDOW_POINTS:
            covered[sym] = (float(w), ds, m)
        else:
            missing.append(sym)

    if not covered:
        return None

    per_holding: List[dict] = []
    book_pnl = 0.0
    for sym, (w, ds, m) in covered.items():
        first, last = m[ds[0]], m[ds[-1]]
        ret = (last / first - 1.0) if first else 0.0
        pnl = w * ret
        book_pnl += pnl
        per_holding.append({
            "symbol": sym,
            "weightPct": round(w * 100.0, 2),
            "returnPct": round(ret * 100.0, 2),
            "pnlPct": round(pnl * 100.0, 2),
        })
    per_holding.sort(key=lambda h: h["pnlPct"])

    # Aligned daily book equity path over the dates every covered name shares.
    max_dd = 0.0
    common: set = set.intersection(*[set(ds) for _, ds, _ in covered.values()])
    common_sorted = sorted(common)
    if len(common_sorted) >= 3:
        syms = list(covered.keys())
        mat = np.array(
            [[covered[s][2][d] for d in common_sorted] for s in syms], dtype=float
        )  # (n, T)
        w_arr = np.array([covered[s][0] for s in syms], dtype=float)
        rets = mat[:, 1:] / mat[:, :-1] - 1.0  # (n, T-1)
        book_daily = (w_arr[:, None] * rets).sum(axis=0)  # (T-1,)
        equity = np.concatenate([[1.0], np.cumprod(1.0 + book_daily)])
        max_dd = float(max_drawdown(equity))

    return {
        "bookPnlPct": round(book_pnl * 100.0, 2),
        "maxDrawdownPct": round(max_dd * 100.0, 2),
        "covered": list(covered.keys()),
        "missing": missing,
        "perHolding": per_holding,
    }
