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
IBKR_ENGINE_IMAGE="${IBKR_ENGINE_IMAGE:-registry.digitalocean.com/${REGISTRY_NAME}/doomberg-ibkr-engine:${TAG}}"
CADDY_NAMESPACE="${CADDY_NAMESPACE:-doomberg-gateway}"
IBKR_ENGINE_ENABLED="${IBKR_ENGINE_ENABLED:-1}"
IBKR_ENGINE_PORT="${IBKR_ENGINE_PORT:-8090}"
IBKR_ENGINE_STORAGE_SIZE="${IBKR_ENGINE_STORAGE_SIZE:-2Gi}"
IBKR_SIGNIN_PUBLIC="${IBKR_SIGNIN_PUBLIC:-0}"
IBKR_SIGNIN_HOST="${IBKR_SIGNIN_HOST:-ibkr.doomberg.me}"
IBKR_SIGNIN_REMOTE_IPS="${IBKR_SIGNIN_REMOTE_IPS:-0.0.0.0/0}"

case "${DEPLOY_ENV}" in
  prod)
    K8S_GATEWAY_NAMESPACE="${K8S_GATEWAY_NAMESPACE:-doomberg-gateway}"
    K8S_WORKER_NAMESPACE="${K8S_WORKER_NAMESPACE:-doomberg-workers}"
    APP_HOST="${APP_HOST:-app.doomberg.me}"
    MCP_HOST="${MCP_HOST:-mcp.doomberg.me}"
    REST_NODE_PORT="${REST_NODE_PORT:-30080}"
    MCP_NODE_PORT="${MCP_NODE_PORT:-30808}"
    APP_NODE_WORKLOAD="${APP_NODE_WORKLOAD:-paper}"
    WORKER_NODE_WORKLOAD="${WORKER_NODE_WORKLOAD:-paper}"
    APP_REPLICAS="${APP_REPLICAS:-2}"
    WORKER_REPLICAS="${WORKER_REPLICAS:-2}"
    SHORT_LOADER_SUSPEND="${SHORT_LOADER_SUSPEND:-false}"
    DOOMBERG_PLATFORM_DB_URL="${DOOMBERG_PLATFORM_DB_URL:-${DOOMBERG_PROD_URL:-}}"
    DOOMBERG_ARCHIVE_URL="${DOOMBERG_ARCHIVE_URL:-${DOOMBERG_PLATFORM_DB_URL:-}}"
    ;;
  dev)
    K8S_GATEWAY_NAMESPACE="${K8S_GATEWAY_NAMESPACE:-doomberg-dev-gateway}"
    K8S_WORKER_NAMESPACE="${K8S_WORKER_NAMESPACE:-doomberg-dev-workers}"
    APP_HOST="${APP_HOST:-dev-app.doomberg.me}"
    MCP_HOST="${MCP_HOST:-dev-mcp.doomberg.me}"
    REST_NODE_PORT="${REST_NODE_PORT:-30082}"
    MCP_NODE_PORT="${MCP_NODE_PORT:-30810}"
    APP_NODE_WORKLOAD="${APP_NODE_WORKLOAD:-backtest}"
    WORKER_NODE_WORKLOAD="${WORKER_NODE_WORKLOAD:-backtest}"
    APP_REPLICAS="${APP_REPLICAS:-1}"
    WORKER_REPLICAS="${WORKER_REPLICAS:-1}"
    SHORT_LOADER_SUSPEND="${SHORT_LOADER_SUSPEND:-true}"
    DOOMBERG_PLATFORM_DB_URL="${DOOMBERG_PLATFORM_DB_URL:-${DOOMBERG_DEV_URL:-}}"
    DOOMBERG_ARCHIVE_URL="${DOOMBERG_ARCHIVE_URL:-${DOOMBERG_PLATFORM_DB_URL:-}}"
    ;;
  *)
    echo "ERROR: DEPLOY_ENV must be prod or dev; got ${DEPLOY_ENV}" >&2
    exit 2
    ;;
