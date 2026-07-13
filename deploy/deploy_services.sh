#!/usr/bin/env bash
# Deploy the always-on Doomberg services into one environment namespace pair.
#
#   DEPLOY_ENV=dev IMAGE_TAG=dev-feature-a5fe2a0 deploy/deploy_services.sh
#   DEPLOY_ENV=prod deploy/deploy_services.sh a5fe2a0
#   DEPLOY_ENV=dev DEPLOY_DRY_RUN=client deploy/deploy_services.sh test-image
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
IBKR_ENGINE_PORT="${IBKR_ENGINE_PORT:-8090}"
IBKR_ENGINE_STORAGE_SIZE="${IBKR_ENGINE_STORAGE_SIZE:-2Gi}"
SHARED_IBKR_NAMESPACE="${SHARED_IBKR_NAMESPACE:-doomberg-gateway}"
IBKR_SIGNIN_PUBLIC="${IBKR_SIGNIN_PUBLIC:-0}"
IBKR_SIGNIN_HOST="${IBKR_SIGNIN_HOST:-ibkr.doomberg.me}"
IBKR_SIGNIN_REMOTE_IPS="${IBKR_SIGNIN_REMOTE_IPS:-0.0.0.0/0}"
APP_REPLICAS_EXPLICIT="${APP_REPLICAS+x}"
WORKER_REPLICAS_EXPLICIT="${WORKER_REPLICAS+x}"
DEPLOY_DRY_RUN="${DEPLOY_DRY_RUN:-0}"
case "${DEPLOY_DRY_RUN}" in
  0|false|no|off|"")
    DEPLOY_DRY_RUN_MODE="off"
    ;;
  1|true|yes|on|client)
    DEPLOY_DRY_RUN_MODE="client"
    ;;
  server)
    DEPLOY_DRY_RUN_MODE="server"
    ;;
  *)
    echo "ERROR: DEPLOY_DRY_RUN must be off, client, or server; got ${DEPLOY_DRY_RUN}" >&2
    exit 2
    ;;
esac

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
    APP_REPLICAS="${APP_REPLICAS:-}"
    WORKER_REPLICAS="${WORKER_REPLICAS:-}"
    DOOMBERG_PLATFORM_DB_URL="${DOOMBERG_PLATFORM_DB_URL:-${DOOMBERG_PROD_URL:-}}"
    IBKR_ENGINE_ENABLED="${IBKR_ENGINE_ENABLED:-1}"
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
    DOOMBERG_PLATFORM_DB_URL="${DOOMBERG_PLATFORM_DB_URL:-${DOOMBERG_DEV_URL:-}}"
    # Dev shares the single customer-authenticated IBKR engine by default.
    # Set IBKR_ENGINE_ENABLED=1 explicitly only when intentionally testing an
    # isolated Client Portal/engine stack.
    IBKR_ENGINE_ENABLED="${IBKR_ENGINE_ENABLED:-0}"
    ;;
  *)
    echo "ERROR: DEPLOY_ENV must be prod or dev; got ${DEPLOY_ENV}" >&2
    exit 2
    ;;
esac

if [[ -z "${DOOMBERG_DB_ALLOW_FORWARD_MIGRATIONS+x}" ]]; then
  if [[ "${DEPLOY_ENV}" == "dev" ]]; then
    DOOMBERG_DB_ALLOW_FORWARD_MIGRATIONS="1"
  else
    DOOMBERG_DB_ALLOW_FORWARD_MIGRATIONS="0"
  fi
fi

MCP_ALLOWED_HOSTS="${MCP_ALLOWED_HOSTS:-${MCP_HOST},${MCP_HOST}:443}"
CLERK_ALLOWED_ORIGINS="${CLERK_ALLOWED_ORIGINS:-https://${APP_HOST}}"
if [[ -z "${APPLY_CADDY+x}" ]]; then
  if [[ "${DEPLOY_ENV}" == "${CADDY_APPLY_ENV:-prod}" ]]; then
    APPLY_CADDY="1"
  else
    APPLY_CADDY="0"
  fi
fi

node_count_for_workload() {
  local workload="$1"
  kubectl get nodes -l "workload=${workload}" --no-headers 2>/dev/null | awk 'END { print NR + 0 }'
}

