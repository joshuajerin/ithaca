# Verification Contract: kural-doomberg-shared-vercel-supabase-hermes

Created: 2026-06-15T23:28:53Z
Repo: `/root/doomberg`

## Goal
Deploy Kural on the same Saber Vercel project/GitHub repository as Doomberg, attach `kural.website`/`www.kural.website` alongside `doomberg.me`/`www.doomberg.me`, connect GitHub auto-deploy when Vercel permissions allow, and add a shared Supabase-backed Hermes AI-call setup modelled on the existing Cloudflare custom endpoint.

## Existing behavior to preserve
- The Doomberg terminal frontend must continue to build and render from `artifacts/terminal`.
- Existing `vercel.json` behavior for static deployment must not regress unless replaced with an equivalent production deployment.
- Existing local Hermes custom endpoint `/portfolio-website` must not be broken or have its secrets exposed.
- Existing Python API modules under `artifacts/api-server/app` must keep importing successfully.
- No real secrets are committed to git; docs/config templates may contain placeholders only.

## New behavior / change
- Vercel Saber project `doomberg` has both Doomberg and Kural domains attached where the CLI/API permits it.
- Repo contains a clear shared environment/config contract for one Supabase project used by both hostnames.
- Repo contains a Vercel-serverless Hermes proxy pattern that mirrors the current Cloudflare/tunnel setup: browser calls Vercel API route, Vercel authenticates to the Hermes custom endpoint using server-side env vars, and no Hermes key is exposed client-side.
- Repo contains Supabase schema/seed documentation or migrations for domain/app isolation within the same Supabase database.
- Smoke checks cover the Vercel/Hermes proxy input validation without requiring live secrets.

## Verification plan
Deterministic commands to run before final answer:
- `pnpm --filter @workspace/terminal run build`
- `python -m compileall -q artifacts/api-server/app`
- Any added smoke tests/scripts for Vercel AI proxy and Supabase schema files.
- Vercel CLI domain/project checks (`vercel project inspect`, `vercel domains inspect`, `curl`) where network/account permissions allow.

## Tests / checks to add or identify
- Add a Node smoke check for the Vercel AI proxy route, using mocked `fetch` and dummy env vars, to prove auth/header forwarding and error handling without calling live Hermes.
- Add SQL/schema file validation via simple grep/parse checks if no database credentials are available.
- If GitHub/Supabase account operations are blocked by missing OAuth/credentials, record exact CLI output and verify all local code/config artifacts instead.

## Risks
- Vercel GitHub auto-deploy requires a GitHub Login Connection in the Saber Vercel account; CLI cannot bypass missing integration permissions.
- Adding the same domain to multiple Vercel projects can fail if currently owned/assigned elsewhere.
- Supabase production changes require project credentials/service role and must not be guessed.
- Hermes endpoint secrets must remain server-side only; exposing them as `VITE_` env vars would leak keys.
- Cloudflare trycloudflare URLs can rotate; production Vercel env should use the current tunnel URL or a stable Cloudflare Tunnel hostname if configured.

## Done criteria
- Saber Vercel domain/project/GitHub state has been attempted and verified with exact commands/output.
- Local repo contains deployable shared Supabase/Hermes integration artifacts with no committed secrets.
- Build/smoke checks pass and evidence is recorded under `.verification/runs/`.
- Independent verifier returns `APPROVE`; if blocked, final answer says blocked and why.
