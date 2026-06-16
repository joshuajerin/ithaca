# Verification Contract: kural-doomberg-consolidate

Created: 2026-06-16T00:32:36Z
Repo: `/root/doomberg`

## Goal
Consolidate Doomberg + Kural shared hosting on the existing `api/[...path].js`
catch-all serverless function: per-tenant Hermes endpoints
(doomberg → `/doomberg`, kural → `/kural`) with shared Supabase logging; remove
redundant standalone routes; deploy prebuilt to the Saber Vercel project because
remote builds hang at UNKNOWN (no build container).

## Existing behavior to preserve
- The Doomberg terminal frontend still builds from `artifacts/terminal` via
  `PORT=4173 BASE_PATH=/ pnpm --filter @workspace/terminal run build`.
- The catch-all API keeps serving every existing route the frontend calls:
  `/api/healthz`, `/api/auth/user`, `/api/auth/login|signup|logout`,
  `/api/skills`, `/api/sectors`, `/api/suggestions`, `/api/dashboard/default`,
  `/api/dashboards`, `/api/watchlist`, `/api/orchestrate`,
  `/api/orchestrate/stream`, `/api/ai`, `/api/navigate`, `/api/speak`,
  `/api/transcribe`.
- Host-based tenant detection still returns `doomberg` for doomberg.me and
  `kural` for kural.website.
- The local Hermes `/portfolio-website` endpoint and its secret are untouched.
- Python API modules under `artifacts/api-server/app` still compile.
- No real secrets committed to git.

## New behavior / change
- `callHermes` selects a per-tenant Hermes endpoint+key:
  doomberg → `${HERMES_BASE_URL}/doomberg` with `DOOMBERG_HERMES_KEY`,
  kural → `${HERMES_BASE_URL}/kural` with `KURAL_HERMES_KEY`.
- Falls back to the legacy single endpoint (`HERMES_AI_ENDPOINT` /
  `HERMES_AI_API_KEY`) when a per-tenant key is absent.
- `/api/healthz` reports the resolved per-tenant `hermesConfigured` boolean.
- Redundant standalone routes (`api/ai/*`, `api/health.js`, `api/_lib/*`,
  `artifacts/terminal/src/lib/aiClient.ts`) are removed; the catch-all is the
  single canonical implementation.
- Supabase migration `supabase/migrations/0001_shared_sites_schema.sql` matches
  the `ai_interactions` insert shape used by the code.

## Verification plan
Deterministic commands:
- `pnpm install`  (must exit 0 — see pnpm build-scripts pitfall below)
- `PORT=4173 BASE_PATH=/ pnpm --filter @workspace/terminal run build`
- `node scripts/smoke-ai-proxy.mjs`  (catch-all per-tenant routing, mocked fetch)
- `python3 -m compileall -q artifacts/api-server/app`
Live (already executed, recorded in this turn):
- `curl --resolve doomberg.me:443:76.76.21.21 https://doomberg.me/api/healthz`
  → `{"tenant":"doomberg","hermesConfigured":true}`
- `curl --resolve kural.website:443:76.76.21.21 https://kural.website/api/healthz`
  → `{"tenant":"kural","hermesConfigured":true}`
- `POST https://doomberg.me/api/orchestrate` → live Hermes /doomberg answer,
  degraded:false
- `POST https://kural.website/api/orchestrate` → live Hermes /kural answer,
  degraded:false

## Tests / checks added
- `scripts/smoke-ai-proxy.mjs`: imports the catch-all handler and, with a mocked
  global fetch (no live secrets), asserts:
  - healthz tenant detection for both hosts
  - orchestrate routes to `/kural` with `KURAL_HERMES_KEY` for kural.website
  - orchestrate routes to `/doomberg` with `DOOMBERG_HERMES_KEY` for doomberg.me
  - legacy fallback to `/portfolio-website` + `HERMES_AI_API_KEY`
  - unknown route → 404

## Risks
- pnpm 11 build-scripts: `pnpm install` exits 1 with ERR_PNPM_IGNORED_BUILDS for
  esbuild/core-js even when listed in `onlyBuiltDependencies`. Fix: run
  `pnpm rebuild esbuild core-js` once to clear the sticky `ignoredBuilds` state
  in `node_modules/.modules.yaml`; afterwards `pnpm install` exits 0. The
  package.json `pnpm` field is NOT read by pnpm 11.7 — the allowlist lives in
  `pnpm-workspace.yaml`.
- Remote Vercel builds hang at UNKNOWN on the Saber account → must use
  `vercel build` + `vercel deploy --prebuilt`.
- GitHub auto-deploy blocked: Saber Vercel account has no GitHub Login
  Connection. `vercel git connect` returns 400 until that's added in the UI.
- Supabase logging is inert until `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`
  are set (no token on this box). `supabaseConfigured:false` is expected.

## Done criteria
- All deterministic commands pass (exit 0) and are recorded under
  `.verification/runs/`.
- Live healthz + orchestrate verified on both hostnames (recorded above).
- Independent verifier returns `APPROVE`; if blocked, final answer says blocked
  and why.
