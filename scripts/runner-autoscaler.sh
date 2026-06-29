#!/usr/bin/env bash
# GitHub Actions self-hosted runner autoscaler for DigitalOcean.
#
# Runs as a systemd timer on the controller droplet. Polls GitHub for queued
# jobs and spins up ephemeral DO droplets on demand. Cleans up finished ones.
#
# Config (env or /etc/runner-autoscaler.env):
#   DO_TOKEN            — DigitalOcean API token
#   GH_PAT              — GitHub personal access token (repo scope)
#   REPOS               — space-separated list of repos
#   SSH_KEY_ID          — DO SSH key ID to inject into ephemeral droplets
#   DROPLET_SIZE        — DO droplet slug (default: s-4vcpu-8gb)
#   DROPLET_REGION      — DO region (default: nyc1)
#   MAX_RUNNERS         — max concurrent ephemeral runners (default: 6)
#   SNAPSHOT_ID         — DO snapshot ID with pre-installed tools
#   BASE_RUNNER         — name of the persistent base runner (excluded from cleanup)

set -eo pipefail

# grep returns 1 when no matches — don't let that kill the script
grep() { command grep "$@" || true; }

CONFIG_FILE="/etc/runner-autoscaler.env"
[ -f "$CONFIG_FILE" ] && source "$CONFIG_FILE"

DO_TOKEN="${DO_TOKEN:?DO_TOKEN not set}"
GH_PAT="${GH_PAT:?GH_PAT not set}"
REPOS="${REPOS:?REPOS not set}"
SSH_KEY_ID="${SSH_KEY_ID:?SSH_KEY_ID not set}"
DROPLET_SIZE="${DROPLET_SIZE:-s-4vcpu-8gb}"
DROPLET_REGION="${DROPLET_REGION:-nyc1}"
MAX_RUNNERS="${MAX_RUNNERS:-6}"
SNAPSHOT_ID="${SNAPSHOT_ID:-234895636}"
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
  curl -sf --max-time 10 -H "Authorization: token $GH_PAT" \
    "https://api.github.com/repos/$repo/actions/runs?status=queued&per_page=100" | \
    jq '.workflow_runs | length' 2>/dev/null || echo 0
}

# Get a registration token for a repo
get_reg_token() {
  local repo="$1"
  curl -sf --max-time 10 -X POST -H "Authorization: token $GH_PAT" \
    "https://api.github.com/repos/$repo/actions/runners/registration-token" | \
    jq -r '.token' 2>/dev/null
}

# Create an ephemeral droplet (non-blocking — no --wait)
create_runner() {
  local repo="$1"
  local name="ephemeral-$(date +%s)-$((RANDOM % 1000))"
  local token
  token=$(get_reg_token "$repo")

  if [ -z "$token" ]; then
    log "ERROR: could not get registration token for $repo"
    return 1
  fi

  log "Creating ephemeral runner $name for $repo"

  # Write user-data to a temp file
  local tmp_script
  tmp_script=$(mktemp)
  sed "s|__REPO__|$repo|g; s|__TOKEN__|$token|g; s|__NAME__|$name|g" \
    < "$USER_DATA_SCRIPT" > "$tmp_script"

  # Non-blocking create — don't wait for the droplet to become active.
  # The droplet boots from snapshot (~60s) and self-registers via user-data.
  doctl compute droplet create "$name" \
    --size "$DROPLET_SIZE" \
    --image "$SNAPSHOT_ID" \
    --region "$DROPLET_REGION" \
    --ssh-keys "$SSH_KEY_ID" \
    --tag-names "ephemeral-runner,$repo" \
    --enable-private-networking \
    --user-data-file "$tmp_script" 2>&1 | tail -1

  rm -f "$tmp_script"
  log "Requested $name"
}

# Clean up powered-off and stale ephemeral droplets
cleanup() {
  # Delete powered-off droplets (job completed, self-shutdown)
  doctl compute droplet list --format ID,Name,Status --no-header 2>/dev/null | \
    grep "ephemeral-" | awk '$3 == "off" { print $1 }' | while read -r id; do
      log "Cleaning up powered-off droplet $id"
      doctl compute droplet delete "$id" --force 2>/dev/null || true
    done

  # Force-delete stuck droplets via API (running > 45 min with no job completion)
  # doctl doesn't expose created_at, so we use the DO API directly.
  local now
  now=$(date +%s)
  curl -sf --max-time 10 -H "Authorization: Bearer $DO_TOKEN" \
    "https://api.digitalocean.com/v2/droplets?tag_name=ephemeral-runner" | \
    jq -r '.droplets[] | select(.status=="active") | "\(.id) \(.name) \(.created_at)"' 2>/dev/null | \
    while read -r id name created; do
      local created_ts
      created_ts=$(date -d "$created" +%s 2>/dev/null || echo 0)
      local age=$((now - created_ts))
      if [ "$age" -gt 2700 ]; then
        log "Force-cleaning stale droplet $name (age ${age}s)"
        doctl compute droplet delete "$id" --force 2>/dev/null || true
      fi
    done
}

# Main
main() {
  cleanup

  local current
  current=$(count_ephemeral)
  log "Current ephemeral runners: $current / $MAX_RUNNERS"

  if [ "$current" -ge "$MAX_RUNNERS" ]; then
    log "At max capacity, skipping"
    return 0
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
    return 0
  fi

  # Spin up runners for the most backlogged repo
  local to_create=$((MAX_RUNNERS - current))
  if [ "$to_create" -gt "$most_queued" ]; then
    to_create="$most_queued"
  fi

  for i in $(seq 1 "$to_create"); do
    create_runner "$repo_with_most_queued" || true
  done

  log "Requested $to_create new runners"
}

main
