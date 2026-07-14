"""SQLite-backed local handle shared by the platform stores.

`open_db(path|":memory:")` returns a :class:`Db` handle the stores share. The handle
owns the connection, the schema, a per-process write lock (SQLite is single-writer), and
an in-process pub/sub registry used by :class:`~ithaca_platform.trace_store.TraceStore`
to deliver a live tail to SSE subscribers.

Local design notes:
- The in-process pub/sub (a per-run :class:`threading.Condition` over an in-memory list of
  recent events) is only for SQLite/local. Postgres uses a compatible adapter with durable
  replay plus ``LISTEN``/``NOTIFY``; the public signatures here do not change.
- A single :class:`threading.RLock` serializes all writes. SQLite only allows one writer at a
  time; centralizing it here lets ``TraceStore.append`` compute a gap-free seq inside one
  transaction without racing other writers (runs, strategies) on the same connection.
"""

from __future__ import annotations

import sqlite3
import threading
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

# Version 1 of the platform schema. This string is a migration artifact: do not
# edit it in place. Add a new migration in ``migrations.py`` for every schema
# change so existing Postgres installations have an ordered upgrade path.
_BASELINE_SCHEMA = """
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

CREATE INDEX IF NOT EXISTS idx_runs_tenant_updated
    ON runs (tenant_id, updated_at DESC, run_id DESC);

CREATE INDEX IF NOT EXISTS idx_runs_tenant_kind_updated
    ON runs (tenant_id, kind, updated_at DESC, run_id DESC);

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
-- secret is ever stored; the plaintext key (ith_<env>_<keyid>_<secret>) is shown ONCE at
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

-- Short-lived one-time bearer tickets for browser EventSource connections.
-- EventSource cannot send Authorization headers; these tickets are minted over normal
-- authenticated REST, scoped to one tenant/run, and consumed by the SSE route. Only a
-- SHA-256 hash of the ticket secret is persisted.
CREATE TABLE IF NOT EXISTS sse_tickets (
    ticket_id   TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    run_id      TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    secret_hash TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_sse_tickets_tenant_run
    ON sse_tickets (tenant_id, run_id, expires_at);

-- Durable compute jobs. A run can own multiple jobs over time, but the first cut creates
-- one job per queued run. The lease columns let workers recover jobs abandoned by a dead
-- worker without relying on an MCP/client process staying alive.
CREATE TABLE IF NOT EXISTS jobs (
    tenant_id          TEXT NOT NULL,
    job_id             TEXT NOT NULL,
    run_id             TEXT NOT NULL,
    kind               TEXT NOT NULL,
    profile            TEXT NOT NULL,
    state              TEXT NOT NULL,
    payload            TEXT NOT NULL,
    idempotency_key    TEXT,
    attempts           INTEGER NOT NULL DEFAULT 0,
    max_attempts       INTEGER NOT NULL DEFAULT 3,
    worker_id          TEXT,
    lease_expires_at   TEXT,
    heartbeat_at       TEXT,
    checkpoint_ref     TEXT,
    result             TEXT,
    error              TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    PRIMARY KEY (tenant_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_run
    ON jobs (tenant_id, run_id, created_at);

CREATE INDEX IF NOT EXISTS idx_jobs_claim
    ON jobs (state, profile, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idempotency
    ON jobs (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Cross-process leadership leases for active worker loops such as trigger polling and
-- paper scheduling. These are infrastructure rows, not tenant data: every replica can
-- attempt to renew, but only the current owner can run the singleton loop until the
-- lease expires or is released.
CREATE TABLE IF NOT EXISTS worker_leases (
    lease_name       TEXT PRIMARY KEY,
    owner_id         TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    heartbeat_at     TEXT NOT NULL,
    metadata         TEXT NOT NULL,
    version          INTEGER NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_worker_leases_expires
    ON worker_leases (lease_expires_at);

-- Per signed-in user adaptive dashboard profile. The spec is strict JSON over a
-- server-side widget allowlist; no generated code or browser-exposed model output
-- is stored here.
CREATE TABLE IF NOT EXISTS adaptive_dashboard_profiles (
    tenant_id            TEXT NOT NULL,
    user_id              TEXT NOT NULL,
    spec                 TEXT NOT NULL,
    model                TEXT NOT NULL,
    source_session_count INTEGER NOT NULL,
    source_event_count   INTEGER NOT NULL,
    generated_for_date   TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_adaptive_dashboard_profiles_date
    ON adaptive_dashboard_profiles (generated_for_date, tenant_id, user_id);

-- Large outputs live outside trace_events; trace rows point at artifact ids.
CREATE TABLE IF NOT EXISTS artifacts (
    tenant_id    TEXT NOT NULL,
    artifact_id  TEXT NOT NULL,
    run_id       TEXT NOT NULL,
    job_id       TEXT,
    kind         TEXT NOT NULL,
    uri          TEXT NOT NULL,
    media_type   TEXT,
    bytes        INTEGER,
    metadata     TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (tenant_id, artifact_id)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_run
    ON artifacts (tenant_id, run_id, created_at);

-- Approval records for future risk-gated execution and trigger workflows.
CREATE TABLE IF NOT EXISTS approvals (
    tenant_id     TEXT NOT NULL,
    approval_id   TEXT NOT NULL,
    run_id        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    state         TEXT NOT NULL,
    request       TEXT NOT NULL,
    decision      TEXT,
    requested_by  TEXT,
    decided_by    TEXT,
    expires_at    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (tenant_id, approval_id)
);

CREATE INDEX IF NOT EXISTS idx_approvals_run
    ON approvals (tenant_id, run_id, created_at);

CREATE INDEX IF NOT EXISTS idx_approvals_state
    ON approvals (tenant_id, state, created_at);

-- Provider/data entitlement state. Credentials stay outside this table; credential_ref
-- points to Keychain/secret-manager/libsecret/etc.
CREATE TABLE IF NOT EXISTS provider_connections (
    tenant_id          TEXT NOT NULL,
    connection_id      TEXT NOT NULL,
    provider           TEXT NOT NULL,
    account_ref        TEXT,
    credential_ref     TEXT,
    state              TEXT NOT NULL,
    capabilities       TEXT NOT NULL,
    entitlements       TEXT NOT NULL,
    retention_policy   TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    PRIMARY KEY (tenant_id, connection_id)
);

CREATE INDEX IF NOT EXISTS idx_provider_connections_provider
    ON provider_connections (tenant_id, provider, state);

CREATE TABLE IF NOT EXISTS dataset_snapshots (
    tenant_id          TEXT NOT NULL,
    snapshot_id        TEXT NOT NULL,
    provider           TEXT NOT NULL,
    dataset            TEXT NOT NULL,
    entitlement_class  TEXT NOT NULL,
    as_of              TEXT NOT NULL,
    uri                TEXT,
    manifest           TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    PRIMARY KEY (tenant_id, snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_dataset_snapshots_lookup
    ON dataset_snapshots (tenant_id, provider, dataset, as_of);

-- Trigger policy skeleton for the next phase. The policy document is typed at the
-- contract layer; this table gives the control plane a durable home for it.
CREATE TABLE IF NOT EXISTS trigger_policies (
    tenant_id    TEXT NOT NULL,
    trigger_id   TEXT NOT NULL,
    name         TEXT NOT NULL,
    state        TEXT NOT NULL,
    policy       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (tenant_id, trigger_id)
);

CREATE INDEX IF NOT EXISTS idx_trigger_policies_state
    ON trigger_policies (tenant_id, state, name);

CREATE INDEX IF NOT EXISTS idx_trigger_policies_recent
    ON trigger_policies (tenant_id, updated_at DESC, trigger_id DESC);

-- Trigger firings are the stateful dedupe/cooldown/budget memory for the trigger engine.
-- They deliberately point at the run created by the trigger, so Sessions can replay the
-- exact market event -> analysis run lineage.
CREATE TABLE IF NOT EXISTS trigger_firings (
    tenant_id    TEXT NOT NULL,
    firing_id    TEXT NOT NULL,
    trigger_id   TEXT NOT NULL,
    run_id       TEXT NOT NULL,
    dedupe_key   TEXT,
    event_time   TEXT NOT NULL,
    payload      TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (tenant_id, firing_id)
);

CREATE INDEX IF NOT EXISTS idx_trigger_firings_lookup
    ON trigger_firings (tenant_id, trigger_id, dedupe_key, event_time);

-- Trigger baselines let percentage-move policies compare a live quote against a durable
-- reference such as a fixed price, last firing, or first snapshot captured at activation.
CREATE TABLE IF NOT EXISTS trigger_baselines (
    tenant_id       TEXT NOT NULL,
    trigger_id      TEXT NOT NULL,
    baseline_key    TEXT NOT NULL,
    baseline_type   TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    price           REAL NOT NULL,
    baseline_time   TEXT NOT NULL,
    trading_day     TEXT NOT NULL,
    payload         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (tenant_id, trigger_id, baseline_key)
);

CREATE INDEX IF NOT EXISTS idx_trigger_baselines_lookup
    ON trigger_baselines (tenant_id, trigger_id, symbol, baseline_type);

-- Durable notification outbox. Trigger detection writes here; worker delivery is retried
-- independently of MCP/WebSocket/client availability.
CREATE TABLE IF NOT EXISTS notification_outbox (
    tenant_id          TEXT NOT NULL,
    notification_id    TEXT NOT NULL,
    event_type         TEXT NOT NULL,
    subject_type       TEXT NOT NULL,
    subject_id         TEXT NOT NULL,
    priority           TEXT NOT NULL,
    state              TEXT NOT NULL,
    dedupe_key         TEXT,
    payload            TEXT NOT NULL,
    attempts           INTEGER NOT NULL DEFAULT 0,
    max_attempts       INTEGER NOT NULL DEFAULT 10,
    next_attempt_at    TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    sent_at            TEXT,
    PRIMARY KEY (tenant_id, notification_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_dedupe
    ON notification_outbox (tenant_id, dedupe_key)
    WHERE dedupe_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_notification_claim
    ON notification_outbox (state, next_attempt_at, created_at);

CREATE INDEX IF NOT EXISTS idx_notification_tenant_recent
    ON notification_outbox (tenant_id, created_at DESC, notification_id DESC);

CREATE TABLE IF NOT EXISTS delivery_targets (
    tenant_id       TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    kind            TEXT NOT NULL,
    state           TEXT NOT NULL,
    config          TEXT NOT NULL,
    secret_ref      TEXT,
    capabilities    TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (tenant_id, target_id)
);

CREATE INDEX IF NOT EXISTS idx_delivery_targets_kind
    ON delivery_targets (tenant_id, kind, state);

CREATE TABLE IF NOT EXISTS notification_attempts (
    tenant_id        TEXT NOT NULL,
    attempt_id       TEXT NOT NULL,
    notification_id  TEXT NOT NULL,
    target_id        TEXT NOT NULL,
    state            TEXT NOT NULL,
    request          TEXT NOT NULL,
    response         TEXT,
    error            TEXT,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (tenant_id, attempt_id)
);

CREATE INDEX IF NOT EXISTS idx_notification_attempts_notification
    ON notification_attempts (tenant_id, notification_id, created_at);

-- Execution records. Broker writes must pass through the deterministic execution gateway;
-- these rows establish the order-intent, broker-order, and fill audit surface.
CREATE TABLE IF NOT EXISTS order_intents (
    tenant_id        TEXT NOT NULL,
    intent_id        TEXT NOT NULL,
    run_id           TEXT NOT NULL,
    strategy_id      TEXT,
    account_ref      TEXT,
    state            TEXT NOT NULL,
    payload          TEXT NOT NULL,
    risk_decision    TEXT,
    idempotency_key  TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (tenant_id, intent_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_order_intents_idempotency
    ON order_intents (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS orders (
    tenant_id        TEXT NOT NULL,
    order_id         TEXT NOT NULL,
    intent_id        TEXT NOT NULL,
    broker           TEXT NOT NULL,
    broker_order_id  TEXT,
    client_order_id  TEXT NOT NULL,
    state            TEXT NOT NULL,
    payload          TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_client_order
    ON orders (tenant_id, broker, client_order_id);

CREATE TABLE IF NOT EXISTS fills (
    tenant_id        TEXT NOT NULL,
    fill_id          TEXT NOT NULL,
    order_id         TEXT NOT NULL,
    broker_fill_id   TEXT,
    payload          TEXT NOT NULL,
    event_time       TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (tenant_id, fill_id)
);

CREATE INDEX IF NOT EXISTS idx_fills_order
    ON fills (tenant_id, order_id, event_time);

-- Product feedback submitted by signed-in humans from the web rail.
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_tenant_created
    ON feedback (tenant_id, created_at);
"""

