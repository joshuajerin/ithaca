# Core DigitalOcean topology for Doomberg v2 (MASTER-PLAN §5.7).
# RELIABILITY-FIRST, HA, CPU-ONLY. Budget is generous; we optimize for uptime.
#
#   VPC ── DOKS cluster ── node pool: backtest (autoscale min 1 -> max 8, WARM)
#       │              └── node pool: paper    (ALWAYS-ON HA pool, >=2 nodes:
#       │                                       gateways + paper scheduler)
#       ├── Managed Postgres 16 (primary + standby HA, automated backups/PITR)
#       └── Data Gateway facade (the only egress target the workers may reach)
#   Container Registry (the single multi-service image)
#   Load Balancer  (public ingress -> always-on gateways)
#   Spaces bucket  (artifacts/logs/blobs)
#
# Declarative only. NOT applied by the build. No credentials committed.

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = [
    "doomberg",
    var.environment,
    "managed-by:terraform",
  ]
}

# ---------------------------------------------------------------------------
# VPC — private network holding the cluster, Postgres, and the Data Gateway.
# Workers have NO public egress; their only allowed destination is the Gateway.
# ---------------------------------------------------------------------------
resource "digitalocean_vpc" "doomberg" {
  name     = "${local.name_prefix}-vpc"
  region   = var.region
  ip_range = var.vpc_ip_range
}

# ---------------------------------------------------------------------------
# DOKS cluster + the default (backtest) node pool.
# The default pool is the CPU-optimized backtest pool with scale-to-zero.
# ---------------------------------------------------------------------------
data "digitalocean_kubernetes_versions" "current" {
  version_prefix = "${var.kubernetes_version}."
}

resource "digitalocean_kubernetes_cluster" "doomberg" {
  name     = "${local.name_prefix}-doks"
  region   = var.region
  version  = data.digitalocean_kubernetes_versions.current.latest_version
  vpc_uuid = digitalocean_vpc.doomberg.id

  # Pull the private image from DOCR without per-Deployment imagePullSecrets.
  registry_integration = true

  # Routine patch upgrades on a fixed window; no surprise version drift.
  auto_upgrade  = true
  surge_upgrade = true

  # Simple/non-HA control plane for now; flip to true when we set up HA properly.
  ha = false

  maintenance_policy {
    start_time = "04:00"
    day        = "sunday"
  }

  tags = local.common_tags

  # Default pool == backtest pool. CPU-optimized, autoscaling. RELIABILITY-FIRST:
  # min_nodes >= 1 keeps a WARM node so a queued backtest never pays the cold
  # node-provision latency; the autoscaler bursts to max_nodes under load.
  node_pool {
    name       = "backtest"
    size       = var.backtest_node_size
    auto_scale = true
    min_nodes  = var.backtest_node_min
    max_nodes  = var.backtest_node_max

    # Taint so ONLY backtest Jobs (with the matching toleration) land here and
    # keep the pool able to drain back to zero.
    taint {
      key    = "workload"
      value  = "backtest"
      effect = "NoSchedule"
    }

    labels = {
      pool     = "backtest"
      workload = "backtest"
    }

    tags = local.common_tags
  }

  # registry_integration above needs the registry to exist first.
  depends_on = [digitalocean_container_registry.doomberg]
}

# ---------------------------------------------------------------------------
# Paper / gateway pool — the ALWAYS-ON HA pool (node_count >= 2). Hosts the
# always-on plane: mcp-gateway + rest-gateway + control-plane (2+ replicas each
# via the k8s manifests) and the market-calendar-aware paper scheduler + short
# paper-tick Jobs. NOT scale-to-zero; a node failure must not take it down.
# ---------------------------------------------------------------------------
resource "digitalocean_kubernetes_node_pool" "paper" {
  cluster_id = digitalocean_kubernetes_cluster.doomberg.id
  name       = "paper"
  size       = var.paper_node_size
  node_count = var.paper_node_count
  auto_scale = false

  taint {
    key    = "workload"
    value  = "paper"
    effect = "NoSchedule"
  }

  labels = {
    pool     = "paper"
    workload = "paper"
  }

  # The always-on pool carries the gateway tag so the public LB targets these
  # droplets by tag (see loadbalancer.tf), independent of ephemeral node ids.
  tags = concat(local.common_tags, [local.gateway_pool_tag])
}

# ---------------------------------------------------------------------------
# Managed Postgres 16 — the RLS-enforced system of record (MASTER-PLAN §F/§7).
# Lives inside the VPC; reachable from the cluster only. RELIABILITY-FIRST:
# node_count >= 2 == primary + standby (automatic failover).
#
# Backups: DO Managed Postgres takes DAILY automated backups and retains WAL for
# point-in-time restore (PITR) for the cluster's retention window — this is
# always-on and not a knob on the resource. The configurable schedule here is the
# maintenance window (when DO applies engine patches), pinned off-peak below.
# Restore-from-backup is operator-driven via `backup_restore` (see RUNBOOK.md).
# ---------------------------------------------------------------------------
resource "digitalocean_database_cluster" "postgres" {
  name       = "${local.name_prefix}-pg"
  engine     = "pg"
  version    = var.postgres_version
  size       = var.postgres_size
  region     = var.region
  node_count = var.postgres_node_count # >= 2 -> primary + standby (HA)
  # Bind the DB into the same private network as the workers.
  private_network_uuid = digitalocean_vpc.doomberg.id

  # Off-peak engine-maintenance window (UTC). Backups/PITR are automatic.
  maintenance_window {
    day  = var.postgres_maintenance_day
    hour = format("%02d:00:00", var.postgres_maintenance_hour)
  }

  # Grow storage automatically before it fills (reliability over cost).
  storage_autoscale {
    enabled           = true
    increment_gib     = 10
    threshold_percent = 80
  }

  tags = local.common_tags

  # A standby (HA) cluster must not be silently destroyed by a slug typo.
  lifecycle {
    prevent_destroy = true
  }
}

# Application database (distinct from the engine `defaultdb`).
resource "digitalocean_database_db" "app" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = var.postgres_app_db_name
}

# Non-owner application role. RLS + FORCE ROW LEVEL SECURITY are applied to this
# role in the schema migration (out of band); the role itself is provisioned here.
resource "digitalocean_database_user" "app" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = var.postgres_app_user
}

# Lock the DB firewall to the cluster only. No public ingress to Postgres.
resource "digitalocean_database_firewall" "postgres" {
  cluster_id = digitalocean_database_cluster.postgres.id

  rule {
    type  = "k8s"
    value = digitalocean_kubernetes_cluster.doomberg.id
  }
}

# ---------------------------------------------------------------------------
# Spaces bucket — backtest artifacts, logs, blobs (MASTER-PLAN §F).
# Private; never public. Suffixed with a random id for global uniqueness.
# ---------------------------------------------------------------------------
resource "random_id" "bucket_suffix" {
  byte_length = 3
}

resource "digitalocean_spaces_bucket" "artifacts" {
  name   = "${var.spaces_bucket_name}-${var.environment}-${random_id.bucket_suffix.hex}"
  region = var.region
  acl    = "private"

  versioning {
    enabled = true
  }

  # Reproduce-this-run artifacts are cheap to keep; expire raw logs to control cost.
  lifecycle_rule {
    id      = "expire-logs"
    enabled = true
    prefix  = "logs/"

    expiration {
      days = 90
    }
  }
}
