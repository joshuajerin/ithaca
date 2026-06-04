"""Self-building feature pipeline.

Takes a plain-language feature description, asks the LLM to author (a) a Python
skill module and (b) a React panel component, validates the Python in an isolated
subprocess, writes both artifacts to disk, and registers the new skill in-process
so it is callable immediately — no server restart.

All output is additive: only NEW files under ``skills_generated/`` (Python) and the
terminal's ``panels/generated/`` (TSX). Core files are never modified by this flow.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Iterator, Optional, Tuple

from . import ai, dynamic_skills, skills

# Where the generated React panel components live (terminal artifact).
_THIS_DIR = os.path.dirname(__file__)
_WORKSPACE_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
PANEL_DIR = os.path.join(
    _WORKSPACE_ROOT,
    "artifacts", "terminal", "src", "components", "terminal", "panels", "generated",
)


# ----------------------------- prompt -----------------------------
_SYSTEM_PROMPT = r"""You extend an "Agentic Terminal" — a market-intelligence dashboard — by authoring
a brand-new, self-contained capability ("skill" + "panel") from a user's plain-language request.

You MUST respond with a SINGLE JSON object (no prose, no code fences) with EXACTLY these keys:
{
  "panel_type": string,        // unique snake_case id, e.g. "forex_forecast" (lowercase, a-z 0-9 _)
  "feature_name": string,      // short Title Case display name, e.g. "Forex Forecast"
  "invoke_example": string,    // a natural-language chat command that triggers it, e.g. "show me a forex forecast for EURUSD"
  "python_code": string,       // a complete Python module (see contract below)
  "tsx_code": string           // a complete React (TypeScript) panel component (see contract below)
}

=== PYTHON MODULE CONTRACT ===
The python_code is a standalone module. It MUST define:

1) SKILL_DEFINITION: a dict with keys:
   - "id": kebab-case id (e.g. "forex-forecast")
   - "name": same as feature_name
   - "panel_type": same as panel_type
   - "description": one sentence describing WHEN to use it (used to route AI requests)
   - "default_title": short title (e.g. "Forex Forecast")
   - "subskills": list of {"name","description","expectedOutput"} (2-4 entries)
   - "invoke_phrases": list of lowercase trigger phrases (e.g. ["forex forecast","fx forecast"])
   - "parameters": dict of JSON-schema property objects the request may include
        (e.g. {"pair": {"type":"string","description":"Currency pair like EURUSD"}}).
        Use "symbol" or "ticker" as the key if it takes a stock ticker. May be {}.

2) build(params: dict) -> dict
   - Returns the panel "data" dict that the React panel will render via its `data` prop.
   - MUST work when called with an EMPTY dict (sensible defaults) and never raise.
   - Use ONLY the Python standard library (math, random, datetime, etc.). NO third-party imports.
   - Generate plausible SYNTHETIC data deterministically (seed `random.Random(<stable seed>)`).
   - You MAY include "asOf" (ISO timestamp string) and "source" ("live" or "mock") keys; they are
     read as freshness metadata. Default "source" to "mock".
   - Keep the returned shape FLAT and JSON-serializable (str/int/float/bool/list/dict only).

Example python_code (study the shape, then write your own for the request):
---
import random
from datetime import datetime, timezone

SKILL_DEFINITION = {
    "id": "forex-forecast",
    "name": "Forex Forecast",
    "panel_type": "forex_forecast",
    "description": "Show a short-term forecast for a currency pair. Use when the user asks about FX or forex forecasts.",
    "default_title": "Forex Forecast",
    "subskills": [
        {"name": "resolve_pair", "description": "Pick the currency pair.", "expectedOutput": "A pair like EURUSD."},
        {"name": "project_path", "description": "Project a short forward path.", "expectedOutput": "Dated forecast points."},
    ],
    "invoke_phrases": ["forex forecast", "fx forecast", "currency forecast"],
    "parameters": {"pair": {"type": "string", "description": "Currency pair, e.g. EURUSD"}},
}

