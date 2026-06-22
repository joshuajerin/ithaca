# Plan: Dashboard and Sessions UI

Status: proposed, awaiting approval. No implementation has been done yet.

## Goal

Redesign the authenticated app around a warm, light Doomberg dashboard while preserving the dense terminal/observability feel.

The left nav should become:

- New Session
- Dashboard
- Sessions
- Docs
- Settings

After login, `/` should open `/dashboard`. The Sessions area should show MCP workflow traces in real time: the user prompt, the tool/skill calls, outputs returned, deployed/backtest/paper actions, and the full prompt/workflow record for one session.

## Current State Found

- [web/src/App.tsx](/Users/joshuajerin/Desktop/jarvis/doomberg/web/src/App.tsx) currently defines the nav as `Runs`, `Deploys`, `Trades`, `Ideas`, `Settings`, and redirects `/` to `/runs`.
- [web/src/index.css](/Users/joshuajerin/Desktop/jarvis/doomberg/web/src/index.css) is explicitly a black terminal theme: black background, mono labels, sharp borders, white foreground, compact tables, and a three-column run layout.
- [web/src/pages/RunDetail.tsx](/Users/joshuajerin/Desktop/jarvis/doomberg/web/src/pages/RunDetail.tsx) already has the core session detail shape: reasoning column, tool timeline column, evidence column, live EventSource updates, and a replay scrubber.
- [web/src/pages/RunsList.tsx](/Users/joshuajerin/Desktop/jarvis/doomberg/web/src/pages/RunsList.tsx) lists all runs together. It does not filter to `kind=research`, so research sessions, backtests, and paper deployments are not separated for the user.
- [web/src/timeline.ts](/Users/joshuajerin/Desktop/jarvis/doomberg/web/src/timeline.ts) folds `tool_call` and `tool_result` by `span_id`, but renders a flat list. It preserves `parent_span_id`, so a connected workflow tree can be derived without changing the existing event contract.
- [web/src/hooks/useRunEvents.ts](/Users/joshuajerin/Desktop/jarvis/doomberg/web/src/hooks/useRunEvents.ts) subscribes to `/api/runs/:id/events` over SSE and keeps the ordered raw `TraceEvent[]`. This is the right source of truth for real-time session visualization.
- [web/src/panels/registry.tsx](/Users/joshuajerin/Desktop/jarvis/doomberg/web/src/panels/registry.tsx) is already a fixed renderer registry with JSON fallback. This matches the security model: no dynamic/eval panel code.
- [services/platform/src/doomberg_platform/run_store.py](/Users/joshuajerin/Desktop/jarvis/doomberg/services/platform/src/doomberg_platform/run_store.py) has `create_research`, which creates `kind="research"` rows for MCP activity.
- [services/mcp-gateway/src/doomberg_mcp/server.py](/Users/joshuajerin/Desktop/jarvis/doomberg/services/mcp-gateway/src/doomberg_mcp/server.py) opens a research run on first traced tool call and emits `session_open`, then `tool_call` / `tool_result` for MCP tools.
- [services/mcp-gateway/src/doomberg_mcp/trace.py](/Users/joshuajerin/Desktop/jarvis/doomberg/services/mcp-gateway/src/doomberg_mcp/trace.py) puts `session_id`, `origin_session_id`, `span_id`, and `parent_span_id` on events. `tool_result` currently stores compact summaries, not always full raw tool payloads.
- [services/mcp-gateway/src/doomberg_mcp/http.py](/Users/joshuajerin/Desktop/jarvis/doomberg/services/mcp-gateway/src/doomberg_mcp/http.py) only passes `tenant_id` and `agent_id` into the tool context. Hosted HTTP MCP does not currently propagate a per-conversation session id, so session grouping may be too broad.
- [services/rest-gateway/src/doomberg_rest/app.py](/Users/joshuajerin/Desktop/jarvis/doomberg/services/rest-gateway/src/doomberg_rest/app.py) exposes `GET /api/runs`, `GET /api/runs/:id`, and `GET /api/runs/:id/events`, but not first-class `/api/sessions` aliases yet.
- [services/rest-gateway/src/doomberg_rest/readmodel.py](/Users/joshuajerin/Desktop/jarvis/doomberg/services/rest-gateway/src/doomberg_rest/readmodel.py) shapes run trace lanes for non-web consumers and keeps raw `events` for the web reducer.
- [packages/contracts/schema/events.schema.json](/Users/joshuajerin/Desktop/jarvis/doomberg/packages/contracts/schema/events.schema.json) allows `session_open`, `reasoning`, `tool_call`, `tool_result`, `strategy_proposed`, lifecycle events, marks, fills, denials, errors, and arbitrary object data. This can carry prompt metadata inside `session_open.data` without a schema migration.
- [site/src/index.css](/Users/joshuajerin/Desktop/jarvis/doomberg/site/src/index.css) already defines the warm public-site palette: cream, paper, sand, ink, olive, amber, blueprint blue, and line colors.
- [docs/plans/doomberg-v2/designs/webui.md](/Users/joshuajerin/Desktop/jarvis/doomberg/docs/plans/doomberg-v2/designs/webui.md) already describes the intended v2 observability model: external agents call MCP, the browser reads REST/SSE, and the run trace is the audit surface.
- [history/v1/artifacts/terminal/src/components/terminal/panels](/Users/joshuajerin/Desktop/jarvis/doomberg/history/v1/artifacts/terminal/src/components/terminal/panels) contains 83 old terminal panel files. They can be reused selectively later, but this dashboard pass should not pull the whole v1 terminal into the current app.

