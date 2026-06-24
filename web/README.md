# @doomberg/web — observability surface

React + Vite + TS. NO chat console — the "conversation" is the agent trace. Speaks the thin
rest-gateway REST/SSE only (never MCP directly).

## Screens (left rail)

- **Runs** — the centerpiece. Three columns: reasoning rail (collapsible, often empty for BYO
  agents) | tool-call timeline (the spine, built from the SSE `TraceEvent` stream via a pure
  reducer) | evidence panels (keyed by a static `panelType` registry). Subscribes to
  `/api/runs/{id}/events` via `EventSource` and renders live; a scrubber replays the fetched
  events seq-by-seq. Denials/errors surface honestly on the audited path. Paper runs that are
  promotable show a human-only **Promote** button (proxied to the control plane).
- **Deploys** — Backtests / Paper tabs. Each deploy card renders the equity curve (SVG),
  top stats, and the risk badge (gross/net/maxName + violations + relaxed flag).
- **Trades** — paper fills harvested across runs (display-only ledger).
- **Ideas** — proposed strategy specs from `StrategyStore`.

## Panel registry (no eval)

`src/panels/registry.tsx` is a STATIC `panelType -> component` lookup. No `eval`, no `sucrase`,
no dynamic import of agent-authored code (the v1 RCE lesson). `backtest` -> `BacktestPanel`;
everything else -> the generic JSON/table `JsonPanel`.

## The reducer

`src/timeline.ts` — pure `applyEvent` / `reduceEvents` / `reduceUpTo`. The SSE hook accumulates
raw ordered events; both live view and the replay scrubber derive the three lanes from the same
list. Tested in `src/timeline.test.ts` (`pnpm --filter @doomberg/web test`).

## Run it

```bash
pnpm --filter @doomberg/web dev      # http://localhost:5173, proxies /api -> :8000
pnpm --filter @doomberg/web build    # tsc -b && vite build (typecheck + bundle)
pnpm --filter @doomberg/web test     # vitest
```

### Config (`src/config.ts`, env overrides)

- `VITE_API_BASE` — API base. Default `/api` (the Vite dev proxy forwards to the gateway).
- `VITE_API_PROXY` — dev proxy target. Default `http://localhost:8000`.
- `VITE_TENANT_ID` — `X-Tenant-Id` sent on every request (the hard isolation key).
  Default `00000000-0000-0000-0000-000000000001`.

`EventSource` can't set headers, so production streams first mint a short-lived
`/api/runs/{id}/events-ticket` over authenticated REST and pass only that one-time ticket to
the SSE URL. Local dev can still fall back to `?tenant_id=`.
