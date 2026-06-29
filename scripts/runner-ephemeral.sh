#!/usr/bin/env bash
# Ephemeral GitHub Actions runner — boots from pre-baked snapshot with all tools.
# Only registers the runner, runs ONE job, then self-destructs.
# Placeholders __REPO__, __TOKEN__, __NAME__ are replaced by the autoscaler.
set -euo pipefail

REPO="__REPO__"
TOKEN="__TOKEN__"
RUNNER_NAME="__NAME__"

echo "[runner] Starting ephemeral runner for $REPO as $RUNNER_NAME (snapshot-based)"

# Tools already installed in the snapshot:
#   Node 24, pnpm, uv, Docker, Terraform, unzip, jq
# Just need to register the runner.

# Create runner user (may already exist from snapshot)
useradd -m -s /bin/bash runner 2>/dev/null || true
usermod -aG docker runner

# Download and configure the runner
su - runner -c "cd /home/runner && \
  curl -sL https://github.com/actions/runner/releases/download/v2.319.0/actions-runner-linux-x64-2.319.0.tar.gz | tar xz && \
  ./config.sh --url https://github.com/$REPO --token $TOKEN --name $RUNNER_NAME --labels 'self-hosted,linux,ephemeral' --unattended --ephemeral"

# Install and start as service
cd /home/runner
./svc.sh install runner
./svc.sh start

echo "[runner] Runner started, waiting for job completion..."

# Wait for the runner service to stop (ephemeral runners exit after one job)
while systemctl is-active --quiet actions.runner.*.service 2>/dev/null; do
  sleep 10
done

echo "[runner] Job complete. Self-destroying droplet."
poweroff
