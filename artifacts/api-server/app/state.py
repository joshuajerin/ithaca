"""In-memory session and watchlist state (Phase 1, no database).

Every per-session store is keyed by a ``(firm_id, session_id)`` tuple so two
firms can never read or clobber each other's in-memory sessions, history, DCF
models or alert rules/events — even if a session id were ever reused. The firm
is taken from the current request's tenant context. The watchlist is global by
design (shared default symbols), so it is intentionally not firm-scoped.
"""
from __future__ import annotations

import time
from threading import Lock
from typing import Dict, List, Tuple

from . import tenant

# (firmId, sessionId) -> list of panel dicts (the current dashboard for that session)
_sessions: Dict[Tuple[str, str], List[dict]] = {}
# (firmId, sessionId) -> last user query (light context)
_session_history: Dict[Tuple[str, str], List[dict]] = {}
# (firmId, sessionId) -> list of saved DCF model dicts ({name, symbol, assumptions, savedAt})
_dcf_models: Dict[Tuple[str, str], List[dict]] = {}
# (firmId, sessionId) -> list of trade-flow alert rule dicts
_alert_rules: Dict[Tuple[str, str], List[dict]] = {}
# (firmId, sessionId) -> list of fired alert event dicts (most recent last)
_alert_events: Dict[Tuple[str, str], List[dict]] = {}
# (firmId, sessionId) -> {"userId", "firmId"} owning identity (set once a
# logged-in user drives a session).
_session_owners: Dict[Tuple[str, str], dict] = {}

_watchlist: List[str] = ["NVDA", "XOM", "MSFT"]

_lock = Lock()


def _key(session_id: str) -> Tuple[str, str]:
    """Compose the firm-scoped store key for the current request's firm."""
    return (tenant.current_firm_id(), session_id)


def get_dashboard(session_id: str) -> List[dict]:
    with _lock:
        return list(_sessions.get(_key(session_id), []))


def set_dashboard(session_id: str, panels: List[dict]) -> None:
    with _lock:
        _sessions[_key(session_id)] = list(panels)


def update_panel(session_id: str, panel: dict) -> None:
    key = _key(session_id)
    with _lock:
        panels = _sessions.get(key, [])
        for i, p in enumerate(panels):
            if p.get("id") == panel.get("id"):
                panels[i] = panel
                break
        _sessions[key] = panels


def get_panel(session_id: str, panel_id: str) -> dict | None:
    with _lock:
        for p in _sessions.get(_key(session_id), []):
            if p.get("id") == panel_id:
                return dict(p)
    return None


def set_session_owner(session_id: str, user_id: str, firm_id: str) -> None:
    """Tag a session with the logged-in user/firm that drives it.

    Recorded once and not overwritten, so the first authenticated caller owns the
    session.
    """
    if not session_id or not user_id:
        return
    with _lock:
        _session_owners.setdefault(_key(session_id), {"userId": user_id, "firmId": firm_id})


def get_session_owner(session_id: str) -> dict | None:
    with _lock:
        owner = _session_owners.get(_key(session_id))
        return dict(owner) if owner else None


def get_history(session_id: str) -> List[dict]:
    with _lock:
        return list(_session_history.get(_key(session_id), []))


def append_history(session_id: str, role: str, content: str) -> None:
    with _lock:
        hist = _session_history.setdefault(_key(session_id), [])
        hist.append({"role": role, "content": content})
        # keep only the last few turns for light context
        if len(hist) > 8:
            del hist[: len(hist) - 8]


def list_dcf_models(session_id: str, symbol: str | None = None) -> List[dict]:
    """Return saved DCF models for a session, optionally filtered by symbol."""
    with _lock:
        models = list(_dcf_models.get(_key(session_id), []))
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
    key = _key(session_id)
    with _lock:
        models = _dcf_models.setdefault(key, [])
        # overwrite a model with the same name + symbol
        for i, m in enumerate(models):
            if m.get("name") == name and m.get("symbol") == sym:
                models[i] = entry
                break
        else:
            models.append(entry)
        result = [dict(m) for m in models if m.get("symbol") == sym]
    return result


def delete_dcf_model(session_id: str, name: str, symbol: str) -> List[dict]:
    """Delete a named DCF model and return the remaining list for that symbol."""
    sym = symbol.upper()
    key = _key(session_id)
    with _lock:
        models = _dcf_models.get(key, [])
        _dcf_models[key] = [
            m for m in models
            if not (m.get("name") == name and m.get("symbol") == sym)
        ]
        result = [dict(m) for m in _dcf_models[key] if m.get("symbol") == sym]
    return result


def get_watchlist() -> List[str]:
    with _lock:
        return list(_watchlist)


def add_watchlist(symbol: str) -> List[str]:
    with _lock:
        s = symbol.upper()
        if s not in _watchlist:
            _watchlist.append(s)
        return list(_watchlist)


def remove_watchlist(symbol: str) -> List[str]:
    with _lock:
        s = symbol.upper()
        if s in _watchlist:
            _watchlist.remove(s)
        return list(_watchlist)


# --------------------------- trade-flow alert rules --------------------------
def get_alert_rules(session_id: str) -> List[dict]:
    with _lock:
        return [dict(r) for r in _alert_rules.get(_key(session_id), [])]


def add_alert_rule(session_id: str, rule: dict) -> dict:
    with _lock:
        rules = _alert_rules.setdefault(_key(session_id), [])
        rules.append(rule)
        return dict(rule)


def remove_alert_rule(session_id: str, rule_id: str) -> List[dict]:
    key = _key(session_id)
    with _lock:
        rules = _alert_rules.get(key, [])
        _alert_rules[key] = [r for r in rules if r.get("id") != rule_id]
        return [dict(r) for r in _alert_rules[key]]


def get_alert_events(session_id: str) -> List[dict]:
    with _lock:
        return [dict(e) for e in _alert_events.get(_key(session_id), [])]


def add_alert_events(session_id: str, events: List[dict]) -> List[dict]:
    """Append new events, skipping any whose signature already fired. Returns the
    events that were actually added (the genuinely new ones)."""
    if not events:
        return []
    with _lock:
        existing = _alert_events.setdefault(_key(session_id), [])
        seen = {e.get("signature") for e in existing}
        added: List[dict] = []
        for ev in events:
            if ev.get("signature") in seen:
                continue
            existing.append(ev)
            seen.add(ev.get("signature"))
            added.append(dict(ev))
        # keep only the most recent 50 events per session
        if len(existing) > 50:
            del existing[: len(existing) - 50]
        return added


def clear_alert_events(session_id: str) -> None:
    with _lock:
        _alert_events[_key(session_id)] = []
