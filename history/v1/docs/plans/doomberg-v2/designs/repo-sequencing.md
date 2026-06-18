# Design: Repo Structure, Tech Choices & Phased Sequencing

I now have a complete picture of v1: ~5000 LOC of pure numpy quant engine (15 modules), ~4000 LOC of keyless data adapters (12 sources) behind a resilience wrapper, 79 skills, a 297KB agent.py orchestrator and the RCE-laden codegen path to drop, plus an existing TS/pnpm/drizzle/zod workspace. I have the review's six cross-cutting lessons. Here is the design doc.

---

# Doomberg v2 — Repo Structure, Tech Stack & Phased Build Sequence

**Status:** Design proposal | **Date:** 2026-06-16 | **Supersedes:** v1 monolith at `artifacts/api-server/app`

Doomberg v2 is a **financial tool-platform**: the user's own agent calls Doomberg's tools (DATA LAYER), deploys accepted strategies (DEPLOY LAYER), and watches it work in a web UI that **observes** the external agent rather than running it. MCP is the primary interface; a thin REST/SSE layer feeds the UI from the same core. Paper execution only at launch, with a pluggable brokerage seam.

This doc bakes in the six cross-cutting lessons from the v1 architecture review so we do not repeat them:
1. **No static-guard-then-trust.** We drop v1's `code_guard.py`/`dynamic_skills.py`/`feature_builder.py` codegen path entirely. v2 ships *no runtime codegen*. Tools are static, typed, code-reviewed. (If user-authored strategy code ever returns, it runs out-of-process, network-denied, rlimited — never `exec_module` in an API process.)
2. **No silent swallowing.** Structured logging + typed errors from day one; no bare `except: pass`.
3. **Tenant isolation is an invariant, not per-call-site.** Enforced in one place (a tenant-scoped repository layer + Postgres RLS), not re-implemented per store.
4. **No unlocked read-modify-write on the money path.** All mutable book/strategy/run state mutates via `SELECT … FOR UPDATE` or optimistic version guards, in one txn.
5. **Aggregate deadlines, not just per-call timeouts.** Every multi-step operation (backtest, live tick cycle) carries a wall-clock budget.
6. **Tests gate from day one.** GitHub Actions `required` checks; a merge cannot land red. This is built in Phase 0, before features.

---

## 1. Monorepo vs polyrepo + top-level layout

**Decision: single monorepo, pnpm + uv workspaces.** Rationale:
- v2's value is a **shared contract** (tool schemas, panel/event schemas, run records) consumed by Python (MCP/quant/workers), TypeScript (control-plane API, web UI), and IaC. A monorepo lets one source-of-truth schema package generate Python (pydantic) and TS (zod) types, so a contract change fails CI in every consumer atomically — the opposite of v1, where panel data was `as any` and drift was invisible until render.
- v1 already uses a pnpm workspace + uv (`pnpm-workspace.yaml`, `uv.lock`) with `lib/db`, `lib/api-zod`, `lib/api-client-react`. We keep that proven shape and extend it; polyrepo would re-introduce the cross-repo version skew that made v1's contract drift undetectable.
- Atomic refactors across DATA↔DEPLOY↔UI in one PR; one CI gate covers all languages.

