#!/usr/bin/env bash
# Entrypoint for the dedicated Ithaca IBKR engine image.
set -euo pipefail

ROLE="${1:-ibkr-engine}"
shift || true

CLIENT_PORTAL_HOME="${CLIENT_PORTAL_HOME:-/opt/clientportal}"
CLIENT_PORTAL_STATE="${CLIENT_PORTAL_STATE:-/opt/clientportal/root}"
CLIENT_PORTAL_TEMPLATE="${CLIENT_PORTAL_TEMPLATE:-/opt/clientportal-root-template}"

ensure_client_portal_state() {
  mkdir -p "${CLIENT_PORTAL_STATE}"
  if [[ ! -f "${CLIENT_PORTAL_STATE}/conf.yaml" ]]; then
    cp -a "${CLIENT_PORTAL_TEMPLATE}/." "${CLIENT_PORTAL_STATE}/"
  fi
  cp /usr/local/share/ithaca/ibkr-conf.yaml "${CLIENT_PORTAL_STATE}/conf.yaml"
}

case "${ROLE}" in
  ibkr-gateway)
    ensure_client_portal_state
    cd "${CLIENT_PORTAL_HOME}"
    exec ./bin/run.sh root/conf.yaml "$@"
    ;;
  ibkr-engine)
    exec python -m ithaca_ibkr_engine "$@"
    ;;
  shell)
    exec /bin/bash "$@"
    ;;
  *)
    exec "${ROLE}" "$@"
    ;;
esac
