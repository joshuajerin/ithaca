"""Authentication primitives: password hashing, session tokens, identity.

Credentials are hashed with PBKDF2-HMAC-SHA256 (Python stdlib — no third-party
dependency, so nothing new to install and no package-firewall risk). Session
tokens are random, opaque strings; only their SHA-256 hash is ever stored, so a
database leak does not expose usable session tokens.

This module is pure logic — it does not touch the database. ``auth_store`` owns
persistence and ``main`` wires the FastAPI dependency that resolves an identity
from the session cookie.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

# Name of the httpOnly session cookie set on login/signup.
COOKIE_NAME = "at_session"
# How long a session stays valid (also the cookie max-age).
SESSION_TTL_DAYS = 30
SESSION_TTL_SECONDS = SESSION_TTL_DAYS * 24 * 60 * 60

# Roles a user can hold. Enforcement of what each may do is a separate task —
# here we only define and persist the role on the user.
ROLES = ("admin", "trader", "analyst", "read-only")
DEFAULT_ROLE = "trader"

_PBKDF2_ALGO = "sha256"
_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16


def hash_password(password: str) -> tuple[str, str]:
    """Return ``(hash_hex, salt_hex)`` for a plaintext password."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        _PBKDF2_ALGO, password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return digest.hex(), salt.hex()


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    """Constant-time check of a plaintext password against a stored hash+salt."""
    if not hash_hex or not salt_hex:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        _PBKDF2_ALGO, password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(digest.hex(), hash_hex)


def new_session_token() -> str:
    """A fresh opaque session token to hand to the browser (never stored raw)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 of a session token — this is what we persist and look up by."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def valid_role(role: str | None) -> str:
    role = (role or "").strip().lower()
    return role if role in ROLES else DEFAULT_ROLE


@dataclass(frozen=True)
class Identity:
    """The verified caller resolved from a session cookie."""

    user_id: str
    firm_id: str
    role: str
    name: str
    email: str
    firm_name: str

    def to_payload(self) -> dict:
        """Shape returned to the frontend for the current user."""
        return {
            "user": {
                "id": self.user_id,
                "name": self.name,
                "email": self.email,
                "role": self.role,
            },
            "firm": {"id": self.firm_id, "name": self.firm_name},
        }
