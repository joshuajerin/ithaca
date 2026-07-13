from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from platform_helpers import new_uuid, trace_event

from doomberg_platform import (
    AuthStore,
    CompliancePolicyConflict,
    CompliancePolicyStore,
    ExecutionControlConflict,
    ExecutionControlStore,
    ExecutionStore,
    JobStore,
    LeaseStore,
    RunStore,
    TraceStore,
    WorkerHeartbeatStore,
    open_db,
)
from doomberg_platform.migrations import (
    MIGRATIONS,
    Migration,
    MigrationDrift,
    MigrationRequired,
    apply_migrations,
    validate_migrations,
)
from doomberg_platform.pg_db import (
    PostgresDb,
    PostgresPoolConfig,
    _convert_placeholders,
    allow_forward_migrations,
    is_postgres_dsn,
    migration_mode,
)


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


def test_postgres_rls_migration_forces_direct_and_indirect_tenant_policies() -> None:
    rls = MIGRATIONS[1]
    assert rls.version == 2
    for table in ("runs", "api_keys", "trace_events", "order_intents", "run_seq"):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in rls.sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in rls.sql
        assert f"CREATE POLICY doomberg_{table}_access ON {table}" in rls.sql
    assert "scoped_run.tenant_id = current_setting('doomberg.tenant_id', true)" in rls.sql
    assert "scoped_user.id = oauth_accounts.user_id" in rls.sql
    assert "scoped_user.id = user_sessions.user_id" in rls.sql


def test_postgres_execution_migration_deduplicates_broker_records() -> None:
    execution = MIGRATIONS[2]
    assert execution.version == 3
    assert "idx_orders_broker_order" in execution.sql
    assert "WHERE broker_order_id IS NOT NULL" in execution.sql
    assert "idx_fills_broker_fill" in execution.sql
    assert "WHERE broker_fill_id IS NOT NULL" in execution.sql


