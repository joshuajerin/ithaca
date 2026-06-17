"""The Doomberg MCP server — Data Layer tools the BYO agent discovers and calls.

The agent can READ (market.get_ohlcv, backtest.run) and PROPOSE (propose_strategy) only —
it can never promote or move money (that's a human action in the web UI). Every call wraps
``doomberg_core.Core`` (so the MCP path and the UI path share one core) and emits a trace
event the observability UI replays.

Run: ``python -m doomberg_mcp``. Transport is env-selected — ``DOOMBERG_MCP_TRANSPORT=stdio``
(default; locally-trusted, no auth) or ``=http`` (hosted streamable-HTTP for REMOTE BYO
agents, per-tenant bearer auth + scopes; see :mod:`doomberg_mcp.http`).
"""
from __future__ import annotations

import uuid

from doomberg_core import SKILLS, Core, SkillSet

from .trace import InMemoryTrace, PlatformTraceSink, Tracer

_DEFAULT_TENANT = "00000000-0000-0000-0000-000000000000"

# Pydantic-validated provenance summaries are small; we surface key fields into the trace
# so the UI timeline can show "what came back" without the full payload.


def _provenance_summary(envelope: dict) -> dict:
    prov = envelope.get("provenance") or {}
    summary = {
        "source": prov.get("source"),
        "freshness": prov.get("freshness"),
        "pit": prov.get("pit"),
        "coverage": prov.get("coverage"),
        "partial": envelope.get("partial"),
    }
    # Skill envelopes carry warning codes (e.g. ARCHIVE_UNAVAILABLE / PARTIAL_COVERAGE) but no
    # coverage block; surface the codes so the timeline can show "what came back".
    warnings = envelope.get("warnings") or []
    if warnings:
        summary["warnings"] = [w.get("code") for w in warnings if isinstance(w, dict)]
    return summary


class Toolset:
    """The tool implementations, decoupled from transport so they're directly testable.

    When ``runs`` (a ``RunStore``-like with ``create_research``) is provided, the agent's
    activity is grouped into a persistent **research-session run** so it lists + renders in
    the observability UI: the first traced call of a session opens a ``research`` run row and
    a ``session_open`` event, and every subsequent call in that session attaches to the same
    run_id. Without ``runs`` (unit tests), behavior is unchanged — an ephemeral per-call run.
    """

    def __init__(self, core: Core | None = None, sink=None, runs=None, archive=None):
        self.core = core or Core()
        self.sink = sink or InMemoryTrace()
        self.runs = runs  # optional RunStore-like; enables persistent research sessions
        # The archive-backed Skill catalog. ``archive`` is duck-typed to ArchiveGateway; None is
        # fine (skills then return an ARCHIVE_UNAVAILABLE warning instead of crashing).
        self.skills = SkillSet(archive)
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

    def call_skill(self, tool: str, params: dict, _ctx: dict | None = None) -> dict:
        """Run an archive-backed Skill catalog tool, traced exactly like market_get_ohlcv.

        ``tool`` is the canonical SKILLS name (e.g. ``market.news``). Declarative args only — the
        skill never executes agent code. tool_call / tool_result events are emitted on the same
        gap-free, research-session-aware tracer the existing tools use.
        """
        method = SKILLS.get(tool)
        if method is None:
            raise ValueError(f"unknown skill: {tool!r} (have {sorted(SKILLS)})")
        tr = self._tracer(_ctx)
        span = tr.tool_call(tool, params)
        out = getattr(self.skills, method)(params)
        tr.tool_result(tool, span, _provenance_summary(out))
        return out


def _build_archive():
    """Lazily build the real archive gateway from ``DOOMBERG_ARCHIVE_URL``.

    Stream 1's ``doomberg_archive`` package may not be synced yet, so this is best-effort: if the
    package is importable it constructs the gateway, otherwise it returns None and the archive-backed
    skills degrade to a clear ARCHIVE_UNAVAILABLE warning. Never raises at import time.
    """
    import os

    url = os.environ.get("DOOMBERG_ARCHIVE_URL") or os.environ.get("DOOMBERG_DB")
    try:
        from doomberg_archive import ArchiveGateway as _Gateway  # type: ignore
    except Exception:
        return None
    try:
        return _Gateway(url) if url else _Gateway()
    except Exception:
        return None


def _platform_backed_toolset() -> Toolset:
    """A Toolset whose trace persists to the shared platform store (``DOOMBERG_DB``).

    Imported lazily so unit tests (which always pass their own Toolset) never need the
    platform package, and a missing/unset DB falls back to ``:memory:``.
    """
    import os

    from doomberg_platform import Platform

    platform = Platform(os.environ.get("DOOMBERG_DB", ":memory:"))
    return Toolset(
        core=Core(),
        sink=PlatformTraceSink(platform.trace),
        runs=platform.runs,
        archive=_build_archive(),
    )


