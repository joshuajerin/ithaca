# Verification Contract — doomberg-infra-cleanup

## Goal
Restore the API contract as the single source of truth and get the repo's own
build gate (`pnpm run typecheck` / prod build) green again. The "wide vibe-coded"
state had let the canonical `lib/api-spec/openapi.yaml` drift away from what the
backend emits and the frontend renders.

## Existing behavior to preserve
- Backend (FastAPI `app/main.py`, run by systemd via uvicorn :5001) and the
  agent self-building pipeline (`code_guard.py`, `dynamic_skills.py`,
  `feature_builder.py`) are unchanged.
- Production deploy = Vercel building ONLY `@workspace/terminal`
  (`PORT=4173 BASE_PATH=/ pnpm --filter @workspace/terminal run build`).
- `DynamicPanel` fallback still renders any panel type not explicitly cased.

## New behavior
- `PanelType` enum in `openapi.yaml` reconciled from 30 -> 79 types: the union of
  spec + every `case` rendered in `PanelContainer.tsx` + every `SkillDef` panel_type
  registered in `skills.py`.
- Generated clients (`lib/api-zod`, `lib/api-client-react`) regenerated from spec
  via `pnpm --filter @workspace/api-spec run codegen` so types match reality.
- `artifacts/launch-video/tsconfig.json` gains `"lib": ["es2022","dom","dom.iterable"]`
  to match the other browser apps (it uses `window`/canvas APIs).

## Verification plan / commands
- `pnpm run typecheck`  (full monorepo typecheck) -> must exit 0
- `PORT=4173 BASE_PATH=/ pnpm --filter @workspace/terminal run build` -> prod build, exit 0

## Risks
- Spec enum is now the authoritative list; any future panel must be added here
  and codegen re-run (this is the intended guardrail, not a regression).
- The non-prod sandbox apps (`mockup-sandbox`, `launch-video`) still require a
  `PORT` env at `vite build` time — pre-existing, not in the prod path.

## Done criteria
- Typecheck exit 0, prod build exit 0 (recorded under `.verification/runs/`).
- Contract drift closed: spec/zod/react PanelType all carry the same 79 types.
- Committed and pushed to `main`.
