# infra — Doomberg v2 DigitalOcean topology (Terraform)

Declarative IaC for the deploy layer (MASTER-PLAN §5.7). **Nothing here is applied
by the build, and no credentials are committed.** This directory describes the
target topology so it is reviewable; an operator applies it deliberately with
their own DO token.

RELIABILITY-FIRST, HA, **CPU-only** stack (budget is generous — optimized for
uptime, not cost). The end-to-end deploy sequence + node-failover test live in
[`deploy/RUNBOOK.md`](../deploy/RUNBOOK.md).

```
infra/
└── terraform/
    ├── versions.tf            # pinned providers: digitalocean ~>2.43, kubernetes ~>2.32, random ~>3.6
    ├── providers.tf           # provider wiring (token/keys from env — NO secrets)
    ├── variables.tf           # region / sizes / node counts / deadlines — HA defaults + CPU-only validation
    ├── guardrails.tf          # CPU-ONLY GUARDRAIL — fails the plan on any GPU/inference size slug
    ├── main.tf                # VPC, HA DOKS + 2 node pools, HA Managed PG 16, Spaces bucket
    ├── registry.tf            # Container Registry (DOCR) — the single multi-service image
    ├── loadbalancer.tf        # public HA Load Balancer → always-on gateway pool
    ├── network_policy.tf      # default-deny egress + single allow to the Data Gateway
    ├── jobs.tf                # backtest Job + paper CronJob + one-shot archive-load Job SHAPES
    ├── outputs.tf             # kubeconfig, db DSN, archive DSN (sensitive), registry endpoint, LB IP...
    ├── terraform.tfvars.example
    ├── .env.example           # DIGITALOCEAN_TOKEN + SPACES_* (gitignored .env)
    ├── .gitignore             # never commit *.tfstate / *.auto.tfvars / .terraform
    └── manifests/
        ├── backtest-job.yaml             # per-run Job template (control plane renders it)
        ├── paper-tick-cronjob.yaml       # per-deployment CronJob template
        ├── archive-load-job.yaml         # one-shot loader: seeds archive.* on first deploy
        └── networkpolicy-egress-deny.yaml # standalone copy of the egress invariant
```

Build/deploy tooling lives in [`deploy/`](../deploy/): `build_and_push.sh`
(image → DOCR), `apply.sh` (init/validate/plan; apply only behind `--apply`),
`entrypoint.sh` (role dispatcher baked into the image), and `RUNBOOK.md`.

## Topology

```
                         Load Balancer (HA, size_unit=2)  ← public ingress
                                    │
                    VPC  (10.20.0.0/20)
  ┌───────────────────────────────────────────────────────────┐
  │  DOKS cluster  (HA control plane)                           │
  │   ├─ node pool: backtest   CPU-optimized, autoscale 1 → 8   │
  │   │     WARM floor (min 1, no cold start) · workload=backtest│
  │   │     hosts per-run backtest Jobs (restartPolicy Never)   │
  │   └─ node pool: paper      ALWAYS-ON HA pool (count = 2)    │
  │         gateways (2+ replicas each) + calendar scheduler +  │
  │         paper-tick CronJobs                                 │
  │                                                             │
  │   namespace doomberg-workers:                               │
  │     NetworkPolicy default-deny (ingress+egress)             │
  │     + single allow → Data Gateway (doomberg-gateway ns)     │
  │   namespace doomberg-gateway: gateways + one-shot archive-load│
  │                                                             │
  │  Managed Postgres 16  (primary + standby HA, private host,  │
  │                        daily backups + WAL/PITR)            │
  │  Data Gateway facade  (the ONLY egress target for workers)  │
  └───────────────────────────────────────────────────────────┘
       │                       │                    │
       ▼                       ▼                    ▼
   Container Registry      Spaces bucket        (no public egress
   (the image)            (artifacts/logs)       from workers)
```

- **VPC** — one private network holds the cluster, Managed Postgres, and the
  Data Gateway facade. The DB firewall allows only the cluster; there is no
  public ingress to Postgres.
- **DOKS** — `ha = true` (redundant API server) and `registry_integration = true`
  (pulls the private image without per-Deployment imagePullSecrets).
