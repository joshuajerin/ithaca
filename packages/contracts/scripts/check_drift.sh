#!/usr/bin/env bash
# THE GATE: regenerate from schema, then fail if the committed generated code differs.
# A breaking contract change (or a hand-edit of generated code) turns CI red and locks merge.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

bash scripts/codegen.sh

if ! git diff --quiet -- py/doomberg_contracts/generated ts/src/generated; then
  echo "" >&2
  echo "ERROR: generated contracts are out of date with schema/." >&2
  echo "Run 'bash packages/contracts/scripts/codegen.sh' and commit the result." >&2
  echo "" >&2
  git --no-pager diff --stat -- py/doomberg_contracts/generated ts/src/generated >&2
  exit 1
fi

echo "==> contracts are in sync with schema (no drift)"
