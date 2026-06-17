# Container Registry (DOCR) — holds the single multi-stage doomberg image that
# every service (mcp-gateway, rest-gateway, control-plane, runtime worker/
# scheduler, archive loader) runs from. CPU-only image; no GPU/inference.
#
# DOCR is a global, account-scoped resource (one per account by default). The
# `deploy/build_and_push.sh` script tags + pushes `:<tag>` here; the DOKS cluster
# pulls it via `registry_integration = true` (set on the cluster in main.tf),
# which maintains the dockercfg pull secret across namespaces automatically — no
# per-Deployment imagePullSecrets needed.

resource "digitalocean_container_registry" "doomberg" {
  name                   = var.registry_name
  subscription_tier_slug = var.registry_subscription_tier
  region                 = var.region
}
