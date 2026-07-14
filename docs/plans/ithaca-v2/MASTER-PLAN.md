# Ithaca v2 — Master Implementation Plan

**Status:** approved-to-build • **Date:** 2026-06-16 • **Supersedes:** v1 monolith at `artifacts/api-server/app`
**Inputs synthesized:** 6 subsystem designs (topology, data layer, deploy layer, web UI, security, repo/sequencing) + 2 red-team critiques (integration, feasibility).

This plan resolves every contradiction the red teams surfaced. Where docs conflicted, the resolution is stated inline with a one-line rationale and tagged **[RESOLVED]**. Where a feasibility critique forces a scope cut, it is tagged **[CUT-FOR-v2.0]**. This is meant to be buildable from on Monday.

---

## 1. Vision & positioning

Ithaca v2 is a **financial tool-platform**: a hosted set of quantitative research and paper-trading capabilities that an external, bring-your-own (BYO) agent — Claude, GPT, or a custom agent — calls over MCP. v1 was a monolith that ran *its own* agent loop inside the server and compiled AI-authored code at runtime (the source of two critical RCEs); v2 inverts that completely — **Ithaca never runs the agent and never executes agent-authored code**, it only exposes vetted tools, executes declarative strategy specs on trusted infrastructure, and *observes*. The product is three surfaces over one shared Python core: an **MCP gateway** (the primary API the agent uses to research and propose strategies), a **DigitalOcean deploy layer** that backtests and paper-trades accepted strategies, and a **web observability UI** that lets a human watch their agent think, work, and trade — replayable and fully audited. The shift in one line: *from "an AI terminal that does the thinking" to "a tool-platform someone else's agent thinks with, and a glass box that records everything it did."*

---

## 2. Target architecture

### 2.1 The load-bearing resolution: one core, one language, one contracts package

The single biggest structural risk the integration red-team found is that the six docs each invented their own auth format, spec shape, event schema, tenant key, and allow-list — *while topology asserts a single shared core*. We resolve this at the foundation:

- **[RESOLVED — control-plane language] The entire backend is Python.** The repo-sequencing doc's TypeScript control plane is **overruled** (topology, deploy, and security all specify Python/FastAPI). Rationale: the spec validator, the post-projection gross-L1 risk attestation, and the operator registry are the security boundary and live in numpy/Pydantic. A TS control plane would either duplicate that math (the exact v1 divergence-bug class) or add an unowned Python hop per validation. TypeScript is kept **only for the web UI.**
- **[RESOLVED — one core, no re-porting] `engine/`, `sources/`, `paperbook`, `execution` live in exactly one shared Python package (`ithaca-core`), imported — never re-ported — by the MCP gateway, the REST gateway, and the DO workers.** This kills the three-homes-for-the-money-path problem and guarantees `backtest math ≡ paper math` because both drivers import the same code.
- **`packages/contracts` is frozen in Phase 0 before any service is built.** It owns: the event/trace schema, the `StrategySpec` schema, the provenance envelope, the canonical tenant key, and the auth principal. This is the repo-sequencing doc's stated Phase-0 unlock that the other five docs each violated by inventing their own shapes.

### 2.2 Component map

| | Component | Language | Role |
|---|---|---|---|
| **A** | MCP gateway | Python (official MCP SDK, streamable-http + stdio) | Primary product surface. Token → principal; advertises Data + `propose_strategy`; per-call deadline; emits a trace event per call. Thin adapter over the core. |
| **B** | REST/SSE gateway | Python (FastAPI) | Feeds the web UI from the **same** core. Browser auth, REST reads, SSE fan-out, **human control actions (accept/promote/pause/halt)**. |
| **C** | `ithaca-core` | Python 3.12 + numpy | Ported v1 `engine/` (pure quant) + `sources/` (adapters behind `_resilient`) + the operator registry + the graph evaluator + the accounting/risk kernel. No I/O in `engine`; no agent code anywhere. |
| **D** | Deploy control plane | Python (FastAPI), separate deployable | Owns immutable versioned specs, the run state machine, scheduling onto DO, the pre-trade compliance gate. **Single writer of the money path.** |
| **E** | Event/trace spine | Postgres LISTEN/NOTIFY (launch) → Redis Streams (scale) | Append-only `(run_id, seq)` events. |
| **F** | Datastores | Postgres 16 (+ RLS), DO Spaces | System of record + blobs. TimescaleDB deferred. |
| **G** | DO workers | Python, **same `ithaca-core` image** | Execute backtests + paper-live ticks. Pull jobs, stream telemetry. Reach data **only** through the Data Gateway facade. |
| **H** | Web UI | React + Vite + TS | Observability surface, no chat console. Pure SSE+REST projection. |

### 2.3 [RESOLVED — Data Gateway vs Data Layer are the same service]

The integration red-team found `sources/` had two competing owners (the MCP data layer and a worker-only "Data Gateway"). **Resolution: there is one `sources/` package inside `ithaca-core`. The "Data Gateway" is not a separate service — it is a thin point-in-time facade in front of that one package, exposing a private RPC reachable only from the worker VPC.** The agent path (MCP `core.run_tool`) and the worker path (Gateway RPC with `asOf`) call the *same* adapters, the same breakers, the same provenance builder. The only difference is the `asOf` truncation parameter (see §2.4). This honors topology's "MCP and UI can never diverge."

