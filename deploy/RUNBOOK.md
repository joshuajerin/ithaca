# Doomberg v2 — DigitalOcean deploy RUNBOOK

Reliability-first, HA, **CPU-only** stack on DOKS. This is the full one-command-ish
sequence to take the repo from "apply-ready Terraform" to a running paper-prod
cluster, plus the node-failover test that proves HA.

## GitHub-controlled deploys

The normal deploy path is now GitHub Actions:

| Branch | Environment | Kubernetes namespaces | Public hosts |
|---|---|---|---|
| `main` | `prod` | `doomberg-gateway`, `doomberg-workers` | `app.doomberg.me`, `mcp.doomberg.me` |
| any other same-repo branch | `dev` | `doomberg-dev-gateway`, `doomberg-dev-workers` | `dev-app.doomberg.me`, `dev-mcp.doomberg.me` |

Prod app and active worker pods default to the `paper` node pool. Dev app and
worker pods default to the tainted `backtest` pool so dev does not compete with
prod for the current paper node; override with `APP_NODE_WORKLOAD` or
`WORKER_NODE_WORKLOAD` if the cluster topology changes. Prod app replicas
default to `2`; active worker replicas default to `1`.

`deploy-do.yml` builds an immutable DOCR image from the checked-out SHA, deploys only
that tag, and moves `latest` only after a successful prod rollout. The prod job also
verifies that the deploying SHA still equals `origin/main`.

