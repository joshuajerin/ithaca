"""The Doomberg MCP server — Data Layer tools the BYO agent discovers and calls.

The agent can READ (market.get_ohlcv, backtest.run) and PROPOSE (propose_strategy) only —
it can never promote or move money (that's a human action in the web UI). Every call wraps
``doomberg_core.Core`` (so the MCP path and the UI path share one core) and emits a trace
event the observability UI replays. Run: ``python -m doomberg_mcp`` (stdio transport).
"""
from __future__ import annotations

import uuid

from doomberg_core import Core

from .trace import InMemoryTrace, PlatformTraceSink, Tracer

_DEFAULT_TENANT = "00000000-0000-0000-0000-000000000000"

# Pydantic-validated provenance summaries are small; we surface key fields into the trace
# so the UI timeline can show "what came back" without the full payload.


def _provenance_summary(envelope: dict) -> dict:
    prov = envelope.get("provenance") or {}
    return {
        "source": prov.get("source"),
        "freshness": prov.get("freshness"),
        "pit": prov.get("pit"),
        "coverage": prov.get("coverage"),
        "partial": envelope.get("partial"),
    }


class Toolset:
    """The tool implementations, decoupled from transport so they're directly testable.

    When ``runs`` (a ``RunStore``-like with ``create_research``) is provided, the agent's
    activity is grouped into a persistent **research-session run** so it lists + renders in
    the observability UI: the first traced call of a session opens a ``research`` run row and
    a ``session_open`` event, and every subsequent call in that session attaches to the same
    run_id. Without ``runs`` (unit tests), behavior is unchanged — an ephemeral per-call run.
    """

    def __init__(self, core: Core | None = None, sink=None, runs=None):
        self.core = core or Core()
        self.sink = sink or InMemoryTrace()
        self.runs = runs  # optional RunStore-like; enables persistent research sessions
        self._proc_session = uuid.uuid4().hex  # groups a stdio process's calls when ctx has none
        self._sessions: dict[tuple[str, str], str] = {}  # (tenant, session) -> research run_id

    def _research_run(self, tenant_id: str, session: str, agent_id: str | None) -> str:
        """Return (creating if needed) the research run_id for this (tenant, session)."""
        key = (tenant_id, session)
        run_id = self._sessions.get(key)
        if run_id is None:
            run_id = self.runs.create_research(tenant_id)
            self._sessions[key] = run_id
            # Open the session lineage. session_id is the (UUID) research run_id so the event
            # validates; the agent's raw session string rides along in data.
            Tracer(self.sink, run_id=run_id, tenant_id=tenant_id, session_id=run_id,
                   actor_id=agent_id).event("session_open", {"agentSession": session})
        return run_id

    def _tracer(self, ctx: dict | None) -> Tracer:
        ctx = ctx or {}
        tenant_id = ctx.get("tenant_id") or _DEFAULT_TENANT
        agent_id = ctx.get("agent_id")
        if self.runs is not None:
            session = str(ctx.get("session_id") or self._proc_session)
            run_id = self._research_run(tenant_id, session, agent_id)
            return Tracer(self.sink, run_id=run_id, tenant_id=tenant_id,
                          session_id=run_id, actor_id=agent_id)
        # No platform: ephemeral run per the supplied ctx (the unit-test path).
        return Tracer(
            self.sink,
            run_id=ctx.get("run_id") or uuid.uuid4().hex,
            tenant_id=tenant_id,
            session_id=ctx.get("session_id"),
            actor_id=agent_id,
        )

    def market_get_ohlcv(self, symbol: str, range: str = "6mo", interval: str = "1d",
                         _ctx: dict | None = None) -> dict:
        tr = self._tracer(_ctx)
        span = tr.tool_call("market.get_ohlcv", {"symbol": symbol, "range": range, "interval": interval})
        out = self.core.run_tool("market.get_ohlcv", {"symbol": symbol, "range": range, "interval": interval})
        tr.tool_result("market.get_ohlcv", span, _provenance_summary(out))
        return out

    def backtest_run(self, spec: dict, range: str = "1y", _ctx: dict | None = None) -> dict:
        tr = self._tracer(_ctx)
        span = tr.tool_call("backtest.run", {"spec": spec, "range": range})
        out = self.core.run_tool("backtest.run", {"spec": spec, "range": range})
        summary = _provenance_summary(out)
        if out.get("data"):
            summary["stats"] = out["data"].get("stats")
            summary["riskOk"] = out["data"].get("risk", {}).get("ok")
        tr.tool_result("backtest.run", span, summary)
        return out

    def propose_strategy(self, spec: dict, _ctx: dict | None = None) -> dict:
        """Validate a StrategySpec and register it as a DRAFT. No deploy, no money.

        The closed schema rejects any smuggled free-form field. id/version/tenant_id are
        server-stamped; the agent's values are ignored. Real persistence + the run state
        machine live in the control plane — here we validate, stamp a draft id, and emit
        the strategy_proposed event so the proposal shows up in the agent's trace.
        """
        tr = self._tracer(_ctx)
        validated = self.core.validate_spec(spec)  # raises on closed-schema violation
        strategy_id = "stg_" + uuid.uuid4().hex[:12]
        validated["id"] = strategy_id
        tr.event("strategy_proposed", {"strategy_id": strategy_id, "name": validated.get("name")})
        return {"strategy_id": strategy_id, "status": "draft", "spec": validated}


def _platform_backed_toolset() -> Toolset:
    """A Toolset whose trace persists to the shared platform store (``DOOMBERG_DB``).

    Imported lazily so unit tests (which always pass their own Toolset) never need the
    platform package, and a missing/unset DB falls back to ``:memory:``.
    """
    import os

    from doomberg_platform import Platform

    platform = Platform(os.environ.get("DOOMBERG_DB", ":memory:"))
    return Toolset(core=Core(), sink=PlatformTraceSink(platform.trace), runs=platform.runs)


def create_server(toolset: Toolset | None = None):
    """Build the FastMCP server. Imported lazily so the toolset is testable without the SDK."""
    from mcp.server.fastmcp import FastMCP

    ts = toolset or _platform_backed_toolset()
    mcp = FastMCP("doomberg")

    @mcp.tool(description="Fetch OHLCV price history for one symbol, with a provenance envelope.")
    def market_get_ohlcv(symbol: str, range: str = "6mo", interval: str = "1d") -> dict:
        return ts.market_get_ohlcv(symbol, range, interval)

    @mcp.tool(description="Run a price/technical backtest from a declarative StrategySpec.")
    def backtest_run(spec: dict, range: str = "1y") -> dict:
        return ts.backtest_run(spec, range)

    @mcp.tool(description="Validate and register a StrategySpec as a draft (no deploy, no money).")
    def propose_strategy(spec: dict) -> dict:
        return ts.propose_strategy(spec)

    return mcp, ts


def main() -> None:
    mcp, _ = create_server()
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
