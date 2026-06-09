"""In-memory session and watchlist state (Phase 1, no database)."""
from __future__ import annotations

import time
from threading import Lock
from typing import Dict, List

# sessionId -> list of panel dicts (the current dashboard for that session)
_sessions: Dict[str, List[dict]] = {}
# sessionId -> last user query (light context)
_session_history: Dict[str, List[dict]] = {}
# sessionId -> list of saved DCF model dicts ({name, symbol, assumptions, savedAt})
_dcf_models: Dict[str, List[dict]] = {}
# sessionId -> list of trade-flow alert rule dicts
_alert_rules: Dict[str, List[dict]] = {}
# sessionId -> list of fired alert event dicts (most recent last)
_alert_events: Dict[str, List[dict]] = {}
# sessionId -> {"userId", "firmId"} owning identity (set once a logged-in user
# drives a session). Foundation hook for the separate firm-isolation task.
_session_owners: Dict[str, dict] = {}

_watchlist: List[str] = ["NVDA", "XOM", "MSFT"]

_lock = Lock()


def get_dashboard(session_id: str) -> List[dict]:
    with _lock:
        return list(_sessions.get(session_id, []))


def set_dashboard(session_id: str, panels: List[dict]) -> None:
    with _lock:
        _sessions[session_id] = list(panels)


def update_panel(session_id: str, panel: dict) -> None:
    with _lock:
        panels = _sessions.get(session_id, [])
        for i, p in enumerate(panels):
            if p.get("id") == panel.get("id"):
                panels[i] = panel
                break
        _sessions[session_id] = panels


def get_panel(session_id: str, panel_id: str) -> dict | None:
    with _lock:
        for p in _sessions.get(session_id, []):
            if p.get("id") == panel_id:
                return dict(p)
    return None


def set_session_owner(session_id: str, user_id: str, firm_id: str) -> None:
    """Tag a session with the logged-in user/firm that drives it.

    Recorded once and not overwritten, so the first authenticated caller owns the
    session. This is the hook the separate firm-isolation task builds on; it does
    not itself gate access.
    """
    if not session_id or not user_id:
        return
    with _lock:
        _session_owners.setdefault(session_id, {"userId": user_id, "firmId": firm_id})


def get_session_owner(session_id: str) -> dict | None:
    with _lock:
        owner = _session_owners.get(session_id)
        return dict(owner) if owner else None


def get_history(session_id: str) -> List[dict]:
    with _lock:
        return list(_session_history.get(session_id, []))


def append_history(session_id: str, role: str, content: str) -> None:
    with _lock:
        hist = _session_history.setdefault(session_id, [])
        hist.append({"role": role, "content": content})
        # keep only the last few turns for light context
        if len(hist) > 8:
            del hist[: len(hist) - 8]


def list_dcf_models(session_id: str, symbol: str | None = None) -> List[dict]:
    """Return saved DCF models for a session, optionally filtered by symbol."""
    with _lock:
        models = list(_dcf_models.get(session_id, []))
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
    with _lock:
        models = _dcf_models.setdefault(session_id, [])
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
    with _lock:
        models = _dcf_models.get(session_id, [])
        _dcf_models[session_id] = [
            m for m in models
            if not (m.get("name") == name and m.get("symbol") == sym)
        ]
        result = [dict(m) for m in _dcf_models[session_id] if m.get("symbol") == sym]
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
        return [dict(r) for r in _alert_rules.get(session_id, [])]


def add_alert_rule(session_id: str, rule: dict) -> dict:
    with _lock:
        rules = _alert_rules.setdefault(session_id, [])
        rules.append(rule)
        return dict(rule)


def remove_alert_rule(session_id: str, rule_id: str) -> List[dict]:
    with _lock:
        rules = _alert_rules.get(session_id, [])
        _alert_rules[session_id] = [r for r in rules if r.get("id") != rule_id]
        return [dict(r) for r in _alert_rules[session_id]]


def get_alert_events(session_id: str) -> List[dict]:
    with _lock:
        return [dict(e) for e in _alert_events.get(session_id, [])]


def add_alert_events(session_id: str, events: List[dict]) -> List[dict]:
    """Append new events, skipping any whose signature already fired. Returns the
    events that were actually added (the genuinely new ones)."""
    if not events:
        return []
    with _lock:
        existing = _alert_events.setdefault(session_id, [])
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
        _alert_events[session_id] = []