def _transport_security():
    """DNS-rebinding host policy for the hosted HTTP app.

    The SDK defaults to protection ON with a localhost-only allowlist, which 421s every
    request whose ``Host`` is the public hostname — i.e. anything behind a load balancer. In
    the hosted topology the real network boundary is the auth middleware + the k8s
    Service/NetworkPolicy the lead adds, and the Host arriving at the pod is the LB's choosing,
    so we make the allowlist explicit:

    * ``DOOMBERG_MCP_ALLOWED_HOSTS`` unset → protection OFF (trust the proxy + bearer auth).
    * set (comma-separated, e.g. ``mcp.doomberg.ai,mcp.doomberg.ai:443``) → protection ON,
      restricted to exactly those hosts (``host:*`` wildcard-port patterns supported by the SDK).
    """
    import os

    from mcp.server.transport_security import TransportSecuritySettings

    raw = (os.environ.get("DOOMBERG_MCP_ALLOWED_HOSTS") or "").strip()
    if not raw:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts
    )


def create_server(toolset: Toolset | None = None, *, http: bool = False):
    """Build the FastMCP server. Imported lazily so the toolset is testable without the SDK.

    ``http=True`` (the hosted path) makes every tool wrapper resolve the per-request
    authenticated principal and pass it into the Toolset as ``_ctx`` — so each remote call is
    tenant-scoped and traced under the verified tenant. ``http=False`` (stdio / unit tests) is
    the existing locally-trusted behavior: no ``_ctx`` is injected (an ephemeral/dev session).
    """
    from mcp.server.fastmcp import FastMCP

    ts = toolset or _platform_backed_toolset()
    mcp = FastMCP("doomberg", transport_security=_transport_security() if http else None)

    def _ctx() -> dict | None:
        """The per-request tenant ``_ctx`` in HTTP mode; None in stdio mode."""
        if not http:
            return None
        from .http import current_principal

        principal = current_principal()
        return principal.ctx() if principal is not None else None

    def call_skill(tool: str, params: dict) -> dict:
        """Skill-catalog dispatch that injects the per-request tenant ``_ctx`` (HTTP mode)."""
        return ts.call_skill(tool, params, _ctx=_ctx())

    @mcp.tool(description="Fetch OHLCV price history for one symbol, with a provenance envelope.")
    def market_get_ohlcv(symbol: str, range: str = "6mo", interval: str = "1d") -> dict:
        return ts.market_get_ohlcv(symbol, range, interval, _ctx=_ctx())

    @mcp.tool(description="Run a price/technical backtest from a declarative StrategySpec.")
    def backtest_run(spec: dict, range: str = "1y") -> dict:
        return ts.backtest_run(spec, range, _ctx=_ctx())

    @mcp.tool(description="Validate and register a StrategySpec as a draft (no deploy, no money).")
    def propose_strategy(spec: dict) -> dict:
        return ts.propose_strategy(spec, _ctx=_ctx())

    # ---- archive-backed Skill catalog (declarative args only, traced like market.get_ohlcv) ----
    @mcp.tool(name="market_news",
              description="Recent news headlines for a ticker or sector, from the v1 archive.")
    def market_news(ticker: str | None = None, sector: str | None = None, limit: int = 50) -> dict:
        return call_skill("market.news", {"ticker": ticker, "sector": sector, "limit": limit})

    @mcp.tool(name="market_screener",
              description="Ranked equity screen over the tracked universe (fundamentals + 1Y return).")
    def market_screener(sector: str | None = None, limit: int = 100) -> dict:
        return call_skill("market.screener", {"sector": sector, "limit": limit})

    @mcp.tool(name="market_movers",
              description="Heatmap-style market movers with 1D moves and trailing returns.")
    def market_movers(sector: str | None = None, limit: int = 100) -> dict:
        return call_skill("market.movers", {"sector": sector, "limit": limit})

    @mcp.tool(name="fundamentals_get",
              description="Single-name fundamentals metric cards from the archive.")
    def fundamentals_get(symbol: str) -> dict:
        return call_skill("fundamentals.get", {"symbol": symbol})

    @mcp.tool(name="fundamentals_compare",
              description="Peer comparison table across two or more symbols.")
    def fundamentals_compare(symbols: list[str]) -> dict:
        return call_skill("fundamentals.compare", {"symbols": symbols})

    @mcp.tool(name="fundamentals_pit",
              description="Point-in-time fundamentals: the latest report known on/before as_of (pit=true).")
    def fundamentals_pit(symbol: str, as_of: str | None = None) -> dict:
        return call_skill("fundamentals.pit", {"symbol": symbol, "as_of": as_of})

    @mcp.tool(name="analyst_ratings",
              description="Wall Street consensus, price-target band and recent changes for a ticker.")
    def analyst_ratings(symbol: str) -> dict:
        return call_skill("analyst.ratings", {"symbol": symbol})

    @mcp.tool(name="congress_trades",
              description="STOCK Act congressional trading disclosures, with notable highlights.")
    def congress_trades(ticker: str | None = None, member: str | None = None, limit: int = 60) -> dict:
        return call_skill("congress.trades", {"ticker": ticker, "member": member, "limit": limit})

    @mcp.tool(name="insider_activity",
              description="SEC Form 4/5 insider transactions for one ticker with a net buy/sell summary.")
    def insider_activity(symbol: str, limit: int = 100) -> dict:
        return call_skill("insider.activity", {"symbol": symbol, "limit": limit})

    @mcp.tool(name="institutional_holdings",
              description="Top 13F institutional holders of one ticker with QoQ change.")
    def institutional_holdings(symbol: str) -> dict:
        return call_skill("institutional.holdings", {"symbol": symbol})

    @mcp.tool(name="institutional_flows",
              description="QoQ institutional fund flows (biggest buyers/sellers) in one ticker.")
    def institutional_flows(symbol: str) -> dict:
        return call_skill("institutional.flows", {"symbol": symbol})

    @mcp.tool(name="etf_holdings",
              description="Ranked constituents of an ETF with top-N concentration.")
    def etf_holdings(etf: str) -> dict:
        return call_skill("etf.holdings", {"etf": etf})

    @mcp.tool(name="etf_exposure",
              description="Reverse lookup: which ETFs hold a given stock, and at what weight.")
    def etf_exposure(symbol: str) -> dict:
        return call_skill("etf.exposure", {"symbol": symbol})

    @mcp.tool(name="sentiment_get",
              description="Persisted sentiment snapshot for a symbol, sector or topic.")
    def sentiment_get(scope: str, scope_type: str | None = None) -> dict:
        return call_skill("sentiment.get", {"scope": scope, "scope_type": scope_type})

    @mcp.tool(name="macro_dashboard",
              description="Macro tiles grouped by asset class with a rule-based regime read.")
    def macro_dashboard() -> dict:
        return call_skill("macro.dashboard", {})

    @mcp.tool(name="universe_list",
              description="Investable-universe overview: symbols, sectors and coverage.")
    def universe_list(sector: str | None = None, limit: int = 150) -> dict:
        return call_skill("universe.list", {"sector": sector, "limit": limit})

    # ---- COMPUTED skills (source="computed"): pure math on agent inputs / real archive series ----
    @mcp.tool(name="options_greeks",
              description="Black-Scholes price + greeks for one European option (agent-supplied "
                          "S, K, T-years, r, sigma, type=call|put). Computed, no market data.")
    def options_greeks(S: float, K: float, T: float, sigma: float, r: float = 0.0,
                       type: str = "call") -> dict:
        return call_skill("options.greeks",
                             {"S": S, "K": K, "T": T, "r": r, "sigma": sigma, "type": type})

    @mcp.tool(name="options_implied_vol",
              description="Black-Scholes implied volatility from an observed option price "
                          "(agent-supplied price, S, K, T-years, r, type). Computed.")
    def options_implied_vol(price: float, S: float, K: float, T: float, r: float = 0.0,
                           type: str = "call") -> dict:
        return call_skill("options.implied_vol",
                             {"price": price, "S": S, "K": K, "T": T, "r": r, "type": type})

    @mcp.tool(name="vol_realized",
              description="Annualized realized (close-to-close log-return) volatility computed over "
                          "real archive closes for a symbol.")
    def vol_realized(symbol: str, lookback: int = 0) -> dict:
        return call_skill("vol.realized", {"symbol": symbol, "lookback": lookback})

    @mcp.tool(name="vol_term_structure",
              description="Realized-vol term structure at trailing windows (default 20/60/120/252) "
                          "computed over real archive closes.")
    def vol_term_structure(symbol: str, windows: list[int] | None = None) -> dict:
        return call_skill("vol.term_structure", {"symbol": symbol, "windows": windows})

    @mcp.tool(name="correlation_matrix",
              description="Pearson correlation matrix of daily returns across symbols, computed on "
                          "real archive closes (symmetric, 1.0 diagonal).")
    def correlation_matrix(symbols: list[str], lookback: int = 0) -> dict:
        return call_skill("correlation.matrix", {"symbols": symbols, "lookback": lookback})

    @mcp.tool(name="factor_exposures",
              description="Standardized style-factor exposures (Market/Size/Value/Momentum/Quality) "
                          "cross-sectionally z-scored from real archive fundamentals.")
    def factor_exposures(symbols: list[str] | None = None, sector: str | None = None) -> dict:
        return call_skill("factor.exposures", {"symbols": symbols, "sector": sector})

    @mcp.tool(name="dcf_value",
              description="5-year discounted-cash-flow valuation seeded from a symbol's archive "
                          "fundamentals; agent may override DCF assumptions. Deterministic.")
    def dcf_value(symbol: str, assumptions: dict | None = None) -> dict:
        return call_skill("dcf.value", {"symbol": symbol, "assumptions": assumptions})

    @mcp.tool(name="portfolio_optimize",
              description="Mean-variance optimal long-only weights over real archive returns "
                          "(mode=max_sharpe|min_variance|target_vol). Weights sum to ~1.")
    def portfolio_optimize(symbols: list[str] | None = None, sector: str | None = None,
                          mode: str = "max_sharpe") -> dict:
        return call_skill("portfolio.optimize",
                             {"symbols": symbols, "sector": sector, "mode": mode})

    @mcp.tool(name="montecarlo_simulate",
              description="GBM/bootstrap terminal-price distribution (percentile fan + summary). "
                          "Deterministic via 'seed'. Drives from a symbol's archive history, or "
                          "agent-supplied sigma/drift/S.")
    def montecarlo_simulate(symbol: str | None = None, sigma: float | None = None,
                           drift: float = 0.0, S: float | None = None, horizon: int = 252,
                           paths: int = 1000, seed: int = 12345, method: str = "gbm") -> dict:
        return call_skill("montecarlo.simulate",
                             {"symbol": symbol, "sigma": sigma, "drift": drift, "S": S,
                              "horizon": horizon, "paths": paths, "seed": seed, "method": method})

    @mcp.tool(name="scenario_project",
              description="Baseline-vs-scenario forward projection: Monte-Carlo baseline on a "
                          "symbol's real history plus an explicit incremental annualized drift. "
                          "Deterministic via 'seed'.")
    def scenario_project(symbol: str, scenarioDriftPct: float = 0.0, horizon: int = 252,
                        paths: int = 1000, seed: int = 4242) -> dict:
        return call_skill("scenario.project",
                             {"symbol": symbol, "scenarioDriftPct": scenarioDriftPct,
                              "horizon": horizon, "paths": paths, "seed": seed})

    @mcp.tool(name="risk_stress",
              description="Estimate book P&L under agent-supplied shocks: factor shocks "
                          "(exposures x shocks) or asset shocks (weights x shocks). Computed.")
    def risk_stress(shocks: dict, exposures: dict | None = None,
                   weights: dict | None = None) -> dict:
        return call_skill("risk.stress",
                             {"shocks": shocks, "exposures": exposures, "weights": weights})

    @mcp.tool(name="tearsheet",
              description="Single-strategy backtest tearsheet (curve, drawdown, trade log, stats) "
                          "over a symbol's real archive closes.")
    def tearsheet(symbol: str, strategy: str = "momentum", params: dict | None = None,
                 cost_bps: float = 5.0) -> dict:
        return call_skill("tearsheet",
                             {"symbol": symbol, "strategy": strategy, "params": params,
                              "cost_bps": cost_bps})

    @mcp.tool(name="walkforward_run",
              description="Anchored walk-forward validation + overfitting diagnostics over a "
                          "symbol's real archive closes (honest coverage block, no fabricated folds).")
    def walkforward_run(symbol: str, strategy: str = "momentum", n_splits: int = 5) -> dict:
        return call_skill("walkforward.run",
                             {"symbol": symbol, "strategy": strategy, "n_splits": n_splits})

    return mcp, ts


def main() -> None:
    """Entry point for ``python -m doomberg_mcp``.

    Transport is selected by env (so the same image serves both modes):

    * ``DOOMBERG_MCP_TRANSPORT=stdio`` (default) — a locally-launched, locally-trusted agent;
      no auth, the existing dev behavior.
    * ``DOOMBERG_MCP_TRANSPORT=http`` — hosted streamable-HTTP for REMOTE BYO agents, served
      by uvicorn on ``DOOMBERG_MCP_PORT`` (default 8080, bind 0.0.0.0), with per-tenant bearer
      auth + scope enforcement (see :mod:`doomberg_mcp.http`).
    """
    import os

    transport = (os.environ.get("DOOMBERG_MCP_TRANSPORT") or "stdio").strip().lower()
    if transport == "http":
        from .http import serve_http

        port = int(os.environ.get("DOOMBERG_MCP_PORT", "8080"))
        serve_http(host="0.0.0.0", port=port)
        return
    mcp, _ = create_server()
    mcp.run()  # stdio transport (default; local trust, no auth)


if __name__ == "__main__":
    main()