Each GitHub environment owns its own secrets and variables. Required secrets are
`DIGITALOCEAN_ACCESS_TOKEN`, `DOOMBERG_ARCHIVE_URL`, `DOOMBERG_SESSION_SECRET`,
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `OAUTH_GITHUB_CLIENT_ID`,
`OAUTH_GITHUB_CLIENT_SECRET`, and `DOOMBERG_ADMIN_TOKEN`. Optional secrets include
`FMP_API_KEY` and `DOOMBERG_SMOKE_API_KEY`.

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
> reads the prod DB via the `DOOMBERG_PROD_URL` secret), `manage_spaces=false` (no
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
login`, and pushes to `registry.digitalocean.com/doomberg/doomberg:<tag>`.
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
| node pool `paper` (always-on) | `s-4vcpu-8gb` × **2** (HA) — gateways + scheduler |
| Managed Postgres 16 | `db-s-2vcpu-4gb`, **2 nodes = primary + standby (HA)**, daily backups + WAL/PITR, storage autoscale |
| Container Registry | `doomberg`, professional tier |
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
terraform output -raw kubeconfig > /tmp/doomberg.kubeconfig
export KUBECONFIG=/tmp/doomberg.kubeconfig
kubectl get nodes        # expect 1 backtest (warm) + 2 paper nodes Ready

# DB DSN secret (used by gateways, control-plane, runtime, and the archive loader).
# platform_url is the platform system-of-record; archive_url is the read-only archive.
APP_URI="$(terraform output -raw postgres_app_uri)"
ARCHIVE_URI="$(terraform output -raw archive_url)"
kubectl create namespace doomberg-gateway --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace doomberg-workers --dry-run=client -o yaml | kubectl apply -f -
kubectl -n doomberg-gateway create secret generic doomberg-db \
  --from-literal=db_url="${APP_URI}" \
  --from-literal=platform_url="${APP_URI}" \
  --from-literal=archive_url="${ARCHIVE_URI}"
kubectl -n doomberg-workers create secret generic doomberg-db \
  --from-literal=db_url="${APP_URI}" \
  --from-literal=platform_url="${APP_URI}" \
  --from-literal=archive_url="${ARCHIVE_URI}"
```

> `deploy/deploy_services.sh` creates/updates the full `doomberg-db` Secret in
> both namespaces, including OAuth/session/IBKR/execution keys. The manual
> commands above are only for a minimal bootstrap or break-glass path. The DB
> firewall already restricts Postgres to the cluster.

---

## 5. Apply the platform schema

`deploy/deploy_services.sh` runs the `platform-migrate` init container before
the API/worker containers start. The same idempotent schema migration also runs
when a platform process opens `DOOMBERG_DB`, so ordinary restarts self-heal.

Optional RLS policies can be installed by setting `DOOMBERG_POSTGRES_ENABLE_RLS=1`
for the migration role. Do not set `DOOMBERG_POSTGRES_FORCE_RLS=1` until the
per-service DB role split is complete, because the conductor and auth resolver
currently perform legitimate cross-tenant infrastructure reads.

---

## 6. Seed `archive.*` (one-shot loader Job)

First, upload the ~92 MB `data/v1_archive.json` export to the Spaces artifacts
bucket once (it is intentionally NOT baked into the image):

```bash
BUCKET="$(terraform output -raw spaces_bucket_name)"
# (using s3cmd/aws-cli configured with your SPACES_* keys, region from var.region)
aws s3 cp data/v1_archive.json "s3://${BUCKET}/seed/v1_archive.json" \
  --endpoint-url "https://$(terraform output -raw region 2>/dev/null || echo nyc3).digitaloceanspaces.com"
```

Then run the loader. Terraform renders the Job from `enable_archive_load_job`
(default `true`) — it runs on apply. To run/re-run it by hand:

```bash
# Render the manifest's placeholders and apply it:
sed -e "s|\${ARCHIVE_LOADER_IMAGE}|registry.digitalocean.com/doomberg/doomberg:latest|" \
    -e "s|\${ARCHIVE_LOADER_ACTIVE_DEADLINE_SECONDS}|3600|" \
    -e "s|\${ARCHIVE_SRC}|s3://${BUCKET}/seed/v1_archive.json|" \
    infra/terraform/manifests/archive-load-job.yaml | kubectl apply -f -

kubectl -n doomberg-gateway wait --for=condition=complete job/archive-load --timeout=1h
kubectl -n doomberg-gateway logs job/archive-load
```

The loader (`scripts/import_v1_archive.py`, owned by the data-archive stream)
creates the `archive.*` schema and bulk-loads the 15 market-data tables
(~240k rows). After a successful load, set `enable_archive_load_job = false` so
re-applies don't re-seed.

---

## 7. Deploy the services

Deploy the always-on planes with `deploy/deploy_services.sh`. The current
runtime topology has two deployments:

`doomberg-app` in the gateway namespace:

- `rest-gateway`
- `control-plane`
- `mcp-gateway`

`doomberg-workers` in the worker namespace:

- `conductor` (`BacktestWorker`, trigger-job worker, and paper scheduler)
- `trigger-engine` (active trigger policy polling)

Both deployments intentionally share the managed Postgres platform store through
`DOOMBERG_DB=doomberg-db.platform_url`; no SQLite PVC is mounted in the normal
deploy path. NodePorts stay `30080` (rest/app) and `30808` (MCP), matching the
load balancer rules in Terraform. The service manifest, worker network policy,
both `doomberg-db` Secrets, and replica counts are rendered/applied by
`deploy/deploy_services.sh`.

Keep `WORKER_REPLICAS=1` until the paper scheduler and trigger polling have
explicit leader leases. Durable backtest and trigger-analysis job claiming uses
Postgres worker leases, but those always-on loops are still active pollers.

For connected-account live trigger quotes, set:

```bash
export DOOMBERG_IBKR_ENGINE_URL=https://your-ibkr-vps.example.com
export DOOMBERG_IBKR_ENGINE_TOKEN=...        # optional
export DOOMBERG_IBKR_QUOTE_PATH=/quote?symbol={symbol}  # optional
```

For live broker submission through the deterministic execution gateway, set the
same engine URL plus the explicit live-execution switch and limits:

```bash
export DOOMBERG_ENABLE_LIVE_EXECUTION=1
export DOOMBERG_IBKR_ORDER_PATH=/orders
export DOOMBERG_EXECUTION_MAX_NOTIONAL_USD=10000
export DOOMBERG_EXECUTION_MAX_QUANTITY=10000
export DOOMBERG_EXECUTION_MAX_FRESHNESS_MS=10000
```

If `DOOMBERG_ENABLE_LIVE_EXECUTION=1` is set without `DOOMBERG_IBKR_ENGINE_URL`,
`deploy/deploy_services.sh` fails before applying manifests. The gateway still
requires a connected provider row with order/trading capability for live broker
intents, and human submission remains the only path from intent to order.

If `DOOMBERG_IBKR_ENGINE_URL` is unset, the trigger worker still deploys and
idles, but active live-data policies will emit provider errors until the VPS URL
is configured.

```bash
# Public ingress IP for DNS:
terraform output -raw load_balancer_ip
```

---

## 8. HA / node-failover test (proves reliability-first)

Confirm the always-on plane survives losing a node.

```bash
export KUBECONFIG=/tmp/doomberg.kubeconfig

# 8a. Baseline: app plane has >=2 replicas spread across the 2 paper nodes.
kubectl -n doomberg-gateway get pods -o wide
kubectl -n doomberg-workers get pods -o wide
kubectl get nodes -l pool=paper

# 8b. Cordon + drain ONE paper node (simulate a node failure / DO maintenance).
NODE="$(kubectl get nodes -l pool=paper -o jsonpath='{.items[0].metadata.name}')"
kubectl cordon  "${NODE}"
kubectl drain   "${NODE}" --ignore-daemonsets --delete-emptydir-data --force --grace-period=30

# 8c. At least one app pod stays healthy or reschedules onto the surviving
#     paper node; the LB healthcheck keeps routing to healthy backends.
kubectl -n doomberg-gateway get pods -o wide      # all Running on the other node
kubectl -n doomberg-workers get pods -o wide      # worker may restart once; runs stay durable in Postgres
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
one `doomberg-app` replica stays `Running`. The single active worker may restart
on the surviving node; queued/running work remains auditable in Postgres and
leased jobs retry or fail through the durable job state. That is the public
node-failover guarantee the `paper_node_count >= 2` + `lb_size_unit >= 2` +
multi-replica app deployment buys.

---

## 9. Day-2 notes

- **DB restore (PITR):** DO keeps daily backups + WAL. Restore into a NEW cluster
  from a backup via the console or `digitalocean_database_cluster` with a
  `backup_restore { database_name, backup_created_at }` block, then repoint the
  app. (Never restore in-place over the live primary.)
- **Scaling backtests:** the `backtest` pool is reserved for heavier future
  worker profiles and can be selected with `WORKER_NODE_WORKLOAD=backtest`.
  Keep the always-on `doomberg-workers` deployment at one replica until worker
  leader leases are added; job leasing is durable, but paper/trigger pollers are
  intentionally single-active today.
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
| Paper/gateway pool (always-on HA) | `s-4vcpu-8gb` × 2 | 96 |
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