def test_postgres_execution_control_migration_is_forced_and_tenant_scoped() -> None:
    controls = MIGRATIONS[3]
    assert controls.version == 4
    for table in ("execution_controls", "execution_control_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in controls.sql
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in controls.sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in controls.sql
        assert f"CREATE POLICY doomberg_{table}_access ON {table}" in controls.sql


def test_postgres_compliance_policy_migration_is_forced_and_tenant_scoped() -> None:
    policies = MIGRATIONS[4]
    assert policies.version == 5
    for table in ("compliance_policies", "compliance_policy_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in policies.sql
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in policies.sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in policies.sql
        assert f"CREATE POLICY doomberg_{table}_access ON {table}" in policies.sql


def test_postgres_worker_heartbeat_migration_is_system_only() -> None:
    heartbeats = MIGRATIONS[5]
    assert heartbeats.version == 6
    assert "CREATE TABLE IF NOT EXISTS worker_heartbeats" in heartbeats.sql
    assert "ALTER TABLE worker_heartbeats ENABLE ROW LEVEL SECURITY" in heartbeats.sql
    assert "ALTER TABLE worker_heartbeats FORCE ROW LEVEL SECURITY" in heartbeats.sql
    assert "current_setting('doomberg.system_access', true) = 'on'" in heartbeats.sql


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


def test_platform_baseline_checksum_matches_the_immutable_deployment_ledger() -> None:
    assert MIGRATIONS[0].checksum == (
        "07db08432553da23cf2faca06e7944631a5b876a8ba175b048d5b1cfba4ada53"
    )


def test_postgres_migrations_allow_explicit_forward_compatible_schema() -> None:
    conn = _MigrationConnection()
    migration = Migration(1, "one", "SELECT 1")
    future = Migration(2, "future", "SELECT 2")
    conn.applied = {
        1: (migration.name, migration.checksum),
        2: (future.name, future.checksum),
    }

    with pytest.raises(MigrationDrift, match="unknown to this release: 2"):
        validate_migrations(conn, (migration,))

    status = validate_migrations(conn, (migration,), allow_forward=True)

    assert status.current_version == 2
    assert status.latest_version == 1
    assert status.pending_versions == ()


def test_forward_migration_override_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOOMBERG_DB_ALLOW_FORWARD_MIGRATIONS", raising=False)
    assert allow_forward_migrations() is False
    monkeypatch.setenv("DOOMBERG_DB_ALLOW_FORWARD_MIGRATIONS", "true")
    assert allow_forward_migrations() is True
    monkeypatch.setenv("DOOMBERG_DB_ALLOW_FORWARD_MIGRATIONS", "sometimes")
    with pytest.raises(ValueError, match="must be a boolean value"):
        allow_forward_migrations()


def test_postgres_migration_mode_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOOMBERG_DB_MIGRATION_MODE", raising=False)
    assert migration_mode() == "apply"
    monkeypatch.setenv("DOOMBERG_DB_MIGRATION_MODE", "validate")
    assert migration_mode() == "validate"
    monkeypatch.setenv("DOOMBERG_DB_MIGRATION_MODE", "invalid")
    with pytest.raises(ValueError, match="must be apply, validate, or off"):
        migration_mode()


@pytest.mark.parametrize("mode", ["apply", "validate"])
def test_postgres_migration_mode_passes_forward_compatibility_override(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("DOOMBERG_DB_MIGRATION_MODE", mode)
    monkeypatch.setenv("DOOMBERG_DB_ALLOW_FORWARD_MIGRATIONS", "1")
    conn = _MigrationConnection()
    if mode == "validate":
        for migration in MIGRATIONS:
            conn.applied[migration.version] = (migration.name, migration.checksum)
    db = SimpleNamespace(system_scope=lambda: nullcontext(), conn=nullcontext(conn))

    status = PostgresDb._migrate(db)

    assert status.current_version == MIGRATIONS[-1].version
    assert status.pending_versions == ()


def test_postgres_migration_mode_off_does_not_parse_forward_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOOMBERG_DB_MIGRATION_MODE", "off")
    monkeypatch.setenv("DOOMBERG_DB_ALLOW_FORWARD_MIGRATIONS", "invalid")
    db = SimpleNamespace()

    status = PostgresDb._migrate(db)

    assert status == status.__class__(current_version=0, latest_version=0, pending_versions=())


def test_postgres_pool_config_is_bounded_and_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOOMBERG_POSTGRES_POOL_MIN", "2")
    monkeypatch.setenv("DOOMBERG_POSTGRES_POOL_MAX", "6")
    monkeypatch.setenv("DOOMBERG_POSTGRES_POOL_TIMEOUT_S", "4.5")
    config = PostgresPoolConfig.from_env()
    assert (config.min_size, config.max_size, config.timeout_seconds) == (2, 6, 4.5)

    monkeypatch.setenv("DOOMBERG_POSTGRES_POOL_MIN", "7")
    with pytest.raises(ValueError, match="POOL_MIN cannot exceed POOL_MAX"):
        PostgresPoolConfig.from_env()

    monkeypatch.setenv("DOOMBERG_POSTGRES_POOL_MIN", "1")
    monkeypatch.setenv("DOOMBERG_POSTGRES_POOL_TIMEOUT_S", "nan")
    with pytest.raises(ValueError, match="must be greater than 0"):
        PostgresPoolConfig.from_env()


@pytest.mark.skipif(
    not os.environ.get("DOOMBERG_PLATFORM_PG_URL"),
    reason="set DOOMBERG_PLATFORM_PG_URL to run the live Postgres pool test",
)
def test_live_postgres_pool_parallelism_transaction_pinning_and_recovery() -> None:
    url = os.environ["DOOMBERG_PLATFORM_PG_URL"]
    db = PostgresDb(url, pool_config=PostgresPoolConfig(min_size=1, max_size=4))
    try:
        with db.conn as conn:
            first_pid = conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
            second_pid = conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
        assert first_pid == second_pid

        def sleeping_backend(_: int) -> int:
            row = db.conn.execute(
                "SELECT pg_backend_pid() AS pid FROM (SELECT pg_sleep(0.1)) AS wait"
            ).fetchone()
            return int(row["pid"])

        with ThreadPoolExecutor(max_workers=4) as executor:
            backend_ids = set(executor.map(sleeping_backend, range(4)))
        assert len(backend_ids) >= 2

        victim = int(db.conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"])
        with psycopg.connect(url, autocommit=True) as killer:
            assert killer.execute("SELECT pg_terminate_backend(%s)", (victim,)).fetchone()[0]
        assert db.conn.execute("SELECT 1 AS healthy").fetchone()["healthy"] == 1
        assert db.pool_stats["pool_max"] == 4

        tenant_id = AuthStore(db).create_tenant("pool listener recovery")
        run_ids = (new_uuid(), new_uuid())

        def next_event(run_id: str) -> dict[str, object]:
            stream = db.subscribe(tenant_id, run_id)
            try:
                return next(stream)
            finally:
                stream.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(next_event, run_id) for run_id in run_ids]
            listener_pid = None
            deadline = time.monotonic() + 3
            with psycopg.connect(url, autocommit=True) as admin:
                while listener_pid is None and time.monotonic() < deadline:
                    row = admin.execute(
                        "SELECT pid FROM pg_stat_activity "
                        "WHERE application_name = 'doomberg-listener' LIMIT 1"
                    ).fetchone()
                    listener_pid = None if row is None else int(row[0])
                    if listener_pid is None:
                        time.sleep(0.02)
                assert listener_pid is not None
                listener_count = admin.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE application_name = 'doomberg-listener'"
                ).fetchone()[0]
                assert listener_count == 1
                assert admin.execute(
                    "SELECT pg_terminate_backend(%s)", (listener_pid,)
                ).fetchone()[0]
                replacement_pid = None
                deadline = time.monotonic() + 4
                while replacement_pid is None and time.monotonic() < deadline:
                    row = admin.execute(
                        "SELECT pid FROM pg_stat_activity "
                        "WHERE application_name = 'doomberg-listener' AND pid <> %s LIMIT 1",
                        (listener_pid,),
                    ).fetchone()
                    replacement_pid = None if row is None else int(row[0])
                    if replacement_pid is None:
                        time.sleep(0.02)
                assert replacement_pid is not None
            for run_id in run_ids:
                TraceStore(db).append(trace_event(tenant_id, run_id))
            recovered = [future.result(timeout=5) for future in futures]
        assert [event["run_id"] for event in recovered] == list(run_ids)
    finally:
        db.close()


@pytest.mark.skipif(
    not os.environ.get("DOOMBERG_PLATFORM_PG_URL"),
    reason="set DOOMBERG_PLATFORM_PG_URL to run the live Postgres RLS test",
)
def test_live_postgres_rls_fails_closed_and_scopes_tenant_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = os.environ["DOOMBERG_PLATFORM_PG_URL"]
    owner_db = PostgresDb(url, pool_config=PostgresPoolConfig(min_size=1, max_size=2))
    role = f"doomberg_rls_{new_uuid().replace('-', '')[:16]}"
    password = new_uuid()
    app_db: PostgresDb | None = None
    role_created = False
    try:
        tenant_a = AuthStore(owner_db).create_tenant("RLS tenant A")
        tenant_b = AuthStore(owner_db).create_tenant("RLS tenant B")
        run_a = RunStore(owner_db).create(tenant_a, "research", None, {"name": "A"})
        run_b = RunStore(owner_db).create(tenant_b, "research", None, {"name": "B"})
        TraceStore(owner_db).append(trace_event(tenant_a, run_a))
        TraceStore(owner_db).append(trace_event(tenant_b, run_b))
        controls = ExecutionControlStore(owner_db)
        controls.set_tenant(
            tenant_a, enabled=True, reason="tenant-a", actor_id="owner", expect_version=0
        )
        controls.set_tenant(
            tenant_b, enabled=False, reason=None, actor_id="owner", expect_version=0
        )
        policies = CompliancePolicyStore(owner_db)
        default_limits = {
            "maxPositionPct": 15.0,
            "maxNetPct": 120.0,
            "maxLeverage": 2.0,
            "maxConcentrationPct": 50.0,
        }
        policies.set(
            tenant_a,
            limits=default_limits,
            limits_enforced=False,
            restricted=["TSLA"],
            watch=[],
            action="tenant a policy",
            actor_id="owner",
            expect_version=0,
        )
        policies.set(
            tenant_b,
            limits=default_limits,
            limits_enforced=True,
            restricted=["GME"],
            watch=[],
            action="tenant b policy",
            actor_id="owner",
            expect_version=0,
        )

        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
            role_created = True
            admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(conninfo_to_dict(url).get("dbname") or admin.info.dbname),
                sql.Identifier(role),
            ))
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                sql.Identifier(role)
            ))
            admin.execute(sql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
            ).format(sql.Identifier(role)))

        app_url = make_conninfo(url, user=role, password=password)
        with psycopg.connect(app_url) as raw_app:
            assert raw_app.execute("SELECT run_id FROM runs").fetchall() == []
            raw_app.execute("SELECT set_config('doomberg.tenant_id', %s, true)", (tenant_a,))
            assert raw_app.execute("SELECT run_id FROM runs").fetchall() == [(run_a,)]
            assert raw_app.execute("SELECT run_id FROM run_seq").fetchall() == [(run_a,)]

        monkeypatch.setenv("DOOMBERG_DB_MIGRATION_MODE", "validate")
        app_db = PostgresDb(app_url, pool_config=PostgresPoolConfig(min_size=1, max_size=2))
        assert RunStore(app_db).get(tenant_a, run_a) is not None
        assert RunStore(app_db).get(tenant_b, run_a) is None
        assert ExecutionControlStore(app_db).get(tenant_a)["reason"] == "tenant-a"
        assert ExecutionControlStore(app_db).get(tenant_b)["reason"] is None
        assert CompliancePolicyStore(app_db).get(tenant_a)["restricted"] == ["TSLA"]
        assert CompliancePolicyStore(app_db).get(tenant_b)["restricted"] == ["GME"]
        assert {row["run_id"] for row in RunStore(app_db).list_by_state("draft")} == {
            run_a,
            run_b,
        }
        with app_db.tenant_scope(tenant_a):
            with pytest.raises(RuntimeError, match="cannot switch tenant"):
                with app_db.tenant_scope(tenant_b):
                    pass
            with pytest.raises(RuntimeError, match="cannot elevate"):
                with app_db.system_scope():
                    pass
    finally:
        if app_db is not None:
            app_db.close()
        owner_db.close()
        if role_created:
            with psycopg.connect(url, autocommit=True) as admin:
                admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


