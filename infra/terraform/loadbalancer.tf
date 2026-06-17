# Public Load Balancer — ingress to the ALWAYS-ON gateways (mcp-gateway +
# rest-gateway). HA: size_unit >= 2. Lives in the VPC; forwards to the always-on
# (paper/gateway) node pool by droplet tag.
#
# Topology note: DOKS can also provision an LB implicitly from a
# `Service type=LoadBalancer`. We define the LB explicitly in Terraform instead
# so its IP is a stable, reviewable output (outputs.tf -> load_balancer_ip) and
# its HA size_unit is pinned. The always-on gateway pool is tagged so the LB and
# the cluster firewall can target it by tag rather than by ephemeral droplet id.

# Stable tag applied to the always-on (paper/gateway) pool droplets so the LB can
# target them without referencing ephemeral node ids.
locals {
  gateway_pool_tag = "${local.name_prefix}-gateway"
}

resource "digitalocean_loadbalancer" "gateways" {
  name      = "${local.name_prefix}-lb"
  region    = var.region
  size_unit = var.lb_size_unit
  vpc_uuid  = digitalocean_vpc.doomberg.id

  # Target the always-on gateway pool by tag (set on the node pool in main.tf).
  droplet_tag = local.gateway_pool_tag

  redirect_http_to_https = false

  # rest-gateway (REST + SSE) — the browser-facing surface.
  forwarding_rule {
    entry_port      = 80
    entry_protocol  = "http"
    target_port     = 30080 # NodePort the rest-gateway Service publishes
    target_protocol = "http"
  }

  # mcp-gateway — the primary product surface (MCP over HTTP/SSE).
  forwarding_rule {
    entry_port      = 8080
    entry_protocol  = "http"
    target_port     = 30808 # NodePort the mcp-gateway Service publishes
    target_protocol = "http"
  }

  # Reliability: drop a node out of rotation fast if the gateway is unhealthy.
  healthcheck {
    protocol                 = "http"
    port                     = 30080
    path                     = "/healthz"
    check_interval_seconds   = 5
    response_timeout_seconds = 3
    healthy_threshold        = 2
    unhealthy_threshold      = 3
  }

  depends_on = [digitalocean_kubernetes_node_pool.paper]
}
