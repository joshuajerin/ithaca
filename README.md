# Doomberg v2

A financial **tool-platform** that external (bring-your-own) AI agents call over **MCP** to research
markets and run **backtests + paper-trading** on trusted infrastructure — with a web **observability
surface** that lets a human watch their agent think, work, and trade.

> v1 was a monolith that ran its *own* agent loop and compiled AI-authored code at runtime (the source of
> two critical RCEs). **v2 never runs the agent and never executes agent-authored code.** It exposes vetted
> tools, executes *declarative* strategy specs on trusted infra, and observes.

Full plan: [`docs/plans/doomberg-v2/MASTER-PLAN.md`](docs/plans/doomberg-v2/MASTER-PLAN.md).
Data sourcing strategy: [`docs/plans/doomberg-v2/DATA-SOURCING-STRATEGY.md`](docs/plans/doomberg-v2/DATA-SOURCING-STRATEGY.md).

## Layout

```
packages/contracts/   FROZEN source of truth — JSON Schema -> generated pydantic + zod (this is Phase 0)
doomberg-core/        the ONE shared Python core (engine/ sources/ registry/ graph/ accounting/ risk/ gateway/)
services/
  mcp-gateway/        primary product surface: MCP tools the agent calls
  rest-gateway/       feeds the web UI (REST + SSE) from the same core
  control-plane/      specs, run state machine, compliance gate — SINGLE writer of the money path
  runtime/            DO workers: backtest_runner + live_runner (import doomberg-core)
web/                  React/Vite observability UI (no chat console)
infra/                Terraform for DigitalOcean (DOKS, Managed PG, Spaces, VPC)
```

## Status

The full vertical slice **and the deploy-layer conductor** run end-to-end locally on **free data**:

- a BYO agent calls MCP tools; its research session is recorded as a persistent `research` run so the
  observability UI lists + replays it;
- a declarative `StrategySpec` is validated + proposed, and the control plane enqueues runs + gates promotions
  (the single writer of the money path);
- the **conductor** (`scripts/run_workers.py`) *pulls the queue*: the backtest worker executes queued runs to
  `succeeded`, and the paper scheduler ticks `live` deployments — the runtime *proposes* a book delta and the
  control plane's single-writer `apply_paper_delta` re-gates and writes the position book (applied `fill`);
- every step is a gap-free trace; the UI replays it and exposes the human lifecycle controls
  (promote → activate → pause/resume → retire) + the live paper book.
- the DigitalOcean deploy path uses managed Postgres as the platform system-of-record and splits
  stateless API/MCP pods from the always-on worker loops (`conductor` + `trigger-engine`), so
  the app plane no longer depends on a shared SQLite PVC.

The DigitalOcean deploy layer is shaped in Terraform (declarative, not applied); "prod" is paper-only by design.

```bash
# one-time
uv sync --all-packages --extra dev    # Python workspace
pnpm install                          # TS workspace (contracts + web)

# prove the whole pipeline (research → propose → backtest → observe), offline + deterministic
uv run python scripts/demo_e2e.py
# prove the deploy layer drives itself (control plane enqueues → worker pulls → paper money path applies)
uv run python scripts/demo_deploy.py

# run every Python suite
for p in packages/contracts/py doomberg-core services/platform services/mcp-gateway \
         services/control-plane services/rest-gateway services/runtime; do
  (cd "$p" && uv run --extra dev pytest -q); done

# contracts gate + UI
pnpm run contracts:check                      # regen from schema, fail on drift
pnpm --filter @doomberg/contracts run test    # zod round-trip
pnpm --filter @doomberg/web run test && pnpm --filter @doomberg/web run build
```

### Run the services locally

```bash
export DOOMBERG_DB=./doomberg.db              # local SQLite system-of-record (default :memory:)
# Production uses managed Postgres instead:
# export DOOMBERG_DB=postgresql://user:pass@host:5432/dbname?sslmode=require

# MCP server the BYO agent connects to (stdio)
uv run python -m doomberg_mcp

# control plane (single money-path writer) and the UI's REST+SSE backend
uv run --package doomberg-control-plane uvicorn doomberg_control.app:app --port 8001
uv run --package doomberg-rest-gateway  uvicorn doomberg_rest.app:app   --port 8000

# the deploy-layer conductor: pulls the backtest queue + ticks live paper deployments
uv run python scripts/run_workers.py

# trigger engine: polls active trigger policies and creates durable runs.
# For live quotes, point it at the user-run IBKR engine on the VPS.
export DOOMBERG_IBKR_ENGINE_URL=https://your-ibkr-engine.example.com
export DOOMBERG_IBKR_ENGINE_TOKEN=replace-with-bearer-token   # optional if the VPS is otherwise private
# Optional when the VPS does not expose GET /quote?symbol=NVDA.
# export DOOMBERG_IBKR_QUOTE_PATH=/v1/market/quote/{symbol}
uv run --package doomberg-runtime python -m doomberg_runtime.trigger_engine

# execution gateway: paper fills are enabled by default. Live IBKR submission is
# blocked unless this is explicitly set and an IBKR order endpoint is configured.
# export DOOMBERG_ENABLE_LIVE_EXECUTION=1
# export DOOMBERG_IBKR_ORDER_PATH=/orders
# export DOOMBERG_EXECUTION_MAX_NOTIONAL_USD=10000

# observability UI (proxies /api -> :8000)
pnpm --filter @doomberg/web dev
```

All six local processes share the same platform system-of-record via `DOOMBERG_DB`. The browser talks only to the
rest-gateway (`:8000`); its human money-path actions (promote/activate/pause/resume/retire) call the same
`doomberg_control.actions` the control plane exposes, so there is one money-path implementation, two transports.
The trigger engine also shares `DOOMBERG_DB`, uses the IBKR engine only as a per-user connected-account data
source, and never submits broker orders directly.

In Kubernetes, `deploy/deploy_services.sh` creates the same `doomberg-db` Secret in the gateway and worker
namespaces. `doomberg-app` runs `rest-gateway`, `control-plane`, and hosted HTTP MCP; `doomberg-workers`
runs the active queue/paper/trigger loops against the same Postgres store.

The implemented skill catalog is contract-backed by `doomberg_core.skills.ALL_SKILL_MANIFESTS`.
MCP `search_skills` and `describe_skill` read those manifests, while `run_skill` still only
executes skills present in the runnable registry.

### Contracts (the frozen source of truth)

`packages/contracts/schema/*.schema.json` generate both pydantic (Python) and zod (TS). Edit a schema →
`pnpm run contracts:codegen` → commit schema + regenerated code together. CI fails on drift.

### Requirements
Python 3.11+, uv, Node 24+, pnpm. Contract codegen pins its tools
(`datamodel-code-generator`, `black`, `json-schema-to-zod`) for deterministic output.

> `site/` is a standalone marketing landing page (its own lockfile, not in the workspace), generated
> alongside the product as a bonus — not part of the platform.
