# Verification Contract: deploy-doomberg-vercel

Created: 2026-06-15T23:10:33.990373Z
Repo: `/root/doomberg`

## Goal
Deploy the existing doomberg GitHub project to Vercel and bind doomberg.me/www.doomberg.me so the website is live

## Existing behavior to preserve
- TODO: list behavior that must not regress.

## New behavior / change
- TODO: list the precise behavior this task must make true.

## Verification plan
Deterministic commands to run before final answer:
- `python -m compileall -q .`
- `python -m pytest -q`
- `pnpm run typecheck`
- `pnpm run build`

## Tests / checks to add or identify
- TODO: tests first when feasible; otherwise explain why and add a smoke/characterization check.

## Risks
- TODO: likely breakpoints, migrations, config, API compatibility, data loss, perf, security.

## Done criteria
- All relevant deterministic commands pass.
- Evidence is recorded under `.verification/runs/`.
- Independent verifier returns `APPROVE`; if blocked, final answer says blocked and why.
