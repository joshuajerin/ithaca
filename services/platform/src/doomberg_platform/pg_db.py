"""Postgres-backed platform database adapter.

The store modules intentionally speak a small sqlite3-like surface: ``conn.execute()``,
``with conn:``, row objects indexable by column name, and ``write_lock``. This adapter keeps
that surface while putting production state in Postgres. Local/dev can continue to use the
SQLite ``Db`` implementation from :mod:`doomberg_platform.db`.
"""

from __future__ import annotations

import json
import math
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from .migrations import MigrationStatus, apply_migrations, validate_migrations

TRACE_CHANNEL = "doomberg_trace_events"


@dataclass(frozen=True)
class PostgresPoolConfig:
    min_size: int = 1
    max_size: int = 4
    timeout_seconds: float = 10.0
    max_lifetime_seconds: float = 1800.0
    max_idle_seconds: float = 300.0
    reconnect_timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "PostgresPoolConfig":
        config = cls(
            min_size=_env_int("DOOMBERG_POSTGRES_POOL_MIN", cls.min_size),
            max_size=_env_int("DOOMBERG_POSTGRES_POOL_MAX", cls.max_size),
            timeout_seconds=_env_float("DOOMBERG_POSTGRES_POOL_TIMEOUT_S", cls.timeout_seconds),
            max_lifetime_seconds=_env_float(
                "DOOMBERG_POSTGRES_POOL_MAX_LIFETIME_S", cls.max_lifetime_seconds
            ),
            max_idle_seconds=_env_float(
                "DOOMBERG_POSTGRES_POOL_MAX_IDLE_S", cls.max_idle_seconds
            ),
            reconnect_timeout_seconds=_env_float(
                "DOOMBERG_POSTGRES_RECONNECT_TIMEOUT_S", cls.reconnect_timeout_seconds
            ),
        )
        if config.min_size > config.max_size:
            raise ValueError("DOOMBERG_POSTGRES_POOL_MIN cannot exceed POOL_MAX")
        return config


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        value = default if raw is None else int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        value = default if raw is None else float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return value


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


class _DetachedResult:
    """Cursor-shaped result that no longer owns a pooled connection."""

    def __init__(self, rows: list[Any], rowcount: int) -> None:
        self._rows = rows
        self._index = 0
        self.rowcount = rowcount

    def fetchone(self) -> Any | None:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self) -> list[Any]:
        rows = self._rows[self._index :]
        self._index = len(self._rows)
        return rows


@dataclass
class _TransactionState:
    context: Any
    connection: psycopg.Connection[Any]
    depth: int = 1
    configured_scope: tuple[str, str] | None = None


@dataclass(frozen=True)
class _AccessScope:
    mode: str
    tenant_id: str = ""


@dataclass
class _RunSignal:
    condition: threading.Condition
    version: int = 0
    subscribers: int = 0


class _PostgresConnection:
    """sqlite3-compatible facade over a thread-safe psycopg connection pool."""

    def __init__(
        self,
        pool: ConnectionPool[Any],
        *,
        timeout_seconds: float,
        access_scope: ContextVar[_AccessScope | None],
    ) -> None:
        self._pool = pool
        self._timeout_seconds = timeout_seconds
        self._access_scope = access_scope
        self._local = threading.local()

    def __enter__(self) -> "_PostgresConnection":
        state = self._state()
        if state is not None:
            state.depth += 1
            return self
        context = self._pool.connection(timeout=self._timeout_seconds)
        connection = context.__enter__()
        self._local.state = _TransactionState(context=context, connection=connection)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        state = self._state()
        if state is None:
            raise RuntimeError("Postgres connection context exited without entering")
        state.depth -= 1
        if state.depth > 0:
            return False
        del self._local.state
        return bool(state.context.__exit__(exc_type, exc, tb))

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] | None = None) -> Any:
        converted = _convert_placeholders(sql)
        bind = tuple(params or ())
        state = self._state()
        if state is not None:
            self._configure(state.connection, state)
            return state.connection.execute(converted, bind)
        with self._pool.connection(timeout=self._timeout_seconds) as connection:
            self._configure(connection)
            cursor = connection.execute(converted, bind)
            rows = cursor.fetchall() if cursor.description is not None else []
            return _DetachedResult(rows, cursor.rowcount)

    def _state(self) -> _TransactionState | None:
        return getattr(self._local, "state", None)

    def _configure(
        self,
        connection: psycopg.Connection[Any], state: _TransactionState | None = None
    ) -> None:
        access = self._access_scope.get()
        scope = (
            access.tenant_id if access and access.mode == "tenant" else "",
            "on" if access and access.mode == "system" else "off",
        )
        if state is not None and state.configured_scope == scope:
            return
        connection.execute(
            "SELECT set_config('doomberg.tenant_id', %s, true), "
            "set_config('doomberg.system_access', %s, true)",
            scope,
        )
        if state is not None:
            state.configured_scope = scope


