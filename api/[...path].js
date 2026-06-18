const HERMES_DEFAULT_ENDPOINT = "https://urban-baseball-nerve-offices.trycloudflare.com/portfolio-website";

const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,OPTIONS,DELETE",
  "access-control-allow-headers": "content-type,authorization",
};

// ---------------------------------------------------------------------------
// Live market data (keyless Yahoo Finance endpoints).
//
// Two upstreams that work without an API key from a server context:
//   - v8 chart  : real-time-ish quote + OHLCV history per symbol.
//   - v1 search : symbol lookup + fresh news headlines.
// The v7 batch-quote endpoint now returns Unauthorized, so quotes are fanned
// out one chart call per symbol (bounded) instead. Every value returned is the
// genuine upstream number — never synthesised. Upstream failures surface as a
// clean per-symbol error entry rather than a fabricated price.
// ---------------------------------------------------------------------------
const YF_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/";
const YF_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search";
const YF_UA = { "user-agent": "Mozilla/5.0 (compatible; DoombergTerminal/1.0)" };
const YF_TIMEOUT_MS = 12000;
const MAX_SYMBOLS = 25;

// A small, liquid default universe for the /movers endpoint when no symbols
// are supplied. These are well-known large caps; the move numbers are still the
// real upstream values, only the membership of the list is curated.
const MOVERS_UNIVERSE = [
  "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "AVGO",
  "JPM", "BAC", "XOM", "WMT", "DIS", "BA", "INTC", "PYPL", "CRM", "ORCL",
];

function round(v, p = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return null;
  const f = 10 ** p;
  return Math.round(Number(v) * f) / f;
}

function isoFromEpoch(sec) {
  if (!sec) return null;
  return new Date(Number(sec) * 1000).toISOString();
}

function parseSymbols(raw) {
  return String(raw || "")
    .split(",")
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, MAX_SYMBOLS);
}

async function yfFetch(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), YF_TIMEOUT_MS);
  try {
    const resp = await fetch(url, { headers: YF_UA, signal: controller.signal });
    if (!resp.ok) throw new Error(`upstream HTTP ${resp.status}`);
    return await resp.json();
  } finally {
    clearTimeout(timer);
  }
}

async function fetchQuote(symbol) {
  const url = `${YF_CHART}${encodeURIComponent(symbol)}?range=1d&interval=1d&includePrePost=false`;
  const data = await yfFetch(url);
  const r0 = data?.chart?.result?.[0];
  const err = data?.chart?.error;
  if (err) throw new Error(err?.description || err?.code || `no data for ${symbol}`);
  if (!r0?.meta) throw new Error(`no quote data for ${symbol}`);
  const m = r0.meta;
  const price = m.regularMarketPrice ?? null;
  const prev = m.chartPreviousClose ?? m.previousClose ?? null;
  let change = null;
  let changePct = null;
  if (price !== null && prev) {
    change = round(price - prev);
    changePct = round(((price - prev) / prev) * 100);
  }
  return {
    symbol: m.symbol || symbol.toUpperCase(),
    name: m.longName || m.shortName || null,
    price,
    change,
    changePct,
    currency: m.currency || "USD",
    marketState: m.marketState || null,
    exchange: m.fullExchangeName || m.exchangeName || null,
    dayHigh: m.regularMarketDayHigh ?? null,
    dayLow: m.regularMarketDayLow ?? null,
    open: m.regularMarketOpen ?? null,
    previousClose: prev,
    week52High: m.fiftyTwoWeekHigh ?? null,
    week52Low: m.fiftyTwoWeekLow ?? null,
    volume: m.regularMarketVolume ?? null,
    asOf: isoFromEpoch(m.regularMarketTime),
  };
}

async function fetchQuotes(symbols) {
  const settled = await Promise.allSettled(symbols.map((s) => fetchQuote(s)));
  const quotes = [];
  const errors = [];
  settled.forEach((r, i) => {
    if (r.status === "fulfilled") quotes.push(r.value);
    else errors.push({ symbol: symbols[i], error: r.reason instanceof Error ? r.reason.message : String(r.reason) });
  });
  return { quotes, errors };
}

