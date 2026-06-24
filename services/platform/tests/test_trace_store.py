"""TraceStore: gap-free seq, tenant isolation, contract validation, replay, live tail."""

from __future__ import annotations

import threading
import time

import pytest
from platform_helpers import new_uuid, trace_event
from pydantic import ValidationError


def test_seq_is_gap_free_and_starts_at_zero(trace_store):
    tenant = new_uuid()
    run = new_uuid()
    seqs = [trace_store.append(trace_event(tenant, run)) for _ in range(5)]
    assert seqs == [0, 1, 2, 3, 4]


def test_seq_is_per_run(trace_store):
    tenant = new_uuid()
    run_a, run_b = new_uuid(), new_uuid()
    assert trace_store.append(trace_event(tenant, run_a)) == 0
    assert trace_store.append(trace_event(tenant, run_b)) == 0
    assert trace_store.append(trace_event(tenant, run_a)) == 1
    assert trace_store.append(trace_event(tenant, run_b)) == 1


def test_supplied_seq_is_ignored(trace_store):
    tenant = new_uuid()
    run = new_uuid()
    ev = trace_event(tenant, run)
    ev["seq"] = 999  # caller must not control seq
    assert trace_store.append(ev) == 0


def test_concurrent_appends_stay_gap_free(trace_store):
    tenant = new_uuid()
    run = new_uuid()
    results: list[int] = []
    lock = threading.Lock()

    def worker():
        for _ in range(20):
            s = trace_store.append(trace_event(tenant, run))
            with lock:
                results.append(s)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == list(range(80))  # gap-free, no duplicates


def test_events_replay_after_seq(trace_store):
    tenant = new_uuid()
    run = new_uuid()
    for _ in range(4):
        trace_store.append(trace_event(tenant, run))
    all_events = trace_store.events(tenant, run)
    assert [e["seq"] for e in all_events] == [0, 1, 2, 3]
    tail = trace_store.events(tenant, run, after_seq=1)
    assert [e["seq"] for e in tail] == [2, 3]


def test_tenant_isolation_on_events(trace_store):
    tenant_a, tenant_b = new_uuid(), new_uuid()
    run = new_uuid()
    trace_store.append(trace_event(tenant_a, run))
    # Tenant B cannot read tenant A's run events even with the run_id.
    assert trace_store.events(tenant_b, run) == []
    assert len(trace_store.events(tenant_a, run)) == 1


def test_validation_rejects_bad_event_type(trace_store):
    tenant = new_uuid()
    run = new_uuid()
    bad = trace_event(tenant, run, type="not_a_real_type")
    with pytest.raises(ValidationError):
        trace_store.append(bad)


def test_validation_rejects_extra_field(trace_store):
    tenant = new_uuid()
    run = new_uuid()
    bad = trace_event(tenant, run)
    bad["totally_unknown_field"] = "x"  # extra=forbid on the contract
    with pytest.raises(ValidationError):
        trace_store.append(bad)


def test_validation_rejects_non_uuid_tenant(trace_store):
    with pytest.raises(ValidationError):
        trace_store.append(trace_event("not-a-uuid", new_uuid()))


def test_nothing_persisted_when_validation_fails(trace_store):
    tenant = new_uuid()
    run = new_uuid()
    with pytest.raises(ValidationError):
        trace_store.append(trace_event(tenant, run, type="bogus"))
    assert trace_store.events(tenant, run) == []


def test_event_payload_roundtrips(trace_store):
    tenant = new_uuid()
    run = new_uuid()
    session = new_uuid()
    trace_store.append(
        trace_event(
            tenant,
            run,
            type="tool_call",
            data={"name": "market.get_ohlcv", "args": {"symbol": "SPY"}},
            session_id=session,
            span_id="span-1",
            actor={"kind": "agent", "id": "researcher"},
        )
    )
    [ev] = trace_store.events(tenant, run)
    assert ev["type"] == "tool_call"
    assert ev["data"] == {"name": "market.get_ohlcv", "args": {"symbol": "SPY"}}
    assert ev["session_id"] == session
    assert ev["span_id"] == "span-1"
    assert ev["actor"] == {"kind": "agent", "id": "researcher"}


def test_subscribe_receives_live_events(trace_store):
    tenant = new_uuid()
    run = new_uuid()
    received: list[int] = []

    def consume():
        for ev in trace_store.subscribe(run):
            received.append(ev["seq"])
            if len(received) == 3:
                return

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    time.sleep(0.05)  # let the subscriber start waiting
    for _ in range(3):
        trace_store.append(trace_event(tenant, run))
    t.join(timeout=2.0)
    assert received == [0, 1, 2]
