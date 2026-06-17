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

# Backtest pool: CPU-burst Jobs, scales to zero when idle (the cost-control story).
variable "backtest_node_size" {
  description = "Droplet size slug for the CPU-optimized backtest node pool."
  type        = string
  default     = "c-4" # 4 vCPU dedicated CPU-optimized
}

variable "backtest_node_min" {
  description = "Minimum backtest nodes. 0 enables scale-to-zero (cost control)."
  type        = number
  default     = 0
}

variable "backtest_node_max" {
  description = "Maximum backtest nodes the autoscaler may provision."
  type        = number
  default     = 5
}

# Paper pool: small stable pool that always hosts the market-calendar scheduler
# and the short paper-tick Jobs. Not scaled to zero — the scheduler must persist.
variable "paper_node_size" {
  description = "Droplet size slug for the stable paper node pool."
  type        = string
  default     = "s-2vcpu-4gb"
}

variable "paper_node_count" {
  description = "Fixed node count for the paper pool (stable, not scale-to-zero)."
  type        = number
  default     = 2
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
  description = "Managed Postgres node size slug."
  type        = string
  default     = "db-s-1vcpu-2gb"
}

variable "postgres_node_count" {
  description = "Postgres nodes (1 = primary only; >=2 adds standby for HA)."
  type        = number
  default     = 1
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
  description = "Container image for the shared doomberg-core worker (backtest + paper-tick)."
  type        = string
  default     = "registry.digitalocean.com/doomberg/worker:latest"
}
