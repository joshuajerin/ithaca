# infra/k8s - Doomberg v2 service manifests

Deployment + Service manifests for the always-on plane, rendered by
`deploy/deploy_services.sh` and applied with `kubectl` after the DOKS cluster
exists (see `deploy/RUNBOOK.md`).

The manifests are environment-aware shell templates. `DEPLOY_ENV=prod` keeps the
existing production namespaces and NodePorts; `DEPLOY_ENV=dev` renders into a
separate namespace pair with distinct NodePorts and secrets.

## App/Worker Split

The platform system-of-record is now Postgres: every app container receives
`DOOMBERG_DB` from the `doomberg-db.platform_url` Secret key. The read-only
archive uses `DOOMBERG_ARCHIVE_URL` from `doomberg-db.archive_url`; those DSNs
may point at the same managed database with different schemas.

`app-deployment.yaml` runs only the stateless ingress/control roles:
`rest-gateway`, `control-plane`, and `mcp-gateway`. `worker-deployment.yaml`
runs the active loops: `conductor` and `trigger-engine`. Postgres removes the
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
- `worker-deployment.yaml` - conductor + trigger-engine.
- `app-service.yaml` - NodePort service with env-specific ports.
- `worker-networkpolicy.yaml` - default-deny worker namespace plus DNS, gateway, Postgres, and provider egress.
- `caddy.yaml` - public HTTPS routing for prod and dev hostnames.
- `pvc.yaml` - legacy SQLite state PVC retained for rollback/dev experiments; not applied by `deploy_services.sh`.

The `doomberg-db` Secret is created in both the gateway and worker namespaces by
`deploy/deploy_services.sh`, along with the image tag and replica counts.
Set `DOOMBERG_PLATFORM_DB_URL` for the platform store and `DOOMBERG_ARCHIVE_URL`
for archive reads. If `DOOMBERG_ARCHIVE_URL` is omitted, the deploy script uses
the platform DSN for both.

Set `DOOMBERG_IBKR_ENGINE_URL` (and optionally `DOOMBERG_IBKR_ENGINE_TOKEN` /
`DOOMBERG_IBKR_QUOTE_PATH`) in the deploy environment to back live trigger quote
evaluation with the user-run IBKR engine. Without a URL, the worker stays up but
active live-data trigger evaluations will return provider errors until configured.
Run `ibkr-smoke --symbol AAPL --json` from the deployed image, or call
`GET /api/ops/ibkr-smoke?symbol=AAPL`, to verify the read-only quote route,
source, entitlement class, and freshness before enabling live-data triggers.
Run `launch-gate --mode local --require-postgres --require-ibkr --json` from
the app image after rollout for the broader customer-handoff gate: platform
schema, REST auth, sessions, SSE replay, artifact reads, MCP auth rejection,
ops status, and provider smoke.

The REST and control-plane containers also receive the IBKR order endpoint and
execution safety knobs:

- `DOOMBERG_ENABLE_LIVE_EXECUTION` - must be `1` before the gateway will submit to IBKR.
- `DOOMBERG_IBKR_ORDER_PATH` - default `/orders`.
- `DOOMBERG_EXECUTION_MAX_NOTIONAL_USD`, `DOOMBERG_EXECUTION_MAX_QUANTITY`,
  `DOOMBERG_EXECUTION_MAX_FRESHNESS_MS` - deterministic risk limits.

Paper orders can be filled locally by the execution gateway. Live orders require
the explicit switch, an IBKR engine URL, a connected provider record with
order/trading capability, and a human submit action.
