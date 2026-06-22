#!/usr/bin/env bash
# Deploy the always-on Doomberg services into one environment namespace pair.
#
#   DEPLOY_ENV=dev IMAGE_TAG=dev-feature-a5fe2a0 deploy/deploy_services.sh
#   DEPLOY_ENV=prod deploy/deploy_services.sh a5fe2a0
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

if [[ "${LOAD_LOCAL_ENV:-1}" != "0" && -f infra/terraform/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source infra/terraform/.env
  set +a
fi

DEPLOY_ENV="${DEPLOY_ENV:-prod}"
TAG="${IMAGE_TAG:-${1:-latest}}"
REGISTRY_NAME="${REGISTRY_NAME:-doomberg}"
WORKER_IMAGE="${WORKER_IMAGE:-registry.digitalocean.com/${REGISTRY_NAME}/doomberg:${TAG}}"
CADDY_NAMESPACE="${CADDY_NAMESPACE:-doomberg-gateway}"

case "${DEPLOY_ENV}" in
  prod)
    K8S_GATEWAY_NAMESPACE="${K8S_GATEWAY_NAMESPACE:-doomberg-gateway}"
    K8S_WORKER_NAMESPACE="${K8S_WORKER_NAMESPACE:-doomberg-workers}"
    APP_HOST="${APP_HOST:-app.doomberg.me}"
    MCP_HOST="${MCP_HOST:-mcp.doomberg.me}"
    REST_NODE_PORT="${REST_NODE_PORT:-30080}"
    MCP_NODE_PORT="${MCP_NODE_PORT:-30808}"
    APP_NODE_WORKLOAD="${APP_NODE_WORKLOAD:-paper}"
    SHORT_LOADER_SUSPEND="${SHORT_LOADER_SUSPEND:-false}"
    DOOMBERG_ARCHIVE_URL="${DOOMBERG_ARCHIVE_URL:-${DOOMBERG_PROD_URL:-}}"
    ;;
  dev)
    K8S_GATEWAY_NAMESPACE="${K8S_GATEWAY_NAMESPACE:-doomberg-dev-gateway}"
    K8S_WORKER_NAMESPACE="${K8S_WORKER_NAMESPACE:-doomberg-dev-workers}"
    APP_HOST="${APP_HOST:-dev-app.129.212.135.120.sslip.io}"
    MCP_HOST="${MCP_HOST:-dev-mcp.129.212.135.120.sslip.io}"
    DEV_APP_HOST_CANONICAL="${DEV_APP_HOST_CANONICAL:-dev-app.doomberg.me}"
    DEV_MCP_HOST_CANONICAL="${DEV_MCP_HOST_CANONICAL:-dev-mcp.doomberg.me}"
    REST_NODE_PORT="${REST_NODE_PORT:-30082}"
    MCP_NODE_PORT="${MCP_NODE_PORT:-30810}"
    APP_NODE_WORKLOAD="${APP_NODE_WORKLOAD:-backtest}"
    SHORT_LOADER_SUSPEND="${SHORT_LOADER_SUSPEND:-true}"
    DOOMBERG_ARCHIVE_URL="${DOOMBERG_ARCHIVE_URL:-${DOOMBERG_DEV_URL:-}}"
    ;;
  *)
    echo "ERROR: DEPLOY_ENV must be prod or dev; got ${DEPLOY_ENV}" >&2
    exit 2
    ;;
esac

if [[ "${DEPLOY_ENV}" == "dev" ]]; then
  MCP_ALLOWED_HOSTS="${MCP_ALLOWED_HOSTS:-${MCP_HOST},${MCP_HOST}:443,${DEV_MCP_HOST_CANONICAL},${DEV_MCP_HOST_CANONICAL}:443}"
else
  MCP_ALLOWED_HOSTS="${MCP_ALLOWED_HOSTS:-${MCP_HOST},${MCP_HOST}:443}"
fi

: "${DOOMBERG_ARCHIVE_URL:?DOOMBERG_ARCHIVE_URL must be set for ${DEPLOY_ENV}}"
: "${DOOMBERG_SESSION_SECRET:?DOOMBERG_SESSION_SECRET must be set for ${DEPLOY_ENV}}"