class PostgresDb:
    """Shared Postgres handle with the same public surface as ``Db``."""

    is_postgres = True

    def __init__(self, dsn: str, *, pool_config: PostgresPoolConfig | None = None) -> None:
        self.path = dsn
        self.dsn = dsn
        self.write_lock = threading.RLock()
        self._closed = threading.Event()
        self._signals_lock = threading.Lock()
        self._signals: dict[str, _RunSignal] = {}
        self._listener_lock = threading.Lock()
        self._listener_thread: threading.Thread | None = None
        self._access_scope: ContextVar[_AccessScope | None] = ContextVar(
            f"doomberg_database_access_scope_{id(self)}", default=None
        )
        self.pool_config = pool_config or PostgresPoolConfig.from_env()
        self._pool = ConnectionPool(
            conninfo=dsn,
            name="doomberg-platform",
            min_size=self.pool_config.min_size,
            max_size=self.pool_config.max_size,
            timeout=self.pool_config.timeout_seconds,
            max_lifetime=self.pool_config.max_lifetime_seconds,
            max_idle=self.pool_config.max_idle_seconds,
            reconnect_timeout=self.pool_config.reconnect_timeout_seconds,
            kwargs={
                "row_factory": dict_row,
                "application_name": "doomberg-platform",
                "connect_timeout": max(1, math.ceil(self.pool_config.timeout_seconds)),
            },
            check=ConnectionPool.check_connection,
            open=True,
        )
        try:
            self._pool.wait(timeout=self.pool_config.timeout_seconds)
            self._facade = _PostgresConnection(
                self._pool,
                timeout_seconds=self.pool_config.timeout_seconds,
                access_scope=self._access_scope,
            )
            self._migration_status = self._migrate()
        except Exception:
            self._pool.close()
            raise

    @property
    def conn(self) -> _PostgresConnection:
        return self._facade

    @property
    def migration_status(self) -> MigrationStatus:
        return self._migration_status

    @property
    def pool_stats(self) -> dict[str, int]:
        return dict(self._pool.get_stats())

    @contextmanager
    def tenant_scope(self, tenant_id: str) -> Iterator[None]:
        tenant_id = str(tenant_id).strip()
        if not tenant_id:
            raise ValueError("tenant database scope requires a tenant id")
        current = self._access_scope.get()
        if current is not None and current.mode == "tenant" and current.tenant_id != tenant_id:
            raise RuntimeError("cannot switch tenant inside an active tenant database scope")
        token = self._access_scope.set(_AccessScope("tenant", tenant_id))
        try:
            yield
        finally:
            self._access_scope.reset(token)

    @contextmanager
    def system_scope(self) -> Iterator[None]:
        current = self._access_scope.get()
        if current is not None and current.mode == "tenant":
            raise RuntimeError("cannot elevate a tenant database scope to system access")
        token = self._access_scope.set(_AccessScope("system"))
        try:
            yield
        finally:
            self._access_scope.reset(token)

    def _migrate(self) -> MigrationStatus:
        mode = migration_mode()
        allow_forward = allow_forward_migrations()
        with self.system_scope(), self.conn as conn:
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
            pass
        self._wake_subscribers(str(run_id))

    def subscribe(
        self, tenant_id: str, run_id: str, after_seq: int = -1
    ) -> Iterator[dict[str, Any]]:
        tenant_id = str(tenant_id)
        run_id = str(run_id)
        last_seq = int(after_seq)
        signal = self._acquire_signal(run_id)
        self._ensure_listener()
        try:
            while not self._closed.is_set():
                with signal.condition:
                    observed_version = signal.version
                for event in self._events_after_run(tenant_id, run_id, last_seq):
                    last_seq = int(event["seq"])
                    yield event
                with signal.condition:
                    if signal.version == observed_version and not self._closed.is_set():
                        signal.condition.wait(timeout=1.0)
        finally:
            self._release_signal(run_id, signal)

    def _ensure_listener(self) -> None:
        with self._listener_lock:
            if self._listener_thread is not None and self._listener_thread.is_alive():
                return
            if self._closed.is_set():
                return
            self._listener_thread = threading.Thread(
                target=self._listen_for_notifications,
                name="doomberg-postgres-listener",
                daemon=True,
            )
            self._listener_thread.start()

    def _listen_for_notifications(self) -> None:
        retry_seconds = 1.0
        while not self._closed.is_set():
            try:
                with psycopg.connect(
                    self.dsn,
                    autocommit=True,
                    row_factory=dict_row,
                    application_name="doomberg-listener",
                    connect_timeout=max(1, math.ceil(self.pool_config.timeout_seconds)),
                ) as listen_conn:
                    listen_conn.execute(f"LISTEN {TRACE_CHANNEL}")
                    retry_seconds = 1.0
                    while not self._closed.is_set():
                        for notify in listen_conn.notifies(timeout=1.0, stop_after=1):
                            try:
                                payload = json.loads(notify.payload)
                            except json.JSONDecodeError:
                                continue
                            if not isinstance(payload, dict):
                                continue
                            run_id = payload.get("run_id")
                            if isinstance(run_id, str):
                                self._wake_subscribers(run_id)
            except (psycopg.OperationalError, psycopg.InterfaceError, PoolTimeout):
                if self._closed.wait(retry_seconds):
                    return
                retry_seconds = min(retry_seconds * 2, 30.0)

    def _acquire_signal(self, run_id: str) -> _RunSignal:
        with self._signals_lock:
            signal = self._signals.get(run_id)
            if signal is None:
                signal = _RunSignal(condition=threading.Condition())
                self._signals[run_id] = signal
            signal.subscribers += 1
            return signal

    def _release_signal(self, run_id: str, signal: _RunSignal) -> None:
        with self._signals_lock:
            signal.subscribers -= 1
            if signal.subscribers == 0 and self._signals.get(run_id) is signal:
                del self._signals[run_id]

    def _wake_subscribers(self, run_id: str) -> None:
        with self._signals_lock:
            signal = self._signals.get(run_id)
        if signal is None:
            return
        with signal.condition:
            signal.version += 1
            signal.condition.notify_all()

    def _events_after_run(
        self, tenant_id: str, run_id: str, after_seq: int
    ) -> list[dict[str, Any]]:
        with self.tenant_scope(tenant_id):
            rows = self.conn.execute(
                "SELECT * FROM trace_events "
                "WHERE tenant_id = ? AND run_id = ? AND seq > ? ORDER BY seq ASC",
                (tenant_id, run_id, int(after_seq)),
            ).fetchall()
        return [_trace_row_to_event(row) for row in rows]

    def close(self) -> None:
        with self.write_lock:
            self._closed.set()
            with self._signals_lock:
                signals = tuple(self._signals.values())
            for signal in signals:
                with signal.condition:
                    signal.condition.notify_all()
            self._pool.close()
            listener = self._listener_thread
            if listener is not None and listener is not threading.current_thread():
                listener.join(timeout=2.0)


def migration_mode() -> str:
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
