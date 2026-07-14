# Agent-Native Control Plane Implementation Plan

Status: Proposed

## Goal

Implement the Ithaca plan as an agent-native trading control plane, not as a bigger synchronous MCP tool bundle. The target boundary is:

> MCP creates, observes, and controls durable Ithaca runs. Ithaca owns data entitlements, compute, triggers, policy, execution, artifacts, and traceability.

This plan intentionally starts from the current repo rather than replacing it wholesale. The repo already has useful pieces: a typed contract package, MCP and REST gateways, a control-plane service, a runtime worker loop, trace storage, a paper-only money path, a React session UI, deployment manifests, and archive-backed financial skills. The implementation should harden those pieces into a durable platform.

## Current-State Findings

### What Already Aligns

- `README.md` frames v2 as a financial tool-platform for external agents, with `packages/contracts`, `ithaca-core`, `services/mcp-gateway`, `services/rest-gateway`, `services/control-plane`, `services/runtime`, `web`, and `infra`.
- `packages/contracts/schema/provenance.schema.json` already defines a real provenance envelope with `source`, `as_of`, `freshness`, `pit`, coverage, warnings, and cost fields.
- `packages/contracts/schema/strategy_spec.schema.json` keeps strategy specs declarative and closed to arbitrary agent-authored code.
- `services/control-plane/src/ithaca_control/actions.py` is already the single transport-agnostic write path for strategies and paper deployment actions.
- `services/runtime/src/ithaca_runtime/orchestrator.py` and `backtest_runner.py` already poll persisted runs and execute backtests outside request/response paths.
- `services/platform/src/ithaca_platform/trace_store.py` already stores append-only run events and streams them through REST/SSE.
- `services/control-plane/src/ithaca_control/money.py` keeps broker-like writes paper-only and behind risk rechecks.
- `infra/k8s/worker-networkpolicy.yaml` already starts separating worker egress from app services.

### Gaps Against The Target

- MCP still exposes a large top-level tool catalog. `services/mcp-gateway/src/ithaca_mcp/server.py` runs `market_get_ohlcv`, `backtest_run`, `propose_strategy`, and archive skills inline, while many skills are advertised as separate MCP tools. This conflicts with the target small progressive-discovery surface.
- Durable runs exist through REST/control-plane, but not as the primary MCP behavior. MCP calls do not generally return `{run_id, status, status_url, estimated_profile}`.
- Platform state is SQLite with an in-process pub/sub. `services/platform/src/ithaca_platform/db.py` lacks provider connections, dataset snapshots, entitlements, jobs, leases, run attempts, spans, artifacts, triggers, approvals, order intents, orders, fills, costs, and provider health tables.
- Queueing is not yet production-grade. `RunStore.claim_queued` is effectively optimistic state transition without leases, visibility timeouts, heartbeat recovery, checkpoint awareness, or cancellation.
- The data layer is not entitlement-aware. `ithaca-core/src/ithaca_core/gateway/data_gateway.py` and archive skills do not route by tenant/provider entitlement. Several skill implementations call public/live APIs directly instead of centralizing through the gateway.
- Provenance envelopes diverge. `DataGateway` mostly follows the contract, but `ithaca-core/src/ithaca_core/skills/envelope.py` emits a lighter shape that omits required contract fields.
- The dashboard is still sample-driven. `web/src/pages/Dashboard.tsx` builds local panels from prompt presets and stamps them with `source: "sample"`.
- Session UI exists but does not yet make provider provenance, artifacts, approvals, order intents, costs, or replay bundles first-class.
- Execution remains paper-only and lacks first-class `order_intent`, `approval`, `order`, `fill`, and reconciliation state machines.
- The deployment currently co-locates app services to share a SQLite PVC. `infra/k8s/pvc.yaml` explicitly notes this is durable but not HA.
- Worker profiles are not truly jobized yet. The Terraform job templates are reference-only and disabled, while runtime execution is still a daemon conductor polling SQLite.
- Deployment has two public ingress/LB shapes: Terraform-created DigitalOcean Load Balancer plus optional Caddy `LoadBalancer` service. Ownership should be consolidated before production hardening.
- CI can look green while missing important surfaces: `site`, real worker job entrypoints, HA/Postgres topology, and some lint/security checks are not fully covered.
- There are stale parallel deploy/onboarding surfaces from earlier Vercel/Hermes/Supabase-era hosting that should be retired or clearly marked legacy.
- Production security footguns remain: wildcard CORS, dev tenant fallback behavior, and SSE access tokens in query strings need tightening before the platform is treated as a control plane.

## Target Architecture In This Repo

The target should evolve the current package layout into these bounded responsibilities:

```text
Agent / MCP client
  -> services/mcp-gateway
  -> services/control-plane / services/orchestrator
  -> platform job queue and event store
  -> workers
  -> data gateway and provider adapters
  -> policy / approval service
  -> execution gateway
  -> broker adapters
  -> sessions, terminal, audit UI
```

The existing services can be extended before directories are split:

- `services/mcp-gateway`: thin discovery, run creation, run observation, approvals, artifacts, and compatibility wrappers.
- `services/control-plane`: authoritative state transitions, admission control, policy checks, approvals, strategy lifecycle, and execution-intent lifecycle.
- `services/runtime`: durable worker leases, job execution, checkpoints, artifacts, cancellation, retries, and profile enforcement.
- `ithaca-core`: pure financial primitives, canonical data contracts, strategy validation, risk math, and no broker writes.
- live-data provider layer: connected-account providers, entitlement routing, dataset snapshots, and normalized payloads.
- `web`: live control-plane dashboard, sessions trace UI, provider/entitlement UI, trigger UI, approval/execution UI, artifacts and replay.
- `infra`: Managed Postgres platform state, Spaces artifacts, split services, worker pools, secrets boundaries, and autoscaling.

## Implementation Phases

### Phase 1: Contract And State Foundation

Purpose: make the platform able to represent the target before changing user behavior.

Edits:

- Add contract schemas for:
  - `skill_manifest`
  - `run`, `run_attempt`, `job`, `worker_lease`
  - `span`, `artifact`
  - `provider_connection`, `dataset`, `dataset_snapshot`, `entitlement`
  - `trigger_policy`, `trigger_event`
  - `approval`
  - `order_intent`, `order`, `fill`, `position_snapshot`
  - typed platform errors
- Update generated TS/Python contracts and drift checks.
- Align `ithaca-core/src/ithaca_core/skills/envelope.py` with `provenance.schema.json`.
- Add platform migrations/tables while preserving the existing SQLite implementation for local dev.
- Introduce a store interface that can support Postgres as production state and SQLite as local/dev fallback.

Acceptance:

- Every skill result has the same envelope shape.
- Contracts compile in TypeScript and Python.
- Existing demos still pass.
- New unit tests validate provider entitlement rows, job rows, artifact rows, and typed error payloads.

### Phase 2: Thin MCP Facade

Purpose: move MCP from runtime surface to control-plane surface.

New primary MCP tools:

```text
search_skills(query, asset_class?, intent?)
describe_skill(skill_id, version?)
run_skill(skill_id, input, mode, idempotency_key?)
get_run(run_id)
subscribe_run(run_id, cursor?)
cancel_run(run_id)
list_approvals()
decide_approval(approval_id, decision)
get_artifact(artifact_id)
```

Resources:

```text
ithaca://skills/catalog
ithaca://skills/{skill_id}/{version}
ithaca://runs/{run_id}
ithaca://policies/current
ithaca://accounts
ithaca://data/providers
```

Implementation notes:

- `run_skill` should enqueue a durable run/job and return a run ID instead of executing long work inside the MCP handler.
- Keep the existing top-level skill tools temporarily as compatibility wrappers, but mark them deprecated in descriptions and route long work through `run_skill` where possible.
- Add MCP scope checks for run creation, cancellation, approvals, artifact access, and execution-related actions.
- Return typed errors such as `AUTH_REQUIRED`, `ENTITLEMENT_REQUIRED`, `DATA_STALE`, `PROVIDER_DEGRADED`, `RATE_LIMITED`, `MARKET_CLOSED`, `JOB_BUDGET_EXCEEDED`, `POLICY_DENIED`, `APPROVAL_REQUIRED`, `ORDER_STATE_CONFLICT`, and `DUPLICATE_IDEMPOTENCY_KEY`.

Acceptance:

- Killing the MCP client does not stop a queued/running job.
- A new MCP client can retrieve the same run by ID.
- Existing clients using old tools still work during the migration window.

### Phase 3: Durable Compute Plane

Purpose: make scans, backtests, and optimizations robust under disconnects, crashes, retries, and worker loss.

Edits:

- Add job profiles: `interactive`, `scan`, `backtest`, `optimization`, `stream`.
- Add persisted leases with owner, heartbeat, visibility timeout, attempt count, profile, resource limits, and cancellation state.
- Add explicit lifecycle:

```text
created -> admitted -> queued -> leased -> starting -> running -> checkpointing -> succeeded / failed / cancelled / timed_out
```

- Add checkpoint and artifact upload APIs.
- Store artifacts in Spaces in production and local filesystem in dev.
- Make workers honor cancellation and heartbeat their leases.
- Add idempotency keys for run/job creation.
- Add retry policies that never duplicate broker-facing side effects.

