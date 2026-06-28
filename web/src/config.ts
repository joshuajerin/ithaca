// API base. Defaults to same-origin "/api" (the Vite dev proxy or a reverse proxy in prod).
// Override at build/dev time with VITE_API_BASE, e.g. VITE_API_BASE=http://localhost:8000/api.
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

// Local-dev tenant. The rest-gateway requires X-Tenant-Id (a UUID string) on every request.
// Override with VITE_TENANT_ID. This is the single hard isolation key the UI sends.
export const TENANT_ID: string =
  (import.meta.env.VITE_TENANT_ID as string | undefined) ??
  "00000000-0000-0000-0000-000000000001";

// Production API key (dmbg_<env>_<keyid>_<secret>). When set, the UI authenticates with
// `Authorization: Bearer <key>` and the gateway derives the tenant from the key — the
// X-Tenant-Id header is only used as the local-dev fallback when no key is configured.
export const API_KEY: string | undefined =
  (import.meta.env.VITE_API_KEY as string | undefined) || undefined;

// Hosted MCP target for external agents.
export const MCP_BASE: string =
  (import.meta.env.VITE_MCP_BASE as string | undefined) || "https://mcp.doomberg.me/mcp";
