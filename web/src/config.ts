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

export function shouldUseClerkApiToken(isDev: boolean, override?: string): boolean {
  if (override != null && override.trim() !== "") {
    return override.trim().toLowerCase() === "true";
  }
  return !isDev;
}

// Local Vite uses the gateway's X-Tenant-Id fallback. This keeps expired or revoked Clerk
// development sessions from shadowing the seeded local tenant with an invalid bearer token.
// Set VITE_USE_CLERK_API_AUTH=true only when intentionally testing Clerk-backed local APIs.
export const USE_CLERK_API_AUTH = shouldUseClerkApiToken(
  import.meta.env.DEV,
  import.meta.env.VITE_USE_CLERK_API_AUTH as string | undefined,
);

// Hosted MCP target for external agents.
export const MCP_BASE: string =
  (import.meta.env.VITE_MCP_BASE as string | undefined) || "https://mcp.tradeithaca.com/mcp";
