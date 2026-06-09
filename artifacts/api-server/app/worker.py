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
import json
import logging
import os
from typing import List, Optional

from . import data, db, orderbook_store, repo, strategy
from .sources import fundamentals as f_src
from .sources import holdings as h_src
from .sources import iex_deep
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
MACRO_INTERVAL = 120
ONDEMAND_INTERVAL = 15
# How often to check for queued order-book replay reconstructions. The job itself
# is very slow (streams a ~13 GB DEEP capture), so the poll is gentle.
ORDERBOOK_INTERVAL = 20
# Point-in-time backfill cadence: real OHLCV for delisted names + as-reported
# quarterly fundamentals. This history barely changes, so a long sleep is fine —
# it only needs to be present, not minute-fresh.
PIT_INTERVAL = 6 * 3600
# Daily mark cadence: re-check hourly. record_daily_snapshots is idempotent per
# trading day (one row per strategy per day), so an hourly pass simply keeps the
# day's NAV fresh and settles to the close once prices stop moving.
SNAPSHOT_INTERVAL = 3600
# How often to check for due scheduled rebalances. The check itself is cheap and
# per-strategy cadence is enforced in days by ``strategy.is_due``.
REBALANCE_INTERVAL = 3600

# ETF holdings refresh: fund compositions change slowly, so a gentle round-robin
# over the common ETF set keeps the holdings cache warm for instant panels and
# the reverse "which ETFs hold X" lookup. Deferred and small-batch so it never
# competes with the live price/fundamentals loops.
HOLDINGS_INTERVAL = 600
HOLDINGS_BATCH = 4
HOLDINGS_STARTUP_DELAY = 240
# Common, liquid ETFs whose top holdings power the holdings panel and seed the
# reverse-lookup index. Mirrors the benchmark/sector ETF set used elsewhere.
HOLDINGS_ETFS = [
    "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "RSP", "MDY",
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLC", "XLB", "XLRE", "XLU",
    "SMH", "SOXX", "CIBR", "XBI", "ITA", "ICLN", "ARKK", "IYT", "KIE", "XME",
    "EFA", "EEM",
]

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
        "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS earnings_eps_estimate DOUBLE PRECISION",
        "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS mcap_refreshed_at TIMESTAMPTZ",
        # Point-in-time universe lifecycle: listing/delisting dates + status so a
        # historical window can resolve to the names active then (incl. delisted).
        "ALTER TABLE universe ADD COLUMN IF NOT EXISTS listed_at DATE",
        "ALTER TABLE universe ADD COLUMN IF NOT EXISTS delisted_at DATE",
        "ALTER TABLE universe ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'",
    ):
        db.execute(ddl)

    # As-reported (point-in-time) fundamentals history, one row per fiscal period
    # with the date it became public. Kept separate from the single-snapshot
    # `fundamentals` table so a backtest can read the figures knowable at an as-of
    # date instead of today's restated numbers.
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS fundamentals_pit (
            symbol TEXT NOT NULL,
            period_end DATE NOT NULL,
            report_date DATE NOT NULL,
            revenue DOUBLE PRECISION,
            net_income DOUBLE PRECISION,
            net_margin DOUBLE PRECISION,
            eps DOUBLE PRECISION,
            report_estimated BOOLEAN NOT NULL DEFAULT FALSE,
            source TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (symbol, period_end)
        )
        """
    )

    # Real analyst ratings & price targets, one snapshot row per symbol. Kept in
    # its own table so the consensus, distribution and recent upgrades/downgrades
    # never collide with the single-snapshot `fundamentals` schema. ``covered``
    # records whether Yahoo actually carries analyst coverage so the panel can be
    # honest about uncovered names instead of fabricating targets.
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS analyst_ratings (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            covered BOOLEAN NOT NULL DEFAULT FALSE,
            consensus_key TEXT,
            recommendation_mean DOUBLE PRECISION,
            num_analysts INTEGER,
            strong_buy INTEGER,
            buy INTEGER,
            hold INTEGER,
            sell INTEGER,
            strong_sell INTEGER,
            target_mean DOUBLE PRECISION,
            target_high DOUBLE PRECISION,
            target_low DOUBLE PRECISION,
            target_median DOUBLE PRECISION,
            current_price DOUBLE PRECISION,
            changes JSONB,
            source TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # Dedicated macro quote table — kept separate from `fundamentals` so live
    # macro instruments never leak into equity screeners/heatmaps/all_symbols.
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_prices (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            price DOUBLE PRECISION,
            change_pct DOUBLE PRECISION,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # Real ETF constituents (top holdings) from the free Yahoo funds feed. Kept
    # in its own table — it indexes holding tickers that may not be in `universe`
    # (the feed supplies the name), and powers both the holdings panel and the
    # reverse "which ETFs hold X" lookup.
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS etf_holdings (
            etf TEXT NOT NULL,
            symbol TEXT NOT NULL,
            name TEXT,
            weight DOUBLE PRECISION,
            as_of DATE,
            source TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (etf, symbol)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS etf_holdings_symbol_idx ON etf_holdings (symbol)"
    )

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

    # Seed curated delisted names into `universe` ONLY (status='delisted', never
    # tracked, never into `fundamentals`) so they stay out of current screeners
    # but a point-in-time historical window can resolve to them. Listing/delisting
    # dates come from the curated set; real OHLCV is fetched later by _pit_loop.
    del_rows = [
        (sym, d["name"], d["sector"], d.get("exchange"), d["listed"], d["delisted"])
        for sym, d in data.DELISTED.items()
    ]
    db.execute_many(
        """
        INSERT INTO universe (symbol, name, sector, exchange, tracked, pending,
                              status, listed_at, delisted_at)
        VALUES (%s, %s, %s, %s, FALSE, FALSE, 'delisted', %s, %s)
        ON CONFLICT (symbol) DO UPDATE
          SET name = COALESCE(universe.name, EXCLUDED.name),
              sector = COALESCE(universe.sector, EXCLUDED.sector),
              exchange = COALESCE(universe.exchange, EXCLUDED.exchange),
              status = 'delisted',
              listed_at = COALESCE(universe.listed_at, EXCLUDED.listed_at),
              delisted_at = COALESCE(universe.delisted_at, EXCLUDED.delisted_at)
        """,
        del_rows,
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


def _upsert_macro_quote(key: str, q: dict) -> None:
    db.execute(
        """
        INSERT INTO macro_prices (symbol, name, price, change_pct, updated_at)
        VALUES (%s, %s, %s, %s, now())
        ON CONFLICT (symbol) DO UPDATE SET
          name = COALESCE(EXCLUDED.name, macro_prices.name),
          price = COALESCE(EXCLUDED.price, macro_prices.price),
          change_pct = COALESCE(EXCLUDED.change_pct, macro_prices.change_pct),
          updated_at = now()
        """,
        (key, q.get("name"), q.get("price"), q.get("changePct")),
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
                                  dividend_date, earnings_eps_estimate, updated_at)
        VALUES (%s, %s, %s, %s, %s, now())
        ON CONFLICT (symbol) DO UPDATE SET
          earnings_date = COALESCE(EXCLUDED.earnings_date, fundamentals.earnings_date),
          ex_dividend_date = COALESCE(EXCLUDED.ex_dividend_date, fundamentals.ex_dividend_date),
          dividend_date = COALESCE(EXCLUDED.dividend_date, fundamentals.dividend_date),
          earnings_eps_estimate = COALESCE(EXCLUDED.earnings_eps_estimate, fundamentals.earnings_eps_estimate),
          updated_at = now()
        """,
        (c.get("symbol"), c.get("earningsDate"), c.get("exDividendDate"),
         c.get("dividendDate"), c.get("earningsEpsEstimate")),
    )


