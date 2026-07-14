# Ithaca v2 — DigitalOcean deploy RUNBOOK

Reliability-first, HA, **CPU-only** stack on DOKS. This is the full one-command-ish
sequence to take the repo from "apply-ready Terraform" to a running paper-prod
cluster, plus the node-failover test that proves HA.

## GitHub-controlled deploys

The normal deploy path is now GitHub Actions:

| Branch | Environment | Kubernetes namespaces | Public hosts |
|---|---|---|---|
| `main` | `prod` | `ithaca-gateway`, `ithaca-workers` | `app.tradeithaca.com`, `mcp.tradeithaca.com` |
| any other same-repo branch | `dev` | `ithaca-dev-gateway`, `ithaca-dev-workers` | `dev-app.tradeithaca.com`, `dev-mcp.tradeithaca.com` |

Prod app and active worker pods default to the `paper` node pool. Dev app and
worker pods default to the tainted `backtest` pool so dev does not compete with
prod for the current paper node; override with `APP_NODE_WORKLOAD` or
`WORKER_NODE_WORKLOAD` if the cluster topology changes. Prod app replicas
default to `2`; active worker replicas default to `2`.

`deploy-do.yml` builds an immutable DOCR image from the checked-out SHA, deploys only
that tag, and moves `latest` only after a successful prod rollout. The prod job also
verifies that the deploying SHA still equals `origin/main`.

Each GitHub environment owns its own secrets and variables. Required secrets are
`DIGITALOCEAN_ACCESS_TOKEN`, `ITHACA_PLATFORM_DB_URL`, `ITHACA_SESSION_SECRET`,
`CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, and either `CLERK_PEM_PUBLIC_KEY` or the
`CLERK_JWKS_URL` variable. Required variables include `CLERK_ALLOWED_ORIGINS`.

### Clerk waitlist access

Enable **Waitlist** mode in the Clerk Dashboard and keep email authentication enabled.
Existing users and invited waitlist users can sign in; everyone else is sent to the
Clerk-managed waitlist at `/waitlist`.

Approve one or more email addresses with Clerk's waitlist API:

```bash
CLERK_SECRET_KEY=... uv run --package ithaca-platform \
  python scripts/clerk_waitlist.py approved@example.com another@example.com
```

The command is idempotent for already invited or completed entries. Clerk sends the
invitation email and remains the source of truth for approval status.
Production also requires `ITHACA_ADMIN_TOKEN`, `ITHACA_SMOKE_API_KEY`, and
`ITHACA_SMOKE_NO_SCOPE_API_KEY`. Optional secrets include `FMP_API_KEY` and
`DATABENTO_API_KEY`.

Before the first deploy, enable **User API keys** in Clerk Dashboard under
**Configure → API keys → Enable API keys**. Ithaca creates keys through Clerk's Backend
API with tenant-binding claims and capability scopes. Clerk owns the plaintext secret,
verification, usage metadata, and revocation; the local `api_keys` table is retained only so
previously-issued `ith_` keys keep working during migration.

Local scripts in this directory remain available as break-glass tooling. They now
accept `DEPLOY_ENV=prod|dev` and render environment-specific Kubernetes
manifests instead of assuming prod.

> **Boundary:** every step below requires a DigitalOcean API token in
> `infra/terraform/.env`. There is no token in the repo and nothing here runs
> automatically — applying creates billable resources. Read the cost section first.

---

## 0. Prerequisites (one time)

```bash
# Tools
brew install hashicorp/tap/terraform doctl   # or your platform's installer
# docker (a running daemon) for the image build