default_replicas_for_workload() {
  local workload="$1"
  local count
  count="$(node_count_for_workload "${workload}")"
  if [[ "${count}" -ge 2 ]]; then
    echo "2"
  else
    echo "1"
  fi
}

dump_rollout_debug() {
  local status=$?
  if [[ "${status}" -eq 0 ]]; then
    return 0
  fi
  if [[ "${DEPLOY_DRY_RUN_MODE:-off}" != "off" ]]; then
    echo "ERROR: deploy dry-run failed before any manifests were applied" >&2
    exit "${status}"
  fi
  echo "ERROR: deploy failed; dumping Kubernetes rollout diagnostics" >&2
  for ns in "${K8S_GATEWAY_NAMESPACE}" "${K8S_WORKER_NAMESPACE}"; do
    echo "==> namespace ${ns}: deployments" >&2
    kubectl -n "${ns}" get deployments -o wide >&2 || true
    echo "==> namespace ${ns}: pods" >&2
    kubectl -n "${ns}" get pods -o wide >&2 || true
    echo "==> namespace ${ns}: recent warning events" >&2
    kubectl -n "${ns}" get events --sort-by=.lastTimestamp --field-selector type=Warning 2>/dev/null | tail -n 60 >&2 || true
  done
  for target in \
    "${K8S_GATEWAY_NAMESPACE}/deployment/doomberg-app" \
    "${K8S_GATEWAY_NAMESPACE}/deployment/ibkr-engine" \
    "${K8S_GATEWAY_NAMESPACE}/deployment/ibkr-gateway" \
    "${K8S_WORKER_NAMESPACE}/deployment/doomberg-workers"; do
    local ns="${target%%/*}"
    local deploy="${target#*/}"
    echo "==> describe ${ns}/${deploy}" >&2
    kubectl -n "${ns}" describe "${deploy}" >&2 || true
  done
  for container in rest-gateway control-plane mcp-gateway; do
    echo "==> doomberg-app ${container} logs" >&2
    kubectl -n "${K8S_GATEWAY_NAMESPACE}" logs deployment/doomberg-app -c "${container}" --tail=80 --prefix >&2 || true
  done
  echo "==> doomberg-workers logs" >&2
  kubectl -n "${K8S_WORKER_NAMESPACE}" logs deployment/doomberg-workers --all-containers --tail=80 --prefix >&2 || true
  exit "${status}"
}

trap dump_rollout_debug ERR

if [[ "${DEPLOY_ENV}" == "prod" ]]; then
  if [[ -z "${APP_REPLICAS}" ]]; then
    APP_REPLICAS="$(default_replicas_for_workload "${APP_NODE_WORKLOAD}")"
    echo "==> derived APP_REPLICAS=${APP_REPLICAS} from workload=${APP_NODE_WORKLOAD}"
  elif [[ -z "${APP_REPLICAS_EXPLICIT}" ]]; then
    echo "==> default APP_REPLICAS=${APP_REPLICAS}"
  fi
  if [[ -z "${WORKER_REPLICAS}" ]]; then
    WORKER_REPLICAS="$(default_replicas_for_workload "${WORKER_NODE_WORKLOAD}")"
    echo "==> derived WORKER_REPLICAS=${WORKER_REPLICAS} from workload=${WORKER_NODE_WORKLOAD}"
  elif [[ -z "${WORKER_REPLICAS_EXPLICIT}" ]]; then
    echo "==> default WORKER_REPLICAS=${WORKER_REPLICAS}"
  fi
fi

APP_MAX_SURGE="${APP_MAX_SURGE:-1}"
APP_MAX_UNAVAILABLE="${APP_MAX_UNAVAILABLE:-0}"
WORKER_MAX_SURGE="${WORKER_MAX_SURGE:-1}"
WORKER_MAX_UNAVAILABLE="${WORKER_MAX_UNAVAILABLE:-1}"
if [[ "${APP_REPLICAS}" -le 1 ]]; then
  APP_MAX_SURGE="${APP_MAX_SURGE_SINGLE:-0}"
  APP_MAX_UNAVAILABLE="${APP_MAX_UNAVAILABLE_SINGLE:-1}"
