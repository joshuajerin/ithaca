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
_invitations: Dict[str, dict] = {}
_mem_lock = threading.Lock()

# Billing groundwork: a per-firm plan with a seat allowance. Read-only in the
# product for now (no payment processing) — the admin console just displays it.
DEFAULT_PLAN = "starter"
DEFAULT_SEATS = 5
# How long a pending invitation stays acceptable before it lapses.
INVITE_TTL_DAYS = 14


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
            # Deactivation flag: a deactivated user keeps their row (and history)
            # but can no longer authenticate. Added idempotently so existing rows
            # default to active.
            db.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true"
            )
            # Billing groundwork on the firm: a named plan + seat allowance.
            db.execute(
                "ALTER TABLE firms ADD COLUMN IF NOT EXISTS plan text NOT NULL DEFAULT 'starter'"
            )
            db.execute(
                "ALTER TABLE firms ADD COLUMN IF NOT EXISTS seats integer NOT NULL DEFAULT 5"
            )
            # Pending user invitations. Only a SHA-256 hash of the invite token is
            # stored (mirroring sessions), so a DB leak never exposes a usable link.
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS invitations (
                    id text PRIMARY KEY,
                    firm_id text NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
                    email text NOT NULL,
                    name text,
                    role text NOT NULL DEFAULT 'trader',
                    token_hash text NOT NULL UNIQUE,
                    status text NOT NULL DEFAULT 'pending',
                    created_at timestamptz NOT NULL DEFAULT now(),
                    expires_at timestamptz NOT NULL,
                    accepted_at timestamptz
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS invitations_firm_idx ON invitations (firm_id, status)"
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
def _firm_view(rec: dict) -> dict:
    plan = rec.get("plan") or DEFAULT_PLAN
    seats = rec.get("seats")
    return {
        "id": rec["id"],
        "name": rec["name"],
        "plan": plan,
        "seats": int(seats) if seats is not None else DEFAULT_SEATS,
    }


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
            return get_firm(firm_id) or {"id": firm_id, "name": name, "plan": DEFAULT_PLAN, "seats": DEFAULT_SEATS}
        except Exception as exc:  # noqa: BLE001
            log.warning("create_firm DB error: %s", exc)
    with _mem_lock:
        _firms[firm_id] = {
            "id": firm_id, "name": name, "plan": DEFAULT_PLAN, "seats": DEFAULT_SEATS,
            "createdAt": _iso(_now()),
        }
        return _firm_view(_firms[firm_id])


def get_firm(firm_id: str) -> Optional[dict]:
    _ensure_schema()
    if not firm_id:
        return None
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT id, name, plan, seats FROM firms WHERE id = %s", (firm_id,)
            )
            return _firm_view(row) if row else None
        except Exception as exc:  # noqa: BLE001
            log.warning("get_firm DB error: %s", exc)
    with _mem_lock:
        rec = _firms.get(firm_id)
        return _firm_view(rec) if rec else None