```
doomberg2/
├── pnpm-workspace.yaml          # TS workspaces: services/*, web, packages/*
├── pyproject.toml + uv.lock     # uv workspace: py packages below
├── turbo.json                   # task graph / caching for TS build+test+lint
├── Makefile                     # one entrypoint: make test|lint|typecheck|up
├── .github/workflows/ci.yml     # the gate (Phase 0) — see §6
│
├── packages/                    # SHARED CONTRACTS (the spine)
│   ├── contracts/               # canonical schemas, language-neutral source of truth
│   │   ├── schema/              # JSON Schema / .proto-free: authored as zod+pydantic generated from one IR
│   │   │   ├── tools/           # MCP tool input/output schemas (one file per tool family)
│   │   │   ├── events/          # agent-observation event envelope, run lifecycle events
│   │   │   ├── panels/          # UI panel data shapes (trades, news, algos, trace)
│   │   │   └── runs/            # backtest + live run records, fills, positions
│   │   ├── ts/                  # generated zod + TS types (published as @doomberg/contracts)
│   │   └── py/                  # generated pydantic models (doomberg_contracts)
│   ├── provenance/              # shared {source, asOf, freshnessSec, mode, coverage} type (review lesson)
│   └── tsconfig/ + eslint/      # shared TS config
│
├── services/
│   ├── data-mcp/                # PYTHON — DATA LAYER: MCP server (primary agent interface)
│   │   ├── doomberg_data/
│   │   │   ├── server.py        # MCP server: registers tools, SSE/stdio + streamable-http transport
│   │   │   ├── tools/           # one module per tool family; thin wrappers over engine+sources
│   │   │   │   ├── news.py  insider.py  fundamentals.py  prices.py
│   │   │   │   ├── factors.py  signals.py  backtest.py  optimize.py  risk.py
│   │   │   ├── engine/          # PORTED from v1 app/engine (crown jewel, pure numpy)
│   │   │   ├── sources/         # PORTED from v1 app/sources (keyless adapters + _resilient)
│   │   │   ├── observe.py       # emits agent-observation events to control-plane (tool call/args/result)
│   │   │   └── budget.py        # aggregate deadline helper (review lesson #5)
│   │   └── tests/
│   │
│   ├── control-plane/           # TYPESCRIPT — DEPLOY LAYER API + UI backend
│   │   ├── src/
│   │   │   ├── http/            # REST + SSE (feeds web UI from same core)
│   │   │   ├── runs/            # backtest + live "prod" run orchestration (create/start/stop)
│   │   │   ├── do/              # DigitalOcean integration (provision/scale CPU clusters, droplet/k8s API)
│   │   │   ├── observe/         # ingest agent-observation events; fan out to UI via SSE
│   │   │   ├── tenancy/         # the ONE place firm isolation is enforced (repo layer + RLS guard)
│   │   │   └── db/              # drizzle schema + migrations (extends v1 lib/db pattern)
│   │   └── tests/
│   │
│   ├── runtime/                 # PYTHON — DEPLOY LAYER worker that runs on DO CPU clusters
│   │   ├── doomberg_runtime/
│   │   │   ├── backtest_runner.py   # pulls run spec, calls engine, streams progress + result
│   │   │   ├── live_runner.py       # live market data → strategy → PAPER book (simulated fills)
│   │   │   ├── paperbook.py         # PORTED from v1 engine/paperbook.py
│   │   │   ├── brokerage/           # pluggable adapter SEAM (PaperAdapter only at launch)
│   │   │   └── checkpoint.py        # crash-safe run state (FOR UPDATE / versioned, review lesson #4)
│   │   └── tests/
│   │
│   └── scheduler/               # job queue + cron for live run ticks (could be part of control-plane)
│
├── web/                         # TYPESCRIPT/React — OBSERVABILITY UI (no chat console)
│   ├── src/
│   │   ├── panels/              # Trades, News/Ideas, Algos, AgentTrace (the showcase)
│   │   ├── dashboard/           # user-configurable tile layout
│   │   └── lib/                 # SSE client, generated @doomberg/contracts types
│   └── tests/
│
└── infra/                       # IaC for DigitalOcean
    ├── terraform/               # DO droplets/DOKS, managed Postgres, Spaces, VPC, firewall
    ├── docker/                  # service Dockerfiles + runtime image baked with engine
    └── compose/                 # local dev stack (postgres, spaces-compat minio, services)
```

---

## 2. Tech-stack decisions + rationale