## Product Shape

### App Shell

Replace the current rail with a session-first shell:

- `New Session` as a top rail action, visually stronger than the other links.
- `Dashboard` as the default route and selected page after login.
- `Sessions` for MCP workflow history and live traces.
- `Docs` for setup instructions, MCP endpoint, key usage, and tool catalog.
- `Settings` for account, integrations, and MCP key management.

Keep the existing signed-in user chip and sign-out affordance. Move API/tenant diagnostic text into Settings or a small dev-only rail footer so the production nav feels cleaner.

### Dashboard

Create `web/src/pages/Dashboard.tsx` as the first screen after auth.

The Dashboard should be a compact operator surface, not a marketing page:

- Active research sessions: latest `kind=research` runs with state, agent, prompt/title if captured, last event time, and call count.
- Recent workflow lane: last few tool calls across active/recent sessions.
- Deployment/activity summaries: reuse data from existing Deploys, Trades, and Ideas logic as dashboard modules rather than keeping them as top-level nav.
- MCP status: endpoint, active keys count or key state if available, and connection/realtime status.
- Empty state: show a direct path to New Session and Settings/MCP access, not a large explainer.

Use the current black/white terminal density as the interaction model: mono metadata, thin rules, compact rows, fast scanning, and no nested cards.

### Sessions List

Rename the user-facing concept from Runs to Sessions while keeping backend run ids.

Create or refactor to `web/src/pages/SessionsList.tsx`:

- Fetch `api.listRuns("research")`.
- Show research session rows with `Session`, `Prompt`, `Agent`, `State`, `Calls`, `Last event`, `Warnings`, and `Created`.
- Derive prompt/title from `session_open.data.prompt`, `session_open.data.userPrompt`, `run.spec.prompt`, or first user/reasoning event when present.
- Show a clear `Prompt not captured` state for older/current MCP traces where Doomberg did not receive the prompt.
- Link rows to `/sessions/:id`.

Keep old `/runs` and `/runs/:id` as redirects to `/sessions` and `/sessions/:id` for compatibility.

### Session Detail

Evolve `RunDetail` into `SessionDetail` rather than rewriting it.