Acceptance:

- A worker killed mid-run either resumes from checkpoint or fails cleanly with complete audit state.
- Duplicate `run_skill` calls with the same idempotency key return the existing run.
- Long jobs produce artifact manifests rather than stuffing large outputs into trace events.

### Phase 4: Entitlement-Aware Data Gateway

Purpose: make every market-data result sourceable, fresh, legally permitted, and auditable.

Edits:

- Add provider connection and entitlement stores.
- Define canonical entities:

```text
Instrument
Listing
OptionContract
Quote
Trade
Bar
OptionQuote
OptionTrade
CorporateAction
NewsItem
Filing
FundamentalFact
MacroObservation
DatasetSnapshot
PortfolioSnapshot
Position
```

- Add dataset snapshot manifests and snapshot resolution for backtests.
- Centralize provider access behind adapter interfaces:

```text
capabilities()
entitlements(user)
quote(request)
bars(request)
chain(request)
news(request)
health()
usage()
normalize(response)
```

- Move direct yfinance/FMP/CoinGecko/Quiver calls behind the gateway or mark them internal/dev-only.
- Add request coalescing, token buckets, retries, circuit breakers, stale-data checks, retention policy, and usage/cost accounting.
- Implement initial modes:
  - Community/public-delayed data with visible source/freshness.
  - Connected-account data for the first broker/provider.
  - A placeholder adapter interface for future Ithaca-licensed data.

Acceptance:

- No user-visible or agent-visible market value lacks source, timestamp, freshness, entitlement class, and snapshot/provider ID.
- Backtests resolve dataset snapshots before computing.
- Provider degradation produces typed recoverable errors.

### Phase 5: Triggers

Purpose: make proactive monitoring a core platform primitive rather than a scheduled prompt.

Edits:

- Add typed trigger AST, trigger policy store, trigger event store, and trigger evaluation workers.
- Support market calendars, dedupe keys, debounce, cooldown, daily budgets, compute budgets, approval requirements, and dry-run history.
- Add trigger families:
  - Market
  - Options
  - News and filings
  - Portfolio and risk
  - Operational
- Emit full trigger-to-run trace linkage.

Acceptance:

- A user can create, dry-run, and activate a useful trigger without writing code.
- Trigger output starts with observe/analyze/propose/approve by default.
- Trigger runs can be inspected and replayed like manual runs.

### Phase 6: Risk-Gated Execution Gateway

Purpose: make agent-proposed execution deterministic, idempotent, and auditable.

Edits:

- Add `order_intent`, `approval`, `order`, `fill`, and reconciliation stores.
- Split paper execution and future live broker adapters behind one execution gateway.
- Require:
  - idempotency keys
  - broker `client_order_id` mapping
  - stale-data blocking
  - buying-power checks
  - max notional/position/loss limits
  - options permission checks
  - restricted-symbol rules
  - market-hours rules
  - approval expiry
  - organization, agent, strategy, account, and global kill switches
- Keep paper trading as the default. Live execution should remain disabled until legal/data/broker review is complete and explicit live scopes exist.

Acceptance:

- Retried execution requests cannot duplicate an order.
- Skills and agents cannot call broker adapters directly.
- Every execution step is visible in Sessions and the execution blotter.

### Phase 7: Sessions And Terminal UI

Purpose: turn traces into an operational control plane users can inspect and act from.

Edits:

- Replace `web/src/pages/Dashboard.tsx` sample panels with live platform data.
- Restore reachable run detail/lifecycle controls or merge them cleanly into the session detail route.
- Add first-class UI for:
  - live run trace DAG/timeline
  - selected span inspector
  - evidence and provenance
  - provider/source/freshness badges
  - artifacts and replay bundles
  - approvals
  - order intents, orders, fills, and reconciliation
  - triggers
  - provider status and entitlement state
  - costs and quotas
- Create a shared context bus for `symbol`, `expiry`, `time range`, `account`, `strategy`, `session`, `data source`, and `freshness`.
- Keep the renderer static and audited. Remove or quarantine runtime-generated TSX/Sucrase panel execution before treating the dashboard as production control-plane UI.

Acceptance:

- The first screen is a live operational dashboard, not a prompt-generated sample workspace.
- Selecting a session/run/span updates evidence, artifacts, policy, and execution panes coherently.
- Source/freshness is visible wherever market data appears.

### Phase 8: Deployment And Operations

Purpose: make production deployment match the trust boundaries.

Edits:

- Move production platform state from SQLite/PVC to Managed Postgres.
- Use Postgres notifications or a production event stream for cross-service events.
- Activate Spaces for artifacts, raw payloads, parquet, reports, checkpoints, and replay bundles.
- Split co-located services once they no longer need shared SQLite:
  - MCP gateway
  - REST gateway
  - control plane
  - orchestrator/trigger engine
  - data gateway
  - execution gateway
  - worker pools
