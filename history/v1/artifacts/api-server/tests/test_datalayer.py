"""Unit tests for the live-data layer (repo.py) and its mock fallback (data.py),
plus the source adapters that parse free Yahoo/Google payloads (sources/*).

Runnable two ways:
    python artifacts/api-server/tests/test_datalayer.py   # standalone
    pytest artifacts/api-server/tests/test_datalayer.py    # if pytest installed

repo.py is the contract between the DB and the 8 panel skills. Its central
guarantee is "no empty panels": every accessor returns real (live) data when the
DB is populated and falls back to the deterministic curated mock set when the DB
is unavailable or has no rows. These tests pin that guarantee, the output
schemas (which the panels read), and the asOf/source freshness fields for both
the live and mock paths — without touching a real database. They also exercise
the source adapters against captured sample Yahoo/Google payloads so parsing is
verified with no network access.
"""
from __future__ import annotations

import contextlib
import os
import sys
from datetime import date, datetime, timezone

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

import feedparser  # noqa: E402

from datetime import timedelta  # noqa: E402

from app import data, db, repo, skills  # noqa: E402
from app.sources import fundamentals, news, prices, sectors, sentiment  # noqa: E402


# ============================================================================
# DB stubbing helpers
# ============================================================================
def _boom(*_a, **_k):
    raise RuntimeError("db down")


@contextlib.contextmanager
def fake_db(available=True, query=None, query_one=None, execute=None):
    """Swap the db module accessors so repo runs without a real Postgres.

    With ``available=False`` the repository must take its mock fallback path and
    never call the query helpers. With ``available=True`` the supplied ``query``/
    ``query_one`` callables drive the "live" path; any unspecified accessor
    defaults to raising so an unexpected call is caught by a test rather than
    silently hitting a real DB.
    """
    orig = {k: getattr(db, k) for k in
            ("db_available", "query", "query_one", "execute", "execute_many")}
    db.db_available = lambda: available
    db.query = query or _boom
    db.query_one = query_one or _boom
    db.execute = execute or (lambda *a, **k: None)
    db.execute_many = lambda *a, **k: None
    try:
        yield
    finally:
        for k, v in orig.items():
            setattr(db, k, v)


def _company_row(symbol="NVDA", price=121.4, is_live=True,
                 updated_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)):
    return {
        "symbol": symbol, "name": "NVIDIA Corp.", "sector": "semiconductors",
        "country": "United States", "exchange": "NASDAQ",
        "price": price, "change_pct": 2.34, "market_cap": 2.98e12,
        "pe_ratio": 54.2, "volume": 312_000_000, "revenue": 96.3e9,
        "net_margin": 55.0, "eps": 2.24, "dividend_yield": 0.03, "beta": 1.68,
        "week52_high": 140.76, "week52_low": 75.61,
        "description": "GPUs for AI.", "is_live": is_live, "updated_at": updated_at,
    }


def _ohlcv_rows(n=10, with_updated=False):
    base = date(2026, 1, 1)
    from datetime import timedelta
    rows = []
    for i in range(n):
        r = {"d": base + timedelta(days=i), "o": 100.0 + i, "h": 101.0 + i,
             "l": 99.0 + i, "c": 100.5 + i, "v": 1_000_000 + i}
        if with_updated:
            r["updated_at"] = datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc)
        rows.append(r)
    return rows


# Business keys every company record must expose, live or mock.
_COMPANY_KEYS = {
    "symbol", "name", "sector", "price", "changePct", "marketCap", "peRatio",
    "volume", "revenue", "netMargin", "eps", "dividendYield", "beta",
    "week52High", "week52Low", "description", "country", "exchange",
    "_asOf", "_source",
}


# ============================================================================
# repo.get_company — live vs mock
# ============================================================================
def test_get_company_live_sets_schema_and_freshness():
    with fake_db(query_one=lambda *a, **k: _company_row()):
        c = repo.get_company("nvda")
    assert c is not None
    assert set(c.keys()) == _COMPANY_KEYS
    assert c["symbol"] == "NVDA"
    assert c["price"] == 121.4
    assert c["_source"] == "live"
    assert c["_asOf"] == "2026-06-01T12:00:00+00:00"


def test_get_company_live_not_live_flag_marks_mock_source():
    # A row that exists but is_live=False is curated breadth, not real data.
    with fake_db(query_one=lambda *a, **k: _company_row(is_live=False)):
        c = repo.get_company("NVDA")
    assert c["_source"] == "mock"


