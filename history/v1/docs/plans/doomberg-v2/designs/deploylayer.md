# Design: Deploy Layer & Control Plane (DigitalOcean)

I have everything I need. Returning the design doc.

---

# Doomberg v2 — Deploy Layer Design

**Scope:** the control plane + runtime that runs backtests and paper-live strategies on DigitalOcean CPU clusters. Greenfield. Built so an external (BYO) agent can deploy a strategy and the web UI can observe it.

**North star from v1's review:** every architecture decision below is chosen to *not* repeat the five cross-cutting failures — static-guard-then-trust, silent swallowing, per-store (not invariant) tenancy, unlocked read-modify-write on the money path, and per-call-but-not-aggregate timeouts. These map to concrete invariants, not aspirations.

---

## 0. The load-bearing decision: declarative spec, not arbitrary code

**A deployed strategy is a declarative `StrategySpec` (a signal graph over a fixed library of operators), never arbitrary user/agent code.** This is the single most important call in the whole layer and it directly kills v1's two critical RCEs at the root.

Why declarative wins here:

1. **v1 already proved the dangerous path is unsafe.** `code_guard.py` is an AST allow-list that the review showed is trivially bypassed (`string.Formatter().get_field("0.__globals__[...]")` reaches a live `__import__`), and worse, the *validation* subprocess didn't even cover the in-process `exec_module`/`build()` that actually ran. "Static guard then trust" produced five findings from one decision. We do not get a second chance to relitigate this.
2. **v1's quant value is already declarative-shaped.** `engine/strategies.py` strategies are `(closes, params) -> target_position_array` pure functions. `engine/backtest.py`, `paperbook.py`, `execution.py` are pure numpy, no I/O. The proven edge isn't in users writing Python — it's in *composing these primitives*. A spec captures 95% of real strategies (MA crossover, momentum, mean-reversion, cross-sectional factor ranks, multi-asset rebalancing) with zero code execution.
3. **The agent is external and untrusted by definition.** BYO-agent means the thing emitting strategies is outside our trust boundary. A declarative spec is *data we validate*, not *code we run*. We can diff it, version it, render it in the UI, reproduce it, and reason about it. Arbitrary code is none of those.

### What a `StrategySpec` is

A versioned, JSON/YAML document — a **signal graph**: nodes are typed operators drawn from a **fixed, server-owned operator registry**; edges pass numpy arrays (or small structured frames). The agent emits this; we validate it against a schema + a semantic linter before anything runs.

```jsonc
{
  "specVersion": "1.0",
  "id": "strat_01J...",            // server-assigned, never client-trusted
  "firmId": "...",                  // stamped from auth, never from payload
  "name": "dual-momentum-tech",
  "universe": { "symbols": ["AAPL","MSFT","NVDA"], "source": "prices" },
  "graph": {
    "nodes": [
      { "id": "px",  "op": "load_closes", "args": { "lookbackBars": 252 } },
      { "id": "mom", "op": "momentum",    "in": ["px"], "args": { "lookback": 90 } },
      { "id": "rank","op": "cross_sectional_rank", "in": ["mom"], "args": { "top": 2 } },
      { "id": "tgt", "op": "to_weights",  "in": ["rank"], "args": { "gross": 1.0, "longOnly": true } }
    ],
    "output": "tgt"
  },
  "risk": { "maxGross": 1.0, "maxNet": 1.0, "maxNamePct": 0.25 },
  "execution": { "costBps": 5, "algo": "vwap", "rebalance": "daily@close" },
  "resources": { "tier": "standard" }
}
```

**The operator registry is the entire trust surface.** Each `op` maps to a vetted pure function (most already exist in `engine/`). Adding an operator is a code review + a new server release — not a runtime event. There is no `op: "eval"`, no free-text expression node, no lambda. If a strategy genuinely needs logic the registry can't express, that's a feature request to add a *reviewed* operator, not a hole to punch.

**Escape hatch, deliberately deferred and isolated:** a `CustomPythonNode` (a single pure `(inputs, params) -> array` function) *can* exist later, but only ever runs inside the Worker sandbox (Section 1) with stripped builtins, no network, rlimited — and it is **off by default, firm-gated, and never on the control-plane path**. We design the seam; we don't ship it at launch. The v1 lesson is explicit: "sandboxed self-built skills as a real product — *only after* out-of-process exec." Same rule here.

