from __future__ import annotations

import os

import pytest
from platform_helpers import new_uuid, trace_event

from doomberg_platform import AuthStore, ExecutionStore, JobStore, LeaseStore, TraceStore, open_db
from doomberg_platform.pg_db import _convert_placeholders, is_postgres_dsn


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
