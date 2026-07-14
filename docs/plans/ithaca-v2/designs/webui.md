# Design: Web UI / Observability Surface

Stack confirmed: React + Vite + Tailwind + framer-motion + recharts, monorepo with `@workspace/api-client-react`. I have all I need to write the design doc. Returning it now as my final output.

---

# Ithaca v2 Web UI — Observability Surface Design

## 0. Framing: what changed and what the UI is now

v1's UI was the *front-end of an agent that lived inside Ithaca*. The user typed into a chat console (`ChatPanel`), Ithaca's own orchestrator picked skills, generated a `DashboardSpec`, and the UI rendered panels — sometimes by **compiling AI-authored TSX in the browser** (`registry.ts` → `sucrase` → `new Function`, the RCE the architecture review flagged).

v2 inverts this. **Ithaca does not run the agent.** The user's own agent (Claude/GPT/custom) connects over MCP, discovers tools, calls them, and reasons. Ithaca's job is to **observe that external activity and render it** — the agent's thought process, each tool call and its result, the algos/strategies it proposes, what gets deployed, and the live P&L. The UI is a **read-mostly observability + control surface**, fed by a thin REST/SSE layer over the same core the MCP server uses. The chat box is gone; the "conversation" is now the **agent trace**.

The single most reusable asset from v1 is the **~79 panel components** (`artifacts/terminal/src/components/terminal/panels/`). They are pure `({ data }) => JSX` Recharts/typography renderers (verified: `BacktestPanel`, `TradeFlowPanel`, `PerformancePnlPanel` take a `data` prop and draw — no orchestration coupling). In v2 they stop being "what the AI laid out on a grid" and become **result-renderers for tool outputs**: tool `backtest.run` returns data → render `BacktestPanel`. That mapping is the backbone of the whole design.

---

## 1. Information Architecture

A persistent left rail switches between six top-level views. A global header carries: connected-agent status (the MCP session indicator), the active **Run** selector, and environment (paper/live) badge. No chat console anywhere.

```
┌── Ithaca v2 ───────────────────────────────────────────────┐
│ [agent: Claude ● connected]   Run: research-NVDA-0617 ▾   PAPER │
├──────────┬───────────────────────────────────────────────────┤
│ ▸ Runs    │                                                    │
│ ▸ Algos   │             ACTIVE VIEW                            │
│ ▸ Deploys │                                                    │
│ ▸ Trades  │                                                    │
│ ▸ Ideas   │                                                    │
│ ▸ Boards  │                                                    │
└──────────┴───────────────────────────────────────────────────┘
```

**1.1 Agent-Run Observability view (`/runs/:runId`) — the centerpiece.** A live (and replayable) timeline of one agent run: its reasoning stream on the left, a tool-call timeline in the middle, and the **panel(s)** each tool call produces on the right. This is where the user *watches their agent think and work*. Detailed in §2.

**1.2 Algos / Strategies view (`/algos`).** A library of strategy definitions the agent has authored or the user has saved. Each algo is a **declarative spec** (not generated code — see security note): entry/exit rules, parameters, universe, factor weights. Card grid → detail view embedding v1's `BacktestPanel`, `WalkForwardPanel`, `MonteCarloPanel`, `TearSheetPanel`, `FactorAttributionPanel` as result renderers. Actions: *Backtest*, *Deploy (paper)*, *Fork*, *Diff versions*.

**1.3 Deployments view (`/deploys`).** Two tabs over the **fresh-built control plane** (DigitalOcean runtime):
- **Backtests** — historical runs, queued/running/done, each opening a tear-sheet (`TearSheetPanel`, `PerformancePnlPanel`, `WalkForwardComparePanel`).
- **Paper-Live** — strategies running live on real market data, filling against the simulated book. Per-deployment: status (provisioning/running/halted), live equity curve (`PerformancePnlPanel`), open risk (`RiskMonitorPanel`, `PortfolioRiskPanel`), DO node health, kill switch. P&L streams in over SSE.

**1.4 Trades / Positions view (`/trades`).** The simulated book: open positions, fills, exposure. Renderers: `PerformancePnlPanel`, `PortfolioRiskPanel`, `TradeFlowPanel`, `OrderBookPanel`, `RebalancePlanPanel`. Every trade row links back to *the run + the tool call + the algo* that produced it — full provenance.

**1.5 News / Ideas feed (`/ideas`).** A streaming feed of candidate ideas the agent surfaced (news hits, insider clusters, screen results it flagged as interesting) but hasn't acted on. Renderers: `NewsPanel`, `SentimentPanel`, `InsiderActivityPanel`, `CongressTradesPanel`, `ScreenerPanel`, `EarningsCalendarPanel`. Each idea card → "Open in run" to see the reasoning, or "Hand to agent" (writes a note the agent can pick up via a tool).

