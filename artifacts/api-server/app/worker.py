"""Background data-ingestion worker.

Runs inside the FastAPI lifespan as a set of staggered async loops:
  - prices       (fast)   : OHLCV + a light quote snapshot per tracked symbol
  - fundamentals (slow)   : full quote-summary snapshot per tracked symbol
  - news         (medium) : RSS headlines per sector, tagged with sentiment
  - sentiment    (slow)   : aggregate sentiment per symbol and per sector
  - on-demand    (frequent): fetch newly-referenced ("pending") symbols ASAP

Network/parse failures are caught and logged per symbol/source so one bad
source never blocks the request path or the rest of the loop. All writes are
idempotent upserts keyed by (symbol[, date]) / news id / (scope_type, scope).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Optional

from . import data, db, strategy
from .sources import fundamentals as f_src
from .sources import news as n_src
from .sources import prices as p_src
from .sources import sentiment as s_src
from .sources._resilient import CircuitOpenError

log = logging.getLogger("terminal.worker")

# Cadences (seconds). Prices fast; fundamentals/news/sentiment slower.
PRICE_INTERVAL = 90
FUNDAMENTALS_INTERVAL = 900
NEWS_INTERVAL = 120
SENTIMENT_INTERVAL = 600
ONDEMAND_INTERVAL = 15
# Daily mark cadence: re-check hourly. record_daily_snapshots is idempotent per
# trading day (one row per strategy per day), so an hourly pass simply keeps the
# day's NAV fresh and settles to the close once prices stop moving.
SNAPSHOT_INTERVAL = 3600
MACRO_INTERVAL = 120

# A macro quote is only treated as "live" when its upstream timestamp is within
# this many days. Some Yahoo macro symbols (illiquid futures, etc.) go stale or
# stop updating; we never present a month-old print as a live quote.
MACRO_STALE_DAYS = 5

# Breadth market-cap refresh: a deliberately slow round-robin that touches only
# the single market_cap field on mock breadth names (is_live = FALSE), so the
# hand-entered cap hints don't drift over months. Small batch + long sleep so it
# never competes with the live loops or the request path. ~556 breadth names at
# 10 per tick / 5 min ≈ a full sweep every few hours.
BREADTH_INTERVAL = 300
BREADTH_BATCH = 10
# Defer the first breadth pass so it never piles onto cold-start ingestion/boot.
BREADTH_STARTUP_DELAY = 180

# Small pause between RSS batches so a fast news cadence doesn't trip Yahoo 403/429.
NEWS_BATCH_PAUSE = 1.5

_SEM = asyncio.Semaphore(5)  # bound concurrent network calls
_tasks: List[asyncio.Task] = []


async def _net(fn, *args):
    async with _SEM:
        return await asyncio.to_thread(fn, *args)


# ----------------------------- seeding -----------------------------
def _seed_universe() -> None:
    """Seed sectors + the full curated universe and pre-seed mock fundamentals.

    The whole catalog (US + SGX) is registered so sector filters, screeners and
    heatmaps have breadth immediately, but only the curated CORE set is marked
    ``tracked`` for continuous live ingestion. Everything else carries
    deterministic mock fundamentals (``is_live = FALSE``) and is refreshed with
    real data on demand when a user opens it. Schema is extended idempotently so
    no migration step is required."""
    for ddl in (
        "ALTER TABLE universe ADD COLUMN IF NOT EXISTS country TEXT",
        "ALTER TABLE universe ADD COLUMN IF NOT EXISTS exchange TEXT",
        "ALTER TABLE universe ADD COLUMN IF NOT EXISTS industry TEXT",
        "ALTER TABLE universe ADD COLUMN IF NOT EXISTS website TEXT",
        "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS is_live BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS revenue_growth DOUBLE PRECISION",
        "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS earnings_date DATE",
        "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS ex_dividend_date DATE",
        "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS dividend_date DATE",
        "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS mcap_refreshed_at TIMESTAMPTZ",
    ):
        db.execute(ddl)

    for sid, name in data.SECTORS.items():
        db.execute(
            "INSERT INTO sectors (id, name) VALUES (%s, %s) "
            "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = now()",
            (sid, name),
        )

    core = set(data.CORE_SYMBOLS)
    uni_rows = [
        (sym, c["name"], c["sector"], c.get("country"), c.get("exchange"),
         sym in core)
        for sym, c in data.COMPANIES.items()
    ]
    db.execute_many(
        """
        INSERT INTO universe (symbol, name, sector, country, exchange, tracked, pending)
        VALUES (%s, %s, %s, %s, %s, %s, FALSE)
        ON CONFLICT (symbol) DO UPDATE
          SET name = COALESCE(universe.name, EXCLUDED.name),
              sector = COALESCE(universe.sector, EXCLUDED.sector),
              country = COALESCE(universe.country, EXCLUDED.country),
              exchange = COALESCE(universe.exchange, EXCLUDED.exchange),
              tracked = universe.tracked OR EXCLUDED.tracked
        """,
        uni_rows,
    )

    # Pre-seed deterministic mock fundamentals so breadth panels never read empty.
    # DO NOTHING preserves any real (is_live) data already ingested in prior runs.
    fund_rows = [
        (sym, c["name"], c["price"], c["changePct"], c["marketCap"], c["peRatio"],
         c["volume"], c["revenue"], c["netMargin"], c["eps"], c["dividendYield"],
         c["beta"], c["week52High"], c["week52Low"], c["description"])
        for sym, c in data.COMPANIES.items()
    ]
    db.execute_many(
        """
        INSERT INTO fundamentals (symbol, name, price, change_pct, market_cap,
            pe_ratio, volume, revenue, net_margin, eps, dividend_yield, beta,
            week52_high, week52_low, description, is_live, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, FALSE, now())
        ON CONFLICT (symbol) DO NOTHING
        """,
        fund_rows,
    )
    log.info(
        "seeded universe: %d sectors, %d symbols (%d core tracked)",
        len(data.SECTORS), len(data.COMPANIES), len(core),
    )


def _ensure_macro_schema() -> None:
    """Dedicated, isolated table for live macro/cross-asset quotes.

    Kept separate from `universe`/`fundamentals` so macro pseudo-symbols
    (^TNX, indices, FX, futures) never leak into equity screeners/heatmaps."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_quotes (
            symbol      TEXT PRIMARY KEY,
            price       DOUBLE PRECISION,
            change_pct  DOUBLE PRECISION,
            sparkline   JSONB,
            is_live     BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def _tracked_symbols() -> List[str]:
    rows = db.query("SELECT symbol FROM universe WHERE tracked = TRUE ORDER BY symbol")
    return [r["symbol"] for r in rows]


