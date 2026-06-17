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
#   backtest-runner  -> python -m doomberg_runtime.backtest_runner
#   live-runner      -> python -m doomberg_runtime.live_runner
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
    exec uvicorn doomberg_rest.app:app --host "${HOST}" --port "${REST_PORT}" "$@"
    ;;
  control-plane)
    exec uvicorn doomberg_control.app:app --host "${HOST}" --port "${CONTROL_PORT}" "$@"
    ;;
  conductor)
    # The deploy-layer conductor: pulls the backtest queue + ticks paper deploys.
    exec python scripts/run_workers.py "$@"
    ;;
  backtest-runner)
    exec python -m doomberg_runtime.backtest_runner "$@"
    ;;
  live-runner)
    exec python -m doomberg_runtime.live_runner "$@"
    ;;
  archive-load)
    # Stream 1's one-shot archive loader (seeds archive.* on first deploy).
    exec python scripts/import_v1_archive.py "$@"
    ;;
  shell)
    exec /bin/bash "$@"
    ;;
  *)
    # Unknown role: treat the whole argv as a literal command.
    exec "${ROLE}" "$@"
    ;;
esac