async function fetchHistory(symbol, range = "6mo", interval = "1d") {
  const url = `${YF_CHART}${encodeURIComponent(symbol)}?range=${encodeURIComponent(range)}&interval=${encodeURIComponent(interval)}&includePrePost=false`;
  const data = await yfFetch(url);
  const r0 = data?.chart?.result?.[0];
  const err = data?.chart?.error;
  if (err) throw new Error(err?.description || err?.code || `no data for ${symbol}`);
  if (!r0) throw new Error(`no history for ${symbol}`);
  const m = r0.meta || {};
  const ts = r0.timestamp || [];
  const q = (r0.indicators?.quote || [{}])[0] || {};
  const o = q.open || [];
  const h = q.high || [];
  const l = q.low || [];
  const c = q.close || [];
  const v = q.volume || [];
  const intraday = /m$|^1h$|h$/.test(interval) && interval !== "1mo" && interval !== "3mo";
  const points = [];
  for (let i = 0; i < ts.length; i += 1) {
    const close = c[i];
    if (close === null || close === undefined) continue;
    const when = new Date(Number(ts[i]) * 1000);
    points.push({
      t: intraday ? when.toISOString() : when.toISOString().slice(0, 10),
      o: round(o[i] ?? close),
      h: round(h[i] ?? close),
      l: round(l[i] ?? close),
      c: round(close),
      v: Number(v[i] ?? 0) || 0,
    });
  }
  return {
    symbol: m.symbol || symbol.toUpperCase(),
    name: m.longName || m.shortName || null,
    currency: m.currency || "USD",
    range,
    interval,
    price: m.regularMarketPrice ?? null,
    asOf: isoFromEpoch(m.regularMarketTime),
    count: points.length,
    points,
  };
}

async function fetchNews(queryStr, limit = 10) {
  const n = Math.max(1, Math.min(50, Number(limit) || 10));
  const url = `${YF_SEARCH}?q=${encodeURIComponent(queryStr)}&newsCount=${n}&quotesCount=0&enableFuzzyQuery=false`;
  const data = await yfFetch(url);
  return (data?.news || []).slice(0, n).map((item) => ({
    uuid: item.uuid || null,
    title: item.title || null,
    publisher: item.publisher || null,
    link: item.link || null,
    publishedAt: isoFromEpoch(item.providerPublishTime),
    type: item.type || null,
    relatedTickers: item.relatedTickers || [],
    thumbnail: item.thumbnail?.resolutions?.[0]?.url || null,
  }));
}

async function fetchSearch(queryStr, limit = 10) {
  const n = Math.max(1, Math.min(20, Number(limit) || 10));
  const url = `${YF_SEARCH}?q=${encodeURIComponent(queryStr)}&quotesCount=${n}&newsCount=0&enableFuzzyQuery=false`;
  const data = await yfFetch(url);
  return (data?.quotes || [])
    .filter((q) => q.symbol)
    .slice(0, n)
    .map((q) => ({
      symbol: q.symbol,
      name: q.longname || q.shortname || null,
      exchange: q.exchDisp || q.exchange || null,
      type: q.quoteType || q.typeDisp || null,
      sector: q.sector || null,
      industry: q.industry || null,
    }));
}

async function fetchMovers(symbols, limit = 10) {
  const { quotes, errors } = await fetchQuotes(symbols);
  const ranked = quotes
    .filter((q) => q.changePct !== null)
    .sort((a, b) => b.changePct - a.changePct);
  const n = Math.max(1, Math.min(symbols.length, Number(limit) || 10));
  return {
    gainers: ranked.slice(0, n),
    losers: ranked.slice(-n).reverse(),
    universe: symbols,
    errors,
  };
}

function sendData(res, payload, { cacheSeconds = 15 } = {}) {
  return sendJson(res, 200, payload, {
    "cache-control": `public, max-age=0, s-maxage=${cacheSeconds}, stale-while-revalidate=60`,
  });
}

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
  // Legacy fallback: single shared endpoint + key.
  return {
    endpoint: (process.env.HERMES_AI_ENDPOINT || HERMES_DEFAULT_ENDPOINT).replace(/\/+$/, ""),
    key: process.env.HERMES_AI_API_KEY,
  };
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

