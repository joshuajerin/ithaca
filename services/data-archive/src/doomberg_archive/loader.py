"""Bulk-loader for the v1 market-data archive into Postgres schema ``archive``.

Reads ``data/v1_archive.json`` -- a JSON array of ``{"tbl": <name>, "row": {...}}``
records (~92 MB, 240,220 rows across 15 tables) -- groups by table, (re)creates the
canonical schema, and bulk-loads each table into ``archive.<tbl>`` via psycopg COPY.

The load is idempotent: each target table is TRUNCATEd before its rows are copied in.

Type handling is driven by ``TABLE_COLUMNS`` -- the single authoritative ordered
column spec per table. Each column carries a coercion class:

* ``text`` / ``int`` / ``float`` / ``bool`` -- scalar coercion (with NaN-string guard)
* ``date`` / ``timestamptz`` -- pass the ISO string straight through; Postgres parses it
* ``text[]`` -- a JSON list becomes a Postgres array literal
* ``jsonb`` -- the value is re-serialized to a JSON string

The parse/group/coercion logic and SQL generation are importable and unit-testable
without a database; only :func:`load_archive` requires a live Postgres connection.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

__all__ = [
    "TABLE_COLUMNS",
    "TABLES",
    "iter_records",
    "group_records",
    "coerce_value",
    "row_to_tuple",
    "create_table_sql",
    "copy_sql",
    "load_archive",
    "SCHEMA",
]

SCHEMA = "archive"

# ---------------------------------------------------------------------------
# Authoritative per-table column spec: ordered (name, type) pairs.
# The type string is the *coercion class*, which maps 1:1 onto the schema.sql DDL.
# ---------------------------------------------------------------------------
TABLE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "universe": [
        ("symbol", "text"), ("name", "text"), ("sector", "text"),
        ("tracked", "bool"), ("pending", "bool"),
        ("first_seen_at", "timestamptz"), ("updated_at", "timestamptz"),
        ("country", "text"), ("exchange", "text"), ("industry", "text"),
        ("website", "text"), ("listed_at", "date"), ("delisted_at", "date"),
        ("status", "text"),
    ],
    "sectors": [
        ("id", "text"), ("name", "text"), ("updated_at", "timestamptz"),
    ],
    "ohlcv": [
        ("symbol", "text"), ("d", "date"),
        ("o", "float"), ("h", "float"), ("l", "float"),
        ("c", "float"), ("v", "float"), ("updated_at", "timestamptz"),
    ],
    "fundamentals": [
        ("symbol", "text"), ("name", "text"), ("price", "float"),
        ("change_pct", "float"), ("market_cap", "float"), ("pe_ratio", "float"),
        ("volume", "float"), ("revenue", "float"), ("net_margin", "float"),
        ("eps", "float"), ("dividend_yield", "float"), ("beta", "float"),
        ("week52_high", "float"), ("week52_low", "float"), ("description", "text"),
        ("updated_at", "timestamptz"), ("is_live", "bool"),
        ("revenue_growth", "float"), ("earnings_date", "date"),
        ("ex_dividend_date", "date"), ("dividend_date", "date"),
        ("mcap_refreshed_at", "timestamptz"), ("earnings_eps_estimate", "float"),
    ],
    "fundamentals_pit": [
        ("symbol", "text"), ("period_end", "date"), ("report_date", "date"),
        ("revenue", "float"), ("net_income", "float"), ("net_margin", "float"),
        ("eps", "float"), ("report_estimated", "bool"), ("source", "text"),
        ("updated_at", "timestamptz"),
    ],
    "analyst_ratings": [
        ("symbol", "text"), ("name", "text"), ("covered", "bool"),
        ("consensus_key", "text"), ("recommendation_mean", "float"),
        ("num_analysts", "int"), ("strong_buy", "int"), ("buy", "int"),
        ("hold", "int"), ("sell", "int"), ("strong_sell", "int"),
        ("target_mean", "float"), ("target_high", "float"), ("target_low", "float"),
        ("target_median", "float"), ("current_price", "float"),
        ("changes", "jsonb"), ("source", "text"), ("updated_at", "timestamptz"),
    ],
    "news": [
        ("id", "text"), ("headline", "text"), ("source", "text"),
        ("summary", "text"), ("url", "text"), ("published_at", "timestamptz"),
        ("sentiment", "text"), ("tickers", "text[]"), ("sector", "text"),
        ("fetched_at", "timestamptz"),
    ],
    "congress_trades": [
        ("id", "text"), ("member", "text"), ("chamber", "text"), ("party", "text"),
        ("party_code", "text"), ("ticker", "text"), ("txn_type", "text"),
        ("raw_type", "text"), ("amount_range", "text"), ("amount_low", "float"),
        ("amount_high", "float"), ("transaction_date", "date"),
        ("disclosure_date", "date"), ("source_url", "text"), ("description", "text"),
        ("fetched_at", "timestamptz"),
    ],
    "insider_transactions": [
        ("accession_no", "text"), ("txn_seq", "int"), ("symbol", "text"),
        ("cik", "text"), ("issuer_name", "text"), ("insider_name", "text"),
        ("role", "text"), ("transaction_code", "text"), ("transaction_type", "text"),
        ("acquired_disposed", "text"), ("security_title", "text"),
        ("is_derivative", "bool"), ("shares", "float"), ("price", "float"),
        ("value", "float"), ("shares_owned_after", "float"),
        ("transaction_date", "date"), ("filing_date", "date"), ("form", "text"),
        ("url", "text"), ("source", "text"), ("updated_at", "timestamptz"),
    ],
    "inst_holdings": [
        ("cik", "text"), ("period", "date"), ("cusip", "text"), ("put_call", "text"),
        ("institution", "text"), ("ticker", "text"), ("name", "text"),
        ("title_of_class", "text"), ("shares_type", "text"), ("shares", "float"),
        ("value", "float"), ("url", "text"), ("accession_no", "text"),
        ("source", "text"), ("updated_at", "timestamptz"),
    ],
    "inst_filings": [
        ("cik", "text"), ("period", "date"), ("institution", "text"),
        ("accession_no", "text"), ("form", "text"), ("filing_date", "date"),
        ("url", "text"), ("total_value", "float"), ("positions", "int"),
        ("source", "text"), ("updated_at", "timestamptz"),
    ],
    "etf_holdings": [
        ("etf", "text"), ("symbol", "text"), ("name", "text"), ("weight", "float"),
        ("as_of", "date"), ("source", "text"), ("updated_at", "timestamptz"),
    ],
    "sentiment": [
        ("scope_type", "text"), ("scope", "text"), ("overall", "float"),
        ("label", "text"), ("sources", "jsonb"), ("trend", "jsonb"),
        ("updated_at", "timestamptz"),
    ],
    "macro_prices": [
        ("symbol", "text"), ("name", "text"), ("price", "float"),
        ("change_pct", "float"), ("updated_at", "timestamptz"),
    ],
    "macro_quotes": [
        ("symbol", "text"), ("price", "float"), ("change_pct", "float"),
        ("sparkline", "jsonb"), ("is_live", "bool"), ("updated_at", "timestamptz"),
    ],
}

TABLES: tuple[str, ...] = tuple(TABLE_COLUMNS)

# Truncate order is irrelevant (no FKs), but a stable order keeps logs deterministic.


def _is_nan(value: Any) -> bool:
    """True for float NaN and the literal JSON string ``"NaN"`` (seen in fundamentals_pit)."""
    if isinstance(value, float):
        return math.isnan(value)
    return isinstance(value, str) and value.strip().lower() == "nan"


def coerce_value(value: Any, coltype: str) -> Any:
    """Coerce a raw JSON value to the Python value psycopg adapts for ``coltype``.

    Returns ``None`` for missing/null/NaN. Dates and timestamps are passed through as
    ISO strings (Postgres parses them on the column type). ``text[]`` becomes a Python
    list[str]; ``jsonb`` becomes a ``Json``-wrapped value if psycopg is available, else
    a JSON string (the COPY path always serializes jsonb to a string).
    """
    if value is None or _is_nan(value):
        return None

    if coltype == "text":
        return str(value)
    if coltype == "int":
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if coltype == "float":
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return None
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(f) else f
    if coltype == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"t", "true", "1", "yes", "y"}
        return None
    if coltype in ("date", "timestamptz"):
        # ISO strings parse natively on the target column type.
        return str(value)
    if coltype == "text[]":
        if isinstance(value, (list, tuple)):
            return [str(x) for x in value]
        if isinstance(value, str):
            return [value]
        return None
    if coltype == "jsonb":
        # Caller (copy_record / row_to_tuple) decides string vs Json wrapper.
        return value
    raise ValueError(f"unknown coltype {coltype!r}")


def _array_literal(items: list[str]) -> str:
    """Render a Postgres text[] literal, escaping embedded quotes/backslashes."""
    parts = []
    for it in items:
        s = str(it).replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'"{s}"')
    return "{" + ",".join(parts) + "}"


def row_to_tuple(table: str, row: dict, *, jsonb_as_string: bool = True) -> tuple:
    """Project a raw archive row dict onto the ordered column tuple for ``table``.

    Missing keys yield ``None``. ``text[]`` columns become Postgres array literals;
    ``jsonb`` columns become JSON strings (``jsonb_as_string=True``, the COPY path) or
    raw Python objects (``False``, the executemany path with a ``Json`` adapter).
    """
    cols = TABLE_COLUMNS[table]
    out: list[Any] = []
    for name, coltype in cols:
        raw = row.get(name)
        val = coerce_value(raw, coltype)
        if val is None:
            out.append(None)
        elif coltype == "text[]":
            out.append(_array_literal(val))
        elif coltype == "jsonb":
            out.append(json.dumps(val) if jsonb_as_string else val)
        else:
            out.append(val)
    return tuple(out)


def create_table_sql() -> str:
    """Return the canonical schema DDL (read from the sibling ``schema.sql``)."""
    return (Path(__file__).parent / "schema.sql").read_text()


def copy_sql(table: str) -> str:
    """``COPY archive.<table> (col, ...) FROM STDIN`` for the ordered columns."""
    cols = ", ".join(name for name, _ in TABLE_COLUMNS[table])
    return f"COPY {SCHEMA}.{table} ({cols}) FROM STDIN"


def truncate_sql(table: str) -> str:
    return f"TRUNCATE {SCHEMA}.{table}"


# ---------------------------------------------------------------------------
# Streaming parse + group
# ---------------------------------------------------------------------------
def iter_records(path: str | Path) -> Iterator[dict]:
    """Yield each ``{"tbl","row"}`` record from the archive JSON array.

    Uses an incremental ``raw_decode`` scan so the whole file need not be parsed at
    once by the array machinery, but it does read the file into memory (~92 MB) -- a
    one-shot import, not a long-running service.
    """
    text = Path(path).read_text()
    dec = json.JSONDecoder()
    i = text.find("[")
    if i < 0:
        return
    i += 1
    n = len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "]":
            break
        obj, end = dec.raw_decode(text, i)
        i = end
        yield obj


def group_records(records: Iterable[dict]) -> dict[str, list[dict]]:
    """Group ``{"tbl","row"}`` records into ``{table: [row, ...]}``.

    Unknown tables (not in :data:`TABLE_COLUMNS`) are ignored -- the v1 secret/app
    tables must never be imported even if they leak into the export.
    """
    grouped: dict[str, list[dict]] = {t: [] for t in TABLE_COLUMNS}
    for rec in records:
        tbl = rec.get("tbl")
        if tbl in grouped:
            grouped[tbl].append(rec.get("row") or {})
    return grouped


# ---------------------------------------------------------------------------
# Live load (requires psycopg + a Postgres DSN)
# ---------------------------------------------------------------------------
def load_archive(
    dsn: str,
    json_path: str | Path,
    *,
    create_schema: bool = True,
    truncate: bool = True,
    only: Iterable[str] | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Load the archive JSON into Postgres at ``dsn``; return ``{table: rows_loaded}``.

    Idempotent: when ``truncate`` is set, each target table is emptied before its rows
    are COPYed in, so re-running yields the same state. ``only`` restricts the load to a
    subset of tables (used by the sampled integration test).
    """
    import psycopg  # imported lazily so the module imports without a DB driver present

    log = log or (lambda _msg: None)
    tables = tuple(only) if only is not None else TABLES
    grouped = group_records(iter_records(json_path))

    counts: dict[str, int] = {}
    with psycopg.connect(dsn) as conn:
        if create_schema:
            conn.execute(create_table_sql())
            conn.commit()
        for table in tables:
            rows = grouped.get(table, [])
            with conn.cursor() as cur:
                if truncate:
                    cur.execute(truncate_sql(table))
                copy_stmt = copy_sql(table)
                with cur.copy(copy_stmt) as cp:
                    for row in rows:
                        cp.write_row(row_to_tuple(table, row, jsonb_as_string=True))
            conn.commit()
            counts[table] = len(rows)
            log(f"loaded archive.{table}: {len(rows)} rows")
    return counts
