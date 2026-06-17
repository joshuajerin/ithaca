# All knobs for the topology. Sensible defaults; override per-environment with a
# gitignored *.auto.tfvars. No secrets live here.

variable "project_name" {
  description = "Short slug used as a name prefix for all resources."
  type        = string
  default     = "doomberg"
}

variable "environment" {
  description = "Deployment environment (dev|staging|prod). Used in resource names + tags."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "region" {
  description = "DigitalOcean region slug (e.g. nyc3, sfo3, fra1)."
  type        = string
  default     = "nyc3"
}

# ---------------------------------------------------------------------------
# Kubernetes
# ---------------------------------------------------------------------------

variable "kubernetes_version" {
  description = "DOKS version slug prefix. Use the latest patch for this minor."
  type        = string
  default     = "1.31"
}

# Backtest pool: CPU-burst Jobs. RELIABILITY-FIRST: min 1 keeps a WARM node so a
# queued backtest never pays a cold node-provision; the autoscaler bursts to max
# under load. (Budget is generous; we trade idle cost for zero cold-start.)
variable "backtest_node_size" {
  description = "Droplet size slug for the CPU-optimized backtest node pool. MUST be a CPU slug (s-*/c-*/g-*/gd general/m-*); GPU slugs are rejected."
  type        = string
  default     = "c-4" # 4 vCPU dedicated CPU-optimized

  validation {
    # CPU-only allowlist: shared (s-), CPU-optimized (c-), general (g-/gd-),
    # memory-optimized (m-). Reject GPU Droplet families (gpu-*, p-*).
    condition = (
      can(regex("^(s-|c-|g-|gd-|m-|m3-|m6-|c2-|so-|so1_5-)", var.backtest_node_size)) &&
      !can(regex("^(gpu-|p-)", var.backtest_node_size))
    )
    error_message = "backtest_node_size must be a CPU Droplet slug (s-*/c-*/g-*/gd-*/m-*); GPU slugs (gpu-*/p-*) are forbidden by the CPU-ONLY GUARDRAIL."
  }
}

variable "backtest_node_min" {
  description = "Minimum backtest nodes. 0 = scale-to-zero (simple/cheap); set 1 later to keep a warm node (no cold start)."
  type        = number
  default     = 0

  validation {
    condition     = var.backtest_node_min >= 0
    error_message = "backtest_node_min must be >= 0."
  }
}

variable "backtest_node_max" {
  description = "Maximum backtest nodes the autoscaler may provision."
  type        = number
  default     = 8

  validation {
    condition     = var.backtest_node_max >= var.backtest_node_min && var.backtest_node_max >= 1
    error_message = "backtest_node_max must be >= backtest_node_min and >= 1."
  }
}

# Paper pool: ALWAYS-ON HA pool that hosts the gateways + market-calendar
# scheduler + short paper-tick Jobs. >=2 nodes so a node failure never takes the
# always-on plane down. Not scaled to zero — the scheduler/gateways must persist.
variable "paper_node_size" {
  description = "Droplet size slug for the always-on HA paper/gateway node pool. MUST be a CPU slug; GPU slugs are rejected."
  type        = string
  default     = "s-2vcpu-4gb"

  validation {
    condition = (
      can(regex("^(s-|c-|g-|gd-|m-|m3-|m6-|c2-|so-|so1_5-)", var.paper_node_size)) &&
      !can(regex("^(gpu-|p-)", var.paper_node_size))
    )
    error_message = "paper_node_size must be a CPU Droplet slug (s-*/c-*/g-*/gd-*/m-*); GPU slugs (gpu-*/p-*) are forbidden by the CPU-ONLY GUARDRAIL."
  }
}

variable "paper_node_count" {
  description = "Fixed node count for the always-on pool. 1 = simple (no HA); set >=2 later for node-failover HA."
  type        = number
  default     = 1

  validation {
    condition     = var.paper_node_count >= 1
    error_message = "paper_node_count must be >= 1."
  }
}

# ---------------------------------------------------------------------------
# Managed Postgres 16
# ---------------------------------------------------------------------------

variable "postgres_version" {
  description = "Managed Postgres major version."
  type        = string
  default     = "16"
}

variable "postgres_size" {
  description = "Managed Postgres node size slug. MUST be a db-* CPU slug; GPU/inference slugs are rejected."
  type        = string
  default     = "db-s-1vcpu-2gb"

  validation {
    # Managed Postgres slugs are all db-*. There is no GPU database; reject anything else.
    condition = (
      can(regex("^db-", var.postgres_size)) &&
      !can(regex("^(gpu-|gd-|p-)", var.postgres_size))
    )
    error_message = "postgres_size must be a Managed-Postgres CPU slug (db-*); GPU/inference families are forbidden by the CPU-ONLY GUARDRAIL."
  }
}

variable "postgres_node_count" {
  description = "Postgres nodes. 1 = simple single-node (no standby); set >=2 later for primary+standby HA failover."
  type        = number
  default     = 1

  validation {
    condition     = var.postgres_node_count >= 1
    error_message = "postgres_node_count must be >= 1."
  }
}

variable "postgres_app_db_name" {
  description = "Application database name (RLS-enforced system of record)."
  type        = string
  default     = "doomberg"
}

variable "postgres_app_user" {
  description = "Non-owner application role. RLS + FORCE ROW LEVEL SECURITY apply to it (MASTER-PLAN §7)."
  type        = string
  default     = "doomberg_app"
}

# ---------------------------------------------------------------------------
# Spaces (artifacts / logs / blobs)
# ---------------------------------------------------------------------------

variable "spaces_bucket_name" {
  description = "Spaces bucket for backtest artifacts. Must be globally unique; suffixed in code."
  type        = string
  default     = "doomberg-artifacts"
}

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

variable "vpc_ip_range" {
  description = "Private CIDR for the VPC that holds the cluster + Postgres + Data Gateway."
  type        = string
  default     = "10.20.0.0/20"
}

# ---------------------------------------------------------------------------
# Data Gateway egress allow-list (the single NetworkPolicy exception)
# ---------------------------------------------------------------------------

variable "worker_namespace" {
  description = "Kubernetes namespace the backtest/paper worker pods run in."
  type        = string
  default     = "doomberg-workers"
}

variable "data_gateway_namespace" {
  description = "Namespace hosting the Data Gateway facade Service (the one allowed egress target)."
  type        = string
  default     = "doomberg-gateway"
}

variable "data_gateway_port" {
  description = "TCP port of the Data Gateway facade RPC the workers are allowed to reach."
  type        = number
  default     = 8080
}

# ---------------------------------------------------------------------------
# Deadlines (the aggregate wall-clock budget, surfaced into Job manifests)
# ---------------------------------------------------------------------------

variable "backtest_active_deadline_seconds" {
  description = "Aggregate wall-clock deadline for a backtest Job (activeDeadlineSeconds). SIGKILL on breach."
  type        = number
  default     = 1800 # 30 min
}

variable "paper_tick_active_deadline_seconds" {
  description = "Aggregate wall-clock deadline for one stateless paper-tick Job."
  type        = number
  default     = 120 # 2 min
}

variable "paper_tick_schedule" {
  description = "Cron schedule for the paper-tick CronJob (UTC). Default: every weekday minute during US RTH window is gated in-app; here a coarse cadence."
  type        = string
  default     = "*/5 13-21 * * 1-5" # every 5 min, 13:00-21:00 UTC, Mon-Fri (covers US RTH)
}

variable "worker_image" {
  description = "Container image for the shared doomberg-core worker (backtest + paper-tick). Built from the repo Dockerfile + pushed to the DO Container Registry below."
  type        = string
  default     = "registry.digitalocean.com/doomberg/doomberg:latest"
}

# ---------------------------------------------------------------------------
# Container Registry (DOCR) — holds the single multi-service image
# ---------------------------------------------------------------------------

variable "registry_name" {
  description = "DigitalOcean Container Registry name (global; account-unique). Holds the doomberg image."
  type        = string
  default     = "doomberg"
}

variable "registry_subscription_tier" {
  description = "DOCR subscription tier. 'professional' for generous storage/throughput (budget allows)."
  type        = string
  default     = "professional"

  validation {
    condition     = contains(["starter", "basic", "professional"], var.registry_subscription_tier)
    error_message = "registry_subscription_tier must be one of: starter, basic, professional."
  }
}

# ---------------------------------------------------------------------------
# Managed Postgres — off-peak engine-maintenance window
# (daily backups + WAL/PITR are automatic and always-on, not configured here)
# ---------------------------------------------------------------------------

variable "postgres_maintenance_day" {
  description = "Day of week DO may apply Managed-Postgres engine maintenance."
  type        = string
  default     = "sunday"

  validation {
    condition = contains(
      ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
      var.postgres_maintenance_day
    )
    error_message = "postgres_maintenance_day must be a lowercase weekday name."
  }
}

variable "postgres_maintenance_hour" {
  description = "UTC hour (0-23) for the off-peak Managed-Postgres maintenance window."
  type        = number
  default     = 5

  validation {
    condition     = var.postgres_maintenance_hour >= 0 && var.postgres_maintenance_hour <= 23
    error_message = "postgres_maintenance_hour must be 0-23."
  }
}

# ---------------------------------------------------------------------------
# archive.* loader (Stream 1's loader image, run once on first deploy)
# ---------------------------------------------------------------------------

variable "archive_loader_image" {
  description = "Image that runs scripts/import_v1_archive.py to seed archive.* on first deploy. Defaults to the same repo image (the loader script ships in it)."
  type        = string
  default     = "registry.digitalocean.com/doomberg/doomberg:latest"
}

variable "archive_loader_active_deadline_seconds" {
  description = "Wall-clock deadline for the one-shot archive-load Job (bulk load of ~240k rows)."
  type        = number
  default     = 3600 # 1h — bulk COPY of the v1 archive
}

variable "enable_archive_load_job" {
  description = "Render the one-shot archive-load Kubernetes Job. Seeds archive.* on first deploy; set false after the archive is loaded."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------------
# Public Load Balancer (the always-on gateways' ingress)
# ---------------------------------------------------------------------------

variable "lb_size_unit" {
  description = "DO Load Balancer size_unit (number of LB nodes; 1 = simple, >=2 for HA)."
  type        = number
  default     = 1

  validation {
    condition     = var.lb_size_unit >= 1
    error_message = "lb_size_unit must be >= 1."
  }
}

variable "gateway_node_label" {
  description = "Node-pool label value the LB forwards to (the always-on gateway/paper pool)."
  type        = string
  default     = "paper"
}
