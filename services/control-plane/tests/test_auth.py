"""Front-door auth on the control plane: bearer keys, scope enforcement, admin gating.

These ride the SAME ``client``/``platform`` fixtures as the rest of the suite. The existing
``X-Tenant-Id`` dev path is covered elsewhere; here we add the authed-key path on top.
"""

from __future__ import annotations

import uuid

import pytest

from conftest import valid_spec


def _mint(platform, scopes, name="Acme"):
    """Create a tenant + key directly via the platform AuthStore."""
    tid = platform.auth.create_tenant(name)
    key, key_id = platform.auth.mint_key(tid, scopes)
    return tid, key, key_id


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


# ---- the bearer key resolves a real principal ------------------------------------------
def test_valid_key_resolves_ctx_and_proposes(client, platform):
    tid, key, _ = _mint(platform, ["strategy:author"])
    resp = client.post("/strategies", json={"spec": valid_spec()}, headers=_bearer(key))
    assert resp.status_code == 201
    body = resp.json()
    # The strategy is persisted under the key's tenant (NOT any header tenant).
    assert platform.strategies.get(tid, body["id"]) is not None


def test_bad_key_is_401(client):
    resp = client.post("/strategies", json={"spec": valid_spec()},
                       headers={"Authorization": "Bearer dmbg_test_nope_bogus"})
    assert resp.status_code == 401


def test_revoked_key_is_401(client, platform):
    tid, key, key_id = _mint(platform, ["strategy:author"])
    assert platform.auth.revoke_key(key_id) is True
    resp = client.post("/strategies", json={"spec": valid_spec()}, headers=_bearer(key))
    assert resp.status_code == 401


# ---- scope enforcement -----------------------------------------------------------------
def test_scope_too_low_for_propose_is_403(client, platform):
    # A data:read-only key cannot author a strategy.
    _, key, _ = _mint(platform, ["data:read"])
    resp = client.post("/strategies", json={"spec": valid_spec()}, headers=_bearer(key))
    assert resp.status_code == 403


def test_backtest_create_needs_deploy_backtest_scope(client, platform):
    tid, key, _ = _mint(platform, ["strategy:author"])  # no deploy:backtest
    sid = client.post("/strategies", json={"spec": valid_spec()},
                      headers=_bearer(key)).json()["id"]
    resp = client.post("/runs", json={"strategy_id": sid, "kind": "backtest"},
                       headers=_bearer(key))
    assert resp.status_code == 403


def test_agent_key_with_deploy_paper_can_request_but_cannot_promote(client, platform):
    # deploy:paper means "may REQUEST" — the key can create a paper run, but an agent
    # actor can never self-promote (the human-actor rule, independent of scope).
    tid, key, _ = _mint(platform, ["strategy:author", "deploy:paper"])
    sid = client.post("/strategies", json={"spec": valid_spec()},
                      headers=_bearer(key)).json()["id"]
    run_id = client.post("/runs", json={"strategy_id": sid, "kind": "paper"},
                         headers=_bearer(key)).json()["run_id"]
    resp = client.post(f"/runs/{run_id}/promote", headers=_bearer(key))
    assert resp.status_code == 403  # agent actor blocked at the human gate
    types = [e["type"] for e in platform.traces.events(tid, run_id)]
    assert "denial" in types


def test_agent_key_cannot_spoof_human_actor_header(client, platform):
    tid, key, _ = _mint(platform, ["strategy:author", "deploy:paper"])
    sid = client.post("/strategies", json={"spec": valid_spec()},
                      headers=_bearer(key)).json()["id"]
    run_id = client.post("/runs", json={"strategy_id": sid, "kind": "paper"},
                         headers=_bearer(key)).json()["run_id"]

    resp = client.post(
        f"/runs/{run_id}/promote",
        headers={**_bearer(key), "X-Actor-Kind": "human", "X-Actor-Id": "spoof"},
    )

    assert resp.status_code == 403


# ---- dev fallback still works (no bearer key) ------------------------------------------
def test_x_tenant_id_dev_fallback_still_works(client):
    tid = str(uuid.uuid4())
    resp = client.post("/strategies", json={"spec": valid_spec()},
                       headers={"X-Tenant-Id": tid, "X-Actor-Kind": "human"})
    assert resp.status_code == 201


def test_x_tenant_id_fallback_disabled_in_prod(client, monkeypatch):
    monkeypatch.setenv("DOOMBERG_ENV", "prod")
    tid = str(uuid.uuid4())
    resp = client.post("/strategies", json={"spec": valid_spec()},
                       headers={"X-Tenant-Id": tid, "X-Actor-Kind": "human"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "authentication required"


def test_no_credentials_at_all_is_401(client):
    assert client.post("/strategies", json={"spec": valid_spec()}).status_code == 401


# ---- admin endpoints: inert unless DOOMBERG_ADMIN_TOKEN is set -------------------------
def test_admin_endpoints_404_when_token_unset(client, monkeypatch):
    monkeypatch.delenv("DOOMBERG_ADMIN_TOKEN", raising=False)
    assert client.post("/admin/tenants", json={"name": "x"}).status_code == 404
    assert client.post(f"/admin/tenants/{uuid.uuid4()}/keys",
                       json={"scopes": ["data:read"]}).status_code == 404


def test_admin_requires_matching_token(client, monkeypatch):
    monkeypatch.setenv("DOOMBERG_ADMIN_TOKEN", "s3cret")
    assert client.post("/admin/tenants", json={"name": "x"}).status_code == 401
    assert client.post("/admin/tenants", json={"name": "x"},
                       headers={"X-Admin-Token": "wrong"}).status_code == 401


def test_admin_can_create_tenant_and_mint_key_end_to_end(client, platform, monkeypatch):
    monkeypatch.setenv("DOOMBERG_ADMIN_TOKEN", "s3cret")
    h = {"X-Admin-Token": "s3cret"}
    created = client.post("/admin/tenants", json={"name": "Acme"}, headers=h)
    assert created.status_code == 201
    tid = created.json()["tenant_id"]

    minted = client.post(f"/admin/tenants/{tid}/keys",
                         json={"scopes": ["data:read", "strategy:author"]}, headers=h)
    assert minted.status_code == 201
    key = minted.json()["api_key"]
    # The freshly minted key works against the authed path.
    assert client.post("/strategies", json={"spec": valid_spec()},
                       headers=_bearer(key)).status_code == 201


def test_admin_mint_rejects_deploy_live_scope(client, monkeypatch):
    monkeypatch.setenv("DOOMBERG_ADMIN_TOKEN", "s3cret")
    h = {"X-Admin-Token": "s3cret"}
    tid = client.post("/admin/tenants", json={"name": "Acme"}, headers=h).json()["tenant_id"]
    resp = client.post(f"/admin/tenants/{tid}/keys",
                       json={"scopes": ["deploy:live"]}, headers=h)
    assert resp.status_code == 400