def test_get_company_falls_back_to_mock_when_db_unavailable():
    with fake_db(available=False):
        c = repo.get_company("NVDA")
    assert c is not None
    assert c["_source"] == "mock"
    assert c["_asOf"] is None
    # Schema must match the live path exactly so panels read either identically.
    assert set(c.keys()) == _COMPANY_KEYS
    # Values come straight from the curated dataset.
    assert c["symbol"] == "NVDA"
    assert c["price"] == data.COMPANIES["NVDA"]["price"]


def test_get_company_falls_back_to_mock_on_db_error():
    # db_available is True but every query raises -> must still degrade to mock.
    with fake_db(available=True, query=_boom, query_one=_boom):
        c = repo.get_company("NVDA")
    assert c["_source"] == "mock"


def test_get_company_unknown_symbol_returns_none():
    with fake_db(available=False):
        assert repo.get_company("ZZZZ9") is None


def test_get_company_live_and_mock_have_identical_schema():
    with fake_db(query_one=lambda *a, **k: _company_row()):
        live = repo.get_company("NVDA")
    with fake_db(available=False):
        mock = repo.get_company("NVDA")
    assert set(live.keys()) == set(mock.keys())


# ============================================================================
# repo.price_series / price_series_meta — live vs mock
# ============================================================================
_PRICE_POINT_KEYS = {"t", "o", "h", "l", "c", "v"}


def test_price_series_live_from_db():
    with fake_db(query=lambda *a, **k: _ohlcv_rows(12)):
        pts = repo.price_series("NVDA", days=12)
    assert len(pts) == 12
    assert set(pts[0].keys()) == _PRICE_POINT_KEYS
    assert pts[0]["t"] == "2026-01-01"
    assert pts[0]["c"] == 100.5


def test_price_series_falls_back_when_too_few_rows():
    # Fewer than 2 DB rows is treated as no coverage -> deterministic mock series.
    with fake_db(query=lambda *a, **k: _ohlcv_rows(1)):
        pts = repo.price_series("NVDA", days=30)
    assert len(pts) == 30  # mock series honors the requested length
    assert set(pts[0].keys()) == _PRICE_POINT_KEYS


def test_price_series_falls_back_when_db_unavailable():
    with fake_db(available=False):
        pts = repo.price_series("NVDA", days=20)
    assert len(pts) == 20
    assert pts == data.price_series("NVDA", days=20)


def test_price_series_meta_live_reports_source_and_asof():
    with fake_db(query=lambda *a, **k: _ohlcv_rows(8, with_updated=True)):
        meta = repo.price_series_meta("NVDA", days=8)
    assert set(meta.keys()) == {"points", "source", "asOf"}
    assert meta["source"] == "live"
    assert meta["asOf"] == "2026-01-10T00:00:00+00:00"
    assert len(meta["points"]) == 8


def test_price_series_meta_mock_when_db_unavailable():
    with fake_db(available=False):
        meta = repo.price_series_meta("NVDA", days=8)
    assert set(meta.keys()) == {"points", "source", "asOf"}
    assert meta["source"] == "mock"
    assert meta["asOf"] is None
    assert meta["points"]


def test_price_series_meta_mock_on_db_error():
    with fake_db(available=True, query=_boom):
        meta = repo.price_series_meta("NVDA", days=8)
    assert meta["source"] == "mock"


# ============================================================================
# repo.news_for — live vs mock
# ============================================================================
_NEWS_KEYS = {"id", "headline", "source", "summary", "url", "publishedAt",
              "sentiment", "tickers"}


def _news_db_rows():
    return [{
        "id": "news-abc", "headline": "NVIDIA surges on AI demand",
        "source": "Yahoo Finance", "summary": "Strong quarter.",
        "url": "https://example.com/a",
        "published_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "fetched_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "sentiment": "positive", "tickers": ["NVDA"],
    }]


def test_news_for_live_from_db():
    with fake_db(query=lambda *a, **k: _news_db_rows()):
        items = repo.news_for("symbol", "NVDA", limit=10)
    assert items
    assert set(items[0].keys()) == _NEWS_KEYS
    assert items[0]["headline"] == "NVIDIA surges on AI demand"
    assert items[0]["tickers"] == ["NVDA"]


def test_news_for_falls_back_to_mock_when_db_unavailable():
    with fake_db(available=False):
        items = repo.news_for("sector", "semiconductors", limit=5)
    assert items
    assert set(items[0].keys()) == _NEWS_KEYS


def test_news_for_falls_back_to_mock_on_db_error():
    with fake_db(available=True, query=_boom, query_one=_boom):
        items = repo.news_for("topic", "earnings", limit=5)
    assert items  # curated mock topic search still yields headlines


# ============================================================================
# repo sector / universe accessors — live vs mock
# ============================================================================
def test_list_sectors_live_uses_db_counts():
    with fake_db(query=lambda *a, **k: [{"sector": "semiconductors", "n": 999}]):
        out = repo.list_sectors()
    by_id = {s["id"]: s for s in out}
    assert by_id["semiconductors"]["tickerCount"] == 999
    # Sectors without a DB count fall back to a mock count (never zero/missing).
    assert all("tickerCount" in s and "name" in s for s in out)


