"""Fundamentals adapter using yfinance, which handles Yahoo's crumb/cookie auth
for the otherwise key-less quote-summary data. Normalizes into the fundamentals
schema and maps the company's sector to an internal sector id.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Dict, Optional

import yfinance as yf

from ._resilient import guard as _guard
from .sectors import map_sector

# yfinance does its own HTTP, so it shares no breaker with the chart endpoint; a
# throttle there should not pause the chart sources and vice versa.
_SOURCE = "yfinance"


def _fetch_info(sym: str) -> Dict:
    """Fetch yfinance `.info`, raising a clean ValueError when there's no data.

    Kept separate so the resilient ``guard`` can retry only on throttles while a
    genuine "no data for this symbol" propagates immediately.
    """
    info = yf.Ticker(sym).info or {}
    if not info.get("regularMarketPrice") and not info.get("currentPrice") \
            and not info.get("marketCap"):
        raise ValueError(f"no fundamentals for {sym}")
    return info


def fetch_fundamentals(symbol: str) -> Dict:
    """Return a normalized fundamentals dict for `symbol`. Raises on failure."""
    sym = symbol.upper()
    info = _guard(_SOURCE, _fetch_info, sym)

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
    change_pct = None
    if price is not None and prev:
        change_pct = round((price - prev) / prev * 100, 2)

    net_margin = info.get("profitMargins")
    if net_margin is not None:
        net_margin = round(net_margin * 100, 2)  # fraction -> percent

    rev_growth = info.get("revenueGrowth")
    if rev_growth is not None:
        rev_growth = round(rev_growth * 100, 2)  # fraction -> percent (YoY)

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
        "revenueGrowth": rev_growth,
        "eps": _f(info.get("trailingEps")),
        "dividendYield": _f(info.get("dividendYield")) or 0.0,
        "beta": _f(info.get("beta")),
        "week52High": _f(info.get("fiftyTwoWeekHigh")),
        "week52Low": _f(info.get("fiftyTwoWeekLow")),
        "description": (info.get("longBusinessSummary") or "")[:600] or None,
        "sector": map_sector(info.get("sector"), info.get("industry")),
        "industry": info.get("industry") or None,
        "website": info.get("website") or None,
    }


def fetch_fundamentals_history(symbol: str) -> list:
    """Return as-reported quarterly fundamentals history for `symbol`.

    Reads yfinance's quarterly income statement (free quote-summary data) and
    normalizes each fiscal quarter into a point-in-time row. The income statement
    is indexed by the *period end* (fiscal quarter close); the date a figure
    actually became public (filing/earnings) isn't in this feed, so `reportDate`
    is estimated as period end + a conservative 45-day reporting lag and flagged
    via `reportEstimated=True`. Callers persist these so a backtest can read the
    numbers knowable at a given as-of date instead of today's restated snapshot.

    Returns a list of dicts (may be empty); raises on network/throttle failure so
    the resilient guard can retry.
    """
    sym = symbol.upper()

    def _pull():
        t = yf.Ticker(sym)
        df = getattr(t, "quarterly_income_stmt", None)
        if df is None or getattr(df, "empty", True):
            df = getattr(t, "quarterly_financials", None)
        return df

    df = _guard(_SOURCE, _pull)
    if df is None or getattr(df, "empty", True):
        return []

    def _row(name):
        try:
            return df.loc[name]
        except (KeyError, AttributeError):
            return None

    revenue_row = _row("Total Revenue")
    net_income_row = _row("Net Income")
    eps_row = _row("Diluted EPS")
    if eps_row is None:
        eps_row = _row("Basic EPS")

    out: list = []
    for col in df.columns:
        period_end = _to_iso_date(col)
        if not period_end:
            continue
        revenue = _f(revenue_row[col]) if revenue_row is not None else None
        net_income = _f(net_income_row[col]) if net_income_row is not None else None
        eps = _f(eps_row[col]) if eps_row is not None else None
        net_margin = None
        if revenue and net_income is not None and revenue != 0:
            net_margin = round(net_income / revenue * 100, 2)  # fraction -> percent
        # Estimate the public-report date as period end + 45d (typical filing lag).
        try:
            pe = date.fromisoformat(period_end)
            report_date = (pe + timedelta(days=45)).isoformat()
        except ValueError:
            report_date = period_end
        if revenue is None and net_income is None and eps is None:
            continue
        out.append({
            "symbol": sym,
            "periodEnd": period_end,
            "reportDate": report_date,
            "revenue": revenue,
            "netIncome": net_income,
            "netMargin": net_margin,
            "eps": eps,
            "reportEstimated": True,
            "source": _SOURCE,
        })
    out.sort(key=lambda r: r["periodEnd"])
    return out


def fetch_calendar(symbol: str) -> Dict:
    """Return upcoming earnings/dividend dates for `symbol` from yfinance's
    free calendar feed.

    Keys (any may be None): ``earningsDate``, ``exDividendDate``,
    ``dividendDate`` — each an ISO date string for the soonest upcoming event —
    plus ``earningsEpsEstimate``, the consensus per-share estimate Yahoo carries
    alongside the next earnings date (the calendar's "Earnings Average").
    Falls back to the ``info`` earnings timestamp / forward EPS when the calendar
    lacks them. Raises on network/parse failure so the worker can log and skip
    this symbol.
    """
    sym = symbol.upper()
    ticker = yf.Ticker(sym)
    cal = ticker.calendar or {}
    if not isinstance(cal, dict):  # very old yfinance returned a DataFrame
        cal = {}

    earnings = _soonest_date(cal.get("Earnings Date"))
    ex_div = _soonest_date(cal.get("Ex-Dividend Date"))
    div = _soonest_date(cal.get("Dividend Date"))
    eps_estimate = _f(cal.get("Earnings Average"))

    if earnings is None or eps_estimate is None:
        info = ticker.info or {}
        if earnings is None:
            ts = info.get("earningsTimestampStart") or info.get("earningsTimestamp")
            if ts:
                try:
                    earnings = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
                except (TypeError, ValueError, OSError):
                    earnings = None
        if eps_estimate is None:
            eps_estimate = _f(info.get("epsCurrentYear") or info.get("forwardEps"))

    return {
        "symbol": sym,
        "earningsDate": earnings,
        "exDividendDate": ex_div,
        "dividendDate": div,
        "earningsEpsEstimate": eps_estimate,
    }


def _soonest_date(v) -> Optional[str]:
    """Pick the soonest upcoming date (>= today) from a value that may be a
    single date or a list; fall back to the latest known date if all are past.
    Returns an ISO date string or None."""
    if isinstance(v, (list, tuple)):
        dates = [d for d in (_to_iso_date(x) for x in v) if d]
    else:
        d = _to_iso_date(v)
        dates = [d] if d else []
    if not dates:
        return None
    today = date.today().isoformat()
    upcoming = sorted(d for d in dates if d >= today)
    return upcoming[0] if upcoming else max(dates)


def _to_iso_date(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str):
        return v[:10] or None
    try:  # pandas Timestamp or similar
        return v.date().isoformat()
    except Exception:  # noqa: BLE001
        return None


def fetch_market_cap(symbol: str) -> Optional[float]:
    """Return just the live market cap (USD) for `symbol`, or None if unknown.

    Uses yfinance ``fast_info``, which derives market cap from the last price and
    shares outstanding via the lightweight chart endpoint — far cheaper than the
    full ``.info`` quote-summary. Intended for a slow breadth refresh that touches
    only this single field, so it must NOT be treated as a full live snapshot.

    Raises on network/auth failure so the caller can log and skip the symbol.
    """
    sym = symbol.upper()
    fast = yf.Ticker(sym).fast_info
    try:
        mcap = fast["market_cap"]
    except (KeyError, AttributeError, TypeError):
        mcap = getattr(fast, "market_cap", None)
    val = _f(mcap)
    return val if val and val > 0 else None


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
