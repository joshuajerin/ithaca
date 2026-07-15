"""Explicit authorization policy for every hosted Ithaca MCP surface."""
from __future__ import annotations

from dataclasses import dataclass


class InsufficientScopeError(RuntimeError):
    """Stable, non-enumerating denial returned by an MCP tool/resource."""

    code = "INSUFFICIENT_SCOPE"
    message = "This credential cannot access this Ithaca capability."

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    credential_kind: str
    scopes: frozenset[str]
    subject: str | None


def require_scope(principal: Principal, scope: str) -> None:
    if scope not in principal.scopes:
        raise InsufficientScopeError()


# Policy is deliberately exhaustive rather than relying on a permissive default.  OAuth
# principals get a server-defined subset; API keys keep exactly the capabilities assigned at
# creation time.
TOOL_SCOPES: dict[str, str] = {
    "search_skills": "agent:read", "list_toolkits": "agent:read",
    "describe_toolkit": "agent:read", "describe_skill": "agent:read",
    "run_skill": "runs:write", "get_run": "data:read", "subscribe_run": "data:read",
    "cancel_run": "runs:cancel", "list_approvals": "approvals:read",
    "decide_approval": "approvals:decide", "triggers_create": "triggers:write",
    "triggers_dry_run": "triggers:write", "triggers_list": "triggers:read",
    "triggers_set_state": "triggers:write", "trigger_firings_list": "triggers:read",
    "alerts_list": "alerts:read", "alerts_subscribe": "alerts:read",
    "alerts_ack": "alerts:ack", "get_artifact": "artifacts:read",
    "start_research_session": "agent:read", "session_context": "agent:read",
    "ithaca_init": "agent:read", "market_get_ohlcv": "data:read",
    "market_quote": "data:read", "backtest_run": "runs:write",
    "propose_strategy": "strategy:author", "market_news": "data:read",
    "market_screener": "data:read", "market_movers": "data:read",
    "options_greeks": "data:read", "options_implied_vol": "data:read",
    "risk_stress": "data:read", "vix_term_structure": "data:read",
}

RESOURCE_SCOPES: dict[str, str] = {
    "ithaca://skills/catalog": "agent:read",
    "ithaca://toolkits/catalog": "agent:read",
    "ithaca://toolkits/{toolkit_id}": "agent:read",
    "ithaca://skills/{skill_id}/{version}": "agent:read",
    "ithaca://runs/{run_id}": "data:read",
    "ithaca://policies/current": "agent:read",
    "ithaca://accounts": "data:read",
    "ithaca://data/providers": "data:read",
    "ithaca://triggers": "triggers:read",
    "ithaca://triggers/{trigger_id}": "triggers:read",
    "ithaca://alerts/open": "alerts:read",
    "ithaca://alerts/{notification_id}": "alerts:read",
    "ithaca://trigger-firings/recent": "triggers:read",
}