def test_list_sectors_mock_when_db_unavailable():
    with fake_db(available=False):
        out = repo.list_sectors()
    assert out == data.list_sectors()


def test_symbols_in_sector_live_then_mock():
    with fake_db(query=lambda *a, **k: [{"symbol": "AAA"}, {"symbol": "BBB"}]):
        assert repo.symbols_in_sector("semiconductors") == ["AAA", "BBB"]
    with fake_db(available=False):
        assert repo.symbols_in_sector("semiconductors") == \
            data.symbols_in_sector("semiconductors")


def test_symbols_in_sector_empty_db_falls_back():
    # An empty DB result is treated as no coverage -> mock breadth.
    with fake_db(query=lambda *a, **k: []):
        out = repo.symbols_in_sector("semiconductors")
    assert out == data.symbols_in_sector("semiconductors")


def test_all_symbols_live_then_mock():
    with fake_db(query=lambda *a, **k: [{"symbol": "AAA"}, {"symbol": "BBB"}]):
        assert repo.all_symbols() == ["AAA", "BBB"]
    with fake_db(available=False):
        assert repo.all_symbols() == data.all_symbols()


def test_resolve_sector_delegates_to_curated_taxonomy():
    assert repo.resolve_sector("semiconductors") == "semiconductors"
    assert repo.resolve_sector("Semiconductors") == "semiconductors"
    assert repo.resolve_sector("") is None
    assert repo.resolve_sector("totally-not-a-sector-xyz") is None


# ============================================================================
# repo.get_sentiment — live only (no mock fabrication)
# ============================================================================
def test_get_sentiment_live_from_db():
    row = {
        "overall": 0.3, "label": "bullish",
        "sources": [{"channel": "Reddit", "score": 0.4, "volume": 1200, "change": 5.0}],
        "trend": [{"t": "2026-06-01", "score": 0.3}],
        "updated_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
    }
    with fake_db(query_one=lambda *a, **k: row):
        s = repo.get_sentiment("symbol", "NVDA")
    assert s is not None
    assert s["overall"] == 0.3
    assert s["label"] == "bullish"
    assert s["sources"] and s["trend"]
    assert s["_asOf"] == "2026-06-01T00:00:00+00:00"


def test_get_sentiment_none_when_db_unavailable():
    # Sentiment is never fabricated: no DB -> None (panel hides the block).
    with fake_db(available=False):
        assert repo.get_sentiment("symbol", "NVDA") is None


def test_get_sentiment_none_on_db_error():
    with fake_db(available=True, query_one=_boom):
        assert repo.get_sentiment("symbol", "NVDA") is None


# ============================================================================
# repo freshness helpers
# ============================================================================
def test_as_of_and_source_of_helpers():
    live = {"_asOf": "2026-06-01T00:00:00+00:00", "_source": "live"}
    older = {"_asOf": "2026-05-01T00:00:00+00:00", "_source": "live"}
    mock = {"_asOf": None, "_source": "mock"}
    assert repo.as_of(older, live, mock) == "2026-06-01T00:00:00+00:00"
    assert repo.as_of(mock) is None
    assert repo.source_of(mock, live) == "live"
    assert repo.source_of(mock, mock) == "mock"


# ============================================================================
# Earnings calendar builder — real dates, honest coverage, source semantics
# ============================================================================
@contextlib.contextmanager
def _fake_calendar_snapshots(snapshots):
    """Drive ``build_earnings_calendar`` from controlled company snapshots.

    Patches symbol resolution and the bulk repository read so the builder runs
    with no DB, exercising the real date/coverage/source logic in
    ``data.earnings_calendar`` + ``build_earnings_calendar``.
    """
    bulk = {s.upper(): dict(snap, symbol=s.upper()) for s, snap in snapshots.items()}
    orig_get = data.get_company
    orig_bulk = repo.companies_bulk
    data.get_company = lambda s: {"symbol": str(s).upper()}
    repo.companies_bulk = lambda syms: {s: bulk[s] for s in syms if s in bulk}
    try:
        yield
    finally:
        data.get_company = orig_get
        repo.companies_bulk = orig_bulk


