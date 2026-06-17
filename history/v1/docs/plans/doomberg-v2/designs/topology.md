# Design: System Architecture & Topology

I've written the design doc to `/Users/joshuajerin/Desktop/jarvis/doomberg/docs/design/v2-system-architecture.md`. Here it is in full (it is the spine the other v2 designs hang off):

# Doomberg v2 — System Architecture & Topology

Grounded in v1 code at `artifacts/api-server/app/` (engine, sources, strategy lifecycle, tenant context, worker, SSE) and `docs/reviews/architecture-review-2026-06-16.md`.

## 0. North star & the v1 lessons that shape this

Doomberg v2 is a financial **tool-platform** that someone else's agent plugs into. Two consequences drive every decision: (1) the agent is external and untrusted-as-a-client — Doomberg never runs the agent loop and never executes agent-authored code in-process (v1's two critical RCEs came from running LLM-authored code behind a static guard; v2 deletes that path); (2) we must reconstruct a thought process we don't own — we can only see what crosses the MCP wire.

Six v1 failure themes map to six non-negotiable v2 invariants:

| v1 failure theme | v2 invariant |
|---|---|
| Static-guard-then-trust → RCE | No agent/LLM code ever executes in a privileged process. Strategies are declarative specs, not code. |
| "Never crash" swallowing erases audit | Every tool call, transition, and money-path mutation is an append-only event; no silent `except: pass`. |
| Tenant isolation per-store, not invariant | `tenant_id` resolved at the auth boundary, enforced once at the data-access seam. |
| Unlocked read-modify-write on money path | All book/run mutations go through the control plane in serialized transactions. |
| Per-call timeouts but no aggregate budget | Every run and tool call has a wall-clock deadline, enforced at gateway and runtime. |
| Tested path ≠ shipped path | CI gates the MCP tool contract and the deploy state machine — the surfaces everything depends on. |

## 1. Component map

- **(A) MCP server** — the PRIMARY product surface. Speaks MCP; advertises Data + Deploy tools; authenticates agent token → `tenant_id`+`session_id`; per-call deadlines; emits a trace event per call. Thin adapter over the shared core.
- **(B) REST/SSE gateway** — feeds the web UI from the SAME core. Browser auth/sessions, REST reads, SSE fan-out (trace + telemetry), human control actions (accept/promote/pause). Never a second source of truth.
- **(C) Data Layer core (Python)** — ports v1 `app/engine/` (backtest, signals, portfolio, riskmodel, optimize, execution, paperbook, stats, attribution, montecarlo, stress) + `app/sources/` (prices, news, edgar, congress, thirteenf, fundamentals, rates, sentiment, iex_deep, holdings, polymarket). Pure quant; no agent code; no I/O in engine.
- **(D) Deploy Layer control plane** — owns versioned/immutable strategy specs, the run state machine (draft→backtest→paper→retired), scheduling onto DO, the pre-trade compliance gate (`engine/compliance`). Single writer of the money path.
- **(E) Event bus / trace spine** — append-only `(run_id, seq, event)`. Postgres LISTEN/NOTIFY at launch (transactional with the write); Redis Streams at scale.
- **(F) Datastores** — Postgres (system of record: tenants, specs, runs, books, `trace_event`, audit); object store (S3/Spaces for backtest artifacts, IEX captures, reports); TimescaleDB optional for heavy tick/quote/curve series.
- **(G) DO CPU clusters** — stateless workers that EXECUTE backtests and the paper-live loop against a spec using the SAME trusted engine image; never run agent code; emit telemetry to the bus; propose book deltas (never write the book).
- **(H) Web UI (React)** — observability surface, NO chat console. Tabs: Trace, Trades, News/Ideas, Algos, Books. Pure SSE+REST projection.

(A) and (B) are two thin front doors over one shared Python core; both publish to the same event bus.

## 2. End-to-end flows

**(a) Research a stock:** agent opens MCP to (A) with a token → resolves `tenant_id`+`session_id`; `tools.list` returns the Data Layer catalog; `tools.call("get_news",{...})` opens a trace span on (E), sets a per-call deadline, routes through (C)'s resilience wrapper, attaches a **mandatory provenance block** (`{source, asOf, freshnessSec, mode: live|stale|mock, coverage}`), closes the span. UI renders spans live.