esac

MCP_ALLOWED_HOSTS="${MCP_ALLOWED_HOSTS:-${MCP_HOST},${MCP_HOST}:443}"

if [[ "${IBKR_ENGINE_ENABLED}" == "1" ]]; then
  if [[ -z "${IBKR_GATEWAY_IMAGE:-}" ]]; then
    IBKR_GATEWAY_IMAGE="$(kubectl -n "${K8S_GATEWAY_NAMESPACE}" get deployment ibkr-gateway \
      -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true)"
  fi
  if [[ -z "${IBKR_GATEWAY_IMAGE:-}" ]]; then
    IBKR_GATEWAY_IMAGE="$(kubectl -n "${K8S_GATEWAY_NAMESPACE}" get deployment ibkr-engine \
      -o jsonpath='{range .spec.template.spec.containers[?(@.name=="ibkr-client-portal-gateway")]}{.image}{end}' 2>/dev/null || true)"
  fi
  IBKR_GATEWAY_IMAGE="${IBKR_GATEWAY_IMAGE:-${IBKR_ENGINE_IMAGE}}"
  DOOMBERG_IBKR_ENGINE_URL="${DOOMBERG_IBKR_ENGINE_URL:-http://ibkr-engine.${K8S_GATEWAY_NAMESPACE}.svc.cluster.local:${IBKR_ENGINE_PORT}}"
  if [[ -z "${DOOMBERG_IBKR_ENGINE_TOKEN:-}" ]]; then
    DOOMBERG_IBKR_ENGINE_TOKEN="$(kubectl -n "${K8S_GATEWAY_NAMESPACE}" get secret ibkr-engine \
      -o jsonpath='{.data.engine_token}' 2>/dev/null | base64 --decode || true)"
  fi
  if [[ -z "${DOOMBERG_IBKR_ENGINE_TOKEN:-}" ]]; then
    DOOMBERG_IBKR_ENGINE_TOKEN="$(openssl rand -hex 32)"
  fi
  DOOMBERG_IBKR_QUOTE_PATH="${DOOMBERG_IBKR_QUOTE_PATH:-/quote?symbol={symbol}}"
  DOOMBERG_IBKR_HISTORY_PATH="${DOOMBERG_IBKR_HISTORY_PATH:-/history?symbol={symbol}}"
  DOOMBERG_IBKR_NEWS_PATH="${DOOMBERG_IBKR_NEWS_PATH:-/news}"
  DOOMBERG_IBKR_SCANNER_PATH="${DOOMBERG_IBKR_SCANNER_PATH:-/scanner}"
  DOOMBERG_IBKR_ACCOUNTS_PATH="${DOOMBERG_IBKR_ACCOUNTS_PATH:-/accounts}"
  DOOMBERG_IBKR_POSITIONS_PATH="${DOOMBERG_IBKR_POSITIONS_PATH:-/positions?account={account}}"
  DOOMBERG_IBKR_ORDERS_PATH="${DOOMBERG_IBKR_ORDERS_PATH:-/orders?account={account}}"
fi

: "${DOOMBERG_PLATFORM_DB_URL:?DOOMBERG_PLATFORM_DB_URL must be set for ${DEPLOY_ENV}}"
: "${DOOMBERG_ARCHIVE_URL:?DOOMBERG_ARCHIVE_URL must be set for ${DEPLOY_ENV}}"
: "${DOOMBERG_SESSION_SECRET:?DOOMBERG_SESSION_SECRET must be set for ${DEPLOY_ENV}}"
if [[ -z "${DOOMBERG_IBKR_ENGINE_URL:-}" ]]; then
  echo "WARN: DOOMBERG_IBKR_ENGINE_URL is unset; trigger-engine worker will stay up, but active live-data trigger policies will report provider errors until configured." >&2
