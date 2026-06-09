#!/usr/bin/env bash
# Smoke check for the API Server.
#
# Boots the FastAPI app exactly the way the workflow does (same `python -m uvicorn`
# command against the live .pythonlibs environment), waits for it to come up, and
# asserts that POST /api/orchestrate serves a 200. This catches the whole class of
# "server can't boot" failures before they ship: missing/uninstalled Python deps
# (ModuleNotFoundError), import errors, and broken startup/lifespan code.
set -uo pipefail

PORT="${SMOKE_PORT:-8137}"
BASE="http://127.0.0.1:${PORT}"
LOG="$(mktemp)"
BODY="$(mktemp)"
SERVER_PID=""

cleanup() {
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null
    wait "${SERVER_PID}" 2>/dev/null
  fi
  rm -f "${LOG}" "${BODY}"
}
trap cleanup EXIT

echo "Starting API Server on port ${PORT} (live .pythonlibs env) ..."
# Skip the continuous live-ingestion worker: a boot check verifies the server
# imports, boots and serves a request — it should not kick off hundreds of
# background network calls. The request path still works off persisted data.
TERMINAL_SKIP_WORKER=1 python -m uvicorn app.main:app \
  --host 127.0.0.1 --port "${PORT}" \
  --app-dir artifacts/api-server >"${LOG}" 2>&1 &
SERVER_PID=$!

# Wait for the server to boot and answer health checks.
HEALTHY=0
for _ in $(seq 1 60); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    echo "ERROR: API Server process exited during startup (import or boot failure)."
    echo "----- server log -----"
    cat "${LOG}"
    exit 1
  fi
  code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/healthz" || true)"
  if [[ "${code}" == "200" ]]; then
    HEALTHY=1
    break
  fi
  sleep 1
done

if [[ "${HEALTHY}" != "1" ]]; then
  echo "ERROR: API Server did not become healthy within timeout."
  echo "----- server log -----"
  cat "${LOG}"
  exit 1
fi
echo "Health check OK."

# The whole business API is gated behind a session (multi-tenant auth), so the
# boot check must authenticate first. Sign up a throwaway firm/admin and grab the
# session token. The cookie is Secure (not echoed back over plain http), so we
# present the token via the supported `Authorization: Bearer` header instead.
echo "POST /api/auth/signup ..."
HDRS="$(mktemp)"
SUFFIX="$$_$(date +%s)"
signup_status="$(curl -s -o "${BODY}" -D "${HDRS}" -w '%{http_code}' \
  -X POST "${BASE}/api/auth/signup" \
  -H 'Content-Type: application/json' \
  --max-time 30 \
  -d "{\"firmName\":\"Smoke Firm ${SUFFIX}\",\"name\":\"Smoke Admin\",\"email\":\"smoke_${SUFFIX}@example.com\",\"password\":\"smoke-pass-123\"}" || true)"

if [[ "${signup_status}" != "200" ]]; then
  echo "ERROR: POST /api/auth/signup returned ${signup_status} (expected 200)."
  echo "----- response body -----"; cat "${BODY}"; echo
  echo "----- server log -----"; cat "${LOG}"
  rm -f "${HDRS}"
  exit 1
fi

# Pull the session token out of the Set-Cookie: at_session=<token>; ... header.
TOKEN="$(grep -i '^set-cookie:' "${HDRS}" | sed -n 's/.*at_session=\([^;]*\).*/\1/p' | head -n1)"
rm -f "${HDRS}"
if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: could not extract at_session token from signup response."
  echo "----- server log -----"; cat "${LOG}"
  exit 1
fi
echo "Signup OK (session established)."

# Assert the orchestrate endpoint serves a 200. This exercises the full request
# path (model imports, skill harness, data layer), not just a bare health route.
echo "POST /api/orchestrate ..."
status="$(curl -s -o "${BODY}" -w '%{http_code}' \
  -X POST "${BASE}/api/orchestrate" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${TOKEN}" \
  --max-time 90 \
  -d '{"query":"Give me a market overview of what is moving today"}' || true)"

if [[ "${status}" != "200" ]]; then
  echo "ERROR: POST /api/orchestrate returned ${status} (expected 200)."
  echo "----- response body -----"
  cat "${BODY}"
  echo
  echo "----- server log -----"
  cat "${LOG}"
  exit 1
fi

echo "POST /api/orchestrate returned 200. Smoke check passed."
exit 0