### 2.4 [RESOLVED — point-in-time is a per-source capability, not a plane guarantee]

The feasibility red-team's **#1 critical** is that v1's free sources cannot deliver true PIT: Yahoo is survivorship-biased and dividend-restated with no vintaging; `fetch_fundamentals_history` *estimates* knowable-dates with a 45-day lag. **Resolution, adopted in full:**
- PIT is a **per-source capability flag in the provenance envelope** (`pit: true | false | estimated`), not a property the gateway can manufacture.
- `asOf` becomes an **optional input parameter** on data-fetch tool schemas (closing the integration red-team's #4). The worker path always passes `asOf = bar_i`; the agent path passes `asOf = now`. One entry point, one truncation knob.
- **[CUT-FOR-v2.0] Fundamental-factor backtests are forbidden at launch.** v2.0 backtests are scoped to **price/technical strategies** (momentum, MA-cross, vol, cross-sectional rank on returns) where Yahoo's restated-but-internally-consistent daily closes are defensible. Fundamental-factor backtesting unlocks only when a vintaged source (Sharadar/Compustat PIT) is wired. **This framing must be fixed before the Gateway is built — otherwise we ship a backtester that lies.**

### 2.5 ASCII architecture diagram

```
                        ┌─────────────────────────────────────────┐
   BYO Agent            │            packages/contracts            │
 (Claude/GPT/custom)    │  events · StrategySpec · provenance ·    │
        │               │  tenant_id · auth principal  (FROZEN P0) │
        │ MCP            └─────────────────────────────────────────┘
        ▼                                  ▲ generates types
 ┌──────────────┐   in-proc   ┌────────────┴───────────────┐
 │ (A) MCP      │────────────▶│   (C) ithaca-core         │
 │   gateway    │  core.run_  │   engine/ (pure numpy)      │
 └──────────────┘   tool()    │   sources/ (+ _resilient)   │
        │                     │   operator registry         │
        │ emits trace         │   graph evaluator           │
        ▼                     │   accounting + risk kernel  │
 ┌──────────────┐   core.read │   Data Gateway facade(asOf) │
 │ (B) REST/SSE │◀────────────│                             │
 │   gateway    │   (view)    └─────┬───────────────┬───────┘
 └──────┬───────┘                   │ propose/      │ private RPC
        │ SSE                       │ create_run    │ (asOf, VPC-only)
        │ + human control           ▼               │
        ▼                  ┌──────────────────┐     │
 ┌──────────────┐          │ (D) Deploy        │     │
 │ (H) Web UI   │◀── SSE ──│   control plane   │     │
 │  React/TS    │          │  specs·runs·books │     │
 │  Runs│Algos│ │          │  state machine    │     │
 │  Deploys│    │          │  compliance gate  │     │
 │  Trades│Ideas│          │  SINGLE WRITER    │     │
 └──────────────┘          └───┬───────────┬───┘     │
                               │ enqueue   │ apply    │
        ┌──────────────────────┘  job      │ delta    │
        ▼                                  ▲          ▼
 ┌─────────────────────────────────────────┴──────────────────┐
 │  (G) DigitalOcean DOKS — workers (same ithaca-core image) │
 │   node pool: backtest (scale-to-zero)  │  node pool: paper  │
 │   deny-all egress except Data Gateway RPC                   │
 │   propose book deltas → (D) applies in serialized txn       │
 └─────────────────────────────────────────────────────────────┘
        │                         │
        ▼                         ▼
 ┌──────────────┐         ┌──────────────┐
 │ (F) Postgres │         │ DO Spaces     │
 │  +RLS  (E)   │         │  artifacts    │
 │  trace_event │         │  logs/blobs   │
 │  LISTEN/NOTIFY│        └──────────────┘
 └──────────────┘
```

### 2.6 Layer contracts (enforced once, never per-call-site)

- **Agent ↔ Ithaca (MCP, THE product API):** every tool has JSON-Schema input, a typed output with a **mandatory provenance block**, a declared deadline, a stable name+version. The agent can **read and `propose_strategy` only**. It cannot promote or move money.
- **Gateway ↔ Core (in-process):** both A and B call one `core.run_tool(name, args, ctx)` / `core.read(view, ctx)`. `ctx` carries `tenant_id, session_id, actor, deadline`. The MCP path and UI path cannot diverge.
- **Core ↔ Deploy:** D exposes `create_run, transition_run, apply_book_delta, evaluate_gate`. Spec is a closed declarative schema validated against the operator registry; **no free-form code field exists** (see §5).
- **Control plane ↔ DO runtime:** workers PULL jobs, STREAM telemetry, **PROPOSE deltas, never write the book** (see §5.4 resolution). Deadline checked inside worker loops. Jobs idempotent on `(run_id, seq)`.
- **Tenancy:** `tenant_id` resolved at the two front doors only, bound into `ctx`; the data-access layer + Postgres RLS is the single enforcement point.

---

## 3. The four key end-to-end flows

**Flow 1 — Research (agent ↔ MCP, observable for free).** The agent opens MCP with a token → resolves to `(tenant_id, agent_id, scopes)` and a `session_id`. `tools.list` returns the Data Layer catalog. `meta.open_research_session({focus})` binds a session carrying a wall-clock **deadline + credit budget** (the aggregate cap v1 lacked). Each `tools.call` (e.g. `market.get_ohlcv`, `signals.evaluate_signal`) opens a trace span, sets a per-call deadline = `min(default, remaining_budget)`, routes through the core's resilience wrapper, and returns an envelope with a **mandatory provenance block** `{source, asOf, freshness, pit, coverage, cost}`. Because we own the server, **every call is a trace event with zero agent cooperation.** The UI renders spans live.

**Flow 2 — Propose (agent → control plane, validated as data).** The agent calls `propose_strategy({spec})`. The spec is the **one canonical `StrategySpec`** (§5). D validates against the schema + semantic linter + **design-time risk pre-attestation**, assigns server-stamped `strategy_id` + immutable `version`, stamps `origin_session_id`, and persists `draft`. Nothing deploys. The agent has emitted *data we validate*, never code we run.

**Flow 3 — Accept → backtest (human-gated, runs on DO).** **[RESOLVED — promotion authority]** A **human** clicks "Backtest" / "Deploy (paper)" in the UI through gateway (B). The agent's `deploy:paper` scope is narrowed to *"may request a deployment that requires human acceptance"* — it cannot self-promote. D creates a guarded `run`, enqueues a job. A backtest worker (G) pulls it, runs trusted `engine/backtest` over a point-in-time window (`asOf = bar_i`, scoped to PIT-capable sources), streams progress telemetry with heartbeats, writes the artifact to Spaces + summary to Postgres, and **always emits the walk-forward/overfitting diagnostics** (deflated Sharpe, PBO/CSCV) — honesty by default. UI animates the equity curve with the integrity/provenance badge.

**Flow 4 — Promote → paper-live → observe (human-gated, single-writer money path).** Human promotes through (B). D runs the pre-trade compliance gate (gross/net/per-name caps, restricted lists) and **re-checks `sum|w|` vs gross AFTER projection** (closes the v1 311%-gross optimizer bug — see §5.3). On pass, D opens a paper book and schedules a market-calendar-aware **paper-live tick** job. Each tick: worker loads current marks, evaluates the graph on **real current data with a hard max-staleness floor** (skip-and-alert if stale — see §7), computes target weights, routes through the **paper venue adapter**, and **proposes a book delta**. D applies it in a serialized `SELECT … FOR UPDATE` transaction. Every fill, mark, and transition is a trace event; the UI streams P&L into Deployments and Trades. The whole chain research→proposal→backtest→paper is one unbroken `origin_session_id` lineage.

---

## 4. Data Layer plan

### 4.1 MCP tool taxonomy

Naming: `<group>.<verb_noun>`. 15 groups, each tool ports from a named v1 module. Headline tools per group:

- **`market`** — `get_quote`, `get_ohlcv`, `get_intraday`, `get_daily_closes` (PIT-safe, real-only), `get_trade_flow`. *(ports `sources/prices`, `iex_deep`)*
- **`fundamentals`** — `get_snapshot` (unit-corrected), `get_history`, `compare_companies`, `classify_sector`. *(ports `sources/fundamentals`, `sectors`)*
- **`calendar`** — `get_earnings`, `get_ma_activity`, `get_economic_releases`, `get_series_revisions`.
- **`news`** — `get_ticker_news`, `get_topic_news`, `get_sentiment`. *(PIT-capable: real `publishedAt`)*
- **`ownership`** — `get_insider_transactions`, `get_congress_trades`, `get_13f_holdings`, `get_etf_holdings`, `search_filings`. *(EDGAR is PIT-capable)*
- **`signals`** — `list_signals`, `evaluate_signal`, `combine_signals`, `compute_ic`, `correlation_matrix`, `factor_analysis`.
- **`risk`** — `build_factor_model`, `decompose_portfolio`, `attribution`, `stress_scenario`, `performance_stats`.
- **`portfolio`** — `construct`, `optimize_mean_variance`, `optimize_risk_parity`, `optimize_hrp`, `black_litterman`, `rebalance_plan`.
- **`backtest`** — `list_strategies`, `run`, `walk_forward`, `monte_carlo`. *(research primitives, NOT deploy)*
- **`execution`** — `estimate_costs`, `simulate_orders` (real intraday only), `tca_report`, `borrow_profile`.
- **`options`** — `get_chain`, `screen`, `price_strategy`, `iv_surface`, `vol_term_structure`.
- **`fixedincome`** — `get_treasury_curve`, `compare_sovereigns`, `cashflow_duration`, `cds_price`, `credit_spreads`.
- **`macro`** — `get_regime`, `get_fred_series`, `list_prediction_markets`, `get_prediction_market`.
- **`screen`** — `universe` (PIT-aware via `listedAt`), `run_screener`, `heatmap`.
- **`meta`** — `list_tools`, `data_quality`, `open_research_session`, `session_summary`.

**[CUT-FOR-v2.0]** `market.reconstruct_order_book` (IEX DEEP) is **removed from the synchronous agent surface** (feasibility #9: a single call decodes ~13GB). If re-added: high-cost class, **hard byte cap** (not just wall-clock), async job, pre-materialized per session-date.

### 4.2 Provenance contract (structural, every payload)

```jsonc
{ "data": {...},
  "provenance": {
    "source": "yahoo-chart", "asOf": "2026-06-16T14:32:05Z",
    "freshness": "live|stale|mock", "staleAgeSec": 0,
    "pit": "true|false|estimated",          // per-source capability — NOT a plane guarantee
    "coverage": { "requested": 12, "resolved": 11, "missing": ["BRKB"] },
    "cost": { "class": "cheap|network|heavy", "credits": 1 }, "cacheHit": true },
  "partial": false,
  "warnings": [{ "code": "MOCK_FALLBACK", "scope": "US2Y" }] }
```

Rules: data is **never imputed** to hide gaps; `mock` is never dressed as live; `asOf` is the *data's* timestamp not fetch time. Typed errors with stable codes (`UNSUPPORTED_WINDOW`, `UPSTREAM_THROTTLED`, `DEADLINE_EXCEEDED`, …). Stale-while-revalidate serves cached data labeled `stale` rather than fabricating mock.

### 4.3 Porting map (fix-on-port)

Port `engine/` (~5000 LOC, genuinely pure per feasibility verification) and `sources/` (~4000 LOC) nearly verbatim into `ithaca-core`. Fix during port: optimizer gross-L1 re-check (`optimize.py:177`), Carino-link attribution (`attribution.py:357`), cross-sectional forward-window alignment (`signals.py:342`), route Treasury/FRED through `_resilient` (`rates.py:91`). **Drop entirely:** `agent.py`, `code_guard.py`, `dynamic_skills.py`, `feature_builder.py`, `skills_generated/`. The 79 v1 skills are **not** ported as the skill abstraction — their underlying engine/source calls become the static MCP tools above.

---

## 5. Deploy Layer plan

### 5.1 [RESOLVED — strategy model: declarative-only, parameterized primitives at launch]

Three docs proposed three spec shapes (flat `signal_id+scheme` / operator-DAG / `engine/strategies.py` primitives) and security added a "scripted escape hatch." **Resolution, taking both red teams' advice:**
- **One canonical `StrategySpec` in `packages/contracts`, authored once, one validator, one evaluator.**
- **[CUT-FOR-v2.0] v2.0 ships the parameterized `engine/strategies.py` primitives, NOT the operator-DAG.** Rationale (feasibility #7): the existing strategies are `(closes, params) -> positions` pure functions covering MA-cross/momentum/mean-reversion — they ship faster, the DAG's semantic linter (cycle detection, feasibility pre-attest, registry) is real work for marginal launch value. The DAG is a **post-launch expressiveness upgrade** that reuses the same evaluator seam.
- **[CUT-FOR-v2.0] The `CustomPythonNode` / "scripted escape hatch" does not exist in the launch schema.** topology's invariant holds: *un-expressible beats off-by-default.* security §3.1's "scripted mode" and deploy's `CustomPythonNode` are re-labeled **"future, not in launch schema."** `firmId`/`id` are always server-stamped.

`StrategySpec` (launch shape):
```jsonc
{ "specVersion": "1.0", "id": "<server-stamped>", "tenant_id": "<stamped>",
  "name": "dual-momentum-tech",
  "universe": { "symbols": ["AAPL","MSFT","NVDA"], "source": "prices" },
  "strategy": { "id": "momentum", "params": { "lookback": 90, "top": 2 } },
  "construction": { "scheme": "rank_weight", "longOnly": true, "gross": 1.0 },
  "risk": { "maxGross": 1.0, "maxNet": 1.0, "maxNamePct": 0.25 },
  "execution": { "costBps": 5, "algo": "vwap", "rebalance": "daily@close" },
  "resources": { "tier": "standard" }, "seed": 42 }
```

### 5.2 SAFE execution model

- **[RESOLVED + CUT-FOR-v2.0 — no microVM at launch]** Feasibility #2: since **no untrusted code runs** (declarative-only), the runtime is *our own trusted code over validated data*. A plain container with **cgroup limits + `activeDeadlineSeconds` + a default-deny egress NetworkPolicy** is sufficient and a fraction of the gVisor/Kata/seccomp work. **The microVM sandbox is deferred to the phase that actually ships `CustomPythonNode`, gated on a spike proving the runtime works on DO.** We do not build a microVM fleet to run numpy we wrote.
- **Out-of-process always.** The runtime never runs in the control-plane process (v1's fatal mistake). One job per container, spawned fresh, killed at completion.
- **Deny-all egress** except the Data Gateway RPC, enforced by Kubernetes NetworkPolicy (an invariant in the cluster, not in code).
- **Aggregate wall-clock deadline per job** (not just per-call), SIGKILL on breach, recorded `timeout` with partial artifacts. Terminal states are explicit: `succeeded|failed|timeout|oom|killed|data_unavailable`. No bare `except: pass`.
- **Determinism:** `seed` in spec + pure numpy + fixed `asOf` window ⇒ identical artifact hash. "Reproduce this run" is free; backtests cache on `(spec_hash, asOf_window)`.

### 5.3 The risk gate — runtime, not lint **[RESOLVED, feasibility #8]**

The 311%-gross v1 bug was a *projection* ending on net+box instead of gross-L1. **The gross-L1 re-check runs post-projection, in the executor, on every emitted target book** — refusing to emit a breaching book (`infeasible-relaxed` with the violation). The design-time pre-attestation is a *nicety*; the runtime attestation is *the boundary*. Gating CI test uses the v1 311%-gross case as a fixture.

### 5.4 [RESOLVED — single-writer money path: worker proposes, D applies]

Docs split on worker-writes-book vs control-plane-sole-writer. **Resolution: topology's invariant wins — the worker computes the target book and PROPOSES a delta; D is the sole writer, applying it in one `SELECT … FOR UPDATE` transaction with an optimistic `version` backstop and a per-deployment advisory lock.** This matches security's "single TenantSession writer." `paperbook`/`execution` live once in `ithaca-core`, imported by both the `execution.*` MCP tools and the runtime.

### 5.5 The two runtimes (shared core)

Backtest and paper-live differ only in **clock** and **data window source**; same evaluator, same accounting, same risk gate.
- **Backtest:** simulated clock; one bulk PIT pull at job start; replays bar-by-bar seeing only `data[:i+1]`; CPU burst; emits curve + stats + overfitting diagnostics.
- **Paper-live:** wall-clock, scheduler-driven on `rebalance` cadence; **stateless tick worker, not a daemon** (each tick loads book → evaluates → proposes delta → exits; a crash loses one tick, not the book). Fills against `PaperVenue` on **real current prices**.

### 5.6 Brokerage seam (interface only — do NOT build)

```python
class ExecutionVenue(Protocol):
    def quote(self, symbols, as_of) -> dict[str, Quote]: ...
    def place_orders(self, orders, *, idempotency_key) -> list[Fill]: ...  # MUST be idempotent
    def positions(self) -> list[Position]: ...
    def venue_caps(self) -> VenueCaps: ...
```
`PaperVenue` is the only launch impl. `idempotency_key` is mandatory **now** (retried ticks must not double-fill). `deploy:live` scope is unissuable; no real adapter exists in the dependency graph.

### 5.7 [RESOLVED + CUT-FOR-v2.0 — DigitalOcean topology]

**Choice: DOKS + two node pools + Managed Postgres + Spaces + VPC.** App Platform rejected (no cgroup/NetworkPolicy/scale-to-zero for jobs); raw Droplets rejected (reinventing K8s). But per feasibility #2, **launch with plain containers + cgroups + NetworkPolicy egress-deny + `activeDeadlineSeconds`** — no gVisor/Kata at launch. Topology:
- **VPC** with cluster + Managed Postgres + the Data Gateway facade. Workers have **no public egress**; one NetworkPolicy allow to the Gateway ClusterIP.
- **Node pool `backtest`** — CPU-optimized, autoscale **min 0 → max N**; backtests as K8s Jobs (`restartPolicy: Never`, `activeDeadlineSeconds` = aggregate deadline). Scale-to-zero = cost control.
- **Node pool `paper`** — small stable pool for the market-calendar-aware scheduler + short tick Jobs.
- **State:** Managed Postgres (RLS), Spaces (artifacts), optional managed Redis for the queue.

---

## 6. Web UI plan

The UI is a **read-mostly observability + control surface**. No chat console; the "conversation" is the **agent trace**. Fed by the thin REST/SSE gateway (B) — the browser **never speaks MCP**.

### 6.1 Information architecture

Six views via a left rail: **Runs** (the centerpiece), **Algos**, **Deploys** (Backtests / Paper-Live tabs), **Trades**, **Ideas**, **Boards**. Global header carries connected-agent status, active Run selector, and a **PAPER** badge.

### 6.2 The centerpiece — visualizing external-agent reasoning

Three-column trace at `/runs/:runId`: **Reasoning rail** (left) · **Tool-call timeline** (middle, the spine) · **Evidence panels** (right). Each `tool_result` carries a `panelType` that keys a **static renderer registry** → renders the matching v1 panel with the result `data`. *A tool call is a question; the panel is the answer; the reasoning is why it was asked.*

**[RESOLVED — reasoning-optional-first, feasibility #5]** A BYO host will almost never volunteer chain-of-thought. So: **the tool-call timeline + evidence panels must be the compelling product with ZERO reasoning.** The reasoning rail is an opt-in enhancement (fed by an `emit_reasoning` tool / MCP notifications when the host supports it; otherwise it collapses and the timeline widens). Deterministic, non-LLM templated annotations (tagged `derived:true`) are the realistic primary fill — designed as such, not a footnote. The aggregate run-deadline bar is first-class in the header (makes a runaway run obvious — the v1 "no aggregate deadline" lesson, visualized).

Trace is **event-sourced** (`TraceEvent[]` + `playhead`); render is pure `select(events, playhead)`, so **live is "playhead pinned to latest seq"** and replay is the same component with a scrubber.

### 6.3 [RESOLVED — `panelType` is part of the tool-output contract, integration #8]

`panelType` is added to the tool-result envelope in `packages/contracts`, and the named panel's prop shape becomes part of the tool output contract. **Contract test:** every tool with a `panelType` produces `data` the named panel renders without `as any`. Unregistered `panelType` → safe static JSON/table viewer (zero eval).

### 6.4 v1 panels: keep / drop

- **KEEP & repurpose (~79 panels)** as display-only tool-output renderers: all the quant/data/strategy panels (`BacktestPanel`, `PerformancePnlPanel`, `FactorAttributionPanel`, `NewsPanel`, `RiskMonitorPanel`, …). Strip `Refine`/`onRefine` (that nudged v1's own agent — gone). Reuse `layout.ts`, `Dashboard.tsx` grid, `Sparkline`, `CoverageBadge`, and the SSE `data:`-chunk parser.
- **DROP:** chat console (`ChatPanel`, console hooks), voice mode, navigator/tour (salvage only the highlight mechanic), and — critically — **`panels/generated/` + the `sucrase` dependency entirely** (the `new Function` client-side RCE). No client-side codegen/eval ever.

---

## 7. Cross-cutting (designed away from v1's failure modes)

| v1 failure | v2 structural fix |
|---|---|
| Static-guard-then-trust → 2 RCEs | No in-process eval of any agent/LLM code. Strategies are declarative data we validate. No client-side codegen. |
| "Never crash" swallowing erases audit | Every tool call, transition, fill, and denial is an append-only trace event; bare `except: pass` banned on audited paths. |
| Tenancy per-store, not invariant | See below — RLS + scoped data layer + CI gate. |
| Unlocked read-modify-write on money | Worker proposes delta; D is sole writer under `FOR UPDATE` + version (§5.4). |
| Per-call timeouts, no aggregate budget | Wall-clock budget per request/session/job; shrinking per-call timeout = `min(default, remaining)`. |
| Tests exist but don't gate | CI gates from Phase 0 (§9). |

- **[RESOLVED — auth, integration #6]** security's account model is authoritative: **Tenant → User → Agent (stable principal) → Credential (rotatable secret).** topology and datalayer adopt `agent_id` as the stable principal and the **`ith_<env>_<keyid>_<secret>`** key format (only `sha256(secret)` stored). Effective permission = **role ∩ scope ∩ tenant**. Capability scopes (`data:read`, `strategy:author`, `deploy:backtest`, `deploy:paper`; `deploy:live` **unissuable at launch**). topology's "agent can propose, not promote" is expressed as the *absence* of self-promote on `deploy:paper`, not a hardcoded rule.
  - **[CUT-FOR-v2.0, feasibility #11]** Launch with **hashed API keys + per-principal rate limits + append-only audit + RLS**. Defer OAuth device-code, 15-min token exchange, hash-chained tamper-evidence, MFA, and edge WAF to post-pilot.
- **Tenant isolation as a HARD INVARIANT.** **[RESOLVED — one tenant key, integration #5]** Canonical name `tenant_id` (uuid), one GUC `app.tenant_id`, in `packages/contracts`; the `firmId`/`firm_id` aliases are **banned in CI.** Two defense layers: (A) **Postgres RLS** with `FORCE ROW LEVEL SECURITY` and `SET LOCAL app.tenant_id` per txn — a forgotten filter returns *zero rows, not another tenant's*; (B) a scoped data layer where unscoped queries are un-expressible (no raw `db.execute`; only a `TenantSession` from `ctx`). A CI test enumerates every tenant-eligible table and **fails the build** on any missing RLS policy or nullable `tenant_id`. **[Budgeted per feasibility #12]:** non-owner app role, PgBouncer transaction-mode + `SET LOCAL` interaction tested on the *pooled* path, and the global-upstream-cache exception (public market data, shared by design) lives in **one reviewed module**, not ad-hoc per call site.
- **Sandboxing:** §5.2 — out-of-process, deny-all egress, cgroup + deadline; microVM deferred to `CustomPythonNode`.
- **Secrets:** control plane holds infra secrets; workers get only short-lived per-job tokens scoped to `tenant/<id>/jobs/<jobid>/`. No secret on a worker disk.
- **Audit:** append-only, tenant-attributed, principal-stable across credential rotation. The run event log *is* the audit trail.
- **Deadlines:** aggregate wall-clock at every entry; long jobs are async with heartbeats (never bounded by an HTTP proxy ceiling).
- **[RESOLVED — money-path freshness floor, feasibility #10]** Provenance honesty protects the *agent's reasoning*, not the *fill engine*. The paper-live tick declares a **max-staleness tolerance and skips-and-alerts** when data exceeds it, rather than filling on stale marks. Freshness is a hard precondition on the money path, distinct from the soft display label on the research path.
- **[RESOLVED — one event schema + sequencer, integration #7]** One `TraceEvent` schema in `packages/contracts` (reconcile the `kind`/`type` enums). **`seq` is per-`run_id`, owned by a single writer per run.** Since research (data layer) and deploy (control plane) write to the *same* `trace_event` store, the chain is stitched by `origin_session_id` + `parent_span`; we **do not claim gap-free `seq` across two independently-writing services** (that's impossible without a shared sequencer) — `seq` is gap-free *within a run*, lineage links runs. **SSE standardizes on `Last-Event-ID` carrying `seq`** (native EventSource), with documented server replay-from-`seq`; the `?from_seq=` variant is dropped. Heartbeat format (`: keepalive` + `run_progress`) lives in `contracts` so all producers emit the same keepalive.
- **[RESOLVED — event bus scaling, feasibility #6]** Postgres LISTEN/NOTIFY is fine for Phase 1–2 but **not blessed as the uncritical launch bus** (8000-byte NOTIFY cap; SSE replay scans the system-of-record). Write the `(run_id, seq)` consumer against an **interface from day one**; set a concrete threshold (events/sec, concurrent SSE clients) at which **observability fan-out moves to Redis Streams** — config, not rewrite. Money-path events stay transactional in Postgres.
- **Paper-only by construction:** `deploy:live` unissuable, real adapter not in the dependency graph, `mode:"paper"` asserted at process start, everything labeled PAPER.

---

## 8. Repo structure & tech stack

```
ithaca2/                              # monorepo: uv (Python) + pnpm (TS)
├── packages/contracts/                 # FROZEN P0 — single source of truth
│   ├── schema/  {events, strategy_spec, provenance, tenant, auth}
│   ├── py/      (generated pydantic)   └── ts/ (generated zod)   # CI fails on drift
├── ithaca-core/                      # PYTHON — the ONE shared core (imported, never re-ported)
│   ├── engine/        # PORTED v1 (pure numpy, fix-on-port)
│   ├── sources/       # PORTED v1 adapters + _resilient (+ asOf, + pit flag)
│   ├── registry/      # strategy primitives (DAG ops deferred)
│   ├── graph/         # evaluator (one seam for primitives now, DAG later)
│   ├── accounting/    # paperbook + execution + TCA
│   ├── risk/          # post-projection gross-L1 attestation (THE boundary)
│   └── gateway/       # Data Gateway facade: asOf truncation, provenance, breakers
├── services/
│   ├── mcp-gateway/   # PYTHON — official MCP SDK; thin over core
│   ├── rest-gateway/  # PYTHON FastAPI — UI reads + SSE + human control actions
│   ├── control-plane/ # PYTHON FastAPI — specs, run state machine, compliance gate, SINGLE WRITER
│   └── runtime/       # PYTHON — backtest_runner + live_runner; imports ithaca-core
├── web/               # TS/React/Vite — observability UI; static renderer registry; NO sucrase
├── infra/             # Terraform (DOKS, Managed PG, Spaces, VPC, NetworkPolicy), Docker, compose
└── .github/workflows/ci.yml            # the gate (P0)
```

| Concern | Choice | One-line rationale |
|---|---|---|
| Backend language | **Python 3.12 end-to-end** | Crown-jewel quant + the security-boundary validator are numpy/Pydantic; polyglot re-introduces divergence bugs. |
| Quant engine | **numpy, ported as-is** | Proven, pure, deterministic; rewriting is pure downside. |
| MCP | **Official Python MCP SDK** (streamable-http + stdio) | First-party tool/schema support; co-located with core = in-process calls. |
| Control plane / gateways | **FastAPI** | Reuse v1's proven SSE + tenant contextvar; small money-path service scales independently. |
| Datastore | **Managed Postgres 16 + RLS** | Tenant isolation as a DB invariant; `FOR UPDATE` for the money path. |
| Object store | **DO Spaces** | Artifacts/logs/blobs; keeps Postgres lean. |
| Queue | **Postgres-backed (`pgmq`/graphile-worker)** | Avoids a second stateful system early; runs are versioned rows. |
| Real-time | **SSE, `Last-Event-ID`** | One-way append-only fan-out; trivial reconnect/replay; heartbeats fix v1's idle-kill. |
| Compute | **DOKS, plain containers + cgroups + NetworkPolicy** | Per-pod limits + egress-deny invariant; microVM deferred until untrusted code ships. |
| IaC | **Terraform + Docker** | Reviewable, reproducible; deploy layer gets real IaC, not click-ops. |
| Web UI | **React + Vite + TS** | Keep the terminal aesthetic as an observability surface; reuse panels, drop chat + codegen. |
| Observability | **structlog JSON + OpenTelemetry** | Correlates tool-call → backtest → fill; answers v1's "no logging." |

---

## 9. Phased roadmap

**The thinnest credible first *shippable* slice = Phase 1 + Phase 2** (agent calls in-process tools; UI renders the trace + a price-only backtest) — no DO, no deploy layer, no sandbox. This proves the entire vision and defers every hard infra problem.

**Critical path:** P0 → P0.5 (spikes) → P1 → P2 → P3 → P4. P5 is breadth on a proven spine.

**Phase 0 — Skeleton + the gate + frozen contracts.** Monorepo; `packages/contracts` with one round-trip schema generating pydantic + zod; empty service stubs; compose local stack; **CI as a required check** (lint/typecheck/tests; RLS-coverage test; pydantic⇄zod round-trip). *Exit:* a breaking contract change turns CI red and locks merge. *Demoable:* "the gate works."

**Phase 0.5 — Three de-risking spikes (parallel, before committing the rest) [feasibility #3].** (a) prove plain-container egress-deny + scale-to-zero on a throwaway DOKS cluster (and whether gVisor is even needed/viable — it isn't at launch); (b) produce **one defensibly-PIT backtest** and enumerate exactly which sources support it; (c) prove MCP trace + session correlation survive ≥2 real agent hosts (Claude/GPT). *Exit:* all three green or the plan changes. *Demoable:* a recorded real-host trace + one honest backtest.

**Phase 1 — Data Layer walking skeleton.** Port `engine/{stats,backtest,strategies,signals}` + `sources/prices`; stand up the MCP server exposing `market.get_ohlcv` + `backtest.run` (in-process, on the agent's machine). Wire a real BYO agent. *Exit:* an external agent discovers the tools, runs a real backtest, gets a provenance block. *Demoable:* **the core vision in miniature.**

**Phase 2 — Observability.** REST/SSE gateway + trace ingest; UI three-column trace (reasoning-optional-first) + backtest evidence panel, heartbeats keeping SSE alive. *Exit:* the live trace + equity curve render in real time. *Demoable:* **watch your agent think and produce an algo.**

**Phase 3 — Deploy Layer: one backtest on DigitalOcean.** Terraform up Managed PG (RLS) + Spaces + a backtest worker; control-plane `runs/` (versioned) enqueues, worker pulls, runs with an **aggregate deadline**, writes artifact. `propose_strategy` + human "Backtest" action wired. *Exit:* human-accepted spec → backtest on DO → firm-scoped result in UI. *Demoable:* **full vision end-to-end (research → propose → backtest on DO → observe).**

**Phase 4 — Live paper deployment.** `live_runner` + market-calendar scheduler; deployed strategy ticks on **real data**, proposes deltas, D applies under `FOR UPDATE`; freshness floor + skip-and-alert; Trades/Deploys panels go live. *Exit:* promote → ticks on real intraday → paper fills stream into Trades. *Demoable:* **a strategy paper-trading live, observable in real time.**

**Phase 5 — Breadth + hardening.** Remaining sources/engine modules as tools (news, edgar, fundamentals, rates, 13F, polymarket, risk/attribution); News/Ideas view; Boards; Redis Streams fan-out at threshold; OAuth/WAF/hash-chain audit tier; (gated spike) the operator-DAG + `CustomPythonNode` microVM. *Exit:* full catalog discoverable; load + canary gates green. *Demoable:* **the full tool-platform** — multi-source research → optimized strategy → live paper deploy.

---

## 10. Top risks & open questions

1. **PIT data honesty (CRITICAL, decided but watch).** Free sources can't deliver true PIT. We've scoped to price-only backtests and a `pit` capability flag. **Open:** budget/timeline for a vintaged fundamentals source (Sharadar/Compustat) to unlock the factor-backtest use case that is arguably the product's headline.
2. **Real-host trace fidelity (HIGH, spike-gated).** The reasoning rail may be empty against real hosts, and sessions may fragment across reconnects. P0.5(c) must confirm what we actually get before IA is finalized. **Open:** do we ship the reasoning rail at all in v2.0, or only the templated `derived` annotations?
3. **DO sandbox/egress viability (HIGH, spike-gated).** Plain-container egress-deny + scale-to-zero is assumed sufficient. P0.5(a) must validate NetworkPolicy + cluster-autoscaler behavior on DOKS. **Open:** does anyone on the team have DOKS-in-anger experience? If not, staff or budget for it.
4. **Event-bus scaling cliff (MEDIUM-HIGH).** Postgres LISTEN/NOTIFY has an 8KB cap and SSE replay hits the system-of-record. Mitigated by the day-one consumer interface. **Open:** the exact events/sec + concurrent-SSE threshold to trigger the Redis Streams cutover.
5. **Risk attestation completeness (MEDIUM-HIGH).** The post-projection gross-L1 gate must catch the general infeasibility class, not just the trivial cases. **Open:** enumerate the construction-scheme × constraint combinations that need explicit fixtures beyond the v1 311%-gross case.
6. **Operator-DAG deferral (MEDIUM).** Shipping parameterized primitives is faster but less expressive. **Open:** what fraction of target strategies the primitives actually cover, and the trigger to invest in the DAG.
7. **Spec handoff mechanism (MEDIUM).** datalayer never defined how a research session's analysis becomes a `StrategySpec` row. **Open:** the `propose_strategy` builder contract — which service writes the draft, under which `run_id`/`origin_session_id`, and how the UI shows "this proposal came from that research."
8. **Team size / parallelization (MEDIUM).** The plan assumes parallel workstreams (Quant, Control-plane, Runtime, UI, Infra) after P0 contracts freeze. **Open:** is the team large enough to run WS-A…E in parallel, or does the critical-path spine (P0→1→2→3→4) need to be strictly sequential?