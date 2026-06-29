#!/usr/bin/env bash
# GitHub Actions self-hosted runner autoscaler for DigitalOcean.
#
# Runs as a systemd timer on the controller droplet. Polls GitHub for queued
# jobs and spins up ephemeral DO droplets on demand. Cleans up finished ones.
#
# Config (env or /etc/runner-autoscaler.env):
#   DO_TOKEN            — DigitalOcean API token
#   GH_PAT              — GitHub personal access token (repo scope)
#   REPOS               — space-separated list of repos (e.g. "joshuajerin/doomberg joshuajerin/ithaca-docs")
#   SSH_KEY_ID          — DO SSH key ID to inject into ephemeral droplets
#   DROPLET_SIZE        — DO droplet slug (default: s-2vcpu-4gb)
#   DROPLET_REGION      — DO region (default: nyc1)
#   MAX_RUNNERS         — max concurrent ephemeral runners (default: 4)
#   BASE_RUNNER droplet — name of the persistent base runner (excluded from cleanup)

set -eo pipefail

# grep returns 1 when no matches — don't let that kill the script
grep() { command grep "$@" || true; }

CONFIG_FILE="/etc/runner-autoscaler.env"
[ -f "$CONFIG_FILE" ] && source "$CONFIG_FILE"

DO_TOKEN="${DO_TOKEN:?DO_TOKEN not set}"
GH_PAT="${GH_PAT:?GH_PAT not set}"
REPOS="${REPOS:?REPOS not set}"
SSH_KEY_ID="${SSH_KEY_ID:?SSH_KEY_ID not set}"
DROPLET_SIZE="${DROPLET_SIZE:-s-2vcpu-4gb}"
DROPLET_REGION="${DROPLET_REGION:-nyc1}"
MAX_RUNNERS="${MAX_RUNNERS:-4}"
BASE_RUNNER="${BASE_RUNNER:-runner}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_DATA_SCRIPT="$SCRIPT_DIR/runner-ephemeral.sh"

log() { echo "[autoscaler] $(date -u +%H:%M:%S) $*"; }

# Count currently active ephemeral droplets (only active/new, not off)
count_ephemeral() {
  doctl compute droplet list --format Name,Status --no-header 2>/dev/null | \
    grep "ephemeral-" | grep -v "off" | wc -l
}

# Get queued jobs count for a repo
get_queued_count() {
  local repo="$1"
  curl -sf -H "Authorization: token $GH_PAT" \
    "https://api.github.com/repos/$repo/actions/runs?status=queued&per_page=100" | \
    jq '.workflow_runs | length'
}

# Get a registration token for a repo
get_reg_token() {
  local repo="$1"
  curl -sf -X POST -H "Authorization: token $GH_PAT" \
    "https://api.github.com/repos/$repo/actions/runners/registration-token" | \
    jq -r '.token'
}

# Create an ephemeral droplet
create_runner() {
  local repo="$1"
  local name="ephemeral-$(date +%s)-$((RANDOM % 1000))"
  local token
  token=$(get_reg_token "$repo")

  log "Creating ephemeral runner $name for $repo"

  # Write user-data to a temp file (doctl needs a file path)
  local tmp_script
  tmp_script=$(mktemp)
  sed "s|__REPO__|$repo|g; s|__TOKEN__|$token|g; s|__NAME__|$name|g" \
    < "$USER_DATA_SCRIPT" > "$tmp_script"

  doctl compute droplet create "$name" \
    --size "$DROPLET_SIZE" \
    --image ubuntu-24-04-x64 \
    --region "$DROPLET_REGION" \
    --ssh-keys "$SSH_KEY_ID" \
    --tag-names "ephemeral-runner,$repo" \
    --enable-private-networking \
    --user-data-file "$tmp_script" \
    --wait 2>&1 | tail -1

  rm -f "$tmp_script"

  log "Created $name"
}

# Clean up powered-off ephemeral droplets
cleanup() {
  local stale
  stale=$(doctl compute droplet list --format ID,Name,Status --no-header 2>/dev/null | \
    grep "ephemeral-" | awk '$3 == "off" { print $1 }')

  if [ -n "$stale" ]; then
    for id in $stale; do
      log "Cleaning up powered-off droplet $id"
      doctl compute droplet delete "$id" --force 2>/dev/null || true
    done
  fi

  # Also clean up droplets that have been running > 30 min (stuck)
  local now
  now=$(date +%s)
  doctl compute droplet list --format ID,Name,Status,Created --no-header 2>/dev/null | \
    grep "ephemeral-" | grep -v "off" | while IFS=$'\t' read -r id name status created; do
      local created_ts
      created_ts=$(date -d "$created" +%s 2>/dev/null || echo 0)
      local age=$((now - created_ts))
      if [ "$age" -gt 1800 ]; then
        log "Force-cleaning stale droplet $name (age ${age}s)"
        doctl compute droplet delete "$id" --force 2>/dev/null || true
      fi
    done
}

# Main loop
main() {
  cleanup

  local current
  current=$(count_ephemeral)
  log "Current ephemeral runners: $current / $MAX_RUNNERS"

  if [ "$current" -ge "$MAX_RUNNERS" ]; then
    log "At max capacity, skipping"
    return
  fi

  local total_queued=0
  local repo_with_most_queued=""
  local most_queued=0

  for repo in $REPOS; do
    local queued
    queued=$(get_queued_count "$repo")
    total_queued=$((total_queued + queued))
    if [ "$queued" -gt "$most_queued" ]; then
      most_queued="$queued"
      repo_with_most_queued="$repo"
    fi
    log "  $repo: $queued queued"
  done

  log "Total queued jobs: $total_queued"

  if [ "$total_queued" -eq 0 ]; then
    log "No queued jobs, skipping"
    return
  fi

  # Spin up runners for the most backlogged repo
  local to_create=$((MAX_RUNNERS - current))
  if [ "$to_create" -gt "$most_queued" ]; then
    to_create="$most_queued"
  fi

  for i in $(seq 1 "$to_create"); do
    create_runner "$repo_with_most_queued"
    sleep 5  # stagger creation
  done

  log "Created $to_create new runners"
}

main
