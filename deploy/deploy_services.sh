#!/usr/bin/env bash
# Deploy the always-on Ithaca services into one environment namespace pair.
#
#   DEPLOY_ENV=dev IMAGE_TAG=dev-feature-a5fe2a0 deploy/deploy_services.sh
#   DEPLOY_ENV=prod deploy/deploy_services.sh a5fe2a0
#   DEPLOY_ENV=dev DEPLOY_DRY_RUN=client deploy/deploy_services.sh test-image
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
# shellcheck source=deploy/lib/execution_kill_switch.sh
source "${REPO_ROOT}/deploy/lib/execution_kill_switch.sh"

if [[ "${LOAD_LOCAL_ENV:-1}" != "0" && -f infra/terraform/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source infra/terraform/.env
  set +a
fi

DEPLOY_ENV="${DEPLOY_ENV:-prod}"
TAG="${IMAGE_TAG:-${1:-latest}}"
REGISTRY_NAME="${REGISTRY_NAME:-ithaca}"
WORKER_IMAGE="${WORKER_IMAGE:-registry.digitalocean.com/${REGISTRY_NAME}/ithaca:${TAG}}"
IBKR_ENGINE_IMAGE="${IBKR_ENGINE_IMAGE:-registry.digitalocean.com/${REGISTRY_NAME}/ithaca-ibkr-engine:${TAG}}"
CADDY_NAMESPACE="${CADDY_NAMESPACE:-ithaca-gateway}"
IBKR_ENGINE_PORT="${IBKR_ENGINE_PORT:-8090}"
IBKR_ENGINE_STORAGE_SIZE="${IBKR_ENGINE_STORAGE_SIZE:-2Gi}"
SHARED_IBKR_NAMESPACE="${SHARED_IBKR_NAMESPACE:-ithaca-gateway}"
IBKR_SIGNIN_PUBLIC="${IBKR_SIGNIN_PUBLIC:-0}"
IBKR_SIGNIN_HOST="${IBKR_SIGNIN_HOST:-ibkr.tradeithaca.com}"
IBKR_SIGNIN_REMOTE_IPS="${IBKR_SIGNIN_REMOTE_IPS:-0.0.0.0/0}"
ITHACA_LEGACY_ROOT_DOMAIN="${ITHACA_LEGACY_ROOT_DOMAIN:-legacy.invalid}"
ITHACA_LEGACY_KEY_PREFIX="${ITHACA_LEGACY_KEY_PREFIX:-}"
APP_REPLICAS_EXPLICIT="${APP_REPLICAS+x}"
WORKER_REPLICAS_EXPLICIT="${WORKER_REPLICAS+x}"
BACKTEST_REPLICAS_EXPLICIT="${BACKTEST_REPLICAS+x}"
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

if [[ -z "${BACKTEST_WORKER_ENABLED:-}" ]]; then
  if [[ "${DEPLOY_ENV}" == "dev" ]]; then
    BACKTEST_WORKER_ENABLED="1"
  else
    BACKTEST_WORKER_ENABLED="0"
  fi
fi
case "${BACKTEST_WORKER_ENABLED}" in
  0|1) ;;
  *)
    echo "ERROR: BACKTEST_WORKER_ENABLED must be 0 or 1; got ${BACKTEST_WORKER_ENABLED}" >&2
    exit 2
    ;;
esac
if [[ "${BACKTEST_WORKER_ENABLED}" == "1" ]]; then
  ITHACA_ENABLE_BACKTEST_LOOP="0"
else
  ITHACA_ENABLE_BACKTEST_LOOP="1"
fi