| Concern | Choice | Rationale |
|---|---|---|
| **DATA LAYER / MCP server** | **Python** (`services/data-mcp`) | The crown jewels (`engine/`, `sources/`) are ~9000 LOC of proven numpy/httpx Python. The MCP server must be co-located with them to call in-process with no IPC tax. Python wins here unambiguously. |
| **MCP SDK** | **Official Python MCP SDK** (`mcp` / `modelcontextprotocol`, FastMCP-style decorators) | Anthropic's official SDK; MCP is the *primary* interface so we want first-party tool/schema support, streamable-HTTP + stdio transports, and the cleanest path for BYO agents (Claude/GPT/custom) to discover tools. v1 had no MCP — this is greenfield. (Verify exact package/version against current SDK docs before pinning; do not assume from memory.) |
| **Quant engine** | **Python + numpy** (ported as-is) | Deterministic, network-free, already unit-test-shaped. Don't rewrite proven math. |
| **Control plane / DEPLOY API** | **TypeScript (Node, Express 5 or Fastify)** | Reuses v1's working `lib/db` (drizzle), `lib/api-zod`, pino logging stack and pnpm tooling. The control plane is I/O-bound orchestration (DO API, SSE fan-out, run records) where TS's async story + shared zod contracts with the UI are a strong fit. Keeps the heavy CPU work in Python where it belongs. |
| **DEPLOY runtime / workers** | **Python** (`services/runtime`) | Runs the *same engine* the agent backtested against — using one language for backtest and live eliminates a backtest-vs-live divergence class of bug. Runs on DO CPU clusters in the engine Docker image. |
| **Web UI** | **React + Vite + TS** (extends v1's `lib/api-client-react`) | Keep the "visual terminal" feel as an observability surface. Reuse v1 panel components where the *render* logic is sound, but every panel gets a per-panel error boundary + provenance badge from the start (review lessons). Remove the chat console. |
| **Primary datastore** | **Managed Postgres (DO Managed DB)** | Tenants, strategies, run records, fills, positions, observation events. **Row-Level Security on by default** so tenant isolation is a DB invariant, not per-query (review lesson #3). |
| **Object storage** | **DO Spaces (S3-compatible)** | Backtest result artifacts, large tick captures (the v1 IEX DEEP path), agent-trace blobs. Keeps Postgres lean. |
| **Queue / scheduler** | **Postgres-backed queue (e.g. `pgmq`/`graphile-worker`) for v1 of v2; Redis only if needed** | Avoids a second stateful system early. Backtest jobs + live-run tick scheduling go through one durable queue with visibility timeouts + aggregate deadlines. A run is a row with a version column (no lost updates). |
| **Real-time to UI** | **SSE** (not WebSockets) | One-way server→browser fan-out of observation + run events; SSE is simpler, proxy-friendly, and v1 already uses it. We fix v1's gap: **heartbeats during blocking work** so idle-timeout proxies don't kill streams. |
| **IaC** | **Terraform** for DO (droplets/DOKS, Managed PG, Spaces, VPC, firewalls) + **Docker** images | Declarative, reviewable, reproducible CPU-cluster provisioning. The deploy layer is "built fresh" so it gets proper IaC, not click-ops. |
| **Observability** | structured JSON logs (pino/structlog), OpenTelemetry traces correlating agent tool-call → backtest → fill | Directly answers v1's "no logging at all" finding; the agent-trace is also a *product surface*, so we instrument it as a first-class citizen. |

---

## 3. What to PORT from v1 — concrete plan

**Crown jewels (port first, nearly verbatim):**

| v1 path | LOC | v2 destination | Notes |
|---|---|---|---|
| `app/engine/` (15 modules: backtest, signals, optimize, riskmodel, stats, attribution, execution, montecarlo, scenario, stress, strategies, portfolio, borrow, compliance, paperbook) | ~5000 | `services/data-mcp/.../engine/` + `paperbook.py`→`runtime/` | Pure numpy, network-free, already designed for isolated unit tests. Port as a package. **Fix-on-port** the review's quant bugs: optimizer gross-L1 re-check (`optimize.py:177`), Carino-link attribution (`attribution.py:357`), cross-sectional forward-window alignment (`signals.py:342`), rename `var95`→`terminalVar95` (`montecarlo.py:112`). |
| `app/sources/` (12 adapters: prices, news, edgar, fundamentals, congress, thirteenf, rates, sectors, sentiment, polymarket, iex_deep, holdings) + `_resilient.py` | ~4000 | `services/data-mcp/.../sources/` | Keyless/free adapters behind the resilience wrapper — directly become MCP data tools. **Fix-on-port**: route Treasury/FRED through `_resilient` (`rates.py:91`), add wall-clock byte-cap to IEX DEEP reconstruct (`iex_deep.py:450`), reuse one keep-alive httpx client, EDGAR overflow paging. Add a **provenance block** `{source, asOf, freshnessSec, mode, coverage}` to every adapter return. |

**Adapt / re-skin (logic sound, structure changes):**
- v1 `lib/db` (drizzle) → `services/control-plane/.../db` — reuse the drizzle migration pattern; new schema for tenants/runs/fills/observations with **RLS + version columns**.
- v1 panel React components → `web/src/panels` — port render logic for Trades/News/Algos; wrap each in an error boundary; add provenance badge.
- v1 `_resilient.py` breaker/backoff → keep as-is; it's good.

**Drop entirely (do NOT port):**
- `app/agent.py` (297KB orchestrator, 197-branch heuristic) — v2 does not run the agent loop. **Deleted.**
- `app/code_guard.py`, `app/dynamic_skills.py`, `app/feature_builder.py`, `app/skills_generated/` — the runtime-codegen RCE path. **Deleted.** No replacement at launch.
- v1 chat console / `ChatPanel.tsx` / console conversation hooks — UI is observe-only.
- v1 in-process `exec_module`/`new Function` panel eval — replaced by static typed panels.

**Port-as-tools mapping:** v1's 79 skills (`skills.py`) are not ported as the skill abstraction; instead the *underlying engine + source calls* they wrapped become a curated set of **static MCP tools** in `data-mcp/tools/` (news, prices, insider, fundamentals, factors, signals, backtest, optimize, risk). One tool family per file, each with a contract schema in `packages/contracts/tools/`.

**Porting sequence:** (1) `engine/stats`+`backtest`+`strategies`+`signals` (smallest closure that runs a backtest) → (2) `sources/prices` (feeds backtest) → (3) wrap both as 2-3 MCP tools → (4) remaining sources → (5) optimize/risk/attribution.

---

## 4. Phased roadmap (exit criteria + demo)

**Phase 0 — Skeleton + the gate (the thinnest *infrastructure* slice).**
Monorepo scaffold, `packages/contracts` with one round-trip schema generating both pydantic + zod, empty service stubs, Docker compose local stack, and **CI that gates** (lint + typecheck + tests as required checks; a red PR cannot merge).
*Exit:* a trivial contract change that breaks a TS consumer turns CI red and blocks merge. *Demo:* "the gate works" — push a breaking change, watch the merge button lock.

**Phase 1 — DATA LAYER walking skeleton: one tool, one agent call.**
Port `engine/stats+backtest+strategies+signals` + `sources/prices`. Stand up the Python MCP server exposing **two tools**: `get_price_history` and `run_backtest` (in-process, synchronous, on the agent's machine — no DO yet). Wire a BYO agent (Claude) to the MCP server.
*Exit:* an external agent discovers the tools, calls `get_price_history` then `run_backtest`, and gets a real numpy backtest result with a provenance block. *Demo:* **the core vision in miniature** — your own agent reaches a decision about a stock using Doomberg tools.

**Phase 2 — OBSERVABILITY: render the agent's work.**
Control-plane SSE + `observe/` ingest; `data-mcp/observe.py` emits tool-call/args/result/timing events. Web UI panels: AgentTrace (live tool calls), and a results panel for the backtest. No DO yet.
*Exit:* agent makes calls in Phase 1; UI renders the live trace + backtest equity curve in real time, with heartbeats keeping the SSE stream alive through blocking work. *Demo:* **watch your agent think and produce an algo** in the terminal UI.

**Phase 3 — DEPLOY LAYER: one backtest run on DigitalOcean.**
Terraform up Managed PG + Spaces + a DO CPU worker; `services/runtime/backtest_runner.py` in the engine Docker image; control-plane `runs/` creates a run row (versioned), enqueues it, worker pulls it, runs the engine **with an aggregate deadline**, streams progress, writes the artifact to Spaces. Tenancy enforced via RLS from this point.
*Exit:* agent's accepted plan → "Deploy backtest" → run executes on a DO worker → result + artifact rendered in UI, scoped to the firm. *Demo:* **the full vision end-to-end** — MCP tool → agent call → backtest on DO → rendered in UI.

**Phase 4 — LIVE paper deployment.**
`runtime/live_runner.py` + scheduler tick: a deployed strategy runs on **live market data** filling against the simulated `paperbook` via `PaperAdapter` (the pluggable seam). Positions/fills persisted with FOR UPDATE. Trades + Algos panels go live.
*Exit:* deploy a strategy "to prod"; it ticks on real intraday data, books paper fills, and the Trades panel updates live. *Demo:* **a strategy running live, paper-trading, observable in real time.**

**Phase 5 — Capability breadth + hardening.**
Port remaining sources (news, edgar/insider, fundamentals, rates, 13F, polymarket, IEX DEEP) and engine modules (optimize, risk, attribution, stress) as additional MCP tools; News/Ideas panel; multi-tenant admin; canary + load gates in CI; DO cluster autoscaling.
*Exit:* full tool catalog discoverable; News/Ideas + factor/risk tools in use; load + canary gates green. *Demo:* the **full tool-platform** — an agent doing multi-source research → factor model → optimized strategy → live paper deploy.

*Critical-path spine:* Phase 0 → 1 → 2 → 3 → 4. Phase 5 is breadth layered on a proven spine.

---

## 5. Parallelization + critical-path dependencies

**Hard dependency (the spine, must be sequential):** `contracts` (P0) → MCP tools (P1) → observation events (P2) → run orchestration on DO (P3) → live runner (P4). Each depends on the prior's schema being frozen.

**The unlock:** `packages/contracts` is the critical enabler. Land schemas for tools/events/runs/panels **first** (P0). Once frozen, every workstream codes against generated types in parallel and integrates without surprises.

**Parallel workstreams after P0 contracts land:**
- **WS-A Quant/Data (Python):** port engine + sources, build MCP tools. *Owns the spine through P1; can keep porting modules ahead of need.*
- **WS-B Control-plane (TS):** DB schema + RLS, runs API, SSE, observe ingest, DO integration. *Can build the runs API + SSE skeleton against contract types before WS-A's tools exist (mock tool events).*
- **WS-C Runtime (Python):** backtest_runner, live_runner, paperbook, brokerage seam. *Shares the engine package with WS-A; can develop the runner harness against a stub engine, swap in the real one when WS-A ports it.*
- **WS-D Web UI (TS):** panels + dashboard + SSE client. *Builds entirely against contract panel/event types + recorded fixture event streams — fully parallel, no live backend needed until P2 integration.*
- **WS-E Infra (Terraform/Docker):** DO provisioning, images, compose. *Independent; only gates P3. Start immediately so DO is ready when the runner is.*

**Sync points:** P1 (WS-A tools real → WS-D swaps fixtures for live), P3 (WS-B + WS-C + WS-E converge for first DO run). Mock/fixture-against-contract is what keeps WS-B/D/E from blocking on WS-A.

---

## 6. Testing/CI that ACTUALLY gates (from day zero)

v1's failure was concrete: only 3 of 33 suites carried `isValidation`, there were no `.github/workflows`, perf gate defaulted off, and the tested paths weren't the shipped paths (orchestrate tests forced `ai_available=False`). v2 fixes the *mechanism*, in Phase 0, before features.

- **`.github/workflows/ci.yml` as the single required gate**, branch-protection enforced: a PR cannot merge while red. This exists before the first feature lands.
- **All suites run, every PR.** Turbo (TS) + uv/pytest (Python) run the *entire* test graph. There is no per-suite opt-in flag; "exists but doesn't run" is structurally impossible.
- **Test the path that ships.** Contract tests assert pydantic⇄zod round-trip on every schema (no `as any`). MCP tools are tested through the real server interface, not internal stubs. The backtest is tested against a golden fixture series with a numerically pinned result. Tenancy: an RLS test that *attempts* cross-firm access and asserts it's denied — isolation is a tested invariant, not a hope.
- **Determinism in the gate.** Engine/quant tests are pure and seeded (no network, no live yfinance) — the opposite of v1's `panel-runtime-test` that coupled build + live server + LLM + live yfinance into one flaky gate. Live-source adapters are tested against recorded fixtures; a separate *non-gating* nightly job hits real upstreams.
- **Money-path concurrency tests.** Explicit tests that concurrent run/book mutations don't lose updates (asserts FOR UPDATE/version-guard behavior).
- **Budget tests.** Assert aggregate-deadline helpers abort chained operations before the proxy ceiling.
- **Load + canary gates default ON** (fix `LOAD_GATE_LATENCY=0`): per-endpoint latency budgets in CI from the start; post-deploy `/canary` monitoring in the deploy workflow.
- **Pre-merge `/review`, post-merge `/document-release`** per the repo's gstack workflow; CI is the hard gate, review is the soft gate.

**Key files to inspect when implementing:** v1 crown jewels to port at `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/engine/` and `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/sources/` (with `_resilient.py`); the code to DROP at `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/{agent.py,code_guard.py,dynamic_skills.py,feature_builder.py}` and `app/skills_generated/`; the existing reusable TS workspace libs at `/Users/joshuajerin/Desktop/jarvis/doomberg/lib/{db,api-zod,api-client-react}`; and the review whose lessons gate this design at `/Users/joshuajerin/Desktop/jarvis/doomberg/docs/reviews/architecture-review-2026-06-16.md`.