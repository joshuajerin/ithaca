"""Databento historical data adapter.

Databento provides institutional-grade, point-in-time market data with full
survivorship-bias-free history. This adapter implements the same
``fetch_price_history(symbol, range_, interval)`` contract as the Yahoo
adapter so it can be injected into ``DataGateway`` as a drop-in replacement.

Key advantages over Yahoo:
  - Point-in-time (PIT=true): no restatements, no survivorship bias
  - Deep intraday history (years, not days)
  - Institutional data quality with full tick/L2 coverage

Requires the ``databento`` SDK: ``pip install databento``
Set ``DATABENTO_API_KEY`` in the environment.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ._resilient import guard

_SOURCE = "databento"

# Databento dataset mapping for common instrument types.
# Maps a symbol suffix or prefix to a Databento dataset code.
# Users can override with DATABENTO_DATASET env var.
_DEFAULT_DATASET = os.environ.get("DATABENTO_DATASET", "XNAS.ITCH")
_DATASET_OVERRIDES = {
    # US equities by exchange
    "NASDAQ": "XNAS.ITCH",
    "XNAS": "XNAS.ITCH",
    "NYSE": "XNYS.ITCH",
    "XNYS": "XNYS.ITCH",
    "ARCA": "XARC.ITCH",
    "XARC": "XARC.ITCH",
    "BATS": "BATS.ITCH",
    "CBOE": "CBOE.GLOBAL_INDEX",
    # Futures
    "CME": "CME.MDP3",
    "CBOT": "CME.MDP3",
    "COMEX": "CME.MDP3",
    "NYMEX": "CME.MDP3",
    # FX
    "FX": "FX.SPOT",
}

# Range token to days mapping (matching Yahoo's range tokens)
_RANGE_DAYS = {
    "1d": 1, "5d": 5, "1mo": 30, "3mo": 90,
    "6mo": 180, "1y": 365, "2y": 730, "5y": 1825,
    "10y": 3650, "max": 3650,
}

# Interval mapping: our interval -> Databento stype + aggregation
# Databento supports "o" (1-second), "m" (1-minute), "h" (1-hour), "d" (1-day), etc.
_INTERVAL_MAP = {
    "1d": "d",
    "1h": "h",
    "60m": "h",
    "90m": "h",
    "30m": "m",
    "15m": "m",
    "5m": "m",
    "2m": "m",
    "1m": "m",
}


class DatabentoError(RuntimeError):
    """Base error for the Databento adapter."""


class DatabentoNoDataError(DatabentoError):
    """No data returned for the requested symbol/range."""


def _get_client():
    """Build a Databento Historical client from the API key in env."""
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise DatabentoError("DATABENTO_API_KEY is not set")
    try:
        from databento import Historical
    except ImportError as e:
        raise DatabentoError(
            "databento SDK not installed. Install with: pip install databento"
        ) from e
    return Historical(key=key)


def _resolve_dataset(symbol: str) -> str:
    """Pick the Databento dataset for a symbol.

    Override with DATABENTO_DATASET env var; otherwise infer from symbol prefix.
    """
    if os.environ.get("DATABENTO_DATASET"):
        return os.environ["DATABENTO_DATASET"]
    upper = symbol.upper()
    for prefix, dataset in _DATASET_OVERRIDES.items():
        if upper.startswith(prefix + ":") or upper.startswith(prefix + "/"):
            return dataset
    return _DEFAULT_DATASET


def _range_to_dates(range_: str) -> tuple[datetime, datetime]:
    """Convert a range token to (start, end) UTC datetimes."""
    end = datetime.now(tz=timezone.utc)
    days = _RANGE_DAYS.get(range_, 180)
    start = end - timedelta(days=days)
    return start, end


def _normalize_symbol(symbol: str) -> str:
    """Strip exchange prefixes for Databento (it expects bare tickers for most datasets)."""
    s = symbol.upper().strip()
    # Remove common exchange prefixes: "NASDAQ:AAPL" -> "AAPL"
    for sep in (":", "/"):
        if sep in s:
            s = s.split(sep)[-1]
    return s


def _round(v: Optional[float]) -> Optional[float]:
    return round(float(v), 2) if v is not None else None


def fetch_price_history(
    symbol: str,
    range_: str = "6mo",
    interval: str = "1d",
) -> Dict:
    """Return {points: [{d,o,h,l,c,v}], quote: {...}} from Databento.

    Drop-in replacement for ``sources.prices.fetch_price_history``.
    Raises ``DatabentoError`` on failure so the gateway can surface it.
    """
    sym = _normalize_symbol(symbol)
    dataset = _resolve_dataset(symbol)
    db_interval = _INTERVAL_MAP.get(interval, "d")
    start, end = _range_to_dates(range_)

    def _do_fetch():
        client = _get_client()
        data = client.timeseries.get_range(
            dataset=dataset,
            symbols=[sym],
            stype_in="native",
            start=start,
            end=end,
            schema="ohlcv-" + db_interval,
        )
        df = data.to_df()
        if df is None or df.empty:
            raise DatabentoNoDataError(f"no data for {sym} in {dataset}")
        return df

    df = guard(_SOURCE, _do_fetch)

    points: List[dict] = []
    for _, row in df.iterrows():
        ts = row.get("ts_event")
        if hasattr(ts, "to_pydatetime"):
            dt = ts.to_pydatetime()
        elif isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts / 1e9, tz=timezone.utc)
        else:
            dt = ts

        if dt.tzinfo is None:
            dt = dt.replace(tz=timezone.utc)

        close = _round(float(row.get("close", 0)))
        if close is None or close <= 0:
            continue

        if interval == "1d":
            date_key = dt.strftime("%Y-%m-%d")
            points.append({
                "d": date_key,
                "o": _round(float(row.get("open", close))),
                "h": _round(float(row.get("high", close))),
                "l": _round(float(row.get("low", close))),
                "c": close,
                "v": float(row.get("volume", 0) or 0),
            })
        else:
            points.append({
                "t": dt.isoformat(),
                "o": _round(float(row.get("open", close))),
                "h": _round(float(row.get("high", close))),
                "l": _round(float(row.get("low", close))),
                "c": close,
                "v": float(row.get("volume", 0) or 0),
            })

    if not points:
        raise DatabentoNoDataError(f"no usable bars for {sym} in {dataset}")

    last = points[-1]
    price = last["c"]
    prev_close = points[-2]["c"] if len(points) >= 2 else None
    change_pct = None
    if prev_close and prev_close > 0:
        change_pct = round((price - prev_close) / prev_close * 100, 2)

    return {
        "points": points,
        "quote": {
            "symbol": sym,
            "price": price,
            "changePct": change_pct,
            "volume": last.get("v"),
            "asOf": (last.get("t") or last.get("d")),
        },
    }


def fetch_daily_closes(symbol: str, start: str, end: str) -> Dict[str, float]:
    """Real daily closes for `symbol` over the inclusive ISO date range.

    Drop-in replacement for ``sources.prices.fetch_daily_closes``.
    Returns {iso_date: close}.
    """
    sym = _normalize_symbol(symbol)
    dataset = _resolve_dataset(symbol)
    d0 = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    d1 = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) + timedelta(days=1)

    def _do_fetch():
        client = _get_client()
        data = client.timeseries.get_range(
            dataset=dataset,
            symbols=[sym],
            stype_in="native",
            start=d0,
            end=d1,
            schema="ohlcv-d",
        )
        df = data.to_df()
        if df is None or df.empty:
            return None
        return df

    df = guard(_SOURCE, _do_fetch)
    if df is None:
        return {}

    out: Dict[str, float] = {}
    for _, row in df.iterrows():
        ts = row.get("ts_event")
        if hasattr(ts, "to_pydatetime"):
            dt = ts.to_pydatetime()
        elif isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts / 1e9, tz=timezone.utc)
        else:
            dt = ts

        if dt.tzinfo is None:
            dt = dt.replace(tz=timezone.utc)

        c = row.get("close")
        if c is None or float(c) <= 0:
            continue
        out[dt.strftime("%Y-%m-%d")] = round(float(c), 4)

    return out
