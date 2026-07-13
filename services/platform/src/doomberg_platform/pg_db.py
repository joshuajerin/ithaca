"""Postgres-backed platform database adapter.

The store modules intentionally speak a small sqlite3-like surface: ``conn.execute()``,
``with conn:``, row objects indexable by column name, and ``write_lock``. This adapter keeps
that surface while putting production state in Postgres. Local/dev can continue to use the
SQLite ``Db`` implementation from :mod:`doomberg_platform.db`.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .migrations import MigrationStatus, apply_migrations, validate_migrations

TRACE_CHANNEL = "doomberg_trace_events"


def is_postgres_dsn(path: Any) -> bool:
    return isinstance(path, str) and path.startswith(("postgres://", "postgresql://"))


def _convert_placeholders(sql: str) -> str:
    """Translate sqlite ``?`` placeholders to psycopg ``%s`` placeholders."""
    out: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            out.append(ch)
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append(sql[i + 1])
                i += 2
                continue
            in_single = not in_single
        elif ch == '"' and not in_single:
            out.append(ch)
            in_double = not in_double
        elif ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _loads(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def _trace_row_to_event(row: Any) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "seq": row["seq"],
        "ts": row["ts"],
        "type": row["type"],
        "tenant_id": row["tenant_id"],
        "session_id": row["session_id"],
        "origin_session_id": row["origin_session_id"],
        "span_id": row["span_id"],
        "parent_span_id": row["parent_span_id"],
        "actor": _loads(row["actor"], None),
        "data": _loads(row["data"], {}),
    }


class _PostgresConnection:
    """sqlite3-compatible facade over one psycopg connection."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn
        self._lock = threading.RLock()
        self._depth = 0

    def __enter__(self) -> "_PostgresConnection":
        self._lock.acquire()
        self._depth += 1
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        try:
            if self._depth == 1:
                if exc_type is None:
                    self._conn.commit()
                else:
                    self._conn.rollback()
        finally:
            self._depth -= 1
            self._lock.release()
        return False

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] | None = None) -> Any:
        converted = _convert_placeholders(sql)
        bind = tuple(params or ())
        with self._lock:
            try:
                cur = self._conn.execute(converted, bind)
                if self._depth == 0:
                    self._conn.commit()
                return cur
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class PostgresDb:
    """Shared Postgres handle with the same public surface as ``Db``."""

    is_postgres = True

    def __init__(self, dsn: str) -> None:
        self.path = dsn
        self.dsn = dsn
        self.write_lock = threading.RLock()
        self._conn = psycopg.connect(dsn, row_factory=dict_row)
        self._facade = _PostgresConnection(self._conn)
        self._migration_status = self._migrate()

    @property
    def conn(self) -> _PostgresConnection:
        return self._facade

    @property
    def migration_status(self) -> MigrationStatus:
        return self._migration_status

    def _migrate(self) -> MigrationStatus:
        mode = migration_mode()
        allow_forward = allow_forward_migrations()
        with self.conn as conn:
            if mode == "apply":
                return apply_migrations(conn, allow_forward=allow_forward)
            if mode == "validate":
                return validate_migrations(conn, allow_forward=allow_forward)
        return MigrationStatus(current_version=0, latest_version=0, pending_versions=())

    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        payload = json.dumps({"run_id": str(run_id), "seq": int(event["seq"])})
        try:
            self.conn.execute("SELECT pg_notify(?, ?)", (TRACE_CHANNEL, payload))
        except Exception:
            # The event is already durable. A notification failure should not turn a
            # committed trace append into an application-level write failure.
            return

    def subscribe(self, run_id: str, after_seq: int = -1) -> Iterator[dict[str, Any]]:
        run_id = str(run_id)
        last_seq = int(after_seq)
        listen_conn = psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row)
        try:
            listen_conn.execute(f"LISTEN {TRACE_CHANNEL}")
            while True:
                for event in self._events_after_run(run_id, last_seq):
                    last_seq = int(event["seq"])
                    yield event

                for notify in listen_conn.notifies(timeout=30.0, stop_after=1):
                    try:
                        payload = json.loads(notify.payload)
                    except json.JSONDecodeError:
                        continue
                    if payload.get("run_id") != run_id:
                        continue
                    break
        finally:
            listen_conn.close()

    def _events_after_run(self, run_id: str, after_seq: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM trace_events WHERE run_id = ? AND seq > ? ORDER BY seq ASC",
            (run_id, int(after_seq)),
        ).fetchall()
        return [_trace_row_to_event(row) for row in rows]

    def close(self) -> None:
        with self.write_lock:
            self._facade.close()


def migration_mode() -> str:
    import os

    mode = os.environ.get("DOOMBERG_DB_MIGRATION_MODE", "apply").strip().lower()
    if mode not in {"apply", "validate", "off"}:
        raise ValueError("DOOMBERG_DB_MIGRATION_MODE must be apply, validate, or off")
    return mode


def allow_forward_migrations() -> bool:
    import os

    value = os.environ.get("DOOMBERG_DB_ALLOW_FORWARD_MIGRATIONS", "0").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(
        "DOOMBERG_DB_ALLOW_FORWARD_MIGRATIONS must be a boolean value"
    )
