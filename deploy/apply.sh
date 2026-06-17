#!/usr/bin/env bash
# Terraform driver for the DigitalOcean deploy layer.
#
#   deploy/apply.sh                 # init + validate + PLAN only (safe; no changes)
#   deploy/apply.sh --plan          # same as no args
#   deploy/apply.sh --apply         # PLAN, then APPLY after an explicit y/N confirm
#   deploy/apply.sh --apply --yes   # APPLY without the interactive prompt (CI/scripted)
#
# Secrets come from infra/terraform/.env (gitignored). Copy the example first:
#   cp infra/terraform/.env.example infra/terraform/.env   # then fill in the token
#
# SAFETY: the default path NEVER applies. `--apply` is the ONLY way to create real
# cloud resources, and it requires either a typed confirmation or `--yes`. The
# CPU-ONLY GUARDRAIL + HA validations fail the plan before any apply if a forbidden
# (GPU) size or a non-HA setting slips in.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${REPO_ROOT}/infra/terraform"
ENV_FILE="${TF_DIR}/.env"

DO_APPLY=0
ASSUME_YES=0
for arg in "$@"; do
  case "${arg}" in
    --apply) DO_APPLY=1 ;;
    --plan)  DO_APPLY=0 ;;
    --yes|-y) ASSUME_YES=1 ;;
    *) echo "unknown flag: ${arg}" >&2; exit 2 ;;
  esac
done

if [[ ! -f "${ENV_FILE}" ]]; then
  cat >&2 <<EOF
ERROR: ${ENV_FILE} not found.

The deploy layer needs a DigitalOcean API token. Create the env file:

    cp infra/terraform/.env.example infra/terraform/.env
    # edit infra/terraform/.env and set DIGITALOCEAN_TOKEN (+ Spaces keys)

Then re-run this script. NOTHING is applied without that token.
EOF
  exit 1
fi

echo "==> Sourcing ${ENV_FILE}"
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

if [[ -z "${DIGITALOCEAN_TOKEN:-}" || "${DIGITALOCEAN_TOKEN}" == *REPLACE_ME* ]]; then
  echo "ERROR: DIGITALOCEAN_TOKEN is unset or still the placeholder in ${ENV_FILE}." >&2
  exit 1
fi

cd "${TF_DIR}"

echo "==> terraform init"
terraform init -input=false

echo "==> terraform validate"
terraform validate

echo "==> terraform plan (-> tfplan)"
terraform plan -input=false -out=tfplan

if [[ "${DO_APPLY}" -eq 0 ]]; then
  echo ""
  echo "PLAN ONLY. No resources were created. To apply, re-run with --apply."
  exit 0
fi

if [[ "${ASSUME_YES}" -ne 1 ]]; then
  echo ""
  echo "About to APPLY the plan above. This creates BILLABLE DigitalOcean resources"
  echo "(DOKS cluster, 2 node pools, HA Managed Postgres, Container Registry, LB)."
  read -r -p "Type 'apply' to proceed: " CONFIRM
  if [[ "${CONFIRM}" != "apply" ]]; then
    echo "Aborted. Nothing applied."
    rm -f tfplan
    exit 1
  fi
fi

echo "==> terraform apply tfplan"
terraform apply -input=false tfplan
rm -f tfplan

echo ""
echo "==> Applied. Next steps (see deploy/RUNBOOK.md):"
echo "    terraform output -raw kubeconfig > /tmp/doomberg.kubeconfig"
echo "    # create the doomberg-db Secret from the postgres_app_uri / archive_url outputs"
echo "    # run the archive-load Job, then deploy the gateway/worker manifests"