case "${DEPLOY_ENV}" in
  prod)
    K8S_GATEWAY_NAMESPACE="${K8S_GATEWAY_NAMESPACE:-ithaca-gateway}"
    K8S_WORKER_NAMESPACE="${K8S_WORKER_NAMESPACE:-ithaca-workers}"
    APP_HOST="${APP_HOST:-app.tradeithaca.com}"
    MCP_HOST="${MCP_HOST:-mcp.tradeithaca.com}"
    REST_NODE_PORT="${REST_NODE_PORT:-30080}"
    MCP_NODE_PORT="${MCP_NODE_PORT:-30808}"
    APP_NODE_WORKLOAD="${APP_NODE_WORKLOAD:-paper}"
    WORKER_NODE_WORKLOAD="${WORKER_NODE_WORKLOAD:-paper}"
    APP_REPLICAS="${APP_REPLICAS:-}"
    WORKER_REPLICAS="${WORKER_REPLICAS:-}"
    BACKTEST_REPLICAS="${BACKTEST_REPLICAS:-}"
    ITHACA_PLATFORM_DB_URL="${ITHACA_PLATFORM_DB_URL:-${ITHACA_PROD_URL:-}}"
    IBKR_ENGINE_ENABLED="${IBKR_ENGINE_ENABLED:-1}"
    ;;
  dev)
    K8S_GATEWAY_NAMESPACE="${K8S_GATEWAY_NAMESPACE:-ithaca-dev-gateway}"
    K8S_WORKER_NAMESPACE="${K8S_WORKER_NAMESPACE:-ithaca-dev-workers}"
    APP_HOST="${APP_HOST:-dev-app.tradeithaca.com}"
    MCP_HOST="${MCP_HOST:-dev-mcp.tradeithaca.com}"
    REST_NODE_PORT="${REST_NODE_PORT:-30082}"
    MCP_NODE_PORT="${MCP_NODE_PORT:-30810}"
    APP_NODE_WORKLOAD="${APP_NODE_WORKLOAD:-backtest}"
    WORKER_NODE_WORKLOAD="${WORKER_NODE_WORKLOAD:-backtest}"
    APP_REPLICAS="${APP_REPLICAS:-1}"
    WORKER_REPLICAS="${WORKER_REPLICAS:-1}"
    BACKTEST_REPLICAS="${BACKTEST_REPLICAS:-1}"
    ITHACA_PLATFORM_DB_URL="${ITHACA_PLATFORM_DB_URL:-${ITHACA_DEV_URL:-}}"
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

if [[ -z "${ITHACA_DB_ALLOW_FORWARD_MIGRATIONS+x}" ]]; then
  if [[ "${DEPLOY_ENV}" == "dev" ]]; then
    ITHACA_DB_ALLOW_FORWARD_MIGRATIONS="1"
  else
    ITHACA_DB_ALLOW_FORWARD_MIGRATIONS="0"
  fi
fi

MCP_ALLOWED_HOSTS="${MCP_ALLOWED_HOSTS:-${MCP_HOST},${MCP_HOST}:443,mcp.${ITHACA_LEGACY_ROOT_DOMAIN},mcp.${ITHACA_LEGACY_ROOT_DOMAIN}:443}"
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
    "${K8S_GATEWAY_NAMESPACE}/deployment/ithaca-app" \
    "${K8S_GATEWAY_NAMESPACE}/deployment/ibkr-engine" \
    "${K8S_GATEWAY_NAMESPACE}/deployment/ibkr-gateway" \
    "${K8S_WORKER_NAMESPACE}/deployment/ithaca-workers"; do
    local ns="${target%%/*}"
    local deploy="${target#*/}"
    echo "==> describe ${ns}/${deploy}" >&2
    kubectl -n "${ns}" describe "${deploy}" >&2 || true
  done
  for container in rest-gateway control-plane mcp-gateway; do
    echo "==> ithaca-app ${container} logs" >&2
    kubectl -n "${K8S_GATEWAY_NAMESPACE}" logs deployment/ithaca-app -c "${container}" --tail=80 --prefix >&2 || true
  done
  echo "==> ithaca-workers logs" >&2
  kubectl -n "${K8S_WORKER_NAMESPACE}" logs deployment/ithaca-workers --all-containers --tail=80 --prefix >&2 || true
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
  if [[ "${BACKTEST_WORKER_ENABLED}" != "1" ]]; then
    BACKTEST_REPLICAS="0"
  elif [[ -z "${BACKTEST_REPLICAS}" ]]; then
    BACKTEST_REPLICAS="$(default_replicas_for_workload backtest)"
    echo "==> derived BACKTEST_REPLICAS=${BACKTEST_REPLICAS} from workload=backtest"
  elif [[ -z "${BACKTEST_REPLICAS_EXPLICIT}" ]]; then
    echo "==> default BACKTEST_REPLICAS=${BACKTEST_REPLICAS}"
  fi
