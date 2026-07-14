# Outputs. Connection material is marked sensitive so it never lands in logs.

output "cluster_id" {
  description = "DOKS cluster id."
  value       = digitalocean_kubernetes_cluster.ithaca.id
}

output "cluster_name" {
  description = "DOKS cluster name."
  value       = digitalocean_kubernetes_cluster.ithaca.name
}

output "cluster_endpoint" {
  description = "DOKS API server endpoint."
  value       = digitalocean_kubernetes_cluster.ithaca.endpoint
}

output "kubeconfig" {
  description = "Raw kubeconfig for the cluster. Sensitive — pipe to a file, never echo."
  value       = digitalocean_kubernetes_cluster.ithaca.kube_config[0].raw_config
  sensitive   = true
}

output "vpc_id" {
  description = "VPC id holding the cluster, Postgres, and the Data Gateway."
  value       = digitalocean_vpc.ithaca.id
}

# Private host/port — the workers reach Postgres over the VPC, never the public host.
# Null when Terraform does not manage Postgres (the prod DB is read via the
# ITHACA_PROD_URL secret instead; see var.manage_postgres).
output "postgres_private_host" {
  description = "Private (VPC) host for Managed Postgres. Null when manage_postgres=false."
  value       = try(one(digitalocean_database_cluster.postgres[*].private_host), null)
}

output "postgres_port" {
  description = "Managed Postgres port. Null when manage_postgres=false."
  value       = try(one(digitalocean_database_cluster.postgres[*].port), null)
}

# Full app DSN over the private network. Composed from the provisioned app user.
# Null when Terraform does not manage Postgres.
output "postgres_app_uri" {
  description = "Application Postgres connection URI (private network, sensitive). Null when manage_postgres=false."
  value = var.manage_postgres ? format(
    "postgresql://%s:%s@%s:%d/%s?sslmode=require",
    digitalocean_database_user.app[0].name,
    digitalocean_database_user.app[0].password,
    digitalocean_database_cluster.postgres[0].private_host,
    digitalocean_database_cluster.postgres[0].port,
    digitalocean_database_db.app[0].name,
  ) : null
  sensitive = true
}

output "spaces_bucket_name" {
  description = "Resolved (globally-unique) Spaces bucket name for artifacts. Null when manage_spaces=false."
  value       = try(one(digitalocean_spaces_bucket.artifacts[*].name), null)
}

output "spaces_bucket_domain" {
  description = "Spaces bucket endpoint domain. Null when manage_spaces=false."
  value       = try(one(digitalocean_spaces_bucket.artifacts[*].bucket_domain_name), null)
}

output "worker_namespace" {
  description = "Namespace the worker pods run in (NetworkPolicy-scoped)."
  value       = kubernetes_namespace.workers.metadata[0].name
}

# ---------------------------------------------------------------------------
# Container Registry — the image build_and_push.sh tags + pushes to.
# ---------------------------------------------------------------------------
output "registry_name" {
  description = "DigitalOcean Container Registry name."
  value       = digitalocean_container_registry.ithaca.name
}

output "registry_endpoint" {
  description = "DOCR endpoint (registry host) — prefix for image refs, e.g. <endpoint>/ithaca:<tag>."
  value       = digitalocean_container_registry.ithaca.endpoint
}

output "registry_server_url" {
  description = "DOCR server URL (for `docker login` / `doctl registry login`)."
  value       = digitalocean_container_registry.ithaca.server_url
}

# ---------------------------------------------------------------------------
# Load Balancer — public ingress to the always-on gateways.
# ---------------------------------------------------------------------------
output "load_balancer_ip" {
  description = "Public IPv4 of the gateways Load Balancer (point DNS here)."
  value       = digitalocean_loadbalancer.gateways.ip
}

output "load_balancer_id" {
  description = "Load Balancer id."
  value       = digitalocean_loadbalancer.gateways.id
}
