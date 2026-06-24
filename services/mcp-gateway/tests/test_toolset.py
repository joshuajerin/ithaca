"""MCP toolset behavior + trace emission + the closed-spec security invariant."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from doomberg_mcp import PlatformTraceSink, Toolset
from doomberg_platform import Platform

R1 = "11111111-1111-1111-1111-111111111111"
R2 = "22222222-2222-2222-2222-222222222222"
R3 = "33333333-3333-3333-3333-333333333333"
R4 = "44444444-4444-4444-4444-444444444444"
R5 = "55555555-5555-5555-5555-555555555555"
AGENT = "agent_x"


def test_market_get_ohlcv_returns_envelope_and_traces(toolset):
    out = toolset.market_get_ohlcv("AAA", range="1y", _ctx={"run_id": R1, "agent_id": AGENT})
    assert out["provenance"]["source"] == "yahoo-chart"
    events = toolset.sink.events(R1)
    assert [e["type"] for e in events] == ["tool_call", "tool_result"]
    # gap-free seq within the run
    assert [e["seq"] for e in events] == [0, 1]


def test_backtest_run_traces_and_returns_stats(toolset, sample_spec):
    out = toolset.backtest_run(sample_spec, range="1y", _ctx={"run_id": R2, "agent_id": AGENT})
    assert out["data"] is not None
    assert "sharpe" in out["data"]["stats"]
    result_event = toolset.sink.events(R2)[-1]
    assert result_event["data"]["summary"]["riskOk"] is True


def test_propose_strategy_stamps_draft(toolset, sample_spec):
    out = toolset.propose_strategy(sample_spec, _ctx={"run_id": R3, "agent_id": AGENT})
    assert out["status"] == "draft"
    assert out["strategy_id"].startswith("stg_")
    assert out["spec"]["id"] == out["strategy_id"]
    assert any(e["type"] == "strategy_proposed" for e in toolset.sink.events(R3))


def test_propose_strategy_rejects_free_form_code(toolset, sample_spec):
    bad = dict(sample_spec)
    bad["code"] = "import os; os.system('id')"
    with pytest.raises(ValidationError):
        toolset.propose_strategy(bad, _ctx={"run_id": R4})


def test_agent_cannot_self_stamp_tenant(toolset, sample_spec):
    sneaky = dict(sample_spec)
    sneaky["tenant_id"] = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    out = toolset.propose_strategy(sneaky, _ctx={"run_id": R5})
    assert out["spec"]["tenant_id"] is None  # server-stamped only; agent value ignored


async def test_server_registers_three_tools(toolset):
    from doomberg_mcp import create_server

    mcp, _ = create_server(toolset)
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert {"market_get_ohlcv", "backtest_run", "propose_strategy"} <= names
    assert {"search_skills", "describe_skill", "run_skill", "get_run", "subscribe_run",
            "cancel_run", "list_approvals", "decide_approval", "get_artifact"} <= names


def test_run_skill_queues_durable_backtest(toolset_core, sample_spec):
    platform = Platform(":memory:")
    tenant = platform.auth.create_tenant("mcp")
    ts = Toolset(
        core=toolset_core,
        sink=PlatformTraceSink(platform.trace),
        runs=platform.runs,
        platform=platform,
    )

    out = ts.run_skill(
        "backtest.run",
        input={"spec": sample_spec, "range": "1y"},
        idempotency_key="same-backtest",
        _ctx={"tenant_id": tenant, "agent_id": "agent"},
    )

    assert out["status"] == "queued"
    assert out["job_id"]
    run = platform.runs.get(tenant, out["run_id"])
    assert run["kind"] == "backtest"
    assert run["state"] == "queued"
    assert platform.jobs.get(tenant, out["job_id"])["idempotency_key"] == "same-backtest"

    again = ts.run_skill(
        "backtest.run",
        input={"spec": sample_spec, "range": "1y"},
        idempotency_key="same-backtest",
        _ctx={"tenant_id": tenant, "agent_id": "agent"},
    )
    assert again["run_id"] == out["run_id"]
    assert again["idempotent"] is True


def test_run_skill_interactive_persists_result_and_trace(toolset_core):
    platform = Platform(":memory:")
    tenant = platform.auth.create_tenant("mcp")
    ts = Toolset(
        core=toolset_core,
        sink=PlatformTraceSink(platform.trace),
        runs=platform.runs,
        platform=platform,
    )

    out = ts.run_skill(
        "market.get_ohlcv",
        input={"symbol": "AAA", "range": "1y"},
        _ctx={"tenant_id": tenant, "agent_id": "agent"},
    )

    assert out["status"] == "succeeded"
    got = ts.get_run(out["run_id"], _ctx={"tenant_id": tenant})
    assert got["run"]["result"]["provenance"]["source"] == "yahoo-chart"
    assert any(e["type"] == "tool_result" for e in got["events"])
