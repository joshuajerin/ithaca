# Plan: GitHub to DigitalOcean Deploy Gating

Status: proposed, awaiting approval.

## Goal

Wire GitHub Actions to DigitalOcean so production is deployed only from the latest commit on `main`, while non-main work deploys only to a dev environment.

The production deploy must never be driven by a local checkout, a stale `main` workflow run, a feature branch, a pull request, or a mutable dev tag.

## Current State Found

- Local `main` is synced with `origin/main` at `a5fe2a0d0da7cf22ad52dfd2904e104f8ce2c834` (`a5fe2a0`, "Install Vercel Web Analytics").
- GitHub repo is `joshuajerin/doomberg`, private, default branch `main`.
- GitHub workflows are only:
  - `ci`: contract drift, Python tests, demos, TS contracts, web tests/build.
  - `deploy-checks`: Docker build smoke test plus Terraform fmt/validate/guardrail.
- There is no GitHub deploy workflow.
- GitHub has existing empty environments named `Preview` and `Production`, but no repository/environment secrets, no variables, no protection rules, and no branch policy.
- `main` branch protection is absent or inaccessible through the API.
- Live DigitalOcean cluster is `doomberg-prod-doks` in `nyc3`, current kubectl context `do-nyc3-doomberg-prod-doks`.
- Live production endpoints are healthy:
  - `https://app.doomberg.me/healthz` returns 200.
  - Terraform-managed LB `http://209.38.49.16/healthz` returns 200.
- Live production image is behind current `main`:
  - `doomberg-app` runs `registry.digitalocean.com/doomberg/doomberg:d8f1759`.
  - DOCR `latest` also points to `d8f1759`.
  - Current `origin/main` is `a5fe2a0`.
- There is also a standalone `doomberg-mcp` deployment still running `f384567`, while public MCP traffic is routed to the `mcp-gateway` container inside `doomberg-app`. The standalone deployment is stale and appears unused by ingress.
- `deploy/build_and_push.sh` is local/manual, sources `infra/terraform/.env`, builds from the local worktree, and always pushes both the explicit tag and `latest`.
- `deploy/deploy_services.sh` is local/manual, sources `infra/terraform/.env`, hardcodes namespace `doomberg-gateway`, requires `DOOMBERG_PROD_URL`, applies the stale `mcp-deployment.yaml`, and prints the generated tenant API key.
- Kubernetes manifests hardcode the production namespace `doomberg-gateway`.
- Caddy hardcodes production hosts `app.doomberg.me` and `mcp.doomberg.me`.
- Terraform state is clean against DigitalOcean, but the repo has a topology mismatch: Terraform manages one public LB at `209.38.49.16`, while DNS currently points `app.doomberg.me` and `mcp.doomberg.me` at the Kubernetes-created Caddy LB `129.212.135.120`.
- Current working tree has unrelated local dirt from verification:
  - tracked: `Dockerfile`, `site/package.json`
  - untracked runtime/artifact paths: `.gstack/`, `data/`, `docs/strategy/`, `doomberg.db*`, `infra/terraform/tfplan`

## Target Design

### Environments

Use two explicit deploy environments:

- `prod`
  - Maps to the existing production namespace `doomberg-gateway`.
  - Uses the production cluster `doomberg-prod-doks`.
  - Uses the production DB/archive DSN.
  - Uses production public hosts `app.doomberg.me` and `mcp.doomberg.me`.
  - Only `refs/heads/main` can deploy.

- `dev`
  - Default recommendation: same DOKS cluster, separate namespace `doomberg-dev-gateway`, separate PVC, separate Kubernetes Secret, separate Caddy config/hosts.
  - Uses the dev DB/archive DSN.
  - Uses dev public hosts if DNS exists, for example `dev-app.doomberg.me` and `dev-mcp.doomberg.me`.
  - Receives non-main branch pushes only.

Reason for recommending same-cluster dev first: the current Terraform has only one DOKS cluster and one registry, and the user asked to connect the existing cluster/infra to GitHub. A separate dev cluster can be added later with a Terraform workspace or `dev.tfvars`, but that is more cost and more infra churn.

### GitHub Environment Setup

Create or normalize GitHub environments to `prod` and `dev`.

Required `prod` secrets:

- `DIGITALOCEAN_ACCESS_TOKEN`
- `DOOMBERG_PROD_URL`
- `DOOMBERG_SESSION_SECRET`
- `DOOMBERG_TENANT_API_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`

Required `dev` secrets:

- `DIGITALOCEAN_ACCESS_TOKEN`
- `DOOMBERG_DEV_URL`
- `DOOMBERG_SESSION_SECRET`
- `DOOMBERG_TENANT_API_KEY`
- optional dev OAuth client secrets if auth should work in dev

Suggested environment variables:

