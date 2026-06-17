"""Durable, firm-scoped session state for the terminal backend.

Active dashboards, conversation history, saved DCF models and trade-flow alert
rules/events are the per-session "working state" of the app. They live in
Postgres so they survive a server restart and are visible to *every* app
instance — which is what lets the API run statelessly behind the platform and
scale horizontally without sessions breaking.

Each record is keyed by ``(firm_id, session_id, kind)`` so two firms can never
read or clobber each other's state (the firm comes from the request's tenant
context) and each concern (dashboard / history / dcf / alerts / owner) is an
independent row that can be read or mutated on its own. Read-modify-write
operations take a row lock (``SELECT ... FOR UPDATE``) so concurrent instances
serialize correctly instead of racing.

When no database is configured the store degrades to an in-process dict — the
feature still works, it just will not persist across a restart or be shared
across instances. This mirrors the DB-first / in-memory-fallback pattern used by
the other stores in this app.

The watchlist is global by design (shared default symbols), so it is stored
under a fixed sentinel key rather than per firm/session.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import db, tenant

log = logging.getLogger(__name__)

# Record "kinds" — one row per (firm, session, kind).
_DASHBOARD = "dashboard"
_HISTORY = "history"
_DCF = "dcf"
_ALERT_RULES = "alert_rules"
_ALERT_EVENTS = "alert_events"
_OWNER = "owner"
_WATCHLIST = "watchlist"

# Sentinel key for the single global watchlist row (not firm-scoped).
_GLOBAL = "__global__"
DEFAULT_WATCHLIST: List[str] = ["NVDA", "XOM", "MSFT"]

_MAX_HISTORY = 8   # keep only the last few turns for light context
_MAX_EVENTS = 50   # keep only the most recent events per session

_schema_ready = False
_schema_lock = threading.Lock()

# In-memory fallback (only used when no DB is available): (firm, session, kind) -> data
_mem: Dict[Tuple[str, str, str], Any] = {}
_lock = threading.Lock()


def _fid() -> str:
    """The firm the current request acts on behalf of (from tenant context)."""
    return tenant.current_firm_id()


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
                CREATE TABLE IF NOT EXISTS session_state (
                    firm_id text NOT NULL DEFAULT 'default',
                    session_id text NOT NULL,
                    kind text NOT NULL,
                    data jsonb NOT NULL,
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (firm_id, session_id, kind)
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS session_state_updated_idx "
                "ON session_state (updated_at)"
            )
            _schema_ready = True
        except Exception as exc:  # noqa: BLE001
            log.warning("session_state schema ensure failed: %s", exc)


def _copy(value: Any) -> Any:
    """Deep-copy a JSON-able value so callers/stores never alias stored data."""
    if value is None:
        return None
    return json.loads(json.dumps(value))


def _read(kind: str, fid: str, sid: str, default: Any) -> Any:
    """Return the stored value for one (firm, session, kind), or a copy of ``default``."""
    _ensure_schema()
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT data FROM session_state "
                "WHERE firm_id = %s AND session_id = %s AND kind = %s",
                (fid, sid, kind),
            )
            return row["data"] if row is not None else _copy(default)
        except Exception as exc:  # noqa: BLE001
            log.warning("session_state read (%s) DB error: %s", kind, exc)
    with _lock:
        val = _mem.get((fid, sid, kind))
        return _copy(val) if val is not None else _copy(default)


def _write(kind: str, fid: str, sid: str, value: Any) -> None:
    """Full-replace the stored value for one (firm, session, kind)."""
    _ensure_schema()
    if db.db_available():
        try:
            db.execute(
                """
                INSERT INTO session_state (firm_id, session_id, kind, data, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, now())
                ON CONFLICT (firm_id, session_id, kind)
                DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                """,
                (fid, sid, kind, json.dumps(value)),
            )
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("session_state write (%s) DB error: %s", kind, exc)
    with _lock:
        _mem[(fid, sid, kind)] = _copy(value)


def _mutate(
    kind: str,
    fid: str,
    sid: str,
    default: Any,
    fn: Callable[[Any], Tuple[Any, Any]],
) -> Any:
    """Atomic read-modify-write under a row lock.

    ``fn(current)`` receives the current value (or a copy of ``default``) and
    returns ``(new_value, result)``; ``new_value`` is persisted and ``result``
    is returned to the caller. The DB path holds ``SELECT ... FOR UPDATE`` for
    the duration so concurrent instances serialize on the same row.
    """
    _ensure_schema()
    if db.db_available():
        try:
            with db.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT data FROM session_state "
                        "WHERE firm_id = %s AND session_id = %s AND kind = %s "
                        "FOR UPDATE",
                        (fid, sid, kind),
                    )
                    row = cur.fetchone()
                    current = row["data"] if row is not None else _copy(default)
                    new_value, result = fn(current)
                    cur.execute(
                        """
                        INSERT INTO session_state (firm_id, session_id, kind, data, updated_at)
                        VALUES (%s, %s, %s, %s::jsonb, now())
                        ON CONFLICT (firm_id, session_id, kind)
                        DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                        """,
                        (fid, sid, kind, json.dumps(new_value)),
                    )
                conn.commit()
            return result
        except Exception as exc:  # noqa: BLE001
            log.warning("session_state mutate (%s) DB error: %s", kind, exc)
    with _lock:
        stored = _mem.get((fid, sid, kind))
        current = _copy(stored) if stored is not None else _copy(default)
        new_value, result = fn(current)
        _mem[(fid, sid, kind)] = _copy(new_value)
    return result


# ------------------------------- dashboard -------------------------------
def get_dashboard(session_id: str) -> List[dict]:
    return _read(_DASHBOARD, _fid(), session_id, [])


def set_dashboard(session_id: str, panels: List[dict]) -> None:
    _write(_DASHBOARD, _fid(), session_id, list(panels))


def update_panel(session_id: str, panel: dict) -> None:
    """Replace the panel with the same id in place (no-op if not present)."""
    def fn(panels):
        panels = list(panels or [])
        for i, p in enumerate(panels):
            if p.get("id") == panel.get("id"):
                panels[i] = panel
                break
        return panels, None

    _mutate(_DASHBOARD, _fid(), session_id, [], fn)


def get_panel(session_id: str, panel_id: str) -> dict | None:
    for p in _read(_DASHBOARD, _fid(), session_id, []):
        if p.get("id") == panel_id:
            return dict(p)
    return None


# ---------------------------- session ownership ---------------------------
def set_session_owner(session_id: str, user_id: str, firm_id: str) -> None:
    """Tag a session with the logged-in user/firm that drives it.

    Recorded once and not overwritten, so the first authenticated caller owns the
    session.
    """
    if not session_id or not user_id:
        return

    def fn(current):
        if current:  # already owned — set once
            return current, None
        return {"userId": user_id, "firmId": firm_id}, None

    _mutate(_OWNER, _fid(), session_id, None, fn)


def get_session_owner(session_id: str) -> dict | None:
    owner = _read(_OWNER, _fid(), session_id, None)
    return dict(owner) if owner else None


# -------------------------------- history --------------------------------
def get_history(session_id: str) -> List[dict]:
    return _read(_HISTORY, _fid(), session_id, [])


def append_history(session_id: str, role: str, content: str) -> None:
    def fn(hist):
        hist = list(hist or [])
        hist.append({"role": role, "content": content})
        if len(hist) > _MAX_HISTORY:
            del hist[: len(hist) - _MAX_HISTORY]
        return hist, None

    _mutate(_HISTORY, _fid(), session_id, [], fn)


# ------------------------------- DCF models -------------------------------
def list_dcf_models(session_id: str, symbol: str | None = None) -> List[dict]:
    """Return saved DCF models for a session, optionally filtered by symbol."""
    models = _read(_DCF, _fid(), session_id, [])
    if symbol:
        sym = symbol.upper()
        models = [m for m in models if m.get("symbol") == sym]
    return models


def save_dcf_model(session_id: str, name: str, symbol: str, assumptions: dict) -> List[dict]:
    """Save (or overwrite) a named DCF model and return the list for that symbol."""
    sym = symbol.upper()
    entry = {
        "name": name,
        "symbol": sym,
        "assumptions": dict(assumptions),
        "savedAt": time.time(),
    }

    def fn(models):
        models = list(models or [])
        for i, m in enumerate(models):
            if m.get("name") == name and m.get("symbol") == sym:
                models[i] = entry
                break
        else:
            models.append(entry)
        result = [dict(m) for m in models if m.get("symbol") == sym]
        return models, result

    return _mutate(_DCF, _fid(), session_id, [], fn)


def delete_dcf_model(session_id: str, name: str, symbol: str) -> List[dict]:
    """Delete a named DCF model and return the remaining list for that symbol."""
    sym = symbol.upper()

    def fn(models):
        models = [
            m for m in (models or [])
            if not (m.get("name") == name and m.get("symbol") == sym)
        ]
        result = [dict(m) for m in models if m.get("symbol") == sym]
        return models, result

    return _mutate(_DCF, _fid(), session_id, [], fn)


# ------------------------------- watchlist --------------------------------
def get_watchlist() -> List[str]:
    return _read(_WATCHLIST, _GLOBAL, _GLOBAL, list(DEFAULT_WATCHLIST))


def add_watchlist(symbol: str) -> List[str]:
    s = symbol.upper()

    def fn(wl):
        wl = list(wl or DEFAULT_WATCHLIST)
        if s not in wl:
            wl.append(s)
        return wl, list(wl)

    return _mutate(_WATCHLIST, _GLOBAL, _GLOBAL, list(DEFAULT_WATCHLIST), fn)


def remove_watchlist(symbol: str) -> List[str]:
    s = symbol.upper()

    def fn(wl):
        wl = [x for x in (wl or DEFAULT_WATCHLIST) if x != s]
        return wl, list(wl)

    return _mutate(_WATCHLIST, _GLOBAL, _GLOBAL, list(DEFAULT_WATCHLIST), fn)


# --------------------------- trade-flow alert rules --------------------------
def get_alert_rules(session_id: str) -> List[dict]:
    return [dict(r) for r in _read(_ALERT_RULES, _fid(), session_id, [])]


def add_alert_rule(session_id: str, rule: dict) -> dict:
    def fn(rules):
        rules = list(rules or [])
        rules.append(rule)
        return rules, dict(rule)

    return _mutate(_ALERT_RULES, _fid(), session_id, [], fn)


def remove_alert_rule(session_id: str, rule_id: str) -> List[dict]:
    def fn(rules):
        rules = [r for r in (rules or []) if r.get("id") != rule_id]
        return rules, [dict(r) for r in rules]

    return _mutate(_ALERT_RULES, _fid(), session_id, [], fn)


def get_alert_events(session_id: str) -> List[dict]:
    return [dict(e) for e in _read(_ALERT_EVENTS, _fid(), session_id, [])]


def add_alert_events(session_id: str, events: List[dict]) -> List[dict]:
    """Append new events, skipping any whose signature already fired. Returns the
    events that were actually added (the genuinely new ones)."""
    if not events:
        return []

    def fn(existing):
        existing = list(existing or [])
        seen = {e.get("signature") for e in existing}
        added: List[dict] = []
        for ev in events:
            if ev.get("signature") in seen:
                continue
            existing.append(ev)
            seen.add(ev.get("signature"))
            added.append(dict(ev))
        if len(existing) > _MAX_EVENTS:
            del existing[: len(existing) - _MAX_EVENTS]
        return existing, added

    return _mutate(_ALERT_EVENTS, _fid(), session_id, [], fn)


def clear_alert_events(session_id: str) -> None:
    _write(_ALERT_EVENTS, _fid(), session_id, [])


def reset_for_tests() -> None:
    """Clear the in-memory fallback store (test helper)."""
    with _lock:
        _mem.clear()