fi
if [[ "${WORKER_REPLICAS}" -le 1 ]]; then
  WORKER_MAX_SURGE="${WORKER_MAX_SURGE_SINGLE:-0}"
  WORKER_MAX_UNAVAILABLE="${WORKER_MAX_UNAVAILABLE_SINGLE:-1}"
fi

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
elif [[ "${DEPLOY_ENV}" == "dev" ]]; then
  DOOMBERG_IBKR_ENGINE_URL="${DOOMBERG_IBKR_ENGINE_URL:-http://ibkr-engine.${SHARED_IBKR_NAMESPACE}.svc.cluster.local:${IBKR_ENGINE_PORT}}"
  if [[ -z "${DOOMBERG_IBKR_ENGINE_TOKEN:-}" ]]; then
    DOOMBERG_IBKR_ENGINE_TOKEN="$(kubectl -n "${SHARED_IBKR_NAMESPACE}" get secret ibkr-engine \
      -o jsonpath='{.data.engine_token}' 2>/dev/null | base64 --decode || true)"
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
: "${DOOMBERG_SESSION_SECRET:?DOOMBERG_SESSION_SECRET must be set for ${DEPLOY_ENV}}"
: "${CLERK_ALLOWED_ORIGINS:?CLERK_ALLOWED_ORIGINS must be set for ${DEPLOY_ENV}}"
: "${CLERK_ISSUER:?CLERK_ISSUER must be set for ${DEPLOY_ENV}}"
if [[ -z "${CLERK_PEM_PUBLIC_KEY:-}" && -z "${CLERK_JWKS_URL:-}" ]]; then
  echo "ERROR: CLERK_PEM_PUBLIC_KEY or CLERK_JWKS_URL must be set for ${DEPLOY_ENV}" >&2
  exit 2
fi
if [[ -z "${DOOMBERG_IBKR_ENGINE_URL:-}" ]]; then
  echo "WARN: DOOMBERG_IBKR_ENGINE_URL is unset; trigger-engine worker will stay up, but active live-data trigger policies will report provider errors until configured." >&2
fi
if [[ "${DOOMBERG_ENABLE_LIVE_EXECUTION:-0}" == "1" && -z "${DOOMBERG_IBKR_ENGINE_URL:-}" ]]; then
  echo "ERROR: DOOMBERG_ENABLE_LIVE_EXECUTION=1 requires DOOMBERG_IBKR_ENGINE_URL" >&2
  exit 2
fi

DOOMBERG_ADAPTIVE_DASHBOARD_PROVIDER="${DOOMBERG_ADAPTIVE_DASHBOARD_PROVIDER:-modal}"
DOOMBERG_ADAPTIVE_DASHBOARD_MODEL="${DOOMBERG_ADAPTIVE_DASHBOARD_MODEL:-google/gemma-4-E4B-it}"
case "${DOOMBERG_ADAPTIVE_DASHBOARD_PROVIDER}" in
  modal|modal-openai)
    : "${DOOMBERG_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL:?DOOMBERG_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL must be set for ${DEPLOY_ENV}}"
    : "${DOOMBERG_ADAPTIVE_DASHBOARD_MODAL_KEY:?DOOMBERG_ADAPTIVE_DASHBOARD_MODAL_KEY must be set for ${DEPLOY_ENV}}"
    : "${DOOMBERG_ADAPTIVE_DASHBOARD_MODAL_SECRET:?DOOMBERG_ADAPTIVE_DASHBOARD_MODAL_SECRET must be set for ${DEPLOY_ENV}}"
    ;;
  openai|openai-compatible)
    : "${DOOMBERG_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL:?DOOMBERG_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL must be set for ${DEPLOY_ENV}}"
    : "${DOOMBERG_ADAPTIVE_DASHBOARD_API_KEY:?DOOMBERG_ADAPTIVE_DASHBOARD_API_KEY must be set for ${DEPLOY_ENV}}"
    ;;
  anthropic)
    : "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set when DOOMBERG_ADAPTIVE_DASHBOARD_PROVIDER=anthropic}"
    ;;
  *)
    echo "ERROR: unsupported DOOMBERG_ADAPTIVE_DASHBOARD_PROVIDER=${DOOMBERG_ADAPTIVE_DASHBOARD_PROVIDER}" >&2
    exit 2
    ;;
