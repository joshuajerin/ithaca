#!/usr/bin/env bash
# THE GATE: regenerate from schema, then fail if generated files change.
# This works in both CI and a dirty local branch: schema+generated changes can be staged or
# unstaged together, but the check fails if running codegen would further mutate the tree.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

tmp_before="$(mktemp)"
tmp_after="$(mktemp)"
trap 'rm -f "$tmp_before" "$tmp_after"' EXIT

snapshot_generated() {
  find py/ithaca_contracts/generated ts/src/generated -type f \
      ! -path '*/__pycache__/*' ! -name '*.pyc' -print0 \
    | sort -z \
    | xargs -0 shasum -a 256
}

snapshot_generated > "$tmp_before"
bash scripts/codegen.sh
snapshot_generated > "$tmp_after"

if ! cmp -s "$tmp_before" "$tmp_after"; then
  echo "" >&2
  echo "ERROR: generated contracts are out of date with schema/." >&2
  echo "Run 'bash packages/contracts/scripts/codegen.sh' and commit the result." >&2
  echo "" >&2
  diff -u "$tmp_before" "$tmp_after" >&2 || true
  exit 1
fi

echo "==> contracts are in sync with schema (no drift)"
