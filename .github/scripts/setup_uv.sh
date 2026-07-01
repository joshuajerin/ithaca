#!/usr/bin/env bash
set -euo pipefail

export PATH="${HOME}/.local/bin:${PATH}"

if command -v uv >/dev/null 2>&1; then
  uv --version
  exit 0
fi

curl -LsSf https://astral.sh/uv/install.sh | sh

export PATH="${HOME}/.local/bin:${PATH}"
uv --version

if [[ -n "${GITHUB_PATH:-}" && -e "${GITHUB_PATH}" ]]; then
  echo "${HOME}/.local/bin" >> "${GITHUB_PATH}"
fi
