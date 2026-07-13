"""User accounts, OAuth links, and session management.

Three account paths:
1. Email + password  — pbkdf2_hmac (sha256, 260k iterations). Argon2 would be
   better but requires a C extension; pbkdf2 is solid stdlib.
2. OAuth (Google/GitHub) — upsert by (provider, provider_id); auto-creates a
   tenant-owning user on first sign-in.
3. Linked — an existing email+password user can also link OAuth providers.

Sessions are signed HMAC-SHA256 JWTs (header.payload.sig, base64url). The secret
key is DOOMBERG_SESSION_SECRET env var; a random fallback is used when unset
(tests pass; restarts invalidate sessions — set the env var in prod).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from .db import Db
from .db_scope import system_scoped_store

__all__ = ["UserStore", "SessionError"]

_PBKDF2_ITERATIONS = 260_000
_SESSION_DAYS = 30


class SessionError(ValueError):
    """Invalid, expired, or revoked session token."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


def _session_key() -> bytes:
    k = os.environ.get("DOOMBERG_SESSION_SECRET", "")
    if k:
        return k.encode()
    # ephemeral fallback — sessions invalidate on restart; fine for dev
    if not hasattr(_session_key, "_ephemeral"):
        _session_key._ephemeral = secrets.token_bytes(32)  # type: ignore[attr-defined]
    return _session_key._ephemeral  # type: ignore[attr-defined]


def _hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(32)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS)
    return h.hex(), salt


def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS)
    return hmac.compare_digest(h.hex(), stored_hash)


def _mint_jwt(payload: dict[str, Any]) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_session_key(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


def _verify_jwt(token: str) -> dict[str, Any]:
    try:
        header, body, sig = token.split(".")
    except ValueError:
        raise SessionError("malformed token")
    expected = _b64(hmac.new(_session_key(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise SessionError("invalid signature")
    payload = json.loads(_unb64(body))
    exp = payload.get("exp")
    if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
        raise SessionError("token expired")
    return payload


@system_scoped_store
class UserStore:
    def __init__(self, db: Db) -> None:
        self._db = db

    # ---- email+password --------------------------------------------------

    def signup(self, email: str, name: str, password: str, tenant_id: str) -> dict[str, Any]:
        """Create a new user with email+password. Raises ValueError on duplicate email."""
        email = email.strip().lower()
        if not email or "@" not in email:
            raise ValueError("invalid email")
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        user_id = str(uuid.uuid4())
        pw_hash, salt = _hash_password(password)
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
                if existing:
                    raise ValueError("email already registered")
                conn.execute(
                    "INSERT INTO users (id,email,name,tenant_id,password_hash,password_salt,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (user_id, email, name, tenant_id, pw_hash, salt, now, now),
                )
        return self._row(user_id)

    def signin(self, email: str, password: str) -> dict[str, Any]:
        """Verify credentials; returns the user dict or raises ValueError."""
        email = email.strip().lower()
        row = self._db.conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not row["password_hash"]:
            raise ValueError("invalid email or password")
        if not _verify_password(password, row["password_hash"], row["password_salt"]):
            raise ValueError("invalid email or password")
        return self._row_to_dict(row)

    # ---- OAuth upsert -----------------------------------------------------

    def oauth_upsert(
        self,
        provider: str,
        provider_id: str,
        email: str,
        name: str,
        avatar_url: str | None,
        tenant_id: str,
    ) -> dict[str, Any]:
        """Find or create a user from an OAuth callback. Returns the user dict."""
        email = email.strip().lower()
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                # Find by OAuth link first
                link = conn.execute(
                    "SELECT user_id FROM oauth_accounts WHERE provider=? AND provider_id=?",
                    (provider, provider_id),
                ).fetchone()
                if link:
                    user_id = link["user_id"]
                    # Refresh name/avatar
                    conn.execute(
                        "UPDATE oauth_accounts SET name=?, avatar_url=? WHERE provider=? AND provider_id=?",
                        (name, avatar_url, provider, provider_id),
                    )
                else:
                    # Find by email (account linking)
                    existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
                    if existing:
                        user_id = existing["id"]
                    else:
                        # New user
                        user_id = str(uuid.uuid4())
                        conn.execute(
                            "INSERT INTO users (id,email,name,avatar_url,tenant_id,created_at,updated_at) "
                            "VALUES (?,?,?,?,?,?,?)",
                            (user_id, email, name, avatar_url, tenant_id, now, now),
                        )
                    # Link the OAuth account
                    conn.execute(
                        "INSERT INTO oauth_accounts (user_id,provider,provider_id,email,name,avatar_url,linked_at) "
                        "VALUES (?,?,?,?,?,?,?) ON CONFLICT(provider,provider_id) DO UPDATE SET "
                        "name=excluded.name, avatar_url=excluded.avatar_url",
                        (user_id, provider, provider_id, email, name, avatar_url, now),
                    )
                # Update user avatar if provided
                if avatar_url:
                    conn.execute(
                        "UPDATE users SET avatar_url=?, updated_at=? WHERE id=?",
                        (avatar_url, now, user_id),
                    )
        return self._row(user_id)

    # ---- sessions --------------------------------------------------------

    def create_session(self, user_id: str) -> str:
        """Mint a signed JWT session token (30-day expiry) and persist the session."""
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=_SESSION_DAYS)
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO user_sessions (session_id,user_id,created_at,expires_at) VALUES (?,?,?,?)",
                    (session_id, user_id, now.isoformat(), expires.isoformat()),
                )
        payload = {
            "sid": session_id,
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
        }
        return _mint_jwt(payload)

    def verify_session(self, token: str) -> dict[str, Any]:
        """Verify the JWT and return the user dict; raises SessionError on failure."""
        payload = _verify_jwt(token)
        session_id = payload.get("sid")
        user_id = payload.get("sub")
        if not session_id or not user_id:
            raise SessionError("missing claims")
        row = self._db.conn.execute(
            "SELECT * FROM user_sessions WHERE session_id=? AND user_id=? AND revoked=0",
            (session_id, user_id),
        ).fetchone()
        if not row:
            raise SessionError("session not found or revoked")
        return self._row(user_id)

    def revoke_session(self, token: str) -> None:
        try:
            payload = _verify_jwt(token)
        except SessionError:
            return
        sid = payload.get("sid")
        if sid:
            with self._db.write_lock:
                with self._db.conn as conn:
                    conn.execute("UPDATE user_sessions SET revoked=1 WHERE session_id=?", (sid,))

    # ---- helpers ---------------------------------------------------------

    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def _row(self, user_id: str) -> dict[str, Any]:
        row = self._db.conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise ValueError(f"user not found: {user_id}")
        return self._row_to_dict(row)

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "avatar_url": row["avatar_url"],
            "tenant_id": row["tenant_id"],
            "created_at": row["created_at"],
        }
