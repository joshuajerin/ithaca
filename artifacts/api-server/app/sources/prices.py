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

# Intraday resolutions Yahoo's chart endpoint serves, mapped to the windows it
# will actually honor for each (longest last). These mirror real upstream limits:
# 1-minute bars go back ~7 days, the finer multi-minute bars ~60 days, and hourly
# bars up to ~2 years. Windows that aren't plain range tokens ("7d", "60d") are
# fetched with explicit period1/period2 epochs since Yahoo has no matching token.
# Requests outside these windows return a clean "unavailable" rather than being
# silently truncated or faked.
INTRADAY_RANGES = {
    "1m": ["1d", "5d", "7d"],
    "2m": ["1d", "5d", "1mo", "60d"],
    "5m": ["1d", "5d", "1mo", "60d"],
    "15m": ["1d", "5d", "1mo", "60d"],
    "30m": ["1d", "5d", "1mo", "60d"],
    "90m": ["1d", "5d", "1mo", "60d"],
    "60m": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y"],
    "1h": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y"],
}

# Windows expressed in days that Yahoo has no range token for; fetched via
# period1/period2 epoch params instead.
INTRADAY_CUSTOM_DAYS = {"7d": 7, "60d": 60}

INTRADAY_DEFAULT_RANGE = {
    "1m": "1d", "2m": "1d", "5m": "5d", "15m": "5d", "30m": "1mo",
    "90m": "1mo", "60m": "1mo", "1h": "1mo",
}


class IntradayUnavailable(Exception):
    """Raised when an intraday window/resolution is not available upstream.

    Callers should surface this as a clean "not available" panel state rather
    than substituting any synthetic or daily data.
    """


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


def fetch_daily_closes(symbol: str, start: str, end: str) -> Dict[str, float]:
    """Real daily closes for `symbol` over the inclusive ISO date range.

    Uses Yahoo's chart endpoint with explicit period1/period2 epochs so arbitrary
    historical windows (e.g. the 2008 crisis) return genuine daily bars rather
    than a truncated range token. Returns {iso_date: close}. Names that did not
    trade in the window come back with fewer (or no) keys — callers must treat a
    sparse/empty result as missing coverage, never impute it.

    Raises on network/parse failure so the caller can fall back to a clean
    "no coverage" state.
    """
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    p1 = int(datetime(d0.year, d0.month, d0.day, tzinfo=timezone.utc).timestamp())
    # +1 day so the end date itself is inclusive of the upstream window.
    p2 = int(datetime(d1.year, d1.month, d1.day, tzinfo=timezone.utc).timestamp()) + 86400

    url = f"{_BASE}{symbol.upper()}"
    params = {"interval": "1d", "period1": p1, "period2": p2, "includePrePost": "false"}
    with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return {}
    r0 = result[0]
    timestamps = r0.get("timestamp") or []
    quote = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []

    out: Dict[str, float] = {}
    for i, ts in enumerate(timestamps):
        c = _at(closes, i)
        if c is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        out[d] = round(float(c), 4)
    return out


def fetch_intraday(symbol: str, interval: str = "5m", range_: Optional[str] = None) -> Dict:
    """Return intraday OHLCV for `symbol` at the requested resolution.

    Returns {points: [{t,o,h,l,c,v}], interval, range, asOf, price, name,
    currency}, where `t` is an ISO datetime (UTC) per bar and `interval`/`range`
    reflect what was actually served.

    Raises `IntradayUnavailable` when the resolution is not intraday, the
    requested window exceeds the source's limit, or no usable bars come back.
    Raises on network/parse failure so the caller can report a clean error.
    """
    iv = (interval or "5m").lower()
    if iv not in INTRADAY_RANGES:
        raise IntradayUnavailable(
            f"{interval} is not an intraday resolution "
            f"(supported: {', '.join(INTRADAY_RANGES)})"
        )
    allowed = INTRADAY_RANGES[iv]
    rng = (range_ or INTRADAY_DEFAULT_RANGE[iv]).lower()
    if rng not in allowed:
        raise IntradayUnavailable(
            f"Yahoo serves {iv} bars only up to {allowed[-1]}; "
            f"a {rng} window exceeds that limit"
        )

    url = f"{_BASE}{symbol.upper()}"
    params = {"interval": iv, "includePrePost": "false"}
    if rng in INTRADAY_CUSTOM_DAYS:
        now = int(datetime.now(tz=timezone.utc).timestamp())
        params["period1"] = now - INTRADAY_CUSTOM_DAYS[rng] * 86400
        params["period2"] = now
    else:
        params["range"] = rng
    with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise IntradayUnavailable(f"no intraday data returned for {symbol}")
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
        t = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        points.append({
            "t": t,
            "o": _round(_at(opens, i, c)),
            "h": _round(_at(highs, i, c)),
            "l": _round(_at(lows, i, c)),
            "c": _round(c),
            "v": float(_at(volumes, i, 0) or 0),
        })

    if not points:
        raise IntradayUnavailable(
            f"no usable {iv} bars for {symbol} over {rng}"
        )

    as_of = _as_of(meta.get("regularMarketTime")) or points[-1]["t"]
    return {
        "points": points,
        "interval": iv,
        "range": rng,
        "asOf": as_of,
        "price": meta.get("regularMarketPrice"),
        "name": meta.get("longName") or meta.get("shortName"),
        "currency": meta.get("currency") or "USD",
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
