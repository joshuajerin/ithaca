"""DB-free unit tests: parse/group/coercion + SQL generation.

These run everywhere (no Postgres, no docker). They lock down the tricky bits of the
loader: type coercion (NaN-string -> NULL, text[] literals, jsonb serialization,
missing keys), grouping (and dropping unknown tables), and the generated DDL/COPY SQL.
"""
from __future__ import annotations

import json

import pytest

from doomberg_archive.loader import (
    SCHEMA,
    TABLE_COLUMNS,
    TABLES,
    coerce_value,
    copy_sql,
    create_table_sql,
    group_records,
    row_to_tuple,
)

# Authoritative per-table counts from the contract doc.
EXPECTED_TABLES = {
    "inst_holdings", "ohlcv", "insider_transactions", "news", "congress_trades",
    "fundamentals_pit", "universe", "fundamentals", "etf_holdings", "sentiment",
    "analyst_ratings", "inst_filings", "sectors", "macro_prices", "macro_quotes",
}


def test_all_15_tables_present():
    assert set(TABLES) == EXPECTED_TABLES
    assert len(TABLES) == 15


def test_schema_sql_covers_every_table_and_column():
    ddl = create_table_sql()
    assert "CREATE SCHEMA IF NOT EXISTS archive" in ddl
    for table, cols in TABLE_COLUMNS.items():
        assert f"archive.{table}" in ddl, f"missing table {table} in DDL"
        for name, _ in cols:
            assert name in ddl, f"column {table}.{name} not in DDL"


def test_copy_sql_lists_columns_in_order():
    sql = copy_sql("ohlcv")
    assert sql == f"COPY {SCHEMA}.ohlcv (symbol, d, o, h, l, c, v, updated_at) FROM STDIN"


def test_coerce_nan_string_becomes_none():
    # fundamentals_pit ships literal "NaN" strings for double precision columns.
    assert coerce_value("NaN", "float") is None
    assert coerce_value("nan", "float") is None
    assert coerce_value(float("nan"), "float") is None


def test_coerce_scalars():
    assert coerce_value("AMD", "text") == "AMD"
    assert coerce_value(7.89, "float") == 7.89
    assert coerce_value("12", "int") == 12
    assert coerce_value(None, "int") is None
    assert coerce_value("", "float") is None


def test_coerce_bool_variants():
    assert coerce_value(True, "bool") is True
    assert coerce_value(False, "bool") is False
    assert coerce_value("true", "bool") is True
    assert coerce_value(0, "bool") is False
    assert coerce_value(1, "bool") is True


def test_coerce_date_and_ts_passthrough():
    assert coerce_value("2026-06-16", "date") == "2026-06-16"
    assert coerce_value("2026-06-17T19:36:47.5+00:00", "timestamptz") == "2026-06-17T19:36:47.5+00:00"
    assert coerce_value(None, "date") is None


def test_coerce_textarray():
    assert coerce_value(["GOOGL", "META"], "text[]") == ["GOOGL", "META"]
    assert coerce_value(None, "text[]") is None


def test_coerce_jsonb_returns_value_for_caller():
    val = [{"t": "2026-06-04", "score": 0.17}]
    assert coerce_value(val, "jsonb") == val


def test_row_to_tuple_news_tickers_array_literal():
    row = {
        "id": "news-1", "headline": "h", "source": "src", "summary": "s",
        "url": "u", "published_at": "2026-06-06T14:37:00+00:00", "sentiment": "neutral",
        "tickers": ["GOOGL", "META", 'WB"D'], "sector": "comms",
        "fetched_at": "2026-06-07T04:39:53+00:00",
    }
    tup = row_to_tuple("news", row)
    cols = [c for c, _ in TABLE_COLUMNS["news"]]
    tickers = tup[cols.index("tickers")]
    # Postgres array literal with the embedded quote escaped.
    assert tickers == '{"GOOGL","META","WB\\"D"}'


def test_row_to_tuple_jsonb_serialized_to_string_by_default():
    row = {
        "scope_type": "ticker", "scope": "AFRM", "overall": 0.17, "label": "bullish",
        "sources": [{"channel": "Reddit", "score": 0.23}],
        "trend": [{"t": "2026-06-04", "score": 0.17}],
        "updated_at": "2026-06-17T00:00:00+00:00",
    }
    tup = row_to_tuple("sentiment", row)
    cols = [c for c, _ in TABLE_COLUMNS["sentiment"]]
    sources = tup[cols.index("sources")]
    assert isinstance(sources, str)
    assert json.loads(sources) == [{"channel": "Reddit", "score": 0.23}]


def test_row_to_tuple_jsonb_raw_when_not_string():
    row = {"scope_type": "ticker", "scope": "X", "sources": {"a": 1},
           "trend": None, "updated_at": "2026-06-17T00:00:00+00:00"}
    tup = row_to_tuple("sentiment", row, jsonb_as_string=False)
    cols = [c for c, _ in TABLE_COLUMNS["sentiment"]]
    assert tup[cols.index("sources")] == {"a": 1}
    assert tup[cols.index("trend")] is None


def test_row_to_tuple_missing_keys_become_none():
    # fundamentals row with most keys absent.
    tup = row_to_tuple("fundamentals", {"symbol": "ZZZ", "is_live": True, "updated_at": "2026-06-17T00:00:00+00:00"})
    cols = [c for c, _ in TABLE_COLUMNS["fundamentals"]]
    assert tup[cols.index("symbol")] == "ZZZ"
    assert tup[cols.index("price")] is None
    assert tup[cols.index("description")] is None
    assert tup[cols.index("is_live")] is True


def test_row_to_tuple_fundamentals_pit_nan_strings_to_none():
    row = {
        "symbol": "ADI", "period_end": "2024-10-31", "report_date": "2024-12-15",
        "revenue": "NaN", "net_income": "NaN", "net_margin": "NaN", "eps": "NaN",
        "report_estimated": True, "source": "yfinance",
        "updated_at": "2026-06-09T16:25:14+00:00",
    }
    tup = row_to_tuple("fundamentals_pit", row)
    cols = [c for c, _ in TABLE_COLUMNS["fundamentals_pit"]]
    for col in ("revenue", "net_income", "net_margin", "eps"):
        assert tup[cols.index(col)] is None
    assert tup[cols.index("report_date")] == "2024-12-15"
    assert tup[cols.index("report_estimated")] is True


def test_group_records_buckets_and_drops_unknown_tables():
    recs = [
        {"tbl": "ohlcv", "row": {"symbol": "AMD"}},
        {"tbl": "ohlcv", "row": {"symbol": "NVDA"}},
        {"tbl": "universe", "row": {"symbol": "AMD"}},
        {"tbl": "users", "row": {"id": "secret"}},          # excluded v1 app table
        {"tbl": "order_book_l2", "row": {"id": "secret"}},  # synthetic v1 table
    ]
    grouped = group_records(recs)
    assert len(grouped["ohlcv"]) == 2
    assert len(grouped["universe"]) == 1
    assert "users" not in grouped
    assert "order_book_l2" not in grouped
    # every known table is present (empty lists for the rest)
    assert set(grouped) == set(TABLES)


def test_unknown_coltype_raises():
    with pytest.raises(ValueError):
        coerce_value("x", "geography")