**1.6 Boards (`/boards`).** User-configured dashboards (§4.2). Repurposes v1's `SavedDashboardsModal` + layout engine, but boards now subscribe to **live data streams / deployment metrics**, not one-shot agent output.

---

## 2. THE CENTERPIECE — visualizing an external agent's reasoning + tool calls

### 2.1 The data we observe

Because Ithaca is the MCP server the agent calls, **every tool call is an observation point** with no extra agent cooperation required. For each call we capture an envelope:

```ts
interface TraceEvent {
  runId: string;
  seq: number;                 // monotonic ordering within a run
  ts: string;
  kind: "thought" | "tool_call" | "tool_result" | "decision" | "error" | "status";
  // tool_call
  tool?: string;               // e.g. "fundamentals.get", "backtest.run"
  args?: Record<string, unknown>;
  callId?: string;             // correlates call ⇄ result
  // tool_result
  status?: "ok" | "error" | "partial";
  panelType?: string;          // which v1 renderer draws this result
  data?: unknown;              // the renderable payload (same shape v1 panels eat)
  durationMs?: number;
  // thought / decision — only present if the agent volunteers reasoning
  text?: string;
  citesCallIds?: string[];     // which tool calls this reasoning leaned on
}
```

`thought`/`decision` events are **best-effort**: a BYO agent may or may not stream its reasoning. The UI must be *legible with tool calls alone* and *richer when reasoning is present* — never assume reasoning exists. (Where the agent supports it, MCP `notifications` / a `reasoning` tool the agent opts into feeds these; otherwise the timeline is purely the observable tool-call sequence.)

### 2.2 The three-column trace UI

```
┌ REASONING ─────────┬ TIMELINE ──────────────┬ EVIDENCE (panels) ──────┐
│ "I want to know if │ ● fundamentals.get     │ ┌─ FundamentalsPanel ──┐ │
│  NVDA's margins     │ │  NVDA            120ms│ │  rev +22% · GM 73%   │ │
│  justify the multi- │ ●─news.search          │ └──────────────────────┘ │
│  ple, so I'll pull  │ │  "NVDA datacenter"    │   ↑ pinned by reasoning  │
│  fundamentals and   │ ●─insider.activity     │                          │
│  recent news…"      │ │  NVDA          ⚠ slow │ ┌─ NewsPanel ──────────┐ │
│                     │ ●─backtest.run         │ │  8 headlines…        │ │
│ ▸ "Momentum looks   │ │  momentum/NVDA  2.3s  │ └──────────────────────┘ │
│   strong → backtest"│ ◐ running…             │                          │
└─────────────────────┴────────────────────────┴──────────────────────────┘
        ◀── replay scrubber ───────●───────────────── 00:42 / LIVE ──▶
```