### Spec validation (the gate, run before any provisioning)
- **Schema validation** (Pydantic v2): types, required fields, value ranges.
- **Semantic lint:** graph is a DAG (no cycles), every `in` references an existing node, every `op` is in the registry, the output node produces weights, declared `risk` limits are internally consistent (`maxNet <= maxGross`).
- **Risk pre-attestation:** reject specs whose static config can't satisfy limits (e.g. `top: 2, longOnly, gross 1.0` with `maxNamePct 0.25` is infeasible — 2 names can't fill 100% gross under a 25% cap). This is the *design-time* analogue of v1's optimizer gross-exposure bug, caught before a worker ever runs.
- `firmId` and `id` are **always server-stamped**, never read from the payload (kills the v1 IDOR class at the door).

---

## 1. Safe execution model (out-of-process, sandboxed, rlimited, egress-controlled)

Even though specs are declarative, we **still execute everything out-of-process** with full isolation — defense in depth, and the mandatory home for the future `CustomPythonNode`. The runtime never runs in the control-plane process. Ever. (v1's fatal mistake was running generated work in the API process.)

**Worker process model (per job):**
- **Separate OS process**, one job at a time, spawned fresh, killed at completion. No long-lived interpreter accumulating state across tenants.
- **Linux namespaces + cgroups v2** (we run our own container image; see DO topology in §4). Each job container gets: `cpu.max` quota, `memory.max` hard cap (OOM-kill, not swap-thrash), `pids.max`, ephemeral writable `/tmp` only, read-only root FS.
- **Network egress: deny-by-default.** Worker containers have **no outbound internet**. The only thing they can reach is the **Data Gateway** (Section 2.0) over a private VPC address on one port. They cannot reach Yahoo/EDGAR/FRED directly, cannot reach the control-plane DB, cannot exfiltrate. This is the structural fix for v1's "egress was wherever a source adapter decided to make an HTTP call." Egress is now an *invariant enforced by the network*, not by code review of each adapter.
- **Stripped interpreter for any code node:** `__builtins__` reduced to a safe map, no `open`/`__import__`/`eval`, `RLIMIT_AS`/`RLIMIT_CPU`/`RLIMIT_NOFILE` set before exec, `seccomp` profile blocking `socket`/`ptrace`/`exec*`.
- **Aggregate wall-clock deadline per job** (not just per-call). v1 had per-call timeouts that summed past the proxy ceiling; here the supervisor sets a hard job deadline at spawn and SIGKILLs on breach, recording `status=timeout` with the partial artifacts. This is the IEX-13GB-stream lesson generalized.
- **Determinism contract:** seed is part of the spec/job; the engine is pure numpy; same spec + same point-in-time data window ⇒ identical artifact hash. This makes "Reproduce this run" (a v1 roadmap ask) free.

**Failure handling is explicit, never swallowed.** Every worker terminal state is one of `succeeded | failed | timeout | oom | killed | data_unavailable`, with a reason string and structured logs shipped to the control plane. No bare `except: pass`. A data gap surfaces as `data_unavailable` with coverage info — never a silently fabricated curve (v1's `paperbook.py` already refuses synthetic curves; we keep that contract end-to-end).

---

## 2. The two runtimes (shared core)

### 2.0 Shared execution core — `runtime-core`
A single Python package, imported by both runtimes, containing:
- The **operator registry** (ports of `engine/strategies.py`, plus `cross_sectional_rank`, `to_weights`, factor ops from v1's `factor_model.py`).
- The **graph evaluator** — topologically evaluates the DAG, calling pure operator fns.
- The **portfolio/accounting kernel** — ports `engine/execution.py` (`generate_orders`, VWAP/TWAP/POV fills, TCA) and `engine/paperbook.py` (`position_marks`, `book_value`, `nav_curve`).
- The **risk attestation** — post-projection re-check of `sum|w|` vs gross *after* the final budget step (the exact v1 optimizer bug: `_project_feasible` ended on net+box, not gross L1, and returned 311%-gross books as "optimal"). Here the core refuses to emit any target book that breaches declared limits; it returns `infeasible-relaxed` with the violation.
- The **Data Gateway client** — the *only* way a worker gets data (see below).

Backtest and paper-live differ only in their **clock** and their **data window source**. Same evaluator, same accounting, same risk gate. One codebase, two drivers.

### 2.0.1 Data Gateway (point-in-time correctness lives here)
A control-plane-side service (reachable only from worker VPC) that wraps v1's `sources/` adapters behind one authenticated RPC. Critically it takes an **`asOf` parameter** on every call and **returns only data that was knowable at `asOf`** — no row with `publishedAt > asOf`, prices truncated at the `asOf` bar. This makes point-in-time correctness a **property of the data plane**, not something each operator must remember (v1's review flagged misaligned forward-return windows and look-ahead in `engine/signals.py` — we remove the operator's ability to cheat by never handing it future data).

The gateway also: enforces tenant scoping on cached data, applies the resilient breaker/retry (v1's `_resilient.request`, routing the Treasury/FRED fetches that v1 left un-wrapped), and returns a `{source, asOf, freshnessSec, mode, coverage}` provenance block on every response — surfaced straight to the UI (the v1 "data lineage" roadmap item, now built in).

### 2.1 Backtest runtime
- **Clock:** simulated, iterates historical bars from a fixed `[start, end]`.
- **Data:** one bulk point-in-time pull from the Data Gateway at job start (the window the spec needs). Backtest then "replays" bar-by-bar, each step seeing only `data[:i+1]` — structurally no lookahead. v1's `run_backtest` already encodes `held[1:] = target[:-1]`; we keep that and additionally enforce it at the data layer.
- **Mode:** CPU-bound burst. Spawn, run to completion (seconds to a few minutes), emit artifacts, die.
- **Output artifact:** equity curve, drawdown, trade log, full stat block (port `engine/stats.py`), plus **always** the walk-forward / overfitting diagnostics from v1's `run_walk_forward` (deflated Sharpe, PBO/CSCV, OOS degradation, honest `coverage.usable=false` when history is too short). Overfitting honesty ships by default, not as a toggle.

### 2.2 Paper-live runtime
- **Clock:** real wall-clock, driven by the control-plane scheduler on the spec's `rebalance` cadence (e.g. `daily@close`).
- **Data:** real, current market data via the Data Gateway (no `asOf` truncation — `asOf = now`).
- **Fills:** against a **simulated/paper book** (port `engine/paperbook.py` + `execution.py`). Live REAL prices, fills against the paper book — exactly the launch scope. The paper book is the durable, marked-to-market state; `nav_curve` reconstructs P&L from real closes since inception (never synthetic).
- **Mode:** **stateless tick worker, not a long-running daemon.** Each scheduled rebalance is a *short job*: the scheduler wakes it, it loads the current book from the control plane (under a lock — see §3), pulls data, evaluates the graph, computes target weights, generates paper orders, applies fills, **atomically persists the new book**, emits a trade/observation event, and exits. Between ticks nothing runs. This is deliberate: long-lived worker processes were where v1 accumulated unscoped global state. A stateless tick model means a crash loses one tick, not the book.
- **Promotion provenance:** when a backtested spec is promoted to paper, the inception, capital, seed, and the backtest artifact hash are stamped on the paper book for audit replay.

---

## 3. Control plane

A stateless API/orchestrator (FastAPI) over Postgres. It **never executes strategy logic**; it only validates specs, schedules jobs, persists state, stores artifacts, and streams observability to the UI and to the agent (via MCP/SSE).

### Core entities (Postgres, every table carries `firm_id`, indexed, filtered in *every* query)
- `strategy_spec` — immutable versioned specs (new version = new row; specs never mutated in place → reproducibility + clean diffs for the UI).
- `deployment` — a spec bound to a runtime + lifecycle stage + paper book.
- `job` — one execution (backtest run or one paper-live tick); status, deadline, resource tier, worker id, reason.
- `paper_book` — positions + cash + capital + inception; the money-path row.
- `artifact` — pointers to Spaces (DO object storage): curves, trade logs, stat blocks, logs.
- `event` — append-only observation stream (tool/graph-node activity, trades, ideas) for the UI trace and the agent.

### Tenant isolation as an invariant (not per-call-site)
v1's #3 failure: tenancy was correct in some stores, absent in others (`template_store`, in-memory `get_dashboard`). Fix: **a single repository layer where `firm_id` is a mandatory, non-optional argument on every read and write**, enforced by:
- Postgres **Row-Level Security** policies keyed on a session GUC (`app.firm_id`) — the DB rejects cross-firm rows even if application code forgets a `WHERE`. Defense in depth: even a bug can't leak.
- A repo base class that *requires* `firm_id`; no in-memory fallback store with different scoping rules (v1's IDOR came from a `_mem` path that ignored scoping when `DATABASE_URL` was unset). There is one path: Postgres.
- The Data Gateway also scopes cached data by firm.

### Money-path concurrency (no unlocked read-modify-write)
v1's #4 failure: strategy books updated via unlocked `INSERT ... ON CONFLICT` over a stale read; the worker advisory lock guarded worker-vs-worker but not worker-vs-API. Fix: **every `paper_book` mutation is `SELECT ... FOR UPDATE` inside one transaction**, plus an **optimistic `version` column** as a backstop. Since paper-live is a single-tick-at-a-time model per deployment, we also take a per-deployment advisory lock so two ticks can't overlap. The mutation path is one function; there is no second writer.

### Lifecycle (explicit state machine, classify-before-act)
`draft → validated → backtesting → backtested → paper_pending → paper_live → paused → retired`, with `promote` (backtested→paper) and `pause`/`resume` as guarded transitions. Each transition: validates the source state, writes an audit `event`, is idempotent. v1 had lifecycle keyword-routing fire *before* intent classification, mutating state on a *question* ("how do I retire a strategy?"). Here lifecycle is an explicit API/MCP action with a typed verb — never inferred from free text. The agent calls `promote(deployment_id)`; there's no NL parsing on the mutation path.

### Scheduling & deadlines
- Backtests → a **work queue** (Redis/RQ or DO-managed Postgres-backed queue) consumed by autoscaled backtest workers.
- Paper-live ticks → a **scheduler** (cron-like, market-calendar-aware) that enqueues a tick job per live deployment at its cadence.
- Every job carries an **aggregate wall-clock deadline** set at enqueue; the worker supervisor enforces it (the v1 "per-call but no aggregate budget" fix). Jobs past deadline are SIGKILLed and recorded `timeout`.
- **Heartbeats:** workers heartbeat to the control plane; a missed heartbeat past threshold marks the job `lost` and (for backtests) re-queues once, (for paper-live) skips the tick and alerts — never silently hangs.

### Observability (the product, not an afterthought)
The UI is an *observation surface*. The control plane streams the `event` table over SSE: graph-node evaluations, the agent's tool calls/args/results (captured because the agent talks to us via MCP), generated target books, paper fills, and the data-provenance badges. Every artifact is reproducible (spec hash + data `asOf` set + seed). Logs/metrics: structured JSON logs to Spaces + a `/health` panel exposing Data Gateway breaker state, queue depth, worker pool saturation, and tick lag — the v1 "SLA/health panel" roadmap item.

### CI that actually gates
v1 ran 3 of 33 suites and had no workflow. Non-negotiable here: a GitHub Actions `required` check runs the full `pytest` suite, the spec-validator property tests, a **golden backtest determinism test** (same spec ⇒ same artifact hash), a **lookahead-detection test** (a spec that tries to peek forward must produce identical results whether or not future bars exist in the store), and a **tenant-isolation test** (firm A cannot read firm B's book/spec/artifact). No merge without green.

---

## 4. DigitalOcean topology (opinionated)

**Choice: DOKS (DigitalOcean Kubernetes) with two node pools + Spaces + Managed Postgres + a VPC. Not App Platform, not raw Droplets.**

Justification against the workload's two distinct shapes:

| Need | Backtests (bursty, CPU-bound, short) | Paper-live (scheduled, short ticks, long-lived *service*) |
|---|---|---|
| Scaling | Scale-to-burst then scale-to-zero | Steady, market-hours-aware |
| Isolation | Strong per-job sandbox + egress control | Same |
| Failure recovery | Re-queue | Skip-and-alert |

- **App Platform rejected:** it's great for stateless web apps but gives us no cgroup/seccomp/network-policy control over *job* containers and no clean scale-to-zero burst model for queued CPU jobs. The sandbox requirements alone disqualify it.
- **Raw Droplets + autoscale rejected as the *primary*:** doable, but we'd hand-roll scheduling, bin-packing, health, and per-job container isolation — reinventing Kubernetes badly. We'd lose the declarative NetworkPolicy that makes egress-deny an *invariant*.
- **DOKS chosen** because it gives us, off the shelf: per-pod resource limits (cgroups), `NetworkPolicy` (the deny-all-egress-except-Data-Gateway invariant — *enforced by the cluster, not by code*), Jobs API for run-to-completion backtests, CronJobs/our scheduler for ticks, and the cluster-autoscaler for burst.

**Concrete topology:**
- **VPC** containing the cluster, Managed Postgres, and the Data Gateway. Workers have **no public egress** (NetworkPolicy default-deny; one allow rule to the Data Gateway service ClusterIP). This is the structural egress control §1 requires.
- **Node pool `backtest`** — CPU-optimized droplets, **autoscaling min 0 → max N**, cluster-autoscaler-backed. Backtests run as Kubernetes **Jobs** (one pod per job, `restartPolicy: Never`, resource `requests`/`limits` from the spec's `resources.tier`, activeDeadlineSeconds = aggregate deadline). Scale-to-zero between bursts = cost control: you pay for backtest compute only while backtests run.
- **Node pool `paper`** — small, stable general-purpose pool for the scheduler + tick jobs. Tick jobs are short Kubernetes Jobs fired by the control-plane scheduler (market-calendar-aware; we run our own scheduler rather than naive CronJobs so we respect holidays/half-days and can pause a single deployment).
- **Control plane** — runs as a regular Deployment (web API + scheduler + Data Gateway), HPA on CPU, fronted by a DO Load Balancer.
- **State:** Managed Postgres (control-plane state, books, events — with RLS), DO Spaces (artifacts, logs), optional managed Redis for the work queue.
- **Cost control:** scale-to-zero backtest pool; per-tier resource caps; aggregate deadlines bound runaway compute; backtest results cached by `(spec_hash, data_asOf_window)` so re-running an identical backtest is a cache hit, not new compute. Budget alarms on node-pool size.
- **Failure recovery:** Jobs API restarts/re-queues failed backtests once; lost paper ticks are skipped-and-alerted (never double-filled — the advisory lock + version guard prevent a re-run from corrupting the book); node failure → pods rescheduled by K8s; control-plane stateless so it restarts cleanly.

---

## 5. Brokerage-adapter seam (interface only — do NOT build)

Launch is paper-only. But the fill path is isolated behind one interface so real execution is a *plugin*, not a rewrite. The paper engine is just the first implementation.

```python
class ExecutionVenue(Protocol):
    """The only seam between the runtime and where orders go.
    Paper book = first impl. A real broker = a future impl. Nothing else changes."""

    def quote(self, symbols: list[str], as_of: str) -> dict[str, Quote]: ...

    def place_orders(self, orders: list[Order], *, idempotency_key: str) -> list[Fill]:
        """MUST be idempotent on idempotency_key (retried ticks must not double-fill)."""

    def positions(self) -> list[Position]: ...
    def cash(self) -> float: ...
    def venue_caps(self) -> VenueCaps:  # supports_short, supports_fractional, min_notional...
        ...
```

- The runtime computes target weights → `generate_orders` (already venue-agnostic in v1) → hands `Order`s to the configured `ExecutionVenue`. Today that's `PaperVenue` (wraps `paperbook`/`execution`). A future `AlpacaVenue`/`IBKRVenue` implements the same Protocol.
- **`idempotency_key`** is mandatory in the interface *now* even though the paper venue is forgiving — because real venues aren't, and our retry/re-queue model means the same logical tick can fire twice. Designing it in at launch is the cheap insurance the v1 review's "lost-update on the money path" lesson demands.
- `venue_caps()` lets the risk attestation reject specs a venue can't honor (e.g. shorting on a long-only venue) at deploy time.

We define the Protocol, the `PaperVenue` impl, and the wiring. We build no real adapter.

---

## 6. Greenfield repo / module structure + stack

**Stack:** Python 3.12, **FastAPI** (control plane + Data Gateway), **Pydantic v2** (spec schema = the security boundary), **Postgres + RLS** (SQLAlchemy core, no fallback in-memory store), **DO Spaces** (artifacts), **Kubernetes Python/Jobs API** for orchestration, **NumPy** runtime core (ported from v1), **Redis/RQ** for the backtest queue. **MCP server (primary agent interface) + thin REST/SSE** sharing the same control-plane services. Why Python end-to-end: v1's proven quant value (`engine/`, `sources/`) is numpy/Python; rewriting it in Go/Rust would re-introduce risk for no isolation benefit (isolation comes from the OS/K8s layer, not the language).

```
doomberg-deploy/
  control_plane/
    api/              # FastAPI REST/SSE — UI-facing, thin
    mcp/              # MCP server — PRIMARY agent interface (deploy/promote/observe tools)
    scheduler/        # market-calendar-aware tick scheduler + backtest enqueuer
    orchestrator/     # K8s Jobs driver: spawn/monitor/deadline/heartbeat
    repo/             # SINGLE data-access layer; firm_id mandatory; RLS-backed
    lifecycle/        # explicit state machine (classify-before-act, audited)
    spec/             # Pydantic StrategySpec schema + semantic linter + risk pre-attest
    events/           # append-only observation stream → SSE/MCP
  data_gateway/       # the ONLY data egress; asOf point-in-time enforcement; provenance; resilient breaker
    adapters/         # ported v1 sources/ (prices, edgar, news, rates, ...), all behind _resilient
  runtime_core/       # SHARED, pure, no-I/O, sandbox-safe
    registry/         # operator registry == the trust surface (ported engine/strategies + factor ops)
    graph/            # DAG evaluator
    accounting/       # paperbook + execution + TCA  (ported engine/)
    stats/            # stat block + walk-forward/overfitting diagnostics (ported engine/)
    risk/             # post-projection gross/net/name attestation (fixes v1 optimizer bug)
  runtimes/
    backtest/         # simulated-clock driver over a point-in-time window
    paper_live/       # wall-clock tick driver, fills via ExecutionVenue
  venues/
    base.py           # ExecutionVenue Protocol  (the future-broker seam)
    paper.py          # PaperVenue (launch impl)
  worker/             # the sandboxed entrypoint run inside each K8s Job pod
    sandbox/          # rlimits, stripped builtins, seccomp, deadline supervisor
  deploy/             # DOKS manifests: node pools, NetworkPolicy (deny-egress), Jobs/CronJobs, RLS migrations
  tests/              # gating CI: determinism, lookahead, tenant-isolation, risk-attestation, spec-fuzz
```

**Trust-boundary summary (one line):** the agent emits *data* (a spec) → control plane *validates* it → workers *execute reviewed operators* out-of-process, network-egress-denied, rlimited, deadline-bounded → all data flows through one point-in-time, provenance-stamped gateway → all state mutations go through one firm-scoped, row-locked repository. Every one of v1's five cross-cutting failures is closed by an *invariant enforced by infrastructure* (RLS, NetworkPolicy, FOR UPDATE, K8s deadlines, fixed operator registry), not by a guard we have to remember to call.

**Relevant source paths reviewed:** `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/engine/{backtest,paperbook,execution,strategies,stats}.py` (reusable pure core), `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/sources/{prices,_resilient}.py` (data adapters to wrap behind the Data Gateway), `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/code_guard.py` (the bypassable guard we are explicitly *not* relying on), and `/Users/joshuajerin/Desktop/jarvis/doomberg/docs/reviews/architecture-review-2026-06-16.md` (the five lessons driving the invariants above).