- Maintain different credentials and network rules for control plane, data, compute, and execution.
- Keep local SQLite/dev mode for contributor speed.
- Replace reference-only worker job templates with runnable worker entrypoints before autoscaling or job-mode deployment is advertised.
- Choose one public ingress ownership model and remove duplicate LB/DNS/TLS paths.
- Remove or quarantine stale Vercel/Hermes/Supabase hosting files that conflict with the current DigitalOcean control-plane deployment.
- Tighten prod REST defaults: no anonymous tenant fallback, restrictive CORS, and no access tokens in SSE query strings.
- Add deployment smoke checks for durable run creation, event streaming, artifact retrieval, provider health, and unauthorized MCP behavior.

Acceptance:

- Scaling MCP or REST does not require shared disk.
- Workers receive only short-lived capability tokens.
- Production secrets are scoped by service responsibility.

## First Implementation Cut After Approval

The safest first code cut should be:

1. Add the missing contracts and platform tables behind compatible store interfaces.
2. Normalize skill envelopes to the formal provenance contract.
3. Add the new MCP progressive-discovery tools while keeping existing tools as compatibility wrappers.
4. Add durable job/lease/cancel/idempotency state for backtest runs.
5. Replace the dashboard sample data path with live sessions/runs/provider placeholders and explicit empty states.

This gives the platform the right boundary without prematurely adding broker live execution or pretending to solve market-data licensing.

## Verification Plan

Baseline verification:

```bash
uv sync --all-packages --extra dev
for pkg in packages/contracts/py ithaca-core services/platform services/mcp-gateway services/control-plane services/rest-gateway services/runtime; do
  (cd "$pkg" && PYTHONDONTWRITEBYTECODE=1 uv run --extra dev pytest -q -p no:cacheprovider)
done
pnpm run contracts:check
pnpm --filter @ithaca/contracts run test
pnpm --filter @ithaca/web run test
pnpm --filter @ithaca/web run build
pnpm --filter @ithaca/site run build
uv run python scripts/demo_e2e.py
uv run python scripts/demo_deploy.py
```

Infra verification:

```bash
(cd infra/terraform && terraform fmt -check -recursive && terraform init -backend=false -input=false && terraform validate -no-color)
docker build -t ithaca:control-plane-test .
rg -n "count = 0|python -m ithaca_runtime" infra/terraform/jobs.tf
rg -n "if __name__|def main" services/runtime/src/ithaca_runtime scripts/run_workers.py
```

New required tests:

- Contract drift tests for all new schemas.
- Envelope conformance tests for every skill group.
- MCP tests for `search_skills`, `describe_skill`, `run_skill`, `get_run`, `subscribe_run`, `cancel_run`, approvals, artifacts, and typed errors.
- Job lease tests for claim, heartbeat, timeout, retry, cancellation, and idempotency.
- Worker crash/resume tests using a forced mid-run failure.
- Provider entitlement tests for denied, delayed, stale, degraded, and connected-account paths.
- Trigger dry-run and cooldown tests.
- Execution gateway property tests proving duplicate submissions cannot create duplicate orders.
- Web tests for dashboard routing, session evidence rendering, source/freshness badges, provider status, triggers, approvals, and execution state.
- CI updates that include `site`, worker entrypoint smoke tests, and lint/security checks.

## Risks And Open Questions

- Market-data licensing and non-display use need legal review before any live customer-facing data claims.
- OPRA/options flow cannot be marketed as market-wide live flow until trade-level entitled data exists.
- Existing MCP clients may depend on the current top-level tool catalog, so compatibility wrappers need a deprecation period.
- SQLite-to-Postgres migration must preserve existing local developer workflow.
- Runtime-generated dashboard panels should be removed carefully because they may still support older demo flows.
- Live broker execution should not be implemented until paper idempotency, risk gates, approvals, and reconciliation are proven.
- The target 82-skill catalog should be implemented through manifests and grouped discovery, not as 82 new MCP top-level tools.
- Provider API rate limits and terms vary by account; runtime entitlement checks cannot assume provider marketing pages are current.
- DO topology should not be called production HA until app state is off SQLite/PVC, worker jobs are real, and ingress ownership is singular.

## Non-Goals For The First Cut

- No Bloomberg-equivalent real-time data promise.
- No shared retail market-data key for customers.
- No live autonomous trading.
- No arbitrary user code on shared workers.
- No custom distributed database.
- No chain-anomaly screen labeled as full options flow.
- No delayed FINRA aggregate screen labeled as live dark-pool tape.
