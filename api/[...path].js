const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

// Per-tenant Hermes endpoint selection. Each site has its OWN isolated Hermes
// sandbox (separate session + system prompt) exposed at a distinct path on the
// shared tunnel. Falls back to the legacy single-endpoint env vars so an
// unconfigured per-tenant key degrades gracefully instead of 500-ing.
function hermesForTenant(id) {
  const base = (process.env.HERMES_BASE_URL || "").replace(/\/+$/, "");
  const perTenant = {
    doomberg: { path: "/doomberg", keyEnv: "DOOMBERG_HERMES_KEY" },
    kural: { path: "/kural", keyEnv: "KURAL_HERMES_KEY" },
  }[id];
  if (base && perTenant && process.env[perTenant.keyEnv]) {
    return { endpoint: `${base}${perTenant.path}`, key: process.env[perTenant.keyEnv] };
  }
  // Legacy fallback only when explicitly configured. Never leak prompts to a baked-in tunnel.
  const endpoint = (process.env.HERMES_AI_ENDPOINT || "").replace(/\/+$/, "");
  return { endpoint, key: endpoint ? process.env.HERMES_AI_API_KEY : undefined };
}

function tenantFromHost(req) {
  const host = String(req.headers.host || "").split(":")[0].toLowerCase();
  if (host.includes("kural.website")) return { id: "kural", name: "Kural", host };
  if (host.includes("doomberg.me")) return { id: "doomberg", name: "Doomberg", host };
  return { id: "doomberg", name: "Doomberg", host: host || "unknown" };
}

function sendJson(res, status, payload, headers = {}) {
  res.statusCode = status;
  for (const [key, value] of Object.entries({ ...JSON_HEADERS, ...headers })) {
    res.setHeader(key, value);
  }
  res.end(JSON.stringify(payload));
}

function envFlag(name) {
  return ["1", "true", "yes", "on"].includes(String(process.env[name] || "").trim().toLowerCase());
}

function legacyApiEnabled() {
  const env = String(process.env.NODE_ENV || "").trim().toLowerCase();
  return envFlag("DOOMBERG_ENABLE_LEGACY_VERCEL_API") || ["test", "local", "dev", "development"].includes(env);
}

function identityForTenant(tenant) {
  return {
    user: {
      id: `${tenant.id}-operator`,
      name: `${tenant.name} Operator`,
      email: `operator@${tenant.id}.local`,
      role: "owner",
    },
    firm: {
      id: `${tenant.id}-firm`,
      name: tenant.name,
    },
    permissions: [
      "terminal:use",
      "dashboard:read",
      "dashboard:write",
      "watchlist:read",
      "watchlist:write",
      "admin:read",
    ],
  };
}

function parsePath(req) {
  const url = new URL(req.url || "/", "https://example.local");
  return url.pathname.replace(/^\/api\/?/, "").replace(/\/+$/, "");
}

async function readBody(req) {
  if (req.body && typeof req.body === "object") return req.body;
  if (typeof req.body === "string") return req.body ? JSON.parse(req.body) : {};
  const chunks = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  const raw = Buffer.concat(chunks).toString("utf8");
  return raw ? JSON.parse(raw) : {};
}

async function supabaseInsert(table, row) {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return { ok: false, skipped: true, reason: "supabase_not_configured" };
  const endpoint = `${url.replace(/\/+$/, "")}/rest/v1/${table}`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      apikey: key,
      authorization: `Bearer ${key}`,
      prefer: "return=minimal",
    },
    body: JSON.stringify(row),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    return { ok: false, status: response.status, error: text.slice(0, 500) };
  }
  return { ok: true };
}

