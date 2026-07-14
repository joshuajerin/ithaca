"""HTTP transport + per-tenant bearer auth for the hosted MCP server.

Two layers, both network-free:

* the auth layer (Principal resolution + scope policy) exercised through the ASGI
  middleware directly with a real :class:`~ithaca_platform.AuthStore` on an in-memory
  Platform — valid key → principal, bad/missing/revoked → 401, scope-too-low → 403; and
* an HTTP-mode smoke test that drives the SDK's streamable-HTTP app via Starlette's
  ``TestClient`` (no real port) to prove auth + scope enforcement + per-request tenant
  injection wire together, and that a tool call is traced under the verified tenant.
"""
from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from ithaca_core import Core, DataGateway
from ithaca_mcp import (
    InMemoryTrace,
    Principal,
    TenantAuthMiddleware,
    Toolset,
    build_http_app,
    current_principal,
)
from ithaca_mcp.http import _bearer, _is_tool_call, _requires_data_read, _scope_needed
from ithaca_platform import Platform


# --------------------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------------------
@pytest.fixture
def platform() -> Platform:
    return Platform(":memory:")


@pytest.fixture
def tenant(platform) -> str:
    return platform.auth.create_tenant("acme")


@pytest.fixture
def keys(platform, tenant) -> dict[str, str]:
    """A spread of minted keys for the policy matrix."""
    full, _ = platform.auth.mint_key(tenant, ["data:read", "strategy:author"])
    run_only, _ = platform.auth.mint_key(tenant, ["data:read", "runs:write"])
    read_only, _ = platform.auth.mint_key(tenant, ["data:read"])
    alert_read, _ = platform.auth.mint_key(tenant, ["data:read", "alerts:read"])
    no_scope, _ = platform.auth.mint_key(tenant, [])  # a tenant key with no capabilities
    revoked, revoked_id = platform.auth.mint_key(tenant, ["data:read"])
    platform.auth.revoke_key(revoked_id)
    return {
        "full": full,
        "run_only": run_only,
        "read_only": read_only,
        "alert_read": alert_read,
        "no_scope": no_scope,
        "revoked": revoked,
    }


def _det_core() -> Core:
    """A network-free Core with a deterministic synthetic price source."""
    import datetime as dt

    def _days(n: int) -> list[str]:
        d = dt.date(2024, 1, 1)
        out: list[str] = []
        while len(out) < n:
            if d.weekday() < 5:
                out.append(d.isoformat())
            d += dt.timedelta(days=1)
        return out

    dates = _days(120)

    def _fetch(symbol, range_="1y", interval="1d"):
        pts = [{"d": dates[i], "o": 100 + i, "h": 100 + i, "l": 100 + i, "c": 100 + i,
                "v": 1e6} for i in range(len(dates))]
        return {"points": pts,
                "quote": {"symbol": symbol.upper(), "price": pts[-1]["c"],
                          "asOf": dates[-1] + "T20:00:00Z"}}

    return Core(DataGateway(fetch_history=_fetch))


# --------------------------------------------------------------------------------------
# unit: small pure helpers (the bearer parse + scope policy)
# --------------------------------------------------------------------------------------
def test_bearer_extracts_token():
    assert _bearer([(b"authorization", b"Bearer ith_test_abc_secret")]) == "ith_test_abc_secret"
    assert _bearer([(b"Authorization", b"bearer xyz")]) == "xyz"  # case-insensitive scheme+name
    assert _bearer([(b"authorization", b"Basic zzz")]) is None  # wrong scheme
    assert _bearer([]) is None  # no header


