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
from typing import List, Optional

from . import data, db
from .sources import fundamentals as f_src
from .sources import news as n_src
from .sources import prices as p_src
from .sources import sentiment as s_src

log = logging.getLogger("terminal.worker")

# Cadences (seconds). Prices fast; fundamentals/news/sentiment slower.
PRICE_INTERVAL = 90
FUNDAMENTALS_INTERVAL = 900
NEWS_INTERVAL = 300
SENTIMENT_INTERVAL = 600
ONDEMAND_INTERVAL = 15

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
        "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS is_live BOOLEAN NOT NULL DEFAULT FALSE",
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
            pe_ratio, volume, revenue, net_margin, eps, dividend_yield, beta,
            week52_high, week52_low, description, is_live, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, TRUE, now())
        ON CONFLICT (symbol) DO UPDATE SET
          name = COALESCE(EXCLUDED.name, fundamentals.name),
          price = COALESCE(EXCLUDED.price, fundamentals.price),
          change_pct = COALESCE(EXCLUDED.change_pct, fundamentals.change_pct),
          market_cap = COALESCE(EXCLUDED.market_cap, fundamentals.market_cap),
          pe_ratio = EXCLUDED.pe_ratio,
          volume = COALESCE(EXCLUDED.volume, fundamentals.volume),
          revenue = COALESCE(EXCLUDED.revenue, fundamentals.revenue),
          net_margin = COALESCE(EXCLUDED.net_margin, fundamentals.net_margin),
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
         d.get("revenue"), d.get("netMargin"), d.get("eps"), d.get("dividendYield"),
         d.get("beta"), d.get("week52High"), d.get("week52Low"), d.get("description")),
    )
    if d.get("sector"):
        db.execute(
            "UPDATE universe SET sector = %s, name = COALESCE(name, %s), "
            "industry = COALESCE(%s, industry), updated_at = now() WHERE symbol = %s",
            (d["sector"], d.get("name"), d.get("industry"), d.get("symbol")),
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
        res = await _net(p_src.fetch_price_history, ysym, "6mo", "1d")
        if res.get("points"):
            await asyncio.to_thread(_upsert_ohlcv, symbol, res["points"])
        if res.get("quote", {}).get("price") is not None:
            quote = dict(res["quote"])
            quote["symbol"] = symbol
            await asyncio.to_thread(_upsert_quote, quote)
    except Exception as exc:  # noqa: BLE001
        log.warning("price ingest failed for %s: %s", symbol, exc)


async def _ingest_fundamentals(symbol: str) -> None:
    ysym = data.yahoo_symbol(symbol)
    try:
        d = await _net(f_src.fetch_fundamentals, ysym)
        d["symbol"] = symbol
        await asyncio.to_thread(_upsert_fundamentals, d)
    except Exception as exc:  # noqa: BLE001
        log.warning("fundamentals ingest failed for %s: %s", symbol, exc)


async def _ingest_news_for(symbols: List[str], sector: Optional[str]) -> None:
    if not symbols:
        return
    try:
        items = await _net(n_src.fetch_news, symbols, sector, 25)
        if items:
            await asyncio.to_thread(_upsert_news, items)
    except Exception as exc:  # noqa: BLE001
        log.warning("news ingest failed for %s: %s", symbols, exc)


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
            for sid in data.SECTORS.keys():
                rows = await asyncio.to_thread(
                    db.query,
                    "SELECT symbol FROM universe WHERE sector = %s AND tracked = TRUE",
                    (sid,),
                )
                syms = [r["symbol"] for r in rows]
                for i in range(0, len(syms), 8):
                    await _ingest_news_for(syms[i:i + 8], sid)
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
    if not db.db_available():
        log.warning("DATABASE_URL not set; data worker disabled, using mock data only")
        return
    try:
        await asyncio.to_thread(_seed_universe)
    except Exception as exc:  # noqa: BLE001
        log.warning("universe seeding failed: %s", exc)
    _tasks.append(asyncio.create_task(_price_loop()))
    _tasks.append(asyncio.create_task(_fundamentals_loop()))
    _tasks.append(asyncio.create_task(_news_loop()))
    _tasks.append(asyncio.create_task(_sentiment_loop()))
    _tasks.append(asyncio.create_task(_ondemand_loop()))
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