- `REGISTRY_NAME=doomberg`
- `DO_CLUSTER_NAME=doomberg-prod-doks`
- `K8S_NAMESPACE=doomberg-gateway` for prod
- `K8S_NAMESPACE=doomberg-dev-gateway` for dev
- `APP_HOST=app.doomberg.me` for prod
- `MCP_HOST=mcp.doomberg.me` for prod
- `APP_HOST=dev-app.doomberg.me` for dev, if DNS is available
- `MCP_HOST=dev-mcp.doomberg.me` for dev, if DNS is available

Set a production environment deployment branch policy allowing only `main`. Add optional manual approval if you want a human gate even after CI passes.

### Branch and Deploy Rules

Production:

- Trigger only on push to `main`.
- Build from the exact GitHub checkout SHA.
- Before deploying, fetch `origin/main` and verify `origin/main == GITHUB_SHA`.
- Use concurrency group `prod-deploy` with `cancel-in-progress: true`, so stale production runs are canceled.
- Deploy only an immutable SHA tag, not `latest`.
- Optionally move `latest` or `prod-latest` only after the rollout succeeds.

Dev:

- Trigger on pushes to non-main branches.
- Build from the exact branch SHA.
- Deploy to the dev namespace only.
- Use a tag like `dev-${safe_branch}-${short_sha}`.
- Never push or deploy `latest`.
- Use concurrency group `dev-deploy` if dev is a shared environment, so the most recent branch push owns dev.

Pull requests:

- Keep PRs as build/test only unless the PR comes from a same-repo branch that already triggered a dev deploy through `push`.
- Do not expose DigitalOcean secrets to arbitrary PR workflows.

## Implementation Steps

1. Normalize local repo hygiene

   Decide what to do with the existing local tracked changes:

   - Keep and commit `Dockerfile` timeout if Docker builds still need it.
   - Keep and commit the `site/package.json` cleanup if the ignored pnpm warning matters.
   - Otherwise revert only those two local edits intentionally.

   Add ignores for transient local state before any deploy automation commit:

   - `.gstack/`
   - `data/` if it is generated/local and not meant for source control
   - `doomberg.db*`
   - `infra/terraform/tfplan`

   `docs/strategy/` needs a decision because it contains strategy artifacts, not clearly disposable runtime output.

2. Make deploy scripts CI-safe and environment-aware

   Refactor `deploy/build_and_push.sh`:

   - Do not require local `.env` in CI.
   - Accept `REGISTRY_NAME`, `IMAGE_TAG`, and `PUSH_LATEST`.
   - Push `latest` only when explicitly requested by a prod main deploy.
   - Prefer the GitHub-provided SHA tag in CI.

   Refactor `deploy/deploy_services.sh`:

   - Accept `DEPLOY_ENV`, `K8S_NAMESPACE`, `WORKER_IMAGE`, `DOOMBERG_DB_URL`, `APP_HOST`, and `MCP_HOST`.
   - Keep local `.env` sourcing as a local fallback only, not the CI source of truth.
   - Never generate a new tenant API key silently in CI. Require `DOOMBERG_TENANT_API_KEY`.
   - Stop printing tenant API keys.
   - Wait for the environment-specific rollouts.
   - Verify the deployed image equals the requested immutable tag.

3. Remove prod hardcoding from Kubernetes manifests

   Add a small rendering layer, either:

   - Kustomize overlays: `infra/k8s/base`, `infra/k8s/overlays/prod`, `infra/k8s/overlays/dev`.
   - Or envsubst templates if keeping shell-first deployment is preferred.

   Required parameters:

   - namespace
   - image
   - app host
   - MCP host
   - PVC names if shared cluster dev/prod run together

   Keep prod and dev PVCs separate so dev cannot write prod SQLite state.

4. Fix the MCP deployment split

   Remove `infra/k8s/mcp-deployment.yaml` from the normal deploy path unless there is a real separate role for it.

   Current public MCP routing goes to `doomberg-app` port 8080, and that co-location is intentional because it shares the SQLite auth store. The stale standalone `doomberg-mcp` deployment should either be:

   - deleted from the cluster and deploy script, or
   - moved to a clearly named internal-only/debug manifest that is not part of prod deploy.

5. Add GitHub Actions deploy workflow

   Add `.github/workflows/deploy-do.yml` with jobs similar to:

   - `classify`
     - Determine `deploy_env`.
     - Determine image tag.
     - Refuse prod unless `github.ref == refs/heads/main`.
   - `checks`
     - Run the existing critical checks or call equivalent steps so deploy is gated in the same workflow.
     - At minimum include Docker build smoke, Terraform fmt/validate/guardrail, Python demos, and web build.
   - `build-push`
     - Install doctl.
     - Authenticate using `DIGITALOCEAN_ACCESS_TOKEN`.
     - `doctl registry login`.
     - Build/push immutable image tag.
   - `deploy`
     - Save kubeconfig for `DO_CLUSTER_NAME`.
     - For prod, re-fetch `origin/main` and fail if `origin/main` no longer equals `GITHUB_SHA`.
     - Run the env-aware deploy script.
     - Run `kubectl rollout status`.
     - Curl environment health endpoint.
     - Assert deployed Kubernetes images contain the exact SHA tag.

