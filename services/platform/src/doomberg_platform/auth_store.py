"""The front door: tenants + API keys (the principal resolver's system-of-record).

Account model (per ``packages/contracts/schema/{auth,tenant}.schema.json``):
    Tenant -> API key (a rotatable credential carrying capability scopes).

Key format is FROZEN by the auth contract::

    dmbg_<env>_<keyid>_<secret>

- ``<env>``   deployment env tag (``test`` by default; ``prod`` in production).
- ``<keyid>`` the public, stable credential id (a uuid4 hex). Lets one credential be
  revoked without rotating the principal; it is what audit attributes to.
- ``<secret>`` a high-entropy URL-safe token. NEVER stored: only ``sha256(salt + secret)``
  is persisted, so a database leak cannot reconstruct a usable key. The plaintext is
  returned exactly ONCE, at mint time.

Verification is constant-time (``hmac.compare_digest``) and ignores revoked keys. Scopes are
the launch capability set (``data:read``, ``strategy:author``, ``deploy:backtest``,
``deploy:paper``); ``deploy:live`` is intentionally unissuable (paper-only by construction).

Stdlib only — no new dependencies (``hashlib`` + ``hmac`` + ``secrets`` + ``uuid``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import Db

__all__ = ["AuthStore", "VALID_SCOPES", "KEY_PREFIX", "hash_secret"]

KEY_PREFIX = "dmbg"

# The launch capability set. deploy:live is deliberately absent (paper-only by construction);
# minting it raises so the contract cannot be violated through this store.
VALID_SCOPES: frozenset[str] = frozenset(
    {
        "data:read",
        "strategy:author",
        "runs:write",
        "runs:cancel",
        "approvals:read",
        "approvals:decide",
        "providers:write",
        "triggers:write",
        "artifacts:read",
        "deploy:backtest",
        "deploy:paper",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_tag() -> str:
    """The ``<env>`` segment baked into minted keys (``test`` unless overridden)."""
    return (os.environ.get("DOOMBERG_ENV") or "test").strip().lower() or "test"


def hash_secret(salt: str, secret: str) -> str:
    """``sha256(salt + secret)`` as hex — the only form of the secret ever stored."""
    return hashlib.sha256((salt + secret).encode("utf-8")).hexdigest()


class AuthStore:
    """Tenants + API keys. The principal resolver both HTTP front doors call."""

    def __init__(self, db: Db) -> None:
        self._db = db

    # ---- tenants -----------------------------------------------------------------------
    def create_tenant(self, name: str) -> str:
        """Create a tenant; returns its uuid id."""
        name = (name or "").strip()
        if not name:
            raise ValueError("tenant name must be non-empty")
        tenant_id = str(uuid.uuid4())
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO tenants (id, name, created_at) VALUES (?, ?, ?)",
                    (tenant_id, name, _now()),
                )
        return tenant_id

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM tenants WHERE id = ?", (str(tenant_id),)
        ).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "name": row["name"], "created_at": row["created_at"]}

    # ---- api keys ----------------------------------------------------------------------
    def mint_key(self, tenant_id: str, scopes: list[str]) -> tuple[str, str]:
        """Mint a key for ``tenant_id``; returns ``(plaintext_key, key_id)``.

        The plaintext (``dmbg_<env>_<keyid>_<secret>``) is the ONLY time the secret exists
        in cleartext — store it; it cannot be recovered. Only the salted hash is persisted.
        Raises ``ValueError`` for an unknown scope (incl. the unissuable ``deploy:live``).
        """
        tenant_id = str(tenant_id)
        if self.get_tenant(tenant_id) is None:
            raise ValueError(f"unknown tenant: {tenant_id}")
        scope_list = list(dict.fromkeys(scopes or []))  # dedupe, preserve order
        bad = [s for s in scope_list if s not in VALID_SCOPES]
        if bad:
            raise ValueError(f"unissuable scope(s): {bad} (valid: {sorted(VALID_SCOPES)})")

        key_id = uuid.uuid4().hex
        secret = secrets.token_urlsafe(32)
        salt = secrets.token_hex(16)
        secret_hash = hash_secret(salt, secret)
        plaintext = f"{KEY_PREFIX}_{_env_tag()}_{key_id}_{secret}"

        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO api_keys "
                    "(key_id, tenant_id, secret_hash, salt, scopes, created_at, revoked) "
                    "VALUES (?, ?, ?, ?, ?, ?, 0)",
                    (key_id, tenant_id, secret_hash, salt, json.dumps(scope_list), _now()),
                )
        return plaintext, key_id

    def verify(self, key: str) -> dict[str, Any] | None:
        """Resolve a presented key to ``{tenant_id, scopes, key_id}`` or ``None``.

        Constant-time secret comparison; revoked keys never verify. A malformed key, an
        unknown ``<keyid>``, or a mismatched secret all return ``None`` (never raises) — the
        caller maps that to a 401.
        """
        if not key or not isinstance(key, str):
            return None
        # dmbg _ <env> _ <keyid> _ <secret>. The secret is base64url (token_urlsafe), which
        # may itself contain "_", so split only the first three separators and keep the rest
        # as the secret. The <keyid> is uuid4 hex (no "_"), so this is unambiguous.
        parts = key.split("_", 3)
        if len(parts) != 4 or parts[0] != KEY_PREFIX:
            return None
        _, _env, key_id, secret = parts
        if not key_id or not secret:
            return None

        row = self._db.conn.execute(
            "SELECT tenant_id, secret_hash, salt, scopes, revoked "
            "FROM api_keys WHERE key_id = ?",
            (key_id,),
        ).fetchone()
        if row is None or int(row["revoked"]) != 0:
            return None

        candidate = hash_secret(row["salt"], secret)
        if not hmac.compare_digest(candidate, row["secret_hash"]):
            return None

        return {
            "tenant_id": row["tenant_id"],
            "scopes": list(json.loads(row["scopes"])),
            "key_id": key_id,
        }

    def revoke_key(self, key_id: str) -> bool:
        """Soft-revoke a key by id (audit-preserving). Returns True if a row was flipped."""
        with self._db.write_lock:
            with self._db.conn as conn:
                cur = conn.execute(
                    "UPDATE api_keys SET revoked = 1 WHERE key_id = ? AND revoked = 0",
                    (str(key_id),),
                )
                return cur.rowcount > 0

    def list_keys(self, tenant_id: str) -> list[dict[str, Any]]:
        """List a tenant's keys (metadata only — never the secret)."""
        rows = self._db.conn.execute(
            "SELECT key_id, scopes, created_at, revoked FROM api_keys "
            "WHERE tenant_id = ? ORDER BY created_at ASC",
            (str(tenant_id),),
        ).fetchall()
        return [
            {
                "key_id": r["key_id"],
                "scopes": list(json.loads(r["scopes"])),
                "created_at": r["created_at"],
                "revoked": bool(r["revoked"]),
            }
            for r in rows
        ]
