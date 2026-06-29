"""MCP key issuance through the web sign-in path.

A signed-in human mints bearer keys for their own tenant; a bare API key cannot mint more
keys (issuance requires a session). Keys are tenant-scoped, the plaintext is shown once, and
revocation is ownership-checked (no cross-tenant revoke).
"""

from __future__ import annotations


def _bearer(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def _clerk_session(client, clerk_auth, email="founder@acme.test", name="Founder"):
    token = clerk_auth(email=email, name=name)
    r = client.get("/api/auth/me", headers=_bearer(token))
    assert r.status_code == 200, r.text
    body = r.json()
    return token, body["tenantId"]


def test_signed_in_user_mints_lists_and_uses_key(client, stores, clerk_auth):
    token, tenant_id = _clerk_session(client, clerk_auth)

    # Mint with explicit scopes; plaintext returned once, bound to the user's tenant.
    r = client.post("/api/auth/keys", json={"scopes": ["data:read"]}, headers=_bearer(token))
    assert r.status_code == 201, r.text
    minted = r.json()
    assert minted["tenant_id"] == tenant_id
    assert minted["scopes"] == ["data:read"]
    api_key = minted["api_key"]
    assert api_key.startswith("dmbg_")

    # The minted key resolves to the same tenant on the data path.
    assert client.get("/api/runs", headers=_bearer(api_key)).status_code == 200

    # It is listed (metadata only — no secret).
    listed = client.get("/api/auth/keys", headers=_bearer(token)).json()["keys"]
    assert [k["key_id"] for k in listed] == [minted["key_id"]]
    assert "api_key" not in listed[0]


def test_mint_defaults_to_agent_operational_scope_set(client, clerk_auth):
    token, _ = _clerk_session(client, clerk_auth)
    r = client.post("/api/auth/keys", json={}, headers=_bearer(token))
    assert r.status_code == 201, r.text
    assert set(r.json()["scopes"]) == {
        "data:read",
        "strategy:author",
        "runs:write",
        "runs:cancel",
        "approvals:read",
        "triggers:read",
        "alerts:read",
        "alerts:ack",
        "artifacts:read",
        "deploy:backtest",
        "deploy:paper",
    }


def test_agent_key_cannot_decide_approval_even_with_scope_or_actor_header(client, stores, clerk_auth):
    token, tenant_id = _clerk_session(client, clerk_auth)
    api_key = client.post(
        "/api/auth/keys",
        json={"scopes": ["data:read", "approvals:read", "approvals:decide"]},
        headers=_bearer(token),
    ).json()["api_key"]
    run_id = stores.runs.create(tenant_id, "trigger", None, {"name": "approval-test"})
    approval = stores.approvals.create(
        tenant_id,
        run_id,
        kind="trigger_action",
        request={"symbol": "NVDA"},
        requested_by="agent",
    )

    resp = client.post(
        f"/api/approvals/{approval['approval_id']}/decide",
        json={"decision": "approved"},
        headers={**_bearer(api_key), "X-Actor-Kind": "human"},
    )

    assert resp.status_code == 403
    assert stores.approvals.list_pending(tenant_id)[0]["approval_id"] == approval["approval_id"]


def test_agent_key_needs_explicit_provider_and_trigger_write_scopes(client, clerk_auth):
    token, _ = _clerk_session(client, clerk_auth)
    api_key = client.post(
        "/api/auth/keys",
        json={"scopes": ["data:read"]},
        headers=_bearer(token),
    ).json()["api_key"]

    provider = client.post(
        "/api/providers",
        json={"provider": "ibkr-engine", "capabilities": ["quote"]},
        headers=_bearer(api_key),
    )
    trigger = client.post(
        "/api/triggers",
        json={
            "name": "nvda",
            "policy": {"when": {"event": "price.threshold"}, "action": {"run_skill": "market.quote"}},
        },
        headers=_bearer(api_key),
    )

    assert provider.status_code == 403
    assert trigger.status_code == 403


def test_unissuable_scope_is_422(client, clerk_auth):
    token, _ = _clerk_session(client, clerk_auth)
    r = client.post("/api/auth/keys", json={"scopes": ["deploy:live"]}, headers=_bearer(token))
    assert r.status_code == 422


def test_api_key_cannot_mint_more_keys(client, stores, clerk_auth):
    """Issuance requires a human session — a bare API key is rejected (401)."""
    token, _ = _clerk_session(client, clerk_auth)
    api_key = client.post("/api/auth/keys", json={"scopes": ["data:read"]},
                          headers=_bearer(token)).json()["api_key"]
    r = client.post("/api/auth/keys", json={"scopes": ["data:read"]}, headers=_bearer(api_key))
    assert r.status_code == 401


def test_anonymous_cannot_manage_keys(client):
    assert client.get("/api/auth/keys").status_code == 401
    assert client.post("/api/auth/keys", json={}).status_code == 401


def test_revoke_then_key_is_dead(client, clerk_auth):
    token, _ = _clerk_session(client, clerk_auth)
    minted = client.post("/api/auth/keys", json={"scopes": ["data:read"]},
                         headers=_bearer(token)).json()
    api_key, key_id = minted["api_key"], minted["key_id"]

    r = client.delete(f"/api/auth/keys/{key_id}", headers=_bearer(token))
    assert r.status_code == 200 and r.json()["revoked"] is True

    # Revoked key no longer authenticates; it drops out of the active list.
    assert client.get("/api/runs", headers=_bearer(api_key)).status_code == 401
    active = [k for k in client.get("/api/auth/keys", headers=_bearer(token)).json()["keys"]
              if not k["revoked"]]
    assert active == []


def test_cannot_revoke_another_tenants_key(client, clerk_auth):
    alice, _ = _clerk_session(client, clerk_auth, email="alice@acme.test", name="Alice")
    bob, _ = _clerk_session(client, clerk_auth, email="bob@beta.test", name="Bob")

    bob_key_id = client.post("/api/auth/keys", json={"scopes": ["data:read"]},
                             headers=_bearer(bob)).json()["key_id"]

    # Alice cannot see or revoke Bob's key.
    r = client.delete(f"/api/auth/keys/{bob_key_id}", headers=_bearer(alice))
    assert r.status_code == 404
