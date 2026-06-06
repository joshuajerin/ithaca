"""End-to-end test for the self-building feature (Build Feature) happy path.

Runnable two ways:
    python artifacts/api-server/tests/test_feature_builder.py   # standalone
    pytest artifacts/api-server/tests/test_feature_builder.py    # if pytest installed

The security guard already has focused rejection coverage (``test_code_guard``).
This test exercises the *happy path*: a valid plain-language request is stubbed
to produce a working skill + panel, and we assert the full pipeline reaches the
``done`` stage, writes both files, registers the skill in ``skills.SKILLS``, and
that ``harness.run_skill`` can build a panel from the freshly generated skill.

The AI call is stubbed so the test is deterministic and offline. Every file the
test creates is removed (and the skill un-registered) in a ``finally`` block so
the generated dirs are left exactly as they were found.
"""
from __future__ import annotations

import json
import os
import sys

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import ai, dynamic_skills, feature_builder, harness, skills  # noqa: E402

# A panel_type unlikely to collide with any built-in or previously generated skill.
_PANEL_TYPE = "e2e_test_widget"

# A valid, contract-abiding Python skill module (stdlib only) that the stubbed AI
# "returns". Mirrors the shape required by the PYTHON MODULE CONTRACT.
_PYTHON_CODE = '''
import random
from datetime import datetime, timezone

SKILL_DEFINITION = {
    "id": "e2e-test-widget",
    "name": "E2E Test Widget",
    "panel_type": "e2e_test_widget",
    "description": "A deterministic synthetic widget used to verify the build pipeline end to end.",
    "default_title": "E2E Test Widget",
    "subskills": [
        {"name": "seed", "description": "Seed a deterministic series.", "expectedOutput": "A stable seed."},
        {"name": "series", "description": "Produce a short series.", "expectedOutput": "Dated points."},
    ],
    "invoke_phrases": ["e2e test widget", "test widget"],
    "parameters": {"symbol": {"type": "string", "description": "A ticker symbol."}},
}

def build(params):
    symbol = (params.get("symbol") or "TEST").upper()
    rng = random.Random(hash(symbol) & 0xFFFFFFFF)
    points = []
    val = 100.0
    for i in range(10):
        val = round(val * (1 + (rng.random() - 0.5) * 0.02), 2)
        points.append({"day": i + 1, "value": val})
    return {
        "symbol": symbol,
        "points": points,
        "asOf": datetime.now(timezone.utc).isoformat(),
        "source": "mock",
    }
'''

# A valid, contract-abiding React panel component (imports only react, default export).
_TSX_CODE = '''import React from "react";

export default function E2ETestWidgetPanel({ data }: { data: any }) {
  const points = data?.points ?? [];
  const max = Math.max(1, ...points.map((p: any) => p.value));
  return (
    <div className="flex flex-col h-full text-white">
      <div className="flex items-baseline justify-between mb-3">
        <span className="font-serif text-xl">{data?.symbol ?? "—"}</span>
        <span className="text-[10px] uppercase tracking-widest text-zinc-400">E2E</span>
      </div>
      <div className="flex items-end gap-1 flex-1">
        {points.map((p: any, i: number) => (
          <div key={i} className="flex-1 bg-zinc-200" style={{ height: `${(p.value / max) * 100}%` }} />
        ))}
      </div>
    </div>
  );
}
'''


class _StubMessage:
    """Mimics the OpenAI chat message object: only ``.content`` is read."""

    def __init__(self, content: str):
        self.content = content


def _make_stub_chat(payload: dict):
    def _stub_chat(messages, tools=None, tool_choice=None, response_format=None):
        return _StubMessage(json.dumps(payload))

    return _stub_chat


def _drive(description: str) -> list:
    """Run the SSE generator to completion, returning the parsed event dicts."""
    events = []
    for line in feature_builder.stream_feature_request(description):
        # Each chunk is "data: {json}\n\n".
        for part in line.splitlines():
            part = part.strip()
            if part.startswith("data:"):
                events.append(json.loads(part[len("data:"):].strip()))
    return events


