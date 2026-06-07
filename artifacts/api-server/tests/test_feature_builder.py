"""End-to-end tests for the self-building feature pipeline.

Runnable two ways:
    python artifacts/api-server/tests/test_feature_builder.py     # standalone
    pytest artifacts/api-server/tests/test_feature_builder.py      # if pytest installed

These exercise the FULL backend pipeline that the "Build a Feature" modal drives
over SSE (``POST /api/feature-request`` -> ``feature_builder.stream_feature_request``):
plan -> validate Python (static guard + isolated subprocess) -> validate TSX ->
write both artifacts -> register the skill in-process -> dispatch it via the
harness (what happens when the user types the invoke example in chat).

The only thing mocked is the single LLM call (``ai.chat``); everything downstream
runs for real, including the subprocess validator and on-disk writes. A unique
test-only panel_type is used and both artifacts are removed afterward so the test
never leaves state behind and never collides with a real generated feature.

Positive test  -> a valid generation reaches "done", writes both files, registers
                  the skill, and the harness builds an "ok" panel from it.
Negative tests -> a generation that fails Python validation, TSX validation, or the
                  static safety guard reports an "error" stage and leaves NO partial
                  files in ``skills_generated/`` or ``panels/generated/``.
"""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import ai, dynamic_skills, feature_builder, harness, skills  # noqa: E402

# A unique, test-only panel type so we never touch a real generated feature.
_TEST_TYPE = "e2e_test_gauge"

# A valid skill module honoring the contract (stdlib only, build({}) works).
_VALID_PY = '''
import random
from datetime import datetime, timezone

SKILL_DEFINITION = {
    "id": "e2e-test-gauge",
    "name": "E2E Test Gauge",
    "panel_type": "e2e_test_gauge",
    "description": "A deterministic test gauge used by the automated feature-builder e2e test.",
    "default_title": "Test Gauge",
    "subskills": [
        {"name": "pick", "description": "Pick a reading.", "expectedOutput": "A number."},
    ],
    "invoke_phrases": ["e2e test gauge", "test gauge"],
    "parameters": {"label": {"type": "string", "description": "An optional label."}},
}

def build(params):
    label = (params.get("label") or "Default").strip()
    rng = random.Random(1234)
    reading = round(rng.random() * 100, 2)
    return {
        "label": label,
        "reading": reading,
        "asOf": datetime.now(timezone.utc).isoformat(),
        "source": "mock",
    }
'''

_VALID_TSX = '''import React from "react";

export default function E2eTestGaugePanel({ data }: { data: any }) {
  const reading = data?.reading ?? 0;
  return (
    <div className="flex flex-col h-full text-white">
      <span className="text-[10px] uppercase tracking-widest text-zinc-400">{data?.label ?? "—"}</span>
      <span className="font-serif text-3xl">{reading}</span>
    </div>
  );
}
'''


def _payload(python_code: str, tsx_code: str) -> dict:
    return {
        "panel_type": _TEST_TYPE,
        "feature_name": "E2E Test Gauge",
        "invoke_example": "show me the e2e test gauge",
        "python_code": python_code,
        "tsx_code": tsx_code,
    }


def _install_fake_ai(monkeyish, payload: dict):
    """Point feature_builder's AI at a canned response. Returns a restore fn."""
    orig_available = ai.ai_available
    orig_chat = ai.chat
    ai.ai_available = lambda: True  # type: ignore[assignment]
    ai.chat = lambda *a, **k: SimpleNamespace(content=json.dumps(payload))  # type: ignore[assignment]

    def restore():
        ai.ai_available = orig_available  # type: ignore[assignment]
        ai.chat = orig_chat  # type: ignore[assignment]

    return restore


def _py_path() -> str:
    return os.path.join(dynamic_skills.GENERATED_DIR, f"{_TEST_TYPE}.py")


def _tsx_path() -> str:
    return os.path.join(feature_builder.PANEL_DIR, f"{_TEST_TYPE}.tsx")


def _cleanup() -> None:
    """Remove any test artifacts and unregister the test skill in-process."""
    for p in (_py_path(), _tsx_path()):
        try:
            os.remove(p)
        except OSError:
            pass
    skills.SKILLS.pop(_TEST_TYPE, None)
    dynamic_skills._DEFINITIONS.pop(_TEST_TYPE, None)
    sys.modules.pop("app.skills_generated." + _TEST_TYPE, None)


def _drive(description: str) -> list:
    """Consume the SSE stream and return the parsed event dicts in order."""
    events = []
    for chunk in feature_builder.stream_feature_request(description):
        line = chunk.strip()
        if not line.startswith("data:"):
            continue
        events.append(json.loads(line[len("data:"):].strip()))
    return events