fi

# The app is intentionally constrained to the paper pool.  Do not require a
# third, temporary pod to be schedulable during a two-replica rollout: that
# pool can legitimately be full.  The app PDB keeps one healthy pod available
# while Kubernetes replaces the other one.
APP_MAX_SURGE="${APP_MAX_SURGE:-0}"
APP_MAX_UNAVAILABLE="${APP_MAX_UNAVAILABLE:-1}"
WORKER_MAX_SURGE="${WORKER_MAX_SURGE:-1}"
WORKER_MAX_UNAVAILABLE="${WORKER_MAX_UNAVAILABLE:-1}"
BACKTEST_MIN_REPLICAS="${BACKTEST_MIN_REPLICAS:-${BACKTEST_REPLICAS}}"
BACKTEST_MAX_REPLICAS="${BACKTEST_MAX_REPLICAS:-8}"
APP_MIN_AVAILABLE="${APP_MIN_AVAILABLE:-$([[ "${APP_REPLICAS}" -gt 1 ]] && echo 1 || echo 0)}"
WORKER_MIN_AVAILABLE="${WORKER_MIN_AVAILABLE:-$([[ "${WORKER_REPLICAS}" -gt 1 ]] && echo 1 || echo 0)}"
BACKTEST_MIN_AVAILABLE="${BACKTEST_MIN_AVAILABLE:-$([[ "${BACKTEST_REPLICAS}" -gt 1 ]] && echo 1 || echo 0)}"
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
  ITHACA_IBKR_ENGINE_URL="${ITHACA_IBKR_ENGINE_URL:-http://ibkr-engine.${K8S_GATEWAY_NAMESPACE}.svc.cluster.local:${IBKR_ENGINE_PORT}}"
  if [[ -z "${ITHACA_IBKR_ENGINE_TOKEN:-}" ]]; then
    ITHACA_IBKR_ENGINE_TOKEN="$(kubectl -n "${K8S_GATEWAY_NAMESPACE}" get secret ibkr-engine \
      -o jsonpath='{.data.engine_token}' 2>/dev/null | base64 --decode || true)"
  fi
  if [[ -z "${ITHACA_IBKR_ENGINE_TOKEN:-}" ]]; then
    ITHACA_IBKR_ENGINE_TOKEN="$(openssl rand -hex 32)"
  fi
  ITHACA_IBKR_QUOTE_PATH="${ITHACA_IBKR_QUOTE_PATH:-/quote?symbol={symbol}}"
  ITHACA_IBKR_HISTORY_PATH="${ITHACA_IBKR_HISTORY_PATH:-/history?symbol={symbol}}"
  ITHACA_IBKR_NEWS_PATH="${ITHACA_IBKR_NEWS_PATH:-/news}"
  ITHACA_IBKR_SCANNER_PATH="${ITHACA_IBKR_SCANNER_PATH:-/scanner}"
  ITHACA_IBKR_ACCOUNTS_PATH="${ITHACA_IBKR_ACCOUNTS_PATH:-/accounts}"
  ITHACA_IBKR_POSITIONS_PATH="${ITHACA_IBKR_POSITIONS_PATH:-/positions?account={account}}"
  ITHACA_IBKR_ORDERS_PATH="${ITHACA_IBKR_ORDERS_PATH:-/orders?account={account}}"
elif [[ "${DEPLOY_ENV}" == "dev" ]]; then
  ITHACA_IBKR_ENGINE_URL="${ITHACA_IBKR_ENGINE_URL:-http://ibkr-engine.${SHARED_IBKR_NAMESPACE}.svc.cluster.local:${IBKR_ENGINE_PORT}}"
  if [[ -z "${ITHACA_IBKR_ENGINE_TOKEN:-}" ]]; then
    ITHACA_IBKR_ENGINE_TOKEN="$(kubectl -n "${SHARED_IBKR_NAMESPACE}" get secret ibkr-engine \
      -o jsonpath='{.data.engine_token}' 2>/dev/null | base64 --decode || true)"
  fi
  ITHACA_IBKR_QUOTE_PATH="${ITHACA_IBKR_QUOTE_PATH:-/quote?symbol={symbol}}"
  ITHACA_IBKR_HISTORY_PATH="${ITHACA_IBKR_HISTORY_PATH:-/history?symbol={symbol}}"
  ITHACA_IBKR_NEWS_PATH="${ITHACA_IBKR_NEWS_PATH:-/news}"
  ITHACA_IBKR_SCANNER_PATH="${ITHACA_IBKR_SCANNER_PATH:-/scanner}"
  ITHACA_IBKR_ACCOUNTS_PATH="${ITHACA_IBKR_ACCOUNTS_PATH:-/accounts}"
  ITHACA_IBKR_POSITIONS_PATH="${ITHACA_IBKR_POSITIONS_PATH:-/positions?account={account}}"
  ITHACA_IBKR_ORDERS_PATH="${ITHACA_IBKR_ORDERS_PATH:-/orders?account={account}}"
