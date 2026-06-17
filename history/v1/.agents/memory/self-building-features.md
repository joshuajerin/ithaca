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

## Security guard (code_guard.py)
- `app/code_guard.py` `validate_python_source(code)` is an AST allow-list audit run BEFORE any
  execution (subprocess or in-process). Allows stdlib-only roots (math/random/datetime/json/…);
  rejects all other imports, eval/exec/compile/__import__/open/getattr/setattr, dunder attr/name
  access (blocks `().__class__.__subclasses__()` escapes), relative imports. Raises `CodeGuardError`.
- Called in `feature_builder.stream_feature_request` (before `_validate_python`) AND in
  `dynamic_skills._import_module` (so startup-loaded on-disk files are re-audited before exec).
- `_validate_python` subprocess is sandboxed: `-I` isolated mode, private temp cwd, minimal env
  (no inherited secrets, no PYTHONPATH), `preexec_fn` does setsid + RLIMIT_CPU/AS/FSIZE, 10s timeout.
- **RLIMIT_AS gotcha:** `.pythonlibs/bin/python` is a Go-shim launcher that reserves a large
  virtual mapping; AS<~1GB makes it die with "failed to reserve page summary memory". Use 2GB.
- `_validate_tsx` also blocks dangerouslySetInnerHTML/eval/fetch/import()/localStorage and any
  import whose source != "react".
- Test: `tests/test_code_guard.py` (no pytest needed; `python tests/test_code_guard.py`).

## Frontend dynamic rendering (two-path: dev glob + prod runtime compile)
- `panels/generated/registry.ts` has BOTH: (1) static Vite `import.meta.glob('./*.tsx',{eager})`
  keyed by filename=panel_type (dev HMR + panels bundled at build time); (2) a RUNTIME path —
  `loadGeneratedComponent(type)` fetches source from `GET /api/generated-panels`, transpiles TSX
  in-browser with **sucrase** (`transforms: typescript,jsx,imports`), evals via `new Function`
  with a require shim that only allows `"react"`, caches the component. Needed because a built/
  deployed app has no HMR and can't bundle a `.tsx` written after build.
- Endpoint `GET /api/generated-panels` (main.py) reads PANEL_DIR `*.tsx`, EXCLUDES infra files
  `DynamicPanel.tsx`/`GeneratedPanel.tsx` and `_`-prefixed. Returns `{panels:[{panelType,source}]}`.
- `DynamicPanel.tsx` `useGeneratedComponent` hook: static component used immediately, else async
  runtime-load; generic `GeneratedPanel.tsx` shown while loading / on any failure; whole thing in
  an ErrorBoundary so a bad generated component can't crash the dashboard.
- **Why:** generated tsx contract = only `import React from "react"` + default export, so the
  require shim + sucrase imports-transform interop (`_interopRequireDefault`) is sufficient.
- Endpoint `POST /api/feature-request` is SSE (StreamingResponse over a sync generator) with
  stages planning→generating_skill→generating_panel→activating→done|error. `FeatureRequestModal`
  reads it via `fetch` + `ReadableStream` (relative `/api/...`, proxy-routed; no base URL set).
- **Planning call heartbeat:** the planning LLM call authors BOTH files at once and takes ~45-50s
  (so the 30s default `CHAT_TIMEOUT` always killed it — fixed by passing `ai.FEATURE_BUILD_TIMEOUT`
  =55s). To avoid the long blocking call tripping the proxy, `stream_feature_request` runs `_call_ai`
  on a worker thread and `yield`s an SSE comment heartbeat (`: keepalive\n\n`, ignored by the
  frontend parser which only acts on `data:` lines) every 5s while it runs; on completion it re-raises
  any worker error so the existing outer except handlers still produce the clean error + zero partial
  files.

## Provenance manifest (debuggability + feature management)
- `dynamic_skills.py` owns `manifest.json` in `skills_generated/`: `read_manifest()` (resilient —
  missing/corrupt/non-list → `[]`, never raises), `record_feature(panel_type,name,description,
  invoke_example)` (appends, replaces same-panel_type, atomic temp+os.replace), `remove_manifest_entry`
  (drops entry on delete). All best-effort: swallow+log errors. Entry keys: panel_type, name,
  description (ORIGINAL user prompt), invoke_example, created_at (ISO).
- **The manifest is provenance ONLY — the loader scans `*.py` on disk and never reads it, so a bad
  manifest can't block skill loading.** `feature_builder` calls `record_feature` AFTER both files
  write (never aborts activation); `remove_feature` calls `remove_manifest_entry`.
- **Feature-management UI is `/api/features` (list) + `DELETE /api/features/{panel_type}`** (main.py),
  served by `feature_builder.list_features()`/`remove_feature()`. `list_features` returns camelCase
  (panelType,name,description,invokeExample,createdAt) and PREFERS manifest data (original prompt +
  true created_at), falling back to SKILL_DEFINITION + .py mtime for pre-manifest features. The
  `FeatureRequestModal` build/manage view consumes it. (An earlier `/api/generated-features` +
  "Features you've built" list was folded into this richer management UI during a rebase.)

## Abuse throttling (resource/cost guard)
- `feature_builder.stream_feature_request` enforces a per-process limiter via
  `_try_acquire_build_slot()`/`_release_build_slot()` (threading.Lock — SSE generator runs in a
  threadpool, so requests race). Concurrency cap `_MAX_CONCURRENT_BUILDS=1` + rolling-window rate
  `_RATE_MAX_IN_WINDOW=5` per `_RATE_WINDOW_SECONDS=60`. Acquire happens AFTER the
  description/ai_available checks; rejection is emitted as a `{"stage":"error"}` SSE event (NOT
  HTTP 429, since the response is already streaming). Slot is freed in a `finally` (also fires on
  client disconnect via GeneratorExit). Single-at-a-time use is unaffected.
