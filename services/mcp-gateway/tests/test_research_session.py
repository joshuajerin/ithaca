"""Research-session trace: a platform-backed Toolset groups a BYO agent's calls into one
persistent research run (session_open + tool_call/tool_result), so the UI can render it."""

from __future__ import annotations

import uuid

from doomberg_mcp import InMemoryTrace, PlatformTraceSink, Toolset

TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class _FakeStore:
    """Duck-typed TraceStore: assigns a gap-free seq per run, records appended events."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._seq: dict[str, int] = {}

    def append(self, event: dict) -> int:
        run_id = str(event["run_id"])
        seq = self._seq.get(run_id, 0)
        self._seq[run_id] = seq + 1
        ev = dict(event)
        ev["seq"] = seq
        self.events.append(ev)
        return seq


class _FakeRuns:
    """Duck-typed RunStore exposing only create_research."""

    def __init__(self) -> None:
        self.created: list[str] = []

    def create_research(self, tenant_id: str) -> str:
        run_id = str(uuid.uuid4())
        self.created.append(run_id)
        return run_id


def test_platform_trace_sink_strips_seq_and_appends():
    store = _FakeStore()
    sink = PlatformTraceSink(store)
    sink.emit({"run_id": str(uuid.uuid4()), "seq": 999, "ts": "2026-01-01T00:00:00Z",
               "type": "reasoning", "tenant_id": TENANT, "data": {"text": "hi"}})
    assert len(store.events) == 1
    assert store.events[0]["seq"] == 0  # store reassigns; the caller's 999 is dropped


def _platform_toolset(core):
    return Toolset(core=core, sink=InMemoryTrace(), runs=_FakeRuns())


def test_session_groups_calls_into_one_research_run(toolset_core):
    ts = _platform_toolset(toolset_core)
    ctx = {"tenant_id": TENANT, "session_id": "agent-sess-1", "agent_id": "claude"}

    ts.market_get_ohlcv("AAA", range="1y", _ctx=ctx)
    ts.market_get_ohlcv("BBB", range="1y", _ctx=ctx)

    assert len(ts.runs.created) == 1  # both calls share ONE research run
    run_id = ts.runs.created[0]
    events = ts.sink.events(run_id)
    types = [e["type"] for e in events]
    assert types[0] == "session_open"
    assert types.count("tool_call") == 2 and types.count("tool_result") == 2
    # gap-free seq within the run
    assert [e["seq"] for e in events] == list(range(len(events)))
    # the canonical tool name key the read-model pairs on is present
    call = next(e for e in events if e["type"] == "tool_call")
    assert call["data"]["name"] == "market.get_ohlcv"


def test_distinct_sessions_get_distinct_runs(toolset_core):
    ts = _platform_toolset(toolset_core)
    ts.market_get_ohlcv("AAA", _ctx={"tenant_id": TENANT, "session_id": "s1"})
    ts.market_get_ohlcv("AAA", _ctx={"tenant_id": TENANT, "session_id": "s2"})
    assert len(ts.runs.created) == 2
