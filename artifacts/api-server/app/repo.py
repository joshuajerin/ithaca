"""DB-backed data-access layer for the panel skills.

Mirrors the public surface of `data.py` (the Phase 1 curated mock dataset) but
reads from Postgres. Every accessor falls back to the deterministic mock data
when the database is unavailable or has no rows for a symbol/scope, preserving
the "no empty panels" guarantee. Freshness is surfaced via `_asOf`/`_source`
keys on company records and an `as_of` helper for panels.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from . import data, db, returns

log = logging.getLogger("terminal.repo")

# Numeric company fields panels format directly (must be real numbers).
_NUMERIC = (
    "price", "changePct", "marketCap", "volume", "netMargin", "eps",
    "dividendYield", "beta", "week52High", "week52Low",
)


def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return str(dt)


def _iso_date(d) -> Optional[str]:
    """Normalize a DB date (date/datetime/str) to a plain ISO ``YYYY-MM-DD``."""
    if d is None:
        return None
    if isinstance(d, str):
        return d[:10] or None
    if hasattr(d, "isoformat"):
        try:
            return d.isoformat()[:10]
        except Exception:  # noqa: BLE001
            return str(d)[:10]
    return str(d)[:10]


# ----------------------------- companies -----------------------------
def get_company(symbol: str) -> Optional[dict]:
    sym = (symbol or "").upper()
    if not sym:
        return None
    if db.db_available():
        try:
            row = db.query_one(
                """
                SELECT f.symbol, f.name, u.sector AS sector,
                       u.country AS country, u.exchange AS exchange,
                       u.industry AS industry, u.website AS website,
                       f.price, f.change_pct, f.market_cap, f.pe_ratio, f.volume,
                       f.revenue, f.net_margin, f.revenue_growth, f.eps,
                       f.dividend_yield, f.beta,
                       f.week52_high, f.week52_low, f.description, f.is_live,
                       f.earnings_date, f.ex_dividend_date, f.dividend_date,
                       f.earnings_eps_estimate,
                       f.updated_at
                FROM fundamentals f
                LEFT JOIN universe u ON u.symbol = f.symbol
                WHERE f.symbol = %s
                """,
                (sym,),
            )
            if row and row.get("price") is not None:
                return _company_from_row(row)
        except Exception as exc:  # noqa: BLE001
            log.warning("get_company DB error for %s: %s", sym, exc)
    # Fallback to curated mock; enqueue for proactive ingestion either way.
    note_symbol(sym)
    company = data.get_company(sym)
    if company:
        c = dict(company)
        c["_asOf"] = None
        c["_source"] = "mock"
        return c
    return None


def _company_from_row(row: dict) -> dict:
    sid = row.get("sector") or "ai_tech"
    mock = data.COMPANIES.get(row["symbol"])
    # Prefer a real (live) logo from the fetched website, then the curated
    # fallback; sub-industry prefers Yahoo's finer industry, then curated, then
    # the broad sector group so the label is always human-readable.
    logo = data.logo_url(row.get("website")) or (mock.get("logoUrl") if mock else None)
    sub = (row.get("industry") or (mock.get("subIndustry") if mock else None)
           or data.sub_industry_name(sid))
    c = {
        "symbol": row["symbol"],
        "name": row.get("name") or row["symbol"],
        "sector": sid,
        "subIndustry": sub,
        "logoUrl": logo,
        "price": _num(row.get("price")),
        "changePct": _num(row.get("change_pct")),
        "marketCap": _num(row.get("market_cap")),
        "peRatio": row.get("pe_ratio"),
        "volume": _num(row.get("volume")),
        "revenue": row.get("revenue"),
        "netMargin": _num(row.get("net_margin")),
        "revenueGrowth": _num(row.get("revenue_growth")) if row.get("revenue_growth") is not None else None,
        "eps": _num(row.get("eps")),
        "dividendYield": _num(row.get("dividend_yield")),
        "beta": _num(row.get("beta")),
        "week52High": _num(row.get("week52_high")),
        "week52Low": _num(row.get("week52_low")),
        "description": row.get("description") or "",
        "country": row.get("country"),
        "exchange": row.get("exchange"),
        "earningsDate": _iso(row.get("earnings_date")),
        "exDividendDate": _iso(row.get("ex_dividend_date")),
        "dividendDate": _iso(row.get("dividend_date")),
        "earningsEpsEstimate": _num(row.get("earnings_eps_estimate")) if row.get("earnings_eps_estimate") is not None else None,
        "_asOf": _iso(row.get("updated_at")),
        "_source": "live" if row.get("is_live") else "mock",
    }
    return c


def _num(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def companies_bulk(symbols: List[str]) -> Dict[str, dict]:
    """Fetch many companies in one query (for screeners/heatmaps).

    Avoids N per-symbol round-trips. Missing symbols fall back to the curated
    mock so breadth panels never show holes."""
    want = [(s or "").upper() for s in symbols if s]
    out: Dict[str, dict] = {}
    if want and db.db_available():
        try:
            rows = db.query(
                """
                SELECT f.symbol, f.name, u.sector AS sector,
                       u.country AS country, u.exchange AS exchange,
                       u.industry AS industry, u.website AS website,
                       f.price, f.change_pct, f.market_cap, f.pe_ratio, f.volume,
                       f.revenue, f.net_margin, f.revenue_growth, f.eps,
                       f.dividend_yield, f.beta,
                       f.week52_high, f.week52_low, f.description, f.is_live,
                       f.earnings_date, f.ex_dividend_date, f.dividend_date,
                       f.earnings_eps_estimate,
                       f.updated_at
                FROM fundamentals f
                LEFT JOIN universe u ON u.symbol = f.symbol
                WHERE f.symbol = ANY(%s) AND f.price IS NOT NULL
                """,
                (want,),
            )
            for r in rows:
                out[r["symbol"]] = _company_from_row(r)
        except Exception as exc:  # noqa: BLE001
            log.warning("companies_bulk DB error: %s", exc)
    for s in want:
        if s not in out:
            company = data.get_company(s)
            if company:
                c = dict(company)
                c["_asOf"] = None
                c["_source"] = "mock"
                out[s] = c
    return out


def get_analyst_ratings(symbol: str) -> Optional[dict]:
    """Last persisted real analyst ratings/price-target snapshot for `symbol`.

    Returns a camelCase dict with ``_asOf``/``_source`` provenance, or None when
    the DB is unavailable, the table is unseeded, or the name has no snapshot.
    Used as the persisted fallback when a live consensus fetch is throttled, and
    as no-network grounding for the qualitative analyst-report/compare builders.
    """
    sym = (symbol or "").upper()
    if not sym or not db.db_available():
        return None
    try:
        row = db.query_one(
            "SELECT * FROM analyst_ratings WHERE symbol = %s", (sym,)
        )
    except Exception as exc:  # noqa: BLE001 — table may be unseeded
        log.warning("get_analyst_ratings DB error for %s: %s", sym, exc)
        return None
    if not row:
        return None
    return _analyst_ratings_from_row(row)


def _analyst_ratings_from_row(row: dict) -> dict:
    changes = row.get("changes")
    if isinstance(changes, str):
        try:
            changes = json.loads(changes)
        except (ValueError, TypeError):
            changes = []
    dist = {
        "strongBuy": row.get("strong_buy") or 0,
        "buy": row.get("buy") or 0,
        "hold": row.get("hold") or 0,
        "sell": row.get("sell") or 0,
        "strongSell": row.get("strong_sell") or 0,
    }
    has_dist = sum(dist.values()) > 0

    def _opt(v) -> Optional[float]:
        return float(v) if v is not None else None

    return {
        "symbol": row["symbol"],
        "name": row.get("name") or row["symbol"],
        "covered": bool(row.get("covered")),
        "consensusKey": row.get("consensus_key"),
        "recommendationMean": _opt(row.get("recommendation_mean")),
        "numAnalysts": row.get("num_analysts"),
        "distribution": dist if has_dist else None,
        "targetMean": _opt(row.get("target_mean")),
        "targetHigh": _opt(row.get("target_high")),
        "targetLow": _opt(row.get("target_low")),
        "targetMedian": _opt(row.get("target_median")),
        "currentPrice": _opt(row.get("current_price")),
        "changes": changes or [],
        "_asOf": _iso(row.get("updated_at")),
        "_source": "live",
    }


def get_all_companies() -> Dict[str, dict]:
    if db.db_available():
        try:
            rows = db.query(
                """
                SELECT f.symbol, f.name, u.sector AS sector
                FROM fundamentals f
                LEFT JOIN universe u ON u.symbol = f.symbol
                WHERE f.price IS NOT NULL
                """
            )
            if rows:
                return {
                    r["symbol"]: {"name": r.get("name") or r["symbol"],
                                  "sector": r.get("sector") or "ai_tech"}
                    for r in rows
                }
        except Exception as exc:  # noqa: BLE001
            log.warning("get_all_companies DB error: %s", exc)
    return {s: {"name": c["name"], "sector": c["sector"]} for s, c in data.COMPANIES.items()}


# ----------------------------- sectors / universe -----------------------------
def resolve_sector(text: str) -> Optional[str]:
    return data.resolve_sector(text)


def sector_name(sid: str) -> str:
    return data.sector_name(sid)


def all_symbols() -> List[str]:
    if db.db_available():
        try:
            rows = db.query(
                "SELECT symbol FROM fundamentals WHERE price IS NOT NULL ORDER BY market_cap DESC NULLS LAST"
            )
            syms = [r["symbol"] for r in rows]
            if syms:
                return syms
        except Exception as exc:  # noqa: BLE001
            log.warning("all_symbols DB error: %s", exc)
    return data.all_symbols()


def symbols_in_sector(sid: str) -> List[str]:
    if db.db_available():
        try:
            rows = db.query(
                """
                SELECT f.symbol FROM fundamentals f
                LEFT JOIN universe u ON u.symbol = f.symbol
                WHERE u.sector = %s AND f.price IS NOT NULL
                ORDER BY f.market_cap DESC NULLS LAST
                """,
                (sid,),
            )
            syms = [r["symbol"] for r in rows]
            if syms:
                return syms
        except Exception as exc:  # noqa: BLE001
            log.warning("symbols_in_sector DB error for %s: %s", sid, exc)
    return data.symbols_in_sector(sid)


# ----------------------------- country / exchange -----------------------------
# Free-text aliases -> canonical values stored on `universe.country` /
# `universe.exchange`. Used to turn requests like "SGX stocks" or "Singapore
# market heatmap" into a concrete country/exchange filter.
_EXCHANGE_ALIASES = {
    "sgx": "SGX",
    "nasdaq": "NASDAQ",
    "nyse": "NYSE",
}

_COUNTRY_ALIASES = {
    "united states": "United States",
    "us": "United States",
    "u.s.": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "america": "United States",
    "american": "United States",
    "singapore": "Singapore",
    "singaporean": "Singapore",
    "sg": "Singapore",
}


def resolve_exchange(text: Optional[str]) -> Optional[str]:
    """Best-effort free-text -> canonical exchange code (e.g. 'SGX')."""
    if not text:
        return None
    up = text.strip().upper()
    if up in ("SGX", "NASDAQ", "NYSE"):
        return up
    t = text.strip().lower()
    if t in _EXCHANGE_ALIASES:
        return _EXCHANGE_ALIASES[t]
    for alias, ex in _EXCHANGE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", t):
            return ex
    return None


def resolve_country(text: Optional[str]) -> Optional[str]:
    """Best-effort free-text -> canonical country (e.g. 'Singapore')."""
    if not text:
        return None
    t = text.strip().lower()
    if t in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[t]
    for alias, co in _COUNTRY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", t):
            return co
    return None


def resolve_market(text: Optional[str]) -> Optional[dict]:
    """Resolve free text to a ``{'country', 'exchange'}`` filter, or None.

    Exchange aliases win when both could match (e.g. "SGX" implies Singapore but
    we keep it as an exchange filter, which is the more specific request).
    """
    ex = resolve_exchange(text)
    co = resolve_country(text)
    if not ex and not co:
        return None
    return {"country": co, "exchange": ex}


def market_label(country: Optional[str], exchange: Optional[str]) -> Optional[str]:
    """Short human label for a country/exchange filter (exchange wins)."""
    if exchange:
        return exchange
    if country:
        return country
    return None


def symbols_by_market(
    sid: Optional[str] = None,
    country: Optional[str] = None,
    exchange: Optional[str] = None,
) -> List[str]:
    """Symbols filtered by optional sector + country + exchange, most-valuable first.

    DB-backed against the universe table; falls back to the curated mock catalog
    when the DB is unavailable so breadth panels never go empty. With no filters
    this is just `all_symbols()`; with only a sector it matches `symbols_in_sector`.
    """
    if not sid and not country and not exchange:
        return all_symbols()
    if not country and not exchange:
        return symbols_in_sector(sid)
    if db.db_available():
        try:
            where = ["f.price IS NOT NULL"]
            params: list = []
            if sid:
                where.append("u.sector = %s")
                params.append(sid)
            if country:
                where.append("u.country = %s")
                params.append(country)
            if exchange:
                where.append("u.exchange = %s")
                params.append(exchange)
            rows = db.query(
                f"""
                SELECT f.symbol FROM fundamentals f
                LEFT JOIN universe u ON u.symbol = f.symbol
                WHERE {' AND '.join(where)}
                ORDER BY f.market_cap DESC NULLS LAST
                """,
                tuple(params),
            )
            syms = [r["symbol"] for r in rows]
            if syms:
                return syms
        except Exception as exc:  # noqa: BLE001
            log.warning("symbols_by_market DB error: %s", exc)
    items = []
    for sym, c in data.COMPANIES.items():
        if sid and c.get("sector") != sid:
            continue
        if country and c.get("country") != country:
            continue
        if exchange and c.get("exchange") != exchange:
            continue
        items.append((sym, c))
    items.sort(key=lambda kv: kv[1].get("marketCap", 0), reverse=True)
    return [s for s, _ in items]


def list_sectors() -> List[dict]:
    counts: Dict[str, int] = {}
    if db.db_available():
        try:
            rows = db.query(
                """
                SELECT u.sector AS sector, COUNT(*) AS n
                FROM fundamentals f
                LEFT JOIN universe u ON u.symbol = f.symbol
                WHERE f.price IS NOT NULL
                GROUP BY 1
                """
            )
            counts = {r["sector"]: int(r["n"]) for r in rows if r.get("sector")}
        except Exception as exc:  # noqa: BLE001
            log.warning("list_sectors DB error: %s", exc)
    out = []
    for sid, name in data.SECTORS.items():
        n = counts.get(sid)
        if not n:
            n = sum(1 for c in data.COMPANIES.values() if c["sector"] == sid)
        out.append({"id": sid, "name": name, "tickerCount": n})
    return out


# ----------------------------- prices -----------------------------
# Canonical chart-window → trading-days mapping. Kept here (not imported from
# skills) so the data layer owns range resolution and skills/agent can round-trip
# a user-selected window straight through to the stored OHLCV query.
RANGE_DAYS = {"1M": 30, "3M": 90, "6M": 180, "1Y": 250, "YTD": 120}


def resolve_range_days(rng: Optional[str], days: int = 90) -> int:
    """Resolve a chart range label (e.g. "1M"/"6M"/"1Y") to a day count.

    Falls back to ``days`` when no/unknown range is given so existing callers
    that pass ``days`` directly keep working unchanged.
    """
    if rng:
        return RANGE_DAYS.get(rng.upper(), days)
    return days


def price_series(symbol: str, days: int = 90, rng: Optional[str] = None) -> List[dict]:
    days = resolve_range_days(rng, days)
    sym = (symbol or "").upper()
    if db.db_available():
        try:
            rows = db.query(
                """
                SELECT d, o, h, l, c, v FROM (
                    SELECT d, o, h, l, c, v FROM ohlcv
                    WHERE symbol = %s ORDER BY d DESC LIMIT %s
                ) sub ORDER BY d ASC
                """,
                (sym, days),
            )
            if len(rows) >= 2:
                return [
                    {
                        "t": r["d"].isoformat() if hasattr(r["d"], "isoformat") else str(r["d"]),
                        "o": _num(r.get("o")),
                        "h": _num(r.get("h")),
                        "l": _num(r.get("l")),
                        "c": _num(r.get("c")),
                        "v": _num(r.get("v")),
                    }
                    for r in rows
                ]
        except Exception as exc:  # noqa: BLE001
            log.warning("price_series DB error for %s: %s", sym, exc)
    return data.price_series(sym, days=days)


def price_series_meta(symbol: str, days: int = 90, rng: Optional[str] = None) -> dict:
    """Like `price_series` but reports provenance for freshness metadata.

    Returns {"points": [...], "source": "live"|"mock", "asOf": iso|None}. The
    series is "live" only when it came from real OHLCV rows in the DB; otherwise
    it falls back to the deterministic curated mock series.
    """
    days = resolve_range_days(rng, days)
    sym = (symbol or "").upper()
    if db.db_available():
        try:
            rows = db.query(
                """
                SELECT d, o, h, l, c, v, updated_at FROM (
                    SELECT d, o, h, l, c, v, updated_at FROM ohlcv
                    WHERE symbol = %s ORDER BY d DESC LIMIT %s
                ) sub ORDER BY d ASC
                """,
                (sym, days),
            )
            if len(rows) >= 2:
                points = [
                    {
                        "t": r["d"].isoformat() if hasattr(r["d"], "isoformat") else str(r["d"]),
                        "o": _num(r.get("o")),
                        "h": _num(r.get("h")),
                        "l": _num(r.get("l")),
                        "c": _num(r.get("c")),
                        "v": _num(r.get("v")),
                    }
                    for r in rows
                ]
                as_of = max((_iso(r.get("updated_at")) for r in rows if r.get("updated_at")), default=None)
                return {"points": points, "source": "live", "asOf": as_of}
        except Exception as exc:  # noqa: BLE001
            log.warning("price_series_meta DB error for %s: %s", sym, exc)
    note_symbol(sym)
    return {"points": data.price_series(sym, days=days), "source": "mock", "asOf": None}


# Yahoo range tokens we step through when we need history deeper than the DB holds
# (the ingest worker only stores ~6mo of daily OHLCV). Ordered shortest->longest so
# we can pick the smallest token that spans the requested start date.
_DEEP_RANGE_TOKENS = ["1y", "2y", "5y", "10y", "max"]


def _deep_range_token(start: Optional[str]) -> str:
    """Pick a Yahoo range token covering `start` (ISO) back from today.

    With no start (e.g. an all-time-peak entry) we fetch the maximum available
    history so the peak search isn't truncated by a short window.
    """
    if not start:
        return "max"
    try:
        d0 = date.fromisoformat(start)
    except (TypeError, ValueError):
        return "max"
    years = (date.today() - d0).days / 365.25
    if years <= 1:
        return "1y"
    if years <= 2:
        return "2y"
    if years <= 5:
        return "5y"
    if years <= 10:
        return "10y"
    return "max"


def deep_price_series(symbol: str, start: Optional[str] = None) -> dict:
    """Real daily closes reaching deeper than the cached ~6mo DB window.

    Used by the backtest's peak / old-date / custom-range entries, where the
    user wants to "invest at the all-time peak" or on a date years back that the
    ingest worker never stored. Fetches genuine daily bars from the live price
    source (routed through the resilient client + circuit breaker); on any
    failure falls back to the deepest series the DB/mock can provide so the panel
    still renders. Returns ``{"points": [...], "source": "live"|"mock", "asOf"}``
    with engine-shaped points (``t``/``o``/``h``/``l``/``c``/``v``).
    """
    sym = (symbol or "").upper()
    try:
        from .sources import prices

        token = _deep_range_token(start)
        res = prices.fetch_price_history(sym, range_=token, interval="1d")
        raw = res.get("points") or []
        points = [
            {
                "t": p["d"],
                "o": _num(p.get("o")),
                "h": _num(p.get("h")),
                "l": _num(p.get("l")),
                "c": _num(p.get("c")),
                "v": _num(p.get("v")),
            }
            for p in raw
            if p.get("d") and p.get("c") is not None
        ]
        if len(points) >= 2:
            as_of = (res.get("quote") or {}).get("asOf")
            return {"points": points, "source": "live", "asOf": as_of}
    except Exception as exc:  # noqa: BLE001 — fall back to cached/mock history
        log.warning("deep_price_series fetch error for %s: %s", sym, exc)

    # Fallback: deepest the DB/mock can give us. ~2600 trading days ≈ 10y so the
    # peak/date search isn't artificially clipped.
    return price_series_meta(sym, days=2600)


# ----------------------------- period returns -----------------------------
# We fetch enough calendar history to anchor a 1Y / YTD window. Live series are
# trading days (this many rows comfortably spans a year); mock series are
# calendar days, so ~400 days guarantees full 1Y coverage.
_RETURN_DAYS = 400


def period_returns(
    symbol: str,
    windows=returns.DEFAULT_WINDOWS,
    days: int = _RETURN_DAYS,
) -> dict:
    """Real period returns (e.g. 1M / YTD / 1Y) for one symbol.

    Computed from the price series so live names reflect genuine history and
    breadth (mock) names use the deterministic series. Returns
    ``{"returns": {window: pct|None}, "source": "live"|"mock", "asOf": iso|None}``.
    """
    meta = price_series_meta(symbol, days=days)
    rets = returns.compute_period_returns(meta["points"], windows=windows)
    return {"returns": rets, "source": meta["source"], "asOf": meta["asOf"]}


def period_returns_bulk(
    symbols: List[str],
    windows=("1Y",),
    days: int = _RETURN_DAYS,
) -> Dict[str, Dict[str, Optional[float]]]:
    """Period returns for many symbols with a single OHLCV round-trip.

    Live names with real OHLCV history are computed from one bulk DB query;
    every remaining symbol falls back to its deterministic mock series. Keeps
    breadth panels (screener/heatmap) cheap even across hundreds of rows.
    """
    want = [(s or "").upper() for s in symbols if s]
    out: Dict[str, Dict[str, Optional[float]]] = {}
    remaining = set(want)

    if want and db.db_available():
        try:
            cutoff = (date.today() - timedelta(days=days + 10)).isoformat()
            rows = db.query(
                """
                SELECT symbol, d, c FROM ohlcv
                WHERE symbol = ANY(%s) AND c IS NOT NULL AND d >= %s
                ORDER BY symbol ASC, d ASC
                """,
                (want, cutoff),
            )
            by_sym: Dict[str, List[dict]] = {}
            for r in rows:
                d = r["d"]
                by_sym.setdefault(r["symbol"], []).append({
                    "t": d.isoformat() if hasattr(d, "isoformat") else str(d),
                    "c": _num(r.get("c")),
                })
            for sym, pts in by_sym.items():
                if len(pts) >= 2:
                    out[sym] = returns.compute_period_returns(pts, windows=windows)
                    remaining.discard(sym)
        except Exception as exc:  # noqa: BLE001
            log.warning("period_returns_bulk DB error: %s", exc)

    for sym in remaining:
        pts = data.price_series(sym, days=days)
        out[sym] = (
            returns.compute_period_returns(pts, windows=windows)
            if pts else {w: None for w in windows}
        )
    return out


def closes_bulk(symbols: List[str], days: int = 180) -> dict:
    """Per-symbol close series for many names with a single OHLCV round-trip.

    Returns ``{"series": {sym: [{"t","c"}, ...]}, "sources": {sym:
    "live"|"mock"}, "asOf": iso|None}``. Live names come from one bulk DB query;
    every remaining symbol falls back to its deterministic curated series. Used
    by the factor risk model to build an aligned cross-sectional return panel.
    """
    want = [(s or "").upper() for s in symbols if s]
    series: Dict[str, List[dict]] = {}
    sources: Dict[str, str] = {}
    as_ofs: List[str] = []
    remaining = set(want)

    if want and db.db_available():
        try:
            cutoff = (date.today() - timedelta(days=days + 10)).isoformat()
            rows = db.query(
                """
                SELECT symbol, d, c, updated_at FROM ohlcv
                WHERE symbol = ANY(%s) AND c IS NOT NULL AND d >= %s
                ORDER BY symbol ASC, d ASC
                """,
                (want, cutoff),
            )
            by_sym: Dict[str, List[dict]] = {}
            upd: Dict[str, List[str]] = {}
            for r in rows:
                d = r["d"]
                by_sym.setdefault(r["symbol"], []).append({
                    "t": d.isoformat() if hasattr(d, "isoformat") else str(d),
                    "c": _num(r.get("c")),
                })
                iso = _iso(r.get("updated_at"))
                if iso:
                    upd.setdefault(r["symbol"], []).append(iso)
            for sym, pts in by_sym.items():
                if len(pts) >= 2:
                    series[sym] = pts
                    sources[sym] = "live"
                    remaining.discard(sym)
                    if upd.get(sym):
                        as_ofs.append(max(upd[sym]))
        except Exception as exc:  # noqa: BLE001
            log.warning("closes_bulk DB error: %s", exc)

    for sym in remaining:
        pts = data.price_series(sym, days=days)
        series[sym] = [{"t": p["t"], "c": p["c"]} for p in pts] if pts else []
        sources[sym] = "mock"
        note_symbol(sym)

    return {"series": series, "sources": sources, "asOf": (max(as_ofs) if as_ofs else None)}


def price_closes_bulk(symbols: List[str], days: int = _RETURN_DAYS) -> dict:
    """Date/close series for many symbols with a single OHLCV round-trip.

    Live names with real OHLCV history come from one bulk DB query; every
    remaining symbol falls back to its deterministic mock series. Used by the
    cross-sectional signal research desk, which needs each name's close series.

    Returns ``{"series": {sym: [{"t", "c"}, ...]}, "live": {sym: bool},
    "source": "live"|"mock", "asOf": iso|None}``. ``source`` is "live" when ANY
    name resolved to real DB history; ``live`` reports provenance per symbol.
    """
    want = [(s or "").upper() for s in symbols if s]
    series: Dict[str, List[dict]] = {}
    live: Dict[str, bool] = {}
    as_of_stamps: List[str] = []
    remaining = set(want)

    if want and db.db_available():
        try:
            cutoff = (date.today() - timedelta(days=days + 10)).isoformat()
            rows = db.query(
                """
                SELECT symbol, d, c, updated_at FROM ohlcv
                WHERE symbol = ANY(%s) AND c IS NOT NULL AND d >= %s
                ORDER BY symbol ASC, d ASC
                """,
                (want, cutoff),
            )
            by_sym: Dict[str, List[dict]] = {}
            for r in rows:
                d = r["d"]
                by_sym.setdefault(r["symbol"], []).append({
                    "t": d.isoformat() if hasattr(d, "isoformat") else str(d),
                    "c": _num(r.get("c")),
                })
                stamp = _iso(r.get("updated_at"))
                if stamp:
                    as_of_stamps.append(stamp)
            for sym, pts in by_sym.items():
                if len(pts) >= 2:
                    series[sym] = pts
                    live[sym] = True
                    remaining.discard(sym)
        except Exception as exc:  # noqa: BLE001
            log.warning("price_closes_bulk DB error: %s", exc)

    for sym in remaining:
        note_symbol(sym)
        pts = data.price_series(sym, days=days)
        series[sym] = [{"t": p["t"], "c": p["c"]} for p in pts] if pts else []
        live[sym] = False

    return {
        "series": series,
        "live": live,
        "source": "live" if any(live.values()) else "mock",
        "asOf": max(as_of_stamps) if as_of_stamps else None,
    }


# ----------------------------- point-in-time / survivorship -----------------------------
def listing_info(symbol: str) -> dict:
    """Listing lifecycle for one symbol: status + listing/delisting dates.

    Reads the `universe` registry (DB) and falls back to the curated catalog so
    callers always get an honest status even before any live ingest. Returns
    ``{symbol, name, sector, status, listedAt, delistedAt, source}`` where
    ``status`` is ``active``/``delisted``/``unknown`` and dates may be null when
    not yet known (best-effort from the free chart's first-trade date)."""
    sym = (symbol or "").upper()
    if sym and db.db_available():
        try:
            r = db.query_one(
                "SELECT symbol, name, sector, status, listed_at, delisted_at "
                "FROM universe WHERE symbol = %s",
                (sym,),
            )
            if r:
                return {
                    "symbol": sym,
                    "name": r.get("name"),
                    "sector": r.get("sector"),
                    "status": r.get("status") or "active",
                    "listedAt": _iso_date(r.get("listed_at")),
                    "delistedAt": _iso_date(r.get("delisted_at")),
                    "source": "db",
                }
        except Exception as exc:  # noqa: BLE001
            log.warning("listing_info DB error: %s", exc)
    dl = data.get_delisted(sym)
    if dl:
        return {
            "symbol": sym, "name": dl.get("name"), "sector": dl.get("sector"),
            "status": "delisted", "listedAt": dl.get("listed"),
            "delistedAt": dl.get("delisted"), "source": "curated",
        }
    company = data.get_company(sym)
    if company:
        return {
            "symbol": sym, "name": company.get("name"),
            "sector": company.get("sector"), "status": "active",
            "listedAt": None, "delistedAt": None, "source": "curated",
        }
    return {
        "symbol": sym, "name": None, "sector": None, "status": "unknown",
        "listedAt": None, "delistedAt": None, "source": "unknown",
    }


def historical_universe(
    start: str,
    end: str,
    sector: Optional[str] = None,
    symbols: Optional[List[str]] = None,
) -> dict:
    """Resolve the universe that was *active during* the [start, end] window.

    Survivorship-bias-free: includes names that were trading in the window but
    have since been delisted (failed/acquired/taken-private), not just today's
    survivors. A name belongs to the window when it was already listed by `end`
    and had not yet delisted before `start`:
        (listed_at IS NULL OR listed_at <= end) AND
        (delisted_at IS NULL OR delisted_at >= start)

    `symbols` (when given) constrains the *active* candidate set (e.g. a signal
    desk's resolved survivors); delisted names in the window are always merged in
    on top, optionally filtered by `sector`. Returns active/delisted breakdown,
    a `survivorshipSafe` flag (true only when we actually carry names that left
    the market in this window), how much of the universe has real listing dates,
    and honest notes about the gaps. Never invents membership.
    """
    sid = resolve_sector(sector) if sector else None
    active = [s.upper() for s in (symbols or []) if s]
    delisted: List[dict] = []
    with_dates = 0
    total_considered = 0
    notes: List[str] = []
    source = "mock"

    def _row_in_window(listed, delisted_d) -> bool:
        if listed and listed > end:
            return False
        if delisted_d and delisted_d < start:
            return False
        return True

    if db.db_available():
        try:
            # Active candidates from the registry when the caller didn't supply a set.
            if not active:
                where = "WHERE COALESCE(u.status, 'active') = 'active' AND f.price IS NOT NULL"
                params: list = []
                if sid:
                    where += " AND u.sector = %s"
                    params.append(sid)
                arows = db.query(
                    f"""
                    SELECT f.symbol FROM fundamentals f
                    LEFT JOIN universe u ON u.symbol = f.symbol
                    {where}
                    ORDER BY f.market_cap DESC NULLS LAST
                    """,
                    tuple(params),
                )
                active = [r["symbol"] for r in arows]
            # Delisted names that were trading in the window.
            dwhere = "WHERE COALESCE(status, 'active') = 'delisted'"
            dparams: list = []
            if sid:
                dwhere += " AND sector = %s"
                dparams.append(sid)
            drows = db.query(
                f"SELECT symbol, name, sector, listed_at, delisted_at FROM universe {dwhere}",
                tuple(dparams),
            )
            for r in drows:
                listed = _iso_date(r.get("listed_at"))
                deld = _iso_date(r.get("delisted_at"))
                if _row_in_window(listed, deld):
                    delisted.append({
                        "symbol": r["symbol"], "name": r.get("name"),
                        "sector": r.get("sector"), "listedAt": listed,
                        "delistedAt": deld,
                    })
            # How many universe rows carry a real listing date (PIT-awareness).
            cov = db.query_one(
                "SELECT COUNT(*) AS total, "
                "COUNT(*) FILTER (WHERE listed_at IS NOT NULL) AS dated FROM universe"
            )
            if cov:
                total_considered = int(cov.get("total") or 0)
                with_dates = int(cov.get("dated") or 0)
            source = "live"
        except Exception as exc:  # noqa: BLE001
            log.warning("historical_universe DB error: %s", exc)

    # Fallback / merge: curated delisted set when DB is empty or sparse.
    if not delisted:
        for sym, meta in data.DELISTED.items():
            if sid and meta.get("sector") != sid:
                continue
            if _row_in_window(meta.get("listed"), meta.get("delisted")):
                delisted.append({
                    "symbol": sym, "name": meta.get("name"),
                    "sector": meta.get("sector"), "listedAt": meta.get("listed"),
                    "delistedAt": meta.get("delisted"),
                })
    if not active:
        cands = data.all_symbols()
        active = [s for s in cands]

    delisted_syms = [d["symbol"] for d in delisted]
    survivorship_safe = len(delisted) > 0
    if not survivorship_safe:
        notes.append(
            "No delisted names resolved for this window — results reflect "
            "today's survivors only (survivorship bias not corrected)."
        )
    else:
        notes.append(
            f"{len(delisted)} delisted name(s) trading in this window are included "
            "to reduce survivorship bias; names lacking free historical coverage "
            "are reported, never imputed."
        )
    if total_considered and with_dates < total_considered:
        notes.append(
            f"Real listing dates known for {with_dates}/{total_considered} names; "
            "the rest are treated as listed for the whole window (best-effort)."
        )

    return {
        "windowStart": start,
        "windowEnd": end,
        "symbols": active + delisted_syms,
        "active": active,
        "delisted": delisted,
        "activeCount": len(active),
        "delistedCount": len(delisted),
        "withListingDates": with_dates,
        "totalConsidered": total_considered,
        "survivorshipSafe": survivorship_safe,
        "source": source,
        "asOf": date.today().isoformat(),
        "notes": notes,
    }


def historical_closes(symbols: List[str], start: str, end: str) -> dict:
    """Real, date-bounded daily closes for many symbols — NO mock fill.

    Unlike `price_closes_bulk`, names without genuine OHLCV in the window are
    omitted and reported under `missing` rather than imputed with a deterministic
    mock series. This is what makes survivorship handling honest: a delisted name
    is only included when we actually have its real history. Returns
    ``{series, covered, missing, asOf, source}``.
    """
    want = [(s or "").upper() for s in symbols if s]
    series: Dict[str, List[dict]] = {}
    as_of_stamps: List[str] = []
    if want and db.db_available():
        try:
            rows = db.query(
                """
                SELECT symbol, d, c, updated_at FROM ohlcv
                WHERE symbol = ANY(%s) AND c IS NOT NULL AND d >= %s AND d <= %s
                ORDER BY symbol ASC, d ASC
                """,
                (want, start, end),
            )
            by_sym: Dict[str, List[dict]] = {}
            for r in rows:
                d = r["d"]
                by_sym.setdefault(r["symbol"], []).append({
                    "t": d.isoformat() if hasattr(d, "isoformat") else str(d),
                    "c": _num(r.get("c")),
                })
                stamp = _iso(r.get("updated_at"))
                if stamp:
                    as_of_stamps.append(stamp)
            for sym, pts in by_sym.items():
                if len(pts) >= 2:
                    series[sym] = pts
        except Exception as exc:  # noqa: BLE001
            log.warning("historical_closes DB error: %s", exc)
    covered = sorted(series.keys())
    missing = [s for s in want if s not in series]
    return {
        "series": series,
        "covered": covered,
        "missing": missing,
        "asOf": max(as_of_stamps) if as_of_stamps else None,
        "source": "live" if covered else "none",
    }


def fundamentals_as_of(symbol: str, as_of: str) -> Optional[dict]:
    """As-reported fundamentals knowable at `as_of` (look-ahead-bias free).

    Reads `fundamentals_pit` for the latest fiscal period whose public report
    date is on/before `as_of`, plus the trailing four quarters for TTM EPS and
    revenue. Returns ``{symbol, periodEnd, reportDate, netMargin, epsTtm,
    revenueTtm, reportEstimated, quartersUsed, source}`` or ``None`` when no
    point-in-time history is available (the caller must then flag the fallback,
    not silently use today's restated snapshot)."""
    sym = (symbol or "").upper()
    if not sym or not as_of or not db.db_available():
        return None
    try:
        rows = db.query(
            """
            SELECT period_end, report_date, revenue, net_income, net_margin,
                   eps, report_estimated, source
            FROM fundamentals_pit
            WHERE symbol = %s AND report_date <= %s
            ORDER BY period_end DESC
            LIMIT 4
            """,
            (sym, as_of),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("fundamentals_as_of DB error: %s", exc)
        return None
    if not rows:
        return None
    latest = rows[0]
    eps_vals = [_num(r.get("eps")) for r in rows if _num(r.get("eps")) is not None]
    rev_vals = [_num(r.get("revenue")) for r in rows if _num(r.get("revenue")) is not None]
    eps_ttm = round(sum(eps_vals), 4) if eps_vals else None
    rev_ttm = round(sum(rev_vals), 2) if rev_vals else None
    return {
        "symbol": sym,
        "periodEnd": _iso_date(latest.get("period_end")),
        "reportDate": _iso_date(latest.get("report_date")),
        "netMargin": _num(latest.get("net_margin")),
        "epsTtm": eps_ttm,
        "revenueTtm": rev_ttm,
        "reportEstimated": bool(latest.get("report_estimated")),
        "quartersUsed": len(rows),
        "source": latest.get("source") or "pit",
    }


def pit_coverage(symbols: List[str]) -> dict:
    """How much point-in-time fundamentals history we hold for `symbols`.

    Returns ``{total, covered, perSymbol, periodRange, asOf}`` so the data-quality
    view can show PIT-safe vs best-effort-current coverage honestly."""
    want = [(s or "").upper() for s in symbols if s]
    per: Dict[str, bool] = {s: False for s in want}
    period_min: Optional[str] = None
    period_max: Optional[str] = None
    as_of: Optional[str] = None
    if want and db.db_available():
        try:
            rows = db.query(
                """
                SELECT symbol, COUNT(*) AS n, MIN(period_end) AS pmin,
                       MAX(period_end) AS pmax, MAX(updated_at) AS upd
                FROM fundamentals_pit WHERE symbol = ANY(%s)
                GROUP BY symbol
                """,
                (want,),
            )
            for r in rows:
                if int(r.get("n") or 0) > 0:
                    per[r["symbol"]] = True
                pmin = _iso_date(r.get("pmin"))
                pmax = _iso_date(r.get("pmax"))
                if pmin and (period_min is None or pmin < period_min):
                    period_min = pmin
                if pmax and (period_max is None or pmax > period_max):
                    period_max = pmax
                stamp = _iso(r.get("upd"))
                if stamp and (as_of is None or stamp > as_of):
                    as_of = stamp
        except Exception as exc:  # noqa: BLE001
            log.warning("pit_coverage DB error: %s", exc)
    covered = sum(1 for v in per.values() if v)
    return {
        "total": len(want),
        "covered": covered,
        "perSymbol": per,
        "periodRange": {"min": period_min, "max": period_max},
        "asOf": as_of,
    }


# ----------------------------- macro -----------------------------
def _macro_spark(closes: Optional[List[float]], points: int = 14) -> Optional[List[float]]:
    if not closes or len(closes) < 2:
        return None
    tail = closes[-points:]
    return [round(float(c), 6) for c in tail]


def _spread_spark(a_closes, b_closes, points: int = 14) -> Optional[List[float]]:
    """Basis-point spread sparkline from two aligned yield close series."""
    if not a_closes or not b_closes:
        return None
    n = min(len(a_closes), len(b_closes), points)
    if n < 2:
        return None
    a = a_closes[-n:]
    b = b_closes[-n:]
    return [round((float(a[i]) - float(b[i])) * 100.0, 4) for i in range(n)]


def macro_assets(keys: List[str]) -> Dict[str, dict]:
    """Live-or-mock macro tiles keyed by internal macro symbol.

    Returns ``{key: {symbol, name, price, changePct, unit, sparkline, source,
    asOf}}``. Each fetchable key is served from the ``macro_prices`` table (real
    Yahoo quote on the worker's price cadence) with its sparkline drawn from real
    OHLCV; the 2s10s spread is derived from the two live yields. Any key without a
    live row — feed unavailable, DB empty, or a curated-only series like the 10Y
    breakeven — falls back to the deterministic ``MACRO_ASSETS`` mock so a tile is
    never blank.
    """
    keys = list(keys)
    # Resolve which underlying symbols we need (direct + derived components).
    needed = set()
    for k in keys:
        if k in data.MACRO_YAHOO:
            needed.add(k)
        for part in data.MACRO_DERIVED_PARTS.get(k, ()):  # spread legs
            if part in data.MACRO_YAHOO:
                needed.add(part)

    live: Dict[str, dict] = {}
    closes: Dict[str, List[float]] = {}
    if needed and db.db_available():
        want = sorted(needed)
        try:
            rows = db.query(
                "SELECT symbol, name, price, change_pct, updated_at "
                "FROM macro_prices WHERE symbol = ANY(%s)",
                (want,),
            )
            for r in rows:
                if r.get("price") is not None:
                    live[r["symbol"]] = r
        except Exception as exc:  # noqa: BLE001
            log.warning("macro_assets quote DB error: %s", exc)
        try:
            crows = db.query(
                "SELECT symbol, d, c FROM ohlcv "
                "WHERE symbol = ANY(%s) AND c IS NOT NULL ORDER BY symbol ASC, d ASC",
                (want,),
            )
            for r in crows:
                closes.setdefault(r["symbol"], []).append(_num(r.get("c")))
        except Exception as exc:  # noqa: BLE001
            log.warning("macro_assets ohlcv DB error: %s", exc)

    out: Dict[str, dict] = {}
    for key in keys:
        mock = data.MACRO_ASSETS.get(key, {})
        name = mock.get("name", key)
        unit = mock.get("unit", "index")

        parts = data.MACRO_DERIVED_PARTS.get(key)
        if parts:
            a, b = parts
            if a in live and b in live:
                ya, yb = _num(live[a]["price"]), _num(live[b]["price"])
                ca, cb = _num(live[a].get("change_pct")), _num(live[b].get("change_pct"))
                ya_prev = ya / (1 + ca / 100.0) if (1 + ca / 100.0) else ya
                yb_prev = yb / (1 + cb / 100.0) if (1 + cb / 100.0) else yb
                spread = (ya - yb) * 100.0          # basis points
                spread_prev = (ya_prev - yb_prev) * 100.0
                chg = ((spread - spread_prev) / abs(spread_prev) * 100.0
                       if spread_prev else 0.0)
                spark = (_spread_spark(closes.get(a), closes.get(b))
                         or data.macro_sparkline(key))
                stamps = [s for s in (_iso(live[a].get("updated_at")),
                                      _iso(live[b].get("updated_at"))) if s]
                asof = max(stamps) if stamps else None
                out[key] = {
                    "symbol": key, "name": name, "price": round(spread, 2),
                    "changePct": round(chg, 2), "unit": unit, "sparkline": spark,
                    "source": "live", "asOf": asof,
                }
                continue
        elif key in live:
            r = live[key]
            spark = _macro_spark(closes.get(key)) or data.macro_sparkline(key)
            out[key] = {
                "symbol": key, "name": name, "price": _num(r["price"]),
                "changePct": _num(r.get("change_pct")), "unit": unit,
                "sparkline": spark, "source": "live", "asOf": _iso(r.get("updated_at")),
            }
            continue

        if mock:
            out[key] = {
                "symbol": key, "name": mock["name"], "price": float(mock["price"]),
                "changePct": float(mock["changePct"]), "unit": mock["unit"],
                "sparkline": data.macro_sparkline(key), "source": "mock", "asOf": None,
            }
    return out


# ----------------------------- news -----------------------------
def _news_item(r: dict) -> dict:
    return {
        "id": r["id"],
        "headline": r["headline"],
        "source": r.get("source") or "Yahoo Finance",
        "summary": r.get("summary") or r["headline"],
        "url": r.get("url"),
        "publishedAt": _iso(r.get("published_at")) or _iso(r.get("fetched_at"))
        or datetime.now(timezone.utc).isoformat(),
        "sentiment": r.get("sentiment") or "neutral",
        "tickers": list(r.get("tickers") or []),
    }


def news_for(scope_type: str, scope: str, limit: int = 100) -> List[dict]:
    if db.db_available():
        try:
            if scope_type == "topic":
                rows = _news_topic_rows(scope, limit)
            elif scope_type == "symbol":
                sym = scope.upper()
                rows = db.query(
                    """
                    SELECT * FROM news WHERE %s = ANY(tickers)
                    ORDER BY published_at DESC NULLS LAST, fetched_at DESC LIMIT %s
                    """,
                    (sym, limit),
                )
                if not rows:
                    company = get_company(sym)
                    sid = company["sector"] if company else None
                    if sid:
                        rows = db.query(
                            "SELECT * FROM news WHERE sector = %s ORDER BY published_at DESC NULLS LAST, fetched_at DESC LIMIT %s",
                            (sid, limit),
                        )
            else:
                sid = resolve_sector(scope) or scope
                rows = db.query(
                    "SELECT * FROM news WHERE sector = %s ORDER BY published_at DESC NULLS LAST, fetched_at DESC LIMIT %s",
                    (sid, limit),
                )
                if not rows:
                    syms = symbols_in_sector(sid)
                    if syms:
                        rows = db.query(
                            "SELECT * FROM news WHERE tickers && %s ORDER BY published_at DESC NULLS LAST, fetched_at DESC LIMIT %s",
                            (syms, limit),
                        )
            if rows:
                return [_news_item(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.warning("news_for DB error (%s/%s): %s", scope_type, scope, exc)
    return data.news_for(scope_type, scope, limit)


# Common words that carry no topical signal in a "<topic> news" prompt.
_NEWS_STOPWORDS = {
    "news", "headlines", "headline", "latest", "recent", "update", "updates",
    "show", "me", "the", "a", "an", "about", "on", "for", "of", "and", "or",
    "in", "to", "what", "whats", "what's", "is", "are", "happening", "with",
    "any", "give", "get", "find", "today", "now", "story", "stories", "around",
}


def news_keywords(text: str) -> List[str]:
    """Extract topical keywords from a free-text news prompt."""
    words = re.findall(r"[a-z0-9][a-z0-9\-]+", (text or "").lower())
    kws = [w for w in words if w not in _NEWS_STOPWORDS and len(w) >= 2]
    seen: set = set()
    out: List[str] = []
    for w in kws:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out[:6]


def _news_topic_rows(scope: str, limit: int) -> List[dict]:
    """Keyword search across headline + summary, ranked by relevance then recency."""
    kws = news_keywords(scope)
    if not kws:
        return []
    score_parts: List[str] = []
    where_parts: List[str] = []
    args: List = []
    for kw in kws:
        like = f"%{kw}%"
        score_parts.append(
            "(CASE WHEN headline ILIKE %s THEN 2 ELSE 0 END) "
            "+ (CASE WHEN summary ILIKE %s THEN 1 ELSE 0 END)"
        )
        args.extend([like, like])
        where_parts.append("(headline ILIKE %s OR summary ILIKE %s)")
        args.extend([like, like])
    sql = (
        f"SELECT *, ({' + '.join(score_parts)}) AS rel FROM news "
        f"WHERE {' OR '.join(where_parts)} "
        "ORDER BY rel DESC, published_at DESC NULLS LAST, fetched_at DESC LIMIT %s"
    )
    args.append(limit)
    return db.query(sql, tuple(args))


def _upsert_news(items: List[dict]) -> None:
    rows = [
        (it["id"], it["headline"], it.get("source"), it.get("summary"), it.get("url"),
         it.get("publishedAt"), it.get("sentiment"), it.get("tickers") or [], it.get("sector"))
        for it in items
    ]
    db.execute_many(
        """
        INSERT INTO news (id, headline, source, summary, url, published_at,
                          sentiment, tickers, sector, fetched_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT (id) DO UPDATE SET
          headline = EXCLUDED.headline, summary = EXCLUDED.summary,
          sentiment = EXCLUDED.sentiment,
          tickers = EXCLUDED.tickers,
          sector = COALESCE(EXCLUDED.sector, news.sector),
          fetched_at = now()
        """,
        rows,
    )


def refresh_news_live(scope_type: str, scope: str) -> None:
    """Best-effort, bounded live news fetch at query time so fresh headlines land
    in the panel for the current request. Never raises; failures fall back to
    whatever is already stored."""
    if not db.db_available() or not scope:
        return
    try:
        from .sources import news as n_src
        if scope_type == "topic":
            items = n_src.fetch_topic_news(scope, limit=100, timeout=8.0)
        elif scope_type == "symbol":
            sym = scope.upper()
            company = get_company(sym)
            sid = company["sector"] if company else None
            items = n_src.fetch_news([sym], sid, limit=100, timeout=8.0)
        else:
            sid = resolve_sector(scope) or scope
            syms = symbols_in_sector(sid)[:8]
            items = n_src.fetch_news(syms, sid, limit=100, timeout=8.0) if syms else []
        items = n_src.dedupe(items)
        if items:
            _upsert_news(items)
    except Exception as exc:  # noqa: BLE001
        log.warning("query-time news fetch failed (%s/%s): %s", scope_type, scope, exc)


# ----------------------------- congress trades -----------------------------
def _congress_row(r: dict) -> dict:
    txn = _iso_date(r.get("transaction_date"))
    disc = _iso_date(r.get("disclosure_date"))
    lag = None
    if txn and disc:
        try:
            from datetime import date as _date
            d = (_date.fromisoformat(disc) - _date.fromisoformat(txn)).days
            lag = d if d >= 0 else None
        except ValueError:
            lag = None
    return {
        "id": r["id"],
        "member": r.get("member"),
        "chamber": r.get("chamber"),
        "party": r.get("party") or "Unknown",
        "partyCode": r.get("party_code"),
        "ticker": r.get("ticker"),
        "type": r.get("txn_type") or "other",
        "rawType": r.get("raw_type"),
        "amountRange": r.get("amount_range"),
        "amountLow": _num(r.get("amount_low"), None) if r.get("amount_low") is not None else None,
        "amountHigh": _num(r.get("amount_high"), None) if r.get("amount_high") is not None else None,
        "transactionDate": txn,
        "disclosureDate": disc,
        "lagDays": lag,
        "sourceUrl": r.get("source_url"),
        "description": r.get("description"),
        "_asOf": _iso(r.get("fetched_at")),
        "_source": "live",
    }


def congress_trades(ticker: Optional[str] = None, chamber: Optional[str] = None,
                    party: Optional[str] = None, limit: int = 60) -> List[dict]:
    """Most-recent disclosed congressional trades, optionally filtered by ticker /
    chamber / party. Falls back to the curated mock set if the DB is unavailable
    or empty so the panel never renders blank."""
    if db.db_available():
        try:
            where: List[str] = []
            args: List = []
            if ticker:
                where.append("ticker = %s")
                args.append(ticker.upper())
            if chamber:
                where.append("LOWER(chamber) = %s")
                args.append(chamber.strip().lower())
            if party:
                where.append("(LOWER(party) = %s OR party_code = %s)")
                args.extend([party.strip().lower(), party.strip().upper()])
            clause = (" WHERE " + " AND ".join(where)) if where else ""
            args.append(limit)
            rows = db.query(
                "SELECT * FROM congress_trades" + clause +
                " ORDER BY disclosure_date DESC NULLS LAST,"
                " transaction_date DESC NULLS LAST, fetched_at DESC LIMIT %s",
                tuple(args),
            )
            if rows:
                return [_congress_row(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.warning("congress_trades DB error (%s/%s/%s): %s", ticker, chamber, party, exc)
    return data.congress_trades(ticker=ticker, chamber=chamber, party=party, limit=limit)


def upsert_congress_trades(items: List[dict]) -> None:
    """Idempotent upsert of normalized congress trades keyed by stable id."""
    if not items:
        return
    rows = [
        (it["id"], it.get("member"), it.get("chamber"), it.get("party"),
         it.get("partyCode"), it.get("ticker"), it.get("type"), it.get("rawType"),
         it.get("amountRange"), it.get("amountLow"), it.get("amountHigh"),
         it.get("transactionDate"), it.get("disclosureDate"),
         it.get("sourceUrl"), it.get("description"))
        for it in items
    ]
    db.execute_many(
        """
        INSERT INTO congress_trades
            (id, member, chamber, party, party_code, ticker, txn_type, raw_type,
             amount_range, amount_low, amount_high, transaction_date,
             disclosure_date, source_url, description, fetched_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT (id) DO UPDATE SET
          member = EXCLUDED.member, chamber = EXCLUDED.chamber,
          party = EXCLUDED.party, party_code = EXCLUDED.party_code,
          ticker = EXCLUDED.ticker, txn_type = EXCLUDED.txn_type,
          raw_type = EXCLUDED.raw_type, amount_range = EXCLUDED.amount_range,
          amount_low = EXCLUDED.amount_low, amount_high = EXCLUDED.amount_high,
          transaction_date = EXCLUDED.transaction_date,
          disclosure_date = EXCLUDED.disclosure_date,
          source_url = COALESCE(EXCLUDED.source_url, congress_trades.source_url),
          description = COALESCE(EXCLUDED.description, congress_trades.description),
          fetched_at = now()
        """,
        rows,
    )


def _congress_stale(max_age_seconds: float = 3600.0) -> bool:
    """True if the stored congress feed is missing or older than ``max_age_seconds``."""
    try:
        row = db.query_one("SELECT MAX(fetched_at) AS m FROM congress_trades")
    except Exception:  # noqa: BLE001 — table may not exist yet
        return False
    m = row.get("m") if row else None
    if not m:
        return True
    if isinstance(m, datetime):
        if m.tzinfo is None:
            m = m.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - m).total_seconds() > max_age_seconds
    return True


def refresh_congress_live() -> None:
    """Best-effort, bounded query-time refresh of the congress feed so the panel
    is fresh on the first request even before the worker loop runs. Skips the
    fetch when the stored data is still fresh. Never raises."""
    if not db.db_available() or not _congress_stale():
        return
    try:
        from .sources import congress as c_src
        items = c_src.dedupe(c_src.fetch_congress_trades(limit=1000, timeout=10.0))
        if items:
            upsert_congress_trades(items)
    except Exception as exc:  # noqa: BLE001
        log.warning("query-time congress fetch failed: %s", exc)


# ----------------------------- sentiment -----------------------------
def get_sentiment(scope_type: str, scope: str) -> Optional[dict]:
    if not db.db_available():
        return None
    key = scope.upper() if scope_type == "symbol" else (resolve_sector(scope) or scope)
    try:
        row = db.query_one(
            "SELECT overall, label, sources, trend, updated_at FROM sentiment WHERE scope_type=%s AND scope=%s",
            (scope_type, key),
        )
        if row and row.get("sources") and row.get("trend"):
            return {
                "overall": _num(row.get("overall")),
                "label": row.get("label") or "neutral",
                "sources": row["sources"],
                "trend": row["trend"],
                "_asOf": _iso(row.get("updated_at")),
            }
    except Exception as exc:  # noqa: BLE001
        log.warning("get_sentiment DB error (%s/%s): %s", scope_type, scope, exc)
    return None


# ----------------------------- on-demand expansion -----------------------------
def note_symbol(symbol: str) -> None:
    """Request live data for a referenced symbol on demand (idempotent).

    Symbols can be alphanumeric (SGX codes such as ``D05``/``C38U``) up to 6
    chars. A catalogued breadth name still carrying mock fundamentals gets its
    ``pending`` flag flipped so the worker refreshes it with real data; once it
    has live data we skip it. Brand-new (uncatalogued) symbols are inserted as
    pending."""
    sym = (symbol or "").upper()
    if not sym.isalnum() or not (1 <= len(sym) <= 6):
        return
    if not db.db_available():
        return
    try:
        existing = db.query_one(
            """
            SELECT u.symbol, u.pending, COALESCE(f.is_live, FALSE) AS is_live
            FROM universe u
            LEFT JOIN fundamentals f ON f.symbol = u.symbol
            WHERE u.symbol = %s
            """,
            (sym,),
        )
        if existing:
            if existing.get("is_live") or existing.get("pending"):
                return  # already live, or already queued
            db.execute(
                "UPDATE universe SET pending = TRUE, tracked = TRUE, updated_at = now() WHERE symbol = %s",
                (sym,),
            )
            log.info("requested on-demand refresh for catalogued symbol: %s", sym)
            return
        db.execute(
            """
            INSERT INTO universe (symbol, tracked, pending)
            VALUES (%s, TRUE, TRUE)
            ON CONFLICT (symbol) DO NOTHING
            """,
            (sym,),
        )
        log.info("enqueued new symbol for ingestion: %s", sym)
    except Exception as exc:  # noqa: BLE001
        log.warning("note_symbol DB error for %s: %s", sym, exc)


def prompt_symbols(limit: int = 80) -> List[str]:
    """A capped, most-valuable-first symbol list for LLM tool/system prompts.

    The full catalog is far too large to inline into every tool description, so
    callers use this lean slice while `all_symbols()`/`symbols_in_sector()` still
    expose the full breadth at request time."""
    if db.db_available():
        try:
            rows = db.query(
                "SELECT symbol FROM fundamentals WHERE price IS NOT NULL "
                "ORDER BY market_cap DESC NULLS LAST LIMIT %s",
                (limit,),
            )
            syms = [r["symbol"] for r in rows]
            if syms:
                return syms
        except Exception as exc:  # noqa: BLE001
            log.warning("prompt_symbols DB error: %s", exc)
    return data.top_symbols(limit)


def universe_overview(sector: Optional[str] = None, limit: int = 150) -> dict:
    """Formal investable-universe accessor with coverage + provenance.

    Returns {rows, summary, sectors, source, asOf}. `rows` lists symbols
    (most-valuable first) each tagged with its sector, industry (when known),
    listing venue and provenance (``live`` once real data has been ingested,
    else ``mock`` catalog breadth). `summary`/`sectors` describe coverage across
    the *whole* universe, not just the capped row slice. Provenance is honest:
    nothing is invented, and unknown fields are reported as null.
    """
    sid = resolve_sector(sector) if sector else None
    rows: List[dict] = []
    sectors: List[dict] = []
    summary = {
        "totalSymbols": 0, "liveSymbols": 0, "mockSymbols": 0,
        "trackedSymbols": 0, "sectorCount": 0, "exchanges": [], "asOf": None,
    }
    latest: Optional[str] = None

    if db.db_available():
        try:
            where = "WHERE f.price IS NOT NULL"
            params: list = []
            if sid:
                where += " AND u.sector = %s"
                params.append(sid)

            row_sql = f"""
                SELECT f.symbol, f.name, u.sector, u.industry, u.country,
                       u.exchange, COALESCE(u.tracked, FALSE) AS tracked,
                       COALESCE(f.is_live, FALSE) AS is_live,
                       f.price, f.market_cap, f.updated_at
                FROM fundamentals f
                LEFT JOIN universe u ON u.symbol = f.symbol
                {where}
                ORDER BY f.market_cap DESC NULLS LAST
                LIMIT %s
            """
            db_rows = db.query(row_sql, tuple(params + [limit]))
            for r in db_rows:
                as_of_row = _iso(r.get("updated_at"))
                is_live = bool(r.get("is_live"))
                if is_live and as_of_row and (latest is None or as_of_row > latest):
                    latest = as_of_row
                rows.append({
                    "symbol": r["symbol"],
                    "name": r.get("name") or r["symbol"],
                    "sector": r.get("sector"),
                    "sectorName": sector_name(r["sector"]) if r.get("sector") else None,
                    "industry": r.get("industry"),
                    "country": r.get("country"),
                    "exchange": r.get("exchange"),
                    "tracked": bool(r.get("tracked")),
                    "price": _num(r.get("price")),
                    "marketCap": _num(r.get("market_cap")),
                    "source": "live" if is_live else "mock",
                    "asOf": as_of_row if is_live else None,
                })

            agg = db.query_one(f"""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE f.is_live) AS live,
                       COUNT(*) FILTER (WHERE COALESCE(u.tracked, FALSE)) AS tracked,
                       COUNT(DISTINCT u.exchange) FILTER (WHERE u.exchange IS NOT NULL) AS venues
                FROM fundamentals f
                LEFT JOIN universe u ON u.symbol = f.symbol
                {where}
            """, tuple(params))
            ex_rows = db.query(f"""
                SELECT DISTINCT u.exchange AS exchange
                FROM fundamentals f
                LEFT JOIN universe u ON u.symbol = f.symbol
                {where} AND u.exchange IS NOT NULL
                ORDER BY u.exchange
            """, tuple(params))
            sec_rows = db.query(f"""
                SELECT u.sector AS sector, COUNT(*) AS n,
                       COUNT(*) FILTER (WHERE f.is_live) AS live
                FROM fundamentals f
                LEFT JOIN universe u ON u.symbol = f.symbol
                {where}
                GROUP BY u.sector
                ORDER BY n DESC
            """, tuple(params))

            if agg:
                total = int(agg.get("total") or 0)
                live = int(agg.get("live") or 0)
                summary = {
                    "totalSymbols": total,
                    "liveSymbols": live,
                    "mockSymbols": total - live,
                    "trackedSymbols": int(agg.get("tracked") or 0),
                    "sectorCount": len([s for s in sec_rows if s.get("sector")]),
                    "exchanges": [e["exchange"] for e in ex_rows if e.get("exchange")],
                    "asOf": latest,
                }
            sectors = [
                {
                    "id": s["sector"],
                    "name": sector_name(s["sector"]),
                    "count": int(s.get("n") or 0),
                    "liveCount": int(s.get("live") or 0),
                }
                for s in sec_rows if s.get("sector")
            ]
            if rows:
                return {
                    "rows": rows, "summary": summary, "sectors": sectors,
                    "source": "live" if summary["liveSymbols"] else "mock",
                    "asOf": latest,
                }
        except Exception as exc:  # noqa: BLE001
            log.warning("universe_overview DB error: %s", exc)

    # Mock fallback (DB unavailable / empty): catalog breadth, honestly labeled.
    companies = data.COMPANIES
    items = [
        (sym, c) for sym, c in companies.items()
        if not sid or c.get("sector") == sid
    ]
    items.sort(key=lambda kv: kv[1].get("marketCap", 0), reverse=True)
    rows = [
        {
            "symbol": sym,
            "name": c.get("name") or sym,
            "sector": c.get("sector"),
            "sectorName": sector_name(c["sector"]) if c.get("sector") else None,
            "industry": None,
            "country": c.get("country"),
            "exchange": c.get("exchange"),
            "tracked": sym in set(data.CORE_SYMBOLS),
            "price": c.get("price"),
            "marketCap": c.get("marketCap"),
            "source": "mock",
            "asOf": None,
        }
        for sym, c in items[:limit]
    ]
    sec_counts: Dict[str, int] = {}
    for _, c in items:
        s = c.get("sector")
        if s:
            sec_counts[s] = sec_counts.get(s, 0) + 1
    sectors = sorted(
        ({"id": s, "name": sector_name(s), "count": n, "liveCount": 0}
         for s, n in sec_counts.items()),
        key=lambda x: x["count"], reverse=True,
    )
    exchanges = sorted({c.get("exchange") for _, c in items if c.get("exchange")})
    summary = {
        "totalSymbols": len(items),
        "liveSymbols": 0,
        "mockSymbols": len(items),
        "trackedSymbols": sum(1 for sym, _ in items if sym in set(data.CORE_SYMBOLS)),
        "sectorCount": len(sec_counts),
        "exchanges": exchanges,
        "asOf": None,
    }
    return {"rows": rows, "summary": summary, "sectors": sectors,
            "source": "mock", "asOf": None}


# ----------------------------- ETF holdings -----------------------------
# Real ETF constituents (top holdings) sourced from the free Yahoo funds feed and
# cached in `etf_holdings` (created at runtime by the worker). The free feed only
# exposes each fund's TOP names, so coverage is partial and reported honestly —
# we never pad or impute the remaining weight.
_ETF_HOLDINGS_STALE_DAYS = 14


def upsert_etf_holdings(etf: str, holdings: List[dict], as_of_iso: Optional[str],
                        source: str = "live") -> None:
    """Persist a fund's top holdings, replacing any prior snapshot for that ETF."""
    e = (etf or "").upper().strip().lstrip("$")
    if not e or not holdings or not db.db_available():
        return
    try:
        db.execute("DELETE FROM etf_holdings WHERE etf = %s", (e,))
        rows = [
            (e, str(h["symbol"]).upper(), h.get("name") or str(h["symbol"]).upper(),
             float(h["weight"]), as_of_iso, source)
            for h in holdings
            if h.get("symbol") and h.get("weight") is not None
        ]
        db.execute_many(
            """
            INSERT INTO etf_holdings (etf, symbol, name, weight, as_of, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (etf, symbol) DO UPDATE
              SET name = EXCLUDED.name, weight = EXCLUDED.weight,
                  as_of = EXCLUDED.as_of, source = EXCLUDED.source,
                  updated_at = now()
            """,
            rows,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("upsert_etf_holdings DB error for %s: %s", e, exc)


def etf_holdings(etf: str) -> Optional[dict]:
    """Persisted top holdings for an ETF, or ``None`` when none are cached.

    Returns ``{holdings: [{symbol, name, weight}], asOf, source, stale}`` where
    ``stale`` flags a snapshot older than the freshness window (the caller can
    then re-fetch). Largest weight first.
    """
    e = (etf or "").upper().strip().lstrip("$")
    if not e or not db.db_available():
        return None
    try:
        rows = db.query(
            """
            SELECT symbol, name, weight, as_of, source, updated_at
            FROM etf_holdings WHERE etf = %s ORDER BY weight DESC
            """,
            (e,),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("etf_holdings DB error for %s: %s", e, exc)
        return None
    if not rows:
        return None
    holdings = [
        {"symbol": r["symbol"], "name": r.get("name") or r["symbol"],
         "weight": _num(r.get("weight"))}
        for r in rows if r.get("weight") is not None
    ]
    if not holdings:
        return None
    updated = rows[0].get("updated_at")
    stale = False
    if isinstance(updated, datetime):
        age = datetime.now(timezone.utc) - (
            updated if updated.tzinfo else updated.replace(tzinfo=timezone.utc))
        stale = age > timedelta(days=_ETF_HOLDINGS_STALE_DAYS)
    return {
        "holdings": holdings,
        "asOf": _iso_date(rows[0].get("as_of")),
        "source": rows[0].get("source") or "live",
        "stale": stale,
    }


def etfs_holding(symbol: str) -> List[dict]:
    """Reverse lookup: every cached ETF that holds ``symbol`` and its weight.

    Returns ``[{etf, name, weight, asOf}]`` sorted by the stock's weight in each
    fund (largest first). Empty when nothing is cached.
    """
    sym = (symbol or "").upper().strip().lstrip("$")
    if not sym or not db.db_available():
        return []
    try:
        rows = db.query(
            """
            SELECT etf, name, weight, as_of FROM etf_holdings
            WHERE symbol = %s ORDER BY weight DESC
            """,
            (sym,),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("etfs_holding DB error for %s: %s", sym, exc)
        return []
    return [
        {"etf": r["etf"], "name": r.get("name") or sym,
         "weight": _num(r.get("weight")), "asOf": _iso_date(r.get("as_of"))}
        for r in rows if r.get("weight") is not None
    ]


def etf_holdings_universe() -> List[str]:
    """Distinct ETFs with cached holdings (for reverse-lookup coverage)."""
    if not db.db_available():
        return []
    try:
        rows = db.query("SELECT DISTINCT etf FROM etf_holdings ORDER BY etf")
        return [r["etf"] for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("etf_holdings_universe DB error: %s", exc)
        return []


_INSIDER_COLS = (
    "symbol", "cik", "issuer_name", "insider_name", "role", "transaction_code",
    "transaction_type", "acquired_disposed", "security_title", "is_derivative",
    "shares", "price", "value", "shares_owned_after", "transaction_date",
    "filing_date", "form", "url", "accession_no",
)


def _numn(v):
    """Float-or-None — unlike ``_num`` this preserves NULLs instead of coercing
    them to 0.0, so a missing insider price/value stays honestly absent."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _insider_row(r: dict) -> dict:
    return {
        "symbol": r.get("symbol"),
        "cik": r.get("cik"),
        "issuerName": r.get("issuer_name"),
        "insider": r.get("insider_name"),
        "role": r.get("role"),
        "code": r.get("transaction_code"),
        "type": r.get("transaction_type"),
        "acquiredDisposed": r.get("acquired_disposed"),
        "security": r.get("security_title"),
        "isDerivative": bool(r.get("is_derivative")),
        "shares": _numn(r.get("shares")),
        "price": _numn(r.get("price")),
        "value": _numn(r.get("value")),
        "sharesOwnedAfter": _numn(r.get("shares_owned_after")),
        "transactionDate": _iso(r.get("transaction_date")),
        "filingDate": _iso(r.get("filing_date")),
        "form": r.get("form"),
        "url": r.get("url"),
        "accession": r.get("accession_no"),
    }


def insider_transactions(symbol: str, days: int = 180) -> List[dict]:
    """Real EDGAR insider (Form 4/5) transactions for a symbol in a trailing
    window, newest first. Returns ``[]`` when the DB has none — never mock."""
    sym = (symbol or "").upper()
    if not db.db_available():
        return []
    cutoff = (date.today() - timedelta(days=days)).isoformat() if days else None
    try:
        if cutoff:
            rows = db.query(
                f"SELECT {', '.join(_INSIDER_COLS)} FROM insider_transactions "
                "WHERE symbol = %s AND transaction_date >= %s "
                "ORDER BY transaction_date DESC NULLS LAST, filing_date DESC NULLS LAST",
                (sym, cutoff),
            )
        else:
            rows = db.query(
                f"SELECT {', '.join(_INSIDER_COLS)} FROM insider_transactions "
                "WHERE symbol = %s "
                "ORDER BY transaction_date DESC NULLS LAST, filing_date DESC NULLS LAST",
                (sym,),
            )
        return [_insider_row(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("insider_transactions DB error (%s): %s", sym, exc)
        return []


def ensure_insider(symbol: str, days: int = 180) -> dict:
    """Return insider transactions for a symbol, fetching live from EDGAR on the
    request path when the DB has none yet (so an arbitrary ticker still works).

    Returns ``{"transactions", "source", "asOf", "issuerName", "cik"}``. Source
    is ``"live"`` whenever data flowed (DB or fresh fetch), ``"unavailable"``
    when the ticker has no SEC CIK, and ``"error"`` on a hard EDGAR failure."""
    sym = (symbol or "").upper()
    rows = insider_transactions(sym, days)
    if rows:
        return {
            "transactions": rows,
            "source": "live",
            "asOf": max([r["filingDate"] for r in rows if r.get("filingDate")], default=None),
            "issuerName": rows[0].get("issuerName"),
            "cik": rows[0].get("cik"),
        }

    # Nothing cached yet — fetch synchronously (bounded) so the panel is useful
    # immediately, persist it, and queue the name for ongoing background refresh.
    from .sources import edgar as e_src
    try:
        res = e_src.fetch_insider_transactions(sym, since_days=days, max_filings=20)
    except Exception as exc:  # noqa: BLE001
        log.warning("ensure_insider EDGAR fetch failed (%s): %s", sym, exc)
        return {"transactions": [], "source": "error", "asOf": None,
                "issuerName": None, "cik": None}

    txns = res.get("transactions") or []
    if res.get("source") == "unavailable":
        return {"transactions": [], "source": "unavailable", "asOf": None,
                "issuerName": res.get("issuerName"), "cik": res.get("cik")}

    if txns and db.db_available():
        try:
            from . import worker  # local import: worker owns the upsert SQL
            worker._upsert_insider(txns)
            note_symbol(sym)  # keep it fresh via the background insider loop
        except Exception as exc:  # noqa: BLE001
            log.warning("ensure_insider persist failed (%s): %s", sym, exc)

    return {
        "transactions": txns,
        "source": "live",
        "asOf": res.get("asOf"),
        "issuerName": res.get("issuerName"),
        "cik": res.get("cik"),
    }


# --------------------------------------------------------------------------- #
# Institutional 13F holdings
# --------------------------------------------------------------------------- #
def inst_data_available() -> bool:
    """True when any institutional 13F filings have been ingested yet."""
    if not db.db_available():
        return False
    try:
        rows = db.query("SELECT 1 FROM inst_filings LIMIT 1")
        return bool(rows)
    except Exception:  # noqa: BLE001
        return False


def inst_latest_period(cik: str) -> Optional[str]:
    """Most recent stored report period for a manager CIK, or None."""
    if not db.db_available():
        return None
    try:
        rows = db.query(
            "SELECT period FROM inst_filings WHERE cik = %s ORDER BY period DESC LIMIT 1",
            (cik,),
        )
        return _iso_date(rows[0]["period"]) if rows else None
    except Exception as exc:  # noqa: BLE001
        log.warning("inst_latest_period DB error (%s): %s", cik, exc)
        return None


def inst_filing_periods() -> List[dict]:
    """Every stored 13F filing (one per manager per period), newest first.

    Used to identify each manager's latest and prior report periods and the
    portfolio total backing percent-of-portfolio."""
    if not db.db_available():
        return []
    try:
        rows = db.query(
            "SELECT cik, institution, period, filing_date, accession_no, url, "
            "total_value, positions FROM inst_filings ORDER BY cik, period DESC"
        )
        return [{
            "cik": r.get("cik"),
            "institution": r.get("institution"),
            "period": _iso_date(r.get("period")),
            "filingDate": _iso_date(r.get("filing_date")),
            "accession": r.get("accession_no"),
            "url": r.get("url"),
            "totalValue": _numn(r.get("total_value")),
            "positions": r.get("positions"),
        } for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("inst_filing_periods DB error: %s", exc)
        return []


def inst_holdings_for_ticker(ticker: str) -> List[dict]:
    """All stored institutional positions in a ticker (share positions and
    option positions across every manager/period). Empty when none — never mock."""
    sym = (ticker or "").upper().strip()
    if not sym or not db.db_available():
        return []
    try:
        rows = db.query(
            "SELECT cik, period, cusip, put_call, institution, ticker, name, "
            "title_of_class, shares_type, shares, value, url, accession_no "
            "FROM inst_holdings WHERE ticker = %s",
            (sym,),
        )
        return [{
            "cik": r.get("cik"),
            "period": _iso_date(r.get("period")),
            "cusip": r.get("cusip"),
            "putCall": r.get("put_call") or "",
            "institution": r.get("institution"),
            "ticker": r.get("ticker"),
            "name": r.get("name"),
            "titleOfClass": r.get("title_of_class"),
            "sharesType": r.get("shares_type"),
            "shares": _numn(r.get("shares")),
            "value": _numn(r.get("value")),
            "url": r.get("url"),
            "accession": r.get("accession_no"),
        } for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("inst_holdings_for_ticker DB error (%s): %s", sym, exc)
        return []
def company_filings(symbol: str, *, forms: Optional[list] = None,
                    days: Optional[int] = None, limit: int = 80) -> dict:
    """Recent SEC filings for an issuer, fetched live from EDGAR on the request
    path. ``source`` is ``"live"`` when EDGAR answered (even with zero filings),
    ``"unavailable"`` when the ticker has no CIK, and ``"error"`` on a hard
    failure — never a fabricated list."""
    sym = (symbol or "").upper().strip()
    from .sources import edgar as e_src
    try:
        return e_src.fetch_company_filings(sym, forms=forms, since_days=days, limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("company_filings EDGAR fetch failed (%s): %s", sym, exc)
        return {"symbol": sym, "cik": None, "issuerName": None,
                "filings": [], "asOf": None, "source": "error"}


def filing_search(query: str, *, forms: Optional[list] = None,
                  symbol: Optional[str] = None, days: Optional[int] = None,
                  limit: int = 40) -> dict:
    """EDGAR full-text keyword search, optionally scoped to one issuer's CIK and a
    look-back window. Honest source states mirror ``company_filings``."""
    from .sources import edgar as e_src
    cik10 = None
    issuer = None
    sym = (symbol or "").upper().strip() or None
    if sym:
        try:
            hit = e_src.resolve_cik(sym)
            if hit:
                cik10, issuer = hit
        except Exception as exc:  # noqa: BLE001
            log.warning("filing_search CIK resolve failed (%s): %s", sym, exc)
    start = (date.today() - timedelta(days=days)).isoformat() if days else None
    try:
        res = e_src.full_text_search(query, forms=forms, cik10=cik10, start=start, limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("filing_search EDGAR failed (%s): %s", query, exc)
        res = {"query": query, "hits": [], "total": 0, "source": "error"}
    res["symbol"] = sym
    res["cik"] = cik10
    res["issuerName"] = issuer
    return res


def as_of(*records) -> Optional[str]:
    """Most-recent freshness timestamp across the given company/sentiment records."""
    stamps = [r.get("_asOf") for r in records if isinstance(r, dict) and r.get("_asOf")]
    return max(stamps) if stamps else None


def source_of(*records) -> str:
    """'live' if any record came from the DB, else 'mock'."""
    for r in records:
        if isinstance(r, dict) and r.get("_source") == "live":
            return "live"
    return "mock"