Target layout:

- Top prompt box:
  - Example visible shape: `user: what does nvda look like`.
  - Shows captured user prompt, agent id, session id, status, and live/replay state.
- Main workflow area:
  - A connected tree/workflow view built from `TimelineNode.parent_span_id`, `span_id`, and sequence fallback.
  - Each node shows tool/skill name, key args, status, timestamp, and warning/freshness badges.
  - Selecting a node opens the exact call args plus returned result summary/output in the evidence pane.
  - Use connector lines and indentation for parent/child relationships; if no parent data exists, fall back to sequence-linked nodes.
- Side or lower panels:
  - Session memory: complete list of captured trace events for the session.
  - Tools called: unique tools/skills, counts, last status, last result summary.
  - Deployed/workflow outputs: strategy proposals, backtest runs, paper lifecycle transitions, marks, fills, denials, and errors.
- Bottom prompt drawer:
  - Shows the actual captured prompt and raw prompt metadata.
  - If prompt was not captured, show the session id and how to start/capture a prompt for new sessions.

Important wording: for existing traces, most MCP `tool_result` events currently contain compact provenance/result summaries, not full raw tool payloads. The UI should label this honestly as `returned summary` unless we add full payload persistence.

## Backend and Contract Work Needed

### Prompt Capture

Doomberg can observe MCP tool calls, but it cannot know the human's original prompt unless the UI or the agent sends it.

Add one first-class prompt capture path:

Option A, preferred for this UI pass:

- Add `POST /api/sessions` in the REST gateway.
- It creates a `kind="research"` run with `RunStore.create_research`.
- It appends a `session_open` event with `data.prompt`, `data.title`, `data.createdBy="web"`, and actor `{kind:"user"}`.
- It returns `{id, session_id, mcp_url, prompt}`.
- The New Session page uses this to create a visible session before MCP tools arrive.

Option B, useful for external agents:

- Add an MCP tool such as `session_context` or `session_note` that records the user prompt/title into the current research run.
- This lets a BYO agent voluntarily attach the prompt to the trace.

Option A gives the UI a concrete New Session flow. Option B improves BYO agent traces. They can be implemented together if scope allows.

### Session Grouping

Fix hosted MCP session grouping. Today `Principal.ctx()` returns only `tenant_id` and `agent_id`, so `Toolset._tracer` falls back to a process-level session key.

Implementation direction:

- Propagate the MCP transport/session identifier into `Principal.ctx()` when the SDK exposes it, or accept a caller-provided session id through the explicit `session_context` tool.
- Keep the stored event `session_id` as the UUID research run id because the event schema requires UUID format.
- Store raw agent session identifiers in `session_open.data.agentSession` as the code already does.

### Full Output vs Summary

Decide whether Sessions should show full tool outputs or compact results.

Current behavior:

- `market.get_ohlcv`, `backtest.run`, and archive skills return full envelopes to the agent.
- Trace events store `_provenance_summary(out)` for most MCP calls.

Recommended for first pass:

- Keep compact summaries for the tree and evidence preview.
- Add an expandable raw JSON pane for whatever is present in the trace.
- Do not claim old traces contain full payloads.

Possible later upgrade:

- Persist full result payloads in an artifact table keyed by `run_id`, `seq`, and `span_id`, while keeping trace events small.

## Frontend Implementation Plan

1. Add route/page structure.

   Files:

   - `web/src/App.tsx`
   - `web/src/pages/Dashboard.tsx`
   - `web/src/pages/SessionsList.tsx`
   - `web/src/pages/SessionDetail.tsx`
   - `web/src/pages/NewSession.tsx`
   - `web/src/pages/Docs.tsx`

   Changes:

   - Update nav order to New Session, Dashboard, Sessions, Docs, Settings.
   - Redirect `/` to `/dashboard`.
   - Redirect `/runs` to `/sessions`; redirect `/runs/:id` to `/sessions/:id`.
   - Keep Deploys, Trades, and Ideas available as internal dashboard sections or lower-priority routes only if needed.

