"""Voice-loop backend tests: /speak audio payloads + /orchestrate narration.

Runnable two ways:
    python artifacts/api-server/tests/test_voice.py     # standalone
    pytest artifacts/api-server/tests/test_voice.py      # if pytest installed

Voice Mode is a stateful loop (listen -> orchestrate -> speak -> highlight). The
two backend halves are:
  * POST /orchestrate with voice=true must return ordered narration segments (a
    lead-in with no panel, then one segment per panel so the UI can highlight
    panels as they are described).
  * POST /speak must turn text into a base64 audio payload, and surface the
    documented error codes (400 empty text, 503 AI unavailable, 502 synth fail).

These were only verified by hand before. The AI path is mocked throughout so the
tests are deterministic and network-free: ``ai.ai_available`` is forced False to
exercise the heuristic narration builder, and ``ai.speak`` is stubbed to return
fixed bytes. The narration LLM parser is unit-tested with a stubbed ``ai.chat``.
"""
from __future__ import annotations

import base64
import os
import sys
from contextlib import contextmanager

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import agent, ai, worker  # noqa: E402
from app.main import app  # noqa: E402


@contextmanager
def _patched(obj, name, value):
    """Temporarily replace ``obj.name`` with ``value``, restoring it after."""
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)


async def _noop_worker(*_args, **_kwargs):
    return None


@contextmanager
def _client():
    """A TestClient with the background data worker neutralized.

    The staggered network-ingestion loops are irrelevant to the voice endpoints
    and would make the tests slow/flaky; endpoints answer from already-ingested
    rows or the deterministic mock fallback either way. The real lifespan still
    runs (dynamic-skill loading, worker wiring) so import-time breakage surfaces.
    """
    from fastapi.testclient import TestClient

    with _patched(worker, "start", _noop_worker), _patched(worker, "stop", _noop_worker):
        with TestClient(app) as client:
            yield client


# --------------------------- /speak audio payloads ---------------------------
def test_speak_returns_base64_audio_payload():
    """A valid /speak call returns the synthesized bytes as base64 + format."""
    fake_audio = b"\x00\x01FAKE-MP3-BYTES\xff"
    captured = {}

    def fake_speak(text, voice=None, fmt="mp3"):
        captured["text"] = text
        captured["voice"] = voice
        return fake_audio

    with _patched(ai, "ai_available", lambda: True), _patched(ai, "speak", fake_speak):
        with _client() as client:
            resp = client.post(
                "/api/speak", json={"text": "Hello from the desk.", "voice": "alloy"}
            )

    assert resp.status_code == 200, f"{resp.status_code}: {resp.text[:300]}"
    body = resp.json()
    assert body["format"] == "mp3", f"unexpected format: {body}"
    # The audio field must be the base64 encoding of exactly the synth bytes.
    assert body["audio"] == base64.b64encode(fake_audio).decode("ascii")
    assert base64.b64decode(body["audio"]) == fake_audio
    # The endpoint forwarded the (stripped) text and selected voice to the synth.
    assert captured["text"] == "Hello from the desk."
    assert captured["voice"] == "alloy"


def test_speak_rejects_empty_text():
    """Empty/whitespace text is a 400 before any synthesis is attempted."""
    called = {"n": 0}

    def fake_speak(*_a, **_k):
        called["n"] += 1
        return b"x"

    with _patched(ai, "ai_available", lambda: True), _patched(ai, "speak", fake_speak):
        with _client() as client:
            resp = client.post("/api/speak", json={"text": "   "})

    assert resp.status_code == 400, f"{resp.status_code}: {resp.text[:300]}"
    assert called["n"] == 0, "synthesis must not run for empty text"


def test_speak_unavailable_returns_503():
    """When the AI client is unavailable, /speak is a clean 503 (not a 500)."""
    with _patched(ai, "ai_available", lambda: False):
        with _client() as client:
            resp = client.post("/api/speak", json={"text": "Read this aloud."})

    assert resp.status_code == 503, f"{resp.status_code}: {resp.text[:300]}"


def test_speak_synth_failure_returns_502():
    """A synthesis exception is surfaced as a 502, not an unhandled crash."""
    def boom(*_a, **_k):
        raise RuntimeError("no audio returned")

    with _patched(ai, "ai_available", lambda: True), _patched(ai, "speak", boom):
        with _client() as client:
            resp = client.post("/api/speak", json={"text": "Read this aloud."})

    assert resp.status_code == 502, f"{resp.status_code}: {resp.text[:300]}"


# ----------------------- /orchestrate narration segments ---------------------
_STUB_PANELS = [
    {"id": "panel-price", "type": "price", "title": "NVDA Price", "status": "ok",
     "layout": {"x": 0, "y": 0, "w": 6, "h": 4}},
    {"id": "panel-news", "type": "news", "title": "AI / Semis News", "status": "ok",
     "layout": {"x": 6, "y": 0, "w": 6, "h": 4}},
]