esac

render_manifest() {
  local file="$1"
  sed \
    -e "s|\${WORKER_IMAGE}|${WORKER_IMAGE}|g" \
    -e "s|\${IBKR_ENGINE_IMAGE}|${IBKR_ENGINE_IMAGE}|g" \
    -e "s|\${IBKR_GATEWAY_IMAGE}|${IBKR_GATEWAY_IMAGE:-}|g" \
    -e "s|\${DOOMBERG_ENV}|${DEPLOY_ENV}|g" \
    -e "s|\${DOOMBERG_DB_ALLOW_FORWARD_MIGRATIONS}|${DOOMBERG_DB_ALLOW_FORWARD_MIGRATIONS}|g" \
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
    -e "s|\${APP_MAX_SURGE}|${APP_MAX_SURGE}|g" \
    -e "s|\${APP_MAX_UNAVAILABLE}|${APP_MAX_UNAVAILABLE}|g" \
    -e "s|\${WORKER_MAX_SURGE}|${WORKER_MAX_SURGE}|g" \
    -e "s|\${WORKER_MAX_UNAVAILABLE}|${WORKER_MAX_UNAVAILABLE}|g" \
    -e "s|\${MCP_ALLOWED_HOSTS}|${MCP_ALLOWED_HOSTS}|g" \
    "${file}"
}

apply_manifest() {
  if [[ "${DEPLOY_DRY_RUN_MODE}" == "client" ]]; then
    kubectl apply --dry-run=client --validate=false -f -
  elif [[ "${DEPLOY_DRY_RUN_MODE}" == "server" ]]; then
    kubectl apply --dry-run=server -f -
  else
    kubectl apply -f -
  fi
}

create_ibkr_secret() {
  kubectl -n "${K8S_GATEWAY_NAMESPACE}" create secret generic ibkr-engine \
    --from-literal=engine_token="${DOOMBERG_IBKR_ENGINE_TOKEN:-}" \
    --from-literal=enable_live_execution="${DOOMBERG_ENABLE_LIVE_EXECUTION:-0}" \
    --dry-run=client -o yaml | apply_manifest
}

create_doomberg_secret() {
  local namespace="$1"
  kubectl -n "${namespace}" create secret generic doomberg-db \
    --from-literal=db_url="${DOOMBERG_PLATFORM_DB_URL}" \
    --from-literal=platform_url="${DOOMBERG_PLATFORM_DB_URL}" \
    --from-literal=session_secret="${DOOMBERG_SESSION_SECRET}" \
    --from-literal=clerk_pem_public_key="${CLERK_PEM_PUBLIC_KEY:-}" \
    --from-literal=clerk_jwks_url="${CLERK_JWKS_URL:-}" \
    --from-literal=clerk_allowed_origins="${CLERK_ALLOWED_ORIGINS:-}" \
    --from-literal=clerk_issuer="${CLERK_ISSUER:-}" \
    --from-literal=admin_token="${DOOMBERG_ADMIN_TOKEN:-}" \
    --from-literal=fmp_api_key="${FMP_API_KEY:-}" \
    --from-literal=databento_api_key="${DATABENTO_API_KEY:-}" \
    --from-literal=databento_dataset="${DATABENTO_DATASET:-XNAS.ITCH}" \
    --from-literal=data_source="${DOOMBERG_DATA_SOURCE:-auto}" \
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
    --dry-run=client -o yaml | apply_manifest
}

