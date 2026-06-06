---
name: Adding new hand-written panel types (passthrough)
description: How to add a new non-generated panel type to the terminal end-to-end without touching openapi codegen, and which tsc errors are expected.
---

# Adding a new hand-written panel type (passthrough pattern)

New panel types (e.g. `company_analytics`, `analyst_report`, `scenario`) can be added
end-to-end WITHOUT touching `openapi.yaml` / generated `models.py` / running codegen.

**How the passthrough works:**
- `harness.py` only validates panel `data` against `DATA_MODELS`. A panel type NOT in
  `DATA_MODELS` has its builder dict passed through untouched; the harness still pops
  `asOf`/`source` into the envelope.
- `models.Panel.data` is `Optional[dict]`, and `DashboardSpec` therefore serializes any
  builder dict over HTTP. So the `/api/orchestrate` response carries the raw dict.
- Frontend `PanelContainer.tsx` switch-cases the new `type` and casts `panel.data as any`
  into the hand-written component.

**Wiring checklist for a new type (mirror `company_analytics`):**
1. `skills.py`: write `build_<x>` with AI + heuristic fallback, register via `_reg(...)`
   with the new `panel_type`.
2. `agent.py`: add `add_<x>` tool in `_tools()`, `_TOOL_TO_TYPE`, `_TYPE_LABELS`,
   `_system_prompt`, and `_orchestrate_heuristic` routing.
3. Frontend: new `panels/<X>Panel.tsx` + import + switch case in `PanelContainer.tsx`.

**Expected (non-blocking) tsc errors — do NOT "fix":**
`pnpm exec tsc` reports "not comparable to type 'PanelType'" errors for every
passthrough panel (and any you add) because the generated `PanelType` enum doesn't
include them. This is by design — the build uses `vite build` (esbuild, no tsc gate)
and dev uses vite, so these never block. Do not regenerate openapi to "fix" them.

**Gotcha — missing `_reg` fails silently as "Unknown panel type":** `skills.build_<x>(params)`
works when called directly, but `/api/orchestrate` dispatches by panel type through the `SKILLS`
registry. If you forget `_reg(SkillDef(... panel_type ...))`, the panel returns a CLEAN failure
(status `error`, note "could not be built: Unknown panel type") with NO traceback in logs — easy
to misread as a builder bug. Always verify the new type via orchestrate, not just the builder.

**Always restart `artifacts/api-server: API Server`** after backend changes — it runs
WITHOUT `--reload`.

**Opposite gotcha — adding a FIELD to an EXISTING typed panel:** types in `DATA_MODELS`
(e.g. `price_chart` → `PriceChartData`) are validated by the hand-maintained pydantic
models in `app/models.py`. A new key your builder returns is **silently stripped** from
the HTTP response if it isn't on that pydantic model — the field just shows up `None`/missing
on the client with no error. For typed panels you must add the field in THREE places in
lockstep: `app/models.py` (pydantic, the one that actually gates the response),
`lib/api-spec/openapi.yaml` + rerun `pnpm --filter @workspace/api-spec run codegen` (for the
typed TS client). The openapi/codegen alone is NOT enough; models.py is the real filter.