def update_firm(firm_id: str, name: str) -> Optional[dict]:
    """Rename a firm (admin-only firm-profile edit). Returns the updated view."""
    _ensure_schema()
    name = (name or "").strip()
    if not firm_id or not name:
        return get_firm(firm_id)
    if db.db_available():
        try:
            db.execute(
                "UPDATE firms SET name = %s, updated_at = now() WHERE id = %s",
                (name, firm_id),
            )
            return get_firm(firm_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("update_firm DB error: %s", exc)
    with _mem_lock:
        rec = _firms.get(firm_id)
        if not rec:
            return None
        rec["name"] = name
        return _firm_view(rec)


# ------------------------------- users ---------------------------------------
def _user_view(row: dict) -> dict:
    return {
        "id": row["id"],
        "firmId": row.get("firm_id") or row.get("firmId"),
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "active": True if row.get("active") is None else bool(row.get("active")),
        "createdAt": _iso(row.get("created_at")),
        "passwordHash": row.get("password_hash") or row.get("passwordHash"),
        "passwordSalt": row.get("password_salt") or row.get("passwordSalt"),
    }


def _user_public(row: dict) -> dict:
    """A user view safe to return to admins — no password material."""
    v = _user_view(row)
    return {
        "id": v["id"],
        "firmId": v["firmId"],
        "email": v["email"],
        "name": v["name"],
        "role": v["role"],
        "active": v["active"],
        "createdAt": v["createdAt"],
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
                    "active": True,
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
            "active": True,
            "created_at": _now(),
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
                "SELECT id, firm_id, email, name, role, active, created_at, "
                "password_hash, password_salt FROM users WHERE email = %s",
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
                "SELECT id, firm_id, email, name, role, active, created_at, "
                "password_hash, password_salt FROM users WHERE id = %s",
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


def delete_user_sessions(user_id: str) -> None:
    """Revoke every live session for a user (used when deactivating/removing)."""
    _ensure_schema()
    if not user_id:
        return
    if db.db_available():
        try:
            db.execute("DELETE FROM auth_sessions WHERE user_id = %s", (user_id,))
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("delete_user_sessions DB error: %s", exc)
    with _mem_lock:
        for tok in [t for t, r in _sessions.items() if r["user_id"] == user_id]:
            _sessions.pop(tok, None)


# --------------------------- admin: user management --------------------------
def list_users(firm_id: str) -> list[dict]:
    """Return all users in a firm (admin-safe view, no password material)."""
    _ensure_schema()
    if not firm_id:
        return []
    if db.db_available():
        try:
            rows = db.query(
                "SELECT id, firm_id, email, name, role, active, created_at "
                "FROM users WHERE firm_id = %s ORDER BY created_at ASC, email ASC",
                (firm_id,),
            )
            return [_user_public(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.warning("list_users DB error: %s", exc)
    with _mem_lock:
        recs = [r for r in _users.values() if r["firm_id"] == firm_id]
    recs.sort(key=lambda r: (str(r.get("created_at") or ""), r.get("email") or ""))
    return [_user_public(r) for r in recs]


def count_active_admins(firm_id: str) -> int:
    """How many active admins a firm has — used to protect the last admin."""
    _ensure_schema()
    if not firm_id:
        return 0
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT count(*) AS n FROM users "
                "WHERE firm_id = %s AND role = 'admin' AND active = true",
                (firm_id,),
            )
            return int(row["n"]) if row else 0
        except Exception as exc:  # noqa: BLE001
            log.warning("count_active_admins DB error: %s", exc)
    with _mem_lock:
        return sum(
            1
            for r in _users.values()
            if r["firm_id"] == firm_id
            and r["role"] == "admin"
            and (r.get("active") in (True, None))
        )


def update_user_role(user_id: str, role: str) -> Optional[dict]:
    _ensure_schema()
    if not user_id:
        return None
    if db.db_available():
        try:
            db.execute(
                "UPDATE users SET role = %s, updated_at = now() WHERE id = %s",
                (role, user_id),
            )
            return get_user_by_id(user_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("update_user_role DB error: %s", exc)
    with _mem_lock:
        rec = _users.get(user_id)
        if not rec:
            return None
        rec["role"] = role
        return _user_view(rec)


def set_user_active(user_id: str, active: bool) -> Optional[dict]:
    _ensure_schema()
    if not user_id:
        return None
    if db.db_available():
        try:
            db.execute(
                "UPDATE users SET active = %s, updated_at = now() WHERE id = %s",
                (bool(active), user_id),
            )
            return get_user_by_id(user_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("set_user_active DB error: %s", exc)
    with _mem_lock:
        rec = _users.get(user_id)
        if not rec:
            return None
        rec["active"] = bool(active)
        return _user_view(rec)


def delete_user(user_id: str) -> None:
    _ensure_schema()
    if not user_id:
        return
    delete_user_sessions(user_id)
    if db.db_available():
        try:
            db.execute("DELETE FROM users WHERE id = %s", (user_id,))
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("delete_user DB error: %s", exc)
    with _mem_lock:
        _users.pop(user_id, None)


# ------------------------------ invitations ----------------------------------
def _invite_view(row: dict) -> dict:
    return {
        "id": row["id"],
        "firmId": row.get("firm_id") or row.get("firmId"),
        "email": row["email"],
        "name": row.get("name"),
        "role": row["role"],
        "status": row["status"],
        "createdAt": _iso(row.get("created_at")),
        "expiresAt": _iso(row.get("expires_at")),
        "acceptedAt": _iso(row.get("accepted_at")),
    }


def create_invitation(
    firm_id: str, email: str, name: str, role: str, token_hash: str
) -> dict:
    _ensure_schema()
    invite_id = uuid.uuid4().hex[:16]
    created = _now()
    expires = created + timedelta(days=INVITE_TTL_DAYS)
    if db.db_available():
        try:
            db.execute(
                """
                INSERT INTO invitations
                    (id, firm_id, email, name, role, token_hash, status, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)
                """,
                (invite_id, firm_id, email, name, role, token_hash, expires),
            )
            row = db.query_one(
                "SELECT * FROM invitations WHERE id = %s", (invite_id,)
            )
            return _invite_view(row) if row else _invite_view(
                {
                    "id": invite_id, "firm_id": firm_id, "email": email, "name": name,
                    "role": role, "status": "pending", "created_at": created,
                    "expires_at": expires,
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("create_invitation DB error: %s", exc)
    with _mem_lock:
        _invitations[invite_id] = {
            "id": invite_id, "firm_id": firm_id, "email": email, "name": name,
            "role": role, "token_hash": token_hash, "status": "pending",
            "created_at": created, "expires_at": expires, "accepted_at": None,
        }
        return _invite_view(_invitations[invite_id])


def list_invitations(firm_id: str, status: Optional[str] = "pending") -> list[dict]:
    _ensure_schema()
    if not firm_id:
        return []
    if db.db_available():
        try:
            if status:
                rows = db.query(
                    "SELECT * FROM invitations WHERE firm_id = %s AND status = %s "
                    "ORDER BY created_at DESC",
                    (firm_id, status),
                )
            else:
                rows = db.query(
                    "SELECT * FROM invitations WHERE firm_id = %s "
                    "ORDER BY created_at DESC",
                    (firm_id,),
                )
            return [_invite_view(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.warning("list_invitations DB error: %s", exc)
    with _mem_lock:
        recs = [
            r
            for r in _invitations.values()
            if r["firm_id"] == firm_id and (status is None or r["status"] == status)
        ]
    recs.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return [_invite_view(r) for r in recs]


def get_invitation_by_token_hash(token_hash: str) -> Optional[dict]:
    """Return the FULL invitation record (incl. firm_id) for a token hash."""
    _ensure_schema()
    if not token_hash:
        return None
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT * FROM invitations WHERE token_hash = %s", (token_hash,)
            )
            return _invite_view(row) if row else None
        except Exception as exc:  # noqa: BLE001
            log.warning("get_invitation_by_token_hash DB error: %s", exc)
    with _mem_lock:
        for r in _invitations.values():
            if r.get("token_hash") == token_hash:
                return _invite_view(r)
    return None


def get_pending_invitation_by_email(firm_id: str, email: str) -> Optional[dict]:
    _ensure_schema()
    if not firm_id or not email:
        return None
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT * FROM invitations WHERE firm_id = %s AND email = %s "
                "AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
                (firm_id, email),
            )
            return _invite_view(row) if row else None
        except Exception as exc:  # noqa: BLE001
            log.warning("get_pending_invitation_by_email DB error: %s", exc)
    with _mem_lock:
        for r in sorted(
            _invitations.values(),
            key=lambda x: str(x.get("created_at") or ""),
            reverse=True,
        ):
            if (
                r["firm_id"] == firm_id
                and r["email"] == email
                and r["status"] == "pending"
            ):
                return _invite_view(r)
    return None


def revoke_invitation(invite_id: str, firm_id: str) -> bool:
    """Mark a pending invitation revoked. Firm-scoped. Returns True if changed."""
    _ensure_schema()
    if not invite_id or not firm_id:
        return False
    if db.db_available():
        try:
            db.execute(
                "UPDATE invitations SET status = 'revoked' "
                "WHERE id = %s AND firm_id = %s AND status = 'pending'",
                (invite_id, firm_id),
            )
            row = db.query_one(
                "SELECT status FROM invitations WHERE id = %s AND firm_id = %s",
                (invite_id, firm_id),
            )
            return bool(row and row["status"] == "revoked")
        except Exception as exc:  # noqa: BLE001
            log.warning("revoke_invitation DB error: %s", exc)
    with _mem_lock:
        rec = _invitations.get(invite_id)
        if rec and rec["firm_id"] == firm_id and rec["status"] == "pending":
            rec["status"] = "revoked"
            return True
    return False


def accept_invitation(invite_id: str) -> None:
    """Mark an invitation accepted (called after the user account is created)."""
    _ensure_schema()
    if not invite_id:
        return
    if db.db_available():
        try:
            db.execute(
                "UPDATE invitations SET status = 'accepted', accepted_at = now() "
                "WHERE id = %s",
                (invite_id,),
            )
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("accept_invitation DB error: %s", exc)
    with _mem_lock:
        rec = _invitations.get(invite_id)
        if rec:
            rec["status"] = "accepted"
            rec["accepted_at"] = _now()
