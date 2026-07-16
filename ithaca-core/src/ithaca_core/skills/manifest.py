"""Contract-shaped manifests for runnable Ithaca skills.

This catalog is intentionally generated from the implemented tool registry. It gives MCP,
REST, and docs a stable skill contract without advertising target skills that are not
runnable yet.
"""

from __future__ import annotations

from typing import Any

from ithaca_contracts import StrategySpec

from .skillset import SKILLS

SKILL_VERSION = "0.1.0"
RUNTIME_IMAGE = "ithaca/skill-runtime:0.1.0"

CORE_SKILL_IDS = (
    "backtest.run",
    "market.get_ohlcv",
    "market.quote",
)

_GROUP_DESCRIPTIONS = {
    "analyst": "Archive-backed analyst consensus, targets, and rating-change intelligence.",
    "broker": "Disabled broker surfaces. This deployment exposes market data and backtests only.",
    "commodity": "Community commodity price snapshots and recent changes.",
    "congress": "STOCK Act congressional trading disclosures and derived screens.",
    "correlation": "Computed correlation analytics over archive return series.",
    "crypto": "Community cryptocurrency price snapshots.",
    "dcf": "Computed discounted-cash-flow valuation using archive fundamentals and assumptions.",
    "dividends": "Community dividend history and trailing yield analytics.",
    "earnings": "Earnings calendars and transcript surfaces where licensed data is available.",
    "economic": "Community macro event calendar data.",
    "etf": "ETF holdings and reverse-exposure archive analytics.",
    "factor": "Computed style-factor exposure estimates from archive fundamentals.",
    "fda": "Community biotech catalyst calendar data.",
    "financials": "Archive financial-statement rows shaped for agent analysis.",
    "forex": "Community foreign-exchange rate snapshots.",
    "fundamentals": "Archive company fundamentals with provenance and point-in-time support.",
    "insider": "SEC insider transaction summaries from Form 4/5 style data.",
    "institutional": "13F institutional holdings and flow analytics from archive data.",
    "macro": "Community macro dashboard and regime summary data.",
    "market": "Ithaca live-data market quotes, history, news, movers, and screeners with provenance.",
    "montecarlo": "Seeded Monte Carlo scenario simulation.",
    "options": "Computed options valuation primitives from declared inputs.",
    "ops": "Internal platform operations diagnostics.",
    "politician": "Estimated politician portfolio analytics from disclosed trades.",
    "portfolio": "Computed portfolio construction and optimization primitives.",
    "risk": "Computed portfolio stress and risk diagnostics.",
    "scenario": "Seeded forward scenario projection.",
    "seasonality": "Archive seasonality analytics over historical return series.",
    "sentiment": "Archive sentiment snapshots by symbol, sector, or topic.",
    "short": "Community short-interest, short-volume, and failures-to-deliver analytics.",
    "stock": "Community corporate-action history.",
    "technical": "Computed technical indicators over archive OHLCV series.",
    "tearsheet": "Backtest tearsheet analytics over archive close series.",
    "universe": "Investable-universe coverage and metadata.",
    "vix": "Community VIX term-structure snapshots.",
    "vol": "Computed volatility analytics over archive series or declared option inputs.",
    "walkforward": "Walk-forward validation over archive close series.",
}

_PROFILE_OVERRIDES = {
    "backtest.run": "backtest",
    "market.screener": "scan",
    "short.screener": "scan",
    "congress.screener": "scan",
    "portfolio.optimize": "scan",
    "tearsheet": "backtest",
    "walkforward.run": "backtest",
    "montecarlo.simulate": "optimization",
}

_SEEDED = {"backtest.run", "montecarlo.simulate", "scenario.project"}

_COMPUTED_GROUPS = {
    "correlation",
    "dcf",
    "factor",
    "montecarlo",
    "options",
    "portfolio",
    "risk",
    "scenario",
    "vol",
}


def _title(skill_id: str) -> str:
    return skill_id.replace("_", " ").replace(".", " ").title()


def _group(skill_id: str) -> str:
    return skill_id.split(".", 1)[0]


def _source_classes(skill_id: str) -> list[str]:
    group = _group(skill_id)
    if skill_id in {
        "market.quote",
        "market.get_ohlcv",
        "market.news",
        "market.screener",
        "market.movers",
    }:
        return ["connected_account"]
    if group in _COMPUTED_GROUPS:
        return ["computed"]
    if skill_id in {"tearsheet", "walkforward.run", "technical.indicators"}:
        return ["community", "computed"]
    return ["community"]