# Portable post-baseline evolutions for SQLite local/dev. PostgreSQL applies the
# equivalent statements through the ordered migration manifest.
_LOCAL_SCHEMA_EVOLUTIONS = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_broker_order
    ON orders (tenant_id, broker, broker_order_id)
    WHERE broker_order_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_fills_broker_fill
    ON fills (tenant_id, broker_fill_id)
    WHERE broker_fill_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS execution_controls (
    tenant_id   TEXT PRIMARY KEY,
    enabled     INTEGER NOT NULL DEFAULT 0,
    reason      TEXT,
    updated_by  TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_control_events (
    tenant_id   TEXT NOT NULL,
    event_id    TEXT NOT NULL,
    enabled     INTEGER NOT NULL,
    reason      TEXT,
    actor_id    TEXT NOT NULL,
    version     INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_execution_control_events_tenant
    ON execution_control_events (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS compliance_policies (
    tenant_id   TEXT PRIMARY KEY,
    limits      TEXT NOT NULL,
    limits_enforced INTEGER NOT NULL DEFAULT 0,
    restricted  TEXT NOT NULL,
    watch       TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS compliance_policy_events (
    tenant_id   TEXT NOT NULL,
    event_id    TEXT NOT NULL,
    action      TEXT NOT NULL,
    payload     TEXT NOT NULL,
    actor_id    TEXT NOT NULL,
    version     INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_compliance_policy_events_tenant
    ON compliance_policy_events (tenant_id, version DESC);

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id    TEXT NOT NULL,
    role         TEXT NOT NULL,
    status       TEXT NOT NULL,
    detail       TEXT,
    metadata     TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (worker_id, role)
);

CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_role_expiry
    ON worker_heartbeats (role, expires_at DESC);
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

    is_postgres = False

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
            self._conn.executescript(_BASELINE_SCHEMA)
            self._conn.executescript(_LOCAL_SCHEMA_EVOLUTIONS)

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    @contextmanager
    def tenant_scope(self, tenant_id: str) -> Iterator[None]:
        """SQLite compatibility shim for the Postgres RLS access scope."""
        del tenant_id
        yield

    @contextmanager
    def system_scope(self) -> Iterator[None]:
        """SQLite compatibility shim for trusted cross-tenant operations."""
        yield

    def _channel(self, run_id: str) -> _RunChannel:
        with self._channels_lock:
            return self._channels[run_id]

    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        """Notify live subscribers of `run_id` that a new event landed."""
        ch = self._channel(run_id)
        with ch.cond:
            ch.events.append(event)
            ch.cond.notify_all()

    def subscribe(
        self, tenant_id: str, run_id: str, after_seq: int = -1
    ) -> Iterator[dict[str, Any]]:
        """Yield live events for `run_id` with seq > after_seq, blocking for new ones.

        Local in-process stand-in for Postgres LISTEN/NOTIFY. Replay-from-seq for
        historical events is the store's job; this only tails what is published live.
        """
        tenant_id = str(tenant_id)
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
                if ev.get("tenant_id") == tenant_id and int(ev["seq"]) > last_seq:
                    last_seq = int(ev["seq"])
                    yield ev

    def close(self) -> None:
        with self.write_lock:
            self._conn.close()


def open_db(path: str = ":memory:") -> Any:
    """Open (or create) the shared platform database.

    ``path`` is a filesystem path, ``":memory:"``, or a ``postgresql://``/``postgres://``
    DSN. The returned handle is shared by all platform stores.
    """
    if isinstance(path, str) and path.startswith(("postgres://", "postgresql://")):
        from .pg_db import PostgresDb

        return PostgresDb(path)
    return Db(path)