# DO API token (scopes: kubernetes, databases, registry, vpc, load_balancer,
# spaces + read on account/regions/sizes). Plus Spaces keys for the bucket.
cp infra/terraform/.env.example infra/terraform/.env
$EDITOR infra/terraform/.env        # set DIGITALOCEAN_TOKEN + SPACES_* keys
```

`infra/terraform/.env` is gitignored. Never commit it; never paste the token in chat.

> **REQUIRED SCOPE — `tag:create`.** DOKS cluster creation makes DigitalOcean
> auto-apply a `k8s:<cluster-id>` tag to the cluster + its worker droplets. If the
> token lacks the **`tag:create`** scope, `terraform apply` fails at the cluster
> with `401 tagging requires tag:create permission` — even with NO user tags. A
> read/databases/kubernetes/registry/vpc token is **not enough**; the token must
> also carry `tag:create` (a full-access token is simplest). Verify before apply:
> `doctl compute tag create scope-probe && doctl compute tag delete scope-probe`.

> **Pre-existing Postgres + no Spaces keys (this deployment).** The dev + prod
> Managed Postgres already exist and are seeded, so Terraform must NOT create a DB.
> `infra/terraform/terraform.auto.tfvars` sets `manage_postgres=false` (workload
> reads the prod DB via the `ITHACA_PROD_URL` secret), `manage_spaces=false` (no
> Spaces keys; bucket not needed), `enable_archive_load_job=false` (already loaded),
> and `apply_resource_tags=false` (the LB targets the auto `k8s:<cluster-id>` tag
> instead of a custom pool tag). Flip any of these on with the right credentials.

---

## 1. Build + push the image

One lean multi-service image (`python:3.12-slim`, CPU-only) serves every role.

```bash
deploy/build_and_push.sh                 # tags with the git short SHA + :latest
# or pin a tag:
deploy/build_and_push.sh v2025-06-17
```

This builds `linux/amd64` (DOKS nodes are amd64), logs in with `doctl registry
login`, and pushes to `registry.digitalocean.com/ithaca/ithaca:<tag>`.
It uses only registry storage — no compute spend.

> If you pinned a non-`latest` tag, set `worker_image` / `archive_loader_image`
> in `infra/terraform/.env`-sourced vars or a `terraform.auto.tfvars` to that tag.
> The defaults point at `:latest`.

---

## 2. Plan the infrastructure (safe — no changes)

```bash
deploy/apply.sh                # init + validate + PLAN only. Creates nothing.
```

The plan fails fast if any node/DB size is a GPU slug (CPU-ONLY GUARDRAIL) or if
Postgres / the paper pool is configured non-HA. Review the plan output.

What it provisions (the allowlist — nothing else):

| Resource | Shape |
|---|---|
| VPC | private `10.20.0.0/20` |
| DOKS cluster | **HA control plane**, registry-integrated, auto-upgrade |
| node pool `backtest` | `c-4`, autoscale **min 1 (warm) → max 8** |
| node pool `paper` (always-on) | `s-2vcpu-4gb` × **4** (HA + rollout headroom) — gateways + scheduler |
| Managed Postgres 16 | `db-s-2vcpu-4gb`, **2 nodes = primary + standby (HA)**, daily backups + WAL/PITR, storage autoscale |
| Container Registry | `ithaca`, professional tier |
| Load Balancer | `size_unit = 2` (HA) → gateway pool |
| Spaces bucket | private, versioned (artifacts/logs) |
| Firewalls / NetworkPolicy | DB locked to cluster; worker namespace default-deny with explicit DNS, gateway, Postgres, and provider egress |

---

## 3. Apply (creates billable resources)

```bash
deploy/apply.sh --apply        # PLAN, then APPLY after you type 'apply'
# scripted / CI:
deploy/apply.sh --apply --yes
```

Provisioning takes ~10–15 min (DOKS + Managed PG are the slow parts).

---

## 4. Wire kubeconfig + secrets

```bash
cd infra/terraform

# kubeconfig
terraform output -raw kubeconfig > /tmp/ithaca.kubeconfig
export KUBECONFIG=/tmp/ithaca.kubeconfig
kubectl get nodes        # expect 1 backtest (warm) + 2 paper nodes Ready

# DB DSN secret used by gateways, control-plane, and runtime.
# platform_url is the platform system-of-record.
APP_URI="$(terraform output -raw postgres_app_uri)"
kubectl create namespace ithaca-gateway --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace ithaca-workers --dry-run=client -o yaml | kubectl apply -f -
kubectl -n ithaca-gateway create secret generic ithaca-db \
  --from-literal=db_url="${APP_URI}" \
  --from-literal=platform_url="${APP_URI}"
kubectl -n ithaca-workers create secret generic ithaca-db \
  --from-literal=db_url="${APP_URI}" \
  --from-literal=platform_url="${APP_URI}"
