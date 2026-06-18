# Doomberg v2 — System Architecture & Topology

> **Status:** Design (spine). This is the foundational architecture other v2 designs hang off.
> **Date:** 2026-06-16
> **Scope of this doc:** component map, end-to-end flows, the BYO-agent trace model, layer boundaries/contracts, and a stack recommendation per component.
> **Grounded in:** v1 code at `artifacts/api-server/app/` (engine, sources, strategy lifecycle, tenant context, worker, SSE) and `docs/reviews/architecture-review-2026-06-16.md`.

---

## 0. North star & the v1 lessons that shape this

Doomberg v2 is **not** an AI terminal. It is a **financial tool-platform** that *someone else's* agent plugs into. The user runs their own agent (Claude/GPT/custom); Doomberg gives that agent (1) a **Data Layer** of callable financial tools and (2) a **Deploy Layer** to backtest and run strategies paper-live — plus a web UI that *observes* the agent and renders what it's doing.

Two consequences drive every decision below:

1. **The agent is external and untrusted-as-a-client.** Doomberg never runs the agent loop and never executes agent-authored code in-process. (v1's single worst class of bug — two critical in-process RCEs — came from running LLM-authored code behind a static guard. v2 deletes that path entirely; see §6.)
2. **We must reconstruct a thought process we don't own.** The agent's reasoning happens inside the user's runtime. Doomberg can only see what crosses the wire: MCP tool calls, their arguments, their results, and whatever reasoning the agent volunteers. §3 is the hard problem and the heart of this doc.

The v1 review surfaced six recurring failure themes. Each maps to a **non-negotiable invariant** in v2:

| v1 failure theme | v2 invariant |
|---|---|
| Static-guard-then-trust → RCE | **No agent/LLM-authored code ever executes in a privileged process.** Strategies are *declarative specs*, not code (§4, §6). |
| "Never crash" swallowing erases audit trails | **Every tool call, run transition, and money-path mutation is an append-only event** with structured errors, never a silent `except: pass` (§3, §7). |
| Multi-tenant isolation per-store, not invariant | **`tenant_id` is carried in the auth/session boundary and enforced once at the data-access seam**, not re-implemented per call site (§4.5, §7). |
| Unlocked read-modify-write on the money path | **All book/run mutations go through the control plane in serialized transactions** (`SELECT … FOR UPDATE` / optimistic version), never racing upserts (§4.4). |
| Per-call timeouts but no aggregate budget | **Every run and every tool call has a wall-clock deadline**, enforced at the gateway and the runtime (§4, §7). |
| Tests exist but don't gate; tested path ≠ shipped path | **The MCP tool contract and the deploy state machine are the gated surfaces**, with golden contract tests in CI (§7). |

---

## 1. Component map

```
                          ┌────────────────────────────────────────────────────────┐
                          │                   USER'S MACHINE / CLOUD                 │
                          │   ┌──────────────────────────────────────────────────┐  │
                          │   │  BYO AGENT (Claude / GPT / custom) — agent loop    │  │
                          │   │  runs HERE. Doomberg does NOT host it.             │  │
                          │   └───────────────┬──────────────────────────────────-┘  │
                          └───────────────────│────────────────────────────────────-─┘
                                              │ MCP (stdio or streamable-HTTP)
                                              │ tools.list / tools.call  + optional emit_reasoning
                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│  DOOMBERG CONTROL REGION                                                                         │
│                                                                                                  │
│   ┌──────────────────────────┐        ┌───────────────────────────────────────────────────┐    │
│   │  (A) MCP SERVER           │        │  (B) REST / SSE GATEWAY                            │    │
│   │  PRIMARY agent interface  │        │  Serves the web UI; auth, sessions, SSE fan-out   │    │
│   │  - auth (token → tenant)  │        │  - REST reads (runs, traces, books, panels)       │    │
│   │  - session correlation    │◄──────►│  - SSE streams (trace + run telemetry)            │    │
│   │  - per-call deadline      │ shared │  - promote/accept/reject control actions          │    │
│   │  - emits trace events     │ core   └───────────────────────────────────────────────────┘    │
│   └────────────┬─────────────┘                              ▲                                    │
│                │ both call the same in-process core         │ both publish to the same bus       │
│                ▼                                             │                                    │
│   ┌────────────────────────────────────────────┐   ┌────────┴──────────────────────────────┐   │
│   │  (C) DATA LAYER CORE  (Python)               │   │  (E) EVENT BUS / TRACE SPINE          │   │
│   │  ports v1 app/engine + app/sources           │   │  append-only run/trace events;        │   │
│   │  - sources: prices,news,edgar,congress,13f,  │   │  Postgres LISTEN/NOTIFY (launch) →     │   │
│   │    fundamentals,rates,sentiment,iex_deep…    │   │  Redis Streams (scale)                 │   │
│   │  - engine: backtest,signals,portfolio,       │   └────────┬──────────────────────────────┘   │
│   │    riskmodel,optimize,execution,paperbook,   │            │                                   │
│   │    stats,attribution,montecarlo,stress       │            │ writes events                     │
│   │  - resilience: retry/breaker/SWR cache       │            │                                   │
│   │  - PURE quant; no agent code; no I/O in engine│           │                                   │
│   └───────────────┬──────────────────────────────┘           │                                   │
│                   │ reads market data                         │                                   │
│                   ▼                                           ▼                                   │
│   ┌──────────────────────────┐   ┌────────────────────────────────────────────────────────┐    │
│   │ (F) DATASTORES           │   │  (D) DEPLOY LAYER CONTROL PLANE                          │    │
│   │  - Postgres (system of    │◄─►│  - strategy spec registry (versioned, immutable)        │    │
│   │    record: tenants, runs, │   │  - run state machine: draft→backtest→paper→retired      │    │
│   │    specs, books, events,  │   │  - schedules backtests + paper-live runs onto DO        │    │
│   │    audit, trace)          │   │  - pre-trade compliance gate (engine/compliance)        │    │
│   │  - Object store (S3/Spaces│   │  - serialized money-path mutations (FOR UPDATE)         │    │
│   │    backtest artifacts,    │   └───────────────────────┬────────────────────────────────┘    │
│   │    IEX captures, reports) │                           │ dispatch jobs / collect results       │
│   │  - TS store (Timescale)   │                           ▼                                       │
│   │    for tick/quote/curve   │   ┌────────────────────────────────────────────────────────┐    │
│   │    time-series (optional) │   │  (G) DO CPU CLUSTERS — STRATEGY RUNTIME                  │    │
│   └──────────────────────────┘   │  workers pull jobs; run backtest engine over history;   │    │
│                                   │  run paper-live loop on REAL market data → SIM book;     │    │
│                                   │  brokerage-adapter SEAM (paper adapter only at launch)   │    │
│                                   │  emit telemetry events back onto the bus (E)             │    │
│                                   └────────────────────────────────────────────────────────┘    │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────┐    │
│   │ (H) WEB UI  (React, observability surface — NO chat console)                            │    │
│   │  Tabs: Trace (agent thought process) · Trades · News / Ideas · Algos · Books            │    │
│   │  Subscribes to SSE from (B); reads REST from (B). Pure view of runs + traces.           │    │
│   └──────────────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Component responsibilities, one line each:**

- **(A) MCP server** — the *primary* product surface. Speaks MCP; advertises Data Layer + Deploy Layer tools; authenticates the agent's token → `tenant_id` + `session_id`; enforces per-call deadlines; emits a trace event for every call. Thin: it adapts MCP → the same in-process core the gateway uses.
- **(B) REST/SSE gateway** — feeds the web UI from the *same core*. Handles browser auth/sessions, serves REST reads, fans out SSE (trace + telemetry), and exposes the human control actions (accept idea, promote to paper, pause/retire). Never a second source of truth.
- **(C) Data Layer core** — the ported v1 quant brain. Pure, deterministic `engine/` (numpy) + resilient `sources/`. Exposed as MCP tools and as REST reads. *No agent code runs here.*
- **(D) Deploy Layer control plane** — owns strategy **specs** (versioned/immutable), the **run state machine**, scheduling onto DO, and the **pre-trade compliance gate**. Single writer for the money path.
- **(E) Event bus / trace spine** — append-only stream of `(run_id, seq, event)`. Postgres `LISTEN/NOTIFY` at launch (one bus, transactional with the write); Redis Streams when fan-out demands it.
- **(F) Datastores** — Postgres = system of record; object store = large artifacts; Timescale (optional) = heavy time-series.
- **(G) DO CPU clusters** — stateless workers that *execute* backtests and the paper-live loop. They run our trusted engine code against a spec; they never run agent code.
- **(H) Web UI** — observability dashboard. The chat console from v1 is removed.

---

## 2. End-to-end flows (step by step)

### (a) Agent discovers + calls a Data Layer tool to research a stock

1. User's agent opens an MCP connection to **(A)** with a Doomberg API token. (A) resolves token → `tenant_id`, mints/loads a `session_id`, and binds both into a request context (the v2 successor to v1's `tenant.py` contextvar — see §4.5).
2. Agent calls `tools.list`. (A) returns the Data Layer catalog: e.g. `get_price_history`, `get_news`, `get_fundamentals`, `get_insider_trades`, `get_congress_trades`, `get_institutional_holders`, `compute_signal`, `run_factor_model`, `screen_universe`, `estimate_execution_cost`. Each tool's schema is generated from the v1 skill/engine signatures.
3. Agent calls `tools.call("get_news", {scope_type:"symbol", scope:"NVDA"})`. (A):
   - **opens a trace span** on the bus **(E)**: `{session_id, tool:"get_news", args, ts, span_id}` (args are recorded for the UI and audit);
   - sets a **per-call deadline** (e.g. 15s) and calls the **(C)** core, which routes to `sources/news.py` through the resilience wrapper (retry/breaker/stale-while-revalidate);
   - on return, attaches the **provenance block** (`{source, asOf, freshnessSec, mode: live|stale|mock, coverage}`) — provenance is mandatory on every tool result (a v1 roadmap item promoted to a contract here);
   - **closes the span**: `{span_id, result_summary, provenance, latency_ms, ok}`.
4. (A) returns the tool result to the agent. The agent keeps researching, calling more tools. Each call is one span on the same `session_id`. The web UI **(H)** is already rendering these spans live via SSE — the user watches the agent "think" by watching the tool timeline fill in (§3).

### (b) Agent proposes a strategy

1. After research, the agent calls a Deploy Layer tool: `tools.call("propose_strategy", {spec})`. The `spec` is a **declarative strategy document**, never code: `{universe, signal_id + params, construction_scheme, rebalance, sizing, risk_limits, costs}` — every field maps to an existing `engine/` primitive (`signals.SIGNALS`, `portfolio.SCHEMES`, `strategies.STRATEGIES`, gross/net limits).
2. **(D)** validates the spec against the engine's registered signals/schemes/limits (a closed allow-list — unknown signal = rejected, not "run arbitrary code"), assigns a `strategy_id` + immutable `version`, persists it `draft`, and emits a `strategy.proposed` event.
3. The UI's **Ideas/Algos** tabs render the proposal as a structured card: the resolved signal, universe, limits, and the trace spans that led to it (the research from flow (a) is linked to this proposal by `session_id`). **Nothing is deployed yet** — proposal is inert until a human accepts.

### (c) User accepts → backtest on the Deploy Layer

1. In **(H)**, the user clicks **Accept & Backtest** (or sets a window). This is a human action through **(B)**: `POST /strategies/{id}/backtest {window, costs}`.
2. **(D)** creates a `run` row `{run_id, strategy_id, version, kind:"backtest", state:"queued", tenant_id, deadline}` and **enqueues a job** for **(G)**. State transitions are a guarded state machine (`queued→running→done|failed`), each transition an event.
3. A DO worker **(G)** claims the job, loads the spec + point-in-time history from **(F)**, and runs the **trusted** `engine/backtest.py` / `engine/portfolio.py`. It streams progress telemetry onto **(E)** (`run.progress`, partial equity curve) and writes the final artifact (equity curve, trade log, stat block, drawdown) to the object store + a summary row to Postgres.
4. **(B)** fans the telemetry to **(H)**; the Backtest panel animates the equity curve as it computes, then shows the final stat block with the integrity/provenance badge (rigor mode: common calendar, non-overlapping forward windows — a v1 correctness fix baked into the contract).

### (d) User promotes → paper-live deployment

1. User clicks **Promote to Paper** in **(H)** → `POST /strategies/{id}/promote {to:"paper", criteria}` on **(B)**.
2. **(D)** runs the **pre-trade compliance gate** (ported `engine/compliance.py`: gross/net exposure, per-name caps, restricted lists). If it fails, the promotion is **blocked** and the reason is surfaced as a structured event — never silently. The optimizer/gate re-checks `sum|w|` against the gross limit *after* projection (closes the v1 optimizer over-exposure bug).
3. On pass, **(D)** opens a `run {kind:"paper", state:"running"}` and a **paper book** (fixed positions + cash, built via `engine/execution.generate_orders` and marked by `engine/paperbook.py`). It schedules a **long-lived paper-live job** on **(G)**.
4. The DO worker runs the paper-live loop: on each market tick/bar (REAL market data from **(C)** sources), it re-evaluates the spec's signal, diffs target vs current book, routes orders through the **brokerage-adapter seam** — which at launch is the **paper/sim adapter only** (fills against a simulated book; NO real brokerage, NO real money). Each fill, mark, and rebalance is an event on **(E)**.
5. **Money-path mutations** (book updates) happen *only* in **(D)** under a serialized transaction (`SELECT … FOR UPDATE` or optimistic version) — never a racing upsert from a worker and an API call (closes the v1 lost-update bug). The worker proposes deltas; (D) applies them atomically.

### (e) The web UI renders the whole thing

1. On load, **(H)** authenticates to **(B)**, gets the tenant's active sessions/runs, and opens an **SSE stream per active view** (one for the live trace, one for run telemetry).
2. The stream replays from a `last_seq` cursor (so a reconnect or a freshly-opened tab catches up deterministically — see §3 replay), then tails live.
3. Tabs are pure projections of events: **Trace** (the agent's tool timeline + reasoning), **Trades** (fills from paper runs), **News/Ideas** (research + proposals), **Algos** (specs + their run states), **Books** (live P&L from `paperbook`). Each panel has a top-level + per-panel error boundary so one bad field downgrades a tile, not the session (closes v1's missing boundaries). No chat console.

---

## 3. THE HARD PROBLEM — capturing & rendering a thought process we don't own

The agent runs on the user's side. Doomberg cannot see the agent's hidden chain-of-thought. We can only see what crosses the MCP wire. The design principle: **make the MCP wire itself the trace**, and add one *optional* channel for volunteered reasoning. Three mechanisms, in priority order.

### 3.1 MCP session correlation (the backbone — always available)

Every MCP connection carries a token → `(tenant_id, agent_id)`. (A) assigns a `session_id` to the connection (or honors an `X-Doomberg-Run` header the agent may set to bind a sequence of calls to a named investigation). **Every `tools.call` is automatically a trace event** — we own the server side of the call, so we record, with zero cooperation required from the agent:

```jsonc
// trace event, written transactionally with the tool's side effects
{
  "run_id":     "sess_7Kp…",      // session or explicit run binding
  "seq":        412,               // monotonic per run_id (gap-free ordering)
  "type":       "tool_call",
  "span_id":    "sp_91a",
  "tool":       "get_news",
  "args":       { "scope_type":"symbol", "scope":"NVDA" },
  "ts":         "2026-06-16T18:02:11.220Z"
}
{
  "run_id":"sess_7Kp…", "seq":413, "type":"tool_result", "span_id":"sp_91a",
  "ok": true,
  "result_summary": { "headlines": 12, "top": "NVDA guidance raise" },
  "provenance": { "source":"yahoo_rss", "asOf":"…", "mode":"live", "coverage":1.0 },
  "latency_ms": 380
}
```

This alone reconstructs **what** the agent did and **in what order** — the tool-call timeline is the spine of the UI's Trace tab. It needs no trust in agent-supplied text and survives any agent implementation.

### 3.2 Optional `emit_reasoning` tool (the "why" — volunteered, never trusted)

The tool timeline shows *what* but not *why*. To capture intermediate reasoning, the Data Layer advertises a first-class, side-effect-free MCP tool:

```
emit_reasoning({ kind: "thought"|"hypothesis"|"decision"|"plan_step",
                 text: string, refs?: [span_id], confidence?: number })
```

Well-behaved agents (Claude/GPT with tool use) call this between research steps to narrate their reasoning; it returns `{ok:true}` and emits a `reasoning` event onto the bus, ordered into the same `seq` stream so it interleaves correctly with tool calls. Because it is **just another tool call**, it needs no special protocol, works over stdio or HTTP MCP, and the UI renders it inline with the tool timeline as the agent's "thought bubbles." It is **display + audit only** — reasoning text never influences control-plane decisions, so a lying or absent agent degrades the *richness* of the trace but can never affect money-path behavior. (This is the inverse of v1's mistake: v1 *trusted* LLM output to the point of executing it; here agent text is purely observed.)

We make `emit_reasoning` attractive by documenting in each tool description that "narrating your reasoning with `emit_reasoning` makes the user's dashboard show your thought process." For agents that won't call it, §3.3 provides a fallback.

### 3.3 Inferred reasoning fallback (best-effort, clearly labeled)

If an agent emits no reasoning, (A) can synthesize lightweight *derived* trace annotations from the call pattern itself — e.g. grouping a burst of `get_fundamentals` + `compute_signal` + `propose_strategy` into a "research → decision" arc with a templated, **non-LLM**, deterministic label ("evaluated 3 signals on a 12-name universe"). These are tagged `derived:true` in the UI so the user knows they're inferred, not the agent's own words. No hidden LLM is invoked to fabricate reasoning (that would be a trust-killer and a cost sink).

### 3.4 The session/trace data model

```
trace_event
  run_id        text     -- session_id OR explicit run binding (FK to run when promoted)
  seq           bigint   -- gap-free, monotonic per run_id (assigned by the writer txn)
  type          enum     -- tool_call | tool_result | reasoning | run_state | run_progress
                          --  | fill | mark | proposal | compliance | error
  span_id       text     -- correlates a call to its result
  parent_span   text     -- nesting (a deploy tool that fans out to data tools)
  payload       jsonb    -- type-specific (args/result/text/state…)
  provenance    jsonb    -- on data results
  tenant_id     text     -- enforced at the data-access seam
  ts            timestamptz
  PRIMARY KEY (run_id, seq)
```

- **Association to a `run_id`:** research happens under a `session_id`. When the agent calls `propose_strategy`, the resulting `strategy_id` records its `origin_session_id`, so the run's trace can show *"this algo came from this research."* When the user backtests/promotes, a new `run_id` is created whose trace **links back** to the originating session via `parent_span`/`origin_session_id`. One unbroken chain: research → proposal → backtest → paper.
- **SSE replay:** the gateway **(B)** exposes `GET /streams/{run_id}?from_seq=N`. On connect it replays events `> N` from Postgres, then tails live (via `LISTEN/NOTIFY` → in-process fan-out). The client tracks `last_seq` and reconnects with it, so refreshes/disconnects never lose or duplicate events. Because `seq` is gap-free per `run_id`, the UI can detect a gap and re-fetch deterministically (fixes v1's "superseded stream clobbers newer answer" race — ordering is explicit, not implicit on arrival time).
- **Heartbeat:** during long blocking work (a slow tool, a long backtest), the writer emits `: keepalive` comments on SSE and `run_progress` events, so idle-timeout proxies never kill the stream (fixes v1's missing-heartbeat bug).

---

## 4. Boundaries & contracts between layers

Three hard seams. Each layer owns its data and exposes a narrow, versioned surface.

### 4.1 Agent ↔ Doomberg (the MCP contract) — *the* product API
- **Owns:** (A). **Surface:** MCP `tools.list` / `tools.call` + `emit_reasoning`.
- **Contract:** every tool has a JSON-Schema'd input, a typed output **with a mandatory provenance block**, a declared per-call deadline, and a stable name+version. Tools are pure reads (Data Layer) or guarded control proposals (`propose_strategy` is the only Deploy Layer tool the agent can call directly; **the agent cannot promote to paper or move money** — that requires a human action through (B)).
- **Invariant:** the agent is a *client*. It can read data and *propose*; it can never deploy, promote, or mutate a book.

### 4.2 Gateway ↔ Core (in-process function calls)
- **(A) and (B) are thin adapters over one shared Python core.** Both call the same `core.run_tool(name, args, ctx)` and `core.read(view, ctx)`. This guarantees the MCP path and the UI path can never diverge (v1 had a single FastAPI app; v2 keeps one core but two front doors). `ctx` carries `tenant_id`, `session_id`, `actor`, `deadline`.

### 4.3 Core ↔ Deploy control plane (internal API)
- **Owns:** (D) owns specs, runs, books, the state machine, and the compliance gate. **Surface:** `create_run`, `transition_run`, `apply_book_delta`, `evaluate_gate`.
- **Contract:** the spec is a **closed, declarative schema** validated against the engine's allow-list of signals/schemes/limits. Unknown field or signal → typed rejection. **No free-form code field exists.**

### 4.4 Control plane ↔ DO runtime (job contract)
- **Owns:** (G) executes; (D) schedules and is the **single writer** of books. **Surface:** workers *pull* jobs `{run_id, spec, version, window|live, deadline}`, *stream* telemetry events, and *propose* book deltas — they never write the book directly.
- **Invariant (money path):** all book mutations are applied by (D) in one serialized transaction (`FOR UPDATE` / optimistic `version`). A worker crash leaves the book consistent; a duplicate job is idempotent on `(run_id, seq)`.
- **Invariant (deadline):** every run carries a wall-clock deadline; (G) checks it inside its loops (no unbounded streams — fixes v1's 13 GB IEX reconstruct that had per-read but no aggregate timeout).

### 4.5 Tenancy & identity (cross-cutting, enforced once)
- `tenant_id` is resolved at the **two front doors only** (MCP token in (A); browser session in (B)) and bound into `ctx`. The **data-access layer in (F) is the single enforcement point**: every query is tenant-scoped by the data layer, not by each call site. Stores never accept an unscoped read. This makes isolation an **invariant**, fixing v1's per-store leaks (template store, in-memory dashboard IDOR, global generated-skill registry).

---

## 5. Tech-stack recommendation per component

| Component | Recommendation | Rationale |
|---|---|---|
| **(C) Data Layer core** | **Python 3.12**, numpy. **Port v1 `app/engine/` + `app/sources/` as-is.** | The quant logic is proven, pure, deterministic, and already unit-testable (engine has no I/O). Rewriting numpy quant in another language is pure downside risk. Keep it. |
| **(A) MCP server** | **Python**, official **MCP Python SDK**, `streamable-http` transport for hosted agents + `stdio` for local. Runs in the same process/image as the core. | MCP is the primary interface; the SDK is first-class in Python; co-locating with the core means tool calls are in-process function calls, not a network hop. One language for the whole quant+tool surface. |
| **(B) REST/SSE gateway** | **Python + FastAPI** (Starlette `StreamingResponse` for SSE) — *same app as v1's proven pattern, minus the chat/orchestrator.* | v1 already runs FastAPI with working SSE and the tenant contextvar; reuse it. Sharing the process with the core avoids a second source of truth. Async-friendly for SSE fan-out. |
| **(D) Deploy control plane** | **Python + FastAPI**, but a **separate deployable service** from the gateway. State machine as explicit table + transitions; compliance gate ports `engine/compliance.py`. | It's the money-path single-writer; isolating it as its own service lets it scale, deploy, and be hardened independently (and keeps its blast radius small). Python keeps it next to the engine it gates against. If we later want stronger compile-time guarantees on the state machine, **Go** is the fallback — but launch in Python to avoid a polyglot tax on day one. |
| **(G) DO runtime workers** | **Python** workers (same engine image), containerized, on **DigitalOcean droplets/k8s CPU pool**. Pull jobs from a queue. | They run the *same* trusted engine code as the core — sharing the image guarantees backtest≡paper math. CPU-bound numpy work fits DO CPU clusters (the locked decision). Stateless + pull-based = trivially horizontally scalable. |
| **(E) Event bus / trace** | **Launch: Postgres `LISTEN/NOTIFY`** (events written transactionally with their side effects). **Scale: Redis Streams.** | At launch, transactional writes + NOTIFY give exactly-once, gap-free ordering for free and one fewer moving part. Swap to Redis Streams only when fan-out/throughput demands it; the `(run_id, seq)` model is bus-agnostic. |
| **(F) Datastores** | **Postgres 16** (system of record: tenants, specs, runs, books, `trace_event`, audit). **DO Spaces / S3** (backtest artifacts, IEX captures, reports). **TimescaleDB** (optional, for heavy tick/quote/curve series). | Postgres is the v1 datastore and gives row-locks (`FOR UPDATE`) the money path needs. Object store for large blobs keeps Postgres lean. Timescale only if tick volume justifies it — don't add it speculatively. |
| **(H) Web UI** | **React + TypeScript + Vite**, SSE via `EventSource`, typed API via **Zod schemas / Orval codegen from an OpenAPI spec** (the lib/ packages already in the repo). | The repo already ships `lib/api-zod`, `lib/api-client-react`, and Orval codegen — reuse them so the UI's types are generated from the contract, not hand-kept. Keep the v1 "terminal" visual feel; drop the chat console; add error boundaries app-shell + per-panel. |
| **Cross-cutting: resilience** | Port v1 `sources/_resilient.py` (retry/backoff/jitter + per-source circuit breaker) and add a **stale-while-revalidate / last-known-good tier** so a tool returns `mode:"stale"` with a real `asOf` instead of fabricating mock. | Directly addresses two v1 themes: silent mock-for-real swaps and unprotected fetches (Treasury/FRED bypassed the wrapper). Provenance becomes truthful by construction. |
| **Cross-cutting: tests/CI** | **pytest** gating the **MCP tool contract** (golden schemas + provenance present), the **deploy state machine** (illegal transitions rejected), and the **money-path serialization** (concurrent delta test). Real CI (`.github/workflows`) that runs the full suite. | v1's defining test failure was that the shipped paths weren't the gated paths. v2 gates exactly the two contracts that matter (tool surface + state machine) so isolation, deadlines, and money-path invariants can't silently regress. |

---

## 6. What we explicitly DROP from v1 (and why)

- **Runtime AI codegen / self-building skills** (`dynamic_skills.py`, `feature_builder.py`, `code_guard.py`, `skills_generated/`, the client `new Function` panel eval). These were the source of both critical RCEs (static-guard-then-trust). v2 has **no path that executes agent- or LLM-authored code in a privileged process.** Strategies are *declarative specs* over a closed engine allow-list. *If* dynamic, user-defined panels ever return, they do so only as a declarative non-executable schema or in a sandboxed cross-origin iframe — not by executing generated code server-side.
- **The orchestrator / 197-branch intent heuristic** (`agent.py`). Doomberg no longer runs an agent loop or decides which panels to build — the external agent does. The keyword cascade and its mis-routing class of bugs are deleted, not ported.
- **The chat console.** The UI is an observability surface, not a conversation.

---

## 7. How each v1 invariant is structurally enforced (summary)

1. **No untrusted code execution** → no code field anywhere; specs are declarative; engine runs only trusted code; agent is a read/propose client. (§4.1, §6)
2. **No silent swallowing** → every tool call, transition, fill, and gate result is an append-only `trace_event`; errors are typed events, not `except: pass`. (§3, §4)
3. **Tenancy is an invariant** → resolved at the two front doors, enforced once at the data-access seam in (F). (§4.5)
4. **Money path serialized** → (D) is the single writer; all book deltas in `FOR UPDATE`/versioned transactions; workers only propose. (§4.4)
5. **Aggregate deadlines** → every run and tool call carries a wall-clock deadline checked inside the loops, at the gateway and the runtime. (§4.4, §5)
6. **Gated contracts = shipped contracts** → CI gates the MCP tool contract and the deploy state machine, the two surfaces everything else depends on. (§5)

---

## 8. Open questions for downstream designs (this doc deliberately defers)

- **Exact MCP tool catalog & schemas** (Data Layer design): which v1 skills become which tools, arg shapes, output schemas.
- **Spec schema in full** (Deploy Layer design): the complete declarative strategy document and its validation rules.
- **Paper-live loop cadence & market-data plumbing** (Deploy/runtime design): tick vs bar, EOD marking, the brokerage-adapter seam interface.
- **UI information architecture** (design track): Trace/Trades/Ideas/Algos/Books layout, the thought-process visualization.
- **AuthN/Z model** (security track): agent token issuance, scopes, human roles for accept/promote.
```
