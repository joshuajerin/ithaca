"""Tests for the first-signin demo research session seeder."""

from __future__ import annotations

from doomberg_platform import Platform, seed_demo_session


def test_seed_creates_a_succeeded_research_run_with_a_gap_free_trace():
    platform = Platform(":memory:")
    tenant = platform.auth.create_tenant("Acme Capital")

    run_id = seed_demo_session(platform, tenant)

    assert run_id is not None
    run = platform.runs.get(tenant, run_id)
    assert run is not None
    assert run["kind"] == "research"
    assert run["state"] == "succeeded"

    events = platform.trace.events(tenant, run_id)
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(len(seqs)))  # gap-free

    types = [e["type"] for e in events]
    assert types[0] == "session_open"
    assert "tool_call" in types
    assert "tool_result" in types
    assert "strategy_proposed" in types
    assert "session_close" in types

    # The prompt is captured on the session_open event so the UI can render it.
    open_ev = next(e for e in events if e["type"] == "session_open")
    assert open_ev["data"]["prompt"]
    assert open_ev["data"]["title"]


def test_seed_is_idempotent():
    platform = Platform(":memory:")
    tenant = platform.auth.create_tenant("Acme Capital")

    first = seed_demo_session(platform, tenant)
    second = seed_demo_session(platform, tenant)

    assert first is not None
    assert second is None  # already has a research run -> no-op


def test_seed_trace_tool_calls_are_span_linked_to_their_results():
    platform = Platform(":memory:")
    tenant = platform.auth.create_tenant("Acme Capital")
    run_id = seed_demo_session(platform, tenant)
    assert run_id is not None

    events = platform.trace.events(tenant, run_id)
    calls = [e for e in events if e["type"] == "tool_call"]
    results = [e for e in events if e["type"] == "tool_result"]
    assert len(calls) == len(results) >= 1

    # Every tool_call has a matching tool_result sharing its span_id.
    call_spans = {e["span_id"] for e in calls}
    result_spans = {e["span_id"] for e in results}
    assert call_spans == result_spans
    assert None not in call_spans  # span_id is always set on calls