async function callHermes({ query, messages, tenant, sessionId }) {
  const { endpoint, key } = hermesForTenant(tenant.id);
  if (!endpoint || !key) {
    throw new Error("Hermes endpoint/key is not configured (set HERMES_BASE_URL with tenant keys, or explicit HERMES_AI_ENDPOINT and HERMES_AI_API_KEY)");
  }
  const system = [
    `You are the AI backend for ${tenant.name} at ${tenant.host}.`,
    "Answer directly and concisely. If the user asks for financial analysis, be useful but avoid pretending to place trades or access private brokerage data.",
    "Keep Doomberg and Kural logically separate by host, but use the shared backend memory/database safely.",
  ].filter(Boolean).join("\n");

  const payload = messages
    ? { messages, system, sessionId }
    : { message: query, system, sessionId };

  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${key}`,
    },
    body: JSON.stringify(payload),
  });
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!response.ok) {
    const msg = data?.error?.message || data?.message || text || `Hermes HTTP ${response.status}`;
    throw new Error(msg);
  }
  const content = data?.choices?.[0]?.message?.content || data?.message?.content || data?.content || data?.raw || "";
  return { content: String(content), upstream: data };
}

function dashboardResult({ tenant, query, answer, sessionId, degraded = false, note = null }) {
  const id = sessionId || `${tenant.id}-${Date.now().toString(36)}`;
  return {
    sessionId: id,
    summary: answer || `Ready for ${tenant.name}.`,
    panels: [],
    narration: [{ text: answer || `Ready for ${tenant.name}.`, panelId: null }],
    intent: "question",
    answer: answer || null,
    degraded,
    note,
  };
}

async function handleOrchestrate(req, res, tenant, stream = false) {
  const body = await readBody(req);
  const query = String(body.query || body.message || body.prompt || "").trim();
  if (!query) return sendJson(res, 400, { detail: "query is required" });
  const started = Date.now();
  let result;
  try {
    const hermes = await callHermes({ query, tenant, sessionId: body.sessionId });
    result = dashboardResult({ tenant, query, answer: hermes.content, sessionId: body.sessionId });
    await supabaseInsert("ai_interactions", {
      tenant_id: tenant.id,
      host: tenant.host,
      session_id: result.sessionId,
      request_kind: stream ? "orchestrate_stream" : "orchestrate",
      prompt: query,
      response: hermes.content,
      status: "ok",
      latency_ms: Date.now() - started,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    result = dashboardResult({
      tenant,
      query,
      answer: `AI backend is not ready: ${message}`,
      sessionId: body.sessionId,
      degraded: true,
      note: "Hermes AI proxy failed.",
    });
    await supabaseInsert("ai_interactions", {
      tenant_id: tenant.id,
      host: tenant.host,
      session_id: result.sessionId,
      request_kind: stream ? "orchestrate_stream" : "orchestrate",
      prompt: query,
      response: result.answer,
      status: "error",
      error: message,
      latency_ms: Date.now() - started,
    });
  }

  if (!stream) return sendJson(res, 200, result);

  const text = result.answer || result.summary || "";
  res.statusCode = 200;
  res.setHeader("content-type", "text/event-stream; charset=utf-8");
  res.setHeader("cache-control", "no-store");
  res.setHeader("connection", "keep-alive");
  const chunks = text.match(/.{1,48}(\s|$)/g) || [text];
  for (const chunk of chunks) {
    res.write(`data: ${JSON.stringify({ type: "delta", text: chunk })}\n\n`);
  }
  res.write(`data: ${JSON.stringify({ type: "done", result })}\n\n`);
  res.end();
}

async function handleAiProxy(req, res, tenant) {
  const body = await readBody(req);
  const started = Date.now();
  const query = String(body.query || body.message || body.prompt || body.input || "").trim();
  const messages = Array.isArray(body.messages) ? body.messages : undefined;
  try {
    const hermes = await callHermes({ query, messages, tenant, sessionId: body.sessionId });
    await supabaseInsert("ai_interactions", {
      tenant_id: tenant.id,
      host: tenant.host,
      session_id: body.sessionId || `${tenant.id}-${Date.now().toString(36)}`,
      request_kind: "ai_proxy",
      prompt: query || JSON.stringify(messages || []).slice(0, 8000),
      response: hermes.content,
      status: "ok",
      latency_ms: Date.now() - started,
    });
    return sendJson(res, 200, hermes.upstream);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    await supabaseInsert("ai_interactions", {
      tenant_id: tenant.id,
      host: tenant.host,
      session_id: body.sessionId || `${tenant.id}-${Date.now().toString(36)}`,
      request_kind: "ai_proxy",
      prompt: query || JSON.stringify(messages || []).slice(0, 8000),
      response: null,
      status: "error",
      error: message,
      latency_ms: Date.now() - started,
    });
    return sendJson(res, 502, { error: { message } });
  }
}

export default async function handler(req, res) {
  const tenant = tenantFromHost(req);
  const path = parsePath(req);

  if (req.method === "OPTIONS") return sendJson(res, 204, {});
  if (req.method === "GET" && path === "healthz") {
    const { key } = hermesForTenant(tenant.id);
    return sendJson(res, 200, {
      status: "ok",
      tenant: tenant.id,
      hermesConfigured: Boolean(key),
      supabaseConfigured: Boolean(process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY),
    });
  }
  if (!legacyApiEnabled()) return sendJson(res, 404, { detail: `Unknown API route: /api/${path}` });
  if (req.method === "GET" && path === "auth/user") return sendJson(res, 200, identityForTenant(tenant));
  if (req.method === "POST" && ["auth/login", "auth/signup", "auth/accept-invite"].includes(path)) {
    res.setHeader("set-cookie", `at_session=${tenant.id}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000`);
    return sendJson(res, 200, identityForTenant(tenant));
  }
  if (req.method === "POST" && path === "auth/logout") {
    res.setHeader("set-cookie", "at_session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0");
    return sendJson(res, 200, { ok: true });
  }
  if (req.method === "GET" && path === "skills") return sendJson(res, 200, []);
  if (req.method === "GET" && path === "sectors") return sendJson(res, 200, []);
  if (req.method === "GET" && path === "suggestions") {
    return sendJson(res, 200, [
      "Give me a market brief",
      "Explain today's biggest macro risk",
      "Compare NVDA and MSFT",
    ]);
  }
  if (req.method === "GET" && path === "dashboard/default") return sendJson(res, 200, dashboardResult({ tenant, query: "default", answer: `Welcome to ${tenant.name}. Ask the AI console anything.`, sessionId: `${tenant.id}-default` }));
  if (req.method === "GET" && path === "dashboards") return sendJson(res, 200, []);
  if (req.method === "POST" && path === "dashboards") return sendJson(res, 201, { id: `${tenant.id}-${Date.now().toString(36)}` });
  if (req.method === "GET" && path === "watchlist") return sendJson(res, 200, []);
  if (req.method === "POST" && path === "watchlist") return sendJson(res, 201, await readBody(req));
  if (req.method === "DELETE" && path.startsWith("watchlist/")) return sendJson(res, 200, { ok: true });
  if (req.method === "POST" && path === "orchestrate") return handleOrchestrate(req, res, tenant, false);
  if (req.method === "POST" && path === "orchestrate/stream") return handleOrchestrate(req, res, tenant, true);
  if (req.method === "POST" && path === "ai") return handleAiProxy(req, res, tenant);
  if (req.method === "POST" && path === "navigate") return sendJson(res, 200, { stops: [] });
  if (req.method === "POST" && path === "speak") return sendJson(res, 200, { audio: "", format: "none" });
  if (req.method === "POST" && path === "transcribe") return sendJson(res, 200, { text: "" });

  return sendJson(res, 404, { detail: `Unknown API route: /api/${path}` });
}
