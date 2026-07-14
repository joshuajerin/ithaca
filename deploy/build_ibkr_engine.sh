#!/usr/bin/env bash
# Build and push the dedicated Ithaca IBKR engine image to DOCR.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

if [[ "${LOAD_LOCAL_ENV:-1}" != "0" && -f infra/terraform/.env ]]; then
  # shellcheck disable=SC1091
  set -a; source infra/terraform/.env; set +a
fi

REGISTRY_NAME="${REGISTRY_NAME:-ithaca}"
REGISTRY_HOST="registry.digitalocean.com/${REGISTRY_NAME}"
IMAGE_NAME="${IBKR_IMAGE_NAME:-ithaca-ibkr-engine}"

IMAGE_TAG="${IMAGE_TAG:-${1:-}}"
if [[ -z "${IMAGE_TAG}" ]]; then
  if IMAGE_TAG="$(git rev-parse --short HEAD 2>/dev/null)"; then :; else IMAGE_TAG="local"; fi
fi

LOCAL_REF="${IMAGE_NAME}:${IMAGE_TAG}"
REMOTE_REF="${REGISTRY_HOST}/${IMAGE_NAME}:${IMAGE_TAG}"

BUILD_TAGS=(-t "${LOCAL_REF}" -t "${REMOTE_REF}")
PUSH_REFS=("${REMOTE_REF}")

if [[ "${PUSH_LATEST:-0}" == "1" ]]; then
  BUILD_TAGS+=(-t "${REGISTRY_HOST}/${IMAGE_NAME}:latest")
  PUSH_REFS+=("${REGISTRY_HOST}/${IMAGE_NAME}:latest")
fi

BUILD_ARGS=()
if [[ -n "${IBKR_GATEWAY_ZIP_URL:-}" ]]; then
  BUILD_ARGS+=(--build-arg "IBKR_GATEWAY_ZIP_URL=${IBKR_GATEWAY_ZIP_URL}")
fi

echo "==> Building ${REMOTE_REF} (linux/amd64, IBKR Client Portal Gateway + Ithaca wrapper)"
DOCKER_BUILDKIT=1 docker build \
  --platform linux/amd64 \
  "${BUILD_TAGS[@]}" \
  ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} \
  -f Dockerfile.ibkr-engine .

echo "==> Logging in to DOCR (${REGISTRY_NAME})"
doctl registry login

for ref in "${PUSH_REFS[@]}"; do
  echo "==> Pushing ${ref}"
  docker push "${ref}"
done

echo "==> Pushed IBKR engine image: ${REMOTE_REF}"
