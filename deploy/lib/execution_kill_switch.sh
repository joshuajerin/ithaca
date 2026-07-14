#!/usr/bin/env bash

# Resolve the deployment-level execution halt without ever turning an unknown
# existing value into "off". The resolved value is written to stdout; status
# messages stay on stderr so callers can safely use command substitution.
resolve_execution_kill_switch() {
  local namespace="$1"
  local dry_run_mode="$2"
  local requested="${ITHACA_EXECUTION_KILL_SWITCH:-}"
  local encoded=""

  if [[ -z "${requested}" && "${dry_run_mode}" == "off" ]]; then
    if ! encoded="$(
      kubectl -n "${namespace}" get secret ithaca-db \
        --ignore-not-found -o jsonpath='{.data.execution_kill_switch}'
    )"; then
      echo "ERROR: unable to read the existing execution kill-switch; refusing to default it off" >&2
      return 1
    fi
    if [[ -n "${encoded}" ]]; then
      if ! requested="$(printf '%s' "${encoded}" | openssl base64 -d -A)"; then
        echo "ERROR: unable to decode the existing execution kill-switch" >&2
        return 1
      fi
      echo "==> preserving existing execution kill-switch value" >&2
    fi
  fi

  requested="${requested:-0}"
  if [[ "${requested}" != "0" && "${requested}" != "1" ]]; then
    echo "ERROR: ITHACA_EXECUTION_KILL_SWITCH must be 0 or 1" >&2
    return 1
  fi
  printf '%s' "${requested}"
}
