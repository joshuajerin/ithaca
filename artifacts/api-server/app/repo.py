"""DB-backed data-access layer for the panel skills.

Mirrors the public surface of `data.py` (the Phase 1 curated mock dataset) but
reads from Postgres. Every accessor falls back to the deterministic mock data
when the database is unavailable or has no rows for a symbol/scope, preserving
the "no empty panels" guarantee. Freshness is surfaced via `_asOf`/`_source`
keys on company records and an `as_of` helper for panels.
"""
from __future__ import annotations

import logging
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
                       f.price, f.change_pct, f.market_cap, f.pe_ratio, f.volume,
                       f.revenue, f.net_margin, f.eps, f.dividend_yield, f.beta,
                       f.week52_high, f.week52_low, f.description, f.is_live,
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
    c = {
        "symbol": row["symbol"],
        "name": row.get("name") or row["symbol"],
        "sector": row.get("sector") or "ai_tech",
        "price": _num(row.get("price")),
        "changePct": _num(row.get("change_pct")),
        "marketCap": _num(row.get("market_cap")),
        "peRatio": row.get("pe_ratio"),
        "volume": _num(row.get("volume")),
        "revenue": row.get("revenue"),
        "netMargin": _num(row.get("net_margin")),
        "eps": _num(row.get("eps")),
        "dividendYield": _num(row.get("dividend_yield")),
        "beta": _num(row.get("beta")),
        "week52High": _num(row.get("week52_high")),
        "week52Low": _num(row.get("week52_low")),
        "description": row.get("description") or "",
        "country": row.get("country"),
        "exchange": row.get("exchange"),
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
                       f.price, f.change_pct, f.market_cap, f.pe_ratio, f.volume,
                       f.revenue, f.net_margin, f.eps, f.dividend_yield, f.beta,
                       f.week52_high, f.week52_low, f.description, f.is_live,
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
def price_series(symbol: str, days: int = 90) -> List[dict]:
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


def price_series_meta(symbol: str, days: int = 90) -> dict:
    """Like `price_series` but reports provenance for freshness metadata.

    Returns {"points": [...], "source": "live"|"mock", "asOf": iso|None}. The
    series is "live" only when it came from real OHLCV rows in the DB; otherwise
    it falls back to the deterministic curated mock series.
    """
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


def news_for(scope_type: str, scope: str, limit: int = 8) -> List[dict]:
    if db.db_available():
        try:
            if scope_type == "symbol":
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