fi

: "${ITHACA_PLATFORM_DB_URL:?ITHACA_PLATFORM_DB_URL must be set for ${DEPLOY_ENV}}"
: "${ITHACA_SESSION_SECRET:?ITHACA_SESSION_SECRET must be set for ${DEPLOY_ENV}}"
: "${CLERK_ALLOWED_ORIGINS:?CLERK_ALLOWED_ORIGINS must be set for ${DEPLOY_ENV}}"
: "${CLERK_ISSUER:?CLERK_ISSUER must be set for ${DEPLOY_ENV}}"
: "${CLERK_SECRET_KEY:?CLERK_SECRET_KEY must be set for Clerk-managed agent API keys}"
if [[ "${DEPLOY_ENV}" == "prod" && "${BACKTEST_WORKER_ENABLED}" == "1" ]]; then
  : "${ITHACA_ARTIFACT_BUCKET:?ITHACA_ARTIFACT_BUCKET must be set for production}"
  : "${ITHACA_ARTIFACT_ENDPOINT_URL:?ITHACA_ARTIFACT_ENDPOINT_URL must be set for production}"
  : "${ITHACA_ARTIFACT_ACCESS_KEY_ID:?ITHACA_ARTIFACT_ACCESS_KEY_ID must be set for production}"
  : "${ITHACA_ARTIFACT_SECRET_ACCESS_KEY:?ITHACA_ARTIFACT_SECRET_ACCESS_KEY must be set for production}"
fi
if [[ -z "${CLERK_PEM_PUBLIC_KEY:-}" && -z "${CLERK_JWKS_URL:-}" ]]; then
  echo "ERROR: CLERK_PEM_PUBLIC_KEY or CLERK_JWKS_URL must be set for ${DEPLOY_ENV}" >&2
  exit 2
fi
if [[ -z "${ITHACA_IBKR_ENGINE_URL:-}" ]]; then
  echo "WARN: ITHACA_IBKR_ENGINE_URL is unset; trigger-engine worker will stay up, but active live-data trigger policies will report provider errors until configured." >&2
fi
if [[ "${ITHACA_ENABLE_LIVE_EXECUTION:-0}" == "1" && -z "${ITHACA_IBKR_ENGINE_URL:-}" ]]; then
  echo "ERROR: ITHACA_ENABLE_LIVE_EXECUTION=1 requires ITHACA_IBKR_ENGINE_URL" >&2
  exit 2
fi

ITHACA_ADAPTIVE_DASHBOARD_PROVIDER="${ITHACA_ADAPTIVE_DASHBOARD_PROVIDER:-modal}"
ITHACA_ADAPTIVE_DASHBOARD_MODEL="${ITHACA_ADAPTIVE_DASHBOARD_MODEL:-google/gemma-4-E4B-it}"
case "${ITHACA_ADAPTIVE_DASHBOARD_PROVIDER}" in
  modal|modal-openai)
    : "${ITHACA_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL:?ITHACA_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL must be set for ${DEPLOY_ENV}}"
    : "${ITHACA_ADAPTIVE_DASHBOARD_MODAL_KEY:?ITHACA_ADAPTIVE_DASHBOARD_MODAL_KEY must be set for ${DEPLOY_ENV}}"
    : "${ITHACA_ADAPTIVE_DASHBOARD_MODAL_SECRET:?ITHACA_ADAPTIVE_DASHBOARD_MODAL_SECRET must be set for ${DEPLOY_ENV}}"
    ;;
  openai|openai-compatible)
    : "${ITHACA_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL:?ITHACA_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL must be set for ${DEPLOY_ENV}}"
    : "${ITHACA_ADAPTIVE_DASHBOARD_API_KEY:?ITHACA_ADAPTIVE_DASHBOARD_API_KEY must be set for ${DEPLOY_ENV}}"
    ;;
  anthropic)
    : "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set when ITHACA_ADAPTIVE_DASHBOARD_PROVIDER=anthropic}"
    ;;
  *)
    echo "ERROR: unsupported ITHACA_ADAPTIVE_DASHBOARD_PROVIDER=${ITHACA_ADAPTIVE_DASHBOARD_PROVIDER}" >&2
    exit 2
    ;;
