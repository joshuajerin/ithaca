# Integrated Real-Time MCP Dashboard

## Goal

Rebuild `/dashboard` into a generic, warm, live operational board that shows what the platform and MCP sessions are doing. It should not be a hardcoded stock dashboard and should not use screenshots. It should adapt to recent session work such as "retail analysis" by surfacing the relevant prompt, tool calls, returned data, warnings, deployments, and strategy activity.

## Current State

- `web/src/App.tsx` routes `/dashboard` to `web/src/pages/Dashboard.tsx`.
- `web/src/pages/Dashboard.tsx` currently renders hardcoded market widgets such as `NVDA`, analyst ratings, news flow, and options flow.
- `web/src/api.ts` already exposes the needed REST calls: `listSessions`, `getSession`, `listRuns`, `listStrategies`, and `eventsUrl`.
- `web/src/hooks/useRunEvents.ts` already subscribes to run/session SSE events.
- `web/src/timeline.ts` and `web/src/sessionWorkflow.ts` already reduce trace events into workflow/tool items.

## Target Design

- `/dashboard` becomes a high-level live MCP/platform board.
- It derives content from sessions, the latest selected session detail, live SSE events, deployment runs, and strategies.
- It keeps the current warm visual palette and uses old Doomberg interaction ideas: compact panels, hover border changes, dense metadata, subtle pop-in animation, and clickable module rows.
- It does not import unsafe v1 dynamic/generated panel execution.

## Implementation

- Replace the current stock-focused `Dashboard.tsx` with an integrated dashboard model:
  - selected session = latest running session, otherwise latest updated session
  - merge persisted session events with live SSE events
  - reduce events into timeline/workflow items
  - derive tool calls, returned data, warnings, deployment summaries, and adaptive topic labels
- Add reusable local panel components:
  - `LivePanel`
  - `MetricTile`
  - `StatusDot`
  - compact rows for sessions, tools, returned data, deployments, and warnings
- Add `live-*` CSS classes in `web/src/index.css` so the dashboard is warm and interactive without relying on the old dark terminal CSS.

## Verification

Run:

```bash
pnpm --filter @doomberg/web typecheck
pnpm --filter @doomberg/web build
pnpm --filter @doomberg/web test
```

Manual checks:

- `/dashboard` is clickable and interactive.
- It shows real platform sessions/runs/strategies from REST.
- It subscribes to the latest session when one exists.
- A session title/prompt like "retail analysis" appears as the active dashboard context.
- No screenshots are embedded.
- The page uses the warm palette, not a pure black/white terminal theme.
