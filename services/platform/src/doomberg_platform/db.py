"""SQLite-backed handle shared by the platform stores.

`open_db(path|":memory:")` returns a :class:`Db` handle the stores share. The handle
owns the connection, the schema, a per-process write lock (SQLite is single-writer), and
an in-process pub/sub registry used by :class:`~doomberg_platform.trace_store.TraceStore`
to deliver a live tail to SSE subscribers.

Local-only design notes (read before swapping to Postgres):
- The in-process pub/sub (a per-run :class:`threading.Condition` over an in-memory list of
  recent events) stands in for Postgres ``LISTEN``/``NOTIFY``. In prod, ``subscribe`` becomes
  a ``LISTEN`` on a per-run channel and replay reads from the durable table; the public
  signatures here do not change.
- A single :class:`threading.RLock` serializes all writes. SQLite only allows one writer at a
  time; centralizing it here lets ``TraceStore.append`` compute a gap-free seq inside one
  transaction without racing other writers (runs, strategies) on the same connection.
"""

from __future__ import annotations

import sqlite3
import threading
from collections import defaultdict
from collections.abc import Iterator
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    tenant_id   TEXT NOT NULL,
    run_id      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    strategy_id TEXT,
    state       TEXT NOT NULL,
    version     INTEGER NOT NULL,
    spec        TEXT,
    result      TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id)
);

-- One immutable row per (strategy_id, version); same name -> new version, never updated.
CREATE TABLE IF NOT EXISTS strategies (
    tenant_id   TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    name        TEXT NOT NULL,
    version     INTEGER NOT NULL,
    spec        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (tenant_id, strategy_id, version)
);

CREATE INDEX IF NOT EXISTS idx_strategies_name
    ON strategies (tenant_id, name, version);

CREATE TABLE IF NOT EXISTS trace_events (
    tenant_id         TEXT NOT NULL,
    run_id            TEXT NOT NULL,
    seq               INTEGER NOT NULL,
    ts                TEXT NOT NULL,
    type              TEXT NOT NULL,
    session_id        TEXT,
    origin_session_id TEXT,
    span_id           TEXT,
    parent_span_id    TEXT,
    actor             TEXT,
    data              TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_trace_tenant_run
    ON trace_events (tenant_id, run_id, seq);

-- Per-run gap-free seq counter. The single writer bumps next_seq inside the same
-- transaction that inserts the event, so seq is gap-free even under concurrent appends.
CREATE TABLE IF NOT EXISTS run_seq (
    run_id   TEXT PRIMARY KEY,
    next_seq INTEGER NOT NULL
);

-- The paper position book a live deployment holds. One row per (tenant, run); the control
-- plane is the single writer and bumps version on every apply (optimistic concurrency).
CREATE TABLE IF NOT EXISTS books (
    tenant_id  TEXT NOT NULL,
    run_id     TEXT NOT NULL,
    capital    REAL NOT NULL,
    weights    TEXT NOT NULL,
    marks      TEXT NOT NULL,
    version    INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id)
);

-- The front-door account model: a tenant owns API keys. Only the salted sha256 of the
-- secret is ever stored; the plaintext key (dmbg_<env>_<keyid>_<secret>) is shown ONCE at
-- mint time and is unrecoverable thereafter. Revocation is a soft flag (audit-preserving).
CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_id      TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    secret_hash TEXT NOT NULL,
    salt        TEXT NOT NULL,
    scopes      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_api_keys_tenant
    ON api_keys (tenant_id);

-- Human user accounts (email/password + OAuth). One row per real person.
-- Password auth: pbkdf2_hmac sha256, only password_hash+password_salt stored.
-- OAuth auth: linked via oauth_accounts; password_hash/salt are NULL for OAuth-only users.
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    avatar_url    TEXT,
    tenant_id     TEXT NOT NULL,
    password_hash TEXT,
    password_salt TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users (tenant_id);

-- OAuth provider links: one row per (user_id, provider). Lets a user connect
-- multiple providers to the same account.
CREATE TABLE IF NOT EXISTS oauth_accounts (
    user_id     TEXT NOT NULL,
    provider    TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    email       TEXT,
    name        TEXT,
    avatar_url  TEXT,
    linked_at   TEXT NOT NULL,
    PRIMARY KEY (provider, provider_id)
);

CREATE INDEX IF NOT EXISTS idx_oauth_user ON oauth_accounts (user_id);

-- Short-lived session tokens (JWT-ish: signed with HMAC-SHA256).
-- The token value in the token column is already hashed; the signed JWT is
-- handed to the browser and never stored raw.
CREATE TABLE IF NOT EXISTS user_sessions (
    session_id TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions (user_id);
"""


class _RunChannel:
    """Live tail buffer + condition for one run (in-proc pub/sub)."""

    __slots__ = ("cond", "events")

    def __init__(self) -> None:
        self.cond = threading.Condition()
        # Recent events kept in order; subscribers index forward from their cursor.
        self.events: list[dict[str, Any]] = []


class Db:
    """Shared SQLite handle: connection + write lock + in-proc pub/sub registry."""

    def __init__(self, path: str) -> None:
        self.path = path
        # check_same_thread=False so the SSE subscribe thread can read; all writes are
        # funneled through `write_lock`, and reads are serialized by SQLite itself.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.write_lock = threading.RLock()
        self._channels: dict[str, _RunChannel] = defaultdict(_RunChannel)
        self._channels_lock = threading.Lock()
        with self._conn:
            self._conn.executescript(_SCHEMA)

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def _channel(self, run_id: str) -> _RunChannel:
        with self._channels_lock:
            return self._channels[run_id]

    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        """Notify live subscribers of `run_id` that a new event landed."""
        ch = self._channel(run_id)
        with ch.cond:
            ch.events.append(event)
            ch.cond.notify_all()

    def subscribe(self, run_id: str, after_seq: int = -1) -> Iterator[dict[str, Any]]:
        """Yield live events for `run_id` with seq > after_seq, blocking for new ones.

        Local in-process stand-in for Postgres LISTEN/NOTIFY. Replay-from-seq for
        historical events is the store's job; this only tails what is published live.
        """
        ch = self._channel(run_id)
        cursor = 0
        last_seq = after_seq
        while True:
            with ch.cond:
                while cursor >= len(ch.events):
                    ch.cond.wait()
                pending = ch.events[cursor:]
                cursor = len(ch.events)
            for ev in pending:
                if int(ev["seq"]) > last_seq:
                    last_seq = int(ev["seq"])
                    yield ev

    def close(self) -> None:
        with self.write_lock:
            self._conn.close()


def open_db(path: str = ":memory:") -> Db:
    """Open (or create) the shared platform database.

    `path` is a filesystem path or ``":memory:"``. The returned handle is shared by
    :class:`TraceStore`, :class:`RunStore`, and :class:`StrategyStore`.
    """
    return Db(path)
