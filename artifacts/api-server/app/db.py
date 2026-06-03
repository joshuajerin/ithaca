"""Postgres access for the terminal backend.

Uses a small psycopg connection pool keyed off DATABASE_URL. All callers go
through `query`/`execute`/`execute_many` so the pool is the single choke point.
If the database is unavailable the helpers raise; callers (the repository) catch
and fall back to the deterministic mock dataset.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterable, List, Optional, Sequence

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except Exception:  # pragma: no cover - import guard
    psycopg = None  # type: ignore
    ConnectionPool = None  # type: ignore
    dict_row = None  # type: ignore

_DATABASE_URL = os.environ.get("DATABASE_URL")
_pool: Optional["ConnectionPool"] = None


def db_available() -> bool:
    return bool(_DATABASE_URL and psycopg is not None and ConnectionPool is not None)


def get_pool() -> Optional["ConnectionPool"]:
    global _pool
    if not db_available():
        return None
    if _pool is None:
        _pool = ConnectionPool(
            _DATABASE_URL,
            min_size=1,
            max_size=8,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


@contextmanager
def connection():
    pool = get_pool()
    if pool is None:
        raise RuntimeError("database unavailable")
    with pool.connection() as conn:
        yield conn


def query(sql: str, params: Sequence[Any] | None = None) -> List[dict]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return list(cur.fetchall())


def query_one(sql: str, params: Sequence[Any] | None = None) -> Optional[dict]:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Sequence[Any] | None = None) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()


def execute_many(sql: str, rows: Iterable[Sequence[Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