```

> `deploy/deploy_services.sh` creates/updates the full `ithaca-db` Secret in
> both namespaces, including Clerk/session/IBKR/execution keys. The manual
> commands above are only for a minimal bootstrap or break-glass path. The DB
> firewall already restricts Postgres to the cluster.

---

## 5. Apply the platform schema

`deploy/deploy_services.sh` runs the `platform-migrate` init container before
the API/worker containers start. It applies ordered migrations under a Postgres
advisory lock and records their checksums in `ithaca_schema_migrations`.
Application containers use `ITHACA_DB_MIGRATION_MODE=validate`, so they fail
closed on a missing, pending, or drifted schema instead of changing DDL during
normal request startup. Outside Kubernetes, Postgres keeps the backwards-
compatible `apply` default; set the mode explicitly to `validate` for managed
deployments and `off` only for schema administration tooling.

Each process uses a bounded psycopg connection pool. Defaults are one warm
connection and four maximum connections per process, with a ten-second
checkout/startup timeout and connection health checks before use. Tune with
`ITHACA_POSTGRES_POOL_MIN`, `ITHACA_POSTGRES_POOL_MAX`,
`ITHACA_POSTGRES_POOL_TIMEOUT_S`, `ITHACA_POSTGRES_POOL_MAX_LIFETIME_S`,
`ITHACA_POSTGRES_POOL_MAX_IDLE_S`, and
`ITHACA_POSTGRES_RECONNECT_TIMEOUT_S`. Size the per-process maximum against
the managed Postgres connection budget multiplied by the total replica and
container count.

Postgres migration 2 enables and forces row-level security on every tenant
table, including indirect ownership through `run_seq`, `oauth_accounts`, and
`user_sessions`. Platform stores establish a transaction-local tenant scope
automatically; trusted authentication and worker queue operations use an
explicit system scope. A direct application query with no scope sees no tenant
rows. Do not bypass the store layer for tenant data.

The production database login must be `NOSUPERUSER NOBYPASSRLS`; PostgreSQL
superusers bypass RLS even when a table uses `FORCE ROW LEVEL SECURITY`. Verify
the deployed role and policy state before admitting traffic:

```sql
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles
WHERE rolname = current_user;

SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relname IN (
  'runs', 'trace_events', 'jobs', 'order_intents',
  'execution_controls', 'compliance_policies'
)
ORDER BY relname;
```

The application credential remains trusted: internal system operations set a
transaction-local `ithaca.system_access` flag. RLS is a containment boundary
for missing or incorrect tenant predicates, not a substitute for protecting
database credentials or preventing arbitrary SQL execution.

Migration 3 adds unique broker-order and broker-fill identities. Before applying
it to an existing database, both queries below must return zero rows; duplicates
require an operator-led broker audit rather than automatic deletion:

```sql
SELECT tenant_id, broker, broker_order_id, count(*)
FROM orders WHERE broker_order_id IS NOT NULL
GROUP BY tenant_id, broker, broker_order_id HAVING count(*) > 1;

