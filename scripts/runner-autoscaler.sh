#!/usr/bin/env bash
# GitHub Actions self-hosted runner autoscaler for DigitalOcean.
#
# Runs as a systemd timer on the controller droplet. Maintains:
#   1. A WARM POOL of always-on, idle runners (instant job pickup, like GitHub-hosted)
#   2. EPHEMERAL runners that scale up on demand and self-destruct after one job
#
# Config (env or /etc/runner-autoscaler.env):
#   DO_TOKEN            — DigitalOcean API token
#   GH_PAT              — GitHub personal access token (repo scope)
#   REPOS               — space-separated list of repos
#   SSH_KEY_ID          — DO SSH key ID to inject into ephemeral droplets
#   DROPLET_SIZE        — DO droplet slug (default: s-4vcpu-8gb)
#   DROPLET_REGION      — DO region (default: nyc1)
#   MAX_RUNNERS         — total cap including warm pool (default: 12)
#   WARM_POOL           — always-on idle runners to maintain (default: 3)
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
MAX_RUNNERS="${MAX_RUNNERS:-12}"
WARM_POOL="${WARM_POOL:-6}"
SNAPSHOT_ID="${SNAPSHOT_ID:-234895636}"
BASE_RUNNER="${BASE_RUNNER:-runner}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EPHEMERAL_SCRIPT="$SCRIPT_DIR/runner-ephemeral.sh"
WARM_SCRIPT="$SCRIPT_DIR/runner-warm.sh"

log() { echo "[autoscaler] $(date -u +%H:%M:%S) $*"; }

# Count active ephemeral droplets (not off, not warm-pool)
count_ephemeral() {
  doctl compute droplet list --format Name,Status --no-header 2>/dev/null | \
    grep "ephemeral-" | grep -v "off" | wc -l
}

# Count active warm-pool droplets (not off)
count_warm() {
  doctl compute droplet list --format Name,Status --no-header 2>/dev/null | \
    grep "warm-" | grep -v "off" | wc -l
}

# Count idle runners via GitHub API (online + not busy)
count_idle_runners() {
  curl -sf --max-time 10 -H "Authorization: token $GH_PAT" \
    "https://api.github.com/repos/$1/actions/runners" | \
    jq '[.runners[] | select(.status=="online" and .busy==false)] | length' 2>/dev/null || echo 0
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

# Create a droplet (non-blocking — no --wait)
create_droplet() {
  local name="$1" repo="$2" script_file="$3"
  local token
  token=$(get_reg_token "$repo")
  if [ -z "$token" ]; then
    log "ERROR: could not get registration token for $repo"
    return 1
  fi

  local tmp_script
  tmp_script=$(mktemp)
  sed "s|__REPO__|$repo|g; s|__TOKEN__|$token|g; s|__NAME__|$name|g" \
    < "$script_file" > "$tmp_script"

  doctl compute droplet create "$name" \
    --size "$DROPLET_SIZE" \
    --image "$SNAPSHOT_ID" \
    --region "$DROPLET_REGION" \
    --ssh-keys "$SSH_KEY_ID" \
    --tag-names "ephemeral-runner,$repo" \
    --enable-private-networking \
    --user-data-file "$tmp_script" 2>&1 | tail -1

  rm -f "$tmp_script"
}

# Clean up powered-off and stale droplets
cleanup() {
  # Delete powered-off droplets (job completed, self-shutdown)
  doctl compute droplet list --format ID,Name,Status --no-header 2>/dev/null | \
    grep -E "ephemeral-|warm-" | awk '$3 == "off" { print $1 }' | while read -r id; do
      log "Cleaning up powered-off droplet $id"
      doctl compute droplet delete "$id" --force 2>/dev/null || true
    done

  # Force-delete stuck droplets via API (running > 45 min with no job completion)
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

# Maintain the warm pool — ensure WARM_POOL runners are always on
maintain_warm_pool() {
  local current_warm
  current_warm=$(count_warm)
  local needed=$((WARM_POOL - current_warm))

  if [ "$needed" -le 0 ]; then
    return 0
  fi

  # Don't exceed MAX_RUNNERS total
  local current_eph
  current_eph=$(count_ephemeral)
  local total=$((current_warm + current_eph))
  local room=$((MAX_RUNNERS - total))
  if [ "$room" -le 0 ]; then
    return 0
  fi
  if [ "$needed" -gt "$room" ]; then
    needed=$room
  fi

  # Pick the repo with most queued jobs (or first repo as default)
  local target_repo=""
  local most_queued=0
  for repo in $REPOS; do
    local queued
    queued=$(get_queued_count "$repo")
    if [ "$queued" -gt "$most_queued" ]; then
      most_queued="$queued"
      target_repo="$repo"
    fi
  done
  # Default to first repo if no queued jobs
  [ -z "$target_repo" ] && target_repo=$(echo "$REPOS" | awk '{print $1}')

  for i in $(seq 1 "$needed"); do
    local name="warm-$(date +%s)-$((RANDOM % 1000))"
    log "Creating warm-pool runner $name for $target_repo"
    create_droplet "$name" "$target_repo" "$WARM_SCRIPT" || true
  done
  log "Warm pool: created $needed warm runners (have $current_warm, want $WARM_POOL)"
}

# Scale up ephemeral runners for queued jobs
scale_ephemeral() {
  local current_eph
  current_eph=$(count_ephemeral)
  local current_warm
  current_warm=$(count_warm)
  local total=$((current_eph + current_warm))

  if [ "$total" -ge "$MAX_RUNNERS" ]; then
    log "At max capacity ($total/$MAX_RUNNERS), skipping ephemeral scale-up"
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

  if [ "$total_queued" -eq 0 ]; then
    log "No queued jobs, skipping ephemeral scale-up"
    return 0
  fi

  # Count idle runners across all repos — if we have enough idle, don't scale
  local total_idle=0
  for repo in $REPOS; do
    local idle
    idle=$(count_idle_runners "$repo")
    total_idle=$((total_idle + idle))
  done
  if [ "$total_idle" -ge "$total_queued" ]; then
    log "Enough idle runners ($total_idle) for queued jobs ($total_queued), skipping"
    return 0
  fi

  local to_create=$((MAX_RUNNERS - total))
  local needed=$((total_queued - total_idle))
  if [ "$to_create" -gt "$needed" ]; then
    to_create=$needed
  fi
  if [ "$to_create" -le 0 ]; then
    return 0
  fi

  for i in $(seq 1 "$to_create"); do
    local name="ephemeral-$(date +%s)-$((RANDOM % 1000))"
    log "Creating ephemeral runner $name for $repo_with_most_queued"
    create_droplet "$name" "$repo_with_most_queued" "$EPHEMERAL_SCRIPT" || true
  done
  log "Scale-up: created $to_create ephemeral runners"
}

# Main
main() {
  cleanup
  maintain_warm_pool
  scale_ephemeral

  local eph warm total
  eph=$(count_ephemeral)
  warm=$(count_warm)
  total=$((eph + warm))
  log "Status: $warm warm + $eph ephemeral = $total total (max $MAX_RUNNERS, warm pool $WARM_POOL)"
}

main