def _datasets(skill_id: str) -> list[str]:
    group = _group(skill_id)
    if skill_id in {
        "market.quote",
        "market.get_ohlcv",
        "market.news",
        "market.screener",
        "market.movers",
    }:
        return []
    if group in _COMPUTED_GROUPS and group != "portfolio":
        return []
    if skill_id in {"portfolio.optimize", "tearsheet", "walkforward.run", "technical.indicators"}:
        return ["ithaca-v1-archive.prices"]
    return [f"ithaca-v1-archive.{group}"]


def _runtime(skill_id: str) -> dict[str, Any]:
    profile = _PROFILE_OVERRIDES.get(skill_id, "interactive")
    timeout = {
        "interactive": 120,
        "scan": 900,
        "backtest": 7200,
        "optimization": 14400,
        "stream": 0,
    }[profile]
    return {
        "profile": profile,
        "image": RUNTIME_IMAGE,
        "cpu": {"interactive": 1, "scan": 4, "backtest": 8, "optimization": 16}[profile],
        "memory_mb": {"interactive": 1024, "scan": 8192, "backtest": 32768, "optimization": 65536}[profile],
        "timeout_seconds": timeout,
    }


def _input_schema(skill_id: str) -> dict[str, Any]:
    if skill_id == "market.quote":
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["symbol"],
            "properties": {
                "symbol": {"type": "string", "minLength": 1},
                "max_freshness_ms": {"type": "integer", "minimum": 0},
            },
        }
    if skill_id == "broker.accounts":
        return {"type": "object", "additionalProperties": False, "properties": {}}
    if skill_id in {"broker.positions", "broker.orders"}:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "account": {"type": "string", "minLength": 1},
            },
        }
    if skill_id == "ops.provider_status":
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "symbol": {"type": "string", "default": "AAPL"},
                "max_freshness_ms": {"type": "integer", "minimum": 0},
            },
        }
    if skill_id == "market.get_ohlcv":
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["symbol"],
            "properties": {
                "symbol": {"type": "string", "minLength": 1},
                "range": {"type": "string", "default": "6mo"},
                "interval": {"type": "string", "default": "1d"},
            },
        }
    if skill_id == "backtest.run":
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["spec"],
            "properties": {
                # The worker validates this payload against the frozen contract.
                # Advertising an untyped object here caused MCP clients to submit
                # structurally invalid specs that only failed after being queued.
                "spec": StrategySpec.model_json_schema(),
                "range": {"type": "string", "default": "1y"},
            },
        }
    return {"type": "object", "additionalProperties": True}


def _manifest(skill_id: str) -> dict[str, Any]:
    group = _group(skill_id)
    description = _GROUP_DESCRIPTIONS.get(group, f"Runnable Ithaca skill: {_title(skill_id)}.")
    broker_permissions: list[str] = []
    network_permissions: list[str] = [] if "computed" in _source_classes(skill_id) else ["archive"]
    if skill_id in {"market.quote", "market.get_ohlcv", "market.news", "market.screener", "market.movers"}:
        network_permissions = ["ithaca-live-data"]
    return {
        "skill_id": skill_id,
        "version": SKILL_VERSION,
        "name": _title(skill_id),
        "description": description,
        "source_classes": _source_classes(skill_id),
        "runtime": _runtime(skill_id),
        "permissions": {
            "datasets": _datasets(skill_id),
            "broker": broker_permissions,
            "network": network_permissions,
        },
        "input_schema": _input_schema(skill_id),
        "output_schema": {"type": "object"},
        "freshness_requirement_seconds": 10 if skill_id == "market.quote" else 900 if skill_id == "market.get_ohlcv" else None,
        "trigger_compatible": group in {"market", "options", "risk", "technical", "vol"},
        "determinism": "seeded" if skill_id in _SEEDED else "deterministic",
        "artifact_types": ["report", "metrics", "orders", "fills"] if "backtest" in _runtime(skill_id)["profile"] else [],
        "deprecated": False,
    }


SKILL_MANIFESTS: dict[str, dict[str, Any]] = {
    skill_id: _manifest(skill_id)
    for skill_id in sorted(SKILLS)
}

CORE_SKILL_MANIFESTS: dict[str, dict[str, Any]] = {
    skill_id: _manifest(skill_id)
    for skill_id in CORE_SKILL_IDS
}

_all = {**CORE_SKILL_MANIFESTS, **SKILL_MANIFESTS}
ALL_SKILL_MANIFESTS: dict[str, dict[str, Any]] = {
    skill_id: _all[skill_id]
    for skill_id in sorted(_all)
}

__all__ = [
    "ALL_SKILL_MANIFESTS",
    "CORE_SKILL_IDS",
    "CORE_SKILL_MANIFESTS",
    "SKILL_MANIFESTS",
]
