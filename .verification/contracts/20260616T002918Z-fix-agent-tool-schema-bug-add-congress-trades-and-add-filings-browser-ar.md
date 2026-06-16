# Verification Contract: fix-agent-tool-schema-bug-add-congress-trades-and-add-filings-browser-ar

Created: 2026-06-16T00:29:18.367944Z
Repo: `/root/doomberg`

## Goal
Fix agent tool-schema bug: add_congress_trades and add_filings_browser are merged into one function dict in app/agent.py _tools(), so add_congress_trades is dropped from the LLM tool catalog and unreachable. Split into two separate function tool dicts. Preserve all other tools and behavior. Verify _tools() exposes both add_congress_trades and add_filings_browser with correct params.

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
