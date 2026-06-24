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
#   backtest-runner  -> python -m doomberg_runtime.backtest_runner
#   live-runner      -> python -m doomberg_runtime.live_runner
#   platform-migrate -> python scripts/migrate_platform.py
#   archive-load     -> python scripts/import_v1_archive.py   (Stream 1's loader)
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
  backtest-runner)
    exec python -m doomberg_runtime.backtest_runner "$@"
    ;;
  live-runner)
    exec python -m doomberg_runtime.live_runner "$@"
    ;;
  platform-migrate)
    # Idempotent DDL for the platform system-of-record (SQLite local or Postgres prod).
    exec python scripts/migrate_platform.py "$@"
    ;;
  archive-load)
    # Stream 1's one-shot archive loader (seeds archive.* on first deploy).
    exec python scripts/import_v1_archive.py "$@"
    ;;
  archive-migrate)
    # Idempotent DDL: applies schema.sql (CREATE TABLE/INDEX IF NOT EXISTS) to the
    # live archive Postgres. Run as an init container before the app starts so new
    # tables appear automatically on every deploy without manual intervention.
    exec python scripts/migrate_archive.py "$@"
    ;;
  archive-load-short)
    # Weekly CronJob: populate archive.short_interest from yfinance for the universe.
    exec python scripts/load_short_interest.py "$@"
    ;;
  shell)
    exec /bin/bash "$@"
    ;;
  *)
    # Unknown role: treat the whole argv as a literal command.
    exec "${ROLE}" "$@"
    ;;
esac