def _stub_heuristic(*_args, **_kwargs):
    """Deterministic panel build, bypassing the real data/network path.

    The real heuristic composer fetches market data (DB/yfinance), which is slow
    and environment-fragile in tests. Stubbing it isolates the contract under
    test — that orchestrate(voice=true) attaches narration over whatever panels
    were built — while the genuine ``_build_narration`` still runs over them.
    """
    return [dict(p) for p in _STUB_PANELS], "Your NVIDIA desk is ready."


def test_orchestrate_voice_returns_narration_segments():
    """voice=true must attach ordered narration: a lead-in then one per panel.

    AI is forced unavailable so narration falls to the deterministic heuristic
    builder — the segment shape (lead-in with no panel, then one segment per
    built panel, each tied to a real panel id) is what the conductor relies on to
    highlight panels as it speaks. The panel composer is stubbed for determinism.
    """
    with _patched(ai, "ai_available", lambda: False), \
            _patched(agent, "_orchestrate_heuristic", _stub_heuristic):
        with _client() as client:
            resp = client.post(
                "/api/orchestrate",
                json={"query": "show me nvidia", "sessionId": "default", "voice": True},
            )

    assert resp.status_code == 200, f"{resp.status_code}: {resp.text[:300]}"
    body = resp.json()
    panels = body.get("panels") or []
    assert panels, f"voice build produced no panels: {body}"

    narration = body.get("narration")
    assert isinstance(narration, list) and narration, f"missing narration: {body}"

    # First segment is a spoken lead-in tied to no panel.
    lead = narration[0]
    assert lead.get("panelId") is None, f"lead-in must have no panelId: {lead}"
    assert lead.get("text"), "lead-in segment must have spoken text"

    # Remaining segments map onto real panels, in panel order.
    panel_ids = [p["id"] for p in panels]
    seg_panel_ids = [s.get("panelId") for s in narration[1:]]
    assert seg_panel_ids == panel_ids, (
        f"per-panel narration must follow panel order: {seg_panel_ids} vs {panel_ids}"
    )
    for seg in narration:
        assert seg.get("text", "").strip(), f"every segment needs spoken text: {seg}"


def test_orchestrate_without_voice_has_no_narration():
    """A non-voice build must NOT carry narration (it's voice-only)."""
    with _patched(ai, "ai_available", lambda: False), \
            _patched(agent, "_orchestrate_heuristic", _stub_heuristic):
        with _client() as client:
            resp = client.post(
                "/api/orchestrate",
                json={"query": "show me nvidia", "sessionId": "default"},
            )

    assert resp.status_code == 200, f"{resp.status_code}: {resp.text[:300]}"
    body = resp.json()
    assert body.get("narration") is None, f"narration leaked into non-voice build: {body}"


# ----------------- narration builders (unit, no HTTP) ------------------------
def test_narration_heuristic_shape():
    """The heuristic builder: lead-in (no panel) + one segment per panel id."""
    panels = [
        {"id": "p1", "type": "price", "title": "NVDA Price"},
        {"id": "p2", "type": "news", "title": "AI News"},
    ]
    segs = agent._narration_heuristic("Here is your desk.", panels)

    assert segs[0]["panelId"] is None and segs[0]["text"]
    assert [s["panelId"] for s in segs[1:]] == ["p1", "p2"]
    assert all(s["text"].strip() for s in segs)


def test_narration_llm_drops_invalid_ids_and_empty_text():
    """The LLM parser keeps only real panel ids and non-empty spoken text."""
    panels = [
        {"id": "p1", "type": "price", "title": "NVDA Price"},
        {"id": "p2", "type": "news", "title": "AI News"},
    ]
    payload = {
        "segments": [
            {"panelId": None, "text": "Here's your NVIDIA desk."},
            {"panelId": "p1", "text": "The price chart shows the move."},
            {"panelId": "ghost", "text": "References a panel that doesn't exist."},
            {"panelId": "p2", "text": "   "},  # empty after strip -> dropped
            {"panelId": "p2", "text": "And the latest news."},
        ]
    }

    class _Msg:
        content = __import__("json").dumps(payload)

    def fake_chat(_messages, **_kwargs):
        return _Msg()

    with _patched(ai, "ai_available", lambda: True), _patched(ai, "chat", fake_chat):
        segs = agent._narration_llm("nvidia", "summary", panels)

    # The empty-text segment is dropped; the ghost id is nulled (text kept).
    assert [(s["panelId"], s["text"]) for s in segs] == [
        (None, "Here's your NVIDIA desk."),
        ("p1", "The price chart shows the move."),
        (None, "References a panel that doesn't exist."),
        ("p2", "And the latest news."),
    ]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok   {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