2. Add session API helpers.

   Files:

   - `web/src/api.ts`
   - `web/src/types.ts`

   Changes:

   - Add `listSessions()` as `listRuns("research")`.
   - Add `getSession(id)` as a typed alias to `getRun(id)`.
   - Add `createSession(prompt, title?)` if the backend endpoint is implemented.
   - Add derived `SessionRow` / `SessionSummary` helpers if useful, but keep raw `RunRow` compatibility.

3. Build workflow tree selectors.

   Files:

   - `web/src/timeline.ts`
   - `web/src/timeline.test.ts`
   - Optional new file: `web/src/sessionWorkflow.ts`

   Changes:

   - Add a pure selector that converts `TimelineState.nodes` plus raw events into a tree:
     - root is session prompt/open event.
     - child links use `parent_span_id -> span_id`.
     - orphan nodes fall back to sequence order.
     - strategy/deploy/fill/mark/denial/error events appear as non-tool workflow nodes.
   - Add tests for parent/child nodes, orphan fallback, replay filtering, and tool result folding.

4. Refactor RunDetail into SessionDetail.

   Files:

   - `web/src/pages/RunDetail.tsx` to be renamed or copied into `SessionDetail.tsx`.
   - New focused components if the page gets too large:
     - `web/src/components/session/PromptBox.tsx`
     - `web/src/components/session/WorkflowTree.tsx`
     - `web/src/components/session/ToolResultPane.tsx`
     - `web/src/components/session/SessionMemory.tsx`

   Changes:

   - Keep `useRunEvents`, `reduceEvents`, replay scrubber, and `Panel`.
   - Replace flat `.tl-node` timeline with a connected workflow tree.
   - Add prompt top box and bottom prompt drawer.
   - Add tabs or sections for `Output`, `Args`, `Raw Event`, and `Session Memory`.
   - Preserve paper-run controls only when the selected linked run is paper; research sessions should not show money-path controls by default.

5. Build New Session.

   Files:

   - `web/src/pages/NewSession.tsx`
   - `web/src/api.ts`
   - Backend files if approved: `services/rest-gateway/src/doomberg_rest/app.py`, platform/control helpers as needed.

   First-pass UX:

   - Prompt textarea at bottom or center-lower area, terminal-like but warm.
   - Submit creates a research session and navigates to `/sessions/:id`.
   - Show MCP endpoint/session id instructions so the user's agent can attach calls.
   - If backend prompt capture is not approved, make the page a setup/copy prompt flow and do not pretend it starts an agent.

6. Add Docs page.

   Files:

   - `web/src/pages/Docs.tsx`

   Content:

   - MCP endpoint.
   - Required `Authorization: Bearer` usage.
   - How sessions are captured.
   - Tool catalog grouped by market data, fundamentals, options/vol, macro, congress/insider, portfolio/risk, backtest/deploy.
   - Link to Settings for key generation.

7. Apply warm terminal theme.

   Files:

   - `web/src/index.css`

   Token direction:

   - `--bg: #f6f1e4`
   - `--panel: #fffaf0` or `#ffffff`
   - `--panel-2: #f1e9d6`
   - `--fg: #1a1a14`
   - `--muted: #5f5d52`
   - `--muted-dim: #8a8a7e`
   - `--border: #ddd0b8`
   - `--border-soft: #e7dcc7`
   - `--accent: #485c11`
   - `--warn: #ef9f2a`
   - `--info: #2f6be5`

   Keep:

   - compact typography
   - mono metadata
   - thin borders
   - sharp or <= 8px radius elements
   - dense tables and workflow panes

   Avoid:

   - landing-page hero treatment inside the app
   - decorative gradient blobs/orbs
   - nested cards
   - a one-note beige-only palette

