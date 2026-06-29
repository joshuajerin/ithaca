"""The single core entry point both gateways (MCP + REST) call.

``run_tool(name, args, ctx)`` dispatches a data-layer tool; ``backtest(spec, ...)`` validates
a StrategySpec against the frozen contract, pulls its universe through the gateway, and runs
the shared accounting kernel. Keeping ONE entry means the MCP path and the UI path can never
diverge. ``ctx`` carries tenant/session/deadline (enforced by callers; threaded here for trace).
"""
from __future__ import annotations

from dataclasses import dataclass

from doomberg_contracts import StrategySpec

from .accounting import run_backtest
from .gateway import DataGateway

__all__ = ["CoreContext", "Core", "TOOLS"]


@dataclass
class CoreContext:
    tenant_id: str | None = None
    session_id: str | None = None
    actor_id: str | None = None
    deadline_ms: int | None = None


class Core:
    def __init__(self, gateway: DataGateway | None = None):
        self.gateway = gateway or DataGateway()

    # ---- data-layer tools -------------------------------------------------------------
    def market_get_ohlcv(self, args: dict, ctx: CoreContext | None = None) -> dict:
        symbol = args["symbol"]
        return self.gateway.get_ohlcv(
            symbol,
            range_=args.get("range", "6mo"),
            interval=args.get("interval", "1d"),
            as_of=args.get("as_of"),
        )

    # ---- research backtest ------------------------------------------------------------
    def backtest_run(self, args: dict, ctx: CoreContext | None = None) -> dict:
        """args = {spec: <StrategySpec>, range?: str, as_of?: str}."""
        spec = self.validate_spec(args["spec"])
        panel, prov = self.gateway.price_panel(
            spec["universe"]["symbols"],
            range_=args.get("range", "1y"),
            as_of=args.get("as_of"),
        )
        if panel.closes.shape[0] < 3 or panel.closes.shape[1] == 0:
            return {
                "data": None,
                "provenance": prov["provenance"],
                "partial": True,
                "warnings": prov["warnings"] + [
                    {"code": "INSUFFICIENT_DATA", "scope": None,
                     "detail": "not enough overlapping bars to backtest"}
                ],
            }
        result = run_backtest(spec, panel.dates, panel.closes, panel.symbols)
        result["dataQuality"] = {
            "ohlcv": panel.quality,
            "pointInTime": prov["provenance"].get("pit") == "true",
        }
        return {
            "data": result,
            "provenance": prov["provenance"],
            "partial": bool(panel.missing),
            "warnings": prov["warnings"],
        }

    # ---- validation -------------------------------------------------------------------
    @staticmethod
    def validate_spec(spec: dict) -> dict:
        """Validate against the frozen StrategySpec contract; strip server-stamped fields.

        Raises pydantic ValidationError on any closed-schema violation (incl. a smuggled
        free-form field). Returns a plain dict with id/version/tenant_id cleared so the agent
        can never set them (they are server-stamped downstream).
        """
        model = StrategySpec.model_validate(spec)
        out = model.model_dump(mode="json", by_alias=True)
        out["id"] = None
        out["version"] = None
        out["tenant_id"] = None
        return out

    # ---- dispatch ---------------------------------------------------------------------
    def run_tool(self, name: str, args: dict, ctx: CoreContext | None = None) -> dict:
        if name not in TOOLS:
            raise ValueError(f"unknown tool: {name!r} (have {sorted(TOOLS)})")
        return getattr(self, TOOLS[name])(args, ctx)


# tool name -> Core method. The MCP gateway advertises these; the REST gateway shares them.
TOOLS: dict[str, str] = {
    "market.get_ohlcv": "market_get_ohlcv",
    "backtest.run": "backtest_run",
}