def test_earnings_calendar_live_with_rows_and_eps():
    soon = (date.today() + timedelta(days=5)).isoformat()
    with _fake_calendar_snapshots({
        "AMD": {"earningsDate": soon, "earningsEpsEstimate": 1.605,
                "_asOf": "2026-06-09T00:00:00+00:00", "_source": "live"},
    }):
        res = skills.build_earnings_calendar({"symbols": ["AMD"]})
    assert res["source"] == "live"
    assert res["asOf"] == "2026-06-09T00:00:00+00:00"
    assert res["count"] == 1
    assert res["rows"][0]["epsEstimate"] == 1.6  # rounded, not fabricated
    assert res["rows"][0]["timing"] == "unknown"  # free feed is date-only
    assert res["uncoveredCount"] == 0


def test_earnings_calendar_live_when_real_date_outside_horizon():
    """Regression: real dates beyond the window must still report source=live.

    The fetch succeeded — the panel just has no rows in this window — so it must
    NOT render the "feed unavailable" empty state.
    """
    far = (date.today() + timedelta(days=100)).isoformat()
    with _fake_calendar_snapshots({
        "NVDA": {"earningsDate": far, "earningsEpsEstimate": None,
                 "_asOf": "2026-06-09T00:00:00+00:00", "_source": "live"},
    }):
        res = skills.build_earnings_calendar({"symbols": ["NVDA"], "days": 7})
    assert res["source"] == "live"  # not "unavailable"
    assert res["asOf"] == "2026-06-09T00:00:00+00:00"
    assert res["count"] == 0          # nothing inside the 7-day window
    assert res["uncoveredCount"] == 0  # a known future date is still covered


def test_earnings_calendar_unavailable_when_no_real_dates():
    with _fake_calendar_snapshots({
        "MSFT": {"earningsDate": None, "earningsEpsEstimate": None,
                 "_asOf": None, "_source": "mock"},
    }):
        res = skills.build_earnings_calendar({"symbols": ["MSFT"]})
    assert res["source"] == "unavailable"
    assert res["asOf"] is None
    assert res["count"] == 0
    assert res["uncoveredCount"] == 1  # flagged honestly, not fabricated


def test_earnings_calendar_stale_date_is_uncovered_but_source_live():
    """A past-only date is honestly uncovered, yet the feed clearly worked."""
    past = (date.today() - timedelta(days=30)).isoformat()
    with _fake_calendar_snapshots({
        "INTC": {"earningsDate": past, "earningsEpsEstimate": 0.4,
                 "_asOf": "2026-06-09T00:00:00+00:00", "_source": "live"},
    }):
        res = skills.build_earnings_calendar({"symbols": ["INTC"]})
    assert res["source"] == "live"
    assert res["count"] == 0
    assert res["uncoveredCount"] == 1


# ============================================================================
# Source adapters — captured payloads, no network
# ============================================================================
class _Resp:
    def __init__(self, *, json_payload=None, content=None):
        self._json = json_payload
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


@contextlib.contextmanager
def fake_httpx(module, resp, capture=None):
    """Replace ``module.httpx.Client`` with a stub that returns ``resp``.

    ``capture`` (if given) records the constructor kwargs and the get() url/params
    so tests can assert request shaping (e.g. period1/period2 windows, redirects).
    """
    cap = capture if capture is not None else {}

    class _Client:
        def __init__(self, *a, **k):
            cap["init"] = k

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            cap["url"] = url
            cap["params"] = params
            return resp

    orig = module.httpx.Client
    module.httpx.Client = _Client
    try:
        yield cap
    finally:
        module.httpx.Client = orig


def _chart_payload(closes, *, opens=None, highs=None, lows=None, vols=None,
                   start_ts=1_700_000_000, step=86400, meta=None):
    n = len(closes)
    quote = {
        "open": opens if opens is not None else closes,
        "high": highs if highs is not None else closes,
        "low": lows if lows is not None else closes,
        "close": closes,
        "volume": vols if vols is not None else [1_000 + i for i in range(n)],
    }
    return {"chart": {"result": [{
        "meta": meta or {},
        "timestamp": [start_ts + i * step for i in range(n)],
        "indicators": {"quote": [quote]},
    }], "error": None}}


# --------------------------- prices adapter ---------------------------
def test_fetch_price_history_parses_points_and_quote():
    meta = {
        "symbol": "NVDA", "longName": "NVIDIA Corp.",
        "regularMarketPrice": 110.0, "chartPreviousClose": 100.0,
        "regularMarketVolume": 5_000_000,
        "fiftyTwoWeekHigh": 140.0, "fiftyTwoWeekLow": 70.0,
        "regularMarketTime": 1_700_000_000,
    }
    payload = _chart_payload([100.0, 105.0, 110.0], meta=meta)
    with fake_httpx(prices, _Resp(json_payload=payload)):
        out = prices.fetch_price_history("nvda", range_="6mo", interval="1d")
    assert len(out["points"]) == 3
    assert set(out["points"][0].keys()) == {"d", "o", "h", "l", "c", "v"}
    assert out["points"][0]["d"] == "2023-11-14"  # epoch 1_700_000_000 UTC date
    q = out["quote"]
    assert q["symbol"] == "NVDA"
    assert q["price"] == 110.0
    # changePct derived from price vs chartPreviousClose: (110-100)/100 = 10%.
    assert q["changePct"] == 10.0
    assert q["week52High"] == 140.0
    assert q["asOf"] == "2023-11-14T22:13:20+00:00"


