"""Regression tests guarding the AI-down fallback paths.

Runnable two ways:
    python artifacts/api-server/tests/test_ai_fallback.py   # standalone
    pytest artifacts/api-server/tests/test_ai_fallback.py    # if pytest installed

The dashboard must keep working when the AI client is unavailable or slow. The
orchestrate path is expected to fall back to the keyword heuristic builder, and
the voice narration path is expected to fall back to its heuristic narrator. If
a future change removes a try/except, changes a timeout, or reorders the
fallback logic, these tests fail instead of silently reintroducing the
empty-dashboard / 502 bug (see Task #59).
"""
from __future__ import annotations

import os
import sys

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import agent, ai  # noqa: E402


class _patch:
    """Tiny context manager to set/restore an attribute (no pytest dep needed)."""

    def __init__(self, obj, name, value):
        self._obj = obj
        self._name = name
        self._value = value
        self._had = False
        self._orig = None

    def __enter__(self):
        self._had = hasattr(self._obj, self._name)
        if self._had:
            self._orig = getattr(self._obj, self._name)
        setattr(self._obj, self._name, self._value)
        return self

    def __exit__(self, *exc):
        if self._had:
            setattr(self._obj, self._name, self._orig)
        else:  # pragma: no cover - defensive
            delattr(self._obj, self._name)
        return False


def _boom_timeout(*_a, **_k):
    """Stand-in for a slow/unreachable upstream: raises like a client timeout."""
    raise TimeoutError("AI upstream timed out")


# --------------------------- orchestrate fallback ---------------------------
def test_orchestrate_builds_when_ai_unavailable():
    # AI reports itself unavailable (no creds / SDK) -> must still build via the
    # keyword heuristic, never an empty dashboard.
    with _patch(ai, "ai_available", lambda: False):
        result = agent.orchestrate("show me a price chart for NVDA", None)
    assert result["panels"], "expected a non-empty panels list when AI is unavailable"
    assert result["intent"] == "build"
    assert isinstance(result["summary"], str) and result["summary"].strip()


def test_orchestrate_builds_when_ai_call_times_out():
    # AI claims to be available, but every chat call hangs/raises (timeout). The
    # orchestrate path must catch the failure and fall back to the heuristic.
    with _patch(ai, "ai_available", lambda: True), _patch(ai, "chat", _boom_timeout):
        result = agent.orchestrate("show me a price chart for NVDA", None)
    assert result["panels"], "expected a non-empty panels list when the AI call times out"
    assert result["intent"] == "build"
    assert isinstance(result["summary"], str) and result["summary"].strip()


def test_orchestrate_voice_narration_present_when_ai_down():
    # The voice flow must still build panels AND attach narration when AI is down.
    with _patch(ai, "ai_available", lambda: False):
        result = agent.orchestrate("show me a price chart for NVDA", None, voice=True)
    assert result["panels"], "expected panels in the voice flow when AI is unavailable"
    narration = result.get("narration")
    assert narration, "expected non-empty narration when AI is unavailable"
    # Heuristic narration leads with a no-panel lead-in segment.
    assert narration[0]["panelId"] is None
    assert all(seg.get("text", "").strip() for seg in narration)


# --------------------------- narration fallback ---------------------------
def _sample_panels():
    return [
        {"id": "price_chart-aaaa1111", "type": "price_chart", "title": "NVDA Price"},
        {"id": "news-bbbb2222", "type": "news", "title": "NVDA News"},
    ]


def test_build_narration_falls_back_when_ai_unavailable():
    panels = _sample_panels()
    with _patch(ai, "ai_available", lambda: False):
        segs = agent._build_narration("show NVDA", "Here is NVDA.", panels)
    # One lead-in + one per panel.
    assert len(segs) == len(panels) + 1
    assert segs[0]["panelId"] is None
    assert {s["panelId"] for s in segs[1:]} == {p["id"] for p in panels}
    assert all(s["text"].strip() for s in segs)


def test_build_narration_falls_back_when_ai_call_times_out():
    panels = _sample_panels()
    # AI available but the narration call raises -> must degrade to the heuristic
    # narrator rather than returning nothing.
    with _patch(ai, "ai_available", lambda: True), _patch(ai, "chat", _boom_timeout):
        segs = agent._build_narration("show NVDA", "Here is NVDA.", panels)
    assert len(segs) == len(panels) + 1
    assert segs[0]["panelId"] is None
    assert all(s["text"].strip() for s in segs)


def test_narration_heuristic_handles_no_panels():
    # No panels -> still produce a single spoken lead-in (never an empty list).
    segs = agent._narration_heuristic("Nothing to show.", [])
    assert len(segs) == 1
    assert segs[0]["panelId"] is None
    assert segs[0]["text"].strip()


def _run_all():
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in funcs:
        fn()
        passed += 1
        print(f"  PASS {fn.__name__}")
    print(f"\n{passed}/{len(funcs)} ai-fallback tests passed")


if __name__ == "__main__":
    _run_all()