def build(params):
    pair = (params.get("pair") or "EURUSD").upper()
    rng = random.Random(hash(pair) & 0xFFFFFFFF)
    spot = round(1 + rng.random(), 4)
    points = []
    val = spot
    for i in range(14):
        val = round(val * (1 + (rng.random() - 0.5) * 0.01), 4)
        points.append({"day": i + 1, "value": val})
    bias = "bullish" if points[-1]["value"] > spot else "bearish"
    return {
        "pair": pair,
        "spot": spot,
        "bias": bias,
        "points": points,
        "asOf": datetime.now(timezone.utc).isoformat(),
        "source": "mock",
    }
---

=== TSX PANEL CONTRACT ===
The tsx_code is a complete React component file. It MUST:
- `import React from "react";`
- Export a DEFAULT React function component that accepts `{ data }: { data: any }`.
- Render `data` (the exact dict returned by build) using plain JSX + Tailwind utility classes.
- Match the terminal's dark editorial aesthetic: black background, white/zinc text, thin borders
  (use classes like "text-white", "text-zinc-400", "border-zinc-800", "font-serif", small uppercase labels).
- Be defensive: guard against missing/empty fields (e.g. `const points = data?.points ?? [];`).
- NOT import any external libraries or other project files (no charts libs, no "@/..." imports).
  Draw simple bars/sparklines with divs if you need a visual.
- Use only inline Tailwind classes; do not import CSS.

Example tsx_code:
---
import React from "react";

export default function ForexForecastPanel({ data }: { data: any }) {
  const points = data?.points ?? [];
  const max = Math.max(1, ...points.map((p: any) => p.value));
  return (
    <div className="flex flex-col h-full text-white">
      <div className="flex items-baseline justify-between mb-3">
        <span className="font-serif text-xl">{data?.pair ?? "—"}</span>
        <span className="text-[10px] uppercase tracking-widest text-zinc-400">{data?.bias ?? ""}</span>
      </div>
      <div className="flex items-end gap-1 flex-1">
        {points.map((p: any, i: number) => (
          <div key={i} className="flex-1 bg-zinc-200" style={{ height: `${(p.value / max) * 100}%` }} />
        ))}
      </div>
    </div>
  );
}
---

