"""MCP toolset behavior + trace emission + the closed-spec security invariant."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from pydantic import ValidationError

from doomberg_mcp import PlatformTraceSink, Toolset
from doomberg_platform import Platform

R1 = "11111111-1111-1111-1111-111111111111"
R2 = "22222222-2222-2222-2222-222222222222"
R3 = "33333333-3333-3333-3333-333333333333"
R4 = "44444444-4444-4444-4444-444444444444"
R5 = "55555555-5555-5555-5555-555555555555"
R6 = "66666666-6666-6666-6666-666666666666"
AGENT = "agent_x"


class _QuoteServer:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                owner.requests.append({"path": self.path, "tenant": self.headers.get("X-Tenant-Id")})
                now = datetime.now(timezone.utc).isoformat()
                if self.path.startswith("/accounts"):
                    payload = {"accounts": [{"account_id": "DU12345", "type": "paper", "token": "secret"}]}
                elif self.path.startswith("/positions"):
                    payload = {"positions": [{"symbol": "AAPL", "quantity": 3, "secret": "x"}]}
                elif self.path.startswith("/orders"):
                    payload = {"orders": [{"order_id": "100", "symbol": "AAPL", "status": "Submitted"}]}
                else:
                    payload = {
                        "data": {
                            "quote": {
                                "symbol": "AAPL",
                                "price": 212.45,
                                "event_time": now,
                                "received_time": now,
                                "source": "doomberg-live-data",
                                "entitlement_class": "doomberg_live",
                            }
                        }
                    }
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_args: Any) -> None:
                return

        self._handler = Handler
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url = ""

    def __enter__(self) -> "_QuoteServer":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler)
        host, port = self._server.server_address
        self.url = f"http://{host}:{port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


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
    assert {
        "doomberg_init",
        "start_research_session",
        "session_context",
        "search_skills",
        "describe_skill",
        "list_toolkits",
        "describe_toolkit",
        "run_skill",
        "get_run",
        "subscribe_run",
        "cancel_run",
        "list_approvals",
        "decide_approval",
        "get_artifact",
    } <= names
    assert {"triggers_create", "triggers_dry_run", "triggers_list", "triggers_set_state",
            "trigger_firings_list", "alerts_list", "alerts_subscribe", "alerts_ack"} <= names
    assert {"create_order_intent", "preview_order_intent", "get_order_intent",
            "submit_order_intent"}.isdisjoint(names)
    assert "ibkr_smoke" not in names


def test_doomberg_init_returns_first_call_workflow(toolset):
    out = toolset.doomberg_init(goal="research AAPL momentum")

    assert out["status"] == "ready"
    assert out["goal_captured"] is True
    assert out["session_id"]
    assert out["session"]["prompt"] == "research AAPL momentum"
    assert out["start_here"][0]["tool"] == "start_research_session"
    assert out["start_here"][0]["status"] == "already_started_by_doomberg_init"
    assert {tool["name"] for tool in out["direct_tools"]} >= {
        "market_get_ohlcv",
        "market_news",
        "run_skill",
        "get_run",
    }
    assert {"search_skills", "describe_skill"}.isdisjoint(
        {step["tool"] for step in out["start_here"][:3]}
    )
    assert "move money" in out["boundaries"]["cannot"]


async def test_server_registers_control_plane_resources(toolset):
    from doomberg_mcp import create_server

    mcp, _ = create_server(toolset)

    resources = await mcp.list_resources()
    uris = {str(resource.uri) for resource in resources}
    assert {
        "doomberg://skills/catalog",
        "doomberg://toolkits/catalog",
        "doomberg://policies/current",
        "doomberg://accounts",
        "doomberg://data/providers",
        "doomberg://triggers",
        "doomberg://alerts/open",
        "doomberg://trigger-firings/recent",
    } <= uris

    templates = await mcp.list_resource_templates()
    template_uris = {template.uriTemplate for template in templates}
    assert {
        "doomberg://skills/{skill_id}/{version}",
        "doomberg://toolkits/{toolkit_id}",
        "doomberg://runs/{run_id}",
        "doomberg://triggers/{trigger_id}",
        "doomberg://alerts/{notification_id}",
    } <= template_uris


async def test_skill_resources_return_catalog_and_manifest(toolset):
    from doomberg_mcp import create_server

    mcp, _ = create_server(toolset)

    catalog_contents = await mcp.read_resource("doomberg://skills/catalog")
    catalog = json.loads(catalog_contents[0].content)
    assert catalog["kind"] == "skills.catalog"
    assert catalog["count"] >= 50
    assert any(skill["skill_id"] == "market.get_ohlcv" for skill in catalog["skills"])

    manifest_contents = await mcp.read_resource("doomberg://skills/market.get_ohlcv/0.1.0")
    manifest = json.loads(manifest_contents[0].content)
    assert manifest["skill_id"] == "market.get_ohlcv"
    assert manifest["version"] == "0.1.0"
    assert manifest["runtime"]["profile"] == "interactive"


async def test_toolkit_resources_return_grouped_direct_tools(toolset):
    from doomberg_mcp import create_server

    mcp, ts = create_server(toolset)

    listed = ts.list_toolkits()
    assert any(t["toolkit_id"] == "market-research" for t in listed["toolkits"])
    market_listing = next(t for t in listed["toolkits"] if t["toolkit_id"] == "market-research")
    assert "market_get_ohlcv" in market_listing["direct_tools"]
    assert market_listing["required_first_tool"] == "start_research_session"

    toolkit = ts.describe_toolkit("backtest-paper")
    assert toolkit["required_first_tool"] == "start_research_session"
    assert "backtest_run" in toolkit["direct_tools"]
    assert "list_approvals" in toolkit["direct_tools"]

    catalog_contents = await mcp.read_resource("doomberg://toolkits/catalog")
    catalog = json.loads(catalog_contents[0].content)
    assert catalog["kind"] == "toolkits.catalog"
    assert any(t["toolkit_id"] == "portfolio-risk" for t in catalog["toolkits"])

    toolkit_contents = await mcp.read_resource("doomberg://toolkits/market-research")
    manifest = json.loads(toolkit_contents[0].content)
    assert "market_tide" in manifest["direct_tools"]


async def test_platform_resources_return_tenant_scoped_views_without_secrets(toolset_core):
    from doomberg_mcp import create_server

    default_tenant = "00000000-0000-0000-0000-000000000000"
    platform = Platform(":memory:")
    run_id = platform.runs.create(default_tenant, "interactive", None, {"skill_id": "market.get_ohlcv"})
    platform.trace.append({
        "run_id": run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "run_transition",
        "tenant_id": default_tenant,
        "data": {"from": "draft", "to": "queued"},
    })
    platform.providers.upsert_connection(
        default_tenant,
        provider="ibkr",
        capabilities=["quote", "orders"],
        entitlements=[{"dataset": "equities", "entitlement_class": "doomberg_live"}],
        account_ref="DU12345",
        credential_ref="secret://ibkr-token",
    )
    platform.providers.create_snapshot(
        default_tenant,
        provider="community",
        dataset="prices",
        entitlement_class="public_delayed",
        as_of="2026-06-24T00:00:00+00:00",
        manifest={"symbols": ["AAPL"]},
        uri="spaces://doomberg-artifacts/snapshots/prices.parquet",
    )
    ts = Toolset(
        core=toolset_core,
        sink=PlatformTraceSink(platform.trace),
        runs=platform.runs,
        platform=platform,
    )
    mcp, _ = create_server(ts)

    run_contents = await mcp.read_resource(f"doomberg://runs/{run_id}")
    run_body = json.loads(run_contents[0].content)
    assert run_body["run"]["run_id"] == run_id
    assert run_body["events"][0]["type"] == "run_transition"

    accounts = json.loads((await mcp.read_resource("doomberg://accounts"))[0].content)
    assert accounts["accounts"] == []
    assert "credential_ref" not in json.dumps(accounts)
    assert "DU12345" not in json.dumps(accounts)

    providers = json.loads((await mcp.read_resource("doomberg://data/providers"))[0].content)
    assert providers["connections"][0]["provider"] == "doomberg-live-data"
    assert "orders" not in providers["connections"][0]["capabilities"]
    assert providers["dataset_snapshots"][0]["dataset"] == "prices"
    assert "credential_ref" not in json.dumps(providers)


def test_resource_methods_are_tenant_scoped_and_redacted(toolset_core):
    platform = Platform(":memory:")
    tenant_a = platform.auth.create_tenant("tenant-a")
    tenant_b = platform.auth.create_tenant("tenant-b")
    platform.providers.upsert_connection(
        tenant_a,
        provider="alpaca",
        capabilities=["bars"],
        entitlements=[{"dataset": "equities"}],
        account_ref="A-1",
        credential_ref="secret://tenant-a",
    )
    platform.providers.upsert_connection(
        tenant_b,
        provider="ibkr",
        capabilities=["quote"],
        entitlements=[{"dataset": "equities"}],
        account_ref="B-1",
        credential_ref="secret://tenant-b",
    )
    ts = Toolset(
        core=toolset_core,
        sink=PlatformTraceSink(platform.trace),
        runs=platform.runs,
        platform=platform,
    )

    accounts_a = ts.accounts_resource(_ctx={"tenant_id": tenant_a})

    assert accounts_a["accounts"] == []
    assert accounts_a["provider_connections"][0]["account_configured"] is True
    assert "B-1" not in json.dumps(accounts_a)
    assert "A-1" not in json.dumps(accounts_a)
    assert "credential_ref" not in json.dumps(accounts_a)


def test_ibkr_smoke_returns_diagnosis_and_traces_provider_status(toolset, monkeypatch):
    with _QuoteServer() as server:
        monkeypatch.setenv("DOOMBERG_IBKR_ENGINE_URL", server.url)
        monkeypatch.setenv("DOOMBERG_IBKR_QUOTE_PATH", "/quote/{symbol}")

        out = toolset.ibkr_smoke(
            "aapl",
            max_freshness_ms=10_000,
            _ctx={"run_id": R6, "tenant_id": R6, "agent_id": AGENT},
        )

    assert out["ok"] is True
    assert out["quote"]["symbol"] == "AAPL"
    assert "raw" not in out["quote"]
    assert server.requests == [{"path": "/quote/AAPL", "tenant": R6}]
    event = toolset.sink.events(R6)[-1]
    assert event["type"] == "provider_status"
    assert event["data"]["provider"] == "doomberg-live-data"
    assert event["data"]["ok"] is True


def test_run_skill_exposes_live_quote_and_blocks_broker_read_skills(toolset_core, monkeypatch):
    platform = Platform(":memory:")
    tenant = platform.auth.create_tenant("mcp-ibkr")
    ts = Toolset(
        core=toolset_core,
        sink=PlatformTraceSink(platform.trace),
        runs=platform.runs,
        platform=platform,
    )
    ctx = {"tenant_id": tenant, "agent_id": "agent"}
    started = ts.start_research_session("check live quote and broker policy", _ctx=ctx)
    assert started["status"] == "ok"
    with _QuoteServer() as server:
        monkeypatch.setenv("DOOMBERG_IBKR_ENGINE_URL", server.url)
        monkeypatch.setenv("DOOMBERG_IBKR_QUOTE_PATH", "/quote/{symbol}")
        monkeypatch.setenv("DOOMBERG_IBKR_ACCOUNTS_PATH", "/accounts")
        monkeypatch.setenv("DOOMBERG_IBKR_POSITIONS_PATH", "/positions?account={account}")

        quote = ts.run_skill(
            "market.quote",
            input={"symbol": "AAPL", "max_freshness_ms": 10_000},
            _ctx=ctx,
        )
        positions = ts.run_skill(
            "broker.positions",
            input={"account": "DU12345"},
            _ctx=ctx,
        )

    assert quote["status"] == "succeeded"
    assert quote["result"]["data"]["symbol"] == "AAPL"
    assert quote["result"]["provenance"]["source"] == "doomberg-live-data"
    assert positions["status"] == "failed"
    assert positions["error"]["code"] == "POLICY_DENIED"
    assert [request["path"] for request in server.requests] == ["/quote/AAPL"]
    got = ts.get_run(positions["run_id"], _ctx=ctx)
    assert any(
        event["type"] == "error" and event.get("data", {}).get("error") == "POLICY_DENIED"
        for event in got["events"]
    )


def test_run_skill_queues_durable_backtest(toolset_core, sample_spec):
    platform = Platform(":memory:")
    tenant = platform.auth.create_tenant("mcp")
    ts = Toolset(
        core=toolset_core,
        sink=PlatformTraceSink(platform.trace),
        runs=platform.runs,
        platform=platform,
    )
    ctx = {"tenant_id": tenant, "agent_id": "agent"}
    ts.start_research_session("queue durable backtest", _ctx=ctx)

    out = ts.run_skill(
        "backtest.run",
        input={"spec": sample_spec, "range": "1y"},
        idempotency_key="same-backtest",
        _ctx=ctx,
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
        _ctx=ctx,
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
    ctx = {"tenant_id": tenant, "agent_id": "agent"}
    ts.start_research_session("run interactive ohlcv", _ctx=ctx)

    out = ts.run_skill(
        "market.get_ohlcv",
        input={"symbol": "AAA", "range": "1y"},
        _ctx=ctx,
    )

    assert out["status"] == "succeeded"
    got = ts.get_run(out["run_id"], _ctx=ctx)
    assert got["run"]["result"]["provenance"]["source"] == "yahoo-chart"
    assert any(e["type"] == "tool_result" for e in got["events"])


def test_get_run_is_traced_on_active_research_session(toolset_core):
    platform = Platform(":memory:")
    tenant = platform.auth.create_tenant("mcp")
    ts = Toolset(
        core=toolset_core,
        sink=PlatformTraceSink(platform.trace),
        runs=platform.runs,
        platform=platform,
    )
    ctx = {"tenant_id": tenant, "agent_id": "agent"}
    started = ts.start_research_session("inspect durable run", _ctx=ctx)
    run_id = platform.runs.create(tenant, "interactive", None, {"skill_id": "market.get_ohlcv"})

    out = ts.get_run(run_id, _ctx=ctx)

    assert out["run"]["run_id"] == run_id
    events = platform.trace.events(tenant, started["session_id"])
    assert [event["type"] for event in events] == ["session_open", "tool_call", "tool_result"]
    assert events[1]["data"]["name"] == "get_run"


def test_registered_workflow_tools_require_started_session(toolset_core):
    platform = Platform(":memory:")
    tenant = platform.auth.create_tenant("mcp")
    ts = Toolset(
        core=toolset_core,
        sink=PlatformTraceSink(platform.trace),
        runs=platform.runs,
        platform=platform,
    )
    ctx = {"tenant_id": tenant, "agent_id": "agent"}
    run_id = platform.runs.create(tenant, "interactive", None, {"skill_id": "market.get_ohlcv"})

    assert ts.subscribe_run(run_id, _ctx=ctx)["error"]["code"] == "SESSION_CONTEXT_REQUIRED"
    assert ts.triggers_list(_ctx=ctx)["error"]["code"] == "SESSION_CONTEXT_REQUIRED"
    assert ts.alerts_list(_ctx=ctx)["error"]["code"] == "SESSION_CONTEXT_REQUIRED"

    ts.start_research_session("follow workflow tools", _ctx=ctx)

    assert "events" in ts.subscribe_run(run_id, _ctx=ctx)
    assert "triggers" in ts.triggers_list(_ctx=ctx)
    assert "alerts" in ts.alerts_list(_ctx=ctx)


def test_mcp_order_intent_flow_is_disabled(toolset_core):
    platform = Platform(":memory:")
    tenant = platform.auth.create_tenant("mcp-execution")
    run_id = platform.runs.create_research(tenant)
    ts = Toolset(
        core=toolset_core,
        sink=PlatformTraceSink(platform.trace),
        runs=platform.runs,
        platform=platform,
    )

    created = ts.create_order_intent(
        run_id,
        {
            "broker": "paper",
            "symbol": "AAA",
            "side": "buy",
            "quantity": 1,
            "order_type": "limit",
            "limit_price": 100,
        },
        idempotency_key="mcp-intent-1",
        _ctx={"tenant_id": tenant, "agent_id": "agent", "actor_kind": "agent"},
    )
    assert created["error"]["code"] == "POLICY_DENIED"

    preview = ts.preview_order_intent(
        "intent-1",
        _ctx={"tenant_id": tenant, "agent_id": "agent", "actor_kind": "agent"},
    )
    assert preview["error"]["code"] == "POLICY_DENIED"

    fetched = ts.get_order_intent(
        "intent-1",
        _ctx={"tenant_id": tenant, "agent_id": "agent", "actor_kind": "agent"},
    )
    assert fetched["error"]["code"] == "POLICY_DENIED"

    submitted = ts.submit_order_intent(
        "intent-1",
        _ctx={"tenant_id": tenant, "agent_id": "human", "actor_kind": "user"},
    )
    assert submitted["error"]["code"] == "POLICY_DENIED"
    assert platform.approvals.list_pending(tenant) == []
