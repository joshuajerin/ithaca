# Worker Job shapes (MASTER-PLAN §5.2/§5.5).
#
# These are the canonical SHAPES of the two worker runtimes, expressed as
# Terraform so the deadline + restart-policy + scheduling invariants are
# reviewable. In practice the control plane templates a fresh backtest Job
# per run_id (one job per container, spawned fresh, killed at completion) — the
# kubernetes_job below is a reference template, not a long-lived resource. The
# equivalent raw YAML the control plane renders lives in ./manifests.
#
# Invariants encoded here:
#   - activeDeadlineSeconds = the AGGREGATE wall-clock deadline (SIGKILL on breach)
#   - restartPolicy = Never (a crashed tick loses one tick, not the book)
#   - pods carry doomberg/component=worker so the NetworkPolicy binds (deny-all
#     egress except the Data Gateway)
#   - nodeSelector + toleration pin Jobs to the right tainted pool
#   - no public egress; the only network reachability is the Gateway (policy)

locals {
  worker_pod_labels = {
    "doomberg/component" = "worker"
  }
}

# ---------------------------------------------------------------------------
# Backtest Job (reference template). CPU-burst, runs on the scale-to-zero
# backtest pool. The control plane stamps run_id/tenant_id into env per job.
# ---------------------------------------------------------------------------
resource "kubernetes_job" "backtest_template" {
  # This is a template/reference shape. Disable lifecycle churn — real Jobs are
  # rendered per-run by the control plane from the manifest in ./manifests.
  count = 0 # not created on apply; present as a typed, validated shape.

  metadata {
    name      = "backtest-template"
    namespace = kubernetes_namespace.workers.metadata[0].name
    labels    = local.worker_pod_labels
  }

  spec {
    # AGGREGATE wall-clock deadline for the whole Job. SIGKILL on breach.
    active_deadline_seconds = var.backtest_active_deadline_seconds
    backoff_limit           = 0 # restartPolicy Never + no retries (idempotent on (run_id, seq) is the control plane's job)
    completions             = 1
    parallelism             = 1
    ttl_seconds_after_finished = 3600

    template {
      metadata {
        labels = local.worker_pod_labels
      }

      spec {
        restart_policy = "Never"

        # Pin to the backtest pool; tolerate its taint.
        node_selector = {
          workload = "backtest"
        }

        toleration {
          key      = "workload"
          operator = "Equal"
          value    = "backtest"
          effect   = "NoSchedule"
        }

        automount_service_account_token = false

        container {
          name              = "backtest"
          image             = var.worker_image
          image_pull_policy = "IfNotPresent"
          command           = ["python", "-m", "doomberg_runtime.backtest_runner"]

          # run_id / tenant_id stamped per-job by the control plane.
          env {
            name  = "DOOMBERG_MODE"
            value = "backtest"
          }
          env {
            name  = "DATA_GATEWAY_URL"
            value = "http://data-gateway.${var.data_gateway_namespace}.svc.cluster.local:${var.data_gateway_port}"
          }

          resources {
            requests = {
              cpu    = "2"
              memory = "2Gi"
            }
            limits = {
              cpu    = "4"
              memory = "4Gi"
            }
          }

          security_context {
            run_as_non_root            = true
            read_only_root_filesystem  = true
            allow_privilege_escalation = false

            capabilities {
              drop = ["ALL"]
            }
          }
        }
      }
    }

    # Backtests should not auto-retry: a re-run is a new run_id from the control plane.
  }

  wait_for_completion = false
}

# ---------------------------------------------------------------------------
# Paper-tick CronJob shape. Stateless ticks on the stable paper pool. Each tick
# loads the book -> evaluates on real current data -> proposes a delta -> exits.
# A crash loses one tick, not the book (restartPolicy Never).
# ---------------------------------------------------------------------------
resource "kubernetes_cron_job_v1" "paper_tick" {
  count = 0 # reference shape; the scheduler may create these dynamically per deployment.

  metadata {
    name      = "paper-tick"
    namespace = kubernetes_namespace.workers.metadata[0].name
    labels    = local.worker_pod_labels
  }

  spec {
    schedule                      = var.paper_tick_schedule
    concurrency_policy            = "Forbid" # never overlap ticks for the same book
    starting_deadline_seconds     = 60
    successful_jobs_history_limit = 3
    failed_jobs_history_limit     = 3

    job_template {
      metadata {
        labels = local.worker_pod_labels
      }

      spec {
        active_deadline_seconds = var.paper_tick_active_deadline_seconds
        backoff_limit           = 0
        ttl_seconds_after_finished = 600

        template {
          metadata {
            labels = local.worker_pod_labels
          }

          spec {
            restart_policy = "Never"

            node_selector = {
              workload = "paper"
            }

            toleration {
              key      = "workload"
              operator = "Equal"
              value    = "paper"
              effect   = "NoSchedule"
            }

            automount_service_account_token = false

            container {
              name              = "paper-tick"
              image             = var.worker_image
              image_pull_policy = "IfNotPresent"
              command           = ["python", "-m", "doomberg_runtime.live_runner"]

              env {
                name  = "DOOMBERG_MODE"
                value = "paper"
              }
              env {
                name  = "DATA_GATEWAY_URL"
                value = "http://data-gateway.${var.data_gateway_namespace}.svc.cluster.local:${var.data_gateway_port}"
              }

              resources {
                requests = {
                  cpu    = "250m"
                  memory = "512Mi"
                }
                limits = {
                  cpu    = "1"
                  memory = "1Gi"
                }
              }

              security_context {
                run_as_non_root            = true
                read_only_root_filesystem  = true
                allow_privilege_escalation = false

                capabilities {
                  drop = ["ALL"]
                }
              }
            }
          }
        }
      }
    }
  }
}
