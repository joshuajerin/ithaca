# IBKR Engine Customer Handoff Plan

Status: implemented and deployed for the first read-only customer handoff.

Current production state:

- IBKR Client Portal Gateway runs as the dedicated `ibkr-gateway` Deployment.
- The normalized Ithaca wrapper runs separately as `ibkr-engine`.
- App, worker, REST, MCP, and trigger paths use the internal `ibkr-engine`
  ClusterIP service.
- The temporary public sign-in route is closed after authentication.
- `ibkr-smoke` and the authenticated HTTP launch gate pass against production.

The historical investigation and target design are retained below for context.

## Goal

Give a customer a real IBKR sign-in link, run the IBKR engine on Ithaca's DigitalOcean infrastructure, and pipe fresh IBKR market data through Ithaca so dashboard, MCP, launch-gate, and trigger-engine can use the same real-time quote source.

Default scope for the first customer handoff is read-only realtime data: quotes, accounts, positions, and order-history reads. Live order submission should stay disabled unless explicitly enabled after the data path is proven.

Security requirement: the customer-facing IBKR sign-in URL is temporary. After the customer signs in and the cluster confirms an authenticated IBKR session, the public route must be removed or locked down so only the Ithaca cluster can reach the IBKR gateway/API.

## Current-State Findings

### Live infrastructure

- The active kubectl context is `do-nyc3-ithaca-prod-doks`.
- The live production ingress is a Caddy LoadBalancer at `129.212.135.120`.
- `app.tradeithaca.com` and `mcp.tradeithaca.com` currently resolve to `129.212.135.120`.
- `ibkr.tradeithaca.com` does not currently resolve.
- The DNS zone is not manageable with the available DigitalOcean token: `doctl compute domain records list tradeithaca.com` returns a 404. The domain nameservers are `dns1.registrar-servers.com` and `dns2.registrar-servers.com`, so the `ibkr.tradeithaca.com` DNS record likely has to be added at the registrar/DNS provider, not through DO.

### Live Kubernetes drift

Live prod does not match the current repo deployment shape:

- `ithaca-gateway` currently runs one `ithaca-app` deployment with five containers: `rest-gateway`, `control-plane`, `conductor`, `trigger-engine`, and `mcp-gateway`.
- `ithaca-workers` has only the registry pull secret and no worker deployment.
- Live containers still use `ITHACA_DB=/data/ithaca.db`.
- Live `ithaca-db` secret already has keys for `ibkr_engine_url`, `ibkr_engine_token`, and `ibkr_quote_path`.
- Live env wiring sends IBKR only to `trigger-engine`; `rest-gateway`, `control-plane`, and `mcp-gateway` do not receive IBKR env.

This means the live cluster is still serving an older single-pod SQLite topology. Before a customer handoff, the deployment needs to be realigned with the current repo manifests and Postgres-backed split app/worker design.

### Repo support that already exists

- `ithaca-core/src/ithaca_core/providers/ibkr_engine.py` already defines the Ithaca-side IBKR engine client.
- It reads:
  - `ITHACA_IBKR_ENGINE_URL`
  - `ITHACA_IBKR_ENGINE_TOKEN`
  - `ITHACA_IBKR_QUOTE_PATH`
  - `ITHACA_IBKR_ORDER_PATH`
  - `ITHACA_IBKR_ACCOUNTS_PATH`
  - `ITHACA_IBKR_POSITIONS_PATH`
  - `ITHACA_IBKR_ORDERS_PATH`
- The normalized quote contract includes `symbol`, `price`, `bid`, `ask`, `source`, `source_account`, `entitlement_class`, `event_time`, `received_time`, `freshness_ms`, and `quality_flags`.
- `scripts/ibkr_smoke.py` already tests the external engine contract and freshness.
- `services/runtime/src/ithaca_runtime/trigger_engine.py` uses `IbkrEngineClient` for live-data trigger quotes and errors cleanly if `ITHACA_IBKR_ENGINE_URL` is unset.
- `services/mcp-gateway/src/ithaca_mcp/server.py` already exposes `market.quote`, broker read tools, and `ibkr_smoke` against `IbkrEngineClient`.
- `services/control-plane/src/ithaca_control/execution_gateway.py` has live IBKR execution support, but requires `ITHACA_ENABLE_LIVE_EXECUTION=1`, provider configuration, human submit, and execution gates.

