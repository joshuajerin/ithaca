"""Write-action policy tests for the public REST gateway."""

from __future__ import annotations

import uuid

import pytest


def _spec(name="UI Momentum", symbols=None):
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


@pytest.fixture()
def tenant() -> str:
    return str(uuid.uuid4())


def _h(tenant):
    return {"X-Tenant-Id": tenant}


def test_propose_then_backtest_create_succeeds_but_trading_lifecycle_is_disabled(client, tenant):
    r = client.post("/api/strategies", json={"spec": _spec()}, headers=_h(tenant))
    assert r.status_code == 201
    sid = r.json()["id"]

    r = client.post("/api/runs", json={"strategy_id": sid, "kind": "paper"}, headers=_h(tenant))
    assert r.status_code == 403
    assert "trading is disabled" in r.json()["detail"]

    r = client.post("/api/runs", json={"strategy_id": sid, "kind": "backtest"}, headers=_h(tenant))
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    assert r.json()["kind"] == "backtest"

    for action in ("promote", "activate", "pause", "resume", "retire"):
        blocked = client.post(f"/api/runs/{run_id}/{action}", headers=_h(tenant))
        assert blocked.status_code == 403
        assert "trading lifecycle actions are disabled" in blocked.json()["detail"]


def test_agent_actor_cannot_create_trading_run(client, tenant):
    sid = client.post("/api/strategies", json={"spec": _spec()}, headers=_h(tenant)).json()["id"]
    resp = client.post(
        "/api/runs",
        json={"strategy_id": sid, "kind": "paper"},
        headers={"X-Tenant-Id": tenant, "X-Actor-Kind": "agent"},
    )
    assert resp.status_code == 403


def test_propose_invalid_spec_422(client, tenant):
    bad = _spec()
    bad["construction"]["gross"] = 99.0
    assert client.post("/api/strategies", json={"spec": bad}, headers=_h(tenant)).status_code == 422


def test_book_endpoint_returns_none_without_trading_state(client, tenant):
    sid = client.post("/api/strategies", json={"spec": _spec()}, headers=_h(tenant)).json()["id"]
    run_id = client.post("/api/runs", json={"strategy_id": sid, "kind": "backtest"},
                         headers=_h(tenant)).json()["run_id"]
    body = client.get(f"/api/runs/{run_id}/book", headers=_h(tenant)).json()
    assert body["book"] is None


def test_create_run_unknown_strategy_404(client, tenant):
    resp = client.post("/api/runs", json={"strategy_id": str(uuid.uuid4()), "kind": "backtest"},
                       headers=_h(tenant))
    assert resp.status_code == 404
