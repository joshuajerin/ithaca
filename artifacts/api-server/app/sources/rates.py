"""Live rates & credit-spread adapter for the Fixed Income skills.

Two key-less / low-friction public sources:

- **Treasury par yields** — the U.S. Treasury's *Daily Treasury Par Yield Curve
  Rates* CSV (key-less). One file per calendar year; the most recent row is the
  latest published curve. We also pull the two prior years so the yield-curve
  panel's 1y/2y-ago comparison lines are real history, not a synthetic shift.

- **Credit spreads** — ICE BofA OAS indices (used as bond-spread / CDS proxies),
  served by the FRED API. FRED's key-less CSV download is unreliable from some
  egress environments, so we use the official API host with a free
  ``FRED_API_KEY``. Without a key (or on any failure) callers fall back to
  curated mock spreads and honestly report ``source="mock"``.

Everything here raises / returns ``None`` on failure rather than substituting
fabricated numbers, so the panel source badge only says "live" when real data
actually flowed.
"""
from __future__ import annotations

import csv
import io
import os
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AgenticTerminal/1.0)"}
_TIMEOUT = httpx.Timeout(15.0)

# --- U.S. Treasury par yield curve ------------------------------------------

_TREASURY_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/"
    "interest-rates/daily-treasury-rates.csv/{year}/all"
)

# Map the panel's canonical tenor labels to the Treasury CSV column headers.
_TREASURY_COLS = {
    "1M": "1 Mo",
    "3M": "3 Mo",
    "6M": "6 Mo",
    "1Y": "1 Yr",
    "2Y": "2 Yr",
    "3Y": "3 Yr",
    "5Y": "5 Yr",
    "7Y": "7 Yr",
    "10Y": "10 Yr",
    "20Y": "20 Yr",
    "30Y": "30 Yr",
}


def _parse_treasury_csv(text: str) -> List[Tuple[date, Dict[str, float]]]:
    """Parse a Treasury par-yield CSV into [(date, {tenor: pct})] rows."""
    rows: List[Tuple[date, Dict[str, float]]] = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        date_str = (raw.get("Date") or "").strip()
        if not date_str:
            continue
        try:
            d = datetime.strptime(date_str, "%m/%d/%Y").date()
        except ValueError:
            continue
        yields: Dict[str, float] = {}
        for tenor, col in _TREASURY_COLS.items():
            val = (raw.get(col) or "").strip()
            if not val:
                continue
            try:
                yields[tenor] = float(val)
            except ValueError:
                continue
        if yields:
            rows.append((d, yields))
    return rows


def _fetch_treasury_year(year: int) -> List[Tuple[date, Dict[str, float]]]:
    url = _TREASURY_URL.format(year=year)
    params = {
        "type": "daily_treasury_yield_curve",
        "field_tdr_date_value": str(year),
        "_format": "csv",
    }
    with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return _parse_treasury_csv(resp.text)


def _closest_row(
    rows: List[Tuple[date, Dict[str, float]]], target: date
) -> Optional[Tuple[date, Dict[str, float]]]:
    if not rows:
        return None
    return min(rows, key=lambda r: abs((r[0] - target).days))


def fetch_treasury_curve() -> Optional[Dict]:
    """Return the latest real Treasury par-yield curve plus 1y/2y-ago history.

    Shape::

        {
            "tenors":  {tenor: spot_pct},
            "ago1y":   {tenor: pct},   # may be empty if history unavailable
            "ago2y":   {tenor: pct},
            "asOf":    "YYYY-MM-DD",
            "source":  "live",
        }

    Returns ``None`` on any network/parse failure so the caller falls back to a
    clean mock curve. Only the current-year fetch is required; the prior-year
    history lines degrade gracefully to empty if those fetches fail.
    """
    today = date.today()
    try:
        cur_rows = _fetch_treasury_year(today.year)
    except Exception:
        return None
    if not cur_rows:
        return None

    latest_date, latest = max(cur_rows, key=lambda r: r[0])

    ago1y: Dict[str, float] = {}
    ago2y: Dict[str, float] = {}
    try:
        prev_rows = _fetch_treasury_year(today.year - 1)
        match = _closest_row(prev_rows, latest_date.replace(year=latest_date.year - 1))
        if match:
            ago1y = match[1]
    except Exception:
        pass
    try:
        prev2_rows = _fetch_treasury_year(today.year - 2)
        match = _closest_row(prev2_rows, latest_date.replace(year=latest_date.year - 2))
        if match:
            ago2y = match[1]
    except Exception:
        pass

    return {
        "tenors": latest,
        "ago1y": ago1y,
        "ago2y": ago2y,
        "asOf": latest_date.isoformat(),
        "source": "live",
    }


