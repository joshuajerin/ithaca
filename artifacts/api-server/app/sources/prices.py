"""OHLCV price adapter using Yahoo Finance's key-less chart endpoint.

`https://query1.finance.yahoo.com/v8/finance/chart/{symbol}` returns a daily
series plus a `meta` block with the current quote. We normalize the series into
the ohlcv schema and lift the quote fields the fundamentals snapshot needs.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional

import httpx

_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AgenticTerminal/1.0)"}
_TIMEOUT = httpx.Timeout(12.0)


def fetch_price_history(symbol: str, range_: str = "6mo", interval: str = "1d") -> Dict:
    """Return {points: [{d,o,h,l,c,v}], quote: {...}}.

    Raises on network/parse failure so the worker can log and skip this symbol.
    """
    url = f"{_BASE}{symbol.upper()}"
    params = {"range": range_, "interval": interval, "includePrePost": "false"}
    with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise ValueError(f"no chart data for {symbol}")
    r0 = result[0]
    meta = r0.get("meta") or {}
    timestamps = r0.get("timestamp") or []
    quote = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    points: List[dict] = []
    for i, ts in enumerate(timestamps):
        c = _at(closes, i)
        if c is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        points.append({
            "d": d.isoformat(),
            "o": _round(_at(opens, i, c)),
            "h": _round(_at(highs, i, c)),
            "l": _round(_at(lows, i, c)),
            "c": _round(c),
            "v": float(_at(volumes, i, 0) or 0),
        })

    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    change_pct = None
    if price is not None and prev:
        change_pct = round((price - prev) / prev * 100, 2)

    return {
        "points": points,
        "quote": {
            "symbol": meta.get("symbol", symbol.upper()),
            "name": meta.get("longName") or meta.get("shortName"),
            "price": price,
            "changePct": change_pct,
            "volume": meta.get("regularMarketVolume"),
            "week52High": meta.get("fiftyTwoWeekHigh"),
            "week52Low": meta.get("fiftyTwoWeekLow"),
            "asOf": _as_of(meta.get("regularMarketTime")),
        },
    }


def _at(arr, i, default=None):
    try:
        v = arr[i]
        return default if v is None else v
    except IndexError:
        return default


def _round(v: Optional[float]) -> Optional[float]:
    return round(float(v), 2) if v is not None else None


def _as_of(ts) -> Optional[str]:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