**(b) Propose a strategy:** agent calls `propose_strategy({spec})` — a DECLARATIVE document `{universe, signal_id+params, construction_scheme, rebalance, sizing, risk_limits, costs}`, never code, every field mapping to an existing engine primitive. (D) validates against the engine's closed allow-list, assigns `strategy_id`+immutable `version`, persists `draft`. Nothing deploys until a human accepts.

**(c) Accept → backtest:** human action through (B); (D) creates a guarded `run`, enqueues a job; a DO worker (G) runs trusted `engine/backtest` over point-in-time history, streams progress telemetry, writes artifact to object store + summary to Postgres; UI animates the equity curve with the integrity/provenance badge.

**(d) Promote → paper-live:** human action; (D) runs the pre-trade compliance gate (gross/net/per-name caps, restricted lists; re-checks `sum|w|` vs gross AFTER projection — closes v1 optimizer bug). On pass, opens a paper book (`engine/execution.generate_orders` + `engine/paperbook`), schedules a long-lived paper-live job. Worker re-evaluates the signal on REAL market data, routes orders through the **brokerage-adapter seam — paper/sim adapter only at launch** (no real brokerage/money). All book mutations applied ONLY by (D) in serialized transactions (`FOR UPDATE`/optimistic version) — worker proposes deltas, (D) applies atomically.

**(e) UI renders:** (H) authenticates to (B), opens SSE per view, replays from `last_seq` then tails live. Tabs are pure event projections; top-level + per-panel error boundaries.

## 3. THE HARD PROBLEM — capturing a thought process we don't own

Principle: **make the MCP wire itself the trace**, plus one optional channel for volunteered reasoning.

**3.1 MCP session correlation (backbone, always available):** every connection's token → `(tenant_id, agent_id)`; (A) assigns `session_id` (or honors an `X-Doomberg-Run` header). Every `tools.call` is automatically a trace event because we own the server side — `tool_call` + `tool_result` events with args, result summary, provenance, latency. This reconstructs WHAT the agent did and in what order with zero agent cooperation.