def test_scope_policy_recognizes_calls():
    # a market call: tools/call, needs data:read only (extra == "")
    body = json.dumps({"method": "tools/call", "params": {"name": "market_get_ohlcv"}}).encode()
    assert _is_tool_call(body) is True
    assert _scope_needed(body) == set()
    # propose_strategy: tools/call + the extra strategy:author scope
    body = json.dumps({"method": "tools/call", "params": {"name": "propose_strategy"}}).encode()
    assert _scope_needed(body) == {"strategy:author"}
    # durable run creation needs the run-write scope
    body = json.dumps({"method": "tools/call", "params": {"name": "run_skill"}}).encode()
    assert _scope_needed(body) == {"runs:write"}
    # Execution tools are not registered on the public MCP server.
    body = json.dumps({"method": "tools/call", "params": {"name": "create_order_intent"}}).encode()
    assert _scope_needed(body) == set()
    body = json.dumps({"method": "tools/call", "params": {"name": "preview_order_intent"}}).encode()
    assert _scope_needed(body) == set()
    body = json.dumps({"method": "tools/call", "params": {"name": "submit_order_intent"}}).encode()
    assert _scope_needed(body) == set()
    # batches need the union of every tool-specific scope
    body = json.dumps([
        {"method": "tools/call", "params": {"name": "run_skill"}},
        {"method": "tools/call", "params": {"name": "decide_approval"}},
        {"method": "tools/call", "params": {"name": "submit_order_intent"}},
    ]).encode()
    assert _scope_needed(body) == {"runs:write", "approvals:decide"}
    # a handshake/discovery message: not a tool call, no scope gate
    body = json.dumps({"method": "tools/list"}).encode()
    assert _is_tool_call(body) is False
    assert _scope_needed(body) == set()
    assert _requires_data_read(body) is False
    # Resource reads/listing expose control-plane state and require the same data:read
    # baseline enforced by the hosted middleware.
    body = json.dumps({
        "method": "resources/read",
        "params": {"uri": "ithaca://skills/catalog"},
    }).encode()
    assert _scope_needed(body) == set()
    assert _requires_data_read(body) is True
    body = json.dumps({
        "method": "resources/read",
        "params": {"uri": "ithaca://alerts/open"},
    }).encode()
    assert _scope_needed(body) == {"alerts:read"}
    body = json.dumps({"method": "resources/list"}).encode()
    assert _requires_data_read(body) is True
    # garbage body: never raises, gates nothing extra
    assert _scope_needed(b"not json") is None
    assert _requires_data_read(b"not json") is False


# --------------------------------------------------------------------------------------
# auth layer: drive the middleware directly (ASGI, no real port)
# --------------------------------------------------------------------------------------
def _run_mw(verifier, *, token: str | None, body: dict) -> dict:
    """Drive one HTTP request through the ASGI middleware; capture the outcome.

    Returns ``{"status", "principal", "passed"}`` — ``passed`` is True iff the request was
    forwarded to the inner app (i.e. auth+scope allowed it), and ``principal`` is what the
    inner app saw via the ContextVar (proving per-request tenant injection).
    """
    import anyio

    payload = json.dumps(body).encode()
    seen: dict = {"status": None, "principal": None, "passed": False}

    async def inner_app(scope, receive, send):
        # Only reached if auth+scope passed. Record what it sees + drain the replayed body.
        seen["passed"] = True
        seen["principal"] = current_principal()
        await receive()  # the buffered body must replay without hanging
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = TenantAuthMiddleware(inner_app, verifier)

    async def send(message):
        if message["type"] == "http.response.start":
            seen["status"] = message["status"]

    received = {"done": False}

    async def receive():
        if not received["done"]:
            received["done"] = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": headers}

    anyio.run(mw, scope, receive, send)
    return seen


@pytest.fixture
def middleware(platform):
    """The verifier (platform AuthStore) the middleware tests drive."""
    return platform.auth


CALL = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "market_get_ohlcv", "arguments": {"symbol": "AAA"}}}
PROPOSE = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": "propose_strategy", "arguments": {"spec": {}}}}


def test_valid_key_resolves_principal_and_passes(middleware, keys, tenant):
    out = _run_mw(middleware, token=keys["full"], body=CALL)
    assert out["passed"] is True
    p = out["principal"]
    assert isinstance(p, Principal)
    assert p.tenant_id == tenant
    assert p.has("data:read") and p.has("strategy:author")
    # the principal's _ctx tenant-scopes the trace
    assert p.ctx()["tenant_id"] == tenant


def test_missing_key_is_401(middleware):
    out = _run_mw(middleware, token=None, body=CALL)
    assert out["status"] == 401 and out["passed"] is False


def test_bad_key_is_401(middleware):
    out = _run_mw(middleware, token="ith_test_deadbeef_notarealsecret", body=CALL)
    assert out["status"] == 401 and out["passed"] is False


def test_revoked_key_is_401(middleware, keys):
    out = _run_mw(middleware, token=keys["revoked"], body=CALL)
    assert out["status"] == 401 and out["passed"] is False


def test_tool_call_requires_data_read_scope(middleware, keys):
    # a key with NO scopes cannot make a tools/call (needs data:read) -> 403
    out = _run_mw(middleware, token=keys["no_scope"], body=CALL)
    assert out["status"] == 403 and out["passed"] is False


def test_resource_read_requires_data_read_scope(middleware, keys):
    body = {"jsonrpc": "2.0", "id": 1, "method": "resources/read",
            "params": {"uri": "ithaca://skills/catalog"}}

    denied = _run_mw(middleware, token=keys["no_scope"], body=body)
    allowed = _run_mw(middleware, token=keys["read_only"], body=body)

    assert denied["status"] == 403 and denied["passed"] is False
    assert allowed["passed"] is True and allowed["principal"].has("data:read")


