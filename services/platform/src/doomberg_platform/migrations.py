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


MIGRATIONS = (
    Migration(1, "platform baseline", _BASELINE_SCHEMA),
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