SELECT tenant_id, broker_fill_id, count(*)
FROM fills WHERE broker_fill_id IS NOT NULL
GROUP BY tenant_id, broker_fill_id HAVING count(*) > 1;
```

Migration 4 adds tenant and global execution controls plus their append-only
audit events. Row-level security is forced on both tables. Tenant operators use
the authenticated `POST /execution/kill-switch` control-plane route or the
dashboard compliance panel; site operators use the admin-token-protected
`POST /admin/execution/kill-switch` route. Both writes use optimistic versions,
and `expect_version` is required, so a stale release cannot overwrite a newer
emergency halt. Site operators can read the current global control and its audit
history with `GET /admin/execution/kill-switch`.

Migration 5 adds versioned tenant compliance policies and append-only policy
events with forced row-level security. The dashboard's limits, restricted list,
watch list, and pre-trade check all use these rows. Every mutation requires the
current `policyVersion`; stale writes return 409. Built-in limits remain visible
reference defaults until the tenant explicitly saves the limits form, while the built-in
restricted list is always enforced. Once saved, firm limits are enforced during
strategy promotion and every paper-book application; restricted names also
block direct execution intents and watch names produce warnings. Policy events
appear in the same tenant compliance audit timeline as kill-switch events.
Tenant policy writes take the same application fence used by broker sends and
paper-book writes, so each mutation is ordered wholly before or after a money
path action instead of racing its final check.

---

## 6. Verify live-data wiring

Market data now comes from the Ithaca live-data engine. Do not seed or deploy a v1 archive.

---

## 7. Deploy the services

Deploy the always-on planes with `deploy/deploy_services.sh`. The current
runtime topology has two deployments:

`ithaca-app` in the gateway namespace:

- `rest-gateway`
- `control-plane`
- `mcp-gateway`

`ithaca-workers` in the worker namespace:

- `conductor` (backtest/trigger workers, paper scheduler, notifications, adaptive
  dashboard recompute, and broker order reconciliation)
- `trigger-engine` (active trigger policy polling)

Both deployments intentionally share the managed Postgres platform store through
`ITHACA_DB=ithaca-db.platform_url`; no SQLite PVC is mounted in the normal
deploy path. NodePorts stay `30080` (rest/app) and `30808` (MCP), matching the
load balancer rules in Terraform. The service manifest, worker network policy,
both `ithaca-db` Secrets, and replica counts are rendered/applied by
`deploy/deploy_services.sh`.

Production defaults to `WORKER_REPLICAS=2`. Backtest and trigger-analysis jobs
are claimed through durable job leases. The paper scheduler and trigger polling
loops use the platform `worker_leases` table, as does the execution reconciler,
so only one worker replica owns each singleton loop at a time; if the owner dies,
another replica takes over after the lease TTL. Order reconciliation defaults to
five seconds and is tunable with `ITHACA_RECONCILIATION_INTERVAL_S`.

Migration 6 adds `worker_heartbeats`, a system-only durable process registry.
Every conductor loop and the trigger engine records its role, instance id,
status, last heartbeat, expiry, and bounded diagnostic metadata. Leadership
leases still prevent duplicate singleton work; heartbeats answer the separate
question of whether the responsible process is alive and making progress.
`GET /api/ops/status` excludes expired leases from the active list and reports
missing, degraded, expired, and healthy worker roles explicitly.

Both gateways expose `GET /livez` for process liveness and `GET /healthz` plus
`GET /readyz` for a live database ping, migration-ledger validation, and pool
statistics. A database or migration failure returns 503; worker-role degradation
remains visible through the authenticated ops status instead of ejecting a
read-capable gateway from the load balancer.

For connected-account live trigger quotes, use the managed in-cluster IBKR engine
by default:

```bash
./deploy/build_ibkr_engine.sh "${IMAGE_TAG}"
IBKR_ENGINE_ENABLED=1 DEPLOY_ENV=prod IMAGE_TAG="${IMAGE_TAG}" ./deploy/deploy_services.sh
```

When `IBKR_ENGINE_ENABLED=1`, `deploy/deploy_services.sh` defaults the app,
workers, REST, control-plane, and MCP to the internal engine service:

```bash
http://ibkr-engine.ithaca-gateway.svc.cluster.local:8090
```

The customer sign-in URL is temporary. Open it only for the sign-in window, then
deploy again without the flag to remove the public broker surface:

```bash
# Optional: restrict the temporary sign-in route to a known IP/CIDR.
IBKR_SIGNIN_PUBLIC=1 \
IBKR_SIGNIN_HOST=ibkr.tradeithaca.com \
IBKR_SIGNIN_REMOTE_IPS="203.0.113.10/32" \
IBKR_ENGINE_ENABLED=1 \
DEPLOY_ENV=prod \
IMAGE_TAG="${IMAGE_TAG}" \
./deploy/deploy_services.sh

dig +short ibkr.tradeithaca.com A
open https://ibkr.tradeithaca.com/

# After the customer signs in, verify the session from inside the cluster.
kubectl -n ithaca-gateway exec deploy/ibkr-engine -c ithaca-ibkr-engine -- \
  sh -lc 'curl -fsS -H "Authorization: Bearer ${ITHACA_IBKR_ENGINE_TOKEN}" http://127.0.0.1:8090/auth/status'

# Probe semantics are intentionally separate:
# - /livez proves the wrapper process can answer.
# - /readyz proves the private Client Portal gateway is reachable.
# - /data/healthz proves the brokerage/data session is authenticated.
kubectl -n ithaca-gateway exec deploy/ibkr-engine -c ithaca-ibkr-engine -- \
  sh -lc 'curl -fsS http://127.0.0.1:8090/livez && curl -fsS http://127.0.0.1:8090/readyz && curl -fsS http://127.0.0.1:8090/data/healthz'

