"""MCP key issuance through the web sign-in path.

A signed-in human mints bearer keys for their own tenant; a bare API key cannot mint more
keys (issuance requires a session). Keys are tenant-scoped, the plaintext is shown once, and
revocation is ownership-checked (no cross-tenant revoke).
"""

from __future__ import annotations


def _signup(client, email="founder@acme.test", name="Founder", password="hunter2hunter2"):
    r = client.post("/api/auth/signup", json={"email": email, "name": name, "password": password})
    assert r.status_code == 201, r.text
    body = r.json()
    return body["token"], body["user"]["tenantId"]


def _bearer(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def test_signed_in_user_mints_lists_and_uses_key(client, stores):
    token, tenant_id = _signup(client)

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


def test_mint_defaults_to_full_issuable_scope_set(client):
    token, _ = _signup(client)
    r = client.post("/api/auth/keys", json={}, headers=_bearer(token))
    assert r.status_code == 201, r.text
    assert set(r.json()["scopes"]) == {
        "data:read", "strategy:author", "deploy:backtest", "deploy:paper",
    }


def test_unissuable_scope_is_422(client):
    token, _ = _signup(client)
    r = client.post("/api/auth/keys", json={"scopes": ["deploy:live"]}, headers=_bearer(token))
    assert r.status_code == 422


def test_api_key_cannot_mint_more_keys(client, stores):
    """Issuance requires a human session — a bare API key is rejected (401)."""
    token, _ = _signup(client)
    api_key = client.post("/api/auth/keys", json={"scopes": ["data:read"]},
                          headers=_bearer(token)).json()["api_key"]
    r = client.post("/api/auth/keys", json={"scopes": ["data:read"]}, headers=_bearer(api_key))
    assert r.status_code == 401


def test_anonymous_cannot_manage_keys(client):
    assert client.get("/api/auth/keys").status_code == 401
    assert client.post("/api/auth/keys", json={}).status_code == 401


def test_revoke_then_key_is_dead(client):
    token, _ = _signup(client)
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


def test_cannot_revoke_another_tenants_key(client):
    alice, _ = _signup(client, email="alice@acme.test", name="Alice")
    bob, _ = _signup(client, email="bob@beta.test", name="Bob")

    bob_key_id = client.post("/api/auth/keys", json={"scopes": ["data:read"]},
                             headers=_bearer(bob)).json()["key_id"]

    # Alice cannot see or revoke Bob's key.
    r = client.delete(f"/api/auth/keys/{bob_key_id}", headers=_bearer(alice))
    assert r.status_code == 404