def test_fetch_price_history_skips_null_closes():
    payload = _chart_payload([100.0, None, 102.0])
    with fake_httpx(prices, _Resp(json_payload=payload)):
        out = prices.fetch_price_history("X")
    # The bar with a null close is dropped, never imputed.
    assert len(out["points"]) == 2
    assert [p["c"] for p in out["points"]] == [100.0, 102.0]


def test_fetch_price_history_raises_on_empty_result():
    raised = False
    with fake_httpx(prices, _Resp(json_payload={"chart": {"result": []}})):
        try:
            prices.fetch_price_history("X")
        except ValueError:
            raised = True
    assert raised


def test_fetch_daily_closes_returns_date_keyed_closes():
    payload = _chart_payload([10.0, None, 12.0], start_ts=1_700_000_000)
    with fake_httpx(prices, _Resp(json_payload=payload), {}) as cap:
        out = prices.fetch_daily_closes("X", "2023-11-14", "2023-11-16")
    # Null close is omitted (sparse coverage is honest, never filled).
    assert out == {"2023-11-14": 10.0, "2023-11-16": 12.0}
    # The window is fetched via explicit period1/period2 epochs, p1 < p2.
    assert "period1" in cap["params"] and "period2" in cap["params"]
    assert cap["params"]["period1"] < cap["params"]["period2"]


def test_fetch_daily_closes_empty_result_is_no_coverage():
    with fake_httpx(prices, _Resp(json_payload={"chart": {"result": []}})):
        assert prices.fetch_daily_closes("X", "2023-01-01", "2023-01-05") == {}


def test_fetch_intraday_rejects_non_intraday_resolution():
    raised = False
    try:
        prices.fetch_intraday("X", interval="1d")
    except prices.IntradayUnavailable:
        raised = True
    assert raised


def test_fetch_intraday_rejects_out_of_limit_window():
    raised = False
    try:
        # 1m bars are only served up to ~7d; a 1y window must be refused.
        prices.fetch_intraday("X", interval="1m", range_="1y")
    except prices.IntradayUnavailable:
        raised = True
    assert raised


def test_fetch_intraday_parses_and_uses_range_token():
    meta = {"regularMarketPrice": 50.0, "currency": "USD", "longName": "X Co",
            "regularMarketTime": 1_700_000_000}
    payload = _chart_payload([50.0, 51.0], step=300, meta=meta)
    with fake_httpx(prices, _Resp(json_payload=payload), {}) as cap:
        out = prices.fetch_intraday("X", interval="5m", range_="5d")
    assert out["interval"] == "5m"
    assert out["range"] == "5d"
    assert out["currency"] == "USD"
    assert len(out["points"]) == 2
    assert set(out["points"][0].keys()) == {"t", "o", "h", "l", "c", "v"}
    # A plain range token goes through `range`, not period epochs.
    assert cap["params"].get("range") == "5d"
    assert "period1" not in cap["params"]


def test_fetch_intraday_custom_days_uses_period_epochs():
    meta = {"regularMarketPrice": 50.0, "currency": "USD"}
    payload = _chart_payload([50.0, 51.0], step=300, meta=meta)
    with fake_httpx(prices, _Resp(json_payload=payload), {}) as cap:
        prices.fetch_intraday("X", interval="1m", range_="7d")
    # 7d has no Yahoo range token -> must be fetched via period1/period2.
    assert "range" not in cap["params"]
    assert cap["params"]["period1"] < cap["params"]["period2"]


def test_fetch_intraday_raises_when_no_usable_bars():
    payload = _chart_payload([None, None], step=300, meta={"regularMarketPrice": 1.0})
    raised = False
    with fake_httpx(prices, _Resp(json_payload=payload)):
        try:
            prices.fetch_intraday("X", interval="5m", range_="1d")
        except prices.IntradayUnavailable:
            raised = True
    assert raised


# --------------------------- news adapter ---------------------------
_YAHOO_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Yahoo Finance</title>
<item>
  <title>NVIDIA beats earnings and surges to record high</title>
  <link>https://finance.yahoo.com/news/nvidia-beats-123.html</link>
  <description>NVDA posts strong growth and a buyback.</description>
  <pubDate>Mon, 01 Jun 2026 12:00:00 GMT</pubDate>
  <category>NVDA</category>
  <category>AMD</category>