**3.2 Optional `emit_reasoning` tool (the WHY, volunteered, never trusted):** a first-class side-effect-free MCP tool `emit_reasoning({kind, text, refs?, confidence?})`. Well-behaved agents narrate between steps; it emits a `reasoning` event ordered into the same `seq` stream so it interleaves with tool calls. It is display+audit ONLY — reasoning text never influences control-plane decisions, so a lying/absent agent degrades trace richness but never money-path behavior. (The inverse of v1's mistake: v1 trusted LLM output enough to execute it; here agent text is purely observed.)

**3.3 Inferred fallback (best-effort, labeled):** if no reasoning is emitted, (A) synthesizes DETERMINISTIC, non-LLM templated annotations from the call pattern, tagged `derived:true`. No hidden LLM fabricates reasoning.

**3.4 Trace data model:** `trace_event(run_id, seq /*gap-free monotonic*/, type /*tool_call|tool_result|reasoning|run_state|run_progress|fill|mark|proposal|compliance|error*/, span_id, parent_span, payload jsonb, provenance jsonb, tenant_id, ts)`, PK `(run_id, seq)`.
- **Association:** research runs under a `session_id`; `propose_strategy` records `origin_session_id`; backtest/promote create new `run_id`s that link back via `parent_span`/`origin_session_id` — one unbroken chain research→proposal→backtest→paper.
- **SSE replay:** `GET /streams/{run_id}?from_seq=N` replays `>N` from Postgres then tails via LISTEN/NOTIFY; client tracks `last_seq` and reconnects with it; gap-free `seq` lets the UI detect gaps and re-fetch deterministically (fixes v1's superseded-stream clobber).
- **Heartbeat:** `: keepalive` + `run_progress` events during long work (fixes v1's missing-heartbeat kill).

## 4. Boundaries & contracts

- **4.1 Agent ↔ Doomberg (MCP contract, THE product API):** every tool has JSON-Schema input, typed output with mandatory provenance, declared deadline, stable name+version. The agent can read and PROPOSE only; `propose_strategy` is the only Deploy tool it can call. **It cannot promote to paper or move money** — those require a human action through (B).
- **4.2 Gateway ↔ Core (in-process):** (A) and (B) both call one shared `core.run_tool(name,args,ctx)` / `core.read(view,ctx)`; the MCP path and UI path can never diverge. `ctx` carries `tenant_id, session_id, actor, deadline`.
- **4.3 Core ↔ Deploy (internal):** (D) owns specs/runs/books/state-machine/gate; surface `create_run, transition_run, apply_book_delta, evaluate_gate`. Spec is a closed declarative schema validated against the engine allow-list — no free-form code field exists.
- **4.4 Control plane ↔ DO runtime (job contract):** workers PULL jobs, STREAM telemetry, PROPOSE deltas; never write the book. Money path: (D) is single writer under serialized txn; jobs idempotent on `(run_id, seq)`. Deadline checked inside worker loops (fixes v1's unbounded 13GB IEX reconstruct).
- **4.5 Tenancy (cross-cutting, enforced once):** `tenant_id` resolved at the two front doors only, bound into `ctx`; the data-access layer in (F) is the single enforcement point — stores never accept an unscoped read (fixes v1 template-store/in-memory-dashboard/global-skill leaks).

## 5. Stack recommendation per component

- **(C) Data Layer core:** Python 3.12 + numpy; PORT v1 `engine/`+`sources/` as-is — proven, pure, deterministic, already unit-testable; rewriting numpy quant elsewhere is pure downside risk.
- **(A) MCP server:** Python, official MCP SDK, `streamable-http` (hosted) + `stdio` (local), co-located with the core so tool calls are in-process, not a network hop.
- **(B) REST/SSE gateway:** Python + FastAPI (Starlette StreamingResponse for SSE) — reuse v1's proven SSE + tenant contextvar, minus chat/orchestrator.
- **(D) Deploy control plane:** Python + FastAPI as a SEPARATE deployable service (money-path single-writer, small blast radius, scales independently). Go is the fallback if we later want compile-time state-machine guarantees, but launch in Python to avoid a polyglot tax.
- **(G) DO workers:** Python, SAME engine image as the core (guarantees backtest≡paper math), containerized on DO CPU clusters, stateless + pull-based.
- **(E) bus/trace:** launch Postgres LISTEN/NOTIFY (transactional, gap-free ordering, one fewer moving part); scale to Redis Streams; `(run_id, seq)` model is bus-agnostic.
- **(F) datastores:** Postgres 16 (row-locks for the money path), DO Spaces/S3 (blobs), TimescaleDB only if tick volume justifies it.
- **(H) Web UI:** React + TypeScript + Vite, `EventSource` SSE, types generated from the OpenAPI spec via the repo's existing `lib/api-zod` + `lib/api-client-react` + Orval; keep the terminal look, drop chat, add error boundaries.
- **Cross-cutting resilience:** port `sources/_resilient.py` (retry/backoff/jitter + per-source breaker) + add stale-while-revalidate so tools return `mode:"stale"` with a real `asOf` instead of fabricating mock — makes provenance truthful by construction.
- **Cross-cutting CI:** pytest gating the MCP tool contract (golden schemas + provenance present), the deploy state machine (illegal transitions rejected), and money-path serialization (concurrent-delta test); real `.github/workflows`.

## 6. Explicitly DROPPED from v1
Runtime AI codegen / self-building skills (`dynamic_skills.py`, `feature_builder.py`, `code_guard.py`, `skills_generated/`, client `new Function` eval) — the source of both critical RCEs; v2 has no privileged path executing generated code. The orchestrator / 197-branch intent heuristic (`agent.py`) — the external agent decides now. The chat console.

## 7. Open questions deferred to downstream designs
Exact MCP tool catalog & schemas (Data Layer design); full declarative spec schema (Deploy Layer design); paper-live loop cadence + market-data plumbing + brokerage-adapter seam interface (runtime design); UI information architecture (design track); authN/Z model and human roles (security track).

Full doc on disk: `/Users/joshuajerin/Desktop/jarvis/doomberg/docs/design/v2-system-architecture.md`