async function callHermes({ query, messages, instructions, tenant, sessionId }) {
  const { endpoint, key } = hermesForTenant(tenant.id);
  if (!key) {
    throw new Error("Hermes key is not configured (set DOOMBERG_HERMES_KEY / KURAL_HERMES_KEY or HERMES_AI_API_KEY)");
  }
  const system = [
    `You are the AI backend for ${tenant.name} at ${tenant.host}.`,
    "Answer directly and concisely. If the user asks for financial analysis, be useful but avoid pretending to place trades or access private brokerage data.",
    "Keep Doomberg and Kural logically separate by host, but use the shared backend memory/database safely.",
    instructions || "",
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
    const hermes = await callHermes({ query, tenant, sessionId: body.sessionId, instructions: body.instructions });
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
    const hermes = await callHermes({ query, messages, tenant, instructions: body.system || body.instructions, sessionId: body.sessionId });
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
      liveData: {
        source: "yahoo-finance",
        endpoints: [
          "GET /api/market/quote?symbols=AAPL,NVDA",
          "GET /api/market/history?symbol=AAPL&range=6mo&interval=1d",
          "GET /api/market/news?q=AAPL&limit=10",
          "GET /api/market/search?q=apple",
          "GET /api/market/movers?limit=10",
        ],
      },
    });
  }
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

  // ---- Live market data (real, keyless Yahoo Finance upstreams) ------------
  if (req.method === "GET" && (path === "market/quote" || path === "market/quotes")) {
    const url = new URL(req.url || "/", "https://x.local");
    const symbols = parseSymbols(url.searchParams.get("symbols") || url.searchParams.get("symbol"));
    if (!symbols.length) return sendJson(res, 400, { detail: "symbols query param is required, e.g. ?symbols=AAPL,NVDA" });
    try {
      const { quotes, errors } = await fetchQuotes(symbols);
      if (!quotes.length) return sendJson(res, 502, { detail: "no quotes returned", errors });
      return sendData(res, { asOf: new Date().toISOString(), count: quotes.length, quotes, errors });
    } catch (err) {
      return sendJson(res, 502, { detail: err instanceof Error ? err.message : String(err) });
    }
  }
  if (req.method === "GET" && path === "market/history") {
    const url = new URL(req.url || "/", "https://x.local");
    const symbol = (url.searchParams.get("symbol") || "").trim().toUpperCase();
    if (!symbol) return sendJson(res, 400, { detail: "symbol query param is required, e.g. ?symbol=AAPL&range=6mo&interval=1d" });
    const range = url.searchParams.get("range") || "6mo";
    const interval = url.searchParams.get("interval") || "1d";
    try {
      return sendData(res, await fetchHistory(symbol, range, interval), { cacheSeconds: 60 });
    } catch (err) {
      return sendJson(res, 502, { detail: err instanceof Error ? err.message : String(err) });
    }
  }
  if (req.method === "GET" && path === "market/news") {
    const url = new URL(req.url || "/", "https://x.local");
    const q = (url.searchParams.get("q") || url.searchParams.get("symbol") || "stock market").trim();
    const limit = url.searchParams.get("limit") || 10;
    try {
      const news = await fetchNews(q, limit);
      return sendData(res, { query: q, count: news.length, news }, { cacheSeconds: 120 });
    } catch (err) {
      return sendJson(res, 502, { detail: err instanceof Error ? err.message : String(err) });
    }
  }
  if (req.method === "GET" && path === "market/search") {
    const url = new URL(req.url || "/", "https://x.local");
    const q = (url.searchParams.get("q") || "").trim();
    if (!q) return sendJson(res, 400, { detail: "q query param is required, e.g. ?q=apple" });
    try {
      const results = await fetchSearch(q, url.searchParams.get("limit") || 10);
      return sendData(res, { query: q, count: results.length, results }, { cacheSeconds: 300 });
    } catch (err) {
      return sendJson(res, 502, { detail: err instanceof Error ? err.message : String(err) });
    }
  }
  if (req.method === "GET" && path === "market/movers") {
    const url = new URL(req.url || "/", "https://x.local");
    const symbols = parseSymbols(url.searchParams.get("symbols")) ;
    const universe = symbols.length ? symbols : MOVERS_UNIVERSE;
    const limit = url.searchParams.get("limit") || 10;
    try {
      return sendData(res, { asOf: new Date().toISOString(), ...(await fetchMovers(universe, limit)) }, { cacheSeconds: 30 });
    } catch (err) {
      return sendJson(res, 502, { detail: err instanceof Error ? err.message : String(err) });
    }
  }

  return sendJson(res, 404, { detail: `Unknown API route: /api/${path}` });
}