</item>
<item>
  <title>Chip sector faces lawsuit and probe over pricing</title>
  <link>https://finance.yahoo.com/news/chip-probe-456.html</link>
  <description>Regulators warn of concerns.</description>
  <pubDate>Sun, 31 May 2026 09:30:00 GMT</pubDate>
</item>
</channel></rss>"""

_GOOGLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Google News</title>
<item>
  <title>Markets tumble on rate fears - Reuters</title>
  <link>https://news.google.com/articles/abc123</link>
  <description>Stocks decline.</description>
  <pubDate>Mon, 01 Jun 2026 08:00:00 GMT</pubDate>
  <source url="https://www.reuters.com">Reuters</source>
</item>
</channel></rss>"""


def test_fetch_news_normalizes_yahoo_rss():
    resp = _Resp(content=_YAHOO_RSS.encode())
    with fake_httpx(news, resp, {}) as cap:
        items = news.fetch_news(["NVDA"], sector="semiconductors", limit=10)
    assert len(items) == 2
    first = items[0]
    assert set(first.keys()) == {
        "id", "headline", "source", "summary", "url", "publishedAt",
        "sentiment", "tickers", "sector",
    }
    assert first["headline"] == "NVIDIA beats earnings and surges to record high"
    # Tickers come from <category> tags on the entry.
    assert first["tickers"] == ["NVDA", "AMD"]
    # Positive keywords ("beats", "surges", "record") -> positive sentiment.
    assert first["sentiment"] == "positive"
    assert first["publishedAt"] == "2026-06-01T12:00:00+00:00"
    assert first["id"].startswith("news-")
    assert first["sector"] == "semiconductors"
    # The second item has no tags -> falls back to the requested symbols.
    assert items[1]["tickers"] == ["NVDA"]
    assert items[1]["sentiment"] == "negative"  # lawsuit / probe / warn / concerns


def test_fetch_news_empty_symbols_returns_empty():
    assert news.fetch_news([], limit=5) == []


def test_fetch_topic_news_strips_publisher_and_uses_source():
    resp = _Resp(content=_GOOGLE_RSS.encode())
    with fake_httpx(news, resp, {}) as cap:
        items = news.fetch_topic_news("rates", limit=5)
    assert len(items) == 1
    it = items[0]
    # Publisher suffix removed from the headline...
    assert it["headline"] == "Markets tumble on rate fears"
    # ...and lifted into source from <source title>.
    assert it["source"] == "Reuters"
    # Google News feeds must follow redirects or come back empty.
    assert cap["init"].get("follow_redirects") is True


def test_news_dedupe_collapses_by_url_and_title():
    items = [
        {"headline": "A big story", "url": "https://x.com/a?utm=1"},
        {"headline": "A BIG story!", "url": "https://y.com/b"},   # dup title
        {"headline": "Different", "url": "https://x.com/a"},      # dup url
        {"headline": "Another", "url": "https://z.com/c"},
    ]
    out = news.dedupe(items)
    heads = [i["headline"] for i in out]
    assert heads == ["A big story", "Another"]


def test_news_strip_publisher_suffix_keeps_plain_titles():
    assert news._strip_publisher_suffix("No suffix here") == "No suffix here"
    assert news._strip_publisher_suffix("Title - CNBC") == "Title"


def test_news_entry_tickers_filters_non_symbols():
    entry = {"tags": [{"term": "NVDA"}, {"term": "toolongsymbol"},
                      {"term": "123"}, {"term": "amd"}]}
    assert news._entry_tickers(entry, []) == ["NVDA", "AMD"]


def test_news_parse_date_handles_garbage():
    assert news._parse_date(None) is None
    assert news._parse_date("not a date") is None
    assert news._parse_date("Mon, 01 Jun 2026 00:00:00 GMT") == \
        "2026-06-01T00:00:00+00:00"


# --------------------------- fundamentals adapter ---------------------------
class _FakeTicker:
    def __init__(self, info):
        self.info = info


@contextlib.contextmanager
def fake_yf(info):
    orig = fundamentals.yf.Ticker
    fundamentals.yf.Ticker = lambda sym: _FakeTicker(info)
    try:
        yield
    finally:
        fundamentals.yf.Ticker = orig


