#!/usr/bin/env bash
set -euo pipefail

python_packages=(
  packages/contracts/py
  doomberg-core
  services/platform
  services/mcp-gateway
  services/control-plane
  services/rest-gateway
  services/runtime
)

echo "::group::Python workspace sync"
uv sync --all-packages --extra dev
echo "::endgroup::"

echo "::group::Contract drift"
bash packages/contracts/scripts/check_drift.sh
echo "::endgroup::"

echo "::group::Python tests"
for pkg in "${python_packages[@]}"; do
  echo "pytest ${pkg}"
  (cd "${pkg}" && uv run --extra dev pytest -q)
done
echo "::endgroup::"

echo "::group::Demo pipelines"
uv run python scripts/demo_e2e.py
uv run python scripts/demo_deploy.py
echo "::endgroup::"

echo "::group::Web and contracts"
pnpm install --frozen-lockfile
pnpm --filter @doomberg/contracts run test
pnpm --filter @doomberg/web run test
pnpm --filter @doomberg/web run build
echo "::endgroup::"