fi
if [[ "${DOOMBERG_ENABLE_LIVE_EXECUTION:-0}" == "1" && -z "${DOOMBERG_IBKR_ENGINE_URL:-}" ]]; then
  echo "ERROR: DOOMBERG_ENABLE_LIVE_EXECUTION=1 requires DOOMBERG_IBKR_ENGINE_URL" >&2
  exit 2
fi

render_manifest() {
  local file="$1"
  sed \
    -e "s|\${WORKER_IMAGE}|${WORKER_IMAGE}|g" \
    -e "s|\${IBKR_ENGINE_IMAGE}|${IBKR_ENGINE_IMAGE}|g" \
    -e "s|\${IBKR_GATEWAY_IMAGE}|${IBKR_GATEWAY_IMAGE:-}|g" \
    -e "s|\${DOOMBERG_ENV}|${DEPLOY_ENV}|g" \
    -e "s|\${K8S_GATEWAY_NAMESPACE}|${K8S_GATEWAY_NAMESPACE}|g" \
    -e "s|\${K8S_WORKER_NAMESPACE}|${K8S_WORKER_NAMESPACE}|g" \
    -e "s|\${IBKR_ENGINE_PORT}|${IBKR_ENGINE_PORT}|g" \
    -e "s|\${IBKR_ENGINE_STORAGE_SIZE}|${IBKR_ENGINE_STORAGE_SIZE}|g" \
    -e "s|\${IBKR_SIGNIN_HOST}|${IBKR_SIGNIN_HOST}|g" \
    -e "s|\${IBKR_SIGNIN_REMOTE_IPS}|${IBKR_SIGNIN_REMOTE_IPS}|g" \
    -e "s|\${REST_NODE_PORT}|${REST_NODE_PORT}|g" \
    -e "s|\${MCP_NODE_PORT}|${MCP_NODE_PORT}|g" \
    -e "s|\${APP_NODE_WORKLOAD}|${APP_NODE_WORKLOAD}|g" \
    -e "s|\${WORKER_NODE_WORKLOAD}|${WORKER_NODE_WORKLOAD}|g" \
    -e "s|\${APP_REPLICAS}|${APP_REPLICAS}|g" \
    -e "s|\${WORKER_REPLICAS}|${WORKER_REPLICAS}|g" \
    -e "s|\${SHORT_LOADER_SUSPEND}|${SHORT_LOADER_SUSPEND}|g" \
    -e "s|\${MCP_ALLOWED_HOSTS}|${MCP_ALLOWED_HOSTS}|g" \
    "${file}"
}

create_ibkr_secret() {
  kubectl -n "${K8S_GATEWAY_NAMESPACE}" create secret generic ibkr-engine \
    --from-literal=engine_token="${DOOMBERG_IBKR_ENGINE_TOKEN:-}" \
    --from-literal=enable_live_execution="${DOOMBERG_ENABLE_LIVE_EXECUTION:-0}" \
    --dry-run=client -o yaml | kubectl apply -f -
}

