#!/usr/bin/env bash
# Concurrency / load check for the API Server.
#
# Boots the FastAPI app the same way the workflow does, waits for readiness, then
# runs scripts/loadtest_api.py to drive many simultaneous users across multiple
# firms against the hot paths. Establishes a latency baseline and asserts the
# externalized session state is durable and firm-isolated under concurrency.
#
# Tunables (env): LOAD_FIRMS, LOAD_ROUNDS, LOAD_CONCURRENCY. Latency: per-endpoint
# p95 budgets default sensibly and are overridable via LOAD_BUDGET_<LABEL>_MS (or
# the fallback LOAD_LATENCY_BUDGET_MS); set LOAD_GATE_LATENCY=1 to turn the latency
# report into a hard gate (only when driving over loopback, as this script does).
set -uo pipefail

PORT="${LOAD_PORT:-8138}"
BASE="http://127.0.0.1:${PORT}"
LOG="$(mktemp)"
SERVER_PID=""

cleanup() {
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null
    wait "${SERVER_PID}" 2>/dev/null
  fi
  rm -f "${LOG}"
}
trap cleanup EXIT

echo "Starting API Server on port ${PORT} (live .pythonlibs env) ..."
# Skip the continuous live-ingestion worker so the load test measures the
# request path (which serves off persisted/seeded data), not background fetches.
TERMINAL_SKIP_WORKER=1 python -m uvicorn app.main:app \
  --host 127.0.0.1 --port "${PORT}" \
  --app-dir artifacts/api-server >"${LOG}" 2>&1 &
SERVER_PID=$!

# Wait for boot.
HEALTHY=0
for _ in $(seq 1 60); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    echo "ERROR: API Server process exited during startup."
    echo "----- server log -----"; cat "${LOG}"
    exit 1
  fi
  code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/healthz" || true)"
  if [[ "${code}" == "200" ]]; then HEALTHY=1; break; fi
  sleep 1
done
if [[ "${HEALTHY}" != "1" ]]; then
  echo "ERROR: API Server did not become healthy within timeout."
  echo "----- server log -----"; cat "${LOG}"
  exit 1
fi
echo "Health check OK. Running load driver ..."

BASE="${BASE}" python scripts/loadtest_api.py
RC=$?

if [[ "${RC}" != "0" ]]; then
  echo "----- server log (tail) -----"
  tail -n 40 "${LOG}"
fi
exit "${RC}"