def _sector_of(symbol: str) -> Optional[str]:
    row = db.query_one("SELECT sector FROM universe WHERE symbol = %s", (symbol,))
    return row["sector"] if row else None


# ----------------------------- upserts -----------------------------
def _upsert_ohlcv(symbol: str, points: list) -> None:
    rows = [
        (symbol, p["d"], p.get("o"), p.get("h"), p.get("l"), p.get("c"), p.get("v"))
        for p in points
    ]
    db.execute_many(
        """
        INSERT INTO ohlcv (symbol, d, o, h, l, c, v, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (symbol, d) DO UPDATE SET
          o = EXCLUDED.o, h = EXCLUDED.h, l = EXCLUDED.l,
          c = EXCLUDED.c, v = EXCLUDED.v, updated_at = now()
        """,
        rows,
    )


def _upsert_quote(q: dict) -> None:
    db.execute(
        """
        INSERT INTO fundamentals (symbol, name, price, change_pct, volume,
                                  week52_high, week52_low, is_live, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, now())
        ON CONFLICT (symbol) DO UPDATE SET
          name = COALESCE(EXCLUDED.name, fundamentals.name),
          price = COALESCE(EXCLUDED.price, fundamentals.price),
          change_pct = COALESCE(EXCLUDED.change_pct, fundamentals.change_pct),
          volume = COALESCE(EXCLUDED.volume, fundamentals.volume),
          week52_high = COALESCE(EXCLUDED.week52_high, fundamentals.week52_high),
          week52_low = COALESCE(EXCLUDED.week52_low, fundamentals.week52_low),
          is_live = TRUE,
          updated_at = now()
        """,
        (q.get("symbol"), q.get("name"), q.get("price"), q.get("changePct"),
         q.get("volume"), q.get("week52High"), q.get("week52Low")),
    )


