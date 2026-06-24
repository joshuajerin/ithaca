"""Shared test helpers: UUIDs, valid trace events, valid strategy specs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def new_uuid() -> str:
    return str(uuid.uuid4())


def trace_event(
    tenant_id: str,
    run_id: str,
    *,
    type: str = "reasoning",
    data: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "run_id": run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": type,
        "tenant_id": tenant_id,
        "data": data if data is not None else {},
    }
    ev.update(extra)
    return ev


def strategy_spec(name: str = "Momentum 12-1") -> dict[str, Any]:
    return {
        "spec_version": "1.0",
        "name": name,
        "universe": {"symbols": ["SPY", "QQQ", "IWM"], "source": "prices"},
        "strategy": {"id": "momentum", "params": {"lookback": 252, "top": 2}},
        "construction": {"scheme": "equal_weight", "long_only": True, "gross": 1.0},
        "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.5},
        "execution": {"cost_bps": 5.0, "algo": "vwap", "rebalance": "monthly@close"},
        "seed": 42,
    }
