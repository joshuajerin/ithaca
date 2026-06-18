"""The UI's human money-path actions, served by the rest-gateway over the SHARED
control-plane implementation (one money path, two transports)."""

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


def test_propose_then_create_then_promote_then_activate(client, tenant):
    # propose
    r = client.post("/api/strategies", json={"spec": _spec()}, headers=_h(tenant))
    assert r.status_code == 201
    sid = r.json()["id"]

    # create paper run (queued)
    r = client.post("/api/runs", json={"strategy_id": sid, "kind": "paper"}, headers=_h(tenant))
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    assert r.json()["state"] == "queued"

    # promote (human=UI by default) then activate -> live
    assert client.post(f"/api/runs/{run_id}/promote", headers=_h(tenant)).json()["state"] == "promoted"
    assert client.post(f"/api/runs/{run_id}/activate", headers=_h(tenant)).json()["state"] == "live"

    # the run now lists as a live paper deployment
    listed = client.get("/api/runs", params={"kind": "paper"}, headers=_h(tenant)).json()["runs"]
    assert listed[0]["state"] == "live"


def test_agent_actor_cannot_promote_via_ui_backend(client, tenant):
    sid = client.post("/api/strategies", json={"spec": _spec()}, headers=_h(tenant)).json()["id"]
    run_id = client.post("/api/runs", json={"strategy_id": sid, "kind": "paper"},
                         headers=_h(tenant)).json()["run_id"]
    resp = client.post(f"/api/runs/{run_id}/promote",
                       headers={"X-Tenant-Id": tenant, "X-Actor-Kind": "agent"})
    assert resp.status_code == 403


def test_propose_invalid_spec_422(client, tenant):
    bad = _spec()
    bad["construction"]["gross"] = 99.0
    assert client.post("/api/strategies", json={"spec": bad}, headers=_h(tenant)).status_code == 422


def test_book_endpoint_returns_none_until_applied(client, tenant):
    sid = client.post("/api/strategies", json={"spec": _spec()}, headers=_h(tenant)).json()["id"]
    run_id = client.post("/api/runs", json={"strategy_id": sid, "kind": "paper"},
                         headers=_h(tenant)).json()["run_id"]
    body = client.get(f"/api/runs/{run_id}/book", headers=_h(tenant)).json()
    assert body["book"] is None


def test_create_run_unknown_strategy_404(client, tenant):
    resp = client.post("/api/runs", json={"strategy_id": str(uuid.uuid4()), "kind": "backtest"},
                       headers=_h(tenant))
    assert resp.status_code == 404