**Left — Reasoning rail.** The agent's narrated thought process as a vertically scrolling stream of `thought`/`decision` cards, word-by-word as deltas arrive (reuse v1's SSE delta-accumulation loop from `Terminal.tsx` `streamCommand` — the `data:`-line parser is directly portable). Each card can cite the tool calls it depends on; hovering highlights those rows in the timeline (the inverse of v1's navigator highlight, repurposed). If the agent emits no reasoning, this rail collapses and the timeline widens.

**Middle — Tool-call timeline.** The spine. One row per `tool_call`, in `seq` order, each showing tool name, key args, a live status dot (queued ◌ / running ◐ / ok ● / error ⊗ / slow ⚠), and duration. This is where the **deadline/timeout lessons** from the architecture review surface visually: a call exceeding its per-call budget shows ⚠, and the run header shows an **aggregate run deadline** bar (the review called out "per-call timeouts but no aggregate deadline" — make the aggregate first-class in the UI so a runaway run is obvious). Clicking a row scrolls Evidence to that call's panel.

**Right — Evidence column = the tool-call→panel mechanic.** This is the load-bearing reuse of v1. When a `tool_result` arrives:

```
tool_result.panelType ──lookup──▶ PANEL_REGISTRY[panelType] ──render──▶ <BacktestPanel data={result.data}/>
```

The mapping is exactly v1's `PanelContainer` switch (lines 309–404), **lifted out into a static `Map<panelType, Component>`** and reused verbatim. The agent's tool defines a `panelType` + a `data` shape that matches the renderer's existing contract. A panel **pops into the Evidence column the instant its result lands**, with an entrance animation (reuse `PANEL_MOTION` from `Dashboard.tsx`), and a connector line/anchor back to its timeline row. Panels the reasoning explicitly cites get "pinned" to the top; others stack chronologically. This makes the abstraction concrete: *a tool call is a question, the panel is the answer, the reasoning is why it was asked.*

### 2.3 Live vs. replay — one component, two clocks

The trace is **event-sourced** (`TraceEvent[]` keyed by `seq`). That gives replay for free:
- **Live**: subscribe to `GET /api/runs/:id/events` (SSE); append events; auto-scroll all three columns; status dots animate.
- **Replay**: load the full event log via REST; a **scrubber** at the bottom drives a "playhead" `seq`. The same render path filters to `event.seq <= playhead`, so reasoning, timeline, and panels all rewind/fast-forward together. Play/pause/step. Because rendering is a pure function of `(events, playhead)`, live is just "playhead pinned to the latest seq."

A small **run minimap** (sparkline of tool-call density + error markers over time, reuse v1's `Sparkline`) sits above the scrubber for jumping to interesting moments (errors, the decision point, the deploy).

### 2.4 How it reads to a human

The story a watcher should be able to read top-to-bottom: *"My agent wanted X → it called these 4 tools → here's what each returned → it concluded Y → it proposed/deployed this algo."* The reasoning rail gives the *why*, the timeline gives the *what/when/how-long*, the evidence column gives the *result*, and a terminal `decision` event links straight into the Algos or Deployments view (e.g. "Agent deployed `momentum-NVDA` to paper → open deployment").

---

## 3. v1 components: KEEP / REPURPOSE / DROP

### KEEP & REPURPOSE as tool-output renderers (high value)
All ~79 quant/data panels — they are clean `({data}) => JSX`:
- **Charts/quant**: `PriceChartPanel`, `IntradayChartPanel`, `BacktestPanel`, `WalkForwardPanel`, `WalkForwardComparePanel`, `MonteCarloPanel`, `TearSheetPanel`, `PerformancePnlPanel`, `FactorAnalysisPanel`/`FactorAttributionPanel`/`FactorExposurePanel`/`FactorPerformancePanel`, `CorrelationMatrixPanel`, `PortfolioOptimizerPanel`, `RiskModelPanel`/`RiskMonitorPanel`/`PortfolioRiskPanel`, `StressTestPanel`, `ScenarioPanel`, `BrinsonPanel`, `IVSurfacePanel`/`VolTermStructurePanel`/`OptionsChainPanel`/`OptionsStrategyPanel`, `DCFPanel`, `StructuredProductPanel`, `CDSPricerPanel`, `YieldCurvePanel`, `BondRVPanel`.
- **Data/feed**: `NewsPanel`, `SentimentPanel`, `FundamentalsPanel`, `ScreenerPanel`, `HeatmapPanel`, `InsiderActivityPanel`, `CongressTradesPanel`, `InstitutionalHoldersPanel`/`InstitutionalFlowsPanel`, `EarningsCalendarPanel`, `TranscriptPanel`, `AnalystRatingsPanel`/`AnalystReportPanel`/`AnalystComparePanel`, `FilingsBrowserPanel`, `ETFHoldingsPanel`/`ETFExposurePanel`, `EconomicReleasesPanel`, `MacroDashboardPanel`, `TradeFlowPanel`, `OrderBookPanel`.
- **Strategy/exec**: `StrategyDeskPanel`, `MultiStrategyPanel`, `RebalancePlanPanel`, `CombinedAlphaPanel`, `SignalScorecardPanel`/`SignalResearchPanel`/`SignalPortfolioPanel`, `TCAPanelReport`, `CompliancePanel`.

**Repurpose change to make:** strip the per-panel **`Refine`/`Settings2` input and the `onRefine`/`useRefinePanel` round-trips** from `PanelContainer`. Refinement was the user nudging Ithaca's own agent — that's gone. Panels become **display-only** (with read-only controls like chart-range tabs kept, but they re-query the REST layer, not "ask the AImore"). Lift the `panel.type` switch into a static registry `Map`.

**Reuse the layout/board infra:** `lib/layout.ts` (`resolvePanelLayouts`, the reserve-then-reflow grid), `Dashboard.tsx` grid + resize, `SavedDashboardsModal`, `Sparkline`, `CoverageBadge`, `panelExport.ts` (CSV/PDF), the SSE delta-parser in `Terminal.tsx`, `AlertsNotifications`. The responsive 12/6/1-column logic is solid — keep it for Boards.

### DROP
- **Chat console** — `ChatPanel.tsx`, `useConsoleConversation.ts`, the whole `handleCommand`/`streamCommand`/`orchestrate` command path in `Terminal.tsx`. No chat in v2.
- **Voice mode** — `VoicePanel.tsx`, `VoiceOrb.tsx`, `useVoiceConductor.ts`, `useSpeechRecognition.ts`, `voiceSettings.ts`, `/speak` + `/transcribe` clients. Out of scope for an observability surface.
- **Navigator/tour** — `NavigatorCursor.tsx`, `useNavigator.ts`, `/navigate`, the `NAV_INTENT`/`tourSubject` machinery. The "auto-cursor walkthrough" was a demo gimmick for the monolithic agent. **Salvage only the highlight mechanic** (`onHighlight`/`highlightedPanelId`) — repurpose it so hovering a reasoning card or timeline row highlights the linked panel.
- **🔴 SECURITY HOLE — DROP ENTIRELY: `panels/generated/` (`registry.ts`, `DynamicPanel.tsx`, `GeneratedPanel.tsx`) and the `sucrase` dependency.** `registry.ts` fetches arbitrary TSX from `GET /api/generated-panels`, transpiles it, and runs it via `new Function(...)` in the user's browser — a remote code execution path (matches the "runtime AI codegen path (it had critical RCEs)" the brief and review call out). v2 must have **no client-side codegen/eval**. Tool outputs map to a **fixed, vendored registry of renderers** only. If a tool returns a `panelType` with no registered renderer, fall back to a **safe, static JSON/table viewer** (a sanitized rewrite of `GeneratedPanel`'s generic renderer — pure data display, zero eval). Adding a new renderer is a code change that ships through review, never a runtime fetch.
- **`FeatureRequestModal` / `AdminConsoleModal` / `AuditLogModal`** as-is — these belong to v1's "build a feature" codegen flow and its multi-tenant admin. v2 keeps an **audit log view** (it's even more important now — see §4.3) but rebuilt against the v2 control plane, not ported.