render_manifest() {
  local file="$1"
  sed \
    -e "s|\${WORKER_IMAGE}|${WORKER_IMAGE}|g" \
    -e "s|\${DOOMBERG_ENV}|${DEPLOY_ENV}|g" \
    -e "s|\${K8S_GATEWAY_NAMESPACE}|${K8S_GATEWAY_NAMESPACE}|g" \
    -e "s|\${K8S_WORKER_NAMESPACE}|${K8S_WORKER_NAMESPACE}|g" \
    -e "s|\${REST_NODE_PORT}|${REST_NODE_PORT}|g" \
    -e "s|\${MCP_NODE_PORT}|${MCP_NODE_PORT}|g" \
    -e "s|\${APP_NODE_WORKLOAD}|${APP_NODE_WORKLOAD}|g" \
    -e "s|\${SHORT_LOADER_SUSPEND}|${SHORT_LOADER_SUSPEND}|g" \
    -e "s|\${MCP_ALLOWED_HOSTS}|${MCP_ALLOWED_HOSTS}|g" \
    "${file}"
}

echo "==> deploy env=${DEPLOY_ENV} namespace=${K8S_GATEWAY_NAMESPACE} image=${WORKER_IMAGE}"

echo "==> namespaces"
render_manifest infra/k8s/namespace.yaml | kubectl apply -f -

echo "==> secret doomberg-db (${DEPLOY_ENV}; values redacted)"
kubectl -n "${K8S_GATEWAY_NAMESPACE}" create secret generic doomberg-db \
  --from-literal=db_url="${DOOMBERG_ARCHIVE_URL}" \
  --from-literal=archive_url="${DOOMBERG_ARCHIVE_URL}" \
  --from-literal=session_secret="${DOOMBERG_SESSION_SECRET}" \
  --from-literal=google_client_id="${GOOGLE_CLIENT_ID:-}" \
  --from-literal=google_client_secret="${GOOGLE_CLIENT_SECRET:-}" \
  --from-literal=github_client_id="${GITHUB_CLIENT_ID:-}" \
  --from-literal=github_client_secret="${GITHUB_CLIENT_SECRET:-}" \
  --from-literal=admin_token="${DOOMBERG_ADMIN_TOKEN:-}" \
  --from-literal=fmp_api_key="${FMP_API_KEY:-}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> persistent state"
render_manifest infra/k8s/pvc.yaml | kubectl apply -f -

echo "==> worker network policy"
render_manifest infra/k8s/worker-networkpolicy.yaml | kubectl apply -f -

echo "==> app manifests"
for file in infra/k8s/app-deployment.yaml infra/k8s/app-service.yaml infra/k8s/short-loader.yaml; do
  render_manifest "${file}" | kubectl apply -f -
done

caddy_checksum() {
  kubectl -n "${CADDY_NAMESPACE}" get configmap caddy-config \
    -o jsonpath='{.data.Caddyfile}' 2>/dev/null | cksum | awk '{print $1 ":" $2}'
}

if [[ "${APPLY_CADDY:-1}" == "1" ]]; then
  echo "==> caddy public ingress"
  before="$(caddy_checksum || true)"
  kubectl apply -f infra/k8s/caddy.yaml
  after="$(caddy_checksum || true)"
  if [[ "${FORCE_CADDY_RESTART:-0}" == "1" || "${before}" != "${after}" ]]; then
    echo "==> caddy config changed; restarting caddy"
    kubectl -n "${CADDY_NAMESPACE}" rollout restart deployment/caddy
  fi
  kubectl -n "${CADDY_NAMESPACE}" rollout status deployment/caddy --timeout=300s
fi

echo "==> waiting for ${DEPLOY_ENV} rollout"
kubectl -n "${K8S_GATEWAY_NAMESPACE}" rollout status deployment/doomberg-app --timeout=300s

echo "==> verifying image tag"
images="$(kubectl -n "${K8S_GATEWAY_NAMESPACE}" get deployment doomberg-app \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.image}{"\n"}{end}')"
if echo "${images}" | grep -v -Fx "${WORKER_IMAGE}" >/dev/null; then
  echo "ERROR: deployment image mismatch; expected every app container to be ${WORKER_IMAGE}" >&2
  echo "${images}" >&2
  exit 1
fi

echo "==> pods"
kubectl -n "${K8S_GATEWAY_NAMESPACE}" get pods -o wide
echo "==> ${DEPLOY_ENV} deployed: ${APP_HOST} / ${MCP_HOST}"
