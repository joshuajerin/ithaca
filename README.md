# Ithaca v2

A financial **tool-platform** that external (bring-your-own) AI agents call over **MCP** to research
markets and run **backtests + paper-trading** on trusted infrastructure — with a web **observability
surface** that lets a human watch their agent think, work, and trade.

> v1 was a monolith that ran its *own* agent loop and compiled AI-authored code at runtime (the source of
> two critical RCEs). **v2 never runs the agent and never executes agent-authored code.** It exposes vetted
> tools, executes *declarative* strategy specs on trusted infra, and observes.

Full plan: [`docs/plans/ithaca-v2/MASTER-PLAN.md`](docs/plans/ithaca-v2/MASTER-PLAN.md).
Data sourcing strategy: [`docs/plans/ithaca-v2/DATA-SOURCING-STRATEGY.md`](docs/plans/ithaca-v2/DATA-SOURCING-STRATEGY.md).

## Layout

```
packages/contracts/   FROZEN source of truth — JSON Schema -> generated pydantic + zod (this is Phase 0)
ithaca-core/        the ONE shared Python core (engine/ sources/ registry/ graph/ accounting/ risk/ gateway/)
services/
  mcp-gateway/        primary product surface: MCP tools the agent calls
  rest-gateway/       feeds the web UI (REST + SSE) from the same core
  control-plane/      specs, run state machine, compliance gate — SINGLE writer of the money path
  runtime/            DO workers: backtest_runner + live_runner (import ithaca-core)
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
for p in packages/contracts/py ithaca-core services/platform services/mcp-gateway \
         services/control-plane services/rest-gateway services/runtime; do
  (cd "$p" && uv run --extra dev pytest -q); done

# contracts gate + UI
pnpm run contracts:check                      # regen from schema, fail on drift
pnpm --filter @ithaca/contracts run test    # zod round-trip
pnpm --filter @ithaca/web run test && pnpm --filter @ithaca/web run build
```

### Run the services locally

```bash
export ITHACA_DB=./ithaca.db              # local SQLite system-of-record (default :memory:)
export ITHACA_ENV=local                     # enables local X-Tenant-Id dev auth fallback
# Production uses managed Postgres instead:
# export ITHACA_DB=postgresql://user:pass@host:5432/dbname?sslmode=require

# MCP server the BYO agent connects to (stdio)
uv run python -m ithaca_mcp

# control plane (single money-path writer) and the UI's REST+SSE backend
uv run --package ithaca-control-plane uvicorn ithaca_control.app:app --port 8001
uv run --package ithaca-rest-gateway  uvicorn ithaca_rest.app:app   --port 8000

# the deploy-layer conductor: pulls the backtest queue + ticks live paper deployments
# Optional: persist worker-generated backtest artifacts as local files. If unset,
# artifact records still carry deterministic memory:// URIs, byte counts, and SHA-256 hashes.
# export ITHACA_ARTIFACT_DIR=/var/lib/ithaca/artifacts
uv run python scripts/run_workers.py

# trigger engine: polls active trigger policies and creates durable runs.
# For local live quotes, point it at an IBKR engine.
export ITHACA_IBKR_ENGINE_URL=https://your-ibkr-engine.example.com
export ITHACA_IBKR_ENGINE_TOKEN=replace-with-bearer-token   # optional if the VPS is otherwise private
# Optional when the VPS does not expose GET /quote?symbol=NVDA.
# export ITHACA_IBKR_QUOTE_PATH=/v1/market/quote/{symbol}
# Optional hard freshness gate for read-only live-data handoff checks.
# export ITHACA_IBKR_SMOKE_MAX_FRESHNESS_MS=60000
uv run python scripts/ibkr_smoke.py --symbol AAPL --json
uv run --package ithaca-runtime python -m ithaca_runtime.trigger_engine

# execution gateway: paper fills are enabled by default. Live IBKR submission is
# blocked unless this is explicitly set and an IBKR order endpoint is configured.
# export ITHACA_ENABLE_LIVE_EXECUTION=1
# export ITHACA_IBKR_ORDER_PATH=/orders
# export ITHACA_EXECUTION_MAX_NOTIONAL_USD=10000

# customer-handoff launch gate: migrations, REST auth, sessions, SSE replay,
# worker-generated hashed backtest artifact bundles, artifact reads,
# trigger-to-run readiness, MCP auth/resource checks,
# MCP run create/cancel, ops status, and optional IBKR smoke.
uv run python scripts/launch_gate.py --mode local --skip-ibkr

# observability UI (proxies /api -> :8000)
pnpm --filter @ithaca/web dev
```

### Install Ithaca MCP in local agents