def _upsert_fundamentals(d: dict) -> None:
    db.execute(
        """
        INSERT INTO fundamentals (symbol, name, price, change_pct, market_cap,
            pe_ratio, volume, revenue, net_margin, revenue_growth, eps,
            dividend_yield, beta, week52_high, week52_low, description,
            is_live, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, TRUE, now())
        ON CONFLICT (symbol) DO UPDATE SET
          name = COALESCE(EXCLUDED.name, fundamentals.name),
          price = COALESCE(EXCLUDED.price, fundamentals.price),
          change_pct = COALESCE(EXCLUDED.change_pct, fundamentals.change_pct),
          market_cap = COALESCE(EXCLUDED.market_cap, fundamentals.market_cap),
          pe_ratio = EXCLUDED.pe_ratio,
          volume = COALESCE(EXCLUDED.volume, fundamentals.volume),
          revenue = COALESCE(EXCLUDED.revenue, fundamentals.revenue),
          net_margin = COALESCE(EXCLUDED.net_margin, fundamentals.net_margin),
          revenue_growth = COALESCE(EXCLUDED.revenue_growth, fundamentals.revenue_growth),
          eps = COALESCE(EXCLUDED.eps, fundamentals.eps),
          dividend_yield = COALESCE(EXCLUDED.dividend_yield, fundamentals.dividend_yield),
          beta = COALESCE(EXCLUDED.beta, fundamentals.beta),
          week52_high = COALESCE(EXCLUDED.week52_high, fundamentals.week52_high),
          week52_low = COALESCE(EXCLUDED.week52_low, fundamentals.week52_low),
          description = COALESCE(EXCLUDED.description, fundamentals.description),
          is_live = TRUE,
          updated_at = now()
        """,
        (d.get("symbol"), d.get("name"), d.get("price"),
         d.get("changePct"), d.get("marketCap"), d.get("peRatio"), d.get("volume"),
         d.get("revenue"), d.get("netMargin"), d.get("revenueGrowth"), d.get("eps"),
         d.get("dividendYield"), d.get("beta"), d.get("week52High"),
         d.get("week52Low"), d.get("description")),
    )
    if d.get("sector"):
        db.execute(
            "UPDATE universe SET sector = %s, name = COALESCE(name, %s), "
            "industry = COALESCE(%s, industry), website = COALESCE(%s, website), "
            "updated_at = now() WHERE symbol = %s",
            (d["sector"], d.get("name"), d.get("industry"), d.get("website"),
             d.get("symbol")),
        )


def _upsert_calendar(c: dict) -> None:
    """Persist upcoming earnings/dividend dates from the live calendar feed.
    Only overwrites a column when the new value is present so a transient empty
    calendar never wipes a previously-known date."""
    db.execute(
        """
        INSERT INTO fundamentals (symbol, earnings_date, ex_dividend_date,
                                  dividend_date, updated_at)
        VALUES (%s, %s, %s, %s, now())
        ON CONFLICT (symbol) DO UPDATE SET
          earnings_date = COALESCE(EXCLUDED.earnings_date, fundamentals.earnings_date),
          ex_dividend_date = COALESCE(EXCLUDED.ex_dividend_date, fundamentals.ex_dividend_date),
          dividend_date = COALESCE(EXCLUDED.dividend_date, fundamentals.dividend_date),
          updated_at = now()
        """,
        (c.get("symbol"), c.get("earningsDate"), c.get("exDividendDate"),
         c.get("dividendDate")),
    )


def _update_market_cap(symbol: str, market_cap: float) -> None:
    """Refresh ONLY the market_cap of a mock breadth row.

    Guarded by ``is_live = FALSE`` so a cap-only refresh never overwrites a row
    that already carries full live fundamentals, and it never flips ``is_live``
    to TRUE (the refreshed row is still mock for every other field). ``updated_at``
    is intentionally left untouched so this cheap pass doesn't masquerade as a
    full fundamentals snapshot; ``mcap_refreshed_at`` tracks the round-robin."""
    db.execute(
        """
        UPDATE fundamentals
           SET market_cap = %s, mcap_refreshed_at = now()
         WHERE symbol = %s AND is_live = FALSE
        """,
        (market_cap, symbol),
    )


def _upsert_news(items: list) -> None:
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


def _upsert_sentiment(scope_type: str, scope: str, payload: dict) -> None:
    import json
    db.execute(
        """
        INSERT INTO sentiment (scope_type, scope, overall, label, sources, trend, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (scope_type, scope) DO UPDATE SET
          overall = EXCLUDED.overall, label = EXCLUDED.label,
          sources = EXCLUDED.sources, trend = EXCLUDED.trend, updated_at = now()
        """,
        (scope_type, scope, payload["overall"], payload["label"],
         json.dumps(payload["sources"]), json.dumps(payload["trend"])),
    )


