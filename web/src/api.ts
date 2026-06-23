import { API_BASE, API_KEY, TENANT_ID } from "./config";
import type { RunRow, SessionRow, StrategyRow } from "./types";

// Thin REST client over the rest-gateway. The browser NEVER speaks MCP; this is the only
// backend it knows. Two auth modes, resolved at the gateway's single front door:
//   - Prod:  VITE_API_KEY set -> `Authorization: Bearer <key>`; the gateway derives the
//            tenant from the key (the authoritative isolation source).
//   - Dev:   no key -> the X-Tenant-Id header carries the tenant (local-dev fallback).

function headers(): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const oauthToken = localStorage.getItem("doomberg.token");
  if (oauthToken) {
    h.Authorization = `Bearer ${oauthToken}`;
  } else if (API_KEY) {
    h.Authorization = `Bearer ${API_KEY}`;
  } else {
    h["X-Tenant-Id"] = TENANT_ID;
  }
  return h;
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: headers(), signal });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`GET ${path} -> ${res.status} ${res.statusText}${body ? `: ${body}` : ""}`);
  }
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body ?? {}),
    signal,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`POST ${path} -> ${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
  }
  return (await res.json()) as T;
}

async function delJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE", headers: headers(), signal });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`DELETE ${path} -> ${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
  }
  return (await res.json()) as T;
}

// The gateway may return a bare array or { runs: [...] } / { items: [...] }; normalize.
function unwrapList<T>(raw: unknown, key: string): T[] {
  if (Array.isArray(raw)) return raw as T[];
  if (raw && typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    for (const k of [key, "items", "data"]) {
      if (Array.isArray(obj[k])) return obj[k] as T[];
    }
  }
  return [];
}

export const api = {
  tenantId: TENANT_ID,
  apiBase: API_BASE,

  async listRuns(kind?: string, signal?: AbortSignal): Promise<RunRow[]> {
    const q = kind ? `?kind=${encodeURIComponent(kind)}` : "";
    const raw = await getJson<unknown>(`/runs${q}`, signal);
    return unwrapList<RunRow>(raw, "runs");
  },

  async listSessions(signal?: AbortSignal): Promise<SessionRow[]> {
    const raw = await getJson<unknown>(`/sessions`, signal);
    return unwrapList<SessionRow>(raw, "sessions");
  },

  async getRun(id: string, signal?: AbortSignal): Promise<RunRow> {
    return getJson<RunRow>(`/runs/${encodeURIComponent(id)}`, signal);
  },

  async getSession(id: string, signal?: AbortSignal): Promise<RunRow> {
    return getJson<RunRow>(`/runs/${encodeURIComponent(id)}`, signal);
  },

  async createSession(prompt: string, title?: string, signal?: AbortSignal): Promise<RunRow> {
    return postJson<RunRow>(`/sessions`, { prompt, title }, signal);
  },

  async listStrategies(signal?: AbortSignal): Promise<StrategyRow[]> {
    const raw = await getJson<unknown>(`/strategies`, signal);
    return unwrapList<StrategyRow>(raw, "strategies");
  },

  // The /api/runs/{id}/events SSE URL. EventSource cannot set headers, so the tenant
  // is passed as a query param in local dev. Signed-in users pass the session token as
  // access_token so the stream resolves to the same tenant/account as normal REST calls.
  eventsUrl(id: string): string {
    const url = new URL(`${API_BASE}/runs/${encodeURIComponent(id)}/events`, window.location.origin);
    const oauthToken = localStorage.getItem("doomberg.token");
    if (oauthToken) {
      url.searchParams.set("access_token", oauthToken);
    } else {
      url.searchParams.set("tenant_id", TENANT_ID);
    }
    return API_BASE.startsWith("http") ? url.toString() : `${url.pathname}${url.search}${url.hash}`;
  },

  async getBook(id: string, signal?: AbortSignal): Promise<Record<string, unknown> | null> {
    const raw = await getJson<{ book: Record<string, unknown> | null }>(
      `/runs/${encodeURIComponent(id)}/book`,
      signal,
    );
    return raw.book ?? null;
  },

  // Write actions: the UI is the human actor (the gateway defaults X-Actor-Kind to "user").
  async proposeStrategy(spec: Record<string, unknown>, signal?: AbortSignal): Promise<RunRow> {
    return postJson<RunRow>(`/strategies`, { spec }, signal);
  },

  async createRun(strategy_id: string, kind: "backtest" | "paper", range = "1y", signal?: AbortSignal): Promise<RunRow> {
    return postJson<RunRow>(`/runs`, { strategy_id, kind, range }, signal);
  },

  // Human-only money-path actions, served by the gateway over the shared control-plane
  // implementation. Agents may NOT call these (the gateway/control-plane enforce it).
  async promoteRun(id: string, signal?: AbortSignal): Promise<RunRow> {
    return postJson<RunRow>(`/runs/${encodeURIComponent(id)}/promote`, {}, signal);
  },

  async runAction(
    id: string,
    action: "promote" | "activate" | "pause" | "resume" | "retire",
    signal?: AbortSignal,
  ): Promise<RunRow> {
    return postJson<RunRow>(`/runs/${encodeURIComponent(id)}/${action}`, {}, signal);
  },

  // ---- auth ------------------------------------------------------------------
  async signUp(email: string, name: string, password: string) {
    return postJson<{ user: Record<string, unknown>; token: string }>(
      `/auth/signup`,
      { email, name, password },
    );
  },

  async signIn(email: string, password: string) {
    return postJson<{ user: Record<string, unknown>; token: string }>(
      `/auth/signin`,
      { email, password },
    );
  },

  async signOut() {
    await postJson(`/auth/signout`, {}).catch(() => null);
  },

  async me() {
    return getJson<Record<string, unknown>>(`/auth/me`);
  },

  // ---- MCP / agent API keys (signed-in user mints for their own tenant) -------
  async mintKey(scopes?: string[]) {
    return postJson<{ api_key: string; key_id: string; scopes: string[]; tenant_id: string }>(
      `/auth/keys`,
      scopes && scopes.length ? { scopes } : {},
    );
  },

  async listKeys() {
    const raw = await getJson<{
      keys: Array<{ key_id: string; scopes: string[]; created_at: string; revoked: boolean }>;
    }>(`/auth/keys`);
    return raw.keys ?? [];
  },

  async revokeKey(keyId: string) {
    return delJson<{ key_id: string; revoked: boolean }>(`/auth/keys/${encodeURIComponent(keyId)}`);
  },
};