esac

render_manifest() {
  local file="$1"
  sed \
    -e "s|\${WORKER_IMAGE}|${WORKER_IMAGE}|g" \
    -e "s|\${IBKR_ENGINE_IMAGE}|${IBKR_ENGINE_IMAGE}|g" \
    -e "s|\${IBKR_GATEWAY_IMAGE}|${IBKR_GATEWAY_IMAGE:-}|g" \
    -e "s|\${ITHACA_ENV}|${DEPLOY_ENV}|g" \
    -e "s|\${ITHACA_DB_ALLOW_FORWARD_MIGRATIONS}|${ITHACA_DB_ALLOW_FORWARD_MIGRATIONS}|g" \
    -e "s|\${K8S_GATEWAY_NAMESPACE}|${K8S_GATEWAY_NAMESPACE}|g" \
    -e "s|\${K8S_WORKER_NAMESPACE}|${K8S_WORKER_NAMESPACE}|g" \
    -e "s|\${CADDY_NAMESPACE}|${CADDY_NAMESPACE}|g" \
    -e "s|\${IBKR_ENGINE_PORT}|${IBKR_ENGINE_PORT}|g" \
    -e "s|\${IBKR_ENGINE_STORAGE_SIZE}|${IBKR_ENGINE_STORAGE_SIZE}|g" \
    -e "s|\${IBKR_SIGNIN_HOST}|${IBKR_SIGNIN_HOST}|g" \
    -e "s|\${IBKR_SIGNIN_REMOTE_IPS}|${IBKR_SIGNIN_REMOTE_IPS}|g" \
    -e "s|\${ITHACA_LEGACY_ROOT_DOMAIN}|${ITHACA_LEGACY_ROOT_DOMAIN}|g" \
    -e "s|\${REST_NODE_PORT}|${REST_NODE_PORT}|g" \
    -e "s|\${MCP_NODE_PORT}|${MCP_NODE_PORT}|g" \
    -e "s|\${APP_NODE_WORKLOAD}|${APP_NODE_WORKLOAD}|g" \
    -e "s|\${WORKER_NODE_WORKLOAD}|${WORKER_NODE_WORKLOAD}|g" \
    -e "s|\${APP_REPLICAS}|${APP_REPLICAS}|g" \
    -e "s|\${WORKER_REPLICAS}|${WORKER_REPLICAS}|g" \
    -e "s|\${BACKTEST_REPLICAS}|${BACKTEST_REPLICAS}|g" \
    -e "s|\${BACKTEST_MIN_REPLICAS}|${BACKTEST_MIN_REPLICAS}|g" \
    -e "s|\${BACKTEST_MAX_REPLICAS}|${BACKTEST_MAX_REPLICAS}|g" \
    -e "s|\${APP_MIN_AVAILABLE}|${APP_MIN_AVAILABLE}|g" \
    -e "s|\${WORKER_MIN_AVAILABLE}|${WORKER_MIN_AVAILABLE}|g" \
    -e "s|\${BACKTEST_MIN_AVAILABLE}|${BACKTEST_MIN_AVAILABLE}|g" \
    -e "s|\${ITHACA_ENABLE_BACKTEST_LOOP}|${ITHACA_ENABLE_BACKTEST_LOOP}|g" \
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

secret_checksum() {
  local namespace="$1"
  local secret="$2"
  kubectl -n "${namespace}" get secret "${secret}" \
    -o jsonpath='{.data}' 2>/dev/null | cksum | awk '{print $1 ":" $2}'
}

create_ibkr_secret() {
  kubectl -n "${K8S_GATEWAY_NAMESPACE}" create secret generic ibkr-engine \
    --from-literal=engine_token="${ITHACA_IBKR_ENGINE_TOKEN:-}" \
    --from-literal=enable_live_execution="${ITHACA_ENABLE_LIVE_EXECUTION:-0}" \
    --dry-run=client -o yaml | apply_manifest
}

create_ithaca_secret() {
  local namespace="$1"
  kubectl -n "${namespace}" create secret generic ithaca-db \
    --from-literal=db_url="${ITHACA_PLATFORM_DB_URL}" \
    --from-literal=platform_url="${ITHACA_PLATFORM_DB_URL}" \
    --from-literal=session_secret="${ITHACA_SESSION_SECRET}" \
    --from-literal=clerk_secret_key="${CLERK_SECRET_KEY}" \
    --from-literal=clerk_pem_public_key="${CLERK_PEM_PUBLIC_KEY:-}" \
    --from-literal=clerk_jwks_url="${CLERK_JWKS_URL:-}" \
    --from-literal=clerk_allowed_origins="${CLERK_ALLOWED_ORIGINS:-}" \
    --from-literal=clerk_issuer="${CLERK_ISSUER:-}" \
    --from-literal=admin_token="${ITHACA_ADMIN_TOKEN:-}" \
    --from-literal=fmp_api_key="${FMP_API_KEY:-}" \
    --from-literal=databento_api_key="${DATABENTO_API_KEY:-}" \
    --from-literal=databento_dataset="${DATABENTO_DATASET:-XNAS.ITCH}" \
    --from-literal=data_source="${ITHACA_DATA_SOURCE:-auto}" \
    --from-literal=ibkr_engine_url="${ITHACA_IBKR_ENGINE_URL:-}" \
    --from-literal=ibkr_engine_token="${ITHACA_IBKR_ENGINE_TOKEN:-}" \
    --from-literal=ibkr_quote_path="${ITHACA_IBKR_QUOTE_PATH:-}" \
    --from-literal=ibkr_history_path="${ITHACA_IBKR_HISTORY_PATH:-}" \
    --from-literal=ibkr_news_path="${ITHACA_IBKR_NEWS_PATH:-}" \
    --from-literal=ibkr_scanner_path="${ITHACA_IBKR_SCANNER_PATH:-}" \
    --from-literal=ibkr_order_path="${ITHACA_IBKR_ORDER_PATH:-}" \
    --from-literal=ibkr_accounts_path="${ITHACA_IBKR_ACCOUNTS_PATH:-}" \
    --from-literal=ibkr_positions_path="${ITHACA_IBKR_POSITIONS_PATH:-}" \
    --from-literal=ibkr_orders_path="${ITHACA_IBKR_ORDERS_PATH:-}" \
    --from-literal=enable_live_execution="${ITHACA_ENABLE_LIVE_EXECUTION:-0}" \
    --from-literal=execution_kill_switch="${ITHACA_EXECUTION_KILL_SWITCH:-0}" \
    --from-literal=execution_max_notional_usd="${ITHACA_EXECUTION_MAX_NOTIONAL_USD:-10000}" \
    --from-literal=execution_max_quantity="${ITHACA_EXECUTION_MAX_QUANTITY:-10000}" \
    --from-literal=execution_max_freshness_ms="${ITHACA_EXECUTION_MAX_FRESHNESS_MS:-10000}" \
    --from-literal=artifact_bucket="${ITHACA_ARTIFACT_BUCKET:-}" \
    --from-literal=artifact_endpoint_url="${ITHACA_ARTIFACT_ENDPOINT_URL:-}" \
    --from-literal=artifact_region="${ITHACA_ARTIFACT_REGION:-nyc3}" \
    --from-literal=artifact_access_key_id="${ITHACA_ARTIFACT_ACCESS_KEY_ID:-}" \
    --from-literal=artifact_secret_access_key="${ITHACA_ARTIFACT_SECRET_ACCESS_KEY:-}" \
    --from-literal=legacy_key_prefix="${ITHACA_LEGACY_KEY_PREFIX}" \
    --dry-run=client -o yaml | apply_manifest
}

create_adaptive_dashboard_secret() {
  kubectl -n "${K8S_WORKER_NAMESPACE}" create secret generic ithaca-adaptive-dashboard \
    --from-literal=provider="${ITHACA_ADAPTIVE_DASHBOARD_PROVIDER}" \
    --from-literal=openai_base_url="${ITHACA_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL:-}" \
    --from-literal=api_key="${ITHACA_ADAPTIVE_DASHBOARD_API_KEY:-}" \
    --from-literal=modal_key="${ITHACA_ADAPTIVE_DASHBOARD_MODAL_KEY:-}" \
    --from-literal=modal_secret="${ITHACA_ADAPTIVE_DASHBOARD_MODAL_SECRET:-}" \
    --from-literal=model="${ITHACA_ADAPTIVE_DASHBOARD_MODEL}" \
    --from-literal=anthropic_api_key="${ANTHROPIC_API_KEY:-}" \
    --dry-run=client -o yaml | apply_manifest
}

ensure_metrics_server() {
  if [[ "${DEPLOY_DRY_RUN_MODE:-off}" != "off" ]]; then
    echo "==> deploy dry-run: skipping metrics-server installation"
    return 0
  fi
  if kubectl get apiservice v1beta1.metrics.k8s.io >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${INSTALL_METRICS_SERVER:-1}" != "1" ]]; then
    echo "ERROR: metrics-server is required by the backtest HPA" >&2
    return 1
  fi
  command -v doctl >/dev/null 2>&1 || {
    echo "ERROR: doctl is required to install the DOKS metrics-server add-on" >&2
    return 1
  }
  local cluster_id="${DOKS_CLUSTER_ID:-}"
  if [[ -z "${cluster_id}" ]]; then
    local context cluster_name
    context="$(kubectl config current-context)"
    cluster_name="${context#do-*-}"
    cluster_id="$(doctl kubernetes cluster list --format ID,Name --no-header | awk -v name="${cluster_name}" '$2 == name {print $1; exit}')"
  fi
  [[ -n "${cluster_id}" ]] || {
    echo "ERROR: set DOKS_CLUSTER_ID so metrics-server can be installed" >&2
    return 1
  }
  echo "==> installing DOKS metrics-server add-on"
  doctl kubernetes 1-click install "${cluster_id}" --1-clicks metrics-server
  local i
  for i in $(seq 1 36); do
    if kubectl get --raw /apis/metrics.k8s.io/v1beta1 >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  echo "ERROR: metrics-server did not become ready within 180 seconds" >&2
  return 1
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
  echo "==> ibkr shared namespace=${SHARED_IBKR_NAMESPACE} url=${ITHACA_IBKR_ENGINE_URL}"
fi
echo "==> replicas app=${APP_REPLICAS} workers=${WORKER_REPLICAS} backtest=${BACKTEST_REPLICAS} node_workloads app=${APP_NODE_WORKLOAD} workers=${WORKER_NODE_WORKLOAD} backtest=backtest"
echo "==> rollout app=maxSurge:${APP_MAX_SURGE},maxUnavailable:${APP_MAX_UNAVAILABLE} workers=maxSurge:${WORKER_MAX_SURGE},maxUnavailable:${WORKER_MAX_UNAVAILABLE}"

echo "==> namespaces"
render_manifest infra/k8s/namespace.yaml | apply_manifest

if [[ "${BACKTEST_WORKER_ENABLED}" == "1" ]]; then
  ensure_metrics_server
else
  echo "==> dedicated backtest workers disabled; keeping embedded backtest loop enabled"
fi

echo "==> secret ithaca-db (${DEPLOY_ENV}; values redacted)"
if ! ITHACA_EXECUTION_KILL_SWITCH="$(
  resolve_execution_kill_switch "${K8S_GATEWAY_NAMESPACE}" "${DEPLOY_DRY_RUN_MODE}"
)"; then
  exit 1
fi
gateway_db_secret_before="$(secret_checksum "${K8S_GATEWAY_NAMESPACE}" ithaca-db || true)"
worker_db_secret_before="$(secret_checksum "${K8S_WORKER_NAMESPACE}" ithaca-db || true)"
create_ithaca_secret "${K8S_GATEWAY_NAMESPACE}"
create_ithaca_secret "${K8S_WORKER_NAMESPACE}"
gateway_db_secret_after="$(secret_checksum "${K8S_GATEWAY_NAMESPACE}" ithaca-db || true)"
worker_db_secret_after="$(secret_checksum "${K8S_WORKER_NAMESPACE}" ithaca-db || true)"
echo "==> secret ithaca-adaptive-dashboard (${DEPLOY_ENV}; worker namespace only; values redacted)"
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
for file in infra/k8s/app-deployment.yaml infra/k8s/app-service.yaml infra/k8s/worker-deployment.yaml infra/k8s/disruption-budgets.yaml; do
  render_manifest "${file}" | apply_manifest
done
if [[ "${BACKTEST_WORKER_ENABLED}" == "1" ]]; then
  render_manifest infra/k8s/backtest-worker-deployment.yaml | apply_manifest
fi

if [[ "${DEPLOY_DRY_RUN_MODE}" == "off" ]]; then
  if [[ "${gateway_db_secret_before}" != "${gateway_db_secret_after}" ]]; then
    echo "==> ithaca-db secret changed; restarting app pods"
    kubectl -n "${K8S_GATEWAY_NAMESPACE}" rollout restart deployment/ithaca-app
  fi
  if [[ "${worker_db_secret_before}" != "${worker_db_secret_after}" ]]; then
    echo "==> ithaca-db secret changed; restarting worker pods"
    kubectl -n "${K8S_WORKER_NAMESPACE}" rollout restart deployment/ithaca-workers
  fi
fi

caddy_checksum() {
  kubectl -n "${CADDY_NAMESPACE}" get configmap caddy-config \
    -o jsonpath='{.data.Caddyfile}' 2>/dev/null | cksum | awk '{print $1 ":" $2}'
}

if [[ "${APPLY_CADDY:-1}" == "1" ]]; then
  echo "==> caddy public ingress"
  before="$(caddy_checksum || true)"
  caddy_manifest="infra/k8s/caddy.yaml"
  if [[ "${IBKR_SIGNIN_PUBLIC}" == "1" ]]; then
    echo "WARN: applying temporary public IBKR sign-in route host=${IBKR_SIGNIN_HOST} remote_ip=${IBKR_SIGNIN_REMOTE_IPS}" >&2
    caddy_manifest="infra/k8s/caddy-ibkr-signin.yaml"
  fi
  # During the Doomberg-to-Ithaca migration, Caddy itself remains in the
  # legacy gateway namespace. Its existing Deployment selector is immutable,
  # so update just the ConfigMap rather than attempting to replace the Caddy
  # Deployment, Service, and PVC. Fresh installations still receive all of
  # those resources from the full manifest.
  if kubectl -n "${CADDY_NAMESPACE}" get deployment caddy >/dev/null 2>&1; then
    render_manifest "${caddy_manifest}" | sed '/^---$/,$d' | apply_manifest
  else
    render_manifest "${caddy_manifest}" | apply_manifest
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
kubectl -n "${K8S_GATEWAY_NAMESPACE}" rollout status deployment/ithaca-app --timeout=300s
kubectl -n "${K8S_WORKER_NAMESPACE}" rollout status deployment/ithaca-workers --timeout=300s
if [[ "${BACKTEST_WORKER_ENABLED}" == "1" ]]; then
  kubectl -n "${K8S_WORKER_NAMESPACE}" rollout status deployment/ithaca-backtest-workers --timeout=300s
fi

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
verify_deployment_images "${K8S_GATEWAY_NAMESPACE}" ithaca-app
verify_deployment_images "${K8S_WORKER_NAMESPACE}" ithaca-workers
if [[ "${BACKTEST_WORKER_ENABLED}" == "1" ]]; then
  verify_deployment_images "${K8S_WORKER_NAMESPACE}" ithaca-backtest-workers
fi

echo "==> pods"
kubectl -n "${K8S_GATEWAY_NAMESPACE}" get pods -o wide
kubectl -n "${K8S_WORKER_NAMESPACE}" get pods -o wide
echo "==> ${DEPLOY_ENV} deployed: ${APP_HOST} / ${MCP_HOST}"
