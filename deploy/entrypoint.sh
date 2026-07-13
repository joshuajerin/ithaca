#!/usr/bin/env bash
# Role dispatcher for the single doomberg image. The first arg selects the
# service; everything after it is appended to the underlying command so you can
# pass flags (e.g. `rest-gateway --port 9000` won't work directly — use env, see
# below — but extra uvicorn args after the known ones are forwarded).
#
# Roles:
#   mcp-gateway      -> python -m doomberg_mcp
#   rest-gateway     -> uvicorn doomberg_rest.app:app
#   control-plane    -> uvicorn doomberg_control.app:app
#   conductor        -> python scripts/run_workers.py   (backtest worker + paper scheduler)
#   trigger-engine   -> python -m doomberg_runtime.trigger_engine
#   adaptive-dashboard -> python scripts/recompute_adaptive_dashboards.py
#   backtest-runner  -> python -m doomberg_runtime.backtest_runner
#   backtest-worker  -> python scripts/run_backtest_workers.py
#   live-runner      -> python -m doomberg_runtime.live_runner
#   platform-migrate -> python scripts/migrate_platform.py
#   ibkr-smoke       -> python scripts/ibkr_smoke.py
#   launch-gate      -> python scripts/launch_gate.py
#   shell            -> exec a shell (debug)
#
# If the first arg is not a known role, exec it verbatim (so the image still
# behaves like a normal container: `docker run ... python -c ...`).
set -euo pipefail

ROLE="${1:-conductor}"
shift || true

# Bind hosts/ports are configurable via env so the same image serves anywhere.
HOST="${DOOMBERG_BIND_HOST:-0.0.0.0}"
REST_PORT="${DOOMBERG_REST_PORT:-8000}"
CONTROL_PORT="${DOOMBERG_CONTROL_PORT:-8001}"
MCP_PORT="${DOOMBERG_MCP_PORT:-8080}"

case "${ROLE}" in
  mcp-gateway)
    # MCP server (stdio by default; honors its own transport env).
    exec python -m doomberg_mcp "$@"
    ;;
  rest-gateway)
    # Tell the gateway where the baked-in web dist lives (serves the React UI at /).
    export DOOMBERG_WEB_DIST="${DOOMBERG_WEB_DIST:-/app/web/dist}"
    exec uvicorn doomberg_rest.app:app --host "${HOST}" --port "${REST_PORT}" "$@"
    ;;
  control-plane)
    exec uvicorn doomberg_control.app:app --host "${HOST}" --port "${CONTROL_PORT}" "$@"
    ;;
  conductor)
    # The deploy-layer conductor: pulls the backtest queue + ticks paper deploys.
    exec python scripts/run_workers.py "$@"
    ;;
  trigger-engine)
    # Poll active trigger policies and create durable runs from live provider events.
    exec python -m doomberg_runtime.trigger_engine "$@"
    ;;
  adaptive-dashboard)
    # Manual/backfill adaptive dashboard recompute.
    exec python scripts/recompute_adaptive_dashboards.py "$@"
    ;;
  backtest-runner)
    exec python -m doomberg_runtime.backtest_runner "$@"
    ;;
  backtest-worker)
    exec python scripts/run_backtest_workers.py "$@"
    ;;
  live-runner)
    exec python -m doomberg_runtime.live_runner "$@"
    ;;
  platform-migrate)
    # Idempotent DDL for the platform system-of-record (SQLite local or Postgres prod).
    exec python scripts/migrate_platform.py "$@"
    ;;
  ibkr-smoke)
    # Read-only provider handoff check. Does not touch broker order endpoints.
    exec python scripts/ibkr_smoke.py "$@"
    ;;
  launch-gate)
    # Customer-handoff readiness gate over DB, REST, MCP auth, artifacts, SSE, and providers.
    exec python scripts/launch_gate.py "$@"
    ;;
  shell)
    exec /bin/bash "$@"
    ;;
  *)
    # Unknown role: treat the whole argv as a literal command.
    exec "${ROLE}" "$@"
    ;;
esac
