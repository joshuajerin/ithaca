# Verification Contract: deploy-doomberg-saber-vercel

Created: 2026-06-15T23:19:04Z
Repo: `/root/doomberg`

## Goal
Deploy the existing Doomberg project from `/root/doomberg` to Vercel under the Saber team/account (`sabers-projects-2821dd35`) and bind the production domains `doomberg.me` and `www.doomberg.me`.

## Existing behavior to preserve
- Do not change application source code for this deployment pass.
- Preserve the GitHub remote `https://github.com/joshuajerin/doomberg.git` and local `main` checkout.
- Preserve existing DNS records that already point `doomberg.me`/`www.doomberg.me` at Vercel.

## New behavior / change
- Vercel CLI is authenticated.
- A Vercel project named `doomberg` exists under Saber’s Vercel team/account.
- A production deployment exists and serves the built Doomberg frontend.
- `doomberg.me` and `www.doomberg.me` are attached to the `doomberg` Vercel project and resolve to the deployed production site once external DNS caches expire.

## Verification plan
Deterministic commands to run before final answer:
- `PORT=4173 BASE_PATH=/ pnpm --filter @workspace/terminal run build`
- `vercel project inspect doomberg --scope sabers-projects-2821dd35`
- `python`/`requests` smoke check that `https://doomberg-woad.vercel.app` returns HTTP 200 and contains `Agentic Terminal`.
- `curl -k -I --resolve doomberg.me:443:76.76.21.21 https://doomberg.me` should show HTTP 200 and `server: Vercel`.
- `curl -k -I --resolve www.doomberg.me:443:76.76.21.21 https://www.doomberg.me` should show HTTP 200 and `server: Vercel`.
- DNS checks against public resolvers should show `doomberg.me` A `76.76.21.21` and `www.doomberg.me` CNAME `cname.vercel-dns.com`.

## Tests / checks added or identified
- No source tests were added because this task is a deployment/account/domain operation, not an application behavior change.
- Characterization/smoke checks are used instead: Vite production build, Vercel project inspection, production alias HTTP 200/body check, custom-domain forced-DNS HTTP header checks.

## Risks
- Local/default resolver may keep stale Namecheap parking records temporarily even after authoritative/public DNS is correct.
- GitHub auto-deploy connection is not active unless the Saber Vercel account adds a GitHub login connection; CLI reported that GitHub connection is missing.
- The deployed artifact is the static frontend build from `artifacts/terminal/dist/public`; backend `/api` behavior was not converted to Vercel serverless in this pass.
- Vercel’s unique deployment URL may be protected by team deployment protection while the production alias/custom domains remain publicly accessible.

## Done criteria
- Saber-owned Vercel project `doomberg` exists.
- Production deployment URL returns 200 and contains the expected app title.
- `doomberg.me` and `www.doomberg.me` are attached to the project and, when forced to Vercel DNS, return HTTP 200 from Vercel.
- Evidence is recorded under `.verification/runs/`.
- Independent verifier returns `APPROVE`, or final answer reports its verdict and gaps honestly.
