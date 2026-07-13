import { API_BASE, API_KEY, TENANT_ID } from "./config";
import type {
  ApprovalRow,
  ArtifactRow,
  DatasetSnapshotRow,
  JobRow,
  LiveDataSmokeStatus,
  OrderIntentRow,
  OpsStatus,
  ProviderConnectionRow,
  RunRow,
  SessionRow,
  StrategyRow,
  TriggerDryRunResult,
  TriggerRow,
  AdaptiveDashboardResponse,
} from "./types";

export interface ProviderConnectionInput {
  provider: string;
  capabilities?: string[];
  entitlements?: Array<Record<string, unknown>>;
  state?: string;
  connection_id?: string;
  retention_policy?: string;
}

export type AgentToolkitsErrorKind = "auth-required" | "unavailable" | "fetch-failed";

export class AgentToolkitsError extends Error {
  kind: AgentToolkitsErrorKind;
  status?: number;

  constructor(kind: AgentToolkitsErrorKind, message: string, status?: number) {
    super(message);
    this.name = "AgentToolkitsError";
    this.kind = kind;
    this.status = status;
  }
}

export interface AgentCatalogTool {
  name: string;
  description?: string;
}

export interface AgentToolkit {
  toolkit_id: string;
  name: string;
  description: string;
  required_first_tool?: string;
  direct_tool_count: number;
  skill_count?: number;
  direct_tools: string[];
  tools: AgentCatalogTool[];
}

export interface AgentToolkitsCatalog {
  source: "live";
  kind?: string;
  toolkits: AgentToolkit[];
}

// Thin REST client over the rest-gateway. The browser NEVER speaks MCP; this is the only
// backend it knows. Two auth modes, resolved at the gateway's single front door:
//   - Prod:  Clerk session token or VITE_API_KEY -> `Authorization: Bearer <token>`;
//            the gateway derives the tenant from the credential.
//   - Dev:   no token/key -> X-Tenant-Id carries the tenant only when the gateway's local
//            dev fallback is enabled.

let authTokenProvider: (() => Promise<string | null>) | null = null;

export function setAuthTokenProvider(provider: (() => Promise<string | null>) | null): void {
  authTokenProvider = provider;
}