# Close the public route. Ithaca keeps using the internal ClusterIP service.
IBKR_SIGNIN_PUBLIC=0 IBKR_ENGINE_ENABLED=1 DEPLOY_ENV=prod IMAGE_TAG="${IMAGE_TAG}" ./deploy/deploy_services.sh
curl -I https://ibkr.tradeithaca.com/ || true
```

If `ibkr.tradeithaca.com` is not available in DNS, set `IBKR_SIGNIN_HOST` to a
temporary hostname that already resolves to the Caddy LoadBalancer, for example
`ibkr.129.212.135.120.sslip.io`, and remove it after authentication the same way.

Read operations repair an expired `/iserver` session by default. The repair calls
`/tickle`, then a serialized `/iserver/auth/ssodh/init` when browser login is still
valid. Set `IBKR_AUTO_REPAIR_AUTH=false` only for diagnosis. Tune bounded polling
with `IBKR_AUTH_INIT_ATTEMPTS`, `IBKR_AUTH_INIT_RETRY_DELAY_S`, and
`IBKR_AUTH_REPAIR_TIMEOUT_S`. Concurrent repair waiters fail quickly instead of
occupying the API worker pool. A browser-login expiry still fails closed and
requires a new sign-in window.

The wrapper's operational endpoints are:

| Endpoint | Auth | Side effects | Meaning |
| --- | --- | --- | --- |
| `GET /livez` | none | none | Wrapper process is alive. |
| `GET /readyz` | none | none | Private Client Portal gateway is reachable. |
| `GET /data/healthz` | none | none | Brokerage/data session is authenticated and connected. This probe never repairs auth. |
| `GET /healthz` | none | none | Compatibility route with `/readyz` success semantics and its legacy failure envelope. |
| `GET /auth/status` | engine bearer token | none | Sanitized authentication and connection state. Raw IBKR payloads are intentionally omitted. |
| `POST /auth/tickle` | engine bearer token | IBKR keepalive tickle | Refresh and report sanitized session state. |
| `POST /auth/ensure` | engine bearer token | May initialize `/iserver` auth | Run the bounded, serialized repair flow. |

Authenticated control endpoints return `401` for a missing token, `403` for a bad
token, and `503` with a stable `detail.code`, `detail.message`, and optional
`detail.details` object when the upstream operation cannot complete.

If you must point Ithaca at an external engine instead, set:

```bash
export ITHACA_IBKR_ENGINE_URL=https://your-ibkr-vps.example.com
export ITHACA_IBKR_ENGINE_TOKEN=...        # optional if the endpoint is private
export ITHACA_IBKR_QUOTE_PATH=/quote?symbol={symbol}  # optional
export ITHACA_IBKR_SMOKE_MAX_FRESHNESS_MS=60000        # optional live-session gate
```

Before enabling trigger policies that require connected live data, run the same
read-only quote smoke the REST dashboard and MCP `ibkr_smoke` tool use:

```bash
python scripts/ibkr_smoke.py --symbol AAPL --json
```

In Kubernetes, run it from the deployed image with the same Secret-mounted env:

```bash
kubectl -n ithaca-workers run ibkr-smoke --rm -it --restart=Never \
  --image="${IMAGE}" -- ibkr-smoke --symbol AAPL --json
```

Run the full customer-handoff gate after rollout. This creates a synthetic
launch-gate tenant/session/artifact, verifies REST auth rejection, ops status,
gateway liveness plus database/migration readiness, current required worker
heartbeats, the durable personalized compliance surface,
SSE replay, artifact fetch, MCP unauthenticated rejection, authenticated MCP
resource reads, real-time trigger-to-run readiness, MCP durable `run_skill`
enqueue/read/cancel cleanup, MCP no-scope resource denial, and the IBKR quote
smoke when required. The trigger probe creates a synthetic quote-only trigger,
dry-runs it first to prove no durable side effects, fires it once, verifies the
durable run and firing history, then retires it; with `--require-ibkr`, it
reads the configured IBKR engine instead of the offline static quote. Provider
responses are also checked for credential redaction: REST/MCP expose
`credential_configured`, never `credential_ref`:

```bash
kubectl -n ithaca-gateway run launch-gate --rm -it --restart=Never \
  --image="${IMAGE}" -- launch-gate --mode local --require-postgres --require-ibkr --json