### Repo gaps

- There is no Ithaca-owned IBKR engine service in the repo yet. The current code assumes an external user-run engine.
- There is no container/image for IBKR Client Portal Gateway or for a Ithaca wrapper around it.
- `infra/k8s/caddy.yaml` only routes `app.tradeithaca.com`, `mcp.tradeithaca.com`, and dev equivalents. There is no `ibkr.tradeithaca.com` route.
- `.github/workflows/deploy-do.yml` passes only `ITHACA_IBKR_ENGINE_URL`, `ITHACA_IBKR_ENGINE_TOKEN`, and `ITHACA_IBKR_QUOTE_PATH`; it does not pass live execution flags or read endpoint path overrides.
- There are local uncommitted changes in `.env.example`, `deploy/deploy_services.sh`, `infra/k8s/README.md`, and `infra/k8s/app-deployment.yaml` from the earlier IBKR env propagation work. Keep or reconcile those changes during implementation; do not overwrite them.

### External-doc status

The repo instruction says to use the gstack `/browse` skill for web browsing. The browse skill is not set up in this workspace, so the exact current IBKR Client Portal Gateway download/install/login endpoint must be verified during implementation before exposing the final login path. Do not hard-code an unverified IBKR login URL.

## Target Design

### Deployment model

Run a managed IBKR engine deployment on the existing DO/DOKS production cluster, not as an untracked SSH process on a random VPS.

Recommended placement:

- Namespace: `ithaca-gateway` for the first rollout, because Caddy already lives there and can route the customer sign-in endpoint internally.
- Deployment: `ibkr-engine`.
- Service: `ibkr-engine`.
- PersistentVolumeClaim: stores IBKR gateway session/config state so pod restarts do not force needless setup.
- Internal API URL for Ithaca: `http://ibkr-engine.ithaca-gateway.svc.cluster.local:<wrapper-port>`.
- Temporary public sign-in URL for the customer: `https://ibkr.tradeithaca.com/<verified-ibkr-login-path>`.

The public route should expose only the IBKR login/session UI needed for the customer to authenticate, and only during the sign-in window. Once `/auth/status` confirms an authenticated session, remove the `ibkr.tradeithaca.com` route from Caddy or switch it to an operator-only allowlist. The normalized Ithaca API should stay internal to the cluster and require `Authorization: Bearer $ITHACA_IBKR_ENGINE_TOKEN`.

### Containers

Use two cooperating containers in the `ibkr-engine` pod:

- `ibkr-client-portal-gateway`: official IBKR Client Portal Gateway runtime, with Java/runtime dependencies and persisted session/config volume.
- `ithaca-ibkr-engine`: small Ithaca wrapper service that talks to the gateway locally and exposes the normalized API Ithaca already expects.

Use a separate `Dockerfile.ibkr-engine` or equivalent build path so the main Ithaca image does not absorb Java and IBKR gateway dependencies.

### API contract

The wrapper service should implement:

- `GET /healthz`: process health plus upstream IBKR gateway reachability.
- `GET /auth/status`: signed-in/session status, account IDs if available, and reauth-required flag.
- `GET /quote?symbol=AAPL`: returns the normalized quote contract used by `IbkrEngineClient`.
- `GET /accounts`: returns accounts in the normalized envelope expected by MCP broker tools.
- `GET /positions?account=<account>`: returns positions.
- `GET /orders?account=<account>`: returns order history/open orders.
- `POST /orders`: present but disabled unless `ITHACA_ENABLE_LIVE_EXECUTION=1`; return an explicit disabled error otherwise.

Auth:

- All normalized API routes require `Authorization: Bearer <engine token>`.
- The public IBKR login route should not expose the wrapper API.
- Protect `ibkr.tradeithaca.com` with Caddy basic auth or IP allowlist while it is temporarily open for customer sign-in.
- After sign-in, remove the public route entirely or restrict it to operator IPs only; normal Ithaca usage must flow through the cluster-internal `ibkr-engine` service.

### Ithaca integration

Set prod app/worker secrets to:

- `ITHACA_IBKR_ENGINE_URL=http://ibkr-engine.ithaca-gateway.svc.cluster.local:<wrapper-port>`
- `ITHACA_IBKR_ENGINE_TOKEN=<generated high-entropy token>`
- `ITHACA_IBKR_QUOTE_PATH=/quote?symbol={symbol}`
- `ITHACA_IBKR_ACCOUNTS_PATH=/accounts`
- `ITHACA_IBKR_POSITIONS_PATH=/positions?account={account}`
- `ITHACA_IBKR_ORDERS_PATH=/orders?account={account}`
- `ITHACA_ENABLE_LIVE_EXECUTION=0` for the first handoff

After the customer signs in, create or update the IBKR provider connection row for the target tenant so the UI/control-plane understands the broker is connected. The provider should advertise read capabilities first; execution capability should be added only when live trading is deliberately enabled.

## Concrete Changes

1. Add the IBKR engine wrapper package.
   - `services/ibkr-engine/pyproject.toml`
   - `services/ibkr-engine/src/ithaca_ibkr_engine/app.py`
   - `services/ibkr-engine/src/ithaca_ibkr_engine/client_portal.py`
   - `services/ibkr-engine/tests/test_app.py`
   - Root workspace updates in `pyproject.toml` and `uv.lock`.

2. Add a separate IBKR engine image build.
   - `Dockerfile.ibkr-engine`
   - `deploy/build_ibkr_engine.sh`
   - Verify the official IBKR Client Portal Gateway install/download source before writing this image.

3. Add Kubernetes manifests.
   - `infra/k8s/ibkr-engine.yaml` for deployment, service, PVC, probes, and env.
   - `infra/k8s/ibkr-network-policy.yaml` to keep the wrapper API reachable only from the Ithaca app/workers and, during the temporary sign-in window, from Caddy to the IBKR login port.
   - Add `ibkr.tradeithaca.com` reverse proxy handling to `infra/k8s/caddy.yaml` behind an explicit temporary sign-in flag.
   - Add the post-sign-in Caddy state where `ibkr.tradeithaca.com` is absent or operator-only.

4. Extend deploy secret and manifest application.
   - Update `deploy/deploy_services.sh` to create/update IBKR engine secrets and apply the new manifests.
   - Keep the existing `ithaca-db` secret keys for the app/worker consumers.
   - Pass all IBKR path override env vars through the GitHub workflow if deploys continue to run through `.github/workflows/deploy-do.yml`.

5. Realign production manifests.
   - Apply the current app/worker split, not only an image update.
   - Confirm `ithaca-app` uses Postgres via `ithaca-db.platform_url`.
   - Confirm `ithaca-workers` has the conductor/trigger deployment.
   - Confirm IBKR env reaches `rest-gateway`, `control-plane`, `mcp-gateway`, and `trigger-engine`.

6. Add DNS for customer sign-in.
   - Add `ibkr.tradeithaca.com -> 129.212.135.120` at the registrar/DNS provider because the available DO token cannot manage the `tradeithaca.com` zone.
   - If DNS access is unavailable, use a temporary Caddy host under an already controllable domain or the raw LB only as a last resort; the normal customer link should be TLS-backed under `ibkr.tradeithaca.com`.

7. Update runbook.
   - Document the customer sign-in sequence.
   - Document how to check auth/session status.
   - Document reauth behavior and the exact smoke commands.
   - Document that Ithaca does not store the customer's IBKR password.

## Implementation Sequence

1. Verify current IBKR Client Portal Gateway packaging and login flow using official docs.
2. Build the wrapper service locally with mocked gateway responses.
3. Build/push the separate IBKR engine image to DOCR.
4. Apply the IBKR engine manifests to prod.
5. Apply the full current Ithaca app/worker manifests to eliminate live drift.
6. Add DNS for `ibkr.tradeithaca.com`.
7. Wait for TLS and route health.
8. Give the customer the verified sign-in link.
9. After customer login, run IBKR smoke checks from inside the cluster.
10. Remove or lock down the public `ibkr.tradeithaca.com` route.
11. Re-run an internal cluster smoke check to confirm Ithaca still reaches `ibkr-engine` without the public route.
12. Create/update the Ithaca provider connection for the tenant.
13. Run launch-gate with IBKR required.

## Verification Commands

Static and unit checks:

```bash
bash -n deploy/deploy_services.sh deploy/build_ibkr_engine.sh deploy/entrypoint.sh
python - <<'PY'
import pathlib, yaml
for path in pathlib.Path("infra/k8s").glob("*.yaml"):
    list(yaml.safe_load_all(path.read_text()))
PY
uv run --package ithaca-core pytest ithaca-core/tests/test_ibkr_engine.py -q
uv run --package ithaca-mcp-gateway pytest services/mcp-gateway/tests/test_toolset.py -q
uv run --package ithaca-control-plane pytest services/control-plane/tests/test_execution_gateway.py -q
uv run --package ithaca-runtime pytest services/runtime/tests/test_trigger_engine.py -q
uv run --package ithaca-ibkr-engine pytest services/ibkr-engine/tests -q
git diff --check
```

Build and deploy checks:

```bash
./deploy/build_ibkr_engine.sh
./deploy/build_and_push.sh
DEPLOY_ENV=prod ./deploy/deploy_services.sh
kubectl -n ithaca-gateway rollout status deploy/ibkr-engine
kubectl -n ithaca-gateway rollout status deploy/ithaca-app
kubectl -n ithaca-workers rollout status deploy/ithaca-workers
```

Route checks:

```bash
dig +short ibkr.tradeithaca.com A
curl -I https://ibkr.tradeithaca.com/
kubectl -n ithaca-gateway get svc ibkr-engine -o wide
```

Post-sign-in lockdown checks:

```bash
kubectl -n ithaca-gateway apply -f infra/k8s/caddy.yaml
kubectl -n ithaca-gateway rollout status deploy/caddy
curl -I https://ibkr.tradeithaca.com/ || true
kubectl -n ithaca-workers run ibkr-smoke --rm -it --restart=Never \
  --image="registry.digitalocean.com/ithaca/ithaca:<tag>" -- \
  ibkr-smoke --symbol AAPL --json
```

After customer sign-in:

```bash
kubectl -n ithaca-gateway exec deploy/ibkr-engine -c ithaca-ibkr-engine -- \
  curl -fsS http://127.0.0.1:<wrapper-port>/auth/status

kubectl -n ithaca-workers run ibkr-smoke --rm -it --restart=Never \
  --image="registry.digitalocean.com/ithaca/ithaca:<tag>" -- \
  ibkr-smoke --symbol AAPL --json

kubectl -n ithaca-gateway run launch-gate --rm -it --restart=Never \
  --image="registry.digitalocean.com/ithaca/ithaca:<tag>" -- \
  launch-gate --mode local --require-postgres --require-ibkr --json

ITHACA_REST_URL=https://app.tradeithaca.com \
ITHACA_MCP_URL=https://mcp.tradeithaca.com/mcp \
uv run python scripts/launch_gate.py --mode http --require-postgres --require-ibkr --require-mcp --json
```

Acceptance criteria:

- `https://ibkr.tradeithaca.com/...` loads the verified IBKR login/session page only during the temporary sign-in window.
- Customer can sign in without sharing credentials with Ithaca.
- `/auth/status` reports authenticated.
- After sign-in, the public `ibkr.tradeithaca.com` route is removed or operator-only.
- After public-route lockdown, cluster-internal `ibkr-smoke` still returns fresh IBKR data.
- `ibkr-smoke --symbol AAPL --json` returns `ok: true`, fresh `event_time`, fresh `received_time`, and `source: ibkr-engine`.
- MCP `market.quote` returns IBKR-backed data.
- Trigger engine evaluates an active policy using IBKR data without provider errors.
- `ITHACA_ENABLE_LIVE_EXECUTION` remains `0` unless separately approved.

## Risks and Open Questions

- Exact IBKR Client Portal Gateway package URL, container constraints, and login path still need official-doc verification because browser access is not currently set up.
- IBKR sessions can expire or require periodic reauth; the deployment needs clear status and reauth runbook support.
- Realtime data depends on the customer's IBKR market-data entitlements. The wrapper must surface entitlement/delayed-data flags rather than hiding delayed quotes as realtime.
- Exposing a broker login surface publicly is sensitive. Use a temporary protected route for the sign-in window and keep normalized API routes internal.
- Current prod is drifted from the repo manifests. Applying the current manifests is a topology change, not a minor image bump.
- DNS for `tradeithaca.com` is not currently controllable via the available DO token.
