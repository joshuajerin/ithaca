"""Postgres access for the terminal backend.

Uses a small psycopg connection pool keyed off DATABASE_URL. All callers go
through `query`/`execute`/`execute_many` so the pool is the single choke point.
If the database is unavailable the helpers raise; callers (the repository) catch
and fall back to the deterministic mock dataset.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, List, Optional, Sequence

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except Exception:  # pragma: no cover - import guard
    psycopg = None  # type: ignore
    ConnectionPool = None  # type: ignore
    dict_row = None  # type: ignore

log = logging.getLogger(__name__)

_DATABASE_URL = os.environ.get("DATABASE_URL")
_pool: Optional["ConnectionPool"] = None


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "").strip() or default))
    except (TypeError, ValueError):
        return default


# Pool sizing is env-tunable so the same code can serve a single dev instance or
# several concurrent instances behind the platform. The pool is the single choke
# point for every query, so it must be sized for the expected concurrent
# in-flight requests (hot paths + the background worker's bounded fan-out).
_POOL_MIN = _env_int("DB_POOL_MIN", 2)
_POOL_MAX = _env_int("DB_POOL_MAX", 16)


def db_available() -> bool:
    return bool(_DATABASE_URL and psycopg is not None and ConnectionPool is not None)


def get_pool() -> Optional["ConnectionPool"]:
    global _pool
    if not db_available():
        return None
    if _pool is None:
        _pool = ConnectionPool(
            _DATABASE_URL,
            min_size=_POOL_MIN,
            max_size=_POOL_MAX,
            # Don't let a request block forever waiting for a free connection —
            # raise promptly so the caller can fall back instead of hanging.
            timeout=10.0,
            max_idle=300.0,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def pool_stats() -> dict:
    """Best-effort pool telemetry for the readiness endpoint (sizes + in-use)."""
    pool = _pool
    if pool is None:
        return {"open": False}
    try:
        stats = pool.get_stats()
    except Exception:  # noqa: BLE001
        stats = {}
    return {
        "open": True,
        "min": _POOL_MIN,
        "max": _POOL_MAX,
        "size": stats.get("pool_size"),
        "available": stats.get("pool_available"),
        "waiting": stats.get("requests_waiting"),
    }


def ping() -> bool:
    """Lightweight readiness probe: borrow a connection and run ``SELECT 1``."""
    if not db_available():
        return False
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("db ping failed: %s", exc)
        return False


@contextmanager
def advisory_lock(key: int) -> Iterator[bool]:
    """Best-effort cross-instance mutex via a Postgres session advisory lock.

    Yields ``True`` if this instance acquired the lock (and should do the work),
    ``False`` if another instance already holds it (and this tick should be
    skipped). When no database is configured there is only ever one instance, so
    it yields ``True``. The lock is held on a dedicated pooled connection for the
    duration of the block and released on exit.
    """
    pool = get_pool()
    if pool is None:
        yield True
        return
    with pool.connection() as conn:
        acquired = False
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(%s) AS ok", (key,))
                row = cur.fetchone()
                acquired = bool(row and row.get("ok"))
            conn.commit()
            yield acquired
        finally:
            if acquired:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT pg_advisory_unlock(%s)", (key,))
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    log.warning("advisory_unlock failed: %s", exc)


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
