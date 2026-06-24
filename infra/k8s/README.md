# infra/k8s — Doomberg v2 service manifests (Phase 4 deploy)

Deployment + Service manifests for the always-on plane, rendered by
`deploy/deploy_services.sh` and applied with `kubectl` after the DOKS cluster
exists (see `deploy/RUNBOOK.md`).

The manifests are environment-aware shell templates. `DEPLOY_ENV=prod` keeps the
existing production namespaces and NodePorts; `DEPLOY_ENV=dev` renders into a
separate namespace pair with distinct NodePorts and separate PVCs/secrets.

## Why one pod for rest+control+conductor+trigger+mcp

The platform **system-of-record is SQLite** (`doomberg_platform.Db` →
`sqlite3.connect(DOOMBERG_DB)`), not Postgres. The prod Managed Postgres holds
only the **read-only `archive.*`** reference data (read through `DOOMBERG_ARCHIVE_URL`
/ the `ArchiveGateway`). So for a run created via the control-plane/rest-gateway to
actually execute, the **conductor must see the same SQLite file**.

`app-deployment.yaml` therefore co-locates **rest-gateway + control-plane +
conductor + trigger-engine + mcp-gateway** as containers in ONE pod, sharing the
same RWO PVC-backed SQLite file at `/data/doomberg.db`
(`DOOMBERG_DB=/data/doomberg.db`). A created run is visible to the conductor's
`BacktestWorker`; trigger policies are visible to the trigger engine; MCP API
keys minted through the dashboard are visible to the hosted MCP gateway.

> Single-replica by design: SQLite is single-writer and the PVC is ReadWriteOnce,
> so the always-on app pod is **not** horizontally scaled. Node-level HA still
> holds (2 paper nodes; the pod reschedules onto the survivor), and the PVC keeps
> control-plane state across ordinary pod restarts. Migrating the system-of-record to the
> Managed Postgres (RLS schema) is the documented path to multi-replica HA — see
> the Phase 7 hardening notes. Until then, treat this as paper-prod state.

## Files

- `namespace.yaml`        — gateway + worker namespaces for the selected env.
- `app-deployment.yaml`   — rest-gateway + control-plane + conductor + trigger-engine + mcp-gateway (1 pod, shared SQLite PVC).
- `app-service.yaml`      — NodePort service with env-specific ports.
- `worker-networkpolicy.yaml` — default-deny worker egress plus same-env gateway allow.
- `caddy.yaml`            — public HTTPS routing for prod and dev hostnames.

The `doomberg-db` Secret + the image tag are wired by `deploy/deploy_services.sh`.
Set `DOOMBERG_IBKR_ENGINE_URL` (and optionally `DOOMBERG_IBKR_ENGINE_TOKEN` /
`DOOMBERG_IBKR_QUOTE_PATH`) in the deploy environment to back live trigger quote
evaluation with the user-run IBKR engine. Without a URL, the sidecar stays up but
active live-data trigger evaluations will return provider errors until configured.
