#!/usr/bin/env bash
# Ephemeral GitHub Actions runner — auto-registers, runs ONE job, then self-destructs.
# Created by the autoscaler on a fresh DO droplet via user-data.
# Placeholders __REPO__, __TOKEN__, __NAME__, __SSH_KEY_ID__ are replaced by the autoscaler.
set -euo pipefail

REPO="__REPO__"
TOKEN="__TOKEN__"
RUNNER_NAME="__NAME__"

echo "[runner] Starting ephemeral runner for $REPO as $RUNNER_NAME"

# Install essentials
apt-get update -qq && apt-get install -y -qq curl unzip jq sudo lsb-release

# Create runner user
useradd -m -s /bin/bash runner 2>/dev/null || true

# Install Node 24
curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
apt-get install -y -qq nodejs
npm install -g pnpm

# Install uv
su - runner -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'

# Install Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker runner

# Install Terraform
wget -qO- https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" > /etc/apt/sources.list.d/hashicorp.list
apt-get update -qq && apt-get install -y -qq terraform

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
  sleep 30
done

echo "[runner] Job complete. Self-destroying droplet."
# Tag for cleanup, then poweroff
poweroff
