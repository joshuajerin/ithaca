"""Fundamentals adapter using yfinance, which handles Yahoo's crumb/cookie auth
for the otherwise key-less quote-summary data. Normalizes into the fundamentals
schema and maps the company's sector to an internal sector id.
"""
from __future__ import annotations

from typing import Dict, Optional

import yfinance as yf

from .sectors import map_sector


def fetch_fundamentals(symbol: str) -> Dict:
    """Return a normalized fundamentals dict for `symbol`. Raises on failure."""
    sym = symbol.upper()
    ticker = yf.Ticker(sym)
    info = ticker.info or {}
    if not info.get("regularMarketPrice") and not info.get("currentPrice") \
            and not info.get("marketCap"):
        raise ValueError(f"no fundamentals for {sym}")

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
    change_pct = None
    if price is not None and prev:
        change_pct = round((price - prev) / prev * 100, 2)

    net_margin = info.get("profitMargins")
    if net_margin is not None:
        net_margin = round(net_margin * 100, 2)  # fraction -> percent

    return {
        "symbol": sym,
        "name": info.get("longName") or info.get("shortName") or sym,
        "price": _f(price),
        "changePct": change_pct,
        "marketCap": _f(info.get("marketCap")),
        "peRatio": _f(info.get("trailingPE")),
        "volume": _f(info.get("regularMarketVolume") or info.get("volume")),
        "revenue": _f(info.get("totalRevenue")),
        "netMargin": net_margin,
        "eps": _f(info.get("trailingEps")),
        "dividendYield": _f(info.get("dividendYield")) or 0.0,
        "beta": _f(info.get("beta")),
        "week52High": _f(info.get("fiftyTwoWeekHigh")),
        "week52Low": _f(info.get("fiftyTwoWeekLow")),
        "description": (info.get("longBusinessSummary") or "")[:600] or None,
        "sector": map_sector(info.get("sector"), info.get("industry")),
    }


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
