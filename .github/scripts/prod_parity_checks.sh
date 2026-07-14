#!/usr/bin/env bash
set -euo pipefail

export PATH="${HOME}/.local/bin:${PATH}"

python_packages=(
  packages/contracts/py
  ithaca-core
  services/platform
  services/mcp-gateway
  services/control-plane
  services/rest-gateway
  services/runtime
  services/ibkr-engine
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
pnpm --filter @ithaca/contracts run test
pnpm --filter @ithaca/web run test
pnpm --filter @ithaca/web run build
echo "::endgroup::"
