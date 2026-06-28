"""HTTP transport + per-tenant bearer auth for the Doomberg MCP server.

STDIO (the default) is a locally-launched, locally-trusted agent: no auth, the existing
dev behavior. This module adds the **hosted** path so a REMOTE bring-your-own agent can
connect over the network, using the MCP SDK's streamable-HTTP transport
(``FastMCP.streamable_http_app()`` → a Starlette ASGI app served by uvicorn).

Auth is a thin ASGI middleware in front of that app rather than the SDK's ``TokenVerifier``
hook: the SDK hook is an OAuth *resource-server* facility — it refuses to start without full
``AuthSettings`` (issuer URLs, RFC 9728 protected-resource metadata) and changes the wire
protocol. Our credential is a single opaque per-tenant API key (``dmbg_...``) resolved by the
platform's :class:`~doomberg_platform.AuthStore`, so a middleware is both simpler and exactly
what the installed SDK (``mcp==1.27.x``) supports cleanly.

The middleware:

* requires ``Authorization: Bearer dmbg_...`` on every MCP request → **401** on
  missing/invalid/revoked key (``AuthStore.verify`` is constant-time + revocation-aware);
* requires scope ``data:read`` for any ``tools/call`` or MCP resource read/list request,
  and additionally ``strategy:author`` for the ``propose_strategy`` tool → **403** if
  missing;
* stashes the verified principal (``tenant_id`` + scopes) in a request-scoped
  :class:`contextvars.ContextVar` so the tool wrappers can pass it into the Toolset as
  ``_ctx`` — every hosted call is then tenant-scoped and traced under that tenant (the
  Toolset's ``_tracer`` keys research sessions off ``_ctx['tenant_id']``).

No new dependencies: ``mcp``, ``starlette`` and ``uvicorn`` are already in the workspace.
"""
from __future__ import annotations

import contextvars
import json
import os
from dataclasses import dataclass, field

# The per-request authenticated principal. Set by the auth middleware before the MCP
# request is dispatched to a tool; read by the tool wrappers to build ``_ctx``. A
# ContextVar (not a plain global) keeps it correct under concurrent requests — each ASGI
# task gets its own value.
_PRINCIPAL: contextvars.ContextVar["Principal | None"] = contextvars.ContextVar(
    "doomberg_mcp_principal", default=None
)

# Scope policy (kept here, next to enforcement, so it reads as one unit).
SCOPE_TOOL_CALL = "data:read"  # required for any tools/call
RESOURCE_READ_METHODS = {
    "resources/read",
    "resources/list",
    "resources/templates/list",
}
SCOPE_BY_TOOL = {
    "propose_strategy": "strategy:author",
    "run_skill": "runs:write",
    "cancel_run": "runs:cancel",
    "list_approvals": "approvals:read",
    "decide_approval": "approvals:decide",
    "get_artifact": "artifacts:read",
}  # extra scope per tool name


@dataclass(frozen=True)
class Principal:
    """The verified caller behind one HTTP MCP request."""

    tenant_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    key_id: str | None = None

    def has(self, scope: str) -> bool:
        return scope in self.scopes

    def ctx(self) -> dict:
        """The ``_ctx`` the Toolset expects (tenant-scopes the trace + research session)."""
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.key_id,
            "actor_kind": "agent",
            "scopes": set(self.scopes),
        }


def current_principal() -> Principal | None:
    """The principal for the in-flight HTTP request, or None (e.g. stdio mode)."""
    return _PRINCIPAL.get()


def _bearer(headers) -> str | None:
    """Extract the bearer token from a raw ASGI headers list (bytes pairs)."""
    for name, value in headers:
        if name.lower() == b"authorization":
            raw = value.decode("latin-1").strip()
            if raw.lower().startswith("bearer "):
                return raw[7:].strip()
            return None
    return None


def _scope_needed(body: bytes) -> set[str] | None:
    """Extra scopes a JSON-RPC body needs, or None when it cannot be inspected.

    Best-effort parse of the JSON-RPC body: tool-specific calls add all scopes required by
    every call in the body. A batch request therefore gets the union of required scopes
    instead of the first arbitrary set member. Base ``data:read`` gating for tools and
    resources is handled by :func:`_requires_data_read`.
    """
    try:
        msg = json.loads(body)
    except Exception:
        return None
    # A batch is a list; if any element is a tools/call we still gate it. Keep it simple:
    # treat a list by checking each element.
    msgs = msg if isinstance(msg, list) else [msg]
    needs: set[str] = set()
    is_tool_call = False
    for m in msgs:
        if not isinstance(m, dict) or m.get("method") != "tools/call":
            continue
        is_tool_call = True
        name = (m.get("params") or {}).get("name")
        if name in SCOPE_BY_TOOL:
            needs.add(SCOPE_BY_TOOL[name])
    if not is_tool_call:
        return set()
    return needs


def _requires_data_read(body: bytes) -> bool:
    """Whether a JSON-RPC request reads tool/resource data and needs ``data:read``."""
    try:
        msg = json.loads(body)
    except Exception:
        return False
    msgs = msg if isinstance(msg, list) else [msg]
    for m in msgs:
        if not isinstance(m, dict):
            continue
        method = m.get("method")
        if method == "tools/call" or method in RESOURCE_READ_METHODS:
            return True
    return False