def _assert_no_partial_files() -> None:
    assert not os.path.exists(_py_path()), f"left a partial python file: {_py_path()}"
    assert not os.path.exists(_tsx_path()), f"left a partial tsx file: {_tsx_path()}"


# --------------------------- positive ---------------------------
def test_build_feature_happy_path_registers_and_renders():
    """Full pipeline: valid generation -> done -> files written -> skill
    registered -> harness builds an 'ok' panel (the chat-invoke path)."""
    _cleanup()
    restore = _install_fake_ai(None, _payload(_VALID_PY, _VALID_TSX))
    try:
        events = _drive("a deterministic test gauge for the e2e suite")

        stages = [e.get("stage") for e in events]
        assert "error" not in stages, f"unexpected error stage: {events}"
        assert stages[-1] == "done", f"did not reach done: {stages}"

        done = events[-1]
        assert done["feature"]["panelType"] == _TEST_TYPE
        assert done["feature"]["invokeExample"]

        # Both artifacts are on disk.
        assert os.path.exists(_py_path()), "python skill not written"
        assert os.path.exists(_tsx_path()), "tsx panel not written"

        # Skill is registered in-process (no restart needed).
        assert _TEST_TYPE in skills.SKILLS
        assert dynamic_skills.is_dynamic(_TEST_TYPE)

        # Dispatching it (what the chat invoke does) yields a renderable panel.
        panel = harness.run_skill(_TEST_TYPE, {"label": "QA"}, {"x": 0, "y": 0, "w": 6, "h": 4})
        assert panel["status"] == "ok", f"panel build failed: {panel.get('note')}"
        assert panel["type"] == _TEST_TYPE
        assert panel["data"]["label"] == "QA"
        assert isinstance(panel["data"]["reading"], (int, float))
        # Freshness metadata is lifted onto the envelope, not the data dict.
        assert panel["source"] == "mock"
        assert "source" not in panel["data"]
    finally:
        restore()
        _cleanup()


# --------------------------- negative: clean failure leaves no files ---------------------------
def test_invalid_python_leaves_no_partial_files():
    """build() raising means the isolated validator fails -> error, no files."""
    _cleanup()
    bad_py = _VALID_PY.replace(
        "    reading = round(rng.random() * 100, 2)",
        "    raise RuntimeError('boom')\n    reading = 0",
    )
    restore = _install_fake_ai(None, _payload(bad_py, _VALID_TSX))
    try:
        events = _drive("a gauge whose builder explodes")
        assert events[-1]["stage"] == "error", f"expected error, got {events[-1]}"
        _assert_no_partial_files()
        assert _TEST_TYPE not in skills.SKILLS
    finally:
        restore()
        _cleanup()


def test_invalid_tsx_leaves_no_partial_files():
    """A TSX panel without a default export is rejected before any write."""
    _cleanup()
    bad_tsx = _VALID_TSX.replace("export default function", "function")
    restore = _install_fake_ai(None, _payload(_VALID_PY, bad_tsx))
    try:
        events = _drive("a gauge whose panel has no default export")
        assert events[-1]["stage"] == "error", f"expected error, got {events[-1]}"
        _assert_no_partial_files()
        assert _TEST_TYPE not in skills.SKILLS
    finally:
        restore()
        _cleanup()


def test_unsafe_python_blocked_by_guard_leaves_no_files():
    """A disallowed import is rejected by the static guard before execution."""
    _cleanup()
    unsafe_py = "import os\n" + _VALID_PY
    restore = _install_fake_ai(None, _payload(unsafe_py, _VALID_TSX))
    try:
        events = _drive("a gauge that tries to import os")
        assert events[-1]["stage"] == "error", f"expected error, got {events[-1]}"
        assert "safety" in events[-1]["message"].lower()
        _assert_no_partial_files()
        assert _TEST_TYPE not in skills.SKILLS
    finally:
        restore()
        _cleanup()


def test_empty_description_is_rejected():
    """An empty request errors immediately and never calls the AI or writes."""
    _cleanup()
    try:
        events = _drive("   ")
        assert len(events) == 1
        assert events[0]["stage"] == "error"
        _assert_no_partial_files()
    finally:
        _cleanup()


def _run_all() -> int:
    tests = [
        test_build_feature_happy_path_registers_and_renders,
        test_invalid_python_leaves_no_partial_files,
        test_invalid_tsx_leaves_no_partial_files,
        test_unsafe_python_blocked_by_guard_leaves_no_files,
        test_empty_description_is_rejected,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
