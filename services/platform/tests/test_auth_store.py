"""AuthStore — tenants + API keys (the front-door principal resolver)."""

from __future__ import annotations

import pytest

from doomberg_platform import AuthStore, hash_secret
from doomberg_platform.auth_store import KEY_PREFIX, VALID_SCOPES


@pytest.fixture()
def auth(db):
    return AuthStore(db)


# ---- tenants ---------------------------------------------------------------------------
def test_create_tenant_returns_uuid_and_is_retrievable(auth):
    tid = auth.create_tenant("Acme Capital")
    assert len(tid) == 36 and tid.count("-") == 4  # uuid string
    got = auth.get_tenant(tid)
    assert got["id"] == tid
    assert got["name"] == "Acme Capital"


def test_create_tenant_rejects_blank_name(auth):
    with pytest.raises(ValueError):
        auth.create_tenant("   ")


# ---- key format ------------------------------------------------------------------------
def test_mint_key_has_contract_format_and_returns_keyid(auth):
    tid = auth.create_tenant("t")
    key, key_id = auth.mint_key(tid, ["data:read"])
    parts = key.split("_", 3)
    assert parts[0] == KEY_PREFIX  # dmbg
    assert len(parts) == 4         # dmbg_<env>_<keyid>_<secret>
    assert parts[2] == key_id      # the public, stable credential id


def test_only_hash_is_stored_never_the_plaintext(auth, db):
    tid = auth.create_tenant("t")
    key, key_id = auth.mint_key(tid, ["data:read"])
    secret = key.split("_", 3)[3]
    row = db.conn.execute(
        "SELECT secret_hash, salt FROM api_keys WHERE key_id = ?", (key_id,)
    ).fetchone()
    # The plaintext secret is nowhere in the row; only the salted hash matches.
    assert secret not in row["secret_hash"]
    assert row["secret_hash"] == hash_secret(row["salt"], secret)


# ---- verify ----------------------------------------------------------------------------
def test_verify_valid_key_yields_tenant_and_scopes(auth):
    tid = auth.create_tenant("t")
    key, key_id = auth.mint_key(tid, ["data:read", "strategy:author"])
    principal = auth.verify(key)
    assert principal["tenant_id"] == tid
    assert principal["key_id"] == key_id
    assert set(principal["scopes"]) == {"data:read", "strategy:author"}


def test_verify_rejects_garbage_and_wrong_secret(auth):
    tid = auth.create_tenant("t")
    key, key_id = auth.mint_key(tid, ["data:read"])
    assert auth.verify("not-a-key") is None
    assert auth.verify("") is None
    assert auth.verify(None) is None  # type: ignore[arg-type]
    # right keyid, tampered secret
    tampered = f"{KEY_PREFIX}_test_{key_id}_deadbeefdeadbeef"
    assert auth.verify(tampered) is None
    # unknown keyid
    assert auth.verify(f"{KEY_PREFIX}_test_unknownkeyid_{key.split('_', 3)[3]}") is None


def test_verify_ignores_revoked_keys(auth):
    tid = auth.create_tenant("t")
    key, key_id = auth.mint_key(tid, ["data:read"])
    assert auth.verify(key) is not None
    assert auth.revoke_key(key_id) is True
    assert auth.verify(key) is None
    # idempotent: re-revoking an already-revoked key is a no-op
    assert auth.revoke_key(key_id) is False


# ---- scope discipline ------------------------------------------------------------------
def test_mint_rejects_deploy_live_and_unknown_scopes(auth):
    tid = auth.create_tenant("t")
    assert "deploy:live" not in VALID_SCOPES
    with pytest.raises(ValueError):
        auth.mint_key(tid, ["deploy:live"])
    with pytest.raises(ValueError):
        auth.mint_key(tid, ["data:read", "totally:made-up"])


def test_mint_rejects_unknown_tenant(auth):
    with pytest.raises(ValueError):
        auth.mint_key("00000000-0000-0000-0000-0000000000ff", ["data:read"])


def test_two_tenants_keys_are_isolated(auth):
    a, b = auth.create_tenant("a"), auth.create_tenant("b")
    ka, _ = auth.mint_key(a, ["data:read"])
    kb, _ = auth.mint_key(b, ["data:read"])
    assert auth.verify(ka)["tenant_id"] == a
    assert auth.verify(kb)["tenant_id"] == b
    assert auth.verify(ka)["tenant_id"] != auth.verify(kb)["tenant_id"]


def test_list_keys_never_exposes_secret(auth):
    tid = auth.create_tenant("t")
    _, key_id = auth.mint_key(tid, ["data:read", "deploy:paper"])
    listed = auth.list_keys(tid)
    assert len(listed) == 1
    entry = listed[0]
    assert entry["key_id"] == key_id
    assert set(entry["scopes"]) == {"data:read", "deploy:paper"}
    assert entry["revoked"] is False
    assert "secret" not in entry and "secret_hash" not in entry
