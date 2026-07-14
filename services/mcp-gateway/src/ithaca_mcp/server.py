"""The Ithaca MCP server — Data Layer tools the BYO agent discovers and calls.

The agent can READ (market.get_ohlcv, backtest.run) and PROPOSE (propose_strategy) only —
it can never promote or move money (that's a human action in the web UI). Every call wraps
``ithaca_core.Core`` (so the MCP path and the UI path share one core) and emits a trace
event the observability UI replays.

Run: ``python -m ithaca_mcp``. Transport is env-selected — ``ITHACA_MCP_TRANSPORT=stdio``
(default; locally-trusted, no auth) or ``=http`` (hosted streamable-HTTP for REMOTE BYO
agents, per-tenant bearer auth + scopes; see :mod:`ithaca_mcp.http`).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from ithaca_control.actions import ActionError
from ithaca_control.deps import Ctx
from ithaca_control.execution_gateway import ExecutionPolicy
from ithaca_core import ALL_SKILL_MANIFESTS, SKILLS, Core, SkillSet
from ithaca_core.providers import PUBLIC_DATA_SOURCE, PUBLIC_ENTITLEMENT_CLASS, IbkrEngineClient, IbkrEngineError
from ithaca_platform import TransitionConflict

from .trace import InMemoryTrace, PlatformTraceSink, Tracer

_DEFAULT_TENANT = "00000000-0000-0000-0000-000000000000"

_TYPED_ERROR_CODES = [
    "AUTH_REQUIRED",
    "BROKER_CONNECTION_REQUIRED",
    "ENTITLEMENT_REQUIRED",
    "DATA_STALE",
    "PROVIDER_DEGRADED",
    "RATE_LIMITED",
    "SESSION_CONTEXT_REQUIRED",
    "INVALID_SYMBOL",
    "MARKET_CLOSED",
    "JOB_QUEUED",
    "JOB_BUDGET_EXCEEDED",
    "POLICY_DENIED",
    "APPROVAL_REQUIRED",
    "ORDER_STATE_CONFLICT",
    "DUPLICATE_IDEMPOTENCY_KEY",
]

_PUBLIC_SKILL_IDS = {
    "backtest.run",
    "market.get_ohlcv",
    "market.movers",
    "market.news",
    "market.quote",
    "market.screener",
    "options.greeks",
    "options.implied_vol",
    "risk.stress",
    "vix.term_structure",
}

_TOOLKITS: dict[str, dict] = {
    "session": {
        "name": "Research Session",
        "description": "Start a visible Ithaca session, follow durable runs, cancel work, and fetch artifacts.",
        "direct_tools": [
            "start_research_session",
            "get_run",
            "subscribe_run",
            "cancel_run",
            "get_artifact",
        ],
        "skill_ids": [],
        "required_first_tool": "start_research_session",
    },
    "market-research": {
        "name": "Market Research",
        "description": "Ithaca live-data quotes, history, news, movers, screeners, and volatility context.",
        "direct_tools": [
            "market_quote",
            "market_get_ohlcv",
            "market_news",
            "market_screener",
            "market_movers",
            "vix_term_structure",
        ],
        "skill_ids": [
            "market.news",
            "market.screener",
            "market.movers",
            "vix.term_structure",
        ],
        "required_first_tool": "start_research_session",
    },
    "computed-risk": {
        "name": "Computed Risk",
        "description": "Pure computed options, risk shock, and volatility context without archive data.",
        "direct_tools": [
            "options_greeks",
            "options_implied_vol",
            "risk_stress",
            "vix_term_structure",
        ],
        "skill_ids": [
            "options.greeks",
            "options.implied_vol",
            "risk.stress",
            "vix.term_structure",
        ],
        "required_first_tool": "start_research_session",
    },
    "backtest-paper": {
        "name": "Backtest And Paper Handoff",
        "description": "Validate strategy specs, run backtests, queue durable skill runs, and inspect paper approvals.",
        "direct_tools": [
            "propose_strategy",
            "backtest_run",
            "run_skill",
            "get_run",
            "subscribe_run",
            "list_approvals",
            "decide_approval",
            "get_artifact",
        ],
        "skill_ids": ["tearsheet", "walkforward.run"],
        "required_first_tool": "start_research_session",
    },
}


def _json_resource(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _without_none(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if v is not None}


def _public_connection(connection: dict) -> dict:
    """Return an agent-safe provider connection view with no credential material."""
    provider = str(connection.get("provider") or "")
    public_provider = PUBLIC_DATA_SOURCE if provider.lower() in {
        "ibkr",
        "ibkr-engine",
        "interactive_brokers",
        "interactive-brokers",
    } else provider
    return _without_none({
        "connection_id": connection.get("connection_id"),
        "provider": public_provider,
        "state": connection.get("state"),
        "account_configured": bool(connection.get("account_ref")),
        "capabilities": [
            cap for cap in (connection.get("capabilities") or [])
            if str(cap).strip().lower() not in {"orders", "trading", "execution"}
        ],
        "entitlements": [
            {**ent, "entitlement_class": PUBLIC_ENTITLEMENT_CLASS}
            if isinstance(ent, dict) and provider.lower() in {"ibkr", "ibkr-engine", "interactive_brokers", "interactive-brokers"}
            else ent
            for ent in (connection.get("entitlements") or [])
        ],
        "retention_policy": connection.get("retention_policy"),
        "created_at": connection.get("created_at"),
        "updated_at": connection.get("updated_at"),
    })

# Pydantic-validated provenance summaries are small; we surface key fields into the trace
# so the UI timeline can show "what came back" without the full payload.


def _provenance_summary(envelope: dict) -> dict:
    prov = envelope.get("provenance") or {}
    summary = {
        "source": PUBLIC_DATA_SOURCE if prov.get("source") == "ibkr-engine" else prov.get("source"),
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


def _ibkr_skill_envelope(data: dict, *, as_of: str | None = None) -> dict:
    """Wrap private live market data in the same envelope shape as catalog skills."""

    as_of = as_of or datetime.now(timezone.utc).isoformat()
    sanitized = _sanitize_live_data(data)
    return {
        "data": sanitized,
        "provenance": {
            "source": PUBLIC_DATA_SOURCE,
            "as_of": as_of,
            "freshness": "live",
            "stale_age_sec": None,
            "pit": "false",
            "coverage": {"requested": 1, "resolved": 1, "missing": []},
            "cost": {"class": PUBLIC_ENTITLEMENT_CLASS, "credits": 0},
            "cache_hit": False,
        },
        "partial": False,
        "warnings": [],
    }


def _live_news_unavailable_envelope(reason: str, *, scope: str | None = None) -> dict:
    scope = (scope or "Markets").strip().upper() or "Markets"
    return {
        "data": {
            "scope": scope,
            "items": [],
            "count": 0,
            "sentimentMix": {"positive": 0, "negative": 0, "neutral": 0},
            "asOf": datetime.now(timezone.utc).isoformat(),
            "provider": PUBLIC_DATA_SOURCE,
        },
        "provenance": {
            "source": PUBLIC_DATA_SOURCE,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "freshness": "unavailable",
            "stale_age_sec": None,
            "pit": "false",
            "coverage": {"requested": 1, "resolved": 0, "missing": [scope]},
            "cost": {"class": PUBLIC_ENTITLEMENT_CLASS, "credits": 0},
            "cache_hit": False,
        },
        "partial": True,
        "warnings": [{
            "code": "LIVE_NEWS_UNAVAILABLE",
            "scope": scope,
            "detail": reason or "live news is unavailable from the configured live data engine",
        }],
    }


def _market_activity_news_items(rows: list[dict], *, as_of: str, limit: int) -> list[dict]:
    items: list[dict] = []
    for idx, row in enumerate(rows[:limit], start=1):
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        rank = row.get("rank") or idx
        bits = []
        name = row.get("name")
        exchange = row.get("exchange")
        price = row.get("price")
        change_pct = row.get("changePct")
        if name:
            bits.append(str(name))
        if exchange:
            bits.append(f"listed on {exchange}")
        if price is not None:
            bits.append(f"last price {price}")
        if change_pct is not None:
            bits.append(f"change {change_pct}%")
        summary = "; ".join(bits) or "Recent live market-activity signal from Ithaca live data."
        items.append({
            "id": f"market-activity-{symbol}-{rank}",
            "headline": f"{symbol} active in Ithaca live market scan",
            "source": PUBLIC_DATA_SOURCE,
            "summary": summary,
            "url": None,
            "publishedAt": as_of,
            "sentiment": None,
            "tickers": [symbol],
            "sector": None,
            "kind": "market_activity",
        })
    return items


def _sanitize_live_data(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lk = str(key).lower()
            if lk in {"source_account", "account_ref", "credential_ref", "host", "quote_path", "order_path"}:
                continue
            if lk in {"provider", "source"} and str(item).lower() in {
                "ibkr",
                "ibkr-engine",
                "ibkr-client-portal",
                "interactive_brokers",
                "interactive-brokers",
            }:
                out[key] = PUBLIC_DATA_SOURCE
            elif lk == "entitlement_class" and str(item) == "connected_account":
                out[key] = PUBLIC_ENTITLEMENT_CLASS
            elif isinstance(item, str):
                out[key] = (
                    item.replace("IBKR", "Ithaca")
                    .replace("ibkr-engine", PUBLIC_DATA_SOURCE)
                    .replace("ibkr-client-portal", "private-market-data")
                )
            else:
                out[key] = _sanitize_live_data(item)
        return out
    if isinstance(value, list):
        return [_sanitize_live_data(item) for item in value]
    return value


def _i(value, default: int, lo: int, hi: int) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = default
    return max(lo, min(hi, out))


class Toolset:
    """The tool implementations, decoupled from transport so they're directly testable.

    When ``runs`` (a ``RunStore``-like with ``create_research``) is provided, the agent's
    activity is grouped into a persistent **research-session run** so it lists + renders in
    the observability UI: the first traced call of a session opens a ``research`` run row and
    a ``session_open`` event, and every subsequent call in that session attaches to the same
    run_id. Without ``runs`` (unit tests), behavior is unchanged — an ephemeral per-call run.
    """

    def __init__(self, core: Core | None = None, sink=None, runs=None, archive=None, platform=None):
        self.core = core or Core()
        self.sink = sink or InMemoryTrace()
        self.platform = platform
        self.runs = runs  # optional RunStore-like; enables persistent research sessions
        # Legacy SkillSet is retained for pure computed catalog tools; no hosted archive is wired.
        self.skills = SkillSet(archive)
        self._proc_session = uuid.uuid4().hex  # groups a stdio process's calls when ctx has none
        self._sessions: dict[tuple[str, str], str] = {}  # (tenant, session) -> research run_id
        self._agent_active_sessions: dict[tuple[str, str], str] = {}

    def _agent_session_key(self, tenant_id: str, agent_id: str | None) -> tuple[str, str]:
        return (tenant_id, str(agent_id or self._proc_session))

    def _existing_research_run(self, tenant_id: str, session: str) -> str | None:
        """If `session` is an existing research run id, reuse it instead of creating another."""
        try:
            uuid.UUID(str(session))
        except (TypeError, ValueError):
            return None
        getter = getattr(self.runs, "get", None)
        if getter is None:
            return None
        try:
            run = getter(tenant_id, session)
        except TypeError:
            return None
        if run and run.get("kind") == "research":
            return str(session)
        return None

    def _research_run(self, tenant_id: str, session: str, agent_id: str | None) -> str:
        """Return (creating if needed) the research run_id for this (tenant, session)."""
        key = (tenant_id, session)
        run_id = self._sessions.get(key)
        if run_id is None:
            run_id = self._existing_research_run(tenant_id, session)
            created = run_id is None
            if run_id is None:
                run_id = self.runs.create_research(tenant_id)
            self._sessions[key] = run_id
            if created:
                # Open the session lineage. session_id is the (UUID) research run_id so the
                # event validates; the agent's raw session string rides along in data.
                Tracer(self.sink, run_id=run_id, tenant_id=tenant_id, session_id=run_id,
                       actor_id=agent_id).event("session_open", {"agentSession": session})
        return run_id

    def _active_research_session(self, ctx: dict | None) -> str | None:
        """Return the active research session for this tenant+agent, if one exists."""
        if self.runs is None:
            return None
        ctx = dict(ctx or {})
        tenant_id = ctx.get("tenant_id") or _DEFAULT_TENANT
        agent_id = ctx.get("agent_id")
        explicit_session = ctx.get("session_id")
        if explicit_session:
            existing = self._existing_research_run(tenant_id, str(explicit_session))
            if existing is not None:
                self._agent_active_sessions[self._agent_session_key(tenant_id, agent_id)] = existing
                return existing
        active = self._agent_active_sessions.get(self._agent_session_key(tenant_id, agent_id))
        if active:
            return active
        return None

    def _with_active_session(self, ctx: dict | None) -> dict:
        """Copy ctx and attach the active research session id when one is known."""
        out = dict(ctx or {})
        active = self._active_research_session(out)
        if active is not None and not out.get("run_id") and not out.get("session_id"):
            out["session_id"] = active
        return out

    def _session_context_required(self) -> dict:
        return self._typed_error(
            "SESSION_CONTEXT_REQUIRED",
            "start a Ithaca research session before calling data or workflow tools",
            "Call start_research_session with the user's prompt, then call direct tools.",
        )

    def _require_research_session(self, ctx: dict | None) -> dict | None:
        if self.runs is None:
            return None
        if self._active_research_session(ctx) is not None:
            return None
        return self._session_context_required()

    def _trace_workflow_tool(self, name: str, params: dict, result: dict,
                             ctx: dict | None) -> dict:
        if self.runs is None:
            return result
        trace_ctx = self._with_active_session(ctx)
        tr = self._tracer(trace_ctx)
        span = tr.tool_call(name, params)
        summary = {"status": "ok"}
        error = result.get("error") if isinstance(result, dict) else None
        if isinstance(error, dict):
            summary = {"status": "error", "error": error.get("code")}
        elif isinstance(result, dict):
            for key in ("run_id", "status", "cursor"):
                if key in result:
                    summary[key] = result[key]
            if isinstance(result.get("events"), list):
                summary["event_count"] = len(result["events"])
            if isinstance(result.get("jobs"), list):
                summary["job_count"] = len(result["jobs"])
            if isinstance(result.get("artifacts"), list):
                summary["artifact_count"] = len(result["artifacts"])
        tr.tool_result(name, span, summary)
        return result

    def _tracer(self, ctx: dict | None) -> Tracer:
        ctx = ctx or {}
        tenant_id = ctx.get("tenant_id") or _DEFAULT_TENANT
        agent_id = ctx.get("agent_id")
        if self.runs is not None:
            explicit_run = ctx.get("run_id")
            if explicit_run:
                try:
                    run = self.runs.get(tenant_id, str(explicit_run))
                except TypeError:
                    run = None
                if run is not None:
                    return Tracer(self.sink, run_id=str(explicit_run), tenant_id=tenant_id,
                                  session_id=str(explicit_run), actor_id=agent_id)
            active = self._agent_active_sessions.get(self._agent_session_key(tenant_id, agent_id))
            session = str(ctx.get("session_id") or active or self._proc_session)
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

    def start_research_session(self, prompt: str, title: str | None = None,
                               session_id: str | None = None, _ctx: dict | None = None) -> dict:
        """Start or attach the required research session for direct tool calls.

        If ``session_id`` is an existing research-run UUID opened by the web UI, future calls
        from the same tenant+agent key are grouped into that run. If omitted, this opens a
        new research run and records the user prompt on the visible session trace.
        """
        ctx = dict(_ctx or {})
        tenant_id = ctx.get("tenant_id") or _DEFAULT_TENANT
        agent_id = ctx.get("agent_id")
        prompt = str(prompt or "").strip()
        if not prompt:
            return self._typed_error(
                "SESSION_CONTEXT_REQUIRED",
                "start_research_session requires the user's prompt",
                "Pass the full user prompt before calling direct tools.",
            )

        if self.runs is None:
            run_id = str(session_id or ctx.get("run_id") or uuid.uuid4())
            self._agent_active_sessions[self._agent_session_key(tenant_id, agent_id)] = run_id
            tr = Tracer(self.sink, run_id=run_id, tenant_id=tenant_id,
                        session_id=run_id, actor_id=agent_id)
            tr.event("session_open", _without_none({
                "kind": "research_session",
                "prompt": prompt,
                "text": prompt,
                "title": title,
            }))
            return {"status": "ok", "session_id": run_id, "prompt_captured": True}

        existing = self._existing_research_run(tenant_id, str(session_id)) if session_id else None
        created = existing is None
        run_id = existing or self.runs.create_research(tenant_id)
        if session_id:
            self._sessions[(tenant_id, str(session_id))] = run_id
        self._sessions[(tenant_id, run_id)] = run_id
        self._agent_active_sessions[self._agent_session_key(tenant_id, agent_id)] = run_id

        tr = Tracer(self.sink, run_id=run_id, tenant_id=tenant_id,
                    session_id=run_id, actor_id=agent_id)
        data = {
            "kind": "research_session",
            "prompt": prompt,
            "text": prompt,
        }
        if title is not None:
            data["title"] = title
        if created:
            tr.event("session_open", data)
        else:
            tr.event("reasoning", data)
        return {"status": "ok", "session_id": run_id, "prompt_captured": True}

    def session_context(self, prompt: str | None = None, title: str | None = None,
                        session_id: str | None = None, _ctx: dict | None = None) -> dict:
        """Backward-compatible alias for start_research_session."""
        return self.start_research_session(
            prompt=prompt or "",
            title=title,
            session_id=session_id,
            _ctx=_ctx,
        )

    def ithaca_init(self, goal: str | None = None, _ctx: dict | None = None) -> dict:
        """First tool call after an agent installs Ithaca MCP.

        This gives the agent a small, explicit bootstrap contract instead of forcing it to infer
        the workflow from the full tool list.
        """
        visible_prompt = str(goal or "").strip() or "Initialize Ithaca MCP session"
        session = self.session_context(
            prompt=visible_prompt,
            title="Ithaca onboarding",
            _ctx=_ctx,
        )
        direct_tools = self._direct_tool_catalog()
        return {
            "status": "ready",
            "session_id": session["session_id"],
            "session": {
                "session_id": session["session_id"],
                "prompt": visible_prompt,
                "title": "Ithaca onboarding",
                "required": True,
                "context": "All subsequent direct tools are attached to this authenticated research session.",
            },
            "goal_captured": bool(goal),
            "start_here": [
                {
                    "tool": "start_research_session",
                    "status": "already_started_by_ithaca_init",
                    "when": "Use only if the user changes tasks or you need to attach a web-created session_id.",
                },
                {
                    "tool": "market_quote",
                    "when": "Fetch the current live quote for one symbol, including extended-hours data when requested.",
                },
                {
                    "tool": "market_get_ohlcv",
                    "when": "Fetch quick OHLCV history directly.",
                },
                {
                    "tool": "run_skill",
                    "when": "Create a durable run for backtests or longer research jobs inside this session.",
                },
                {
                    "tool": "get_run",
                    "when": "Inspect visible run state, jobs, artifacts, and trace events.",
                },
                {
                    "tool": "propose_strategy",
                    "when": "Register a validated draft StrategySpec for human review.",
                },
            ],
            "direct_tools": direct_tools,
            "toolkits": self.list_toolkits()["toolkits"],
            "discovery_helpers": ["list_toolkits", "describe_toolkit", "search_skills", "describe_skill"],
            "boundaries": {
                "can": ["read market data", "run backtests", "draft strategy proposals", "paper-trading research"],
                "cannot": ["deploy live strategies", "move money", "read raw broker credentials"],
            },
            "dashboard_url": "https://app.tradeithaca.com/dashboard",
        }

    def market_get_ohlcv(self, symbol: str, range: str = "6mo", interval: str = "1d",
                         _ctx: dict | None = None) -> dict:
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        _ctx = self._with_active_session(_ctx)
        tr = self._tracer(_ctx)
        span = tr.tool_call("market.get_ohlcv", {"symbol": symbol, "range": range, "interval": interval})
        ctx = dict(_ctx or {})
        tenant_id = ctx.get("tenant_id") or _DEFAULT_TENANT
        client = IbkrEngineClient()
        if not client.configured():
            out = self._typed_error(
                "BROKER_CONNECTION_REQUIRED",
                "live history requires the Ithaca live-data engine",
                "Configure ITHACA_IBKR_ENGINE_URL and rerun market_get_ohlcv.",
            )
            tr.tool_result("market.get_ohlcv", span, {"source": PUBLIC_DATA_SOURCE, "ok": False,
                                                      "code": out["error"]["code"]})
            return out
        try:
            period, bar = self._ibkr_history_window(range, interval)
            raw = client.history(symbol, period=period, bar=bar, tenant_id=tenant_id)
            points = raw.get("points") or []
            out = _ibkr_skill_envelope(
                {
                    "symbol": str(raw.get("symbol") or symbol).upper(),
                    "points": points,
                    "quote": raw.get("quote") or {},
                    "provider": PUBLIC_DATA_SOURCE,
                    "period": raw.get("period") or period,
                    "bar": raw.get("bar") or bar,
                },
                as_of=(raw.get("quote") or {}).get("asOf")
                or (points[-1].get("t") or points[-1].get("d") if points else None),
            )
        except IbkrEngineError as exc:
            out = self._typed_error(
                "PROVIDER_DEGRADED",
                f"live history unavailable: {exc}",
                "Check the Ithaca live-data engine history route and IBKR session entitlements.",
            )
        tr.tool_result("market.get_ohlcv", span, _provenance_summary(out))
        return out

    def market_quote(
        self,
        symbol: str,
        *,
        max_freshness_ms: int | None = None,
        include_extended_hours: bool = False,
        _ctx: dict | None = None,
    ) -> dict:
        """Entitlement-aware realtime quote via the private live-data engine."""

        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        _ctx = self._with_active_session(_ctx)
        ctx = dict(_ctx or {})
        tenant_id = ctx.get("tenant_id") or _DEFAULT_TENANT
        tr = self._tracer(_ctx)
        span = tr.tool_call(
            "market.quote",
            {
                "symbol": symbol,
                "max_freshness_ms": max_freshness_ms,
                "include_extended_hours": include_extended_hours,
            },
        )
        client = IbkrEngineClient()
        diagnosis = client.diagnose_quote(
            symbol=symbol,
            tenant_id=tenant_id,
            max_freshness_ms=max_freshness_ms,
            include_extended_hours=include_extended_hours,
        )
        if not diagnosis.get("ok"):
            out = self._typed_error(
                diagnosis.get("code") or "PROVIDER_DEGRADED",
                diagnosis.get("error") or diagnosis.get("status") or "live quote failed",
                diagnosis.get("recovery_action") or "Check live market-data connectivity and entitlements.",
                {"diagnosis": {k: v for k, v in diagnosis.items() if k != "quote"}},
            )
            tr.tool_result("market.quote", span, {"source": PUBLIC_DATA_SOURCE, "ok": False,
                                                  "code": out["error"]["code"]})
            return out
        quote = diagnosis["quote"]
        out = _ibkr_skill_envelope(
            {
                **quote,
                "provider": PUBLIC_DATA_SOURCE,
                "diagnostics": {
                    "latency_ms": diagnosis.get("latency_ms"),
                    "invariants": diagnosis.get("invariants") or [],
                },
            },
            as_of=quote.get("event_time"),
        )
        tr.tool_result("market.quote", span, _provenance_summary(out))
        return out

    def market_news(self, ticker: str | None = None, sector: str | None = None,
                    limit: int = 50, _ctx: dict | None = None) -> dict:
        """Live market news only.

        The direct MCP news tool must not silently fall back to the old archive because agents
        use it for "latest news" questions.
        """

        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        _ctx = self._with_active_session(_ctx)
        tr = self._tracer(_ctx)
        span = tr.tool_call("market.news", {"ticker": ticker, "sector": sector, "limit": limit})
        ctx = dict(_ctx or {})
        tenant_id = ctx.get("tenant_id") or _DEFAULT_TENANT
        out = self._ibkr_live_news(
            ticker=(ticker or "").strip().upper() or None,
            sector=sector,
            limit=_i(limit, 50, 1, 50),
            tenant_id=tenant_id,
        )
        tr.tool_result("market.news", span, _provenance_summary(out))
        return out

    def broker_accounts(self, _ctx: dict | None = None) -> dict:
        return self._typed_error(
            "POLICY_DENIED",
            "broker account access is disabled",
            "Use market data and backtest skills only.",
        )

    def broker_positions(self, account: str | None = None, _ctx: dict | None = None) -> dict:
        return self._typed_error(
            "POLICY_DENIED",
            "broker position access is disabled",
            "Use market data and backtest skills only.",
        )

    def broker_orders(self, account: str | None = None, _ctx: dict | None = None) -> dict:
        return self._typed_error(
            "POLICY_DENIED",
            "broker order access is disabled",
            "Use market data and backtest skills only.",
        )

    def ops_provider_status(
        self,
        symbol: str = "AAPL",
        max_freshness_ms: int | None = None,
        _ctx: dict | None = None,
    ) -> dict:
        result = self.ibkr_smoke(symbol=symbol, max_freshness_ms=max_freshness_ms, _ctx=_ctx)
        return _ibkr_skill_envelope({"provider": PUBLIC_DATA_SOURCE, **result})

    def backtest_run(self, spec: dict, range: str = "1y", _ctx: dict | None = None) -> dict:
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        _ctx = self._with_active_session(_ctx)
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
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        _ctx = self._with_active_session(_ctx)
        tr = self._tracer(_ctx)
        validated = self.core.validate_spec(spec)  # raises on closed-schema violation
        strategy_id = "stg_" + uuid.uuid4().hex[:12]
        validated["id"] = strategy_id
        tr.event("strategy_proposed", {"strategy_id": strategy_id, "name": validated.get("name")})
        return {"strategy_id": strategy_id, "status": "draft", "spec": validated}

    def call_skill(self, tool: str, params: dict, _ctx: dict | None = None) -> dict:
        """Run a public Skill catalog tool, traced exactly like market_get_ohlcv.

        ``tool`` is the canonical SKILLS name (e.g. ``market.news``). Declarative args only — the
        skill never executes agent code. tool_call / tool_result events are emitted on the same
        gap-free, research-session-aware tracer the existing tools use.
        """
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        _ctx = self._with_active_session(_ctx)
        tool = self._canonical_skill_id(tool)
        if tool == "market.quote":
            return self.market_quote(
                params["symbol"],
                max_freshness_ms=params.get("max_freshness_ms"),
                _ctx=_ctx,
            )
        if tool == "broker.accounts":
            return self.broker_accounts(_ctx=_ctx)
        if tool == "broker.positions":
            return self.broker_positions(params.get("account"), _ctx=_ctx)
        if tool == "broker.orders":
            return self.broker_orders(params.get("account"), _ctx=_ctx)
        if tool == "ops.provider_status":
            return self.ops_provider_status(
                params.get("symbol", "AAPL"),
                max_freshness_ms=params.get("max_freshness_ms"),
                _ctx=_ctx,
            )
        method = SKILLS.get(tool)
        if method is None:
            raise ValueError(f"unknown skill: {tool!r} (have {sorted(SKILLS)})")
        if tool not in _PUBLIC_SKILL_IDS:
            return self._typed_error(
                "POLICY_DENIED",
                f"{tool} is not available in the live-data-only MCP",
                "Use Ithaca live-data market tools or pure computed tools.",
            )
        tr = self._tracer(_ctx)
        span = tr.tool_call(tool, params)
        ctx = dict(_ctx or {})
        tenant_id = ctx.get("tenant_id") or _DEFAULT_TENANT
        if tool == "market.news":
            out = self._ibkr_live_news(
                ticker=(params.get("ticker") or params.get("symbol") or "").strip().upper() or None,
                sector=params.get("sector"),
                limit=_i(params.get("limit"), 10, 1, 50),
                tenant_id=tenant_id,
            )
            tr.tool_result(tool, span, _provenance_summary(out))
            return out
        if tool in {"market.movers", "market.screener"}:
            try:
                out = self._ibkr_live_skill(tool, params, tenant_id=tenant_id)
                tr.tool_result(tool, span, _provenance_summary(out))
                return out
            except IbkrEngineError as exc:
                out = self._typed_error(
                    "PROVIDER_DEGRADED" if IbkrEngineClient().configured() else "BROKER_CONNECTION_REQUIRED",
                    f"live data unavailable: {exc}",
                    "Check the Ithaca live-data engine route and session entitlements.",
                )
                tr.tool_result(tool, span, {"source": PUBLIC_DATA_SOURCE, "ok": False,
                                            "code": out["error"]["code"]})
                return out
        out = getattr(self.skills, method)(params)
        tr.tool_result(tool, span, _provenance_summary(out))
        return out

    @staticmethod
    def _ibkr_history_window(range_value: str, interval: str) -> tuple[str, str]:
        interval_map = {
            "1m": "1min",
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "1h": "1h",
            "1d": "1d",
            "day": "1d",
            "daily": "1d",
        }
        return range_value or "1d", interval_map.get(str(interval or "").lower(), interval or "5min")

    def _ibkr_live_news(
        self,
        *,
        ticker: str | None,
        sector: str | None,
        limit: int,
        tenant_id: str,
        client: IbkrEngineClient | None = None,
    ) -> dict:
        client = client or IbkrEngineClient()
        scope = ticker or (sector or "").strip() or "Markets"
        if not client.configured():
            return _live_news_unavailable_envelope("live data engine is not configured", scope=scope)

        errors: list[str] = []
        attempts: list[str | None] = [ticker] if ticker else [None]
        if ticker:
            attempts.append(None)

        for news_ticker in attempts:
            try:
                raw = client.news(ticker=news_ticker, limit=limit, tenant_id=tenant_id)
            except IbkrEngineError as exc:
                errors.append(str(exc))
                continue
            items = raw.get("items") if isinstance(raw, dict) else []
            if not isinstance(items, list):
                items = []
            if not items:
                continue
            pos = sum(1 for item in items if isinstance(item, dict) and item.get("sentiment") == "positive")
            neg = sum(1 for item in items if isinstance(item, dict) and item.get("sentiment") == "negative")
            as_of = raw.get("asOf") or next(
                (item.get("publishedAt") for item in items if isinstance(item, dict) and item.get("publishedAt")),
                None,
            )
            data = {
                "scope": raw.get("scope") or news_ticker or scope,
                "items": items,
                "count": len(items),
                "sentimentMix": {"positive": pos, "negative": neg, "neutral": len(items) - pos - neg},
                "asOf": as_of,
                "provider": PUBLIC_DATA_SOURCE,
            }
            return _ibkr_skill_envelope(data, as_of=data.get("asOf"))

        try:
            raw_scan = client.scanner(scan_type="MOST_ACTIVE", limit=limit, tenant_id=tenant_id)
            rows = raw_scan.get("rows") if isinstance(raw_scan, dict) else []
            if not isinstance(rows, list):
                rows = []
            as_of = raw_scan.get("asOf") or datetime.now(timezone.utc).isoformat()
            items = _market_activity_news_items(rows, as_of=as_of, limit=limit)
            if items:
                data = {
                    "scope": scope,
                    "items": items,
                    "count": len(items),
                    "sentimentMix": {"positive": 0, "negative": 0, "neutral": len(items)},
                    "asOf": as_of,
                    "provider": PUBLIC_DATA_SOURCE,
                }
                return _ibkr_skill_envelope(data, as_of=as_of)
        except IbkrEngineError as exc:
            errors.append(str(exc))

        detail = "; ".join(errors) if errors else "live news returned no items"
        return _live_news_unavailable_envelope(detail, scope=scope)

    def _ibkr_live_skill(self, tool: str, params: dict, *, tenant_id: str) -> dict:
        client = IbkrEngineClient()
        if not client.configured():
            raise IbkrEngineError("live data engine is not configured")
        if tool == "market.news":
            ticker = (params.get("ticker") or params.get("symbol") or "").strip().upper() or None
            limit = _i(params.get("limit"), 10, 1, 50)
            return self._ibkr_live_news(
                ticker=ticker,
                sector=params.get("sector"),
                limit=limit,
                tenant_id=tenant_id,
                client=client,
            )
        if tool == "market.movers":
            limit = _i(params.get("limit"), 25, 1, 100)
            gainers = client.scanner(scan_type="TOP_PERC_GAIN", limit=max(5, limit), tenant_id=tenant_id).get("rows") or []
            losers = client.scanner(scan_type="TOP_PERC_LOSE", limit=max(5, limit), tenant_id=tenant_id).get("rows") or []
            active = client.scanner(scan_type="MOST_ACTIVE", limit=limit, tenant_id=tenant_id).get("rows") or []
            if not (gainers or losers or active):
                raise IbkrEngineError("live scanner returned no rows")
            cells = active or (gainers[: limit // 2] + losers[: limit // 2])
            data = {
                "title": "Live Market Movers",
                "cells": cells[:limit],
                "gainers": gainers[:5],
                "losers": losers[:5],
                "provider": PUBLIC_DATA_SOURCE,
            }
            return _ibkr_skill_envelope(data)
        if tool == "market.screener":
            limit = _i(params.get("limit"), 50, 1, 100)
            raw = client.scanner(scan_type="MOST_ACTIVE", limit=limit, tenant_id=tenant_id)
            rows = raw.get("rows") or []
            if not rows:
                raise IbkrEngineError("live scanner returned no rows")
            data = {
                "title": "Live Most Active Screener",
                "rows": rows,
                "count": len(rows),
                "provider": PUBLIC_DATA_SOURCE,
                "asOf": raw.get("asOf"),
            }
            return _ibkr_skill_envelope(data, as_of=data.get("asOf"))
        raise IbkrEngineError(f"live-data override is not available for {tool}")

    def search_skills(self, query: str = "", asset_class: str | None = None,
                      intent: str | None = None) -> dict:
        """Progressive skill discovery: small catalog entries, not all tools as context."""
        q = (query or "").strip().lower()
        entries = [
            self._manifest_entry(m)
            for skill_id, m in ALL_SKILL_MANIFESTS.items()
            if skill_id in _PUBLIC_SKILL_IDS
        ]
        if q:
            entries = [
                e for e in entries
                if q in e["skill_id"].lower()
                or q in e["name"].lower()
                or q in e["description"].lower()
            ]
        if asset_class:
            entries = [e for e in entries if e.get("asset_class") == asset_class]
        if intent:
            qi = intent.lower()
            entries = [
                e for e in entries
                if qi in e["skill_id"].lower() or qi in e["description"].lower()
            ]
        return {"skills": entries[:50], "count": len(entries), "truncated": len(entries) > 50}

    def list_toolkits(self, query: str = "") -> dict:
        """Task-oriented groups for agents that prefer direct tools over catalog search."""
        q = (query or "").strip().lower()
        entries = []
        for toolkit_id, toolkit in sorted(_TOOLKITS.items()):
            entry = {
                "toolkit_id": toolkit_id,
                "name": toolkit["name"],
                "description": toolkit["description"],
                "required_first_tool": toolkit["required_first_tool"],
                "direct_tools": list(toolkit["direct_tools"]),
                "direct_tool_count": len(toolkit["direct_tools"]),
                "skill_count": len(toolkit["skill_ids"]),
            }
            if q and not (
                q in toolkit_id.lower()
                or q in entry["name"].lower()
                or q in entry["description"].lower()
            ):
                continue
            entries.append(entry)
        return {"toolkits": entries, "count": len(entries)}

    def _direct_tool_catalog(self) -> list[dict]:
        seen: set[str] = set()
        tools: list[dict] = []
        for toolkit_id, toolkit in sorted(_TOOLKITS.items()):
            for name in toolkit["direct_tools"]:
                if name in seen:
                    continue
                seen.add(name)
                tools.append({
                    "name": name,
                    "toolkit_id": toolkit_id,
                    "required_first_tool": toolkit["required_first_tool"],
                })
        return tools

    def describe_toolkit(self, toolkit_id: str) -> dict:
        toolkit_id = str(toolkit_id or "").strip().lower()
        toolkit = _TOOLKITS.get(toolkit_id)
        if toolkit is None:
            return self._typed_error(
                "INVALID_SYMBOL",
                f"unknown toolkit: {toolkit_id}",
                "Call list_toolkits and use a returned toolkit_id.",
            )
        skills = [
            self._manifest_entry(manifest)
            for skill_id in toolkit["skill_ids"]
            if (manifest := ALL_SKILL_MANIFESTS.get(skill_id)) is not None
        ]
        return {
            "toolkit_id": toolkit_id,
            "name": toolkit["name"],
            "description": toolkit["description"],
            "required_first_tool": toolkit["required_first_tool"],
            "direct_tools": toolkit["direct_tools"],
            "skills": skills,
            "workflow": [
                f"Call {toolkit['required_first_tool']} with the user's prompt.",
                "Call direct tools from this toolkit as needed.",
                "Use get_run/subscribe_run for durable work and inspect the visible session trace.",
            ],
        }

    def describe_skill(self, skill_id: str, version: str | None = None) -> dict:
        """Return a compact manifest-like description for a skill."""
        skill_id = self._canonical_skill_id(skill_id)
        manifest = ALL_SKILL_MANIFESTS.get(skill_id)
        if manifest is None or skill_id not in _PUBLIC_SKILL_IDS:
            return self._typed_error("INVALID_SYMBOL", f"unknown skill: {skill_id}",
                                     "Call search_skills and use a returned skill_id.")
        out = dict(manifest)
        if version is not None and version != out["version"]:
            return self._typed_error("INVALID_SYMBOL", f"unknown skill version: {version}",
                                     "Call describe_skill without a version or use the advertised version.")
        return out

    def skills_catalog_resource(self) -> dict:
        """Read-only MCP resource for progressive skill discovery."""
        entries = sorted(
            (
                self._manifest_entry(m)
                for skill_id, m in ALL_SKILL_MANIFESTS.items()
                if skill_id in _PUBLIC_SKILL_IDS
            ),
            key=lambda entry: entry["skill_id"],
        )
        return {
            "kind": "skills.catalog",
            "count": len(entries),
            "truncated": False,
            "skills": entries,
        }

    def toolkits_catalog_resource(self) -> dict:
        return {"kind": "toolkits.catalog", **self.list_toolkits()}

    def toolkit_resource(self, toolkit_id: str) -> dict:
        return self.describe_toolkit(toolkit_id)

    def skill_resource(self, skill_id: str, version: str) -> dict:
        """Read-only MCP resource for one skill manifest version."""
        return self.describe_skill(skill_id, version=version)

    def run_resource(self, run_id: str, _ctx: dict | None = None) -> dict:
        """Read-only MCP resource for a durable run, including jobs, artifacts and events."""
        return self._get_run_unchecked(run_id, _ctx=_ctx)

    def policies_resource(self, _ctx: dict | None = None) -> dict:
        """Read-only MCP resource describing current deterministic platform policy."""
        policy = ExecutionPolicy.from_env()
        return {
            "kind": "policies.current",
            "tenant_id": (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT,
            "trading": {"enabled": False, "detail": "live trading is disabled; paper handoff is enabled"},
            "paper_trading_default": True,
            "live_execution": {
                "enabled": policy.live_enabled,
                "requires_connected_provider": policy.require_connected_provider_for_live,
            },
            "execution": {
                "max_notional_usd": policy.max_notional_usd,
                "max_quantity": policy.max_quantity,
                "max_freshness_ms": policy.max_freshness_ms,
            },
            "typed_errors": list(_TYPED_ERROR_CODES),
        }

    def accounts_resource(self, _ctx: dict | None = None) -> dict:
        """Read-only tenant-scoped account view with credential material redacted."""
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        if self.platform is None:
            connections: list[dict] = []
        else:
            connections = [
                _public_connection(c)
                for c in self.platform.providers.list_connections(tenant_id)
            ]
        return {
            "kind": "accounts",
            "tenant_id": tenant_id,
            "trading": {"enabled": False},
            "accounts": [],
            "provider_connections": connections,
        }

    def data_providers_resource(self, _ctx: dict | None = None) -> dict:
        """Read-only tenant-scoped data-provider and dataset snapshot view."""
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        if self.platform is None:
            connections: list[dict] = []
            snapshots: list[dict] = []
        else:
            connections = [
                _public_connection(c)
                for c in self.platform.providers.list_connections(tenant_id)
            ]
            snapshots = self.platform.providers.list_snapshots(tenant_id, limit=50)
        ibkr = IbkrEngineClient()
        return {
            "kind": "data.providers",
            "tenant_id": tenant_id,
            "connections": connections,
            "dataset_snapshots": snapshots,
            "live_data": {
                "configured": ibkr.configured(),
                "entitlement_class": PUBLIC_ENTITLEMENT_CLASS,
            },
            "supported_modes": [
                "community_public_delayed",
                PUBLIC_ENTITLEMENT_CLASS,
                "ithaca_licensed_placeholder",
            ],
        }

    def run_skill(self, skill_id: str, input: dict | None = None, mode: str = "auto",
                  idempotency_key: str | None = None, _ctx: dict | None = None) -> dict:
        """Create a durable Ithaca run for a skill.

        Long work (`backtest.run`) is queued and returns immediately. Interactive skills run
        to completion inside a short-lived run so the caller still receives a run_id, trace,
        result, and replayable audit row.
        """
        params = dict(input or {})
        skill_id = self._canonical_skill_id(skill_id)
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        _ctx = self._with_active_session(_ctx)
        ctx = dict(_ctx or {})
        tenant_id = ctx.get("tenant_id") or _DEFAULT_TENANT
        agent_id = ctx.get("agent_id")
        session_tr = self._tracer(_ctx) if self.runs is not None else None
        session_span = (
            session_tr.tool_call("run_skill", {"skill_id": skill_id, "mode": mode})
            if session_tr is not None
            else None
        )

        def traced(payload: dict) -> dict:
            if session_tr is not None and session_span is not None:
                summary = {
                    "skill_id": skill_id,
                    "status": payload.get("status"),
                    "run_id": payload.get("run_id"),
                    "job_id": payload.get("job_id"),
                }
                error = payload.get("error")
                if isinstance(error, dict):
                    summary["error"] = error.get("code")
                session_tr.tool_result("run_skill", session_span, summary)
            return payload

        if self.platform is None:
            if skill_id == "backtest.run":
                return traced(self.backtest_run(params.get("spec") or params, params.get("range", "1y"), _ctx=_ctx))
            if skill_id == "market.get_ohlcv":
                return traced(self.market_get_ohlcv(params["symbol"], params.get("range", "6mo"),
                                                    params.get("interval", "1d"), _ctx=_ctx))
            if skill_id == "market.quote":
                return traced(self.market_quote(
                    params["symbol"],
                    max_freshness_ms=params.get("max_freshness_ms"),
                    include_extended_hours=bool(params.get("include_extended_hours")),
                    _ctx=_ctx,
                ))
            if skill_id in {"broker.accounts", "broker.positions", "broker.orders", "ops.provider_status"}:
                return traced(self._typed_error(
                    "POLICY_DENIED",
                    "this skill is disabled",
                    "Use market.quote for live data and backtest.run for analysis.",
                ))
            return traced(self.call_skill(skill_id, params, _ctx=_ctx))

        jobs = getattr(self.platform, "jobs", None)
        if idempotency_key and jobs is not None:
            existing = jobs.get_by_idempotency(tenant_id, idempotency_key)
            if existing is not None:
                run = self.platform.runs.get(tenant_id, existing["run_id"])
                return traced({
                    "run_id": existing["run_id"],
                    "job_id": existing["job_id"],
                    "status": run.get("state") if run else existing["state"],
                    "status_url": f"/api/runs/{existing['run_id']}",
                    "estimated_profile": existing["profile"],
                    "idempotent": True,
                })

        if skill_id == "backtest.run":
            spec = params.get("spec")
            if not isinstance(spec, dict):
                return traced(self._typed_error("JOB_BUDGET_EXCEEDED", "backtest.run requires input.spec",
                                                "Pass a StrategySpec under input.spec."))
            range_ = params.get("range", "1y")
            run_spec = dict(spec)
            run_id = self.platform.runs.create(tenant_id, "backtest", None, run_spec)
            queued = self.platform.runs.transition(tenant_id, run_id, "queued", expect=0)
            job = jobs.create_for_run(
                tenant_id, run_id, kind="backtest", profile="backtest",
                payload={"skill_id": skill_id, "spec": run_spec, "range": range_},
                idempotency_key=idempotency_key,
            ) if jobs is not None else None
            Tracer(self.sink, run_id=run_id, tenant_id=tenant_id, session_id=run_id,
                   actor_id=agent_id).event(
                "run_transition",
                {"from": "draft", "to": "queued", "skill_id": skill_id,
                 "job_id": job.get("job_id") if job else None, "profile": "backtest"},
            )
            return traced({
                "run_id": run_id,
                "status": queued["state"],
                "status_url": f"/api/runs/{run_id}",
                "estimated_profile": "backtest",
                "job_id": job.get("job_id") if job else None,
                "approval_required": False,
            })

        run_id = self.platform.runs.create(tenant_id, "interactive", None,
                                           {"skill_id": skill_id, "input": params, "mode": mode})
        self.platform.runs.transition(tenant_id, run_id, "queued", expect=0)
        running = self.platform.runs.transition(tenant_id, run_id, "running", expect=1)
        run_ctx = {**ctx, "run_id": run_id, "session_id": run_id}
        tr = Tracer(self.sink, run_id=run_id, tenant_id=tenant_id, session_id=run_id,
                    actor_id=agent_id)
        tr.event("run_transition", {"from": "draft", "to": "running", "skill_id": skill_id})
        try:
            if skill_id == "market.get_ohlcv":
                out = self.market_get_ohlcv(params["symbol"], params.get("range", "6mo"),
                                            params.get("interval", "1d"), _ctx=run_ctx)
            elif skill_id == "market.quote":
                out = self.market_quote(
                    params["symbol"],
                    max_freshness_ms=params.get("max_freshness_ms"),
                    include_extended_hours=bool(params.get("include_extended_hours")),
                    _ctx=run_ctx,
                )
            elif skill_id in {"broker.accounts", "broker.positions", "broker.orders", "ops.provider_status"}:
                out = self._typed_error(
                    "POLICY_DENIED",
                    "this skill is disabled",
                    "Use market.quote for live data and backtest.run for analysis.",
                )
            else:
                out = self.call_skill(skill_id, params, _ctx=run_ctx)
            if isinstance(out, dict) and out.get("error", {}).get("code") == "POLICY_DENIED":
                self.platform.runs.set_result(tenant_id, run_id, out)
                self.platform.runs.transition(tenant_id, run_id, "failed", expect=running["version"])
                tr.event("error", {"stage": "run_skill", "error": "POLICY_DENIED"})
                return traced({
                    "run_id": run_id,
                    "status": "failed",
                    "error": out["error"],
                    "status_url": f"/api/runs/{run_id}",
                })
        except Exception as exc:  # noqa: BLE001 - return typed error in run result.
            err = self._typed_error("PROVIDER_DEGRADED", type(exc).__name__,
                                    "Inspect the run trace and retry when the provider recovers.",
                                    {"detail": str(exc)[:300]})
            self.platform.runs.set_result(tenant_id, run_id, err)
            self.platform.runs.transition(tenant_id, run_id, "failed", expect=running["version"])
            tr.event("error", {"stage": "run_skill", "error": type(exc).__name__,
                               "detail": str(exc)[:300]})
            return traced({"run_id": run_id, "status": "failed", "error": err,
                           "status_url": f"/api/runs/{run_id}"})
        self.platform.runs.set_result(tenant_id, run_id, out)
        self.platform.runs.transition(tenant_id, run_id, "succeeded", expect=running["version"])
        tr.event("run_transition", {"from": "running", "to": "succeeded", "skill_id": skill_id})
        return traced({
            "run_id": run_id,
            "status": "succeeded",
            "status_url": f"/api/runs/{run_id}",
            "estimated_profile": "interactive",
            "result": out,
            "approval_required": False,
        })

    def get_run(self, run_id: str, _ctx: dict | None = None) -> dict:
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        return self._trace_workflow_tool(
            "get_run",
            {"run_id": run_id},
            self._get_run_unchecked(run_id, _ctx=_ctx),
            _ctx,
        )

    def _get_run_unchecked(self, run_id: str, _ctx: dict | None = None) -> dict:
        if self.platform is None:
            return self._typed_error("JOB_QUEUED", "durable runs are unavailable in this toolset",
                                     "Use the hosted MCP endpoint or REST API.")
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        run = self.platform.runs.get(tenant_id, run_id)
        if run is None:
            return self._typed_error("INVALID_SYMBOL", "run not found",
                                     "Check the run_id and tenant credential.")
        return {
            "run": run,
            "jobs": self.platform.jobs.list_by_run(tenant_id, run_id),
            "artifacts": self.platform.artifacts.list_by_run(tenant_id, run_id),
            "events": self.platform.trace.events(tenant_id, run_id),
        }

    def subscribe_run(self, run_id: str, cursor: int = -1, _ctx: dict | None = None) -> dict:
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        if self.platform is None:
            return self._typed_error("JOB_QUEUED", "durable runs are unavailable in this toolset",
                                     "Use the hosted MCP endpoint or REST API.")
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        events = self.platform.trace.events(tenant_id, run_id, after_seq=int(cursor))
        next_cursor = events[-1]["seq"] if events else int(cursor)
        return self._trace_workflow_tool(
            "subscribe_run",
            {"run_id": run_id, "cursor": cursor},
            {"run_id": run_id, "cursor": next_cursor, "events": events},
            _ctx,
        )

    def cancel_run(self, run_id: str, reason: str | None = None, _ctx: dict | None = None) -> dict:
        if self.platform is None:
            return self._typed_error("JOB_QUEUED", "durable runs are unavailable in this toolset",
                                     "Use the hosted MCP endpoint or REST API.")
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        _ctx = self._with_active_session(_ctx)
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        run = self.platform.runs.get(tenant_id, run_id)
        if run is None:
            return self._typed_error("INVALID_SYMBOL", "run not found",
                                     "Check the run_id and tenant credential.")
        cancelled_jobs = self.platform.jobs.cancel_by_run(tenant_id, run_id, reason=reason)
        if run["state"] not in {"succeeded", "failed", "timeout", "cancelled", "promoted",
                                "live", "paused", "retired"}:
            try:
                self.platform.runs.cancel(tenant_id, run_id, expect=run["version"])
            except TransitionConflict:
                latest = self.platform.runs.get(tenant_id, run_id)
                if latest and latest["state"] not in {
                    "succeeded", "failed", "timeout", "cancelled", "promoted",
                    "live", "paused", "retired",
                }:
                    self.platform.runs.cancel(tenant_id, run_id, expect=latest["version"])
        Tracer(self.sink, run_id=run_id, tenant_id=tenant_id, session_id=run_id,
               actor_id=(_ctx or {}).get("agent_id")).event(
            "run_transition",
            {"from": run["state"], "to": "cancelled", "reason": reason,
             "cancelled_jobs": [j["job_id"] for j in cancelled_jobs]},
        )
        return {"run_id": run_id, "status": "cancelled",
                "cancelled_jobs": [j["job_id"] for j in cancelled_jobs]}

    def list_approvals(self, _ctx: dict | None = None) -> dict:
        if self.platform is None:
            return {"approvals": []}
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        return {"approvals": self.platform.approvals.list_pending(tenant_id)}

    def decide_approval(self, approval_id: str, decision: str, reason: str | None = None,
                        _ctx: dict | None = None) -> dict:
        if self.platform is None:
            return self._typed_error("APPROVAL_REQUIRED", "approvals are unavailable",
                                     "Use the hosted MCP endpoint or REST API.")
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        _ctx = self._with_active_session(_ctx)
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        agent_id = (_ctx or {}).get("agent_id")
        if (_ctx or {}).get("actor_kind") not in {"human", "user"}:
            return self._typed_error(
                "APPROVAL_REQUIRED",
                "approval decisions require a human actor",
                "Open the Ithaca dashboard and approve or deny the request there.",
            )
        try:
            return self.platform.approvals.decide(
                tenant_id, approval_id, decision=decision, decided_by=agent_id, reason=reason
            )
        except Exception as exc:
            return self._typed_error("ORDER_STATE_CONFLICT", "approval cannot be decided",
                                     "Refresh approvals and retry a pending approval id.",
                                     {"detail": str(exc)[:200]})

    def get_artifact(self, artifact_id: str, _ctx: dict | None = None) -> dict:
        if self.platform is None:
            return self._typed_error("JOB_QUEUED", "artifacts are unavailable",
                                     "Use the hosted MCP endpoint or REST API.")
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        artifact = self.platform.artifacts.get(tenant_id, artifact_id)
        if artifact is None:
            return self._typed_error("INVALID_SYMBOL", "artifact not found",
                                     "Check the artifact_id and tenant credential.")
        return artifact

    def create_order_intent(
        self,
        run_id: str,
        payload: dict,
        strategy_id: str | None = None,
        account_ref: str | None = None,
        idempotency_key: str | None = None,
        _ctx: dict | None = None,
    ) -> dict:
        return self._typed_error(
            "POLICY_DENIED",
            "order intents are disabled",
            "This deployment is data and backtest only.",
        )

    def preview_order_intent(self, intent_id: str, _ctx: dict | None = None) -> dict:
        return self._typed_error(
            "POLICY_DENIED",
            "order intents are disabled",
            "This deployment is data and backtest only.",
        )

    def get_order_intent(self, intent_id: str, _ctx: dict | None = None) -> dict:
        return self._typed_error(
            "POLICY_DENIED",
            "order intents are disabled",
            "This deployment is data and backtest only.",
        )

    def submit_order_intent(self, intent_id: str, _ctx: dict | None = None) -> dict:
        return self._typed_error(
            "POLICY_DENIED",
            "order intents are disabled",
            "This deployment is data and backtest only.",
        )

    def _require_platform(self) -> dict | None:
        if self.platform is None:
            return self._typed_error(
                "JOB_QUEUED",
                "durable platform stores are unavailable in this toolset",
                "Use the hosted MCP endpoint or REST API.",
            )
        return None

    def _validate_trigger_policy(self, policy: dict) -> None:
        if not isinstance(policy, dict):
            raise ValueError("policy must be an object")
        when = policy.get("when")
        if not isinstance(when, dict):
            raise ValueError("policy.when must be an object")
        event = when.get("event") or "price.threshold"
        if event not in {"price.threshold", "market.price", "market.quote"}:
            raise ValueError(f"unsupported trigger event: {event}")
        universe = when.get("universe")
        if not ((isinstance(universe, list) and universe) or isinstance(when.get("symbol"), str)):
            raise ValueError("policy.when must include universe or symbol")
        baseline = when.get("baseline")
        if baseline is not None:
            if not isinstance(baseline, dict):
                raise ValueError("policy.when.baseline must be an object")
            if baseline.get("type") not in {
                "previous_close",
                "session_open",
                "fixed_price",
                "last_firing",
                "snapshot",
                "snapshot_on_activation",
            }:
                raise ValueError(f"unsupported baseline type: {baseline.get('type')}")
        action = policy.get("action") or {}
        mode = action.get("mode") or "analyze"
        if mode not in {"notify", "observe", "analyze", "propose", "execute"}:
            raise ValueError(f"unsupported action mode: {mode}")
        if mode == "execute":
            raise ValueError("execute mode is disabled in v1")

    def triggers_create(
        self,
        name: str,
        policy: dict,
        state: str = "draft",
        _ctx: dict | None = None,
    ) -> dict:
        err = self._require_platform()
        if err:
            return err
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        try:
            self._validate_trigger_policy(policy)
            return self._trace_workflow_tool(
                "triggers_create",
                {"name": name, "state": state},
                self.platform.triggers.create(tenant_id, name=name, policy=policy, state=state),
                _ctx,
            )
        except Exception as exc:
            return self._typed_error(
                "POLICY_DENIED",
                "trigger policy could not be created",
                "Validate the TriggerPolicy and retry as draft or active.",
                {"detail": str(exc)[:300]},
            )

    def triggers_dry_run(
        self,
        name: str,
        policy: dict,
        quote: dict | None = None,
        _ctx: dict | None = None,
    ) -> dict:
        err = self._require_platform()
        if err:
            return err
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        from ithaca_runtime import TriggerEngine, TriggerEvaluationError

        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        try:
            self._validate_trigger_policy(policy)
            return self._trace_workflow_tool(
                "triggers_dry_run",
                {"name": name},
                TriggerEngine(self.platform, worker_id="mcp-trigger-dry-run").dry_run(
                    {
                        "tenant_id": tenant_id,
                        "trigger_id": "dry-run-" + uuid.uuid4().hex,
                        "name": name,
                        "state": "draft",
                        "policy": policy,
                    },
                    quote=quote,
                ),
                _ctx,
            )
        except (ValueError, TriggerEvaluationError) as exc:
            return self._typed_error(
                "POLICY_DENIED",
                "trigger policy dry-run failed",
                "Fix the policy, baseline, or quote and retry.",
                {"detail": str(exc)[:300]},
            )

    def triggers_list(self, state: str | None = None, limit: int = 100,
                      _ctx: dict | None = None) -> dict:
        err = self._require_platform()
        if err:
            return err
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        return self._trace_workflow_tool(
            "triggers_list",
            {"state": state, "limit": limit},
            self._triggers_list_unchecked(state=state, limit=limit, _ctx=_ctx),
            _ctx,
        )

    def _triggers_list_unchecked(self, state: str | None = None, limit: int = 100,
                                 _ctx: dict | None = None) -> dict:
        err = self._require_platform()
        if err:
            return err
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        return {"triggers": self.platform.triggers.list(tenant_id, state=state, limit=limit)}

    def triggers_set_state(self, trigger_id: str, state: str, _ctx: dict | None = None) -> dict:
        err = self._require_platform()
        if err:
            return err
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        try:
            return self._trace_workflow_tool(
                "triggers_set_state",
                {"trigger_id": trigger_id, "state": state},
                self.platform.triggers.set_state(tenant_id, trigger_id, state),
                _ctx,
            )
        except Exception as exc:
            return self._typed_error(
                "ORDER_STATE_CONFLICT",
                "trigger state could not be changed",
                "Check the trigger_id and requested state.",
                {"detail": str(exc)[:200]},
            )

    def trigger_firings_list(
        self,
        trigger_id: str | None = None,
        limit: int = 100,
        _ctx: dict | None = None,
    ) -> dict:
        err = self._require_platform()
        if err:
            return err
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        return self._trace_workflow_tool(
            "trigger_firings_list",
            {"trigger_id": trigger_id, "limit": limit},
            self._trigger_firings_list_unchecked(trigger_id=trigger_id, limit=limit, _ctx=_ctx),
            _ctx,
        )

    def _trigger_firings_list_unchecked(
        self,
        trigger_id: str | None = None,
        limit: int = 100,
        _ctx: dict | None = None,
    ) -> dict:
        err = self._require_platform()
        if err:
            return err
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        return {
            "firings": self.platform.triggers.list_firings(
                tenant_id,
                trigger_id=trigger_id,
                limit=limit,
            )
        }

    def alerts_list(self, state: str | None = "open", limit: int = 100,
                    _ctx: dict | None = None) -> dict:
        err = self._require_platform()
        if err:
            return err
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        return self._trace_workflow_tool(
            "alerts_list",
            {"state": state, "limit": limit},
            self._alerts_list_unchecked(state=state, limit=limit, _ctx=_ctx),
            _ctx,
        )

    def _alerts_list_unchecked(self, state: str | None = "open", limit: int = 100,
                               _ctx: dict | None = None) -> dict:
        err = self._require_platform()
        if err:
            return err
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        return {"alerts": self.platform.notifications.list(tenant_id, state=state, limit=limit)}

    def alerts_subscribe(self, cursor: str = "-1", limit: int = 50,
                         _ctx: dict | None = None) -> dict:
        err = self._require_platform()
        if err:
            return err
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        alerts = list(reversed(self.platform.notifications.list(tenant_id, state="open", limit=limit)))
        if cursor and cursor != "-1":
            passed = False
            filtered = []
            for alert in alerts:
                if passed:
                    filtered.append(alert)
                elif alert["notification_id"] == cursor:
                    passed = True
            alerts = filtered
        next_cursor = alerts[-1]["notification_id"] if alerts else cursor
        return self._trace_workflow_tool(
            "alerts_subscribe",
            {"cursor": cursor, "limit": limit},
            {"cursor": next_cursor, "alerts": alerts},
            _ctx,
        )

    def alerts_ack(self, notification_id: str, _ctx: dict | None = None) -> dict:
        err = self._require_platform()
        if err:
            return err
        required = self._require_research_session(_ctx)
        if required is not None:
            return required
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        try:
            return self._trace_workflow_tool(
                "alerts_ack",
                {"notification_id": notification_id},
                self.platform.notifications.ack(tenant_id, notification_id),
                _ctx,
            )
        except KeyError:
            return self._typed_error(
                "INVALID_SYMBOL",
                "alert not found",
                "Check the notification_id and tenant credential.",
            )

    def triggers_resource(self, _ctx: dict | None = None) -> dict:
        return self._triggers_list_unchecked(limit=100, _ctx=_ctx)

    def trigger_resource(self, trigger_id: str, _ctx: dict | None = None) -> dict:
        err = self._require_platform()
        if err:
            return err
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        trigger = self.platform.triggers.get(tenant_id, trigger_id)
        if trigger is None:
            return self._typed_error("INVALID_SYMBOL", "trigger not found", "Check the trigger_id.")
        return {"trigger": trigger}

    def alerts_resource(self, _ctx: dict | None = None) -> dict:
        return self._alerts_list_unchecked(state="open", limit=100, _ctx=_ctx)

    def alert_resource(self, notification_id: str, _ctx: dict | None = None) -> dict:
        err = self._require_platform()
        if err:
            return err
        tenant_id = (_ctx or {}).get("tenant_id") or _DEFAULT_TENANT
        alert = self.platform.notifications.get(tenant_id, notification_id)
        if alert is None:
            return self._typed_error("INVALID_SYMBOL", "alert not found", "Check the notification_id.")
        return {
            "alert": alert,
            "attempts": self.platform.notifications.list_attempts(tenant_id, notification_id),
        }

    def trigger_firings_resource(self, _ctx: dict | None = None) -> dict:
        return self._trigger_firings_list_unchecked(limit=100, _ctx=_ctx)

    def ibkr_smoke(
        self,
        symbol: str = "AAPL",
        max_freshness_ms: int | None = None,
        _ctx: dict | None = None,
    ) -> dict:
        """Read-only smoke for the connected-account IBKR engine quote route."""

        ctx = dict(_ctx or {})
        tenant_id = ctx.get("tenant_id") or _DEFAULT_TENANT
        result = IbkrEngineClient().diagnose_quote(
            symbol=symbol,
            tenant_id=tenant_id,
            max_freshness_ms=max_freshness_ms,
        )
        tr = self._tracer(_ctx)
        tr.event(
            "provider_status",
            {
                "provider": PUBLIC_DATA_SOURCE,
                "symbol": result.get("symbol"),
                "ok": result.get("ok"),
                "status": result.get("status"),
                "code": result.get("code"),
                "host": result.get("host"),
                "latency_ms": result.get("latency_ms"),
            },
        )
        return result

    @staticmethod
    def _canonical_skill_id(skill_id: str) -> str:
        if skill_id == "market_get_ohlcv":
            return "market.get_ohlcv"
        if skill_id == "backtest_run":
            return "backtest.run"
        dotted = str(skill_id).replace("_", ".")
        return dotted if dotted in ALL_SKILL_MANIFESTS else str(skill_id)

    @staticmethod
    def _manifest_entry(manifest: dict) -> dict:
        skill_id = str(manifest["skill_id"])
        runtime = manifest.get("runtime") or {}
        return {
            "skill_id": skill_id,
            "name": manifest["name"],
            "description": manifest["description"],
            "runtime_profile": runtime.get("profile"),
            "asset_class": skill_id.split(".", 1)[0],
            "source_classes": manifest.get("source_classes") or [],
            "trigger_compatible": manifest.get("trigger_compatible", False),
        }

    @staticmethod
    def _typed_error(code: str, message: str, recovery_action: str,
                     details: dict | None = None) -> dict:
        return {
            "error": {
                "code": code,
                "message": message,
                "recovery_action": recovery_action,
                "details": details or {},
            }
        }

    def _ctx_to_control_ctx(self, ctx: dict | None) -> Ctx:
        ctx = ctx or {}
        scopes = ctx.get("scopes")
        if scopes is None:
            scopes = {
                "data:read",
                "strategy:author",
                "runs:write",
                "runs:cancel",
                "approvals:read",
                "approvals:decide",
                "providers:write",
                "triggers:read",
                "triggers:write",
                "alerts:read",
                "alerts:ack",
                "artifacts:read",
                "deploy:backtest",
            }
        return Ctx(
            tenant_id=ctx.get("tenant_id") or _DEFAULT_TENANT,
            actor_kind=(ctx.get("actor_kind") or "agent").strip().lower(),
            actor_id=ctx.get("agent_id") or ctx.get("actor_id") or self._proc_session,
            scopes=frozenset(scopes),
        )

    def _action_error(self, exc: ActionError) -> dict:
        code = "POLICY_DENIED" if exc.status == 409 else "APPROVAL_REQUIRED"
        if exc.status == 404:
            code = "ORDER_STATE_CONFLICT"
        elif exc.status == 403:
            code = "APPROVAL_REQUIRED"
        elif exc.status == 503:
            code = "BROKER_CONNECTION_REQUIRED"
        return self._typed_error(
            code,
            str(exc.detail),
            "Inspect the order intent, risk decision, approvals, and connected broker state.",
            {"status": exc.status, "detail": exc.detail},
        )


def _platform_backed_toolset() -> Toolset:
    """A Toolset whose trace persists to the shared platform store (``ITHACA_DB``).

    Imported lazily so unit tests (which always pass their own Toolset) never need the
    platform package, and a missing/unset DB falls back to ``:memory:``.
    """
    import os

    from ithaca_platform import Platform

    platform = Platform(os.environ.get("ITHACA_DB", ":memory:"))
    return Toolset(
        core=Core(),
        sink=PlatformTraceSink(platform.trace),
        runs=platform.runs,
        platform=platform,
    )


def _transport_security():
    """DNS-rebinding host policy for the hosted HTTP app.

    The SDK defaults to protection ON with a localhost-only allowlist, which 421s every
    request whose ``Host`` is the public hostname — i.e. anything behind a load balancer. In
    the hosted topology the real network boundary is the auth middleware + the k8s
    Service/NetworkPolicy the lead adds, and the Host arriving at the pod is the LB's choosing,
    so we make the allowlist explicit:

    * ``ITHACA_MCP_ALLOWED_HOSTS`` unset → protection OFF (trust the proxy + bearer auth).
    * set (comma-separated, e.g. ``mcp.ithaca.ai,mcp.ithaca.ai:443``) → protection ON,
      restricted to exactly those hosts (``host:*`` wildcard-port patterns supported by the SDK).

    Falls back to ``None`` when the SDK version does not expose
    ``mcp.server.transport_security`` (mcp < 1.10).
    """
    import os

    try:
        from mcp.server.transport_security import TransportSecuritySettings
    except ImportError:
        # mcp < 1.10 — transport_security module not available; pass None (SDK default).
        return None

    raw = (os.environ.get("ITHACA_MCP_ALLOWED_HOSTS") or "").strip()
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
    mcp = FastMCP("ithaca", transport_security=_transport_security() if http else None)

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

    @mcp.resource(
        "ithaca://skills/catalog",
        name="skills_catalog",
        description="Compact Ithaca skill catalog for progressive discovery.",
        mime_type="application/json",
    )
    def skills_catalog_resource() -> str:
        return _json_resource(ts.skills_catalog_resource())

    @mcp.resource(
        "ithaca://toolkits/catalog",
        name="toolkits_catalog",
        description="Task-oriented Ithaca toolkits for direct MCP tool calls.",
        mime_type="application/json",
    )
    def toolkits_catalog_resource() -> str:
        return _json_resource(ts.toolkits_catalog_resource())

    @mcp.resource(
        "ithaca://toolkits/{toolkit_id}",
        name="toolkit_manifest",
        description="One task-oriented Ithaca toolkit with direct tools and related skills.",
        mime_type="application/json",
    )
    def toolkit_resource(toolkit_id: str) -> str:
        return _json_resource(ts.toolkit_resource(toolkit_id))

    @mcp.resource(
        "ithaca://skills/{skill_id}/{version}",
        name="skill_manifest",
        description="One versioned Ithaca skill manifest.",
        mime_type="application/json",
    )
    def skill_manifest_resource(skill_id: str, version: str) -> str:
        return _json_resource(ts.skill_resource(skill_id, version))

    @mcp.resource(
        "ithaca://runs/{run_id}",
        name="run",
        description="Durable run with jobs, artifacts and replayable trace events.",
        mime_type="application/json",
    )
    def run_resource(run_id: str) -> str:
        return _json_resource(ts.run_resource(run_id, _ctx=_ctx()))

    @mcp.resource(
        "ithaca://policies/current",
        name="policies_current",
        description="Current deterministic Ithaca control-plane policies.",
        mime_type="application/json",
    )
    def policies_current_resource() -> str:
        return _json_resource(ts.policies_resource(_ctx=_ctx()))

    @mcp.resource(
        "ithaca://accounts",
        name="accounts",
        description="Tenant-scoped account and provider connection summary with credentials redacted.",
        mime_type="application/json",
    )
    def accounts_resource() -> str:
        return _json_resource(ts.accounts_resource(_ctx=_ctx()))

    @mcp.resource(
        "ithaca://data/providers",
        name="data_providers",
        description="Tenant-scoped data provider and dataset snapshot summary.",
        mime_type="application/json",
    )
    def data_providers_resource() -> str:
        return _json_resource(ts.data_providers_resource(_ctx=_ctx()))

    @mcp.resource(
        "ithaca://triggers",
        name="triggers",
        description="Tenant-scoped trigger policies.",
        mime_type="application/json",
    )
    def triggers_resource() -> str:
        return _json_resource(ts.triggers_resource(_ctx=_ctx()))

    @mcp.resource(
        "ithaca://triggers/{trigger_id}",
        name="trigger",
        description="One tenant-scoped trigger policy.",
        mime_type="application/json",
    )
    def trigger_resource(trigger_id: str) -> str:
        return _json_resource(ts.trigger_resource(trigger_id, _ctx=_ctx()))

    @mcp.resource(
        "ithaca://alerts/open",
        name="alerts_open",
        description="Open durable Ithaca alerts.",
        mime_type="application/json",
    )
    def alerts_open_resource() -> str:
        return _json_resource(ts.alerts_resource(_ctx=_ctx()))

    @mcp.resource(
        "ithaca://alerts/{notification_id}",
        name="alert",
        description="One durable Ithaca alert and delivery attempts.",
        mime_type="application/json",
    )
    def alert_resource(notification_id: str) -> str:
        return _json_resource(ts.alert_resource(notification_id, _ctx=_ctx()))

    @mcp.resource(
        "ithaca://trigger-firings/recent",
        name="trigger_firings_recent",
        description="Recent tenant-scoped trigger firings.",
        mime_type="application/json",
    )
    def trigger_firings_recent_resource() -> str:
        return _json_resource(ts.trigger_firings_resource(_ctx=_ctx()))

    @mcp.tool(description="Optional helper only: search Ithaca skills when no direct named tool fits.")
    def search_skills(query: str = "", asset_class: str | None = None,
                      intent: str | None = None) -> dict:
        return ts.search_skills(query=query, asset_class=asset_class, intent=intent)

    @mcp.tool(description="List task-oriented Ithaca toolkits for direct calls after start_research_session.")
    def list_toolkits(query: str = "") -> dict:
        return ts.list_toolkits(query=query)

    @mcp.tool(description="Describe one Ithaca toolkit: direct tools, related skills, and required workflow.")
    def describe_toolkit(toolkit_id: str) -> dict:
        return ts.describe_toolkit(toolkit_id=toolkit_id)

    @mcp.tool(description="Optional helper only: inspect one skill schema when a direct tool's inputs are unclear.")
    def describe_skill(skill_id: str, version: str | None = None) -> dict:
        return ts.describe_skill(skill_id, version=version)

    @mcp.tool(description="Create a durable Ithaca run for a skill after start_research_session. Backtests are queued and return a run id.")
    def run_skill(skill_id: str, input: dict | None = None, mode: str = "auto",
                  idempotency_key: str | None = None) -> dict:
        return ts.run_skill(skill_id, input=input, mode=mode,
                            idempotency_key=idempotency_key, _ctx=_ctx())

    @mcp.tool(description="Get a durable run with jobs, artifacts and replayable trace events.")
    def get_run(run_id: str) -> dict:
        return ts.get_run(run_id, _ctx=_ctx())

    @mcp.tool(description="Poll run events after a sequence cursor. Use repeatedly to follow progress.")
    def subscribe_run(run_id: str, cursor: int = -1) -> dict:
        return ts.subscribe_run(run_id, cursor=cursor, _ctx=_ctx())

    @mcp.tool(description="Cancel a queued or running durable run and its outstanding worker jobs.")
    def cancel_run(run_id: str, reason: str | None = None) -> dict:
        return ts.cancel_run(run_id, reason=reason, _ctx=_ctx())

    @mcp.tool(description="List pending Ithaca approvals for this tenant.")
    def list_approvals() -> dict:
        return ts.list_approvals(_ctx=_ctx())

    @mcp.tool(description="Approve or deny a pending approval request.")
    def decide_approval(approval_id: str, decision: str, reason: str | None = None) -> dict:
        return ts.decide_approval(approval_id, decision, reason=reason, _ctx=_ctx())

    @mcp.tool(description="Create a durable trigger policy as draft or active.")
    def triggers_create(name: str, policy: dict, state: str = "draft") -> dict:
        return ts.triggers_create(name, policy, state=state, _ctx=_ctx())

    @mcp.tool(description="Evaluate a trigger policy without creating runs, firings, jobs, approvals, or alerts.")
    def triggers_dry_run(name: str, policy: dict, quote: dict | None = None) -> dict:
        return ts.triggers_dry_run(name, policy, quote=quote, _ctx=_ctx())

    @mcp.tool(description="List tenant trigger policies.")
    def triggers_list(state: str | None = None, limit: int = 100) -> dict:
        return ts.triggers_list(state=state, limit=limit, _ctx=_ctx())

    @mcp.tool(description="Set a trigger state to draft, active, paused, or retired.")
    def triggers_set_state(trigger_id: str, state: str) -> dict:
        return ts.triggers_set_state(trigger_id, state, _ctx=_ctx())

    @mcp.tool(description="List recent trigger firings.")
    def trigger_firings_list(trigger_id: str | None = None, limit: int = 100) -> dict:
        return ts.trigger_firings_list(trigger_id=trigger_id, limit=limit, _ctx=_ctx())

    @mcp.tool(description="List durable Ithaca alerts for this tenant.")
    def alerts_list(state: str | None = "open", limit: int = 100) -> dict:
        return ts.alerts_list(state=state, limit=limit, _ctx=_ctx())

    @mcp.tool(description="Poll tenant alerts after a cursor. Use repeatedly to catch trigger alerts.")
    def alerts_subscribe(cursor: str = "-1", limit: int = 50) -> dict:
        return ts.alerts_subscribe(cursor=cursor, limit=limit, _ctx=_ctx())

    @mcp.tool(description="Acknowledge one durable Ithaca alert.")
    def alerts_ack(notification_id: str) -> dict:
        return ts.alerts_ack(notification_id, _ctx=_ctx())

    @mcp.tool(description="Fetch artifact metadata by id. Artifact content is addressed by returned URI.")
    def get_artifact(artifact_id: str) -> dict:
        return ts.get_artifact(artifact_id, _ctx=_ctx())

    @mcp.tool(description="Required first step: start a visible Ithaca research session with the user's prompt before direct tool calls.")
    def start_research_session(prompt: str, title: str | None = None,
                               session_id: str | None = None) -> dict:
        return ts.start_research_session(prompt=prompt, title=title, session_id=session_id, _ctx=_ctx())

    @mcp.tool(description="Compatibility alias for start_research_session. Prefer start_research_session.")
    def session_context(prompt: str | None = None, title: str | None = None,
                        session_id: str | None = None) -> dict:
        return ts.session_context(prompt=prompt, title=title, session_id=session_id, _ctx=_ctx())

    @mcp.tool(description="Initialize Ithaca for this agent session and return the first-call workflow.")
    def ithaca_init(goal: str | None = None) -> dict:
        return ts.ithaca_init(goal=goal, _ctx=_ctx())

    @mcp.tool(description="Direct tool after start_research_session: fetch OHLCV price history for one symbol, with provenance.")
    def market_get_ohlcv(symbol: str, range: str = "6mo", interval: str = "1d") -> dict:
        return ts.market_get_ohlcv(symbol, range, interval, _ctx=_ctx())

    @mcp.tool(description="Direct tool after start_research_session: fetch the current live quote for one symbol. Set include_extended_hours=true for pre/post-market capable routes.")
    def market_quote(symbol: str, max_freshness_ms: int | None = None,
                     include_extended_hours: bool = False) -> dict:
        return ts.market_quote(
            symbol,
            max_freshness_ms=max_freshness_ms,
            include_extended_hours=include_extended_hours,
            _ctx=_ctx(),
        )

    @mcp.tool(description="Direct tool after start_research_session: run a price/technical backtest from a declarative StrategySpec.")
    def backtest_run(spec: dict, range: str = "1y") -> dict:
        return ts.backtest_run(spec, range, _ctx=_ctx())

    @mcp.tool(description="Direct tool after start_research_session: validate and register a StrategySpec draft. No deploy, no money.")
    def propose_strategy(spec: dict) -> dict:
        return ts.propose_strategy(spec, _ctx=_ctx())

    # ---- direct live-data and Skill catalog (declarative args only) ----
    @mcp.tool(name="market_news",
              description="Direct tool after start_research_session: live market news from the Ithaca live-data engine. Never falls back to archive news.")
    def market_news(ticker: str | None = None, sector: str | None = None, limit: int = 50) -> dict:
        return ts.market_news(ticker=ticker, sector=sector, limit=limit, _ctx=_ctx())

    @mcp.tool(name="market_screener",
              description="Direct tool after start_research_session: live most-active screener from the Ithaca live-data engine.")
    def market_screener(sector: str | None = None, limit: int = 100) -> dict:
        return call_skill("market.screener", {"sector": sector, "limit": limit})

    @mcp.tool(name="market_movers",
              description="Direct tool after start_research_session: live gainers, losers, and active movers from the Ithaca live-data engine.")
    def market_movers(sector: str | None = None, limit: int = 100) -> dict:
        return call_skill("market.movers", {"sector": sector, "limit": limit})

    # ---- COMPUTED skills (source="computed"): pure math on agent inputs ----
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

    @mcp.tool(name="risk_stress",
              description="Estimate book P&L under agent-supplied shocks: factor shocks "
                          "(exposures x shocks) or asset shocks (weights x shocks). Computed.")
    def risk_stress(shocks: dict, exposures: dict | None = None,
                   weights: dict | None = None) -> dict:
        return call_skill("risk.stress",
                             {"shocks": shocks, "exposures": exposures, "weights": weights})

    @mcp.tool(name="vix_term_structure", description="VIX spot and futures term structure — contango/backwardation signals market fear regime.")
    def vix_term_structure() -> dict:
        return call_skill("vix.term_structure", {})

    return mcp, ts


def main() -> None:
    """Entry point for ``python -m ithaca_mcp``.

    Transport is selected by env (so the same image serves both modes):

    * ``ITHACA_MCP_TRANSPORT=stdio`` (default) — a locally-launched, locally-trusted agent;
      no auth, the existing dev behavior.
    * ``ITHACA_MCP_TRANSPORT=http`` — hosted streamable-HTTP for REMOTE BYO agents, served
      by uvicorn on ``ITHACA_MCP_PORT`` (default 8080, bind 0.0.0.0), with per-tenant bearer
      auth + scope enforcement (see :mod:`ithaca_mcp.http`).
    """
    import os

    transport = (os.environ.get("ITHACA_MCP_TRANSPORT") or "stdio").strip().lower()
    if transport == "http":
        from .http import serve_http

        port = int(os.environ.get("ITHACA_MCP_PORT", "8080"))
        serve_http(host="0.0.0.0", port=port)
        return
    mcp, _ = create_server()
    mcp.run()  # stdio transport (default; local trust, no auth)


if __name__ == "__main__":
    main()
