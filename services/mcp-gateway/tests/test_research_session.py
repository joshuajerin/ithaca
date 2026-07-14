"""Research-session trace: a platform-backed Toolset groups a BYO agent's calls into one
persistent research run (session_open + tool_call/tool_result), so the UI can render it."""

from __future__ import annotations

import uuid

from ithaca_mcp import InMemoryTrace, PlatformTraceSink, Toolset

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
        self.rows: dict[tuple[str, str], dict] = {}

    def create_research(self, tenant_id: str) -> str:
        run_id = str(uuid.uuid4())
        self.created.append(run_id)
        self.rows[(tenant_id, run_id)] = {"tenant_id": tenant_id, "run_id": run_id, "kind": "research"}
        return run_id

    def get(self, tenant_id: str, run_id: str) -> dict | None:
        return self.rows.get((tenant_id, run_id))

    def seed_research(self, tenant_id: str, run_id: str) -> None:
        self.rows[(tenant_id, run_id)] = {"tenant_id": tenant_id, "run_id": run_id, "kind": "research"}


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
    ctx = {"tenant_id": TENANT, "agent_id": "claude"}

    started = ts.start_research_session("compare AAA and BBB", _ctx=ctx)
    ts.market_get_ohlcv("AAA", range="1y", _ctx=ctx)
    ts.market_get_ohlcv("BBB", range="1y", _ctx=ctx)

    assert started["status"] == "ok"
    assert len(ts.runs.created) == 1  # both calls share ONE research run
    run_id = ts.runs.created[0]
    events = ts.sink.events(run_id)
    types = [e["type"] for e in events]
    assert types[0] == "session_open"
    assert events[0]["data"]["prompt"] == "compare AAA and BBB"
    assert types.count("tool_call") == 2 and types.count("tool_result") == 2
    # gap-free seq within the run
    assert [e["seq"] for e in events] == list(range(len(events)))
    # the canonical tool name key the read-model pairs on is present
    call = next(e for e in events if e["type"] == "tool_call")
    assert call["data"]["name"] == "market.get_ohlcv"


def test_distinct_sessions_get_distinct_runs(toolset_core):
    ts = _platform_toolset(toolset_core)
    ts.start_research_session("first", _ctx={"tenant_id": TENANT, "agent_id": "a1"})
    ts.start_research_session("second", _ctx={"tenant_id": TENANT, "agent_id": "a2"})
    assert len(ts.runs.created) == 2


def test_direct_tool_requires_started_research_session(toolset_core):
    ts = _platform_toolset(toolset_core)

    out = ts.market_get_ohlcv("AAA", _ctx={"tenant_id": TENANT, "agent_id": "claude"})

    assert out["error"]["code"] == "SESSION_CONTEXT_REQUIRED"
    assert ts.runs.created == []
    assert ts.sink.events() == []


def test_existing_run_id_does_not_bypass_research_session_start(toolset_core):
    ts = _platform_toolset(toolset_core)
    stray_run_id = str(uuid.uuid4())
    ts.runs.seed_research(TENANT, stray_run_id)

    out = ts.market_get_ohlcv(
        "AAA",
        _ctx={"tenant_id": TENANT, "agent_id": "claude", "run_id": stray_run_id},
    )

    assert out["error"]["code"] == "SESSION_CONTEXT_REQUIRED"
    assert ts.sink.events(stray_run_id) == []


def test_session_context_can_attach_to_precreated_research_run(toolset_core):
    ts = _platform_toolset(toolset_core)
    run_id = str(uuid.uuid4())
    ts.runs.seed_research(TENANT, run_id)
    ctx = {"tenant_id": TENANT, "agent_id": "claude"}

    out = ts.session_context(
        prompt="what does nvda look like",
        title="NVDA scan",
        session_id=run_id,
        _ctx=ctx,
    )
    ts.market_get_ohlcv("AAA", _ctx=ctx)

    assert out["session_id"] == run_id
    assert ts.runs.created == []  # reused the web-created session instead of opening another
    events = ts.sink.events(run_id)
    assert [e["type"] for e in events] == ["reasoning", "tool_call", "tool_result"]
    assert events[0]["data"]["prompt"] == "what does nvda look like"


def test_get_run_requires_started_session_context(toolset_core):
    ts = _platform_toolset(toolset_core)
    run_id = str(uuid.uuid4())
    ts.runs.seed_research(TENANT, run_id)

    class _Empty:
        def list_by_run(self, *_args):
            return []

    class _Trace:
        def events(self, *_args, **_kwargs):
            return []

    ts.platform = type(
        "Platform",
        (),
        {"runs": ts.runs, "jobs": _Empty(), "artifacts": _Empty(), "trace": _Trace()},
    )()

    out = ts.get_run(run_id, _ctx={"tenant_id": TENANT, "agent_id": "claude"})

    assert out["error"]["code"] == "SESSION_CONTEXT_REQUIRED"
