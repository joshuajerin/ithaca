"""Front-door auth on the UI's backend: bearer keys resolve the tenant + scopes.

The rest-gateway shares the control-plane money path; here we only assert the gateway's own
principal resolver: a bearer key binds the tenant authoritatively, a bad key is 401, and the
existing ``X-Tenant-Id`` dev path is untouched.
"""

from __future__ import annotations

import uuid


def _spec(name="UI Auth Momentum"):
    return {
        "spec_version": "1.0",
        "name": name,
        "universe": {"symbols": ["AAPL", "MSFT", "NVDA", "AMZN"], "source": "prices"},
        "strategy": {"id": "momentum", "params": {"lookback": 60, "top": 2}},
        "construction": {"scheme": "equal_weight", "long_only": True, "gross": 1.0},
        "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.5},
        "execution": {"cost_bps": 5.0, "algo": "vwap", "rebalance": "weekly@close"},
        "seed": 42,
    }


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_bearer_key_binds_tenant_authoritatively(client, stores):
    tid = stores.auth.create_tenant("Acme")
    key, _ = stores.auth.mint_key(tid, ["data:read", "strategy:author"])

    # Read path: the key's tenant is used (no X-Tenant-Id header in sight).
    r = client.get("/api/runs", headers=_bearer(key))
    assert r.status_code == 200
    assert r.json()["runs"] == []

    # Write path: a proposed strategy lands under the key's tenant.
    sid = client.post("/api/strategies", json={"spec": _spec()},
                      headers=_bearer(key)).json()["id"]
    assert stores.strategies.get(tid, sid) is not None


def test_bad_bearer_key_is_401(client):
    r = client.get("/api/runs", headers={"Authorization": "Bearer dmbg_test_nope_bogus"})
    assert r.status_code == 401


def test_revoked_bearer_key_is_401(client, stores):
    tid = stores.auth.create_tenant("Acme")
    key, key_id = stores.auth.mint_key(tid, ["data:read"])
    assert stores.auth.revoke_key(key_id) is True
    assert client.get("/api/runs", headers=_bearer(key)).status_code == 401


def test_agent_key_scope_too_low_to_author_is_403(client, stores):
    tid = stores.auth.create_tenant("Acme")
    key, _ = stores.auth.mint_key(tid, ["data:read"])  # no strategy:author
    r = client.post("/api/strategies", json={"spec": _spec()}, headers=_bearer(key))
    assert r.status_code == 403


def test_x_tenant_id_dev_fallback_still_works(client):
    tid = str(uuid.uuid4())
    assert client.get("/api/runs", headers={"X-Tenant-Id": tid}).status_code == 200


def test_x_tenant_id_fallback_disabled_in_prod(client, monkeypatch):
    monkeypatch.setenv("DOOMBERG_ENV", "prod")
    tid = str(uuid.uuid4())
    resp = client.get("/api/runs", headers={"X-Tenant-Id": tid})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "authentication required"
