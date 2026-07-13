"""Ordered PostgreSQL schema migrations with drift detection.

Production schema changes are serialized with a transaction-scoped advisory
lock and recorded in ``doomberg_schema_migrations``. Migration definitions are
append-only: changing an already-applied migration produces a hard failure
instead of silently mutating production schema from application startup.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from .db import _BASELINE_SCHEMA

MIGRATION_LOCK_ID = 4_445_666_668_269_001
MIGRATION_TABLE = "doomberg_schema_migrations"

_MIGRATION_LEDGER_DDL = f"""
CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
    version     BIGINT PRIMARY KEY,
    name        TEXT NOT NULL,
    checksum    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


class MigrationError(RuntimeError):
    """Base class for schema lifecycle failures."""


class MigrationRequired(MigrationError):
    """The database is behind the application migration manifest."""


class MigrationDrift(MigrationError):
    """An applied migration no longer matches its immutable definition."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        normalized = "\n".join(line.rstrip() for line in self.sql.strip().splitlines())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MigrationStatus:
    current_version: int
    latest_version: int
    pending_versions: tuple[int, ...]


_TENANT_TABLES = (
    "api_keys",
    "users",
    "sse_tickets",
    "runs",
    "strategies",
    "trace_events",
    "books",
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
)


def _policy_sql(table: str, expression: str) -> str:
    policy = f"doomberg_{table}_access"
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {policy} ON {table};
CREATE POLICY {policy} ON {table}
    FOR ALL
    USING ({expression})
    WITH CHECK ({expression});
"""


_SYSTEM_ACCESS = "current_setting('doomberg.system_access', true) = 'on'"
_TENANT_ACCESS = "tenant_id = current_setting('doomberg.tenant_id', true)"
_RLS_SQL = "\n".join(
    [
        _policy_sql("tenants", f"{_SYSTEM_ACCESS} OR id = current_setting('doomberg.tenant_id', true)"),
        *(
            _policy_sql(table, f"{_SYSTEM_ACCESS} OR {_TENANT_ACCESS}")
            for table in _TENANT_TABLES
        ),
        _policy_sql(
            "run_seq",
            f"{_SYSTEM_ACCESS} OR EXISTS ("
            "SELECT 1 FROM runs AS scoped_run "
            "WHERE scoped_run.run_id = run_seq.run_id "
            "AND scoped_run.tenant_id = current_setting('doomberg.tenant_id', true))",
        ),
        _policy_sql(
            "oauth_accounts",
            f"{_SYSTEM_ACCESS} OR EXISTS ("
            "SELECT 1 FROM users AS scoped_user "
            "WHERE scoped_user.id = oauth_accounts.user_id "
            "AND scoped_user.tenant_id = current_setting('doomberg.tenant_id', true))",
        ),
        _policy_sql(
            "user_sessions",
            f"{_SYSTEM_ACCESS} OR EXISTS ("
            "SELECT 1 FROM users AS scoped_user "
            "WHERE scoped_user.id = user_sessions.user_id "
            "AND scoped_user.tenant_id = current_setting('doomberg.tenant_id', true))",
        ),
        _policy_sql("worker_leases", _SYSTEM_ACCESS),
    ]
)

_EXECUTION_IDEMPOTENCY_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_broker_order
    ON orders (tenant_id, broker, broker_order_id)
    WHERE broker_order_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_fills_broker_fill
    ON fills (tenant_id, broker_fill_id)
    WHERE broker_fill_id IS NOT NULL;
"""

_EXECUTION_CONTROLS_SQL = f"""
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

{_policy_sql('execution_controls', f'{_SYSTEM_ACCESS} OR {_TENANT_ACCESS}')}
{_policy_sql('execution_control_events', f'{_SYSTEM_ACCESS} OR {_TENANT_ACCESS}')}
"""

_COMPLIANCE_POLICIES_SQL = f"""
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

{_policy_sql('compliance_policies', f'{_SYSTEM_ACCESS} OR {_TENANT_ACCESS}')}
{_policy_sql('compliance_policy_events', f'{_SYSTEM_ACCESS} OR {_TENANT_ACCESS}')}
"""

_WORKER_HEARTBEATS_SQL = f"""
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

