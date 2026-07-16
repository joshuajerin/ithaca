#!/usr/bin/env bash
# Build the single multi-service doomberg image and push it to DigitalOcean
# Container Registry (DOCR). CI passes explicit immutable tags; local use can
# still default to the current git short SHA.
#
#   IMAGE_TAG=prod-a5fe2a0 PUSH_LATEST=0 deploy/build_and_push.sh
#   deploy/build_and_push.sh a5fe2a0
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

if [[ "${LOAD_LOCAL_ENV:-1}" != "0" && -f infra/terraform/.env ]]; then
  # shellcheck disable=SC1091
  set -a; source infra/terraform/.env; set +a
fi

REGISTRY_NAME="${REGISTRY_NAME:-doomberg}"
REGISTRY_HOST="registry.digitalocean.com/${REGISTRY_NAME}"
IMAGE_NAME="${IMAGE_NAME:-doomberg}"

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

if [[ -n "${EXTRA_IMAGE_TAGS:-}" ]]; then
  IFS=',' read -r -a extra_tags <<< "${EXTRA_IMAGE_TAGS}"
  for tag in "${extra_tags[@]}"; do
    tag="${tag//[[:space:]]/}"
    [[ -z "${tag}" ]] && continue
    BUILD_TAGS+=(-t "${REGISTRY_HOST}/${IMAGE_NAME}:${tag}")
    PUSH_REFS+=("${REGISTRY_HOST}/${IMAGE_NAME}:${tag}")
  done
fi

BUILD_ARGS=()
if [[ -n "${CLERK_PUBLISHABLE_VALUE:-}" ]]; then
  BUILD_ARGS+=(--build-arg "CLERK_PUBLISHABLE_VALUE=${CLERK_PUBLISHABLE_VALUE}")
elif [[ -n "${VITE_CLERK_PUBLISHABLE_KEY:-}" ]]; then
  BUILD_ARGS+=(--build-arg "CLERK_PUBLISHABLE_VALUE=${VITE_CLERK_PUBLISHABLE_KEY}")
fi
if [[ -n "${VITE_API_BASE:-}" ]]; then
  BUILD_ARGS+=(--build-arg "VITE_API_BASE=${VITE_API_BASE}")
fi

echo "==> Building ${REMOTE_REF} (linux/amd64, CPU-only)"
DOCKER_BUILD=(docker build --platform linux/amd64 "${BUILD_TAGS[@]}")
if (( ${#BUILD_ARGS[@]} )); then
  DOCKER_BUILD+=("${BUILD_ARGS[@]}")
fi
DOCKER_BUILDKIT=1 "${DOCKER_BUILD[@]}" -f Dockerfile .

echo "==> Logging in to DOCR (${REGISTRY_NAME})"
doctl registry login

for ref in "${PUSH_REFS[@]}"; do
  echo "==> Pushing ${ref}"
  docker push "${ref}"
done

echo "==> Pushed primary image: ${REMOTE_REF}"
