"""Test fixtures + import-path fallback for the control plane.

In the integrated workspace, ``doomberg_core`` / ``doomberg_contracts`` / ``doomberg_platform``
and this package are installed editable, so the path-insertion below is a no-op. When running
in isolation we add the package source roots so imports resolve.

Each test gets a fresh in-memory platform and a fresh app whose dependency overrides point at
that platform — so tenant isolation and trace state never leak between tests.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _ensure_importable() -> None:
    candidates = [
        _REPO_ROOT / "packages" / "contracts" / "py",
        _REPO_ROOT / "doomberg-core" / "src",
        _REPO_ROOT / "services" / "platform" / "src",
        _REPO_ROOT / "services" / "control-plane" / "src",
    ]
    for path in candidates:
        sp = str(path)
        if path.exists() and sp not in sys.path:
            sys.path.insert(0, sp)


_ensure_importable()

from fastapi.testclient import TestClient  # noqa: E402

from doomberg_control.app import create_app  # noqa: E402
from doomberg_control.deps import Platform, get_core, get_platform  # noqa: E402
from doomberg_core import Core  # noqa: E402


@pytest.fixture()
def platform():
    return Platform(":memory:")


@pytest.fixture()
def client(platform):
    app = create_app()
    app.dependency_overrides[get_platform] = lambda: platform
    app.dependency_overrides[get_core] = lambda: Core()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def tenant_a() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def tenant_b() -> str:
    return str(uuid.uuid4())


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
    """A minimal, schema-valid StrategySpec (long-only momentum, feasible risk limits)."""
    return {
        "spec_version": "1.0",
        "name": name,
        "universe": {"symbols": symbols or ["AAPL", "MSFT", "NVDA", "AMZN"],
                     "source": "prices"},
        "strategy": {"id": "momentum", "params": {"lookback": 60, "top": 2}},
        "construction": {"scheme": "equal_weight", "long_only": True, "gross": 1.0},
        "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.5},
        "execution": {"cost_bps": 5.0, "algo": "vwap", "rebalance": "weekly@close"},
        "seed": 42,
    }


@pytest.fixture()
def spec() -> dict:
    return valid_spec()