{_policy_sql('worker_heartbeats', _SYSTEM_ACCESS)}
"""


MIGRATIONS = (
    Migration(1, "platform baseline", _BASELINE_SCHEMA),
    Migration(2, "enforce tenant row security", _RLS_SQL),
    Migration(3, "deduplicate broker execution records", _EXECUTION_IDEMPOTENCY_SQL),
    Migration(4, "add durable execution kill switches", _EXECUTION_CONTROLS_SQL),
    Migration(5, "add durable tenant compliance policies", _COMPLIANCE_POLICIES_SQL),
    Migration(6, "add durable worker heartbeats", _WORKER_HEARTBEATS_SQL),
)


def _schema_statements(script: str) -> Iterator[str]:
    """Split the repository's simple DDL scripts into executable statements."""
    lines = [line for line in script.splitlines() if not line.strip().startswith("--")]
    for raw in "\n".join(lines).split(";"):
        statement = raw.strip()
        if statement:
            yield statement


def _ordered(migrations: Iterable[Migration]) -> tuple[Migration, ...]:
    ordered = tuple(migrations)
    versions = [migration.version for migration in ordered]
    if versions != sorted(versions) or len(versions) != len(set(versions)):
        raise MigrationError("migration versions must be unique and strictly increasing")
    if any(version <= 0 for version in versions):
        raise MigrationError("migration versions must be positive")
    return ordered


def _applied(conn: Any) -> dict[int, tuple[str, str]]:
    rows = conn.execute(
        f"SELECT version, name, checksum FROM {MIGRATION_TABLE} ORDER BY version"
    ).fetchall()
    return {
        int(row["version"]): (str(row["name"]), str(row["checksum"]))
        for row in rows
    }


def _status(
    applied: dict[int, tuple[str, str]], migrations: tuple[Migration, ...]
) -> MigrationStatus:
    manifest = {migration.version: migration for migration in migrations}
    unknown = sorted(set(applied) - set(manifest))
    if unknown:
        raise MigrationDrift(
            "database contains migration versions unknown to this release: "
            + ", ".join(str(version) for version in unknown)
        )
    for version, (stored_name, stored_checksum) in applied.items():
        expected = manifest[version]
        if stored_name != expected.name or stored_checksum != expected.checksum:
            raise MigrationDrift(
                f"migration {version} drifted: database has {stored_name!r}/"
                f"{stored_checksum}, release expects {expected.name!r}/{expected.checksum}"
            )
    pending = tuple(migration.version for migration in migrations if migration.version not in applied)
    return MigrationStatus(
        current_version=max(applied, default=0),
        latest_version=max(manifest, default=0),
        pending_versions=pending,
    )


def apply_migrations(
    conn: Any, migrations: Iterable[Migration] = MIGRATIONS
) -> MigrationStatus:
    """Apply pending migrations atomically while holding the global schema lock."""
    ordered = _ordered(migrations)
    conn.execute("SELECT pg_advisory_xact_lock(?)", (MIGRATION_LOCK_ID,))
    conn.execute(_MIGRATION_LEDGER_DDL)
    applied = _applied(conn)
    status = _status(applied, ordered)
    by_version = {migration.version: migration for migration in ordered}
    for version in status.pending_versions:
        migration = by_version[version]
        for statement in _schema_statements(migration.sql):
            conn.execute(statement)
        conn.execute(
            f"INSERT INTO {MIGRATION_TABLE} (version, name, checksum) VALUES (?, ?, ?)",
            (migration.version, migration.name, migration.checksum),
        )
        applied[migration.version] = (migration.name, migration.checksum)
    return _status(applied, ordered)


def validate_migrations(
    conn: Any, migrations: Iterable[Migration] = MIGRATIONS
) -> MigrationStatus:
    """Fail if the database is behind or differs from the release manifest."""
    ordered = _ordered(migrations)
    try:
        status = _status(_applied(conn), ordered)
    except Exception as exc:
        if exc.__class__.__name__ == "UndefinedTable":
            raise MigrationRequired(
                "platform schema is not initialized; run the platform-migrate role"
            ) from exc
        raise
    if status.pending_versions:
        versions = ", ".join(str(version) for version in status.pending_versions)
        raise MigrationRequired(
            f"platform schema is at {status.current_version}; pending migrations: {versions}"
        )
    return status
