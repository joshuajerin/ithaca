from __future__ import annotations

import os

import pytest
from platform_helpers import new_uuid, trace_event

from doomberg_platform import AuthStore, ExecutionStore, JobStore, LeaseStore, TraceStore, open_db
from doomberg_platform.migrations import (
    MIGRATIONS,
    Migration,
    MigrationDrift,
    MigrationRequired,
    apply_migrations,
    validate_migrations,
)
from doomberg_platform.pg_db import _convert_placeholders, is_postgres_dsn, migration_mode


class _Rows:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    def fetchall(self) -> list[dict[str, object]]:
        return self._rows


class _MigrationConnection:
    def __init__(self) -> None:
        self.applied: dict[int, tuple[str, str]] = {}
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> _Rows:
        self.statements.append((sql, params))
        if sql.startswith("SELECT version, name, checksum"):
            return _Rows(
                [
                    {"version": version, "name": name, "checksum": checksum}
                    for version, (name, checksum) in sorted(self.applied.items())
                ]
            )
        if sql.startswith("INSERT INTO doomberg_schema_migrations"):
            version, name, checksum = params
            self.applied[int(version)] = (str(name), str(checksum))
        return _Rows()


def test_postgres_dsn_detection() -> None:
    assert is_postgres_dsn("postgresql://user:pw@host/db")
    assert is_postgres_dsn("postgres://user:pw@host/db")
    assert not is_postgres_dsn(":memory:")
    assert not is_postgres_dsn("./doomberg.db")


def test_placeholder_conversion_ignores_sql_string_literals() -> None:
    sql = "SELECT '?' AS marker, * FROM jobs WHERE tenant_id = ? AND state IN (?, ?)"
    assert (
        _convert_placeholders(sql)
        == "SELECT '?' AS marker, * FROM jobs WHERE tenant_id = %s AND state IN (%s, %s)"
    )


def test_postgres_migrations_are_ordered_idempotent_and_locked() -> None:
    conn = _MigrationConnection()

    first = apply_migrations(conn)
    baseline_create_count = sum("CREATE TABLE IF NOT EXISTS runs" in sql for sql, _ in conn.statements)
    second = apply_migrations(conn)

    assert first.current_version == MIGRATIONS[-1].version
    assert first.pending_versions == ()
    assert second == first
    assert baseline_create_count == 1
    assert sum("CREATE TABLE IF NOT EXISTS runs" in sql for sql, _ in conn.statements) == 1
    assert sum("pg_advisory_xact_lock" in sql for sql, _ in conn.statements) == 2
    first_lock = next(i for i, (sql, _) in enumerate(conn.statements) if "pg_advisory" in sql)
    first_ledger = next(
        i for i, (sql, _) in enumerate(conn.statements) if "CREATE TABLE IF NOT EXISTS doomberg_schema" in sql
    )
    assert first_lock < first_ledger


def test_postgres_migration_validation_fails_on_pending_schema() -> None:
    conn = _MigrationConnection()

    with pytest.raises(MigrationRequired, match="pending migrations: 1"):
        validate_migrations(conn)


def test_postgres_migration_validation_detects_definition_drift() -> None:
    conn = _MigrationConnection()
    migration = Migration(1, "one", "SELECT 1")
    conn.applied[1] = (migration.name, "not-the-release-checksum")

    with pytest.raises(MigrationDrift, match="migration 1 drifted"):
        validate_migrations(conn, (migration,))


def test_postgres_migration_mode_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOOMBERG_DB_MIGRATION_MODE", raising=False)
    assert migration_mode() == "apply"
    monkeypatch.setenv("DOOMBERG_DB_MIGRATION_MODE", "validate")
    assert migration_mode() == "validate"
    monkeypatch.setenv("DOOMBERG_DB_MIGRATION_MODE", "invalid")
    with pytest.raises(ValueError, match="must be apply, validate, or off"):
        migration_mode()


@pytest.mark.skipif(
    not os.environ.get("DOOMBERG_PLATFORM_PG_URL"),
    reason="set DOOMBERG_PLATFORM_PG_URL to run the live Postgres platform smoke test",
)
def test_live_postgres_platform_smoke() -> None:
    db = open_db(os.environ["DOOMBERG_PLATFORM_PG_URL"])
    try:
        tenant_id = AuthStore(db).create_tenant("pg smoke")
        run_id = new_uuid()
        jobs = JobStore(db)
        job = jobs.create_for_run(
            tenant_id,
            run_id,
            kind="backtest",
            profile="backtest",
            payload={"ok": True},
            idempotency_key="pg-smoke-job",
        )
        assert job["state"] == "queued"
        claimed = jobs.claim_available(worker_id="pg-smoke-worker")
        assert [j["job_id"] for j in claimed] == [job["job_id"]]
        assert claimed[0]["state"] == "leased"
        leases = LeaseStore(db)
        assert leases.acquire("pg-smoke-leader", "worker-a", ttl_seconds=30) is not None
        assert leases.acquire("pg-smoke-leader", "worker-b", ttl_seconds=30) is None
        assert leases.release("pg-smoke-leader", "worker-a") is True

        seq = TraceStore(db).append(trace_event(tenant_id, run_id))
        assert seq >= 0
        execution = ExecutionStore(db)
        intent = execution.create_order_intent(
            tenant_id,
            run_id,
            payload={"symbol": "AAPL", "side": "buy", "quantity": 1},
            idempotency_key="pg-smoke-intent",
        )
        order = execution.create_order(
            tenant_id,
            intent["intent_id"],
            broker="paper",
            client_order_id="pg-smoke-client-order",
            payload={"symbol": "AAPL", "quantity": 1},
            state="filled",
        )
        fill = execution.create_fill(
            tenant_id,
            order["order_id"],
            payload={"symbol": "AAPL", "quantity": 1, "price": 100},
            event_time="2026-06-24T00:00:00+00:00",
        )
        record = execution.get_record(tenant_id, intent["intent_id"])
        assert record["orders"][0]["order_id"] == order["order_id"]
        assert record["fills"][0]["fill_id"] == fill["fill_id"]
    finally:
        db.close()