With the hosted app deployed, a user can link a coding agent in one command:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3
```

The installer opens the Ithaca app, lets the user sign in or sign up with Clerk,
then asks for approval to mint a scoped MCP key. After approval it stores the
key in `~/.config/ithaca/mcp.env`, registers the hosted streamable-HTTP MCP
server as `ithaca`, verifies a real MCP `initialize` handshake, calls
`ithaca_init` to open a visible onboarding session, and writes the generated
catalog guide to `~/.config/ithaca/TOOLS.md`.

Cursor, Claude Code, Codex, OpenClaw, and Hermes are configured by default.
Codex uses `codex mcp add --url ... --bearer-token-env-var ITHACA_MCP_API_KEY`.
Claude Code uses `claude mcp add --transport http --scope user` with an
`Authorization: Bearer ${ITHACA_MCP_API_KEY}` header reference, not a
hardcoded token. Cursor, OpenClaw, and Hermes get merged `mcpServers` JSON
config files without overwriting existing servers. To target one client, pass
`--client cursor`, `--client claude-code`, `--client codex`, `--client openclaw`,
or `--client hermes`.

See [Agent Client Setup](docs/AGENT_CLIENT_SETUP.md) for per-client behavior.

For agent-driven setup, ask the agent to run:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --agent-init
```

The agent prints the sign-in/signup URL for the user, waits for approval, installs the MCP
config, verifies a real MCP initialize handshake, calls `ithaca_init`, and generates
`~/.config/ithaca/TOOLS.md` from the live MCP tool and toolkit catalogs. See
[Agent-Driven Onboarding](docs/AGENT_DRIVEN_ONBOARDING.md).

All six local processes share the same platform system-of-record via `ITHACA_DB`. The browser talks only to the
rest-gateway (`:8000`); its human money-path actions (promote/activate/pause/resume/retire) call the same
`ithaca_control.actions` the control plane exposes, so there is one money-path implementation, two transports.
The trigger engine also shares `ITHACA_DB`, uses the IBKR engine only as a per-user connected-account data
source, and never submits broker orders directly.
Users can dry-run trigger policies through REST before activation; the dry-run reports the
same condition/control decision without creating runs, firings, approvals, jobs, or broker
actions. The launch gate dry-runs a synthetic quote-only trigger, then creates one active
trigger, verifies it creates a durable run with connected-account provenance, and retires it;
when `--require-ibkr` is set and `ITHACA_IBKR_ENGINE_URL` is configured, the active trigger
probe uses the live IBKR engine instead of the static IBKR-shaped quote used in local/offline
checks.

In Kubernetes, `deploy/deploy_services.sh` creates the same `ithaca-db` Secret in the gateway and worker
namespaces. `ithaca-app` runs `rest-gateway`, `control-plane`, and hosted HTTP MCP; `ithaca-workers`
runs the active queue/paper/trigger loops against the same Postgres store. With `IBKR_ENGINE_ENABLED=1`, the
deploy script also runs the managed IBKR Client Portal Gateway wrapper and points Ithaca at the internal
`ibkr-engine` service. `IBKR_SIGNIN_PUBLIC=1` opens a temporary `https://ibkr.tradeithaca.com/` sign-in route;
set `IBKR_SIGNIN_HOST` to an `sslip.io` hostname if the `tradeithaca.com` DNS record is not available. Deploy
again with `IBKR_SIGNIN_PUBLIC=0` after authentication so only the cluster-internal service remains.

The implemented skill catalog is contract-backed by `ithaca_core.skills.ALL_SKILL_MANIFESTS`.
MCP `search_skills` and `describe_skill` read those manifests, while `run_skill` still only
executes skills present in the runnable registry.
MCP clients can also read the progressive-discovery resources
`ithaca://skills/catalog`, `ithaca://skills/{skill_id}/{version}`,
`ithaca://toolkits/catalog`, `ithaca://toolkits/{toolkit_id}`,
`ithaca://runs/{run_id}`, `ithaca://policies/current`, `ithaca://accounts`,
and `ithaca://data/providers`; hosted HTTP resource reads require `data:read` and
return tenant-scoped, credential-redacted JSON. REST provider responses follow the
same boundary: they expose `credential_configured`, never `credential_ref`. The
customer-handoff launch gate also proves that hosted MCP can queue a durable
`backtest.run`, read it back through `ithaca://runs/{run_id}`, cancel it, and
observe the cancelled run/job state.

### Contracts (the frozen source of truth)

`packages/contracts/schema/*.schema.json` generate both pydantic (Python) and zod (TS). Edit a schema →
`pnpm run contracts:codegen` → commit schema + regenerated code together. CI fails on drift.

### Requirements
Python 3.11+, uv, Node 24+, pnpm. Contract codegen pins its tools
(`datamodel-code-generator`, `black`, `json-schema-to-zod`) for deterministic output.

> `site/` is a standalone marketing landing page (its own lockfile, not in the workspace), generated
> alongside the product as a bonus — not part of the platform.
