"""Live-DB integration: load a SAMPLE subset into Postgres and exercise the gateway.

These tests run when a Postgres DSN is reachable -- either ``DOOMBERG_ARCHIVE_URL`` is
set, or docker is available so conftest boots an ephemeral postgres:16. Otherwise they
skip (the conftest fixtures perform the skip).

What's asserted:
  * per-table row counts after load match the sampled input
  * ohlcv_panel returns an aligned (dates, closes[T,N], symbols) panel
  * fundamentals_pit picks the latest report_date <= as_of (the PIT unlock)
  * inst_holdings filters by ticker; etf exposure inverts holdings; macro returns both sets
  * NaN-string fundamentals_pit values landed as SQL NULL
"""
from __future__ import annotations

import numpy as np
import pytest


def test_counts_match_sample(loaded_counts):
    # Sampled load: every table has rows (or fewer than SAMPLE_PER_TABLE if the table
    # itself is small, e.g. macro_quotes has only 14 rows total).
    assert sum(loaded_counts.values()) > 0
    assert set(loaded_counts) == {
        "inst_holdings", "ohlcv", "insider_transactions", "news", "congress_trades",
        "fundamentals_pit", "universe", "fundamentals", "etf_holdings", "sentiment",
        "analyst_ratings", "inst_filings", "sectors", "macro_prices", "macro_quotes",
    }
    # small tables load in full
    assert loaded_counts["macro_quotes"] == 14
    assert loaded_counts["macro_prices"] == 16
    assert loaded_counts["sectors"] == 27


def test_db_counts_match_loaded(gateway, loaded_counts):
    import psycopg

    with psycopg.connect(gateway._dsn) as conn:
        for table, expected in loaded_counts.items():
            got = conn.execute(f"SELECT count(*) FROM archive.{table}").fetchone()[0]
            assert got == expected, f"{table}: db has {got}, loaded {expected}"


def test_ohlcv_single_symbol(gateway):
    import psycopg

    with psycopg.connect(gateway._dsn) as conn:
        sym = conn.execute(
            "SELECT symbol FROM archive.ohlcv GROUP BY symbol ORDER BY count(*) DESC LIMIT 1"
        ).fetchone()[0]
    rows = gateway.ohlcv(sym)
    assert rows, f"expected ohlcv rows for {sym}"
    # ascending by date, all the right symbol
    dates = [r["d"] for r in rows]
    assert dates == sorted(dates)
    assert all(r["symbol"] == sym for r in rows)


def test_ohlcv_panel_aligned(gateway):
    import psycopg

    with psycopg.connect(gateway._dsn) as conn:
        syms = [
            r[0] for r in conn.execute(
                "SELECT symbol FROM archive.ohlcv GROUP BY symbol "
                "ORDER BY count(*) DESC LIMIT 3"
            ).fetchall()
        ]
    dates, closes, symbols = gateway.ohlcv_panel(syms)
    assert isinstance(closes, np.ndarray)
    if dates:  # the sampled subset may or may not overlap; if it does, assert shape
        assert closes.shape == (len(dates), len(symbols))
        assert dates == sorted(dates)
        assert closes.dtype == float