create_doomberg_secret() {
  local namespace="$1"
  kubectl -n "${namespace}" create secret generic doomberg-db \
    --from-literal=db_url="${DOOMBERG_PLATFORM_DB_URL}" \
    --from-literal=platform_url="${DOOMBERG_PLATFORM_DB_URL}" \
    --from-literal=archive_url="${DOOMBERG_ARCHIVE_URL}" \
    --from-literal=session_secret="${DOOMBERG_SESSION_SECRET}" \
    --from-literal=google_client_id="${GOOGLE_CLIENT_ID:-}" \
    --from-literal=google_client_secret="${GOOGLE_CLIENT_SECRET:-}" \
    --from-literal=github_client_id="${GITHUB_CLIENT_ID:-}" \
    --from-literal=github_client_secret="${GITHUB_CLIENT_SECRET:-}" \
    --from-literal=admin_token="${DOOMBERG_ADMIN_TOKEN:-}" \
    --from-literal=fmp_api_key="${FMP_API_KEY:-}" \
    --from-literal=ibkr_engine_url="${DOOMBERG_IBKR_ENGINE_URL:-}" \
    --from-literal=ibkr_engine_token="${DOOMBERG_IBKR_ENGINE_TOKEN:-}" \
    --from-literal=ibkr_quote_path="${DOOMBERG_IBKR_QUOTE_PATH:-}" \
    --from-literal=ibkr_history_path="${DOOMBERG_IBKR_HISTORY_PATH:-}" \
    --from-literal=ibkr_news_path="${DOOMBERG_IBKR_NEWS_PATH:-}" \
    --from-literal=ibkr_scanner_path="${DOOMBERG_IBKR_SCANNER_PATH:-}" \
    --from-literal=ibkr_order_path="${DOOMBERG_IBKR_ORDER_PATH:-}" \
    --from-literal=ibkr_accounts_path="${DOOMBERG_IBKR_ACCOUNTS_PATH:-}" \
    --from-literal=ibkr_positions_path="${DOOMBERG_IBKR_POSITIONS_PATH:-}" \
    --from-literal=ibkr_orders_path="${DOOMBERG_IBKR_ORDERS_PATH:-}" \
    --from-literal=enable_live_execution="${DOOMBERG_ENABLE_LIVE_EXECUTION:-0}" \
    --from-literal=execution_max_notional_usd="${DOOMBERG_EXECUTION_MAX_NOTIONAL_USD:-10000}" \
    --from-literal=execution_max_quantity="${DOOMBERG_EXECUTION_MAX_QUANTITY:-10000}" \
    --from-literal=execution_max_freshness_ms="${DOOMBERG_EXECUTION_MAX_FRESHNESS_MS:-10000}" \
    --dry-run=client -o yaml | kubectl apply -f -
}

verify_deployment_images() {
  local namespace="$1"
  local deployment="$2"
  local images
  images="$(kubectl -n "${namespace}" get deployment "${deployment}" \
    -o jsonpath='{range .spec.template.spec.initContainers[*]}{.image}{"\n"}{end}{range .spec.template.spec.containers[*]}{.image}{"\n"}{end}')"
  if echo "${images}" | grep -v -Fx "${WORKER_IMAGE}" >/dev/null; then
    echo "ERROR: ${deployment} image mismatch; expected every container to be ${WORKER_IMAGE}" >&2
    echo "${images}" >&2
    exit 1
  fi
}

echo "==> deploy env=${DEPLOY_ENV} gateway=${K8S_GATEWAY_NAMESPACE} workers=${K8S_WORKER_NAMESPACE} image=${WORKER_IMAGE}"
if [[ "${IBKR_ENGINE_ENABLED}" == "1" ]]; then
  echo "==> ibkr enabled wrapper_image=${IBKR_ENGINE_IMAGE} gateway_image=${IBKR_GATEWAY_IMAGE} public_signin=${IBKR_SIGNIN_PUBLIC}"
fi
echo "==> replicas app=${APP_REPLICAS} workers=${WORKER_REPLICAS} node_workloads app=${APP_NODE_WORKLOAD} workers=${WORKER_NODE_WORKLOAD}"

echo "==> namespaces"
render_manifest infra/k8s/namespace.yaml | kubectl apply -f -

echo "==> secret doomberg-db (${DEPLOY_ENV}; values redacted)"
create_doomberg_secret "${K8S_GATEWAY_NAMESPACE}"
create_doomberg_secret "${K8S_WORKER_NAMESPACE}"
if [[ "${IBKR_ENGINE_ENABLED}" == "1" ]]; then
  echo "==> secret ibkr-engine (${DEPLOY_ENV}; values redacted)"
  create_ibkr_secret
fi

echo "==> worker network policy"
render_manifest infra/k8s/worker-networkpolicy.yaml | kubectl apply -f -

if [[ "${IBKR_ENGINE_ENABLED}" == "1" ]]; then
  echo "==> ibkr engine manifests"
  render_manifest infra/k8s/ibkr-engine.yaml | kubectl apply -f -
  render_manifest infra/k8s/ibkr-networkpolicy.yaml | kubectl apply -f -