- **Node pool `backtest`** — CPU-optimized, `auto_scale = true`, **`min_nodes = 1`
  (warm) → `max_nodes = 8`**. RELIABILITY-FIRST: a queued backtest never pays the
  cold node-provision latency; the autoscaler bursts under load and drains back
  to the warm floor. Backtests run as K8s **Jobs** (`restartPolicy: Never`,
  `activeDeadlineSeconds` = the aggregate deadline), tainted `workload=backtest`.
- **Node pool `paper`** — the **always-on HA pool** (`auto_scale = false`,
  `node_count = 2`, ≥2 for node-failover safety). Hosts the gateways (mcp-gateway
  + rest-gateway + control-plane, 2+ replicas each via the k8s manifests), the
  market-calendar-aware scheduler, and short paper-tick Jobs. Tagged so the public
  LB targets it.
- **Managed Postgres 16** — RLS-enforced system of record, **`node_count = 2`
  (primary + standby, automatic failover)**, daily automated backups + WAL for
  point-in-time restore, storage autoscale. A non-owner app role (`doomberg_app`)
  is provisioned here; `FORCE ROW LEVEL SECURITY` + `SET LOCAL app.tenant_id` are
  applied by the schema migration (out of band).
- **Container Registry (DOCR)** — holds the single multi-service image every
  service runs from (role chosen by `entrypoint.sh`).
- **Load Balancer** — HA (`size_unit = 2`), public ingress to the always-on
  gateway pool with a `/healthz` healthcheck for fast unhealthy-node eviction.
- **Spaces** — private, versioned bucket for backtest artifacts / logs / blobs +
  the one-time `v1_archive.json` seed. A lifecycle rule expires `logs/` after 90
  days. Globally-unique name via a random suffix.

## CPU-ONLY GUARDRAIL

`guardrails.tf` + per-variable `validation` blocks **fail `terraform plan`** if any
node or database size slug is a GPU / inference family (`gpu-*`, `gd-*`, `p-*`, or
any non-`db-` Postgres slug). The **allowlist** is exactly: DOKS CPU node pools
(`s-*`/`c-*`/`g-*`/`gd-*` general/`m-*`), Managed Postgres (`db-*`), Spaces,
Container Registry, Load Balancer, VPC, Firewalls. NEVER GPU Droplets, NVIDIA H100
GPU Kubernetes, Bare Metal GPUs, Dedicated/Serverless Inference, Paperspace,
Cloudways, or any third-party pass-through. The guardrail is exercised in CI
(`.github/workflows/deploy-checks.yml`): a `gpu-*` slug must turn the plan red.

## What is intentionally NOT applied

Everything. This is a `terraform plan`-able, reviewable description — not a live
stack. Specifically:

- No `terraform apply` is run by the build, and **no DO API token / Spaces keys
  exist in this repo.** They are supplied at apply time via `DIGITALOCEAN_TOKEN`,
  `SPACES_ACCESS_KEY_ID`, `SPACES_SECRET_ACCESS_KEY`.
- `kubernetes_job.backtest_template` and `kubernetes_cron_job_v1.paper_tick` have
  `count = 0` — they are **typed, validated reference shapes**, not long-lived
  resources. The control plane renders the real per-run Job / per-deployment
  CronJob from the YAML templates in `manifests/` (one Job per `run_id`, spawned
  fresh, killed at completion).
- State files, lock files, and `*.auto.tfvars` are gitignored — `*.tfstate`
  carries the rendered DB URI and kubeconfig, so it must never be committed.

## Reliability-first story (warm floor + HA, not scale-to-zero)

Budget is generous (~$500/mo), so this stack trades idle cost for uptime and
predictable latency:

- The backtest pool keeps a **warm floor** (`min_nodes = 1`) so the *first*
  queued backtest never waits on a cold node provision; it bursts to
  `max_nodes = 8` under load and drains back to the floor.
- The `paper`/gateway pool and Managed Postgres are **HA by default** (≥2 nodes
  each — primary + standby for PG, two gateway nodes), and the LB is `size_unit
  = 2`. A single node failure does not take the always-on plane down (see the
  node-failover test in `deploy/RUNBOOK.md`).
- Full monthly cost breakdown is in `deploy/RUNBOOK.md` (baseline ≈ $389/mo).

## Sandboxing decision — plain containers + cgroups + NetworkPolicy; microVM deferred

