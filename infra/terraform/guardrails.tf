# CPU-ONLY GUARDRAIL (DATA-LAYER-INTERFACES.md → INFRASTRUCTURE GUARDRAIL).
#
# Doomberg v2 runs NO untrusted code and NO model inference on this stack — it is
# trusted numpy over declarative specs. There is therefore NO legitimate reason for
# a GPU node, a GPU database, or any inference / pass-through product to appear here.
#
# This file FAILS `terraform plan` (and `validate`-time evaluation of the size
# variables) if any node-pool or database size slug is a GPU / forbidden slug.
#
# Allowlist (the ONLY DigitalOcean products this stack may provision):
#   - DOKS CPU node pools .......... Droplet size slugs: s-* (shared), c-* (CPU-optimized),
#                                    g-* / gd-* general-purpose CPU, m-* memory-optimized.
#   - Managed Postgres ............. db-* size slugs (incl. db-s-*, db-c-*, db-g-*).
#   - Spaces ....................... object storage (no size slug).
#   - Container Registry ........... subscription tier (basic|professional), no GPU.
#   - Load Balancer ................ size_unit count, no GPU.
#   - VPC / Firewalls .............. network primitives, no compute slug.
#
# Forbidden (NEVER provision or reference): GPU Droplets / GPU DOKS pools
# (`gpu-*`), NVIDIA H100 GPU Kubernetes, Bare Metal GPUs, Dedicated / Serverless
# Inference, Paperspace, Cloudways, or any third-party pass-through. The patterns
# below catch the DO GPU Droplet families (`gpu-*`, `gd-h100-*`, `p-*`) for nodes
# and any non-`db-` slug for the database.

locals {
  # Every compute size slug this configuration could provision a node from.
  _node_size_slugs = [
    var.backtest_node_size,
    var.paper_node_size,
  ]

  # Forbidden GPU / inference Droplet families. DO GPU Droplets are `gpu-*`
  # (e.g. gpu-h100x1-80gb) and the older `gd-*` / `p-*` accelerated families.
  # `g-*` general-purpose CPU Droplets are explicitly ALLOWED, so we anchor the
  # GPU pattern on `gpu-` / `gd-` / `p-` and never on a bare `g`.
  _forbidden_node_regex = "^(gpu-|gd-|p-|gpu)"

  # Database sizes must be Managed-Postgres `db-*` slugs. A `gpu`/`gd`/`p` prefix
  # (or anything not starting with db-) is rejected — there is no GPU database.
  _forbidden_db_regex = "^(gpu-|gd-|p-)"

  # Booleans computed once; the precondition resource asserts on them so the
  # failure message can name the offending slug.
  _gpu_node_hits = [
    for s in local._node_size_slugs : s
    if length(regexall(local._forbidden_node_regex, s)) > 0
  ]

  _db_is_cpu = (
    length(regexall("^db-", var.postgres_size)) > 0 &&
    length(regexall(local._forbidden_db_regex, var.postgres_size)) == 0
  )
}

# A null_resource with preconditions is the portable way to fail a plan on a
# computed condition (no apply needed — preconditions evaluate during plan).
resource "terraform_data" "cpu_only_guardrail" {
  lifecycle {
    precondition {
      condition     = length(local._gpu_node_hits) == 0
      error_message = "CPU-ONLY GUARDRAIL: forbidden GPU/inference node size slug(s) ${jsonencode(local._gpu_node_hits)}. DOKS node pools must be CPU slugs (s-*/c-*/g-*/gd general/m-*); GPU Droplets (gpu-*/gd-*/p-*) are banned."
    }

    precondition {
      condition     = local._db_is_cpu
      error_message = "CPU-ONLY GUARDRAIL: postgres_size='${var.postgres_size}' is not an allowed Managed-Postgres CPU slug. It must start with 'db-' and must not be a GPU/inference family."
    }
  }
}
