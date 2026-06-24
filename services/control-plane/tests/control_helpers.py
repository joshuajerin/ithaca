from __future__ import annotations

import uuid


def human_headers(tenant_id: str) -> dict[str, str]:
    return {
        "X-Tenant-Id": tenant_id,
        "X-Actor-Kind": "human",
        "X-Actor-Id": "trader-1",
    }


def agent_headers(tenant_id: str) -> dict[str, str]:
    return {
        "X-Tenant-Id": tenant_id,
        "X-Actor-Kind": "agent",
        "X-Actor-Id": str(uuid.uuid4()),
    }


def valid_spec(name: str = "Momentum Top-N", symbols: list[str] | None = None) -> dict:
    return {
        "spec_version": "1.0",
        "name": name,
        "universe": {"symbols": symbols or ["AAPL", "MSFT", "NVDA", "AMZN"], "source": "prices"},
        "strategy": {"id": "momentum", "params": {"lookback": 60, "top": 2}},
        "construction": {"scheme": "equal_weight", "long_only": True, "gross": 1.0},
        "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.5},
        "execution": {"cost_bps": 5.0, "algo": "vwap", "rebalance": "weekly@close"},
        "seed": 42,
    }
