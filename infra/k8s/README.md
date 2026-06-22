# infra/k8s — Doomberg v2 service manifests (Phase 4 deploy)

Deployment + Service manifests for the always-on plane, rendered by
`deploy/deploy_services.sh` and applied with `kubectl` after the DOKS cluster
exists (see `deploy/RUNBOOK.md`).

The manifests are environment-aware shell templates. `DEPLOY_ENV=prod` keeps the
existing production namespaces and NodePorts; `DEPLOY_ENV=dev` renders into a
separate namespace pair with distinct NodePorts and separate PVCs/secrets.

## Why one pod for rest+control+conductor

The platform **system-of-record is SQLite** (`doomberg_platform.Db` →
`sqlite3.connect(DOOMBERG_DB)`), not Postgres. The prod Managed Postgres holds
only the **read-only `archive.*`** reference data (read through `DOOMBERG_ARCHIVE_URL`
/ the `ArchiveGateway`). So for a run created via the control-plane/rest-gateway to
actually execute, the **conductor must see the same SQLite file**.

`app-deployment.yaml` therefore co-locates **rest-gateway + control-plane +
conductor** as three containers in ONE pod, sharing an `emptyDir`-backed SQLite
file at `/data/doomberg.db` (`DOOMBERG_DB=/data/doomberg.db`). A created run is
visible to the conductor's `BacktestWorker`, which runs it to `succeeded`.

> Single-replica by design: SQLite is single-writer and an `emptyDir` is
> pod-local, so the always-on app pod is **not** horizontally scaled. Node-level
> HA still holds (2 paper nodes; the pod reschedules onto the survivor), but the
> in-flight SQLite state is ephemeral. Migrating the system-of-record to the
> Managed Postgres (RLS schema) is the documented path to multi-replica HA — see
> the Phase 7 hardening notes. Until then, treat this as paper-prod state.

## Files

- `namespace.yaml`        — gateway + worker namespaces for the selected env.
- `app-deployment.yaml`   — rest-gateway + control-plane + conductor (1 pod, shared SQLite).
- `app-service.yaml`      — NodePort service with env-specific ports.
- `worker-networkpolicy.yaml` — default-deny worker egress plus same-env gateway allow.
- `caddy.yaml`            — public HTTPS routing for prod and dev hostnames.
- `mcp-deployment.yaml`   — legacy standalone MCP deployment. It is no longer applied by the standard deploy path; hosted MCP is the `mcp-gateway` container inside `doomberg-app`.

The `doomberg-db` Secret + the image tag are wired by `deploy/deploy_services.sh`.
