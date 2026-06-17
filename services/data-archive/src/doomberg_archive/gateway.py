"""The read seam over the v1 archive (schema ``archive``).

Skills read ONLY through :class:`ArchiveGateway` -- never raw SQL in a skill. This
module defines the protocol (the cross-stream contract) and a concrete
:class:`PgArchiveGateway` backed by psycopg. The archive is shared, tenant-agnostic
reference data; provenance wrapping (``source: "doomberg-v1-archive"``) is layered on
by the skills, not here.

Import is network-free: psycopg is imported lazily and the connection is opened on
first query, so ``PgArchiveGateway(dsn)`` is cheap and tests can construct it without a
reachable database.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np

__all__ = ["ArchiveGateway", "PgArchiveGateway"]


@runtime_checkable
class ArchiveGateway(Protocol):
    # prices
    def ohlcv(self, symbol: str, start: str | None = None, end: str | None = None) -> list[dict]: ...
    def ohlcv_panel(
        self, symbols: list[str], start: str | None = None, end: str | None = None
    ) -> tuple[list[str], "np.ndarray", list[str]]: ...  # dates, closes[T,N], symbols
    # reference
    def universe(self, tracked_only: bool = True) -> list[dict]: ...
    def sectors(self) -> list[dict]: ...
    # fundamentals
    def fundamentals(self, symbols: list[str]) -> list[dict]: ...
    def fundamentals_pit(self, symbol: str, as_of: str) -> dict | None: ...  # latest report_date <= as_of
    # analyst / news / sentiment
    def analyst_ratings(self, symbols: list[str]) -> list[dict]: ...
    def news(self, ticker: str | None = None, sector: str | None = None, limit: int = 50) -> list[dict]: ...
    def sentiment(self, scope_type: str, scope: str) -> dict | None: ...
    # ownership / flows
    def congress_trades(self, ticker: str | None = None, member: str | None = None, limit: int = 100) -> list[dict]: ...
    def insider_transactions(self, symbol: str, limit: int = 100) -> list[dict]: ...
    def inst_holdings(self, ticker: str | None = None, cik: str | None = None, period: str | None = None) -> list[dict]: ...
    def inst_filings(self, cik: str | None = None, period: str | None = None) -> list[dict]: ...
    def etf_holdings(self, etf: str) -> list[dict]: ...
    def etf_exposure(self, symbol: str) -> list[dict]: ...  # which ETFs hold ``symbol``
    # macro
    def macro(self) -> dict: ...  # {prices: [...], quotes: [...]}


def _iso(value: Any) -> Any:
    """Render date/datetime to ISO strings so results are JSON-serializable."""
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    return iso() if callable(iso) else value


class PgArchiveGateway:
    """Concrete :class:`ArchiveGateway` over a Postgres ``archive`` schema.

    Stateless apart from a lazily-opened connection. Every read returns plain dicts
    (or, for :meth:`ohlcv_panel`, the aligned numpy panel the backtest kernel expects).
    """

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn = None  # opened lazily on first query -- no network at construction

    # -- connection -----------------------------------------------------------------
    def _connection(self):
        if self._conn is None or getattr(self._conn, "closed", False):
            import psycopg  # lazy: keep import-time network-free

            self._conn = psycopg.connect(self._dsn, autocommit=True)
        return self._conn

    def close(self) -> None:
        if self._conn is not None and not getattr(self._conn, "closed", True):
            self._conn.close()
        self._conn = None

    def _rows(self, sql: str, params: tuple | list | None = None) -> list[dict]:
        from psycopg.rows import dict_row

        conn = self._connection()
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params or ())
            return [self._normalize(r) for r in cur.fetchall()]

    @staticmethod
    def _normalize(row: dict) -> dict:
        return {k: _iso(v) for k, v in row.items()}

    # -- prices ---------------------------------------------------------------------
    def ohlcv(self, symbol: str, start: str | None = None, end: str | None = None) -> list[dict]:
        clauses = ["symbol = %s"]
        params: list[Any] = [symbol.upper()]
        if start:
            clauses.append("d >= %s")
            params.append(start)
        if end:
            clauses.append("d <= %s")
            params.append(end)
        sql = (
            "SELECT symbol, d, o, h, l, c, v, updated_at FROM archive.ohlcv "
            f"WHERE {' AND '.join(clauses)} ORDER BY d ASC"
        )
        return self._rows(sql, params)

    def ohlcv_panel(
        self, symbols: list[str], start: str | None = None, end: str | None = None
    ) -> tuple[list[str], "np.ndarray", list[str]]:
        """Aligned close matrix over the intersection of each symbol's trading days.

        Returns ``(dates, closes[T,N], resolved_symbols)`` with dates ascending and NO
        lookahead -- this feeds ``doomberg_core.run_backtest`` unchanged. Symbols with no
        rows (or no overlapping days) are dropped from ``resolved_symbols`` (and the
        matrix), never imputed.
        """
        wanted = [s.upper() for s in symbols]
        if not wanted:
            return [], np.zeros((0, 0), dtype=float), []

        clauses = ["symbol = ANY(%s)", "c IS NOT NULL"]
        params: list[Any] = [wanted]
        if start:
            clauses.append("d >= %s")
            params.append(start)
        if end:
            clauses.append("d <= %s")
            params.append(end)
        sql = (
            "SELECT symbol, d, c FROM archive.ohlcv "
            f"WHERE {' AND '.join(clauses)} ORDER BY d ASC"
        )
        rows = self._rows(sql, params)

        per_symbol: dict[str, dict[str, float]] = {}
        for r in rows:
            per_symbol.setdefault(r["symbol"], {})[str(r["d"])] = float(r["c"])

        # Preserve the caller's requested order for resolved symbols.
        resolved = [s for s in wanted if s in per_symbol]
        if not resolved:
            return [], np.zeros((0, 0), dtype=float), []

        common = set.intersection(*(set(per_symbol[s]) for s in resolved))
        dates = sorted(common)
        if not dates:
            return [], np.zeros((0, 0), dtype=float), []
        closes = np.array(
            [[per_symbol[s][d] for s in resolved] for d in dates], dtype=float
        )
        return dates, closes, resolved

    # -- reference ------------------------------------------------------------------
    def universe(self, tracked_only: bool = True) -> list[dict]:
        sql = (
            "SELECT symbol, name, sector, tracked, pending, first_seen_at, updated_at, "
            "country, exchange, industry, website, listed_at, delisted_at, status "
            "FROM archive.universe"
        )
        if tracked_only:
            sql += " WHERE tracked = true"
        sql += " ORDER BY symbol ASC"
        return self._rows(sql)

    def sectors(self) -> list[dict]:
        return self._rows("SELECT id, name, updated_at FROM archive.sectors ORDER BY id ASC")

    # -- fundamentals ---------------------------------------------------------------
    def fundamentals(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        syms = [s.upper() for s in symbols]
        return self._rows(
            "SELECT * FROM archive.fundamentals WHERE symbol = ANY(%s) ORDER BY symbol ASC",
            [syms],
        )

    def fundamentals_pit(self, symbol: str, as_of: str) -> dict | None:
        """Latest report whose ``report_date <= as_of`` -- the point-in-time unlock."""
        rows = self._rows(
            "SELECT * FROM archive.fundamentals_pit "
            "WHERE symbol = %s AND report_date <= %s "
            "ORDER BY report_date DESC, period_end DESC LIMIT 1",
            [symbol.upper(), as_of],
        )
        return rows[0] if rows else None

    # -- analyst / news / sentiment -------------------------------------------------
    def analyst_ratings(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        syms = [s.upper() for s in symbols]
        return self._rows(
            "SELECT * FROM archive.analyst_ratings WHERE symbol = ANY(%s) ORDER BY symbol ASC",
            [syms],
        )

    def news(self, ticker: str | None = None, sector: str | None = None, limit: int = 50) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if ticker:
            clauses.append("%s = ANY(tickers)")
            params.append(ticker.upper())
        if sector:
            clauses.append("sector = %s")
            params.append(sector)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        return self._rows(
            "SELECT id, headline, source, summary, url, published_at, sentiment, "
            f"tickers, sector, fetched_at FROM archive.news{where} "
            "ORDER BY published_at DESC NULLS LAST LIMIT %s",
            params,
        )

    def sentiment(self, scope_type: str, scope: str) -> dict | None:
        rows = self._rows(
            "SELECT scope_type, scope, overall, label, sources, trend, updated_at "
            "FROM archive.sentiment WHERE scope_type = %s AND scope = %s "
            "ORDER BY updated_at DESC LIMIT 1",
            [scope_type, scope],
        )
        return rows[0] if rows else None

    # -- ownership / flows ----------------------------------------------------------
    def congress_trades(
        self, ticker: str | None = None, member: str | None = None, limit: int = 100
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if ticker:
            clauses.append("ticker = %s")
            params.append(ticker.upper())
        if member:
            clauses.append("member = %s")
            params.append(member)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        return self._rows(
            f"SELECT * FROM archive.congress_trades{where} "
            "ORDER BY transaction_date DESC NULLS LAST LIMIT %s",
            params,
        )

    def insider_transactions(self, symbol: str, limit: int = 100) -> list[dict]:
        return self._rows(
            "SELECT * FROM archive.insider_transactions WHERE symbol = %s "
            "ORDER BY transaction_date DESC NULLS LAST LIMIT %s",
            [symbol.upper(), int(limit)],
        )

    def inst_holdings(
        self, ticker: str | None = None, cik: str | None = None, period: str | None = None
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if ticker:
            clauses.append("ticker = %s")
            params.append(ticker.upper())
        if cik:
            clauses.append("cik = %s")
            params.append(cik)
        if period:
            clauses.append("period = %s")
            params.append(period)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._rows(
            f"SELECT * FROM archive.inst_holdings{where} "
            "ORDER BY period DESC, value DESC NULLS LAST",
            params,
        )

    def inst_filings(self, cik: str | None = None, period: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if cik:
            clauses.append("cik = %s")
            params.append(cik)
        if period:
            clauses.append("period = %s")
            params.append(period)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._rows(
            f"SELECT * FROM archive.inst_filings{where} ORDER BY period DESC, filing_date DESC NULLS LAST",
            params,
        )

    def etf_holdings(self, etf: str) -> list[dict]:
        return self._rows(
            "SELECT * FROM archive.etf_holdings WHERE etf = %s ORDER BY weight DESC NULLS LAST",
            [etf.upper()],
        )

    def etf_exposure(self, symbol: str) -> list[dict]:
        """Which ETFs hold ``symbol`` (the inverse of :meth:`etf_holdings`)."""
        return self._rows(
            "SELECT * FROM archive.etf_holdings WHERE symbol = %s ORDER BY weight DESC NULLS LAST",
            [symbol.upper()],
        )

    # -- macro ----------------------------------------------------------------------
    def macro(self) -> dict:
        prices = self._rows(
            "SELECT symbol, name, price, change_pct, updated_at "
            "FROM archive.macro_prices ORDER BY symbol ASC"
        )
        quotes = self._rows(
            "SELECT symbol, price, change_pct, sparkline, is_live, updated_at "
            "FROM archive.macro_quotes ORDER BY symbol ASC"
        )
        return {"prices": prices, "quotes": quotes}