Make the data and panel genuinely useful and specific to the user's request. Invent a sensible,
information-rich data shape. Keep both files concise but complete.
"""


# ----------------------------- helpers -----------------------------
def _slugify_panel_type(raw: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", (raw or "").strip().lower()).strip("_")
    return s or "custom_panel"


def _pascal_case(panel_type: str) -> str:
    return "".join(part.capitalize() for part in panel_type.split("_")) or "Custom"


def _extract_json(content: str) -> dict:
    content = (content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
    return json.loads(content)


def _call_ai(description: str) -> dict:
    msg = ai.chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Feature request: {description.strip()}"},
        ],
        response_format={"type": "json_object"},
    )
    payload = _extract_json(msg.content or "")
    for key in ("panel_type", "feature_name", "python_code", "tsx_code"):
        if not payload.get(key):
            raise ValueError(f"AI response missing '{key}'")
    return payload


# Validation script run in a clean subprocess. Imports the module, checks the
# contract, and runs build({}) to ensure it executes and returns a dict.
_VALIDATE_SCRIPT = r"""
import importlib.util, json, sys
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("candidate_skill", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
d = getattr(mod, "SKILL_DEFINITION", None)
assert isinstance(d, dict), "SKILL_DEFINITION must be a dict"
for k in ("id", "name", "panel_type", "description"):
    assert d.get(k), "SKILL_DEFINITION missing key: " + k
build = getattr(mod, "build", None)
assert callable(build), "build(params) must be callable"
out = build({})
assert isinstance(out, dict), "build({}) must return a dict"
json.dumps(out)  # must be JSON-serializable
print("OK")
"""


def _validate_python(code: str) -> None:
    """Validate the candidate Python in an isolated subprocess. Raises on failure."""
    with tempfile.TemporaryDirectory() as tmp:
        mod_path = os.path.join(tmp, "candidate_skill.py")
        with open(mod_path, "w", encoding="utf-8") as fh:
            fh.write(code)
        script_path = os.path.join(tmp, "_validate.py")
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write(_VALIDATE_SCRIPT)
        try:
            proc = subprocess.run(
                [sys.executable, script_path, mod_path],
                capture_output=True, text=True, timeout=20,
            )
        except subprocess.TimeoutExpired:
            raise ValueError("Generated skill timed out during validation")
        if proc.returncode != 0 or "OK" not in proc.stdout:
            err = (proc.stderr or proc.stdout or "unknown error").strip().splitlines()
            raise ValueError("Generated skill failed validation: " + (err[-1] if err else "unknown"))


def _validate_tsx(code: str) -> None:
    if "export default" not in code:
        raise ValueError("Generated panel must have a default export")


# ----------------------------- SSE event stream -----------------------------
def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def stream_feature_request(description: str) -> Iterator[str]:
    """Yield Server-Sent-Event lines describing each stage and the final result.

    Stages: planning -> generating_skill -> generating_panel -> activating -> done|error.
    Nothing is written to disk unless BOTH artifacts validate, so a failure leaves
    no partial state.
    """
    if not description or not description.strip():
        yield _sse({"stage": "error", "message": "Please describe the feature you want."})
        return
    if not ai.ai_available():
        yield _sse({"stage": "error", "message": "AI is not available to build features right now."})
        return

    try:
        yield _sse({"stage": "planning", "message": "Interpreting your request…"})
        payload = _call_ai(description)

        panel_type = _slugify_panel_type(payload["panel_type"])
        if panel_type in skills.SKILLS and not dynamic_skills.is_dynamic(panel_type):
            yield _sse({"stage": "error",
                        "message": f"'{panel_type}' conflicts with a built-in panel. Try a more specific request."})
            return

        feature_name = str(payload["feature_name"]).strip()
        invoke_example = str(payload.get("invoke_example") or f"show me {feature_name}").strip()
        python_code = payload["python_code"]
        tsx_code = payload["tsx_code"]

        yield _sse({"stage": "generating_skill", "message": "Writing & validating the data skill…"})
        _validate_python(python_code)

        yield _sse({"stage": "generating_panel", "message": "Designing the panel component…"})
        _validate_tsx(tsx_code)

        yield _sse({"stage": "activating", "message": "Activating the new capability…"})
        dynamic_skills.ensure_dir()
        os.makedirs(PANEL_DIR, exist_ok=True)
        py_path = os.path.join(dynamic_skills.GENERATED_DIR, f"{panel_type}.py")
        tsx_path = os.path.join(PANEL_DIR, f"{panel_type}.tsx")

        # Write Python first, then register in-process; if registration fails, roll back.
        with open(py_path, "w", encoding="utf-8") as fh:
            fh.write(python_code)
        try:
            dynamic_skills.load_one(panel_type)
        except Exception as exc:  # noqa: BLE001
            try:
                os.remove(py_path)
            except OSError:
                pass
            yield _sse({"stage": "error", "message": f"Skill failed to activate: {exc}"})
            return

        with open(tsx_path, "w", encoding="utf-8") as fh:
            fh.write(tsx_code)

        yield _sse({
            "stage": "done",
            "feature": {
                "panelType": panel_type,
                "featureName": feature_name,
                "invokeExample": invoke_example,
            },
            "message": f"{feature_name} added — type \"{invoke_example}\" in the chat to use it.",
        })
    except json.JSONDecodeError:
        yield _sse({"stage": "error", "message": "The AI returned an invalid response. Please try again."})
    except Exception as exc:  # noqa: BLE001
        yield _sse({"stage": "error", "message": f"Feature generation failed: {exc}"})