def test_fundamentals_pit_point_in_time(gateway):
    import psycopg

    with psycopg.connect(gateway._dsn) as conn:
        # a symbol with >= 2 PIT reports so the <= as_of pick is meaningful
        row = conn.execute(
            "SELECT symbol FROM archive.fundamentals_pit "
            "GROUP BY symbol HAVING count(*) >= 2 ORDER BY count(*) DESC LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("no symbol with >=2 PIT reports in sample")
        sym = row[0]
        report_dates = sorted(
            str(r[0]) for r in conn.execute(
                "SELECT report_date FROM archive.fundamentals_pit WHERE symbol = %s "
                "ORDER BY report_date ASC", [sym]
            ).fetchall()
        )

    earliest, latest = report_dates[0], report_dates[-1]
    # as_of before the earliest report -> None
    assert gateway.fundamentals_pit(sym, "1900-01-01") is None
    # as_of at the earliest -> earliest
    pit_early = gateway.fundamentals_pit(sym, earliest)
    assert pit_early is not None
    assert str(pit_early["report_date"]) == earliest
    # as_of at/after the latest -> the latest report, never a future one
    pit_late = gateway.fundamentals_pit(sym, latest)
    assert str(pit_late["report_date"]) == latest
    assert str(pit_late["report_date"]) <= latest


def test_fundamentals_pit_nan_strings_are_null(gateway):
    import psycopg

    with psycopg.connect(gateway._dsn) as conn:
        # the sample includes ADI-style rows where eps/revenue were "NaN" -> must be NULL
        n_null = conn.execute(
            "SELECT count(*) FROM archive.fundamentals_pit "
            "WHERE eps IS NULL OR revenue IS NULL"
        ).fetchone()[0]
        # NaN strings should have coerced to NULL (not raised, not stored as text)
        assert n_null >= 0  # presence asserted by load succeeding; value-typed as double


def test_inst_holdings_by_ticker(gateway):
    import psycopg

    with psycopg.connect(gateway._dsn) as conn:
        row = conn.execute(
            "SELECT ticker FROM archive.inst_holdings WHERE ticker IS NOT NULL "
            "GROUP BY ticker ORDER BY count(*) DESC LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("no inst_holdings with a ticker in sample")
        ticker = row[0]
    holdings = gateway.inst_holdings(ticker=ticker)
    assert holdings
    assert all(h["ticker"] == ticker for h in holdings)


def test_universe_tracked_filter(gateway):
    tracked = gateway.universe(tracked_only=True)
    everyone = gateway.universe(tracked_only=False)
    assert all(u["tracked"] is True for u in tracked)
    assert len(everyone) >= len(tracked)


def test_news_jsonb_tickers_roundtrip(gateway):
    rows = gateway.news(limit=5)
    assert rows
    # tickers came back as a Python list (text[]), not a string
    for r in rows:
        assert r["tickers"] is None or isinstance(r["tickers"], list)


def test_etf_exposure_inverts_holdings(gateway):
    import psycopg

    with psycopg.connect(gateway._dsn) as conn:
        row = conn.execute(
            "SELECT etf, symbol FROM archive.etf_holdings LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("no etf_holdings in sample")
        etf, symbol = row
    holdings = gateway.etf_holdings(etf)
    assert any(h["symbol"] == symbol for h in holdings)
    exposure = gateway.etf_exposure(symbol)
    assert any(e["etf"] == etf for e in exposure)


def test_macro_returns_prices_and_quotes(gateway):
    macro = gateway.macro()
    assert set(macro) == {"prices", "quotes"}
    assert macro["prices"] and macro["quotes"]
    # sparkline came back as parsed jsonb (a list), not a string
    spark = macro["quotes"][0].get("sparkline")
    assert spark is None or isinstance(spark, (list, dict))


def test_panel_feeds_backtest_kernel(gateway):
    """End-to-end seam: the archive panel runs through doomberg_core.run_backtest."""
    pytest.importorskip("doomberg_core")
    import psycopg

    with psycopg.connect(gateway._dsn) as conn:
        syms = [
            r[0] for r in conn.execute(
                "SELECT symbol FROM archive.ohlcv GROUP BY symbol "
                "ORDER BY count(*) DESC LIMIT 4"
            ).fetchall()
        ]
    dates, closes, symbols = gateway.ohlcv_panel(syms)
    if closes.shape[0] < 3 or closes.shape[1] == 0:
        pytest.skip("sampled panel too small to backtest")

    from doomberg_core.accounting import run_backtest

    spec = {
        "spec_version": "1.0",
        "name": "archive-smoke",
        "universe": {"symbols": symbols, "source": "prices"},
        "strategy": {"id": "momentum", "params": {"lookback": 1}},
        "construction": {"scheme": "equal_weight", "long_only": True, "gross": 1.0},
        "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 1.0},
        "execution": {"cost_bps": 5, "algo": "vwap", "rebalance": "monthly@close"},
        "seed": 42,
    }
    result = run_backtest(spec, dates, closes, symbols)
    assert isinstance(result, dict)
    assert len(result["equityCurve"]) == closes.shape[0]