```

For an external check through ingress, provide the public REST/MCP URLs and an
issued API key. Set `ITHACA_MCP_NO_SCOPE_API_KEY` as well when you want the
gate to prove resource reads are denied for a valid key without `data:read`.

```bash
ITHACA_REST_URL=https://app.tradeithaca.com \
ITHACA_MCP_URL=https://mcp.tradeithaca.com/mcp \
ITHACA_API_KEY=ith_... \
python scripts/launch_gate.py --mode http --require-postgres --require-workers-ready --require-ibkr --require-mcp --json
```

`--require-workers-ready` gates on the complete production role set returned by
ops status, not on the mere presence of a lease row: backtest, trigger engine,
trigger jobs, paper, notification, adaptive-dashboard, and execution
reconciliation. Expired and degraded heartbeats fail the gate even when the
corresponding queue happens to be empty.

Use [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for the exact preflight,
evidence capture, rollback boundary, and handoff record for each production
release.

The repository's default IBKR engine is deliberately data-only: `GET /orders`
supports state reconciliation, while `POST /orders` returns 403. Do not enable
live submission against that deployment. A separately approved execution-capable
engine must preserve `client_order_id` idempotency and expose the same read-back
surface before using the deterministic execution gateway:

```bash
export ITHACA_ENABLE_LIVE_EXECUTION=1
export ITHACA_IBKR_ORDER_PATH=/orders
export ITHACA_EXECUTION_MAX_NOTIONAL_USD=10000
export ITHACA_EXECUTION_MAX_QUANTITY=10000
export ITHACA_EXECUTION_MAX_FRESHNESS_MS=10000
```

There are three stop layers for new submissions:

1. `ITHACA_EXECUTION_KILL_SWITCH=1` is the deployment-level break-glass stop.
2. The global durable control halts every tenant.
3. A tenant durable control halts only that tenant.

The effective switch is checked during policy evaluation and again after the
durable submission outbox is claimed. The final check and broker call run behind
Postgres advisory fences: tenant changes exclude that tenant's submissions, while
the global control excludes every submission. This makes each broker send orderable
before or after a committed halt instead of leaving a check-to-send gap. Engaging a
switch does not cancel orders already accepted by a broker; reconciliation continues
so their actual state remains visible. Operators must separately cancel working
broker orders when incident policy requires it. To use the environment stop, set the
variable in the deployment environment and rerun the deployment; the deploy script
detects the Secret change and restarts every consuming app pod. Clear it and redeploy
only after the incident is resolved. If the variable is omitted, deploys preserve the
existing Secret value so a routine release cannot silently clear an active environment
halt. Durable control changes are effective immediately and tenant plus global events
appear in the compliance panel audit trail.

Tenant compliance policy changes are also effective immediately. Removing a
restricted name or loosening a limit requires a human principal with
`deploy:paper` and the latest policy version. A policy update does not authorize
or submit an order; subsequent promotion, paper-tick, and execution paths read
the new policy independently at their normal gate boundaries.

If `ITHACA_ENABLE_LIVE_EXECUTION=1` is set without `ITHACA_IBKR_ENGINE_URL`,
`deploy/deploy_services.sh` fails before applying manifests. The gateway still
requires a connected provider row with order/trading capability for live broker
intents, and human submission remains the only path from intent to order. The
gateway persists a `pending_submission` order before contacting the broker; the
conductor then reconciles `submitting`, submitted, and partially-filled orders
from `GET /orders`, with cumulative fill deltas deduplicated by broker identity.
Connection loss or a broker 5xx after send stays `submitting` and is never
blindly retried because the broker outcome may already be real.

If `IBKR_ENGINE_ENABLED=0` and `ITHACA_IBKR_ENGINE_URL` is unset, the trigger
worker still deploys and idles, but active live-data policies will emit provider
errors until an engine URL is configured.

```bash
# Public ingress IP for DNS:
terraform output -raw load_balancer_ip
```

---

## 8. HA / node-failover test (proves reliability-first)

Confirm the always-on plane survives losing a node.

```bash
export KUBECONFIG=/tmp/ithaca.kubeconfig

# 8a. Baseline: app plane has >=2 replicas spread across the 2 paper nodes.
kubectl -n ithaca-gateway get pods -o wide
kubectl -n ithaca-workers get pods -o wide
kubectl get nodes -l pool=paper

