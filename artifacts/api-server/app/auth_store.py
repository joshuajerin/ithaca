"""Persistence for firms, users, and durable auth sessions.

Identity must survive restarts, so the source of truth is Postgres (idempotent
``CREATE TABLE IF NOT EXISTS`` here, mirroring the strategy/dashboard stores —
there is no Drizzle migration run; the Drizzle schema files document the shape).
When no database is configured the store degrades to in-process dicts so the
feature still works in a stateless environment (it just will not persist across
a restart).

Stored secrets are limited to a PBKDF2 password hash + salt and a SHA-256 hash
of each session token. Raw passwords and raw session tokens are never stored.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from . import db

log = logging.getLogger(__name__)

_schema_ready = False
_schema_lock = threading.Lock()

# In-memory fallbacks (only used when no DB is available).
_firms: Dict[str, dict] = {}
_users: Dict[str, dict] = {}
_sessions: Dict[str, dict] = {}
_mem_lock = threading.Lock()


def _ensure_schema() -> None:
    global _schema_ready
    if _schema_ready or not db.db_available():
        return
    with _schema_lock:
        if _schema_ready:
            return
        try:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS firms (
                    id text PRIMARY KEY,
                    name text NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id text PRIMARY KEY,
                    firm_id text NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
                    email text NOT NULL UNIQUE,
                    name text NOT NULL,
                    role text NOT NULL DEFAULT 'trader',
                    password_hash text NOT NULL,
                    password_salt text NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash text PRIMARY KEY,
                    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    expires_at timestamptz NOT NULL
                )
                """
            )
            _schema_ready = True
        except Exception as exc:  # noqa: BLE001
            log.warning("auth schema ensure failed: %s", exc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v) -> Optional[str]:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else v


# ------------------------------- firms ---------------------------------------
def create_firm(name: str) -> dict:
    _ensure_schema()
    firm_id = uuid.uuid4().hex[:16]
    name = (name or "").strip()
    if db.db_available():
        try:
            db.execute(
                "INSERT INTO firms (id, name) VALUES (%s, %s)",
                (firm_id, name),
            )
            return {"id": firm_id, "name": name}
        except Exception as exc:  # noqa: BLE001
            log.warning("create_firm DB error: %s", exc)
    with _mem_lock:
        _firms[firm_id] = {"id": firm_id, "name": name, "createdAt": _iso(_now())}
    return {"id": firm_id, "name": name}


def get_firm(firm_id: str) -> Optional[dict]:
    _ensure_schema()
    if not firm_id:
        return None
    if db.db_available():
        try:
            row = db.query_one("SELECT id, name FROM firms WHERE id = %s", (firm_id,))
            return {"id": row["id"], "name": row["name"]} if row else None
        except Exception as exc:  # noqa: BLE001
            log.warning("get_firm DB error: %s", exc)
    with _mem_lock:
        rec = _firms.get(firm_id)
        return {"id": rec["id"], "name": rec["name"]} if rec else None


# ------------------------------- users ---------------------------------------
def _user_view(row: dict) -> dict:
    return {
        "id": row["id"],
        "firmId": row.get("firm_id") or row.get("firmId"),
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "passwordHash": row.get("password_hash") or row.get("passwordHash"),
        "passwordSalt": row.get("password_salt") or row.get("passwordSalt"),
    }


def create_user(
    firm_id: str,
    email: str,
    name: str,
    role: str,
    password_hash: str,
    password_salt: str,
) -> dict:
    _ensure_schema()
    user_id = uuid.uuid4().hex[:16]
    if db.db_available():
        try:
            db.execute(
                """
                INSERT INTO users
                    (id, firm_id, email, name, role, password_hash, password_salt)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, firm_id, email, name, role, password_hash, password_salt),
            )
            return _user_view(
                {
                    "id": user_id,
                    "firm_id": firm_id,
                    "email": email,
                    "name": name,
                    "role": role,
                    "password_hash": password_hash,
                    "password_salt": password_salt,
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("create_user DB error: %s", exc)
            raise
    with _mem_lock:
        _users[user_id] = {
            "id": user_id,
            "firm_id": firm_id,
            "email": email,
            "name": name,
            "role": role,
            "password_hash": password_hash,
            "password_salt": password_salt,
        }
        return _user_view(_users[user_id])


def get_user_by_email(email: str) -> Optional[dict]:
    _ensure_schema()
    if not email:
        return None
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT id, firm_id, email, name, role, password_hash, password_salt "
                "FROM users WHERE email = %s",
                (email,),
            )
            return _user_view(row) if row else None
        except Exception as exc:  # noqa: BLE001
            log.warning("get_user_by_email DB error: %s", exc)
    with _mem_lock:
        for rec in _users.values():
            if rec["email"] == email:
                return _user_view(rec)
    return None


def get_user_by_id(user_id: str) -> Optional[dict]:
    _ensure_schema()
    if not user_id:
        return None
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT id, firm_id, email, name, role, password_hash, password_salt "
                "FROM users WHERE id = %s",
                (user_id,),
            )
            return _user_view(row) if row else None
        except Exception as exc:  # noqa: BLE001
            log.warning("get_user_by_id DB error: %s", exc)
    with _mem_lock:
        rec = _users.get(user_id)
        return _user_view(rec) if rec else None


def email_exists(email: str) -> bool:
    return get_user_by_email(email) is not None


# ------------------------------ sessions -------------------------------------
def create_session(token_hash: str, user_id: str, ttl_seconds: int) -> None:
    _ensure_schema()
    expires_at = _now() + timedelta(seconds=ttl_seconds)
    if db.db_available():
        try:
            db.execute(
                "INSERT INTO auth_sessions (token_hash, user_id, expires_at) "
                "VALUES (%s, %s, %s)",
                (token_hash, user_id, expires_at),
            )
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("create_session DB error: %s", exc)
    with _mem_lock:
        _sessions[token_hash] = {
            "token_hash": token_hash,
            "user_id": user_id,
            "expires_at": expires_at,
        }


def get_session_user_id(token_hash: str) -> Optional[str]:
    """Return the user id for a live (non-expired) session, else None.

    Expired sessions are deleted lazily so the table self-cleans on access.
    """
    _ensure_schema()
    if not token_hash:
        return None
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT user_id, expires_at FROM auth_sessions WHERE token_hash = %s",
                (token_hash,),
            )
            if not row:
                return None
            if row["expires_at"] <= _now():
                delete_session(token_hash)
                return None
            return row["user_id"]
        except Exception as exc:  # noqa: BLE001
            log.warning("get_session_user_id DB error: %s", exc)
            return None
    with _mem_lock:
        rec = _sessions.get(token_hash)
        if not rec:
            return None
        if rec["expires_at"] <= _now():
            _sessions.pop(token_hash, None)
            return None
        return rec["user_id"]


def delete_session(token_hash: str) -> None:
    _ensure_schema()
    if not token_hash:
        return
    if db.db_available():
        try:
            db.execute("DELETE FROM auth_sessions WHERE token_hash = %s", (token_hash,))
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("delete_session DB error: %s", exc)
    with _mem_lock:
        _sessions.pop(token_hash, None)