def test_fetch_fundamentals_unit_quirks_and_schema():
    info = {
        "longName": "NVIDIA Corp.", "currentPrice": 110.0,
        "regularMarketPreviousClose": 100.0, "marketCap": 2.98e12,
        "trailingPE": 54.2, "regularMarketVolume": 5_000_000,
        "totalRevenue": 96.3e9, "profitMargins": 0.55,  # fraction
        "trailingEps": 2.24, "dividendYield": 0.47,      # already a percent
        "beta": 1.68, "fiftyTwoWeekHigh": 140.0, "fiftyTwoWeekLow": 70.0,
        "longBusinessSummary": "GPUs for AI.",
        "sector": "Technology", "industry": "Semiconductors",
    }
    with fake_yf(info):
        out = fundamentals.fetch_fundamentals("nvda")
    assert out["symbol"] == "NVDA"
    assert out["price"] == 110.0
    assert out["changePct"] == 10.0
    # profitMargins is a fraction -> multiplied by 100 to get net-margin percent.
    assert out["netMargin"] == 55.0
    # dividendYield is already a percent -> passed through unchanged.
    assert out["dividendYield"] == 0.47
    # Industry "Semiconductors" maps to the internal semiconductors bucket.
    assert out["sector"] == "semiconductors"
    assert out["industry"] == "Semiconductors"


def test_fetch_fundamentals_raises_when_no_quote():
    with fake_yf({"longName": "Empty"}):
        raised = False
        try:
            fundamentals.fetch_fundamentals("X")
        except ValueError:
            raised = True
    assert raised


def test_fetch_fundamentals_missing_dividend_defaults_zero():
    info = {"regularMarketPrice": 10.0, "marketCap": 1e9}
    with fake_yf(info):
        out = fundamentals.fetch_fundamentals("X")
    assert out["dividendYield"] == 0.0
    assert out["netMargin"] is None  # absent profitMargins stays None, not 0


# --------------------------- sectors adapter ---------------------------
def test_map_sector_theme_specificity():
    assert sectors.map_sector("Technology", "Semiconductors") == "semiconductors"
    assert sectors.map_sector("Healthcare", "Drug Manufacturers") == "biotech"
    assert sectors.map_sector("Financial Services", "Banks - Regional") == "financials"
    assert sectors.map_sector("Energy", "Oil & Gas E&P") == "energy"
    assert sectors.map_sector("Technology", "Software - Application") == "cloud"
    # An unknown sector/industry falls back to the documented default.
    assert sectors.map_sector(None, None) == sectors.INTERNAL_DEFAULT
    assert sectors.map_sector("Something Weird", "Nonsense") == sectors.INTERNAL_DEFAULT


# --------------------------- sentiment adapter ---------------------------
def test_classify_headline_polarity():
    assert sentiment.classify_headline("Stock surges to record high on strong beat") == "positive"
    assert sentiment.classify_headline("Shares plunge on lawsuit and downgrade") == "negative"
    assert sentiment.classify_headline("Company holds annual meeting") == "neutral"


def test_derive_sentiment_shape_and_determinism():
    items = [{"sentiment": "positive"}, {"sentiment": "positive"},
             {"sentiment": "negative"}, {"sentiment": "neutral"}]
    a = sentiment.derive_sentiment("symbol", "NVDA", items)
    b = sentiment.derive_sentiment("symbol", "NVDA", items)
    assert set(a.keys()) == {"overall", "label", "sources", "trend"}
    # (2 pos - 1 neg) / 4 = 0.25 overall.
    assert a["overall"] == 0.25
    assert a["label"] in {"very_bullish", "bullish", "neutral", "bearish", "very_bearish"}
    assert len(a["sources"]) == 4
    assert {s["channel"] for s in a["sources"]} == {"Reddit", "X", "StockTwits", "News Wire"}
    assert len(a["trend"]) == 14
    # The trend ends exactly at the headline overall.
    assert a["trend"][-1]["score"] == a["overall"]
    # Same scope + same items -> identical output (seeded, no real randomness).
    assert a == b


def test_derive_sentiment_empty_items_is_neutral():
    out = sentiment.derive_sentiment("sector", "semiconductors", [])
    assert out["overall"] == 0.0
    assert out["label"] == "neutral"


# ============================================================================
# repo.macro_assets — live vs mock vs derived spread
# ============================================================================
_MACRO_TILE_KEYS = {"symbol", "name", "price", "changePct", "unit",
                    "sparkline", "source", "asOf"}


def _macro_db(quotes, ohlcv=None):
    """Build a fake db.query that serves macro_prices then ohlcv rows.

    ``quotes`` maps macro key -> (price, change_pct); ``ohlcv`` maps key ->
    list of closes. The first SELECT (macro_prices) and the second (ohlcv) are
    distinguished by the SQL text.
    """
    ohlcv = ohlcv or {}

    def _q(sql, params=None):
        if "macro_prices" in sql:
            return [
                {"symbol": k, "name": None, "price": p, "change_pct": c,
                 "updated_at": datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)}
                for k, (p, c) in quotes.items()
            ]
        if "ohlcv" in sql:
            rows = []
            base = date(2026, 1, 1)
            from datetime import timedelta
            for k, closes in ohlcv.items():
                for i, c in enumerate(closes):
                    rows.append({"symbol": k, "d": base + timedelta(days=i), "c": c})
            return rows
        raise AssertionError(f"unexpected SQL: {sql}")

    return _q