async function headers(): Promise<HeadersInit> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const clerkToken = authTokenProvider ? await authTokenProvider() : null;
  if (clerkToken) {
    h.Authorization = `Bearer ${clerkToken}`;
  } else if (API_KEY) {
    h.Authorization = `Bearer ${API_KEY}`;
  } else {
    h["X-Tenant-Id"] = TENANT_ID;
  }
  return h;
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: await headers(), signal });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`GET ${path} -> ${res.status} ${res.statusText}${body ? `: ${body}` : ""}`);
  }
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: await headers(),
    body: JSON.stringify(body ?? {}),
    signal,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`POST ${path} -> ${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
  }
  return (await res.json()) as T;
}

async function getBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  const res = await fetch(`${API_BASE}${path}`, { headers: await headers(), signal });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`GET ${path} -> ${res.status} ${res.statusText}${body ? `: ${body}` : ""}`);
  }
  return res.blob();
}

async function delJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE", headers: await headers(), signal });
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

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function stringList(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];
}

function catalogTools(v: unknown): AgentCatalogTool[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((item) => {
    if (typeof item === "string" && item.trim()) return [{ name: item.trim() }];
    const obj = rec(item);
    const name = typeof obj.name === "string" ? obj.name.trim() : "";
    if (!name) return [];
    const description = typeof obj.description === "string" ? obj.description : undefined;
    return [{ name, description }];
  });
}

function normalizeAgentToolkits(raw: unknown): AgentToolkitsCatalog {
  const obj = rec(raw);
  const rows = unwrapList<unknown>(raw, "toolkits");
  return {
    source: "live",
    kind: typeof obj.kind === "string" ? obj.kind : undefined,
    toolkits: rows.flatMap((row): AgentToolkit[] => {
      const item = rec(row);
      const id = typeof item.toolkit_id === "string"
        ? item.toolkit_id
        : typeof item.id === "string"
          ? item.id
          : "";
      if (!id.trim()) return [];
      const directTools = stringList(item.direct_tools);
      const tools = catalogTools(item.tools);
      const directToolCount = typeof item.direct_tool_count === "number"
        ? item.direct_tool_count
        : directTools.length;
      return [{
        toolkit_id: id,
        name: typeof item.name === "string" && item.name.trim() ? item.name : id,
        description: typeof item.description === "string" ? item.description : "",
        required_first_tool: typeof item.required_first_tool === "string" ? item.required_first_tool : undefined,
        direct_tool_count: directToolCount,
        skill_count: typeof item.skill_count === "number" ? item.skill_count : undefined,
        direct_tools: directTools,
        tools,
      }];
    }),
  };
}

const AGENT_TOOLKIT_CATALOG_PATHS = ["/agent/toolkits", "/mcp/toolkits", "/toolkits/catalog"];

async function getAgentToolkits(signal?: AbortSignal): Promise<AgentToolkitsCatalog> {
  let lastNotFound = "";
  for (const path of AGENT_TOOLKIT_CATALOG_PATHS) {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}${path}`, { headers: await headers(), signal });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new AgentToolkitsError(
        "fetch-failed",
        error instanceof Error ? error.message : String(error),
      );
    }
    if (res.status === 404) {
      lastNotFound = path;
      continue;
    }
    if (res.status === 401 || res.status === 403) {
      const body = await res.text().catch(() => "");
      throw new AgentToolkitsError(
        "auth-required",
        `GET ${path} -> ${res.status} ${res.statusText}${body ? `: ${body}` : ""}`,
        res.status,
      );
    }
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new AgentToolkitsError(
        "fetch-failed",
        `GET ${path} -> ${res.status} ${res.statusText}${body ? `: ${body}` : ""}`,
        res.status,
      );
    }
    return normalizeAgentToolkits(await res.json());
  }
  throw new AgentToolkitsError(
    "unavailable",
    `No REST agent toolkit catalog endpoint found${lastNotFound ? `; last tried ${lastNotFound}` : ""}.`,
    404,
  );
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

  async createSession(prompt = "", title?: string, signal?: AbortSignal): Promise<RunRow> {
    return postJson<RunRow>(`/sessions`, { prompt, title }, signal);
  },

  async submitFeedback(message: string, signal?: AbortSignal): Promise<{
    feedback_id: string;
    status: "received";
    created_at: string;
  }> {
    return postJson(`/feedback`, { message }, signal);
  },

  async listStrategies(signal?: AbortSignal): Promise<StrategyRow[]> {
    const raw = await getJson<unknown>(`/strategies`, signal);
    return unwrapList<StrategyRow>(raw, "strategies");
  },

  async listJobs(signal?: AbortSignal): Promise<JobRow[]> {
    const raw = await getJson<unknown>(`/jobs`, signal);
    return unwrapList<JobRow>(raw, "jobs");
  },

  async getOpsStatus(signal?: AbortSignal): Promise<OpsStatus> {
    return getJson<OpsStatus>(`/ops/status`, signal);
  },

  async getAdaptiveDashboard(signal?: AbortSignal): Promise<AdaptiveDashboardResponse> {
    return getJson<AdaptiveDashboardResponse>(`/dashboard/adaptive`, signal);
  },

  async liveDataSmoke(symbol = "AAPL", signal?: AbortSignal): Promise<LiveDataSmokeStatus> {
    return getJson<LiveDataSmokeStatus>(`/ops/live-data-smoke?symbol=${encodeURIComponent(symbol)}`, signal);
  },

  async listArtifacts(signal?: AbortSignal): Promise<ArtifactRow[]> {
    const raw = await getJson<unknown>(`/artifacts`, signal);
    return unwrapList<ArtifactRow>(raw, "artifacts");
  },

  async listApprovals(signal?: AbortSignal): Promise<ApprovalRow[]> {
    const raw = await getJson<unknown>(`/approvals`, signal);
    return unwrapList<ApprovalRow>(raw, "approvals");
  },

  async decideApproval(id: string, decision: "approved" | "denied", reason?: string, signal?: AbortSignal) {
    return postJson<ApprovalRow>(
      `/approvals/${encodeURIComponent(id)}/decide`,
      { decision, reason },
      signal,
    );
  },

  async listOrderIntents(signal?: AbortSignal): Promise<OrderIntentRow[]> {
    const raw = await getJson<unknown>(`/order-intents`, signal);
    return unwrapList<OrderIntentRow>(raw, "order_intents");
  },

  async getOrderIntent(id: string, signal?: AbortSignal): Promise<OrderIntentRow> {
    return getJson<OrderIntentRow>(`/order-intents/${encodeURIComponent(id)}`, signal);
  },

  async createOrderIntent(body: {
    run_id: string;
    payload: Record<string, unknown>;
    strategy_id?: string | null;
    account_ref?: string | null;
    idempotency_key?: string | null;
  }, signal?: AbortSignal): Promise<OrderIntentRow> {
    return postJson<OrderIntentRow>(`/order-intents`, body, signal);
  },

  async previewOrderIntent(id: string, signal?: AbortSignal): Promise<OrderIntentRow> {
    return postJson<OrderIntentRow>(`/order-intents/${encodeURIComponent(id)}/preview`, {}, signal);
  },

  async submitOrderIntent(id: string, signal?: AbortSignal): Promise<OrderIntentRow> {
    return postJson<OrderIntentRow>(`/order-intents/${encodeURIComponent(id)}/submit`, {}, signal);
  },

  async listProviders(signal?: AbortSignal): Promise<{
    connections: ProviderConnectionRow[];
    snapshots: DatasetSnapshotRow[];
  }> {
    const raw = await getJson<{ connections?: ProviderConnectionRow[]; snapshots?: DatasetSnapshotRow[] }>(
      `/providers`,
      signal,
    );
    return { connections: raw.connections ?? [], snapshots: raw.snapshots ?? [] };
  },

  async listAgentToolkits(signal?: AbortSignal): Promise<AgentToolkitsCatalog> {
    return getAgentToolkits(signal);
  },

  async upsertProviderConnection(body: ProviderConnectionInput, signal?: AbortSignal) {
    return postJson<ProviderConnectionRow>(`/providers`, body, signal);
  },

  async listTriggers(signal?: AbortSignal): Promise<TriggerRow[]> {
    const raw = await getJson<unknown>(`/triggers`, signal);
    return unwrapList<TriggerRow>(raw, "triggers");
  },

  async createTrigger(name: string, policy: Record<string, unknown>, state = "draft", signal?: AbortSignal) {
    return postJson<TriggerRow>(`/triggers`, { name, policy, state }, signal);
  },

  async dryRunTrigger(name: string, policy: Record<string, unknown>, signal?: AbortSignal) {
    return postJson<TriggerDryRunResult>(`/triggers/dry-run`, { name, policy }, signal);
  },

  async setTriggerState(triggerId: string, state: string, signal?: AbortSignal) {
    return postJson<TriggerRow>(
      `/triggers/${encodeURIComponent(triggerId)}/state`,
      { state },
      signal,
    );
  },

  async mintRunEventsTicket(id: string, afterSeq = -1, signal?: AbortSignal) {
    return postJson<{
      sse_ticket: string;
      run_id: string;
      tenant_id: string;
      expires_at: string;
      single_use: boolean;
      after_seq?: number;
    }>(`/runs/${encodeURIComponent(id)}/events-ticket`, { after_seq: afterSeq }, signal);
  },

  // The /api/runs/{id}/events SSE URL. EventSource cannot set headers, so production
  // streams use a short-lived one-time ticket minted over normal authenticated REST.
  // Local dev can still fall back to ?tenant_id= when no ticket was minted.
  eventsUrl(id: string, opts?: { sseTicket?: string; afterSeq?: number }): string {
    const url = new URL(`${API_BASE}/runs/${encodeURIComponent(id)}/events`, window.location.origin);
    if (opts?.sseTicket) {
      url.searchParams.set("sse_ticket", opts.sseTicket);
      if (typeof opts.afterSeq === "number" && opts.afterSeq >= 0) {
        url.searchParams.set("after_seq", String(opts.afterSeq));
      }
    } else {
      url.searchParams.set("tenant_id", TENANT_ID);
    }
    return API_BASE.startsWith("http") ? url.toString() : `${url.pathname}${url.search}${url.hash}`;
  },

  // Write actions: the UI is the human actor (the gateway defaults X-Actor-Kind to "user").
  async proposeStrategy(spec: Record<string, unknown>, signal?: AbortSignal): Promise<{ id: string; version: number; state: string }> {
    return postJson<{ id: string; version: number; state: string }>(`/strategies`, { spec }, signal);
  },

  async createRun(
    strategy_id: string,
    kind: "backtest" | "paper",
    range = "1y",
    signal?: AbortSignal,
    idempotency_key?: string,
  ): Promise<RunRow> {
    return postJson<RunRow>(`/runs`, { strategy_id, kind, range, idempotency_key }, signal);
  },

  async downloadArtifact(id: string, signal?: AbortSignal): Promise<Blob> {
    return getBlob(`/artifacts/${encodeURIComponent(id)}/download`, signal);
  },

  async runAction(
    id: string,
    action: "cancel" | "promote" | "activate" | "pause" | "resume" | "retire",
    body: Record<string, unknown> = {},
    signal?: AbortSignal,
  ): Promise<RunRow> {
    return postJson<RunRow>(`/runs/${encodeURIComponent(id)}/${action}`, body, signal);
  },

  // ---- auth ------------------------------------------------------------------
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