Per MASTER-PLAN §5.2/§5.7 and feasibility critique #2: **no untrusted code runs
in v2.0.** Strategies are declarative `StrategySpec` data we validate; the worker
executes *our own trusted numpy* over that data. So the launch sandbox is:

- **Plain containers** with **cgroup limits** (CPU/memory `requests`/`limits` on
  every container).
- **`activeDeadlineSeconds`** = the aggregate wall-clock deadline (SIGKILL on
  breach) — the v1 "no aggregate budget" lesson, encoded in the Job spec.
- A **default-deny egress NetworkPolicy** with a single allow to the Data
  Gateway facade — a cluster invariant, not application code. Workers have no
  public egress and reach data only through the Gateway (`asOf` truncation,
  provenance, breakers all live there).
- Hardened pod security: `runAsNonRoot`, `readOnlyRootFilesystem`,
  `allowPrivilegeEscalation: false`, `capabilities: drop [ALL]`,
  `automountServiceAccountToken: false`, `seccompProfile: RuntimeDefault`.

We deliberately **do NOT** build a gVisor/Kata/microVM fleet at launch — it is a
fraction of the value when there is no untrusted code, and a large fraction of
the work. The microVM sandbox is **deferred to the phase that ships
`CustomPythonNode`** (the operator-DAG escape hatch), gated on a spike proving
the runtime works on DOKS. We do not run a microVM to execute numpy we wrote.

## Validating

```bash
cd infra/terraform
terraform fmt -check -recursive   # formatting (this tree is fmt-clean)
terraform init -backend=false
terraform validate                # type + schema validation, no network/credentials
```

> **Validated:** `terraform fmt -check -recursive` and `terraform validate` both
> PASS against the real providers (digitalocean v2.90.0, kubernetes v2.38.0,
> random v3.9.0) downloaded by `terraform init`. The CPU-ONLY GUARDRAIL and the
> HA validations were exercised by feeding GPU slugs / single-node settings to
> `terraform plan` — they correctly fail the plan with the guardrail message
> (the only credentialed step, the k8s-versions data source, returns the expected
> 401 with no token; the config itself is plan-clean). CI mirrors this in
> `.github/workflows/deploy-checks.yml`.

## Hand-off to the integrator

- The control plane must render `manifests/backtest-job.yaml` per `run_id`
  (substitute `${RUN_ID}`, `${TENANT_ID}`, `${ACTIVE_DEADLINE_SECONDS}`,
  `${WORKER_IMAGE}`) and create it in namespace `doomberg-workers`.
- The scheduler renders `manifests/paper-tick-cronjob.yaml` per paper deployment.
- Worker pods MUST carry label `doomberg/component=worker` or the egress
  NetworkPolicy will (correctly) deny all traffic.
- The Data Gateway Service must run in namespace `doomberg-gateway` with label
  `doomberg/role=data-gateway` on the namespace and
  `doomberg/component=data-gateway` on the pods, listening on `data_gateway_port`
  (default 8080).
- Apply the RLS schema migration against the `postgres_app_uri` (sensitive
  output) using the `doomberg_app` non-owner role.
- The worker container entrypoints (`python -m doomberg_runtime.backtest_runner`
  / `live_runner`) match the `doomberg_runtime` interface in INTERFACES.md, and
  are also reachable as roles of the single image via `deploy/entrypoint.sh`.
- **Archive seed:** the one-shot `archive-load` Job (`jobs.tf` /
  `manifests/archive-load-job.yaml`, gated by `enable_archive_load_job`) runs
  Stream 1's loader `python scripts/import_v1_archive.py` against the Managed PG
  to create + populate `archive.*` on first deploy. It reads `DOOMBERG_ARCHIVE_URL`
  from the `doomberg-db` Secret and the `v1_archive.json` export from Spaces. Set
  `enable_archive_load_job = false` after a successful load.
- **Gateways:** deploy mcp-gateway / rest-gateway / control-plane to
  `doomberg-gateway` with **2+ replicas each** on the `paper` pool; publish
  NodePorts `30080` (rest) + `30808` (mcp) for the `loadbalancer.tf` forwarding
  rules + `/healthz` healthcheck. Point DNS at the `load_balancer_ip` output.
- **Image:** build + push with `deploy/build_and_push.sh` to the DOCR
  (`registry_endpoint` output); the cluster pulls it via `registry_integration`.
