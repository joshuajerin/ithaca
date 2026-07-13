"""Postgres-backed platform database adapter.

The store modules intentionally speak a small sqlite3-like surface: ``conn.execute()``,
``with conn:``, row objects indexable by column name, and ``write_lock``. This adapter keeps
that surface while putting production state in Postgres. Local/dev can continue to use the
SQLite ``Db`` implementation from :mod:`doomberg_platform.db`.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .db import _SCHEMA

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


def _schema_statements(script: str) -> Iterator[str]:
    lines = [
        line for line in script.splitlines()
        if not line.strip().startswith("--")
    ]
    for raw in "\n".join(lines).split(";"):
        stmt = raw.strip()
        if stmt:
            yield stmt


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
        self._migrate()

    @property
    def conn(self) -> _PostgresConnection:
        return self._facade

    def _migrate(self) -> None:
        with self.conn as conn:
            for stmt in _schema_statements(_SCHEMA):
                conn.execute(stmt)
            if _env_flag("DOOMBERG_POSTGRES_ENABLE_RLS"):
                self._enable_rls(conn)

    def _enable_rls(self, conn: _PostgresConnection) -> None:
        for table in _TENANT_TABLES:
            conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            if _env_flag("DOOMBERG_POSTGRES_FORCE_RLS"):
                conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            conn.execute(f"DROP POLICY IF EXISTS doomberg_tenant_isolation ON {table}")
            conn.execute(
                f"CREATE POLICY doomberg_tenant_isolation ON {table} "
                "USING (tenant_id = current_setting('doomberg.tenant_id', true)) "
                "WITH CHECK (tenant_id = current_setting('doomberg.tenant_id', true))"
            )

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


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


_TENANT_TABLES = (
    "runs",
    "strategies",
    "trace_events",
    "books",
    "api_keys",
    "users",
    "sse_tickets",
    "jobs",
    "adaptive_dashboard_profiles",
    "artifacts",
    "approvals",
    "provider_connections",
    "dataset_snapshots",
    "trigger_policies",
    "trigger_firings",
    "trigger_baselines",
    "notification_outbox",
    "delivery_targets",
    "notification_attempts",
    "order_intents",
    "orders",
    "fills",
    "feedback",
)