def test_alert_resource_requires_alert_read_scope(middleware, keys):
    body = {"jsonrpc": "2.0", "id": 1, "method": "resources/read",
            "params": {"uri": "ithaca://alerts/open"}}

    denied = _run_mw(middleware, token=keys["read_only"], body=body)
    allowed = _run_mw(middleware, token=keys["alert_read"], body=body)

    assert denied["status"] == 403 and denied["passed"] is False
    assert allowed["passed"] is True and allowed["principal"].has("alerts:read")


def test_propose_requires_strategy_author_scope(middleware, keys):
    # read-only key can read but cannot propose -> 403
    out = _run_mw(middleware, token=keys["read_only"], body=PROPOSE)
    assert out["status"] == 403 and out["passed"] is False


def test_batch_requires_all_tool_specific_scopes(middleware, keys):
    body = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "run_skill", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "decide_approval", "arguments": {}}},
    ]

    out = _run_mw(middleware, token=keys["run_only"], body=body)

    assert out["status"] == 403 and out["passed"] is False


def test_read_only_key_can_make_data_call(middleware, keys):
    out = _run_mw(middleware, token=keys["read_only"], body=CALL)
    assert out["passed"] is True and out["principal"].has("data:read")


def test_full_key_can_propose(middleware, keys):
    out = _run_mw(middleware, token=keys["full"], body=PROPOSE)
    assert out["passed"] is True


def test_handshake_needs_only_a_valid_key(middleware, keys):
    # tools/list is discovery, not a tool call: a no-scope-but-valid key passes (no 403).
    out = _run_mw(middleware, token=keys["no_scope"], body={"jsonrpc": "2.0", "id": 1,
                                                            "method": "tools/list"})
    assert out["passed"] is True


# --------------------------------------------------------------------------------------
# HTTP-mode smoke: the real SDK streamable-HTTP app via TestClient (no live port)
# --------------------------------------------------------------------------------------
@pytest.fixture
def http_app(platform):
    ts = Toolset(core=_det_core(), sink=InMemoryTrace(), runs=platform.runs)
    app, _mcp, _ts = build_http_app(toolset=ts, verifier=platform.auth)
    return app, ts


def _post(client, method, params, key=None, sid=None, mid=1):
    h = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
    if key:
        h["authorization"] = f"Bearer {key}"
    if sid:
        h["mcp-session-id"] = sid
    body = {"jsonrpc": "2.0", "id": mid, "method": method, "params": params}
    return client.post("/mcp", headers=h, json=body)


def test_http_unauthenticated_tool_call_is_401(http_app):
    app, _ts = http_app
    with TestClient(app) as client:
        r = _post(client, "tools/call", {"name": "market_get_ohlcv", "arguments": {"symbol": "AAA"}})
        assert r.status_code == 401


def test_http_low_scope_propose_is_403(http_app, keys):
    app, _ts = http_app
    with TestClient(app) as client:
        r = _post(client, "tools/call",
                  {"name": "propose_strategy", "arguments": {"spec": {}}}, key=keys["read_only"])
        assert r.status_code == 403


def test_http_authenticated_direct_tool_requires_and_uses_session(http_app, keys, tenant):
    app, ts = http_app
    with TestClient(app) as client:
        init = _post(client, "initialize",
                     {"protocolVersion": "2025-06-18", "capabilities": {},
                      "clientInfo": {"name": "t", "version": "1"}}, key=keys["full"])
        assert init.status_code == 200
        sid = init.headers.get("mcp-session-id")
        assert sid
        # complete the handshake
        client.post("/mcp",
                    headers={"accept": "application/json, text/event-stream",
                             "content-type": "application/json",
                             "authorization": f"Bearer {keys['full']}",
                             "mcp-session-id": sid},
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        r = _post(client, "tools/call",
                  {"name": "market_get_ohlcv", "arguments": {"symbol": "AAA", "range": "6mo"}},
                  key=keys["full"], sid=sid, mid=2)
        assert r.status_code == 200
        assert "SESSION_CONTEXT_REQUIRED" in r.text
        start = _post(client, "tools/call",
                      {"name": "start_research_session",
                       "arguments": {"prompt": "what does AAA look like", "title": "AAA"}},
                      key=keys["full"], sid=sid, mid=3)
        assert start.status_code == 200
        r = _post(client, "tools/call",
                  {"name": "market_get_ohlcv", "arguments": {"symbol": "AAA", "range": "6mo"}},
                  key=keys["full"], sid=sid, mid=4)
        assert r.status_code == 200
        assert "SESSION_CONTEXT_REQUIRED" not in r.text
    # the verified tenant (not the stdio default-tenant zeros) owns the trace
    tenants = {e.get("tenant_id") for e in ts.sink.events()}
    assert tenants == {tenant}
    types = [e["type"] for e in ts.sink.events()]
    assert types[0] == "session_open"
    assert types.count("tool_call") == 1
    assert types.count("tool_result") == 1
