"""In-memory session and watchlist state (Phase 1, no database)."""
from __future__ import annotations

from threading import Lock
from typing import Dict, List

# sessionId -> list of panel dicts (the current dashboard for that session)
_sessions: Dict[str, List[dict]] = {}
# sessionId -> last user query (light context)
_session_history: Dict[str, List[dict]] = {}

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
