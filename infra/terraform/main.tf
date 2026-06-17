# Core DigitalOcean topology for Doomberg v2 (MASTER-PLAN §5.7).
#
#   VPC ── DOKS cluster ── node pool: backtest (autoscale min 0 -> max N, scale-to-zero)
#       │              └── node pool: paper    (small stable pool)
#       ├── Managed Postgres 16 (RLS system of record)
#       └── Data Gateway facade (the only egress target the workers may reach)
#   Spaces bucket (artifacts/logs/blobs)
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

  # Routine patch upgrades on a fixed window; no surprise version drift.
  auto_upgrade  = true
  surge_upgrade = true

  maintenance_policy {
    start_time = "04:00"
    day        = "sunday"
  }

  tags = local.common_tags

  # Default pool == backtest pool. CPU-optimized, autoscaling, scale-to-zero
  # (min 0). This is the cost-control story: no nodes billed when idle.
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
}

# ---------------------------------------------------------------------------
# Paper node pool — small, STABLE (not scale-to-zero). Hosts the
# market-calendar-aware scheduler + short paper-tick Jobs.
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

  tags = local.common_tags
}

# ---------------------------------------------------------------------------
# Managed Postgres 16 — the RLS-enforced system of record (MASTER-PLAN §F/§7).
# Lives inside the VPC; reachable from the cluster only.
# ---------------------------------------------------------------------------
resource "digitalocean_database_cluster" "postgres" {
  name       = "${local.name_prefix}-pg"
  engine     = "pg"
  version    = var.postgres_version
  size       = var.postgres_size
  region     = var.region
  node_count = var.postgres_node_count
  # Bind the DB into the same private network as the workers.
  private_network_uuid = digitalocean_vpc.doomberg.id

  tags = local.common_tags
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