# ----------------------------- per-symbol ingest -----------------------------
async def _ingest_prices(symbol: str) -> None:
    # Fetch under the Yahoo symbol (adds .SI for SGX) but persist under the
    # internal base code so all reads stay keyed consistently.
    ysym = data.yahoo_symbol(symbol)
    try:
        # Fetch ~2 years of daily bars so the store always holds well over a
        # full year of history — enough to anchor a true 1Y return for live
        # names (not just YTD). Upserts are idempotent, so re-fetching the wider
        # window each cycle only refreshes/extends rows.
        res = await _net(p_src.fetch_price_history, ysym, "2y", "1d")
        if res.get("points"):
            await asyncio.to_thread(_upsert_ohlcv, symbol, res["points"])
        if res.get("quote", {}).get("price") is not None:
            quote = dict(res["quote"])
            quote["symbol"] = symbol
            await asyncio.to_thread(_upsert_quote, quote)
    except CircuitOpenError as exc:
        log.debug("price ingest skipped for %s: %s", symbol, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("price ingest failed for %s: %s", symbol, exc)


def _upsert_macro(symbol: str, price, change_pct, sparkline: list, is_live: bool) -> None:
    import json
    db.execute(
        """
        INSERT INTO macro_quotes (symbol, price, change_pct, sparkline, is_live, updated_at)
        VALUES (%s, %s, %s, %s, %s, now())
        ON CONFLICT (symbol) DO UPDATE SET
          price = EXCLUDED.price,
          change_pct = EXCLUDED.change_pct,
          sparkline = EXCLUDED.sparkline,
          is_live = EXCLUDED.is_live,
          updated_at = now()
        """,
        (symbol, price, change_pct, json.dumps(sparkline), is_live),
    )


def _macro_is_stale(as_of: Optional[str]) -> bool:
    if not as_of:
        return True
    try:
        from datetime import datetime, timezone
        then = datetime.fromisoformat(as_of)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - then).days > MACRO_STALE_DAYS
    except Exception:  # noqa: BLE001
        return True


