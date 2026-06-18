#!/usr/bin/env bash
# Build the single multi-service doomberg image and push it to the DigitalOcean
# Container Registry (DOCR). CPU-only image; no GPU layers.
#
#   deploy/build_and_push.sh [TAG]
#
# TAG defaults to the short git SHA (falls back to "latest"). Requires:
#   - docker (a running daemon)
#   - doctl, authenticated:  doctl auth init   (or DIGITALOCEAN_TOKEN in env)
#
# Reads the registry name from infra/terraform/.env if present (REGISTRY_NAME),
# else defaults to "doomberg" (matches infra/terraform var.registry_name).
#
# This script DOES push to your registry — it needs a real DO token. It does NOT
# create cluster/DB resources or spend on compute; it only uses registry storage.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

# Optional .env (the same one apply.sh sources) for REGISTRY_NAME / token.
if [[ -f infra/terraform/.env ]]; then
  # shellcheck disable=SC1091
  set -a; source infra/terraform/.env; set +a
fi

REGISTRY_NAME="${REGISTRY_NAME:-doomberg}"
REGISTRY_HOST="registry.digitalocean.com/${REGISTRY_NAME}"
IMAGE_NAME="doomberg"

# Tag: explicit arg > git short SHA > "latest".
TAG="${1:-}"
if [[ -z "${TAG}" ]]; then
  if TAG="$(git rev-parse --short HEAD 2>/dev/null)"; then :; else TAG="latest"; fi
fi

LOCAL_REF="${IMAGE_NAME}:${TAG}"
REMOTE_REF="${REGISTRY_HOST}/${IMAGE_NAME}:${TAG}"
REMOTE_LATEST="${REGISTRY_HOST}/${IMAGE_NAME}:latest"

echo "==> Building ${LOCAL_REF} (linux/amd64, CPU-only)"
# DOKS nodes are amd64; build for that platform explicitly so an arm64 dev
# machine doesn't push an unschedulable image.
DOCKER_BUILDKIT=1 docker build \
  --platform linux/amd64 \
  -t "${LOCAL_REF}" \
  -t "${REMOTE_REF}" \
  -t "${REMOTE_LATEST}" \
  -f Dockerfile .

echo "==> Logging in to DOCR (${REGISTRY_NAME})"
# Uses DIGITALOCEAN_TOKEN from env / .env, or an existing `doctl auth init`.
doctl registry login

echo "==> Pushing ${REMOTE_REF}"
docker push "${REMOTE_REF}"
echo "==> Pushing ${REMOTE_LATEST}"
docker push "${REMOTE_LATEST}"

echo "==> Pushed:"
echo "      ${REMOTE_REF}"
echo "      ${REMOTE_LATEST}"
echo ""
echo "Set worker_image / archive_loader_image to: ${REMOTE_REF}"
echo "(or leave the :latest default in infra/terraform/variables.tf)"