6. Add GitHub branch/environment protection

   Configure `main` branch protection:

   - Require status checks before merge.
   - Include `ci` and `deploy-checks`, or the new unified deploy workflow check names if checks move there.
   - Require branches to be up to date before merge if desired.

   Configure `prod` environment:

   - Restrict deployment branch to `main`.
   - Optional reviewer approval.

   Configure `dev` environment:

   - Allow branch deploys.
   - No production secrets.

7. DNS and ingress decision

   For prod, leave existing public behavior intact until the LB/Caddy split is cleaned up.

   For dev, choose one:

   - Add dev hostnames to the same Caddy LB and point DNS at `129.212.135.120`.
   - Use the Terraform LB/NodePorts for non-TLS health-only dev verification.
   - Create a separate dev ingress/LB if isolation is worth the cost.

   Recommendation: use the existing Caddy LB for dev hostnames if DNS can be changed, because it preserves HTTPS and matches current production traffic.

8. Documentation updates

   Update `deploy/RUNBOOK.md`:

   - Mark manual local deploy as break-glass only.
   - Document GitHub deploy flow.
   - Document prod main-only gating.
   - Document dev namespace behavior.
   - Remove stale HA claims that no longer match `terraform.auto.tfvars`.
   - Clarify the two-LB situation.

## Verification Plan

Before merge:

- `uv sync --all-packages --extra dev`
- Python pytest packages:
  - `packages/contracts/py`
  - `doomberg-core`
  - `services/data-archive`
  - `services/platform`
  - `services/mcp-gateway`
  - `services/control-plane`
  - `services/rest-gateway`
  - `services/runtime`
- `uv run python scripts/demo_e2e.py`
- `uv run python scripts/demo_deploy.py`
- `pnpm install --frozen-lockfile`
- `pnpm run contracts:check`
- `pnpm --filter @doomberg/contracts run test`
- `pnpm --filter @doomberg/web run test`
- `pnpm --filter @doomberg/web run build`
- `pnpm --filter @doomberg/site run build`
- `terraform -chdir=infra/terraform fmt -check -recursive`
- `terraform -chdir=infra/terraform init -backend=false -input=false`
- `terraform -chdir=infra/terraform validate -no-color`
- CPU guardrail negative plan with `backtest_node_size=gpu-h100x1-80gb`
- `kubectl apply --dry-run=server` or `kubectl diff` against the rendered dev manifests.

After dev deploy:

- `kubectl -n doomberg-dev-gateway rollout status deployment/doomberg-app`
- `kubectl -n doomberg-dev-gateway get deploy,svc,pvc -o wide`
- curl dev `/healthz`
- verify all app containers run the expected `dev-*-${short_sha}` image.
- verify prod namespace images did not change.

After prod deploy:

- workflow guard confirms `origin/main == GITHUB_SHA`.
- `kubectl -n doomberg-gateway rollout status deployment/doomberg-app`
- curl `https://app.doomberg.me/healthz`
- curl `https://mcp.doomberg.me/mcp` expecting 401 without a bearer token.
- verify all routed app containers run the exact main SHA tag.
- verify no dev tag or feature-branch tag is deployed in prod.

## Risks and Decisions Needed

- Dev target: approve same-cluster dev namespace, or ask for a separate dev DOKS cluster.
- GitHub secrets: approve copying local `.env` values into GitHub environment secrets without printing them, or add them manually in GitHub.
- DNS: decide dev hostnames and where DNS is managed, since `doomberg.me` records are not in DigitalOcean DNS.
- Load balancers: decide whether to keep the Kubernetes Caddy LB as the public path or consolidate onto the Terraform LB.
- Stale MCP deployment: approve removing it from the standard deploy path.
- Working tree: decide whether the current tracked local changes should be kept as part of the deploy automation branch or separated.

## Recommended First Implementation Pass

1. Add `.gitignore` entries for obvious runtime output.
2. Convert deploy scripts and manifests to accept environment parameters.
3. Remove the stale standalone MCP deployment from the normal deploy path.
4. Add `deploy-do.yml` with main-only prod and non-main dev classification.
5. Add GitHub environment/branch protection and required secrets.
6. Trigger a non-main dev deploy first.
7. After dev passes, merge to `main` and let only the newest `main` SHA deploy prod.
