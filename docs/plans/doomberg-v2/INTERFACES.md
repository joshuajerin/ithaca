# Doomberg v2 — Service Interfaces (the seams parallel builders MUST conform to)

This pins the contracts between layers so independently-built services integrate. Shapes for
data are in `packages/contracts` (pydantic `doomberg_contracts` / zod `@doomberg/contracts`).
Everything is Python except the web UI.

## Shared core — `doomberg_core` (BUILT, do not change its API)

```python
from doomberg_core import Core, CoreContext, DataGateway
core = Core()                       # real Yahoo gateway; inject DataGateway(fetch_history=...) in tests
core.run_tool(name, args, ctx)      # name in {"market.get_ohlcv","backtest.run"}; returns a provenance envelope dict
core.backtest_run({"spec": <StrategySpec dict>, "range": "1y", "as_of": None})
core.validate_spec(spec) -> dict    # raises pydantic ValidationError on closed-schema violation; clears server-stamped id/version/tenant_id
```
Backtest result `data` shape: `{equityCurve:[{d,v}], stats:{sharpe,cagr,...}, finalWeights:{sym:w}, risk:{ok,gross,net,maxName,violations}, relaxed:bool, bars, symbols}`.
Provenance envelope: `{data, provenance:{source,as_of,freshness,pit,coverage,cost,cache_hit}, partial, warnings}`.

## `doomberg_platform` (Phase A — build FIRST, others depend on it)

Local system-of-record. SQLite-backed, but behind interfaces so Postgres swaps in later. **tenant_id is a hard column on every row** (isolation invariant — never expose an unscoped query).

```python
from doomberg_platform import TraceStore, RunStore, StrategyStore, open_db

# TraceStore — append-only, gap-free seq per run_id (single writer per run)
ts.append(event: dict) -> int                       # validates against TraceEvent contract; returns seq
ts.events(tenant_id, run_id, after_seq=-1) -> list[dict]
ts.subscribe(run_id) -> Iterator[dict]              # live tail for SSE (in-proc pub/sub ok locally)

# RunStore — the run state machine row
# states: draft -> queued -> running -> (succeeded|failed|timeout) ; paper: promoted -> live -> paused -> retired
rs.create(tenant_id, kind, strategy_id, spec) -> run_id
rs.get(tenant_id, run_id) -> dict | None
rs.transition(tenant_id, run_id, to_state, *, expect=None) -> dict   # optimistic version guard
rs.list(tenant_id, kind=None) -> list[dict]
rs.set_result(tenant_id, run_id, result: dict) -> None

# StrategyStore — immutable versioned specs
ss.create(tenant_id, spec) -> {id, version}
ss.get(tenant_id, strategy_id) -> dict | None
ss.list(tenant_id) -> list[dict]
```
Every read/write takes `tenant_id` first and filters by it. `open_db(path|":memory:")` returns a handle the stores share.

## `doomberg_control` (control-plane, FastAPI) — SINGLE writer of the money path

Endpoints (all require an `X-Tenant-Id` header in local dev → ctx):
- `POST /strategies` (propose) → validate via `core.validate_spec`, persist draft via StrategyStore, emit `strategy_proposed`.
- `POST /runs` `{strategy_id, kind:"backtest"|"paper", range}` → create run (queued), enqueue; returns run_id.
- `POST /runs/{id}/promote` → human action; runs the compliance/risk gate; paper runs only. Agent may NOT call promote.
- `GET /runs/{id}` / `GET /runs` → RunStore reads.
The control plane is the ONLY writer that applies a book delta (worker proposes; CP applies under a lock).

## `doomberg_runtime` (workers)

```python
from doomberg_runtime import run_backtest_job, run_paper_tick
run_backtest_job(tenant_id, run_id, *, platform, core)   # pulls run, runs core backtest with an aggregate deadline, streams run_progress + sets result + transitions
run_paper_tick(tenant_id, run_id, *, platform, core)     # one stateless tick on real current data; PROPOSES a delta (CP applies); emits mark/fill
```
Out-of-process by design; deny-all egress in prod. Aggregate wall-clock deadline per job (not just per-call).

## `doomberg_rest` (rest-gateway, FastAPI + SSE) — the web UI's only backend

- `GET /api/runs`, `GET /api/runs/{id}`, `GET /api/strategies` → tenant-scoped reads from platform.
- `GET /api/runs/{id}/events` → **SSE**, `Last-Event-ID` carries `seq` for replay-from-seq, then live tail; emit `: keepalive` heartbeats.
- The browser NEVER speaks MCP. CP write actions are proxied here for the UI's accept/promote buttons.

## web (`web/`, React+Vite+TS)

Observability surface, **no chat**. Views: Runs (three-column trace: reasoning rail · tool-call timeline · evidence panels) · Deploys (Backtests/Paper) · Trades · Ideas. Consume `doomberg_rest` REST+SSE only. A `panelType` on a tool result keys a static renderer (no client-side eval). Reuse v1 panels from `history/v1/artifacts/terminal/src/components/terminal/panels` as display-only renderers where helpful.

## Conventions
- Never `except: pass` on an audited path; emit a `denial`/`error` trace event instead.
- Aggregate wall-clock deadline at every entry; per-call timeout = min(default, remaining).
- `tenant_id`, `run_id`, `session_id` are UUID strings (the TraceEvent contract enforces it).
- Each service: tests pass via `uv run --extra dev pytest` in its dir. Do not edit root `pyproject.toml` or `pnpm-workspace.yaml` (already wired).