---

## 4. Consuming the thin REST/SSE layer (NOT MCP directly)

### 4.1 Why and how
The browser **never speaks MCP**. MCP is the agent's interface. The web UI reads from a thin REST/SSE facade over the *same core* that backs the MCP tools — so the UI and the agent see a consistent world, but the UI gets a stable, queryable, **tenant-scoped** HTTP surface.

```
External Agent ──MCP(tools)──▶ ┌─────────────┐ ──persists──▶ event store / book / deploy state
                               │ Ithaca    │
Web UI ──REST(read)+SSE(live)──▶│  CORE       │
                               └─────────────┘
```

Endpoint sketch (all tenant-scoped by an auth-derived `firmId`, never a client-supplied one — see §4.3):
- `GET /api/runs`, `GET /api/runs/:id` — run metadata + event log (for replay).
- `GET /api/runs/:id/events` *(SSE)* — live `TraceEvent` stream.
- `GET /api/algos`, `GET /api/algos/:id` — strategy specs + version history.
- `GET /api/deploys`, `GET /api/deploys/:id`, `GET /api/deploys/:id/metrics` *(SSE)* — live P&L/risk/node health.
- `POST /api/deploys/:id/halt` — kill switch (one of the few **writes**; everything else is read).
- `GET /api/positions`, `GET /api/trades`, `GET /api/trades/stream` *(SSE)*.
- `GET /api/ideas`, `GET /api/ideas/stream` *(SSE)*.
- `GET /api/boards`, `PUT /api/boards/:id`, `GET /api/series/:key` *(+ SSE)* for board widgets.

Keep v1's pattern: a generated **`@workspace/api-client-react`** package with typed hooks (`useRuns`, `useDeploy`, `useAlgo`) wrapping TanStack Query for REST, plus thin SSE subscription hooks. Reuse v1's robust SSE parser (the `data:`-chunk reader in `Terminal.tsx`) as the shared transport for *all* live streams (`useEventStream<T>(url)`).

### 4.2 Dashboard configurability
Boards (§1.6) let the user assemble a watch-surface: pick which renderers to pin (a deployment's equity curve, the ideas feed, a specific run's evidence column, a positions table), arrange them on the reused 12-col grid, and persist via `PUT /api/boards/:id` (extends `SavedDashboardsModal`). Each widget declares a data source `{ kind, params }` resolved to a REST query + optional SSE subscription, so a board is **live** — it isn't a frozen snapshot of agent output like v1. A user can set a default board (e.g. "my paper deployments + P&L + open positions") that loads on launch, cached like v1's heavy default dashboard.

