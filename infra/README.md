# infra — Doomberg v2 DigitalOcean topology (Terraform)

Declarative IaC for the deploy layer (MASTER-PLAN §5.7). **Nothing here is applied
by the build, and no credentials are committed.** This directory describes the
target topology so it is reviewable; an operator applies it deliberately with
their own DO token.

```
infra/
└── terraform/
    ├── versions.tf            # pinned providers: digitalocean ~>2.43, kubernetes ~>2.32, random ~>3.6
    ├── providers.tf           # provider wiring (token/keys from env — NO secrets)
    ├── variables.tf           # region / sizes / node counts / deadlines — sensible defaults
    ├── main.tf                # VPC, DOKS + 2 node pools, Managed PG 16, Spaces bucket
    ├── network_policy.tf      # default-deny egress + single allow to the Data Gateway
    ├── jobs.tf                # kubernetes_job (backtest) + kubernetes_cron_job_v1 (paper) SHAPES
    ├── outputs.tf             # kubeconfig (sensitive), db URI (sensitive), bucket, vpc...
    ├── terraform.tfvars.example
    ├── .gitignore             # never commit *.tfstate / *.auto.tfvars / .terraform
    └── manifests/
        ├── backtest-job.yaml             # per-run Job template (control plane renders it)
        ├── paper-tick-cronjob.yaml       # per-deployment CronJob template
        └── networkpolicy-egress-deny.yaml # standalone copy of the egress invariant
```

## Topology

```
                    VPC  (10.20.0.0/20)
  ┌───────────────────────────────────────────────────────────┐
  │  DOKS cluster                                               │
  │   ├─ node pool: backtest   CPU-optimized, autoscale 0 → N   │
  │   │     scale-to-zero · tainted workload=backtest           │
  │   │     hosts per-run backtest Jobs (restartPolicy Never)   │
  │   └─ node pool: paper      small STABLE pool (count = 2)    │
  │         hosts the calendar scheduler + paper-tick CronJobs  │
  │                                                             │
  │   namespace doomberg-workers:                               │
  │     NetworkPolicy default-deny (ingress+egress)             │
  │     + single allow → Data Gateway (doomberg-gateway ns)     │
  │                                                             │
  │  Managed Postgres 16  (RLS system of record, private host)  │
  │  Data Gateway facade  (the ONLY egress target for workers)  │
  └───────────────────────────────────────────────────────────┘
       │                                  │
       ▼                                  ▼
   Spaces bucket (artifacts/logs)     (no public egress from workers)
```

- **VPC** — one private network holds the cluster, Managed Postgres, and the
  Data Gateway facade. The DB firewall allows only the cluster; there is no
  public ingress to Postgres.
- **Node pool `backtest`** — CPU-optimized, `auto_scale = true`, `min_nodes = 0`
  → `max_nodes = N`. Backtests run as K8s **Jobs** (`restartPolicy: Never`,
  `activeDeadlineSeconds` = the aggregate deadline). Tainted `workload=backtest`
  so only backtest Jobs land here and the pool can drain back to **zero**.
- **Node pool `paper`** — small fixed pool (`auto_scale = false`,
  `node_count = 2`). Hosts the market-calendar-aware scheduler + short paper-tick
  Jobs. Intentionally **not** scale-to-zero: the scheduler must persist.
- **Managed Postgres 16** — RLS-enforced system of record. A non-owner app role
  (`doomberg_app`) is provisioned here; `FORCE ROW LEVEL SECURITY` +
  `SET LOCAL app.tenant_id` are applied by the schema migration (out of band).
- **Spaces** — private, versioned bucket for backtest artifacts / logs / blobs.
  A lifecycle rule expires `logs/` after 90 days. Globally-unique name via a
  random suffix.

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

## Cost-control story (scale-to-zero)

The backtest pool autoscales **min 0 → max N**. When no backtest Jobs are
queued, the cluster-autoscaler drains the pool to **zero nodes** and DO bills
nothing for backtest compute. A queued Job that tolerates the `workload=backtest`
taint triggers the autoscaler to add a node, runs to completion (or
`activeDeadlineSeconds` SIGKILL), then the node drains again. The only
always-on compute is the small `paper` pool (2 small nodes) for the scheduler.
Postgres is the smallest single-node tier by default; bump `postgres_node_count`
to add a standby for HA.

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
terraform fmt -check        # formatting (this tree is fmt-clean)
terraform init -backend=false
terraform validate          # type + schema validation, no network/credentials
```

> **Not validated in this environment:** `terraform` is not installed on the
> build machine, so `terraform validate` was not run here. The configuration is
> hand-formatted to `terraform fmt` conventions and uses pinned provider schemas
> (`digitalocean ~> 2.43`, `kubernetes ~> 2.32`, `random ~> 3.6`). Run the
> commands above before applying.

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
  / `live_runner`) match the `doomberg_runtime` interface in INTERFACES.md.