# 8b. Cordon + drain ONE paper node (simulate a node failure / DO maintenance).
NODE="$(kubectl get nodes -l pool=paper -o jsonpath='{.items[0].metadata.name}')"
kubectl cordon  "${NODE}"
kubectl drain   "${NODE}" --ignore-daemonsets --delete-emptydir-data --force --grace-period=30

# 8c. At least one app pod stays healthy or reschedules onto the surviving
#     paper node; the LB healthcheck keeps routing to healthy backends.
kubectl -n ithaca-gateway get pods -o wide      # all Running on the other node
kubectl -n ithaca-workers get pods -o wide      # worker may restart once; runs stay durable in Postgres
curl -fsS "http://$(terraform output -raw load_balancer_ip)/healthz" && echo "  <- still 200 OK"

# 8d. DOKS autoscaler / DO replaces the drained node; uncordon to restore HA.
kubectl uncordon "${NODE}"
kubectl get nodes -l pool=paper                    # back to 2 Ready

# 8e. Postgres failover: the Managed PG standby auto-promotes on primary loss.
#     Trigger a managed failover from the console or:
doctl databases pool list <db-id>     # confirm the cluster has a standby node
#   (DO promotes the standby automatically on primary failure; the private DSN
#    host is unchanged, so reconnecting clients land on the new primary.)
```

Pass criteria: during 8b–8c the `/healthz` curl keeps returning 200 and at least
one `ithaca-app` replica stays `Running`. At least one worker pod should also
remain or reschedule; queued/running work remains auditable in Postgres, leased
jobs retry or fail through durable job state, and singleton loops fail over via
`worker_leases`. That is the public node-failover guarantee the
`paper_node_count >= 2` + `lb_size_unit >= 2` + multi-replica app/worker
deployments buy.

---

## 9. Day-2 notes

- **DB restore (PITR):** DO keeps daily backups + WAL. Restore into a NEW cluster
  from a backup via the console or `digitalocean_database_cluster` with a
  `backup_restore { database_name, backup_created_at }` block, then repoint the
  app. (Never restore in-place over the live primary.)
- **Scaling backtests:** the `backtest` pool is reserved for heavier future
  worker profiles and can be selected with `WORKER_NODE_WORKLOAD=backtest`.
  `ithaca-workers` can run multiple replicas: job workers claim work through
  durable job leases, while paper/trigger singleton loops use `worker_leases`.
- **Teardown:** `cd infra/terraform && terraform destroy`. NOTE: the Postgres
  cluster has `prevent_destroy = true` — remove that lifecycle block (or
  `terraform state rm`) deliberately before destroying the DB.

---

## Cost estimate (monthly, HA, CPU-only)

Steady-state baseline (backtest pool at its warm floor of 1 node). Budget is
$500/mo; this stack is reliability-tuned, not cost-tuned.

| Item | Spec | ~$/mo |
|---|---|---|
| DOKS HA control plane | `ha = true` | 40 |
| Backtest pool (warm floor) | `c-4` × 1 (min) | 84 |
| Paper/gateway pool (always-on HA + rollout headroom) | `s-2vcpu-4gb` × 4 | 96 |
| Managed Postgres (HA) | `db-s-2vcpu-4gb`, primary + standby | 120 |
| Container Registry | professional tier | 20 |
| Load Balancer (HA) | `size_unit = 2` | 24 |
| Spaces | bucket + modest storage/egress | 5 |
| VPC / Firewalls | — | 0 |
| **Baseline total** | | **≈ $389/mo** |

Burst: each additional `c-4` backtest node the autoscaler adds is ~$84/mo
prorated by the hours it runs (up to `max_nodes = 8`). Even with one extra
backtest node running continuously (~$84) the total stays ≈ $473/mo, inside the
$500 budget. Backtest nodes are billed only while a node exists, so spiky
backtest load costs far less than the worst case.

> Prices are DigitalOcean list prices as of early 2026 and are estimates; confirm
> against the current DO pricing page. The single remaining step to go live is the
> token (below).

---

## The single remaining step

Put a real DigitalOcean API token in `infra/terraform/.env`
(`DIGITALOCEAN_TOKEN=...` plus the `SPACES_*` keys), then:

```bash
deploy/build_and_push.sh        # image -> DOCR
deploy/apply.sh --apply         # plan, confirm, apply
```

Everything else in this repo is already plan-clean and validated.
