---
name: Self-building feature pipeline (Build Feature)
description: How AI-generated skills+panels are added at runtime with no server restart, and the constraints that make it safe.
---

The terminal can author NEW capabilities from a plain-language description: AI generates a
Python skill module + a React panel, validates, writes them, and registers in-process — no restart.

## Why no `--reload` on api-server
uvicorn `--reload` watches the workspace cwd, so writing any generated `.py`/`.tsx` triggers a
restart that wipes in-memory sessions (`state.py`). The dev run was changed (via the artifacts
skill `verifyAndReplaceArtifactToml`, NOT a direct edit) to drop `--reload`. New skills become
live via in-process `dynamic_skills.load_generated_skills()` instead. After any toml swap you
MUST restart the workflow for it to take effect.

## Backend contract (additive-only, never touch core files)
- Generated skills live in `app/skills_generated/<panel_type>.py`. Each exports
  `SKILL_DEFINITION` (id, name, panel_type, description, default_title, subskills,
  invoke_phrases, parameters) + `build(params)->dict` (stdlib only, must work with `{}`).
- `dynamic_skills.py` scans/imports/registers them into `skills.SKILLS` (a `SkillDef`).
- `harness.run_skill`: `DATA_MODELS.get(panel_type)` — when None (dynamic), pass the builder's
  dict through untouched (no pydantic). `models.Panel.type`/`Skill.panelType` are plain `str`
  and `Panel.data` is `dict` so dynamic types serialize. **Safe because frontend TS types come
  from hand-written `lib/api-spec/openapi.yaml`, NOT the Python pydantic models.**
- `agent.py`: `_dynamic_tools()` appended to LLM tools; `_type_of_tool()` resolves `add_<type>`
  for both built-in (`_TOOL_TO_TYPE`) and dynamic; heuristic fallback matches `invoke_phrases`;
  refine uses `_all_tools()`/`_type_of_tool` (old code KeyError'd on dynamic types).

## Clean-failure guarantee
`feature_builder.py` validates Python in an ISOLATED subprocess (ast import + `build({})` returns
JSON-serializable dict) and checks tsx has a default export BEFORE writing anything. Writes py
first, registers in-process, rolls back (deletes py) if registration throws, then writes tsx.
A failure leaves zero partial files.

## Frontend dynamic rendering
- `panels/generated/registry.ts` uses Vite `import.meta.glob('./*.tsx', {eager:true})`, keyed by
  filename = panel_type. New files are picked up by dev HMR.
- `DynamicPanel.tsx` (rendered from `PanelContainer` default case) prefers the dedicated
  component, falls back to generic `GeneratedPanel.tsx`, wrapped in an ErrorBoundary so a bad
  generated component can't crash the dashboard.
- Endpoint `POST /api/feature-request` is SSE (StreamingResponse over a sync generator) with
  stages planning→generating_skill→generating_panel→activating→done|error. `FeatureRequestModal`
  reads it via `fetch` + `ReadableStream` (relative `/api/...`, proxy-routed; no base URL set).
