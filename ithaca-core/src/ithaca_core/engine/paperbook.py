"""Paper-book mark-to-market engine.

A paper book is a *fixed* set of share positions plus cash, created when a
strategy is promoted to the paper stage. It is marked to market against REAL
prices: the current value uses live quotes, and the P&L *history* is
reconstructed from the real daily closes of the held names since inception — no
synthetic curve is ever stored. All functions here are pure (no I/O); the caller
supplies prices and close series.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from . import stats


def position_marks(positions: List[dict], price_map: Dict[str, float]) -> List[dict]:
    """Mark each position to a current price into a per-name P&L row.

    ``positions`` is a list of ``{symbol, shares, entryPrice}``; ``price_map``
    maps a symbol to its latest price. Names without a usable price keep their
    entry price as the mark (zero P&L) so the book still totals correctly.
    """
    out: List[dict] = []
    for p in positions:
        sym = p["symbol"]
        shares = float(p.get("shares") or 0.0)
        entry = float(p.get("entryPrice") or 0.0)
        px = price_map.get(sym)
        priced = px is not None and px > 0
        mark = float(px) if priced else entry
        mv = shares * mark
        cost = shares * entry
        out.append({
            "symbol": sym,
            "shares": round(shares, 4),
            "entryPrice": round(entry, 4),
            "price": round(mark, 4),
            "marketValue": round(mv, 2),
            "costBasis": round(cost, 2),
            "pnl": round(mv - cost, 2),
            "pnlPct": round((mv / cost - 1.0) * 100.0, 2) if cost else 0.0,
            "priced": priced,
        })
    out.sort(key=lambda r: r["marketValue"], reverse=True)
    return out


def book_value(positions: List[dict], cash: float, price_map: Dict[str, float]) -> float:
    """Total book value = cash + Σ shares·price (entry price when unpriced)."""
    total = float(cash or 0.0)
    for p in positions:
        shares = float(p.get("shares") or 0.0)
        px = price_map.get(p["symbol"])
        mark = float(px) if (px is not None and px > 0) else float(p.get("entryPrice") or 0.0)
        total += shares * mark
    return total


def exposures(marks: List[dict], book_val: float) -> List[dict]:
    """Per-name portfolio weight (% of book value) from marked positions."""
    if book_val <= 0:
        return []
    out = [{"symbol": m["symbol"], "weight": round(m["marketValue"] / book_val * 100.0, 2)}
           for m in marks]
    out.sort(key=lambda r: abs(r["weight"]), reverse=True)
    return out


def nav_curve(
    positions: List[dict],
    cash: float,
    capital: float,
    closes_by_symbol: Dict[str, List[dict]],
    inception: str,
) -> List[dict]:
    """Reconstruct the book's NAV/P&L path from REAL closes since inception.

    ``closes_by_symbol`` maps each held symbol to a ``[{"t","c"}, ...]`` close
    series (ISO date strings, ascending). For every trading date at or after
    ``inception`` present in any held name, NAV = cash + Σ shares·close, carrying
    the last known close forward for a name that did not trade that day. Returns
    ``[{t, nav, pnl, pnlPct}, ...]``; empty when no real history exists yet.
    """
    if not positions:
        return []
    per_sym: Dict[str, Dict[str, float]] = {}
    date_set = set()
    for p in positions:
        sym = p["symbol"]
        pts = closes_by_symbol.get(sym) or []
        m: Dict[str, float] = {}
        for pt in pts:
            t = pt.get("t")
            c = pt.get("c")
            if t is None or c is None:
                continue
            if str(t) >= inception:
                m[str(t)] = float(c)
        per_sym[sym] = m
        date_set.update(m.keys())
    if not date_set:
        return []
    dates = sorted(date_set)
    last = {p["symbol"]: float(p.get("entryPrice") or 0.0) for p in positions}
    cap = float(capital) if capital else 0.0
    curve: List[dict] = []
    for d in dates:
        for p in positions:
            sym = p["symbol"]
            if d in per_sym[sym]:
                last[sym] = per_sym[sym][d]
        nav = float(cash or 0.0) + sum(float(p.get("shares") or 0.0) * last[p["symbol"]] for p in positions)
        curve.append({
            "t": d,
            "nav": round(nav, 2),
            "pnl": round(nav - cap, 2),
            "pnlPct": round((nav / cap - 1.0) * 100.0, 3) if cap else 0.0,
        })
    return curve


def realized_stats(curve: List[dict]) -> Dict[str, float]:
    """Realized performance stats for the NAV curve (reuses the shared stat block).

    Returns an empty dict when there are too few points for a meaningful read.
    """
    if len(curve) < 3:
        return {}
    equity = np.array([c["nav"] for c in curve], dtype=float)
    if equity[0] <= 0:
        return {}
    returns = np.empty(equity.size, dtype=float)
    returns[0] = 0.0
    returns[1:] = equity[1:] / equity[:-1] - 1.0
    return stats.performance_stats(equity, returns)