@pytest.mark.skipif(
    not os.environ.get("DOOMBERG_PLATFORM_PG_URL"),
    reason="set DOOMBERG_PLATFORM_PG_URL to run the live Postgres platform smoke test",
)
def test_live_postgres_platform_smoke() -> None:
    db = open_db(os.environ["DOOMBERG_PLATFORM_PG_URL"])
    second_db = open_db(os.environ["DOOMBERG_PLATFORM_PG_URL"])
    try:
        tenant_id = AuthStore(db).create_tenant("pg smoke")
        other_tenant_id = AuthStore(db).create_tenant("pg smoke unrelated tenant")
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
        heartbeat = WorkerHeartbeatStore(db).heartbeat(
            "pg-smoke-worker", "backtest-worker", ttl_seconds=30
        )
        assert heartbeat["status"] == "healthy"
        assert WorkerHeartbeatStore(second_db).list()[0]["worker_id"] == "pg-smoke-worker"

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
            broker_fill_id="pg-smoke-fill",
            payload={"symbol": "AAPL", "quantity": 1, "price": 100},
            event_time="2026-06-24T00:00:00+00:00",
        )
        same_fill = execution.create_fill(
            tenant_id,
            order["order_id"],
            broker_fill_id="pg-smoke-fill",
            payload={"symbol": "AAPL", "quantity": 1, "price": 100},
            event_time="2026-06-24T00:00:00+00:00",
        )
        assert same_fill["fill_id"] == fill["fill_id"]
        record = execution.get_record(tenant_id, intent["intent_id"])
        assert record["orders"][0]["order_id"] == order["order_id"]
        assert record["fills"][0]["fill_id"] == fill["fill_id"]

        controls_a = ExecutionControlStore(db)
        controls_b = ExecutionControlStore(second_db)
        controls_a.set_tenant(
            tenant_id,
            enabled=True,
            reason="initial",
            actor_id="pg-smoke-a",
            expect_version=0,
        )

        def release(store: ExecutionControlStore, actor_id: str) -> str:
            try:
                store.set_tenant(
                    tenant_id,
                    enabled=False,
                    reason=actor_id,
                    actor_id=actor_id,
                    expect_version=1,
                )
            except ExecutionControlConflict:
                return "conflict"
            return "updated"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(
                executor.map(
                    lambda args: release(*args),
                    ((controls_a, "pg-smoke-a"), (controls_b, "pg-smoke-b")),
                )
            )
        assert sorted(outcomes) == ["conflict", "updated"]
        assert controls_a.get(tenant_id)["version"] == 2

        with ThreadPoolExecutor(max_workers=1) as executor:
            with controls_a.submission_guard(tenant_id):
                halted = executor.submit(
                    controls_b.set_tenant,
                    tenant_id,
                    enabled=True,
                    reason="fenced",
                    actor_id="pg-smoke-b",
                    expect_version=2,
                )
                time.sleep(0.05)
                assert not halted.done()
            assert halted.result(timeout=2)["version"] == 3

        # Tenant fences do not serialize unrelated tenants.
        with controls_a.submission_guard(tenant_id):
            with controls_b.submission_guard(other_tenant_id):
                assert True

        # A global halt takes the exclusive global fence and therefore waits
        # for an in-flight submission from any tenant to finish.
        with ThreadPoolExecutor(max_workers=1) as executor:
            with controls_a.submission_guard(other_tenant_id):
                global_halt = executor.submit(
                    controls_b.set_global,
                    enabled=True,
                    reason="global fence",
                    actor_id="pg-smoke-admin",
                    expect_version=0,
                )
                time.sleep(0.05)
                assert not global_halt.done()
            assert global_halt.result(timeout=2)["version"] == 1

        policy_a = CompliancePolicyStore(db)
        policy_b = CompliancePolicyStore(second_db)
        limits = {
            "maxPositionPct": 25.0,
            "maxNetPct": 100.0,
            "maxLeverage": 1.5,
            "maxConcentrationPct": 100.0,
        }
        policy_a.set(
            tenant_id,
            limits=limits,
            limits_enforced=True,
            restricted=["TSLA"],
            watch=[],
            action="pg policy",
            actor_id="pg-smoke-a",
            expect_version=0,
        )
        policy_b.set(
            tenant_id,
            limits=limits,
            limits_enforced=True,
            restricted=["TSLA", "NVDA"],
            watch=[],
            action="pg policy update",
            actor_id="pg-smoke-b",
            expect_version=1,
        )
        with pytest.raises(CompliancePolicyConflict):
            policy_a.set(
                tenant_id,
                limits=limits,
                limits_enforced=True,
                restricted=[],
                watch=[],
                action="stale pg policy",
                actor_id="pg-smoke-a",
                expect_version=1,
            )
        assert policy_a.get(tenant_id)["version"] == 2

        with ThreadPoolExecutor(max_workers=1) as executor:
            with controls_a.submission_guard(tenant_id):
                policy_update = executor.submit(
                    policy_b.set,
                    tenant_id,
                    limits=limits,
                    limits_enforced=True,
                    restricted=["TSLA", "NVDA", "AAPL"],
                    watch=[],
                    action="fenced pg policy",
                    actor_id="pg-smoke-b",
                    expect_version=2,
                )
                time.sleep(0.05)
                assert not policy_update.done()
            assert policy_update.result(timeout=2)["version"] == 3
    finally:
        second_db.close()
        db.close()
