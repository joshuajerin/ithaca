# Outputs. Connection material is marked sensitive so it never lands in logs.

output "cluster_id" {
  description = "DOKS cluster id."
  value       = digitalocean_kubernetes_cluster.doomberg.id
}

output "cluster_name" {
  description = "DOKS cluster name."
  value       = digitalocean_kubernetes_cluster.doomberg.name
}

output "cluster_endpoint" {
  description = "DOKS API server endpoint."
  value       = digitalocean_kubernetes_cluster.doomberg.endpoint
}

output "kubeconfig" {
  description = "Raw kubeconfig for the cluster. Sensitive — pipe to a file, never echo."
  value       = digitalocean_kubernetes_cluster.doomberg.kube_config[0].raw_config
  sensitive   = true
}

output "vpc_id" {
  description = "VPC id holding the cluster, Postgres, and the Data Gateway."
  value       = digitalocean_vpc.doomberg.id
}

# Private host/port — the workers reach Postgres over the VPC, never the public host.
output "postgres_private_host" {
  description = "Private (VPC) host for Managed Postgres."
  value       = digitalocean_database_cluster.postgres.private_host
}

output "postgres_port" {
  description = "Managed Postgres port."
  value       = digitalocean_database_cluster.postgres.port
}

# Full app DSN over the private network. Composed from the provisioned app user.
output "postgres_app_uri" {
  description = "Application Postgres connection URI (private network, sensitive)."
  value = format(
    "postgresql://%s:%s@%s:%d/%s?sslmode=require",
    digitalocean_database_user.app.name,
    digitalocean_database_user.app.password,
    digitalocean_database_cluster.postgres.private_host,
    digitalocean_database_cluster.postgres.port,
    digitalocean_database_db.app.name,
  )
  sensitive = true
}

output "spaces_bucket_name" {
  description = "Resolved (globally-unique) Spaces bucket name for artifacts."
  value       = digitalocean_spaces_bucket.artifacts.name
}

output "spaces_bucket_domain" {
  description = "Spaces bucket endpoint domain."
  value       = digitalocean_spaces_bucket.artifacts.bucket_domain_name
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
  value       = digitalocean_container_registry.doomberg.name
}

output "registry_endpoint" {
  description = "DOCR endpoint (registry host) — prefix for image refs, e.g. <endpoint>/doomberg:<tag>."
  value       = digitalocean_container_registry.doomberg.endpoint
}

output "registry_server_url" {
  description = "DOCR server URL (for `docker login` / `doctl registry login`)."
  value       = digitalocean_container_registry.doomberg.server_url
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

# ---------------------------------------------------------------------------
# Archive DSN — same Managed-Postgres app DSN, surfaced under the env var name
# the loader + ArchiveGateway read (DOOMBERG_ARCHIVE_URL). Sensitive.
# ---------------------------------------------------------------------------
output "archive_url" {
  description = "Archive Postgres DSN for DOOMBERG_ARCHIVE_URL (same private app DSN). Sensitive."
  value = format(
    "postgresql://%s:%s@%s:%d/%s?sslmode=require",
    digitalocean_database_user.app.name,
    digitalocean_database_user.app.password,
    digitalocean_database_cluster.postgres.private_host,
    digitalocean_database_cluster.postgres.port,
    digitalocean_database_db.app.name,
  )
  sensitive = true
}