def test_macro_assets_live_sets_schema_source_and_asof():
    q = _macro_db({"SPX": (7405.7, -2.56)}, {"SPX": [7600.0, 7500.0, 7405.7]})
    with fake_db(query=q):
        out = repo.macro_assets(["SPX"])
    tile = out["SPX"]
    assert set(tile.keys()) == _MACRO_TILE_KEYS
    assert tile["price"] == 7405.7
    assert tile["changePct"] == -2.56
    assert tile["unit"] == "index"
    assert tile["source"] == "live"
    assert tile["asOf"] == "2026-06-01T20:00:00+00:00"
    # Sparkline comes from the real OHLCV closes, not the mock generator.
    assert tile["sparkline"] == [7600.0, 7500.0, 7405.7]


def test_macro_assets_falls_back_to_mock_when_db_unavailable():
    with fake_db(available=False):
        out = repo.macro_assets(["SPX"])
    tile = out["SPX"]
    assert set(tile.keys()) == _MACRO_TILE_KEYS
    assert tile["source"] == "mock"
    assert tile["asOf"] is None
    assert tile["price"] == float(data.MACRO_ASSETS["SPX"]["price"])
    assert tile["sparkline"]  # mock sparkline still populated


def test_macro_assets_falls_back_to_mock_on_db_error():
    with fake_db(available=True, query=_boom):
        out = repo.macro_assets(["SPX"])
    assert out["SPX"]["source"] == "mock"


def test_macro_assets_missing_live_row_uses_mock_per_tile():
    # DXY has a live quote; SPX is absent from the feed -> SPX must degrade to
    # mock while DXY stays live (per-tile fallback, never all-or-nothing).
    q = _macro_db({"DXY": (104.0, 0.3)}, {"DXY": [103.0, 104.0]})
    with fake_db(query=q):
        out = repo.macro_assets(["SPX", "DXY"])
    assert out["DXY"]["source"] == "live"
    assert out["SPX"]["source"] == "mock"


def test_macro_assets_derived_spread_from_live_legs():
    # 10Y=4.55 (+2.0%), 2Y=3.80 (-1.0%). Spread now = (4.55-3.80)*100 = 75 bps.
    q = _macro_db({"US10Y": (4.55, 2.0), "US2Y": (3.80, -1.0)},
                  {"US10Y": [4.40, 4.55], "US2Y": [3.85, 3.80]})
    with fake_db(query=q):
        out = repo.macro_assets(["US2Y10Y"])
    tile = out["US2Y10Y"]
    assert tile["source"] == "live"
    assert tile["unit"] == "bps"
    assert tile["price"] == round((4.55 - 3.80) * 100, 2)  # 75.0 bps
    # Spread sparkline is the bp difference of the two aligned close series.
    assert tile["sparkline"] == [round((4.40 - 3.85) * 100, 4),
                                 round((4.55 - 3.80) * 100, 4)]


def test_macro_assets_derived_spread_mock_when_a_leg_missing():
    # Only one leg live -> the spread cannot be derived honestly -> mock.
    q = _macro_db({"US10Y": (4.55, 2.0)}, {"US10Y": [4.40, 4.55]})
    with fake_db(query=q):
        out = repo.macro_assets(["US2Y10Y"])
    assert out["US2Y10Y"]["source"] == "mock"
    assert out["US2Y10Y"]["unit"] == "bps"


def test_macro_assets_curated_only_key_stays_mock_even_live_db():
    # TIPS10Y has no Yahoo feed; even with a populated DB it stays mock.
    q = _macro_db({"US10Y": (4.55, 2.0)}, {})
    with fake_db(query=q):
        out = repo.macro_assets(["TIPS10Y"])
    assert out["TIPS10Y"]["source"] == "mock"


def test_macro_assets_live_and_mock_have_identical_schema():
    q = _macro_db({"SPX": (7405.7, -2.56)}, {"SPX": [7600.0, 7405.7]})
    with fake_db(query=q):
        live = repo.macro_assets(["SPX"])["SPX"]
    with fake_db(available=False):
        mock = repo.macro_assets(["SPX"])["SPX"]
    assert set(live.keys()) == set(mock.keys())


# ============================================================================
# runner
# ============================================================================
def _run_all():
    funcs = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in funcs:
        fn()
        passed += 1
        print(f"  PASS {fn.__name__}")
    print(f"\n{passed}/{len(funcs)} data-layer tests passed")


if __name__ == "__main__":
    _run_all()
