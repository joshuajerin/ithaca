# Default-deny egress for worker pods + a SINGLE allow to the Data Gateway.
#
# This is the cluster invariant from MASTER-PLAN §5.2/§5.7: workers reach data
# ONLY through the Data Gateway facade. Expressed as first-class
# kubernetes_network_policy resources so the egress-deny is reviewable IaC, not
# code. DOKS ships Cilium and enforces NetworkPolicy by default.
#
# NOTE: NetworkPolicy is namespaced. The worker namespace is created here so the
# policy has something to bind to; worker Deployments/Jobs land in it (see the
# job manifests in ./manifests).

resource "kubernetes_namespace" "workers" {
  metadata {
    name = var.worker_namespace

    labels = {
      "doomberg/role"                      = "workers"
      "pod-security.kubernetes.io/enforce" = "restricted"
    }
  }
}

resource "kubernetes_namespace" "gateway" {
  metadata {
    name = var.data_gateway_namespace

    labels = {
      "doomberg/role" = "data-gateway"
    }
  }
}

# 1) DEFAULT-DENY all egress (and ingress) for every pod in the worker namespace.
#    An empty podSelector matches all pods; empty egress/ingress = deny-all.
resource "kubernetes_network_policy" "workers_default_deny" {
  metadata {
    name      = "default-deny-all"
    namespace = kubernetes_namespace.workers.metadata[0].name
  }

  spec {
    pod_selector {} # all pods in the namespace

    policy_types = ["Ingress", "Egress"]
    # No ingress and no egress rules == deny everything.
  }
}

# 2) The single ALLOW exception: worker pods may egress to the Data Gateway
#    Service (by namespace + pod label) on its RPC port, plus the in-cluster
#    DNS needed to resolve that Service. Nothing else leaves the pod.
resource "kubernetes_network_policy" "workers_allow_gateway" {
  metadata {
    name      = "allow-egress-data-gateway"
    namespace = kubernetes_namespace.workers.metadata[0].name
  }

  spec {
    # Apply only to the worker pods (backtest + paper tick).
    pod_selector {
      match_labels = {
        "doomberg/component" = "worker"
      }
    }

    policy_types = ["Egress"]

    # Allow: the Data Gateway facade RPC.
    egress {
      to {
        namespace_selector {
          match_labels = {
            "doomberg/role" = "data-gateway"
          }
        }

        pod_selector {
          match_labels = {
            "doomberg/component" = "data-gateway"
          }
        }
      }

      ports {
        protocol = "TCP"
        port     = var.data_gateway_port
      }
    }

    # Allow: cluster DNS (kube-dns) so the Gateway Service name resolves.
    # Without this the deny-all above would also block name resolution.
    egress {
      to {
        namespace_selector {
          match_labels = {
            "kubernetes.io/metadata.name" = "kube-system"
          }
        }
      }

      ports {
        protocol = "UDP"
        port     = 53
      }
      ports {
        protocol = "TCP"
        port     = 53
      }
    }
  }
}
