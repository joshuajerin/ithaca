#!/usr/bin/env bash
# Warm-pool GitHub Actions runner — stays registered and idle, picks up jobs
# as they arrive. Does NOT self-destruct after one job.
# Placeholders __REPO__, __TOKEN__, __NAME__ are replaced by the autoscaler.
set -euo pipefail

REPO="__REPO__"
TOKEN="__TOKEN__"
RUNNER_NAME="__NAME__"

echo "[warm-runner] Starting warm-pool runner for $REPO as $RUNNER_NAME"

# Tools already installed in the snapshot:
#   Node 24, pnpm, uv, Docker, Terraform, unzip, jq, databento
# Runner agent pre-downloaded at /opt/runner-agent/runner.tar.gz

# Create runner user (may already exist from snapshot)
useradd -m -s /bin/bash runner 2>/dev/null || true
usermod -aG docker runner

# Extract pre-downloaded runner agent to a fresh dir (avoid stale config from snapshot)
RUNNER_DIR="/home/runner/actions-runner-$RUNNER_NAME"
mkdir -p "$RUNNER_DIR"
chown runner:runner "$RUNNER_DIR"
tar xzf /opt/runner-agent/runner.tar.gz -C "$RUNNER_DIR"
chown -R runner:runner "$RUNNER_DIR"

# Configure the runner (non-ephemeral: stays registered for multiple jobs)
su - runner -c "cd $RUNNER_DIR && \
  ./config.sh --url https://github.com/$REPO --token $TOKEN --name $RUNNER_NAME --labels 'self-hosted,linux,warm' --unattended"

# Install and start as service
cd "$RUNNER_DIR"
./svc.sh install runner
./svc.sh start

echo "[warm-runner] Runner online and waiting for jobs..."