def _json_error(status: int, message: str):
    """A tiny ASGI app that emits a JSON error response and ends the request."""

    async def app(scope, receive, send):
        payload = json.dumps({"error": message}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("ascii")),
                    # Advertise the scheme so a client knows to present a bearer token.
                    (b"www-authenticate", b'Bearer realm="doomberg-mcp"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})

    return app


class TenantAuthMiddleware:
    """Pure-ASGI middleware enforcing per-tenant bearer auth + scopes on the MCP app.

    Pure ASGI (not ``BaseHTTPMiddleware``) so it can short-circuit with 401/403 *before* the
    streamable-HTTP handler touches the request, and so buffering the JSON-RPC body (needed to
    read the tool name for scope enforcement) and replaying it downstream is explicit and
    correct under streaming.
    """

    def __init__(self, app, verifier) -> None:
        self.app = app
        # ``verifier`` is anything with ``verify(key) -> {tenant_id, scopes, key_id} | None``
        # (the platform AuthStore). Duck-typed so tests can pass a fake/in-memory store.
        self.verifier = verifier

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            # Lifespan / websocket: pass straight through (the SDK app's lifespan runs the
            # streamable-HTTP session manager).
            await self.app(scope, receive, send)
            return

        token = _bearer(scope.get("headers") or [])
        principal = self._resolve(token)
        if principal is None:
            await _json_error(401, "missing or invalid API key")(scope, receive, send)
            return

        # Buffer the body once so we can both inspect it (scope policy) and replay it to the
        # downstream app. MCP requests are small JSON-RPC envelopes.
        body, more = await _read_body(receive)
        extra_scopes = _scope_needed(body)
        if extra_scopes is not None:
            if _requires_data_read(body) and not principal.has(SCOPE_TOOL_CALL):
                await _json_error(403, f"missing scope: {SCOPE_TOOL_CALL}")(scope, receive, send)
                return
            for extra in sorted(extra_scopes):
                if not principal.has(extra):
                    await _json_error(403, f"missing scope: {extra}")(scope, receive, send)
                    return

        token_ctx = _PRINCIPAL.set(principal)
        try:
            await self.app(scope, _replay(body, more, receive), send)
        finally:
            _PRINCIPAL.reset(token_ctx)

    def _resolve(self, token: str | None) -> Principal | None:
        if not token:
            return None
        info = self.verifier.verify(token)
        if not info:
            return None
        return Principal(
            tenant_id=info["tenant_id"],
            scopes=frozenset(info.get("scopes") or []),
            key_id=info.get("key_id"),
        )


def _is_tool_call(body: bytes) -> bool:
    try:
        msg = json.loads(body)
    except Exception:
        return False
    msgs = msg if isinstance(msg, list) else [msg]
    return any(isinstance(m, dict) and m.get("method") == "tools/call" for m in msgs)


async def _read_body(receive) -> tuple[bytes, bool]:
    """Drain the request body from the ASGI receive channel into a single bytes buffer."""
    chunks: list[bytes] = []
    more = True
    while more:
        message = await receive()
        if message["type"] == "http.disconnect":
            return b"".join(chunks), False
        chunks.append(message.get("body", b""))
        more = message.get("more_body", False)
    return b"".join(chunks), False


def _replay(body: bytes, more: bool, original_receive):
    """A receive() that yields the buffered body once, then defers to the original channel."""
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        # After the body, anything further (disconnects) comes from the real channel.
        return await original_receive()

    return receive


def build_auth_store(db_url: str | None = None):
    """Build an :class:`~doomberg_platform.AuthStore` from ``DOOMBERG_DB`` (or ``:memory:``).

    Imported lazily so unit tests that construct their own AuthStore don't force the import,
    and a missing/unset DB falls back to ``:memory:`` (an empty store → every key 401s, which
    is the safe default for a misconfigured deploy).
    """
    from doomberg_platform import Platform

    url = db_url or os.environ.get("DOOMBERG_DB", ":memory:")
    return Platform(url).auth


def build_http_app(toolset=None, verifier=None, *, host: str | None = None,
                   port: int | None = None):
    """Build the auth-wrapped streamable-HTTP ASGI app for the Doomberg MCP server.

    ``toolset`` defaults to the platform-backed Toolset (shared trace store). ``verifier``
    defaults to an AuthStore over ``DOOMBERG_DB``. Returns ``(app, mcp, toolset)`` so callers
    (and tests) can introspect. The tool wrappers pull the per-request principal from the
    ContextVar and pass ``_ctx`` into the Toolset, so every hosted call is tenant-scoped.
    """
    from .server import create_server

    mcp, ts = create_server(toolset, http=True)
    if host is not None:
        mcp.settings.host = host
    if port is not None:
        mcp.settings.port = port

    app = mcp.streamable_http_app()  # Starlette app; carries the session-manager lifespan
    verifier = verifier or build_auth_store()
    app.add_middleware(_AsgiAdapter, inner=TenantAuthMiddleware, verifier=verifier)
    return app, mcp, ts


class _AsgiAdapter:
    """Adapt our pure-ASGI :class:`TenantAuthMiddleware` to Starlette's ``add_middleware``.

    Starlette instantiates a middleware as ``cls(app, **options)``; it then expects the
    instance to be the ASGI callable. We wrap so the options name our real middleware class
    and its verifier, keeping ``TenantAuthMiddleware`` independently testable as ``cls(app,
    verifier)``.
    """

    def __init__(self, app, inner, verifier) -> None:
        self._mw = inner(app, verifier)

    async def __call__(self, scope, receive, send):
        await self._mw(scope, receive, send)


def serve_http(toolset=None, verifier=None, host: str = "0.0.0.0",
               port: int = 8080) -> None:
    """Serve the auth-wrapped streamable-HTTP MCP app with uvicorn (blocking)."""
    import uvicorn

    app, _mcp, _ts = build_http_app(toolset, verifier, host=host, port=port)
    uvicorn.run(app, host=host, port=port, log_level="info")