### 4.3 Carrying the architecture-review lessons into the UI/API seam
- **Tenant isolation as an invariant, not per-call-site.** `firmId` is derived once from the session at the API boundary and applied as a mandatory filter in the data layer — the UI cannot pass it, cannot widen it. Every endpoint above is implicitly `WHERE firm_id = session.firmId`.
- **Aggregate deadlines are visible.** The run header shows the aggregate run-deadline budget, not just per-tool spinners — directly answering the review's "per-call timeouts but no aggregate deadline."
- **No static-guard-then-trust.** The dropped codegen path was exactly that pattern (guard the `require` shim, then trust the eval). v2's renderer registry is a closed set; there is nothing to "guard then trust."
- **Audit view rebuilt.** Because the agent is external and untrusted, the run event log *is* the audit trail. The audit view (replacing v1's `AuditLogModal`) reads `TraceEvent`s and the immutable deploy/halt actions — every tool call, arg, and state change is attributable.

---

## 5. Tech stack, state model, live updates

**Stack — keep v1's, minus the hole.** React + Vite + TypeScript + Tailwind + framer-motion + Recharts, in the existing pnpm workspace with `@workspace/api-client-react`. **Remove `sucrase`** (and `html2canvas-pro`/`jspdf` stay only if export is retained). Add `react-router` for the six top-level views (v1 was effectively single-screen). Keep the editorial black/serif terminal aesthetic — it suits an observability surface.

**State model — three tiers:**
1. **Server cache (TanStack Query)** for all REST reads: runs, algos, deploys, positions, boards. Source of truth lives server-side; the client caches and invalidates.
2. **Event-sourced run state (local reducer):** a run is `TraceEvent[]` + a `playhead`. Render = pure `select(events, playhead)`. Live appends events and pins `playhead`; replay moves it. One reducer powers both modes — this is the key architectural simplification over v1's tangle of refs in `Terminal.tsx`.
3. **Ephemeral UI state (local `useState`/lightweight store):** which view, selected run, pinned panels, board edit mode, highlight target. A small Zustand store is warranted for cross-view selection (active run/deploy) since router + many panels read it; avoid v1's proliferation of `useRef`-mirrored state.

**Live updates — SSE everywhere, one hook.** A single `useEventStream<T>(url, onEvent)` built on v1's proven `data:`-chunk reader handles run traces, deploy metrics, trade fills, and idea feeds uniformly. SSE (not WebSockets) because the data is server→client, append-only, and reconnect/replay is trivial with `Last-Event-ID` (the `seq`). On reconnect, the client resumes from its last `seq`, and because rendering is `select(events, playhead)`, a gap-then-backfill is seamless. Deploy P&L and positions update the same way; the kill switch and board saves are the only client→server writes, done as plain REST mutations with optimistic UI + invalidation.

**Net effect:** the user opens Ithaca, sees their connected agent in the header, watches a run unfold across the three-column trace (reasoning → tool timeline → evidence panels reusing v1's quant renderers), follows a decision into Algos, deploys to paper, and watches live P&L stream into the Deployments and Trades views — all over a tenant-scoped REST/SSE layer, with zero chat, zero client-side codegen, and the agent's entire reasoning recorded as a replayable, auditable event log.

---

**Relevant files inspected (all absolute):**
- `/Users/joshuajerin/Desktop/jarvis/ithaca/artifacts/terminal/src/pages/Terminal.tsx` (command/voice/nav orchestration — mostly DROP; SSE parser KEEP)
- `/Users/joshuajerin/Desktop/jarvis/ithaca/artifacts/terminal/src/components/terminal/Dashboard.tsx` (grid + `PANEL_MOTION` — KEEP for Boards/Evidence)
- `/Users/joshuajerin/Desktop/jarvis/ithaca/artifacts/terminal/src/components/terminal/PanelContainer.tsx` (the `panel.type`→component switch, lines 309–404 — lift into static renderer registry; strip refine)
- `/Users/joshuajerin/Desktop/jarvis/ithaca/artifacts/terminal/src/components/terminal/panels/` (~79 renderers — KEEP)
- `/Users/joshuajerin/Desktop/jarvis/ithaca/artifacts/terminal/src/components/terminal/panels/generated/registry.ts` + `DynamicPanel.tsx` + `GeneratedPanel.tsx` (**RCE — DROP entirely; remove `sucrase`**)
- `/Users/joshuajerin/Desktop/jarvis/ithaca/artifacts/terminal/src/lib/layout.ts` (reserve-then-reflow grid — KEEP)
- `/Users/joshuajerin/Desktop/jarvis/ithaca/docs/reviews/architecture-review-2026-06-16.md` (lessons carried into §4.3)