// API base. Defaults to same-origin "/api" (the Vite dev proxy or a reverse proxy in prod).
// Override at build/dev time with VITE_API_BASE, e.g. VITE_API_BASE=http://localhost:8000/api.
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

// Local-dev tenant. The rest-gateway requires X-Tenant-Id (a UUID string) on every request.
// Override with VITE_TENANT_ID. This is the single hard isolation key the UI sends.
export const TENANT_ID: string =
  (import.meta.env.VITE_TENANT_ID as string | undefined) ??
  "00000000-0000-0000-0000-000000000001";
