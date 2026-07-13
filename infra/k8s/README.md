# infra/k8s - Doomberg v2 service manifests

Deployment + Service manifests for the always-on plane, rendered by
`deploy/deploy_services.sh` and applied with `kubectl` after the DOKS cluster
exists (see `deploy/RUNBOOK.md`).

The manifests are environment-aware shell templates. `DEPLOY_ENV=prod` keeps the
existing production namespaces and NodePorts; `DEPLOY_ENV=dev` renders into a
separate namespace pair with distinct NodePorts and secrets.

## App/Worker Split

The platform system-of-record is now Postgres: every app container receives
`DOOMBERG_DB` from the `doomberg-db.platform_url` Secret key.

`app-deployment.yaml` runs only the stateless ingress/control roles:
`rest-gateway`, `control-plane`, and `mcp-gateway`. `worker-deployment.yaml`
runs the singleton/interactive loops: `conductor` and `trigger-engine`.
With `BACKTEST_WORKER_ENABLED=1`, `backtest-worker-deployment.yaml` runs independently
scalable backtest-only workers on the `workload=backtest` node pool. Otherwise the
conductor keeps its embedded backtest loop enabled. Postgres removes the
old shared SQLite PVC requirement and lets the app replicas scale separately
from queue polling, paper ticks, and trigger evaluation.

The `platform-migrate` init container applies the platform schema before the
app and worker containers start. The process open path also applies idempotent
DDL, so a restart remains self-healing.

Production can run multiple `doomberg-workers` replicas. Backtest and
trigger-analysis jobs are claimed through durable job leases; the paper
scheduler and trigger polling loops use `worker_leases`, so only one replica
owns each singleton loop at a time. The default deploy uses two prod worker
replicas and one dev worker replica.

## Files

- `namespace.yaml` - gateway + worker namespaces for the selected env.
- `app-deployment.yaml` - rest-gateway + control-plane + mcp-gateway.
- `worker-deployment.yaml` - conductor + trigger-engine; its embedded backtest loop is disabled only when dedicated workers are enabled.
- `backtest-worker-deployment.yaml` - dedicated backtest workers, PDB, and CPU HPA.
- `disruption-budgets.yaml` - availability budgets for app and singleton workers.
- `app-service.yaml` - NodePort service with env-specific ports.
- `worker-networkpolicy.yaml` - default-deny worker namespace plus DNS, gateway, Postgres, and provider egress.
- `ibkr-engine.yaml` - split IBKR Client Portal Gateway and Doomberg wrapper services.
- `ibkr-networkpolicy.yaml` - limits the wrapper API to Doomberg app/workers and the login port to Caddy.
- `caddy.yaml` - public HTTPS routing for prod and dev hostnames.
- `caddy-ibkr-signin.yaml` - temporary public IBKR sign-in route; apply only with `IBKR_SIGNIN_PUBLIC=1`.
- `pvc.yaml` - legacy SQLite state PVC retained for rollback/dev experiments; not applied by `deploy_services.sh`.

The `doomberg-db` Secret is created in both the gateway and worker namespaces by
`deploy/deploy_services.sh`, along with the image tag and replica counts.
Set `DOOMBERG_PLATFORM_DB_URL` for the platform store.

Backtest bundles are durable only when private object storage is configured. Dedicated
production workers are opt-in with `BACKTEST_WORKER_ENABLED=1` and then require
`DOOMBERG_ARTIFACT_BUCKET`, `DOOMBERG_ARTIFACT_ENDPOINT_URL`,
`DOOMBERG_ARTIFACT_REGION`, `DOOMBERG_ARTIFACT_ACCESS_KEY_ID`, and
`DOOMBERG_ARTIFACT_SECRET_ACCESS_KEY`. Until those settings exist, production keeps the
embedded loop and its existing artifact behavior. The dedicated worker uploads
tenant/run-prefixed encrypted objects before succeeding; the REST gateway streams
tenant-authorized downloads without exposing storage credentials.

Set `IBKR_ENGINE_ENABLED=1` to deploy the managed in-cluster IBKR engine. The
Client Portal Java process runs as the dedicated `ibkr-gateway` Deployment and
the normalized Doomberg API runs as the separate `ibkr-engine` Deployment. The
deploy script defaults `DOOMBERG_IBKR_ENGINE_URL` to the internal `ibkr-engine`
ClusterIP service and creates matching app/engine tokens. It also reuses the
existing `ibkr-gateway` image unless `IBKR_GATEWAY_IMAGE` is explicitly set, so
ordinary app/wrapper deploys do not restart Java and drop the IBKR authenticated
session. Set `DOOMBERG_IBKR_ENGINE_URL` explicitly only when pointing Doomberg
at an external engine. Without an engine URL, the worker stays up but active
live-data trigger evaluations and IBKR MCP tools will return provider errors
until configured.
`IBKR_SIGNIN_PUBLIC=1` applies the temporary `IBKR_SIGNIN_HOST` sign-in route
(`ibkr.doomberg.me` by default; an `sslip.io` host can be used if registrar DNS
is unavailable). Deploy again with `IBKR_SIGNIN_PUBLIC=0` after customer login so
only the cluster can reach the gateway/API.
Run `ibkr-smoke --symbol AAPL --json` from the deployed image, or call
`GET /api/ops/ibkr-smoke?symbol=AAPL`, to verify the read-only quote route,
source, entitlement class, and freshness before enabling live-data triggers.
Run `launch-gate --mode local --require-postgres --require-ibkr --json` from
the app image after rollout for the broader customer-handoff gate: platform
schema, REST auth, sessions, SSE replay, artifact reads, MCP auth rejection,
real-time trigger-to-run readiness, MCP resource reads, MCP durable run
create/cancel, MCP resource scope denial, ops status, and provider smoke.
With `--require-ibkr`, the trigger probe uses the configured IBKR engine; without
it, local/offline checks use a static IBKR-shaped connected-account quote.

The REST, control-plane, and MCP containers also receive the IBKR order endpoint
and execution safety knobs:

- `DOOMBERG_ENABLE_LIVE_EXECUTION` - must be `1` before the gateway will submit to IBKR.
- `DOOMBERG_IBKR_ORDER_PATH` - default `/orders`.
- `DOOMBERG_IBKR_HISTORY_PATH`, `DOOMBERG_IBKR_NEWS_PATH`, and
  `DOOMBERG_IBKR_SCANNER_PATH` - live IBKR market-data endpoints for MCP
  `market.get_ohlcv`, `market.news`, `market.movers`, and `market.screener`.
- `DOOMBERG_IBKR_ACCOUNTS_PATH`, `DOOMBERG_IBKR_POSITIONS_PATH`, and
  `DOOMBERG_IBKR_ORDERS_PATH` - optional read-model overrides for hosted MCP
  `broker.accounts`, `broker.positions`, and `broker.orders`.
- `DOOMBERG_EXECUTION_MAX_NOTIONAL_USD`, `DOOMBERG_EXECUTION_MAX_QUANTITY`,
  `DOOMBERG_EXECUTION_MAX_FRESHNESS_MS` - deterministic risk limits.

Paper orders can be filled locally by the execution gateway. Live orders require
the explicit switch, an IBKR engine URL, a connected provider record with
order/trading capability, and a human submit action.