fi

echo "==> app manifests"
for file in infra/k8s/app-deployment.yaml infra/k8s/app-service.yaml infra/k8s/worker-deployment.yaml infra/k8s/short-loader.yaml; do
  render_manifest "${file}" | kubectl apply -f -
done

caddy_checksum() {
  kubectl -n "${CADDY_NAMESPACE}" get configmap caddy-config \
    -o jsonpath='{.data.Caddyfile}' 2>/dev/null | cksum | awk '{print $1 ":" $2}'
}

if [[ "${APPLY_CADDY:-1}" == "1" ]]; then
  echo "==> caddy public ingress"
  before="$(caddy_checksum || true)"
  if [[ "${IBKR_SIGNIN_PUBLIC}" == "1" ]]; then
    echo "WARN: applying temporary public IBKR sign-in route host=${IBKR_SIGNIN_HOST} remote_ip=${IBKR_SIGNIN_REMOTE_IPS}" >&2
    render_manifest infra/k8s/caddy-ibkr-signin.yaml | kubectl apply -f -
  else
    kubectl apply -f infra/k8s/caddy.yaml
  fi
  after="$(caddy_checksum || true)"
  if [[ "${FORCE_CADDY_RESTART:-0}" == "1" || "${before}" != "${after}" ]]; then
    echo "==> caddy config changed; restarting caddy"
    kubectl -n "${CADDY_NAMESPACE}" rollout restart deployment/caddy
  fi
  kubectl -n "${CADDY_NAMESPACE}" rollout status deployment/caddy --timeout=300s
fi

echo "==> waiting for ${DEPLOY_ENV} rollout"
if [[ "${IBKR_ENGINE_ENABLED}" == "1" ]]; then
  kubectl -n "${K8S_GATEWAY_NAMESPACE}" rollout status deployment/ibkr-gateway --timeout=600s
  kubectl -n "${K8S_GATEWAY_NAMESPACE}" rollout status deployment/ibkr-engine --timeout=600s
fi
kubectl -n "${K8S_GATEWAY_NAMESPACE}" rollout status deployment/doomberg-app --timeout=300s
kubectl -n "${K8S_WORKER_NAMESPACE}" rollout status deployment/doomberg-workers --timeout=300s

echo "==> verifying image tag"
if [[ "${IBKR_ENGINE_ENABLED}" == "1" ]]; then
  images="$(kubectl -n "${K8S_GATEWAY_NAMESPACE}" get deployment ibkr-gateway \
    -o jsonpath='{range .spec.template.spec.containers[*]}{.image}{"\n"}{end}')"
  if echo "${images}" | grep -v -Fx "${IBKR_GATEWAY_IMAGE}" >/dev/null; then
    echo "ERROR: ibkr-gateway image mismatch; expected every container to be ${IBKR_GATEWAY_IMAGE}" >&2
    echo "${images}" >&2
    exit 1
  fi
  images="$(kubectl -n "${K8S_GATEWAY_NAMESPACE}" get deployment ibkr-engine \
    -o jsonpath='{range .spec.template.spec.containers[*]}{.image}{"\n"}{end}')"
  if echo "${images}" | grep -v -Fx "${IBKR_ENGINE_IMAGE}" >/dev/null; then
    echo "ERROR: ibkr-engine image mismatch; expected every container to be ${IBKR_ENGINE_IMAGE}" >&2
    echo "${images}" >&2
    exit 1
  fi
fi
verify_deployment_images "${K8S_GATEWAY_NAMESPACE}" doomberg-app
verify_deployment_images "${K8S_WORKER_NAMESPACE}" doomberg-workers

echo "==> pods"
kubectl -n "${K8S_GATEWAY_NAMESPACE}" get pods -o wide
kubectl -n "${K8S_WORKER_NAMESPACE}" get pods -o wide
echo "==> ${DEPLOY_ENV} deployed: ${APP_HOST} / ${MCP_HOST}"