def _upsert_analyst_ratings(d: dict) -> None:
    """Persist a real analyst ratings/price-target snapshot for one symbol.

    The whole snapshot is replaced on each refresh (analyst data is a current
    consensus, not an accumulating history), including ``covered`` so a name that
    loses coverage is honestly reflected. ``changes`` is the recent
    upgrades/downgrades list, stored as JSONB."""
    dist = d.get("distribution") or {}
    db.execute(
        """
        INSERT INTO analyst_ratings (symbol, name, covered, consensus_key,
            recommendation_mean, num_analysts, strong_buy, buy, hold, sell,
            strong_sell, target_mean, target_high, target_low, target_median,
            current_price, changes, source, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s, now())
        ON CONFLICT (symbol) DO UPDATE SET
          name = COALESCE(EXCLUDED.name, analyst_ratings.name),
          covered = EXCLUDED.covered,
          consensus_key = EXCLUDED.consensus_key,
          recommendation_mean = EXCLUDED.recommendation_mean,
          num_analysts = EXCLUDED.num_analysts,
          strong_buy = EXCLUDED.strong_buy,
          buy = EXCLUDED.buy,
          hold = EXCLUDED.hold,
          sell = EXCLUDED.sell,
          strong_sell = EXCLUDED.strong_sell,
          target_mean = EXCLUDED.target_mean,
          target_high = EXCLUDED.target_high,
          target_low = EXCLUDED.target_low,
          target_median = EXCLUDED.target_median,
          current_price = EXCLUDED.current_price,
          changes = EXCLUDED.changes,
          source = EXCLUDED.source,
          updated_at = now()
        """,
        (d.get("symbol"), d.get("name"), bool(d.get("covered")), d.get("consensusKey"),
         d.get("recommendationMean"), d.get("numAnalysts"),
         dist.get("strongBuy"), dist.get("buy"), dist.get("hold"), dist.get("sell"),
         dist.get("strongSell"), d.get("targetMean"), d.get("targetHigh"),
         d.get("targetLow"), d.get("targetMedian"), d.get("currentPrice"),
         json.dumps(d.get("changes") or []), d.get("source")),
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


def _update_industry(symbol: str, industry: str) -> None:
    """Fill the industry label for a single universe row, only when blank.

    Used by the one-time backfill. The ``IS NULL OR = ''`` guard makes the
    write idempotent and ensures we never clobber an industry that was already
    captured by a live fundamentals ingest."""
    db.execute(
        "UPDATE universe SET industry = %s, updated_at = now() "
        "WHERE symbol = %s AND (industry IS NULL OR industry = '')",
        (industry, symbol),
    )


def _update_listed_at(symbol: str, listed_at: str) -> None:
    """Record a symbol's best-effort listing date (from the chart's
    ``firstTradeDate``), only when not already set.

    The ``IS NULL`` guard makes this idempotent and keeps a curated delisted
    name's seeded listing date authoritative. It never touches ``delisted_at``
    or ``status`` — active names stay active."""
    db.execute(
        "UPDATE universe SET listed_at = %s, updated_at = now() "
        "WHERE symbol = %s AND listed_at IS NULL",
        (listed_at, symbol),
    )


def _upsert_pit_fundamentals(rows: list) -> None:
    """Persist as-reported quarterly fundamentals into ``fundamentals_pit``.

    One row per (symbol, period_end); idempotent upsert so re-fetching refreshes
    the same periods. These are deliberately kept out of the single-snapshot
    ``fundamentals`` table so they never leak into current screeners."""
    if not rows:
        return
    payload = [
        (r["symbol"], r["periodEnd"], r["reportDate"], r.get("revenue"),
         r.get("netIncome"), r.get("netMargin"), r.get("eps"),
         bool(r.get("reportEstimated")), r.get("source"))
        for r in rows
    ]
    db.execute_many(
        """
        INSERT INTO fundamentals_pit (symbol, period_end, report_date, revenue,
            net_income, net_margin, eps, report_estimated, source, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT (symbol, period_end) DO UPDATE SET
          report_date = EXCLUDED.report_date,
          revenue = EXCLUDED.revenue,
          net_income = EXCLUDED.net_income,
          net_margin = EXCLUDED.net_margin,
          eps = EXCLUDED.eps,
          report_estimated = EXCLUDED.report_estimated,
          source = EXCLUDED.source,
          updated_at = now()
        """,
        payload,
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
        quote = dict(res.get("quote") or {})
        if quote.get("listedAt"):
            await asyncio.to_thread(_update_listed_at, symbol, quote["listedAt"])
        if quote.get("price") is not None:
            quote["symbol"] = symbol
            await asyncio.to_thread(_upsert_quote, quote)
    except CircuitOpenError as exc:
        log.debug("price ingest skipped for %s: %s", symbol, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("price ingest failed for %s: %s", symbol, exc)


async def _ingest_macro_one(key: str, ysym: str) -> None:
    """Fetch one macro instrument and persist its quote + sparkline OHLCV.

    Stored under the internal macro key (e.g. ``SPX``) in a dedicated
    ``macro_prices`` table so equity screeners/heatmaps (which read
    ``fundamentals``) are never polluted, plus ``ohlcv`` for the sparkline."""
    try:
        res = await _net(p_src.fetch_price_history, ysym, "6mo", "1d")
        pts = res.get("points") or []
        if pts:
            await asyncio.to_thread(_upsert_ohlcv, key, pts)
        q = dict(res.get("quote") or {})
        # The 6mo chart's `chartPreviousClose` is the close ~6 months ago, so the
        # adapter's changePct is a multi-month move, not the 1-day change the macro
        # tiles label. Equities get corrected by the fundamentals loop; macro has
        # none, so recompute the true 1D move from the last two real daily closes.
        if len(pts) >= 2 and pts[-2].get("c"):
            base = pts[-2]["c"]
            ref = q.get("price") if q.get("price") is not None else pts[-1].get("c")
            if ref is not None and base:
                q["changePct"] = round((ref - base) / base * 100, 2)
        if q.get("price") is not None:
            await asyncio.to_thread(_upsert_macro_quote, key, q)
    except Exception as exc:  # noqa: BLE001
        log.warning("macro ingest failed for %s (%s): %s", key, ysym, exc)


async def _ingest_macro() -> None:
    items = list(data.MACRO_YAHOO.items())
    await asyncio.gather(*(_ingest_macro_one(k, y) for k, y in items))


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
    # Real analyst ratings & price targets — best-effort on the same slow cadence
    # so a throttle/missing-coverage never blocks the fundamentals snapshot.
    try:
        cons = await _net(f_src.fetch_analyst_consensus, ysym)
        cons["symbol"] = symbol
        await asyncio.to_thread(_upsert_analyst_ratings, cons)
    except CircuitOpenError as exc:
        log.debug("analyst ratings ingest skipped for %s: %s", symbol, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("analyst ratings ingest failed for %s: %s", symbol, exc)


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
        items = await _net(n_src.fetch_news, symbols, sector, 100)
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
        items = await _net(n_src.fetch_market_news, 100)
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
            await _ingest_macro()
            log.info("price cycle complete (%d symbols + %d macro)",
                     len(syms), len(data.MACRO_YAHOO))
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


async def _rebalance_loop():
    """Run the automated, cost-aware rebalance pipeline for due strategies.

    Each pass asks the strategy service which active books have hit their cadence
    (``strategy.is_due``) and rebalances them with the real square-root impact
    cost model, then refreshes their daily snapshot so the applied trades show up
    in the audited NAV series immediately. ``run_scheduled_rebalances`` skips
    weekends and isolates per-strategy failures, so this loop is safe to run
    hourly across restarts (cadence is enforced in days)."""
    while True:
        try:
            res = await asyncio.to_thread(strategy.run_scheduled_rebalances)
            if res.get("rebalanced"):
                log.info("rebalance cycle: %s", res)
                # Re-snapshot so the just-applied trades land in the audited curve.
                await asyncio.to_thread(strategy.record_daily_snapshots)
        except Exception as exc:  # noqa: BLE001
            log.warning("rebalance loop error: %s", exc)
        await asyncio.sleep(REBALANCE_INTERVAL)


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


async def _backfill_one_industry(symbol: str) -> bool:
    """Fetch fundamentals for one symbol and fill its industry if missing."""
    ysym = data.yahoo_symbol(symbol)
    try:
        d = await _net(f_src.fetch_fundamentals, ysym)
        industry = d.get("industry")
        if industry:
            await asyncio.to_thread(_update_industry, symbol, industry)
            return True
    except Exception as exc:  # noqa: BLE001
        log.warning("industry backfill failed for %s: %s", symbol, exc)
    return False


async def _backfill_industry() -> None:
    """One-time backfill of ``universe.industry`` for tracked symbols whose
    fundamentals were ingested before industry capture existed.

    Targets only the gap (tracked rows with a blank industry) and writes just
    the industry column via an idempotent guarded update, so it never produces
    duplicate or partial fundamentals writes and never overwrites an industry
    already captured live. Runs concurrently (bounded by the shared network
    semaphore) so the universe table reads complete without waiting for the
    slow fundamentals refresh cycle."""
    try:
        rows = await asyncio.to_thread(
            db.query,
            "SELECT symbol FROM universe "
            "WHERE tracked = TRUE AND (industry IS NULL OR industry = '') "
            "ORDER BY symbol",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("industry backfill query failed: %s", exc)
        return
    syms = [r["symbol"] for r in rows]
    if not syms:
        log.info("industry backfill: nothing to do")
        return
    log.info("industry backfill: %d tracked symbols missing industry", len(syms))
    results = await asyncio.gather(*(_backfill_one_industry(s) for s in syms))
    log.info("industry backfill complete: %d/%d filled", sum(results), len(syms))


async def _ingest_pit_fundamentals(symbol: str) -> None:
    """Fetch and persist as-reported quarterly fundamentals for one symbol."""
    ysym = data.yahoo_symbol(symbol)
    try:
        rows = await _net(f_src.fetch_fundamentals_history, ysym)
        for r in rows:
            r["symbol"] = symbol  # persist under internal base code
        if rows:
            await asyncio.to_thread(_upsert_pit_fundamentals, rows)
            log.info("pit fundamentals ingested for %s (%d periods)", symbol, len(rows))
    except CircuitOpenError as exc:
        log.debug("pit fundamentals skipped for %s: %s", symbol, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("pit fundamentals failed for %s: %s", symbol, exc)


async def _ingest_delisted_history(symbol: str) -> None:
    """Best-effort real OHLCV for a curated delisted name over its trading life.

    Many delisted tickers still return genuine daily history from the free chart
    endpoint. We fetch only the curated listed..delisted window and persist real
    closes so a point-in-time backtest can include the name with honest data. If
    the endpoint returns nothing, we persist nothing — the gap is surfaced by the
    data-quality view, never imputed with a mock series."""
    meta = data.get_delisted(symbol)
    if not meta:
        return
    start, end = meta.get("listed"), meta.get("delisted")
    if not start or not end:
        return
    try:
        closes = await _net(p_src.fetch_daily_closes, symbol, start, end)
        pts = [{"d": d, "c": c} for d, c in sorted((closes or {}).items())]
        if pts:
            await asyncio.to_thread(_upsert_ohlcv, symbol, pts)
            log.info("delisted history ingested for %s (%d bars)", symbol, len(pts))
        else:
            log.info("delisted history unavailable for %s (no free coverage)", symbol)
    except CircuitOpenError as exc:
        log.debug("delisted history skipped for %s: %s", symbol, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("delisted history failed for %s: %s", symbol, exc)


async def _pit_loop():
    """Slow, one-pass-then-idle loop that backfills point-in-time data:
    real OHLCV for curated delisted names, then as-reported quarterly
    fundamentals for the continuously-tracked core. Runs gently (serialized by
    the network semaphore) and then sleeps long, since this history rarely
    changes — it only needs to be present, not fresh-to-the-minute."""
    first = True
    while True:
        try:
            if first:
                for sym in data.delisted_symbols():
                    await _ingest_delisted_history(sym)
                first = False
            for sym in _tracked_symbols():
                await _ingest_pit_fundamentals(sym)
        except Exception as exc:  # noqa: BLE001
            log.warning("pit loop error: %s", exc)
        await asyncio.sleep(PIT_INTERVAL)


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


async def _orderbook_loop():
    """Reconstruct real IEX DEEP order-book replays for queued symbols.

    Drains ``pending`` jobs, resolves the latest published DEEP session, and
    reconstructs every queued symbol in a SINGLE streaming pass over that day's
    capture (the ~13 GB download is shared, so batching is essentially free).
    Symbols with no real IEX depth that day are marked ``unavailable`` so the
    panel stops promising a real replay; transient failures become ``error`` and
    are retried when the panel is re-opened."""
    while True:
        try:
            syms = await asyncio.to_thread(orderbook_store.pending_jobs, 8)
            if syms:
                sess = await asyncio.to_thread(iex_deep.latest_session)
                if not sess:
                    log.warning("no IEX DEEP session available; deferring %d job(s)", len(syms))
                else:
                    session_iso, link = sess
                    names: dict = {}
                    thresholds: dict = {}
                    for s in syms:
                        c = await asyncio.to_thread(repo.get_company, s)
                        names[s] = (c or {}).get("name") or s
                        avg_vol = (c or {}).get("volume") or 1_000_000
                        thresholds[s] = float(avg_vol) * 0.002
                        await asyncio.to_thread(
                            orderbook_store.mark_job, s, "running", session_iso, None
                        )
                    log.info("reconstructing IEX DEEP replay for %s (session %s)", syms, session_iso)
                    try:
                        results = await asyncio.to_thread(
                            iex_deep.reconstruct, set(syms), link, session_iso, names, thresholds
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.warning("IEX DEEP reconstruction failed: %s", exc)
                        for s in syms:
                            await asyncio.to_thread(
                                orderbook_store.mark_job, s, "error", session_iso, str(exc)[:200]
                            )
                        results = {}
                    for s in syms:
                        payload = results.get(s)
                        if payload:
                            await asyncio.to_thread(
                                orderbook_store.save_replay, s, session_iso, payload,
                                payload.get("source", "IEX DEEP (venue-only, T+1)"), session_iso,
                            )
                            await asyncio.to_thread(
                                orderbook_store.mark_job, s, "done", session_iso, None
                            )
                        elif (await asyncio.to_thread(orderbook_store.job_status, s)) == "running":
                            await asyncio.to_thread(
                                orderbook_store.mark_job, s, "unavailable", session_iso,
                                "no IEX DEEP depth for symbol on session",
                            )
        except Exception as exc:  # noqa: BLE001
            log.warning("order-book loop error: %s", exc)
        await asyncio.sleep(ORDERBOOK_INTERVAL)


async def _ingest_etf_holdings(etf: str) -> None:
    """Fetch + persist one ETF's real top holdings (best-effort)."""
    try:
        res = await _net(h_src.fetch_etf_holdings, etf)
        if res and res.get("holdings"):
            await asyncio.to_thread(
                repo.upsert_etf_holdings, etf, res["holdings"],
                res.get("asOf"), res.get("source", "live"),
            )
    except CircuitOpenError:
        pass  # source cooling down; try again next sweep
    except Exception as exc:  # noqa: BLE001
        log.debug("holdings ingest skipped for %s: %s", etf, exc)


async def _holdings_loop():
    """Round-robin the common ETF set, keeping the holdings cache warm.

    A small batch per tick walks through ``HOLDINGS_ETFS`` so a full sweep
    completes over time without bursting the Yahoo funds feed. Deferred at start
    so it never piles onto cold-start ingestion."""
    await asyncio.sleep(HOLDINGS_STARTUP_DELAY)
    idx = 0
    while True:
        try:
            batch = HOLDINGS_ETFS[idx:idx + HOLDINGS_BATCH]
            if not batch:
                idx = 0
                batch = HOLDINGS_ETFS[idx:idx + HOLDINGS_BATCH]
            for etf in batch:
                await _ingest_etf_holdings(etf)
            idx = (idx + HOLDINGS_BATCH) % max(1, len(HOLDINGS_ETFS))
        except Exception as exc:  # noqa: BLE001
            log.warning("holdings loop error: %s", exc)
        await asyncio.sleep(HOLDINGS_INTERVAL)


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
    # One-time backfill of industry for symbols ingested before industry
    # capture existed; runs once concurrently and exits (not a loop).
    _tasks.append(asyncio.create_task(_backfill_industry()))
    _tasks.append(asyncio.create_task(_price_loop()))
    _tasks.append(asyncio.create_task(_fundamentals_loop()))
    _tasks.append(asyncio.create_task(_news_loop()))
    _tasks.append(asyncio.create_task(_sentiment_loop()))
    _tasks.append(asyncio.create_task(_breadth_market_cap_loop()))
    _tasks.append(asyncio.create_task(_pit_loop()))
    _tasks.append(asyncio.create_task(_ondemand_loop()))
    _tasks.append(asyncio.create_task(_orderbook_loop()))
    _tasks.append(asyncio.create_task(_snapshot_loop()))
    _tasks.append(asyncio.create_task(_rebalance_loop()))
    _tasks.append(asyncio.create_task(_holdings_loop()))
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