## Backend Implementation Plan

1. Add session creation endpoint.

   Files:

   - `services/rest-gateway/src/doomberg_rest/app.py`
   - Maybe `services/rest-gateway/tests/test_sessions.py`

   Endpoint:

   - `POST /api/sessions`
   - Body: `{prompt: string, title?: string}`
   - Auth: signed-in user or tenant credential through existing dependency path.
   - Behavior: create research run, append `session_open` event with prompt metadata, return shaped run/session row.

2. Add optional MCP session context tool.

   Files:

   - `services/mcp-gateway/src/doomberg_mcp/server.py`
   - `services/mcp-gateway/tests/test_research_session.py`

   Tool:

   - `session_context(prompt?: string, title?: string, session_id?: string)`
   - Emits or updates session metadata for the current research run.
   - Gives BYO agents a way to attach the actual user prompt.

3. Improve HTTP session grouping.

   Files:

   - `services/mcp-gateway/src/doomberg_mcp/http.py`
   - `services/mcp-gateway/src/doomberg_mcp/server.py`

   Direction:

   - Pass a stable per-agent-session key into Toolset context where possible.
   - If unavailable from FastMCP, use the explicit `session_context` call as the grouping key for subsequent calls in that process.
   - Add tests that two different external sessions for the same tenant/key become two research runs.

## Styling Acceptance Criteria

- The app feels like a warm Doomberg terminal: light paper shell, ink text, olive/amber/blue accents, dense workflow UI.
- Dashboard is the first screen after login.
- No oversized marketing hero, no explanatory in-app feature copy, no decorative blobs.
- Text fits on narrow widths; workflow nodes and nav labels do not resize layout on hover.
- Sessions tree remains usable on desktop and has a sane mobile fallback, likely stacked Prompt -> Workflow -> Output -> Memory.

## Verification Plan

Frontend:

- `pnpm --filter @doomberg/web test`
- `pnpm --filter @doomberg/web typecheck`
- `pnpm --filter @doomberg/web build`

Contracts:

- `pnpm run contracts:check`

Python/backend, if session endpoints or MCP tools are changed:

- `uv run pytest services/rest-gateway/tests`
- `uv run pytest services/mcp-gateway/tests`
- `uv run pytest services/platform/tests`

Manual QA after implementation:

- Sign in/demo login lands on `/dashboard`.
- Left rail shows New Session, Dashboard, Sessions, Docs, Settings in that order.
- New Session creates a session with prompt text and navigates to `/sessions/:id`.
- Sessions list shows only `kind=research` rows.
- A live MCP tool call appears in the session workflow without refresh.
- Replay scrubber reconstructs the same workflow at earlier sequence numbers.
- Selecting a tool node shows args, returned summary/output, raw event, and provenance/warnings.
- Old traces without prompt show an honest prompt-not-captured state.

## Risks and Decisions

- Prompt capture is the main product gap. Without it, the UI can only show prompts for new captured sessions or agent-volunteered metadata.
- Hosted MCP session grouping is currently too coarse. This should be fixed before marketing Sessions as per-conversation history.
- Full tool output is not currently persisted in every trace. The first UI pass should display the exact trace payload and call it a summary when it is a summary.
- Pulling all v1 terminal panels into the current app would increase scope. Start with the current static registry and add the most valuable v1 renderers only when a tool output needs them.
- `docs/strategy/` is already untracked in the working tree and appears unrelated; do not touch it during this UI work.

## Recommended First Implementation Slice

1. App shell/nav and `/dashboard` route.
2. Warm terminal CSS token pass.
3. Sessions list filtered to `kind=research`.
4. Session detail prompt box plus workflow tree derived from existing events.
5. Backend prompt capture via `POST /api/sessions`.
6. Tests for session filtering, tree selector, and backend session creation.

This gets the user-visible shape right without taking on the larger v1 panel migration or full payload artifact store in the first pass.
