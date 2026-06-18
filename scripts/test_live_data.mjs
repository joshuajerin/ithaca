// Live smoke test for the market-data endpoints in api/[...path].js.
// Imports the REAL handler and drives it with mock req/res objects, hitting
// live Yahoo Finance upstreams. No mocked data — every assertion is against a
// genuine upstream response. Exit non-zero on any failure.
import handler from "../api/[...path].js";

function mockReq(method, url) {
  return { method, url, headers: { host: "doomberg.me" } };
}

function mockRes() {
  return {
    statusCode: 200,
    _headers: {},
    _body: "",
    setHeader(k, v) { this._headers[k.toLowerCase()] = v; },
    end(body) { this._body = body || ""; this._done = true; },
  };
}

async function call(method, url) {
  const req = mockReq(method, url);
  const res = mockRes();
  await handler(req, res);
  let json = null;
  try { json = res._body ? JSON.parse(res._body) : null; } catch { /* non-json */ }
  return { status: res.statusCode, headers: res._headers, json };
}

let failures = 0;
function check(name, cond, detail) {
  const ok = Boolean(cond);
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
  if (!ok) failures += 1;
}

const tests = [
  async () => {
    const r = await call("GET", "/api/healthz");
    check("healthz 200", r.status === 200);
    check("healthz advertises liveData", r.json?.liveData?.source === "yahoo-finance");
  },
  async () => {
    const r = await call("GET", "/api/market/quote?symbols=AAPL,NVDA,MSFT");
    check("quote 200", r.status === 200, `status=${r.status}`);
    check("quote returns >=1", (r.json?.quotes?.length || 0) >= 1, `count=${r.json?.count}`);
    const aapl = r.json?.quotes?.find((q) => q.symbol === "AAPL");
    check("AAPL has real price", typeof aapl?.price === "number" && aapl.price > 0, `price=${aapl?.price}`);
    check("CORS header present", r.headers["access-control-allow-origin"] === "*");
  },
  async () => {
    const r = await call("GET", "/api/market/history?symbol=AAPL&range=1mo&interval=1d");
    check("history 200", r.status === 200, `status=${r.status}`);
    check("history has points", (r.json?.points?.length || 0) > 5, `count=${r.json?.count}`);
    const p = r.json?.points?.[0];
    check("history point shape", p && typeof p.c === "number" && typeof p.t === "string", JSON.stringify(p));
  },
  async () => {
    const r = await call("GET", "/api/market/news?q=AAPL&limit=5");
    check("news 200", r.status === 200, `status=${r.status}`);
    check("news returns items", (r.json?.news?.length || 0) >= 1, `count=${r.json?.count}`);
    const n = r.json?.news?.[0];
    check("news item has title+link", n && n.title && n.link, n?.title);
  },
  async () => {
    const r = await call("GET", "/api/market/search?q=apple");
    check("search 200", r.status === 200, `status=${r.status}`);
    check("search finds AAPL", (r.json?.results || []).some((x) => x.symbol === "AAPL"));
  },
  async () => {
    const r = await call("GET", "/api/market/movers?limit=5");
    check("movers 200", r.status === 200, `status=${r.status}`);
    check("movers has gainers", (r.json?.gainers?.length || 0) >= 1, `gainers=${r.json?.gainers?.length}`);
    check("movers has losers", (r.json?.losers?.length || 0) >= 1, `losers=${r.json?.losers?.length}`);
  },
  async () => {
    const r = await call("GET", "/api/market/quote");
    check("quote missing symbols -> 400", r.status === 400, `status=${r.status}`);
  },
];

for (const t of tests) {
  // eslint-disable-next-line no-await-in-loop
  await t();
}

console.log(`\n${failures === 0 ? "ALL GREEN" : failures + " FAILURE(S)"}`);
process.exit(failures === 0 ? 0 : 1);