async def _ingest_macro(symbol: str) -> None:
    """Fetch a live quote + short sparkline for one macro asset.

    Persists the latest close-series tail as the sparkline and marks the row
    live only when the upstream quote is fresh; a stale/illiquid symbol is
    stored with ``is_live = FALSE`` so the dashboard falls back to its curated
    mock value and labels the tile honestly."""
    ysym = data.macro_yahoo_symbol(symbol)
    if not ysym:
        return
    try:
        res = await _net(p_src.fetch_price_history, ysym, "1mo", "1d")
        quote = res.get("quote") or {}
        price = quote.get("price")
        if price is None:
            return
        change_pct = quote.get("changePct")
        closes = [p["c"] for p in (res.get("points") or []) if p.get("c") is not None]
        sparkline = closes[-14:] if closes else [float(price)]
        is_live = not _macro_is_stale(quote.get("asOf"))
        await asyncio.to_thread(
            _upsert_macro, symbol, float(price),
            float(change_pct) if change_pct is not None else None,
            sparkline, is_live,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("macro ingest failed for %s (%s): %s", symbol, ysym, exc)


async def _ingest_fundamentals(symbol: str) -> None:
    ysym = data.yahoo_symbol(symbol)
    try:
        d = await _net(f_src.fetch_fundamentals, ysym)
        d["symbol"] = symbol
        await asyncio.to_thread(_upsert_fundamentals, d)
    except CircuitOpenError as exc:
        log.debug("fundamentals ingest skipped for %s: %s", symbol, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("fundamentals ingest failed for %s: %s", symbol, exc)
    # Earnings/dividend calendar is a separate (best-effort) call on the same
    # slow cadence so a missing calendar never blocks the fundamentals snapshot.
    try:
        cal = await _net(f_src.fetch_calendar, ysym)
        cal["symbol"] = symbol
        await asyncio.to_thread(_upsert_calendar, cal)
    except Exception as exc:  # noqa: BLE001
        log.warning("calendar ingest failed for %s: %s", symbol, exc)


async def _refresh_market_cap(symbol: str) -> None:
    ysym = data.yahoo_symbol(symbol)
    try:
        mcap = await _net(f_src.fetch_market_cap, ysym)
        if mcap:
            await asyncio.to_thread(_update_market_cap, symbol, mcap)
    except Exception as exc:  # noqa: BLE001
        log.warning("market-cap refresh failed for %s: %s", symbol, exc)


async def _ingest_news_for(symbols: List[str], sector: Optional[str]) -> None:
    if not symbols:
        return
    try:
        items = await _net(n_src.fetch_news, symbols, sector, 40)
        items = n_src.dedupe(items or [])
        if items:
            await asyncio.to_thread(_upsert_news, items)
    except CircuitOpenError as exc:
        log.debug("news ingest skipped for %s: %s", symbols, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("news ingest failed for %s: %s", symbols, exc)


async def _ingest_market_news() -> None:
    """Broad, key-less market/business headlines (Google News) so the feed has
    breadth beyond per-ticker stories. Best-effort."""
    try:
        items = await _net(n_src.fetch_market_news, 40)
        items = n_src.dedupe(items or [])
        if items:
            await asyncio.to_thread(_upsert_news, items)
    except CircuitOpenError as exc:
        log.debug("market news ingest skipped: %s", exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("market news ingest failed: %s", exc)


# ----------------------------- loops -----------------------------
async def _price_loop():
    while True:
        try:
            syms = await asyncio.to_thread(_tracked_symbols)
            await asyncio.gather(*(_ingest_prices(s) for s in syms))
            log.info("price cycle complete (%d symbols)", len(syms))
        except Exception as exc:  # noqa: BLE001
            log.warning("price loop error: %s", exc)
        await asyncio.sleep(PRICE_INTERVAL)


async def _macro_loop():
    syms = data.macro_symbols()
    while True:
        try:
            await asyncio.gather(*(_ingest_macro(s) for s in syms))
            log.info("macro cycle complete (%d symbols)", len(syms))
        except Exception as exc:  # noqa: BLE001
            log.warning("macro loop error: %s", exc)
        await asyncio.sleep(MACRO_INTERVAL)


async def _fundamentals_loop():
    while True:
        try:
            syms = await asyncio.to_thread(_tracked_symbols)
            for s in syms:  # serialized-ish via semaphore; yfinance is heavier
                await _ingest_fundamentals(s)
            log.info("fundamentals cycle complete (%d symbols)", len(syms))
        except Exception as exc:  # noqa: BLE001
            log.warning("fundamentals loop error: %s", exc)
        await asyncio.sleep(FUNDAMENTALS_INTERVAL)


async def _news_loop():
    while True:
        try:
            await _ingest_market_news()
            for sid in data.SECTORS.keys():
                rows = await asyncio.to_thread(
                    db.query,
                    "SELECT symbol FROM universe WHERE sector = %s AND tracked = TRUE",
                    (sid,),
                )
                syms = [r["symbol"] for r in rows]
                for i in range(0, len(syms), 8):
                    await _ingest_news_for(syms[i:i + 8], sid)
                    # Stagger batches so the faster cadence stays under Yahoo limits.
                    await asyncio.sleep(NEWS_BATCH_PAUSE)
            log.info("news cycle complete")
        except Exception as exc:  # noqa: BLE001
            log.warning("news loop error: %s", exc)
        await asyncio.sleep(NEWS_INTERVAL)


async def _sentiment_loop():
    while True:
        try:
            syms = await asyncio.to_thread(_tracked_symbols)
            for s in syms:
                rows = await asyncio.to_thread(
                    db.query,
                    "SELECT sentiment FROM news WHERE %s = ANY(tickers) ORDER BY published_at DESC NULLS LAST LIMIT 30",
                    (s,),
                )
                if rows:
                    payload = s_src.derive_sentiment("symbol", s, rows)
                    await asyncio.to_thread(_upsert_sentiment, "symbol", s, payload)
            for sid in data.SECTORS.keys():
                rows = await asyncio.to_thread(
                    db.query,
                    "SELECT sentiment FROM news WHERE sector = %s ORDER BY published_at DESC NULLS LAST LIMIT 60",
                    (sid,),
                )
                if rows:
                    payload = s_src.derive_sentiment("sector", sid, rows)
                    await asyncio.to_thread(_upsert_sentiment, "sector", sid, payload)
            log.info("sentiment cycle complete")
        except Exception as exc:  # noqa: BLE001
            log.warning("sentiment loop error: %s", exc)
        await asyncio.sleep(SENTIMENT_INTERVAL)


async def _snapshot_loop():
    """Persist a daily mark-to-market NAV/P&L point per active strategy.

    Runs on startup and then hourly. ``record_daily_snapshots`` skips weekends
    and is idempotent per trading day, so this loop survives restarts without
    duplicating points and converges to the day's close as quotes settle.
    """
    while True:
        try:
            res = await asyncio.to_thread(strategy.record_daily_snapshots)
            log.info("snapshot cycle: %s", res)
        except Exception as exc:  # noqa: BLE001
            log.warning("snapshot loop error: %s", exc)
        await asyncio.sleep(SNAPSHOT_INTERVAL)


async def _breadth_market_cap_loop():
    """Slowly round-robin a real market_cap onto mock breadth names.

    Picks the least-recently-refreshed breadth rows (``is_live = FALSE``,
    least-recently-refreshed first via NULLS FIRST) in small batches so every
    name's cap hint gets periodically corrected without promoting it to full live
    fundamentals and without any burst that could affect the request path."""
    await asyncio.sleep(BREADTH_STARTUP_DELAY)
    while True:
        try:
            rows = await asyncio.to_thread(
                db.query,
                """
                SELECT symbol FROM fundamentals
                 WHERE is_live = FALSE
                 ORDER BY mcap_refreshed_at ASC NULLS FIRST, symbol
                 LIMIT %s
                """,
                (BREADTH_BATCH,),
            )
            syms = [r["symbol"] for r in rows]
            for s in syms:  # serialized via the network semaphore; keep it gentle
                await _refresh_market_cap(s)
            if syms:
                log.info("breadth market-cap refresh (%d names)", len(syms))
        except Exception as exc:  # noqa: BLE001
            log.warning("breadth market-cap loop error: %s", exc)
        await asyncio.sleep(BREADTH_INTERVAL)


async def _ondemand_loop():
    while True:
        try:
            rows = await asyncio.to_thread(
                db.query, "SELECT symbol FROM universe WHERE pending = TRUE LIMIT 10"
            )
            for r in rows:
                sym = r["symbol"]
                log.info("on-demand fetch for %s", sym)
                await _ingest_prices(sym)
                await _ingest_fundamentals(sym)
                sector = await asyncio.to_thread(_sector_of, sym)
                await _ingest_news_for([sym], sector)
                await asyncio.to_thread(
                    db.execute,
                    "UPDATE universe SET pending = FALSE, updated_at = now() WHERE symbol = %s",
                    (sym,),
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("on-demand loop error: %s", exc)
        await asyncio.sleep(ONDEMAND_INTERVAL)


# ----------------------------- lifecycle -----------------------------
async def start() -> None:
    # Boot smoke checks (scripts/smoke_api.py) set this so the app can verify it
    # imports, boots and serves a request without kicking off the continuous live
    # ingestion loops (which make hundreds of network calls and, under some
    # process-sandboxed runners, spawn yfinance subprocesses that fail to exec).
    if os.environ.get("TERMINAL_SKIP_WORKER") == "1":
        log.info("data worker disabled (TERMINAL_SKIP_WORKER=1)")
        return
    if not db.db_available():
        log.warning("DATABASE_URL not set; data worker disabled, using mock data only")
        return
    try:
        await asyncio.to_thread(_seed_universe)
    except Exception as exc:  # noqa: BLE001
        log.warning("universe seeding failed: %s", exc)
    try:
        await asyncio.to_thread(_ensure_macro_schema)
    except Exception as exc:  # noqa: BLE001
        log.warning("macro schema ensure failed: %s", exc)
    _tasks.append(asyncio.create_task(_price_loop()))
    _tasks.append(asyncio.create_task(_macro_loop()))
    _tasks.append(asyncio.create_task(_fundamentals_loop()))
    _tasks.append(asyncio.create_task(_news_loop()))
    _tasks.append(asyncio.create_task(_sentiment_loop()))
    _tasks.append(asyncio.create_task(_breadth_market_cap_loop()))
    _tasks.append(asyncio.create_task(_ondemand_loop()))
    _tasks.append(asyncio.create_task(_snapshot_loop()))
    log.info("data worker started (%d loops)", len(_tasks))


async def stop() -> None:
    for t in _tasks:
        t.cancel()
    for t in _tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    _tasks.clear()
    pool = db.get_pool()
    if pool is not None:
        try:
            pool.close()
        except Exception:  # noqa: BLE001
            pass
