#!/usr/bin/env bash
# Phase 4 — deploy the always-on services to the DOKS cluster.
#
#   deploy/deploy_services.sh <git-sha-or-tag>
#
# Prereqs (in order, see RUNBOOK.md):
#   1. terraform apply has created the cluster (needs a tag:create-capable token).
#   2. kubeconfig is saved: doctl kubernetes cluster kubeconfig save doomberg-prod-doks
#   3. the image is built + pushed (deploy/build_and_push.sh).
#
# This script:
#   - creates the doomberg-gateway namespace + the doomberg-db Secret holding the
#     prod DSN (db_url + archive_url) from DOOMBERG_PROD_URL, plus a generated
#     tenant API key,
#   - substitutes ${WORKER_IMAGE} into the manifests and applies them,
#   - waits for the rollouts to be Ready.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

if [[ -f infra/terraform/.env ]]; then
  set -a; source infra/terraform/.env; set +a
fi

TAG="${1:-latest}"
REGISTRY_NAME="${REGISTRY_NAME:-doomberg}"
WORKER_IMAGE="registry.digitalocean.com/${REGISTRY_NAME}/doomberg:${TAG}"
NS="doomberg-gateway"

: "${DOOMBERG_PROD_URL:?DOOMBERG_PROD_URL must be set (prod Managed Postgres DSN)}"

echo "==> namespace ${NS}"
kubectl apply -f infra/k8s/namespace.yaml

echo "==> PersistentVolumeClaim doomberg-state (durable SQLite system-of-record)"
kubectl apply -f infra/k8s/pvc.yaml

# The platform system-of-record is SQLite (pod-local); the prod Postgres holds the
# read-only archive.*. Both Secret keys carry the prod DSN: db_url is informational
# (the app uses the SQLite path), archive_url is what the ArchiveGateway reads.
TENANT_API_KEY="${DOOMBERG_TENANT_API_KEY:-dmbg_prod_$(openssl rand -hex 16)}"

echo "==> Secret doomberg-db (prod DSN + tenant key + OAuth + session)"
kubectl -n "${NS}" create secret generic doomberg-db \
  --from-literal=db_url="${DOOMBERG_PROD_URL}" \
  --from-literal=archive_url="${DOOMBERG_PROD_URL}" \
  --from-literal=tenant_api_key="${TENANT_API_KEY}" \
  --from-literal=session_secret="${DOOMBERG_SESSION_SECRET:-}" \
  --from-literal=google_client_id="${GOOGLE_CLIENT_ID:-}" \
  --from-literal=google_client_secret="${GOOGLE_CLIENT_SECRET:-}" \
  --from-literal=github_client_id="${GITHUB_CLIENT_ID:-}" \
  --from-literal=github_client_secret="${GITHUB_CLIENT_SECRET:-}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> applying manifests with image ${WORKER_IMAGE}"
for f in infra/k8s/app-deployment.yaml infra/k8s/app-service.yaml infra/k8s/mcp-deployment.yaml; do
  sed "s|\${WORKER_IMAGE}|${WORKER_IMAGE}|g" "${f}" | kubectl apply -f -
done

echo "==> waiting for rollouts"
kubectl -n "${NS}" rollout status deployment/doomberg-app --timeout=300s
kubectl -n "${NS}" rollout status deployment/doomberg-mcp --timeout=300s

echo ""
echo "==> Pods:"
kubectl -n "${NS}" get pods -o wide
echo ""
echo "Tenant API key (save it): ${TENANT_API_KEY}"
echo "LB IP: $(terraform -chdir=infra/terraform output -raw load_balancer_ip 2>/dev/null || echo '<terraform output load_balancer_ip>')"
