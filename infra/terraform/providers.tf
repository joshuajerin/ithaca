# Providers. NO credentials are committed. Supply at plan/apply time via:
#   - DIGITALOCEAN_TOKEN           (DigitalOcean API token)
#   - SPACES_ACCESS_KEY_ID / SPACES_SECRET_ACCESS_KEY  (for the Spaces bucket)
# or a *.auto.tfvars that is gitignored. This config is declarative only and is
# NOT applied by the build.

provider "digitalocean" {
  # token, spaces_access_id and spaces_secret_key are read from the
  # DIGITALOCEAN_TOKEN / SPACES_ACCESS_KEY_ID / SPACES_SECRET_ACCESS_KEY
  # environment variables. Do not hardcode secrets here.
}

# The kubernetes provider is wired to the cluster Terraform creates so the
# default-deny egress NetworkPolicy can be expressed as a first-class resource
# (an invariant in the cluster, per MASTER-PLAN §5.2/§5.7).
provider "kubernetes" {
  host  = digitalocean_kubernetes_cluster.doomberg.endpoint
  token = digitalocean_kubernetes_cluster.doomberg.kube_config[0].token

  cluster_ca_certificate = base64decode(
    digitalocean_kubernetes_cluster.doomberg.kube_config[0].cluster_ca_certificate
  )
}
