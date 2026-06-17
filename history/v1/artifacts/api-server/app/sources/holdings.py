"""ETF holdings/constituents adapter using yfinance ``funds_data.top_holdings``.

Yahoo's free quote-summary feed only exposes a fund's TOP holdings (typically
~10 names), not its full constituent list — paid full-holdings feeds are out of
scope. We surface exactly what the free path returns and report the coverage
(how much of the fund's weight the listed names span) honestly, never padding or
imputing the rest.

``holdingPercent`` arrives as a fraction (e.g. ``0.0712`` = 7.12%); we convert
to a percent. Names come straight from the feed, so a holding ticker need not be
in the terminal's own tracked universe.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

import yfinance as yf

from ._resilient import guard as _guard

_SOURCE = "yfinance"


def _fetch_top_holdings(etf: str) -> List[dict]:
    """Fetch an ETF's top holdings, raising a clean ValueError when empty.

    Kept separate so the resilient ``guard`` retries only on throttles while a
    genuine "no holdings for this instrument" (e.g. a single stock, or a fund
    Yahoo does not break out) propagates immediately.
    """
    df = yf.Ticker(etf).funds_data.top_holdings
    if df is None or getattr(df, "empty", True):
        raise ValueError(f"no holdings for {etf}")

    out: List[dict] = []
    for sym, row in df.iterrows():
        try:
            pct = float(row.get("Holding Percent"))
        except (TypeError, ValueError):
            continue
        if pct <= 0:
            continue
        name = row.get("Name")
        out.append({
            "symbol": str(sym).upper().strip(),
            "name": (str(name).strip() if name else str(sym).upper().strip()),
            "weight": round(pct * 100.0, 4),  # fraction -> percent
        })
    if not out:
        raise ValueError(f"no holdings for {etf}")
    # Largest weight first — the feed is usually already sorted, but don't rely on it.
    out.sort(key=lambda h: h["weight"], reverse=True)
    return out


def fetch_etf_holdings(etf: str) -> Optional[Dict]:
    """Return ``{etf, holdings:[{symbol,name,weight}], asOf, source}`` or ``None``.

    ``None`` (rather than a raise) when the instrument has no real fund
    composition or the lookup throttles/fails — the caller then reports the gap
    instead of fabricating constituents.
    """
    e = (etf or "").upper().strip().lstrip("$")
    if not e:
        return None
    try:
        holdings = _guard(_SOURCE, _fetch_top_holdings, e)
    except Exception:  # noqa: BLE001 — best-effort; caller reports the gap
        return None
    if not holdings:
        return None
    return {
        "etf": e,
        "holdings": holdings,
        "asOf": date.today().isoformat(),
        "source": "live",
    }