def _cleanup() -> None:
    """Remove generated files and un-register the skill so nothing is left behind."""
    py_path = os.path.join(dynamic_skills.GENERATED_DIR, f"{_PANEL_TYPE}.py")
    tsx_path = os.path.join(feature_builder.PANEL_DIR, f"{_PANEL_TYPE}.tsx")
    for path in (py_path, tsx_path):
        try:
            os.remove(path)
        except OSError:
            pass
    skills.SKILLS.pop(_PANEL_TYPE, None)
    dynamic_skills._DEFINITIONS.pop(_PANEL_TYPE, None)


def test_build_feature_happy_path():
    """A valid request drives the full pipeline to ``done`` and yields a usable skill."""
    payload = {
        "panel_type": _PANEL_TYPE,
        "feature_name": "E2E Test Widget",
        "invoke_example": "show me the e2e test widget for AAPL",
        "python_code": _PYTHON_CODE,
        "tsx_code": _TSX_CODE,
    }

    orig_chat = ai.chat
    orig_available = ai.ai_available
    # Ensure a clean slate even if a prior run left artifacts behind.
    _cleanup()
    try:
        ai.ai_available = lambda: True
        ai.chat = _make_stub_chat(payload)

        events = _drive("Build me a test widget that shows a synthetic price series.")
        stages = [e.get("stage") for e in events]

        # 1) The pipeline reached the terminal `done` stage (no error stage).
        assert "error" not in stages, f"pipeline errored: {events}"
        assert stages[-1] == "done", f"expected final stage 'done', got stages={stages}"
        done = events[-1]
        assert done["feature"]["panelType"] == _PANEL_TYPE, done

        # 2) Both artifacts were written to disk.
        py_path = os.path.join(dynamic_skills.GENERATED_DIR, f"{_PANEL_TYPE}.py")
        tsx_path = os.path.join(feature_builder.PANEL_DIR, f"{_PANEL_TYPE}.tsx")
        assert os.path.exists(py_path), f"skill module not written: {py_path}"
        assert os.path.exists(tsx_path), f"panel component not written: {tsx_path}"

        # 3) The skill registered in the live registry as a dynamic skill.
        assert _PANEL_TYPE in skills.SKILLS, "skill was not registered in skills.SKILLS"
        assert dynamic_skills.is_dynamic(_PANEL_TYPE), "skill not marked as dynamic"

        # 4) The harness can build a working panel from the new skill.
        panel = harness.run_skill(_PANEL_TYPE, {"symbol": "AAPL"}, {"x": 0, "y": 0, "w": 6, "h": 4})
        assert panel["status"] == "ok", f"harness failed to build panel: {panel}"
        assert panel["type"] == _PANEL_TYPE
        assert panel["data"]["symbol"] == "AAPL"
        assert isinstance(panel["data"]["points"], list) and panel["data"]["points"], panel
        # Freshness metadata is lifted onto the panel envelope, not the data dict.
        assert panel["source"] == "mock"
        assert "source" not in panel["data"]
    finally:
        ai.chat = orig_chat
        ai.ai_available = orig_available
        _cleanup()


def test_build_feature_leaves_generated_dirs_clean():
    """After the happy-path run + cleanup, no test artifacts remain on disk."""
    py_path = os.path.join(dynamic_skills.GENERATED_DIR, f"{_PANEL_TYPE}.py")
    tsx_path = os.path.join(feature_builder.PANEL_DIR, f"{_PANEL_TYPE}.tsx")
    assert not os.path.exists(py_path), "test skill module was left behind"
    assert not os.path.exists(tsx_path), "test panel component was left behind"
    assert _PANEL_TYPE not in skills.SKILLS, "test skill was left registered"


def _run_all() -> int:
    tests = [
        test_build_feature_happy_path,
        test_build_feature_leaves_generated_dirs_clean,
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