def interp_treasury(curve: Dict[str, float], years: float) -> Optional[float]:
    """Linearly interpolate a par yield (pct) at `years` from a {tenor: pct} map."""
    pts = sorted(
        ((_TENOR_YEARS[t], v) for t, v in curve.items() if t in _TENOR_YEARS),
        key=lambda p: p[0],
    )
    if not pts:
        return None
    if years <= pts[0][0]:
        return pts[0][1]
    if years >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= years <= x1:
            if x1 == x0:
                return y0
            w = (years - x0) / (x1 - x0)
            return y0 + w * (y1 - y0)
    return pts[-1][1]


_TENOR_YEARS = {
    "1M": 1 / 12, "3M": 0.25, "6M": 0.5, "1Y": 1, "2Y": 2, "3Y": 3,
    "5Y": 5, "7Y": 7, "10Y": 10, "20Y": 20, "30Y": 30,
}


# --- ICE BofA OAS credit spreads (via FRED) ---------------------------------

_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# Rating bucket -> FRED ICE BofA OAS series id. Values are published in percent;
# we convert to basis points. IG = US Corporate; HY = US High Yield Master II.
_FRED_SERIES = {
    "AAA": "BAMLC0A1CAAA",
    "AA": "BAMLC0A2CAA",
    "A": "BAMLC0A3CA",
    "BBB": "BAMLC0A4CBBB",
    "BB": "BAMLH0A1HYBB",
    "B": "BAMLH0A2HYB",
    "CCC": "BAMLH0A3HYC",
    "IG": "BAMLC0A0CM",       # investment-grade master
    "HY": "BAMLH0A0HYM2",     # high-yield master
}


def fred_api_key() -> Optional[str]:
    key = os.environ.get("FRED_API_KEY")
    return key.strip() if key and key.strip() else None


def _fetch_fred_latest(series_id: str, api_key: str) -> Optional[Tuple[date, float]]:
    """Latest non-empty observation for a FRED series as (date, value_pct)."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 25,
    }
    with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
        resp = client.get(_FRED_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
    for obs in payload.get("observations") or []:
        val = (obs.get("value") or "").strip()
        if val in ("", "."):
            continue
        try:
            v = float(val)
        except ValueError:
            continue
        try:
            d = datetime.strptime(obs["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            d = date.today()
        return d, v
    return None


def fetch_credit_spreads() -> Optional[Dict]:
    """Return live ICE BofA OAS by rating bucket (basis points), or ``None``.

    Shape::

        {"buckets": {"AAA": bps, ... "CCC": bps, "IG": bps, "HY": bps},
         "asOf": "YYYY-MM-DD", "source": "live"}

    Requires a ``FRED_API_KEY``. Returns ``None`` when no key is configured or
    when not a single series could be fetched, so callers fall back to mock
    spreads and report ``source="mock"`` rather than inventing levels.
    """
    api_key = fred_api_key()
    if not api_key:
        return None

    buckets: Dict[str, float] = {}
    latest: Optional[date] = None
    for bucket, series_id in _FRED_SERIES.items():
        try:
            res = _fetch_fred_latest(series_id, api_key)
        except Exception:
            continue
        if res is None:
            continue
        d, pct = res
        buckets[bucket] = round(pct * 100.0, 1)  # percent -> bps
        latest = d if latest is None else max(latest, d)

    if not buckets:
        return None
    return {
        "buckets": buckets,
        "asOf": latest.isoformat() if latest else None,
        "source": "live",
    }