create_adaptive_dashboard_secret() {
  kubectl -n "${K8S_WORKER_NAMESPACE}" create secret generic doomberg-adaptive-dashboard \
    --from-literal=provider="${DOOMBERG_ADAPTIVE_DASHBOARD_PROVIDER}" \
    --from-literal=openai_base_url="${DOOMBERG_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL:-}" \
    --from-literal=api_key="${DOOMBERG_ADAPTIVE_DASHBOARD_API_KEY:-}" \
    --from-literal=modal_key="${DOOMBERG_ADAPTIVE_DASHBOARD_MODAL_KEY:-}" \
    --from-literal=modal_secret="${DOOMBERG_ADAPTIVE_DASHBOARD_MODAL_SECRET:-}" \
    --from-literal=model="${DOOMBERG_ADAPTIVE_DASHBOARD_MODEL}" \
    --from-literal=anthropic_api_key="${ANTHROPIC_API_KEY:-}" \
    --dry-run=client -o yaml | apply_manifest
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
if [[ "${DEPLOY_DRY_RUN_MODE}" != "off" ]]; then
  echo "==> deploy dry-run mode=${DEPLOY_DRY_RUN_MODE}; manifests will not be applied"
fi
if [[ "${IBKR_ENGINE_ENABLED}" == "1" ]]; then
  echo "==> ibkr enabled wrapper_image=${IBKR_ENGINE_IMAGE} gateway_image=${IBKR_GATEWAY_IMAGE} public_signin=${IBKR_SIGNIN_PUBLIC}"
elif [[ "${DEPLOY_ENV}" == "dev" ]]; then
  echo "==> ibkr shared namespace=${SHARED_IBKR_NAMESPACE} url=${DOOMBERG_IBKR_ENGINE_URL}"
fi
echo "==> replicas app=${APP_REPLICAS} workers=${WORKER_REPLICAS} node_workloads app=${APP_NODE_WORKLOAD} workers=${WORKER_NODE_WORKLOAD}"
echo "==> rollout app=maxSurge:${APP_MAX_SURGE},maxUnavailable:${APP_MAX_UNAVAILABLE} workers=maxSurge:${WORKER_MAX_SURGE},maxUnavailable:${WORKER_MAX_UNAVAILABLE}"

echo "==> namespaces"
render_manifest infra/k8s/namespace.yaml | apply_manifest

echo "==> secret doomberg-db (${DEPLOY_ENV}; values redacted)"
create_doomberg_secret "${K8S_GATEWAY_NAMESPACE}"
create_doomberg_secret "${K8S_WORKER_NAMESPACE}"
echo "==> secret doomberg-adaptive-dashboard (${DEPLOY_ENV}; worker namespace only; values redacted)"
create_adaptive_dashboard_secret
if [[ "${IBKR_ENGINE_ENABLED}" == "1" ]]; then
  echo "==> secret ibkr-engine (${DEPLOY_ENV}; values redacted)"
  create_ibkr_secret
fi

echo "==> worker network policy"
render_manifest infra/k8s/worker-networkpolicy.yaml | apply_manifest

if [[ "${IBKR_ENGINE_ENABLED}" == "1" ]]; then
  echo "==> ibkr engine manifests"
  render_manifest infra/k8s/ibkr-engine.yaml | apply_manifest
  render_manifest infra/k8s/ibkr-networkpolicy.yaml | apply_manifest
fi

echo "==> app manifests"
for file in infra/k8s/app-deployment.yaml infra/k8s/app-service.yaml infra/k8s/worker-deployment.yaml; do
  render_manifest "${file}" | apply_manifest
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
    render_manifest infra/k8s/caddy-ibkr-signin.yaml | apply_manifest
  else
    apply_manifest < infra/k8s/caddy.yaml
  fi
  after="$(caddy_checksum || true)"
  if [[ "${FORCE_CADDY_RESTART:-0}" == "1" || "${before}" != "${after}" ]]; then
    echo "==> caddy config changed; restarting caddy"
    if [[ "${DEPLOY_DRY_RUN_MODE}" == "off" ]]; then
      kubectl -n "${CADDY_NAMESPACE}" rollout restart deployment/caddy
    fi
  fi
  if [[ "${DEPLOY_DRY_RUN_MODE}" == "off" ]]; then
    kubectl -n "${CADDY_NAMESPACE}" rollout status deployment/caddy --timeout=300s
  fi
fi

if [[ "${DEPLOY_DRY_RUN_MODE}" != "off" ]]; then
  echo "==> ${DEPLOY_ENV} deploy dry-run validated: ${APP_HOST} / ${MCP_HOST}"
  exit 0
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
