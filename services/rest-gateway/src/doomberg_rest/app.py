"""FastAPI app — the web UI's ONLY backend (the browser never speaks MCP).

Reads (tenant-scoped, observability):
  - ``POST /api/sessions``             open a research session with captured prompt metadata.
  - ``GET  /api/runs``                 list runs for the tenant (optional ?kind=).
  - ``GET  /api/runs/{id}``            one run + its shaped trace (run + three lanes + events).
  - ``GET  /api/runs/{id}/book``       the live paper book (positions) for a deployment.
  - ``GET  /api/strategies``           list the tenant's strategies (latest version each).
  - ``GET  /api/runs/{id}/events``     SSE: replay-from-seq (Last-Event-ID) then live tail.

Human money-path actions (the UI's buttons). These are NOT a second money path: they call the
SAME ``doomberg_control.actions`` functions the control plane exposes, over the same stores, so
there is one implementation of every write no matter which surface a human used:
  - ``POST /api/strategies``                  propose a spec.
  - ``POST /api/runs``                         create a run (queued).
  - ``POST /api/runs/{id}/{cancel|promote|activate|pause|resume|retire}`` run lifecycle.

Tenant isolation: ``X-Tenant-Id`` (header) or ``?tenant_id=`` (EventSource can't set headers)
is required and threaded into every store call as the first arg. No unscoped read path exists.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json as _json
import os
import secrets
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from doomberg_control import actions
from doomberg_control.actions import ActionError
from doomberg_control.deps import HUMAN_ACTOR_KINDS, Ctx
from doomberg_control.execution_gateway import ExecutionGateway
from doomberg_core import Core
from doomberg_core.providers import IbkrEngineClient
from doomberg_platform import (
    AuthStore,
    ApprovalStore,
    ArtifactStore,
    BookStore,
    ExecutionStore,
    JobStore,
    LeaseStore,
    ProviderStore,
    RunStore,
    SessionError,
    StrategyStore,
    TraceStore,
    TriggerStore,
    UserStore,
    open_db,
)

from .readmodel import shape_run, shape_run_row
from .sse import event_stream, parse_last_event_id


class Stores:
    """The platform store quartet + a core, all sharing one db handle.

    This object IS a valid ``platform`` for ``doomberg_control.actions`` (it exposes
    ``runs``/``strategies``/``trace``/``books``), so the UI's write routes reuse the control
    plane's single money-path implementation in-process.
    """

    def __init__(self, db: Any) -> None:
        self.db = db
        self.runs = RunStore(db)
        self.strategies = StrategyStore(db)
        self.trace = TraceStore(db)
        self.books = BookStore(db)
        self.auth = AuthStore(db)
        self.users = UserStore(db)
        self.jobs = JobStore(db)
        self.leases = LeaseStore(db)
        self.artifacts = ArtifactStore(db)
        self.approvals = ApprovalStore(db)
        self.providers = ProviderStore(db)
        self.execution = ExecutionStore(db)
        self.triggers = TriggerStore(db)
        self.core = Core()


class ProposeBody(BaseModel):
    spec: dict[str, Any]


class CreateRunBody(BaseModel):
    strategy_id: str
    kind: str = "backtest"
    range: str = "1y"
    idempotency_key: str | None = None


class CancelRunBody(BaseModel):
    reason: str | None = None


class DecideApprovalBody(BaseModel):
    decision: str
    reason: str | None = None


class CreateTriggerBody(BaseModel):
    name: str
    policy: dict[str, Any]
    state: str = "draft"


class DryRunTriggerBody(BaseModel):
    name: str = "dry-run"
    policy: dict[str, Any]
    quote: dict[str, Any] | None = None


class SetTriggerStateBody(BaseModel):
    state: str


class CreateProviderConnectionBody(BaseModel):
    provider: str
    capabilities: list[str] = []
    entitlements: list[dict[str, Any]] = []
    state: str = "connected"
    connection_id: str | None = None
    account_ref: str | None = None
    credential_ref: str | None = None
    retention_policy: str | None = None


class CreateOrderIntentBody(BaseModel):
    run_id: str
    payload: dict[str, Any]
    strategy_id: str | None = None
    account_ref: str | None = None
    idempotency_key: str | None = None


class CreateSessionBody(BaseModel):
    prompt: str = ""
    title: str | None = None


class GoogleExchangeBody(BaseModel):
    code: str
    redirect_uri: str


class GitHubExchangeBody(BaseModel):
    code: str
    redirect_uri: str


class SignupBody(BaseModel):
    email: str
    name: str
    password: str


class SigninBody(BaseModel):
    email: str
    password: str


class MintKeyBody(BaseModel):
    # Optional scope selection; defaults to the full issuable agent set (deploy:live is
    # unissuable by the AuthStore). The UI lets the user narrow it.
    scopes: list[str] | None = None


class MintSseTicketBody(BaseModel):
    after_seq: int | None = None


def _bearer_key(authorization: str | None) -> str | None:
    """Extract the ``dmbg_...`` token from an ``Authorization: Bearer <key>`` header."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


def _verify_bearer(request: Request, authorization: str | None) -> dict[str, Any] | None:
    """Verify a bearer token — either a session JWT (human) or a dmbg_ API key (agent).

    Returns a principal dict with at least ``tenant_id``, or ``None`` if no bearer
    token was presented (dev / X-Tenant-Id path). Raises 401 on invalid tokens.
    """
    key = _bearer_key(authorization)
    if key is None:
        return None
    stores = request.app.state.stores
    # Session JWT (human users via email+password / OAuth).
    try:
        user = stores.users.verify_session(key)
        return {
            "tenant_id": user["tenant_id"],
            "key_id": user["id"],
            "scopes": [
                "data:read",
                "strategy:author",
                "runs:write",
                "runs:cancel",
                "approvals:read",
                "approvals:decide",
                "providers:write",
                "triggers:write",
                "artifacts:read",
                "deploy:backtest",
                "deploy:paper",
            ],
            "actor_kind": "user",
        }
    except SessionError:
        pass
    # API key (BYO agents).
    principal = stores.auth.verify(key)
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or revoked token")
    return {**principal, "actor_kind": "agent"}


def _validate_tenant_id(value: str) -> str:
    try:
        uuid.UUID(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="tenant_id must be a UUID") from exc
    return str(value)


def _allow_dev_tenant_header() -> bool:
    override = os.environ.get("DOOMBERG_ALLOW_DEV_TENANT_HEADER")
    if override is not None:
        return override.strip().lower() in {"1", "true", "yes", "on"}
    env = (os.environ.get("DOOMBERG_ENV") or "").strip().lower()
    return env in {"", "test", "local"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _configured_host(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc or "configured"


def _has_capability(connection: dict[str, Any], names: set[str]) -> bool:
    caps = {str(cap).strip().lower() for cap in connection.get("capabilities") or []}
    return bool(caps.intersection(names))


def _public_provider_connection(connection: dict[str, Any]) -> dict[str, Any]:
    """Return a REST-safe provider connection view without credential references."""
    return {
        "tenant_id": connection.get("tenant_id"),
        "connection_id": connection.get("connection_id"),
        "provider": connection.get("provider"),
        "account_ref": connection.get("account_ref"),
        "state": connection.get("state"),
        "capabilities": connection.get("capabilities") or [],
        "entitlements": connection.get("entitlements") or [],
        "retention_policy": connection.get("retention_policy"),
        "credential_configured": bool(connection.get("credential_ref")),
        "created_at": connection.get("created_at"),
        "updated_at": connection.get("updated_at"),
    }


def _sse_ticket_ttl_seconds() -> int:
    raw = os.environ.get("DOOMBERG_SSE_TICKET_TTL_SECONDS", "60")
    try:
        return max(5, min(300, int(raw)))
    except ValueError:
        return 60


def _hash_sse_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _mint_sse_ticket(stores: Stores, ctx: Ctx, run_id: str) -> dict[str, Any]:
    run = stores.runs.get(ctx.tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=_sse_ticket_ttl_seconds())
    ticket_id = uuid.uuid4().hex
    secret = secrets.token_urlsafe(32)
    token = f"{ticket_id}.{secret}"
    with stores.db.write_lock:
        with stores.db.conn as conn:
            conn.execute(
                "DELETE FROM sse_tickets WHERE expires_at < ? OR used_at IS NOT NULL",
                (now.isoformat(),),
            )
            conn.execute(
                "INSERT INTO sse_tickets "
                "(ticket_id, tenant_id, run_id, principal_id, secret_hash, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    ticket_id,
                    ctx.tenant_id,
                    run_id,
                    str(ctx.actor_id),
                    _hash_sse_secret(secret),
                    now.isoformat(),
                    expires.isoformat(),
                ),
            )
    return {
        "sse_ticket": token,
        "run_id": run_id,
        "tenant_id": ctx.tenant_id,
        "expires_at": expires.isoformat(),
        "single_use": True,
    }


def _redeem_sse_ticket(stores: Stores, ticket: str, run_id: str) -> str:
    try:
        ticket_id, secret = ticket.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid sse ticket") from exc
    if not ticket_id or not secret:
        raise HTTPException(status_code=401, detail="invalid sse ticket")

    now = datetime.now(timezone.utc)
    with stores.db.write_lock:
        with stores.db.conn as conn:
            row = conn.execute(
                "SELECT * FROM sse_tickets WHERE ticket_id = ? AND used_at IS NULL",
                (ticket_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=401, detail="invalid or already-used sse ticket")
            if row["run_id"] != str(run_id):
                raise HTTPException(status_code=401, detail="sse ticket is not valid for this run")
            expires_at = datetime.fromisoformat(row["expires_at"])
            if expires_at < now:
                raise HTTPException(status_code=401, detail="sse ticket expired")
            if not hmac.compare_digest(row["secret_hash"], _hash_sse_secret(secret)):
                raise HTTPException(status_code=401, detail="invalid sse ticket")
            cur = conn.execute(
                "UPDATE sse_tickets SET used_at = ? WHERE ticket_id = ? AND used_at IS NULL",
                (now.isoformat(), ticket_id),
            )
            if cur.rowcount != 1:
                raise HTTPException(status_code=401, detail="invalid or already-used sse ticket")
            return str(row["tenant_id"])


def _ops_status(stores: Stores, tenant_id: str) -> dict[str, Any]:
    connections = stores.providers.list_connections(tenant_id)
    snapshots = stores.providers.list_snapshots(tenant_id, limit=25)
    jobs = stores.jobs.list(tenant_id, limit=500)
    triggers = stores.triggers.list(tenant_id, limit=500)
    leases = stores.leases.list()

    connected = [c for c in connections if c.get("state") == "connected"]
    ibkr_names = {"ibkr", "ibkr-engine", "interactive_brokers", "interactive-brokers"}
    ibkr_connections = [
        c for c in connected
        if str(c.get("provider") or "").strip().lower() in ibkr_names
    ]
    quote_caps = {"quote", "quotes", "market_data", "market-data", "data"}
    execution_caps = {"orders", "trading", "execution"}
    ibkr_quote_provider = any(_has_capability(c, quote_caps) for c in ibkr_connections)
    ibkr_execution_provider = any(_has_capability(c, execution_caps) for c in ibkr_connections)
    entitlement_records = sum(len(c.get("entitlements") or []) for c in connections)

    ibkr_url = os.environ.get("DOOMBERG_IBKR_ENGINE_URL")
    ibkr_host = _configured_host(ibkr_url)
    live_execution = _env_flag("DOOMBERG_ENABLE_LIVE_EXECUTION")
    queued_jobs = sum(1 for job in jobs if job.get("state") == "queued")
    active_jobs = sum(1 for job in jobs if job.get("state") in {"leased", "running"})
    failed_jobs = sum(1 for job in jobs if job.get("state") in {"failed", "timed_out", "cancelled"})
    active_triggers = sum(1 for trigger in triggers if trigger.get("state") == "active")

    readiness = [
        {
            "name": "Platform store",
            "state": "succeeded" if getattr(stores.db, "is_postgres", False) else "paused",
            "detail": "Postgres system-of-record"
            if getattr(stores.db, "is_postgres", False)
            else "Local SQLite system-of-record",
        },
        {
            "name": "Archive DSN",
            "state": "succeeded" if os.environ.get("DOOMBERG_ARCHIVE_URL") else "warn",
            "detail": "Archive reads configured"
            if os.environ.get("DOOMBERG_ARCHIVE_URL")
            else "DOOMBERG_ARCHIVE_URL is unset",
        },
        {
            "name": "IBKR engine",
            "state": "succeeded" if ibkr_host else "warn",
            "detail": f"Configured for {ibkr_host}" if ibkr_host else "DOOMBERG_IBKR_ENGINE_URL is unset",
        },
        {
            "name": "IBKR provider record",
            "state": "succeeded" if ibkr_quote_provider else "warn",
            "detail": "Connected quote capability registered"
            if ibkr_quote_provider
            else "Register a connected provider with quote capability",
        },
        {
            "name": "Live execution",
            "state": "succeeded" if live_execution and ibkr_execution_provider and ibkr_host else "paused",
            "detail": "Live IBKR submission enabled and provider-gated"
            if live_execution and ibkr_execution_provider and ibkr_host
            else "Paper execution only",
        },
        {
            "name": "Worker backlog",
            "state": "warn" if queued_jobs and active_jobs == 0 else "succeeded",
            "detail": f"{queued_jobs} queued, {active_jobs} leased/running, {failed_jobs} terminal",
        },
        {
            "name": "Worker leadership",
            "state": "succeeded" if leases else "paused",
            "detail": f"{len(leases)} active lease row{'' if len(leases) == 1 else 's'}",
        },
    ]

    return {
        "platform": {
            "database": "postgres" if getattr(stores.db, "is_postgres", False) else "sqlite",
            "archive_configured": bool(os.environ.get("DOOMBERG_ARCHIVE_URL")),
            "mcp_allowed_hosts": os.environ.get("DOOMBERG_MCP_ALLOWED_HOSTS") or "",
        },
        "ibkr": {
            "engine_configured": bool(ibkr_host),
            "engine_host": ibkr_host,
            "quote_path": os.environ.get("DOOMBERG_IBKR_QUOTE_PATH") or "/quote?symbol={symbol}",
            "order_path": os.environ.get("DOOMBERG_IBKR_ORDER_PATH") or "/orders",
            "connected_quote_provider": ibkr_quote_provider,
            "connected_execution_provider": ibkr_execution_provider,
        },
        "execution": {
            "paper_enabled": True,
            "live_enabled": live_execution,
            "max_notional_usd": os.environ.get("DOOMBERG_EXECUTION_MAX_NOTIONAL_USD") or "10000",
            "max_quantity": os.environ.get("DOOMBERG_EXECUTION_MAX_QUANTITY") or "10000",
            "max_freshness_ms": os.environ.get("DOOMBERG_EXECUTION_MAX_FRESHNESS_MS") or "10000",
        },
        "providers": {
            "connections": len(connections),
            "connected": len(connected),
            "entitlement_records": entitlement_records,
            "dataset_snapshots": len(snapshots),
        },
        "jobs": {
            "queued": queued_jobs,
            "leased_or_running": active_jobs,
            "terminal": failed_jobs,
        },
        "leases": leases,
        "triggers": {
            "active": active_triggers,
            "total": len(triggers),
        },
        "readiness": readiness,
    }


def require_tenant(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    tenant_id: str | None = Query(default=None),
) -> str:
    """Tenant from a bearer key (prod) or the ``X-Tenant-Id`` header / ``?tenant_id=`` query.

    A bearer key's tenant takes precedence and is authoritative. Otherwise local/test can use
    the dev header or EventSource query param. Deployed envs require auth unless explicitly
    opted in with ``DOOMBERG_ALLOW_DEV_TENANT_HEADER=1``.

    EventSource cannot send custom headers; the live stream uses short-lived SSE tickets
    minted by an authenticated REST request instead of putting account credentials in URLs.
    """
    principal = _verify_bearer(request, authorization)
    if principal is not None:
        return principal["tenant_id"]
    if not _allow_dev_tenant_header():
        raise HTTPException(status_code=401, detail="authentication required")
    resolved = x_tenant_id or tenant_id
    if not resolved:
        raise HTTPException(status_code=400, detail="X-Tenant-Id header (or ?tenant_id=) is required")
    return _validate_tenant_id(resolved)


def _ctx(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    tenant_id: str | None = Query(default=None),
    x_actor_kind: str | None = Header(default=None, alias="X-Actor-Kind"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
) -> Ctx:
    """Resolve the write-action context.

    - **Bearer key (a BYO agent):** an *agent* actor carrying exactly the key's scopes — it
      may author/request but the human-actor rule still blocks self-promotion.
    - **Local dev/test (no bearer key):** a *user* actor (the human at the keyboard) with the
      full dev scope set, so local UI buttons behave as before.
    """
    principal = _verify_bearer(request, authorization)
    if principal is not None:
        return Ctx(
            tenant_id=principal["tenant_id"],
            actor_kind=(principal.get("actor_kind") or "agent").strip().lower(),
            actor_id=principal["key_id"],
            scopes=frozenset(principal["scopes"]),
        )
    if not _allow_dev_tenant_header():
        raise HTTPException(status_code=401, detail="authentication required")
    resolved = x_tenant_id or tenant_id
    if not resolved:
        raise HTTPException(status_code=400, detail="X-Tenant-Id header (or ?tenant_id=) is required")
    resolved = _validate_tenant_id(resolved)
    return Ctx(
        tenant_id=resolved,
        actor_kind=(x_actor_kind or "user").strip().lower(),
        actor_id=(x_actor_id or "ui").strip() or "ui",
    )


def _do(fn, *args) -> dict[str, Any]:
    try:
        return fn(*args)
    except ActionError as err:
        raise HTTPException(status_code=err.status, detail=err.detail) from err


def _require_scope(ctx: Ctx, scope: str) -> None:
    if not ctx.has_scope(scope):
        raise HTTPException(status_code=403, detail=f"missing required scope: {scope}")


def _session_summary(row: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Add prompt/tool-count metadata to a research run row for the Sessions list."""
    prompt = None
    title = None
    agent = None
    last_event_at = None
    call_count = 0
    warning_count = 0
    for ev in events:
        last_event_at = ev.get("ts") or last_event_at
        actor = ev.get("actor") or {}
        if actor.get("id") and agent is None:
            agent = actor.get("id")
        data = ev.get("data") or {}
        if prompt is None and isinstance(data, dict):
            prompt = data.get("prompt") or data.get("userPrompt")
            title = data.get("title") or title
        if ev.get("type") == "tool_call":
            call_count += 1
        warnings = data.get("warnings") if isinstance(data, dict) else None
        if isinstance(warnings, list):
            warning_count += len(warnings)
    return {
        **shape_run_row(row),
        "prompt": prompt,
        "title": title or (prompt[:80] if isinstance(prompt, str) else None),
        "agent": agent,
        "last_event_at": last_event_at,
        "call_count": call_count,
        "warning_count": warning_count,
    }


def _web_dist_dir() -> Path | None:
    """Locate the built web app (``web/dist``), or ``None`` if it has not been built.

    Override with ``DOOMBERG_WEB_DIST`` (an absolute path) in prod images; otherwise we fall
    back to the repo-relative ``web/dist``. Returning ``None`` keeps tests/dev (no build)
    working — the static mount is simply skipped.
    """
    override = os.environ.get("DOOMBERG_WEB_DIST")
    if override:
        p = Path(override)
        return p if p.is_dir() else None
    # services/rest-gateway/src/doomberg_rest/app.py -> repo root is 4 parents up.
    candidate = Path(__file__).resolve().parents[4] / "web" / "dist"
    return candidate if candidate.is_dir() else None


def create_app(db: Any | None = None) -> FastAPI:
    if db is None:
        db = open_db(os.environ.get("DOOMBERG_DB", ":memory:"))
    stores = Stores(db)

    app = FastAPI(title="doomberg-rest-gateway", version="0.0.0")
    app.state.stores = stores

    # Permissive CORS for local dev only. PIN allowed origins in prod.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Last-Event-ID"],
    )

    def get_stores(request: Request) -> Stores:
        return request.app.state.stores

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # ---- OAuth helpers -----------------------------------------------------------------

    def _http_post_form(url: str, params: dict[str, str],
                        headers: dict[str, str] | None = None) -> dict[str, Any]:
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return _json.loads(resp.read())

    def _http_post_json(url: str, payload: dict[str, str],
                        headers: dict[str, str] | None = None) -> dict[str, Any]:
        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return _json.loads(resp.read())

    def _http_get(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        req = urllib.request.Request(url, method="GET")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return _json.loads(resp.read())

    def _decode_jwt_payload(id_token: str) -> dict[str, Any]:
        """Decode the middle (payload) segment of a JWT without verifying the signature."""
        parts = id_token.split(".")
        if len(parts) < 2:
            raise ValueError("malformed id_token")
        # Add padding to make it valid base64
        segment = parts[1] + "=="
        return _json.loads(base64.b64decode(segment).decode("utf-8"))

    def _oauth_signin(
        provider: str,
        provider_id: str,
        email: str,
        name: str,
        avatar_url: str | None,
    ) -> dict[str, Any]:
        """Upsert user via OAuth, create session JWT, return {user, token}."""
        # Ensure a tenant exists for this user (create one if brand-new).
        existing_user = None
        existing_link = stores.db.conn.execute(
            "SELECT user_id FROM oauth_accounts WHERE provider=? AND provider_id=?",
            (provider, provider_id),
        ).fetchone()
        if existing_link:
            existing_user = stores.users.get_by_id(existing_link["user_id"])

        if existing_user:
            tenant_id = existing_user["tenant_id"]
        else:
            # Check if the email already has a tenant (existing email+pw user).
            existing_by_email = stores.db.conn.execute(
                "SELECT id, tenant_id FROM users WHERE email=?",
                (email.strip().lower(),),
            ).fetchone()
            tenant_id = (
                existing_by_email["tenant_id"]
                if existing_by_email
                else stores.auth.create_tenant(name or email)
            )

        user = stores.users.oauth_upsert(provider, provider_id, email, name, avatar_url, tenant_id)
        token = stores.users.create_session(user["id"])
        return {
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "avatarUrl": user.get("avatar_url"),
                "provider": provider,
                "tenantId": tenant_id,
            },
            "token": token,
        }

    # ---- auth: Google exchange ---------------------------------------------------------

    @app.post("/api/auth/google/exchange")
    def google_exchange(body: GoogleExchangeBody) -> dict[str, Any]:
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise HTTPException(status_code=503, detail="provider not configured")
        try:
            token_resp = _http_post_form(
                "https://oauth2.googleapis.com/token",
                {
                    "code": body.code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": body.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if "error" in token_resp:
            raise HTTPException(status_code=400, detail=token_resp.get("error_description", token_resp["error"]))
        id_token = token_resp.get("id_token", "")
        if not id_token:
            raise HTTPException(status_code=400, detail="no id_token in Google response")
        try:
            claims = _decode_jwt_payload(id_token)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"could not decode id_token: {exc}") from exc
        provider_id = claims.get("sub", "")
        email = claims.get("email", "")
        name = claims.get("name", email)
        avatar_url = claims.get("picture")
        if not provider_id:
            raise HTTPException(status_code=400, detail="missing sub in Google id_token")
        try:
            return _oauth_signin("google", provider_id, email, name, avatar_url)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ---- auth: GitHub exchange ---------------------------------------------------------

    @app.post("/api/auth/github/exchange")
    def github_exchange(body: GitHubExchangeBody) -> dict[str, Any]:
        client_id = os.environ.get("GITHUB_CLIENT_ID", "")
        client_secret = os.environ.get("GITHUB_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise HTTPException(status_code=503, detail="provider not configured")
        # Step 1: exchange code for access_token
        try:
            token_resp = _http_post_json(
                "https://github.com/login/oauth/access_token",
                {
                    "code": body.code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": body.redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if "error" in token_resp:
            raise HTTPException(status_code=400, detail=token_resp.get("error_description", token_resp["error"]))
        access_token = token_resp.get("access_token", "")
        if not access_token:
            raise HTTPException(status_code=400, detail="no access_token in GitHub response")
        # Step 2: fetch user profile
        try:
            user_resp = _http_get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "User-Agent": "doomberg-rest-gateway",
                },
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        provider_id = str(user_resp.get("id", ""))
        name = user_resp.get("name") or user_resp.get("login", "")
        email = user_resp.get("email") or ""
        avatar_url = user_resp.get("avatar_url")
        # Step 3: if email is missing, fetch from /user/emails
        if not email:
            try:
                emails_resp = _http_get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                        "User-Agent": "doomberg-rest-gateway",
                    },
                )
                for entry in emails_resp:
                    if entry.get("primary") and entry.get("verified"):
                        email = entry.get("email", "")
                        break
                if not email and emails_resp:
                    email = emails_resp[0].get("email", "")
            except Exception:
                pass  # email stays empty; not fatal
        if not provider_id:
            raise HTTPException(status_code=400, detail="missing id in GitHub user response")
        try:
            return _oauth_signin("github", provider_id, email, name, avatar_url)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ---- auth: email+password ----------------------------------------------------------

    @app.post("/api/auth/signup", status_code=201)
    def signup(body: SignupBody, stores: Stores = Depends(get_stores)) -> dict[str, Any]:
        try:
            tenant_id = stores.auth.create_tenant(body.name or body.email)
            user = stores.users.signup(body.email, body.name, body.password, tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        token = stores.users.create_session(user["id"])
        return {
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "avatarUrl": None,
                "provider": "email",
                "tenantId": user["tenant_id"],
            },
            "token": token,
        }

    @app.post("/api/auth/signin")
    def signin(body: SigninBody, stores: Stores = Depends(get_stores)) -> dict[str, Any]:
        try:
            user = stores.users.signin(body.email, body.password)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        token = stores.users.create_session(user["id"])
        return {
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "avatarUrl": user.get("avatar_url"),
                "provider": "email",
                "tenantId": user["tenant_id"],
            },
            "token": token,
        }

    @app.post("/api/auth/signout")
    def signout(
        authorization: str | None = Header(default=None, alias="Authorization"),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, str]:
        key = _bearer_key(authorization)
        if key:
            try:
                stores.users.revoke_session(key)
            except Exception:
                pass
        return {"status": "signed out"}

    @app.get("/api/auth/me")
    def me(
        authorization: str | None = Header(default=None, alias="Authorization"),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        key = _bearer_key(authorization)
        if not key:
            raise HTTPException(status_code=401, detail="not authenticated")
        # Try session JWT first, fall back to API key.
        try:
            user = stores.users.verify_session(key)
            return {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "avatarUrl": user.get("avatar_url"),
                "tenantId": user["tenant_id"],
            }
        except SessionError:
            pass
        # Try API key (BYO agents).
        principal = stores.auth.verify(key)
        if principal:
            return {
                "id": principal["tenant_id"],
                "name": "API Key",
                "email": "",
                "tenantId": principal["tenant_id"],
            }
        raise HTTPException(status_code=401, detail="invalid token")

    # ---- MCP API keys (issued to the SIGNED-IN user's tenant) --------------------------
    # The web sign-up/sign-in page is the issuance path: a logged-in human mints a bearer
    # key for their own tenant here, then hands it to their BYO agent. A bare API key
    # CANNOT mint more keys (only a session/human can) — key issuance requires sign-in.
    def _session_user(authorization: str | None, stores: "Stores") -> dict[str, Any]:
        key = _bearer_key(authorization)
        if key:
            try:
                return stores.users.verify_session(key)
            except SessionError:
                pass
        raise HTTPException(status_code=401, detail="sign in to manage API keys")

    _DEFAULT_KEY_SCOPES = [
        "data:read",
        "strategy:author",
        "runs:write",
        "runs:cancel",
        "approvals:read",
        "artifacts:read",
        "deploy:backtest",
        "deploy:paper",
    ]

    @app.post("/api/auth/keys", status_code=201)
    def mint_api_key(
        body: MintKeyBody,
        authorization: str | None = Header(default=None, alias="Authorization"),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        """Mint an MCP/agent API key for the signed-in user's tenant. Plaintext returned ONCE."""
        user = _session_user(authorization, stores)
        scopes = body.scopes if body.scopes else list(_DEFAULT_KEY_SCOPES)
        try:
            plaintext, key_id = stores.auth.mint_key(user["tenant_id"], scopes)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"api_key": plaintext, "key_id": key_id, "scopes": scopes,
                "tenant_id": user["tenant_id"]}

    @app.get("/api/auth/keys")
    def list_api_keys(
        authorization: str | None = Header(default=None, alias="Authorization"),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        """List the signed-in user's tenant's keys (metadata only — secrets are never stored)."""
        user = _session_user(authorization, stores)
        return {"keys": stores.auth.list_keys(user["tenant_id"])}

    @app.delete("/api/auth/keys/{key_id}")
    def revoke_api_key(
        key_id: str,
        authorization: str | None = Header(default=None, alias="Authorization"),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        """Revoke a key — only if it belongs to the signed-in user's tenant (no cross-tenant)."""
        user = _session_user(authorization, stores)
        owned = {k["key_id"] for k in stores.auth.list_keys(user["tenant_id"])}
        if key_id not in owned:
            raise HTTPException(status_code=404, detail="key not found")
        stores.auth.revoke_key(key_id)
        return {"key_id": key_id, "revoked": True}

    @app.post("/api/runs/{run_id}/events-ticket", status_code=201)
    def mint_run_events_ticket(
        run_id: str,
        body: MintSseTicketBody | None = None,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        """Mint a short-lived one-time ticket for EventSource.

        Browsers cannot attach ``Authorization`` to EventSource, so the UI obtains this
        ticket over normal authenticated REST and then presents only the ticket in the SSE
        URL. The long-lived session/API token never appears in query strings.
        """
        _require_scope(ctx, "data:read")
        ticket = _mint_sse_ticket(stores, ctx, run_id)
        if body and body.after_seq is not None:
            ticket["after_seq"] = int(body.after_seq)
        return ticket

    # ---- research sessions ------------------------------------------------------------
    @app.get("/api/sessions")
    def list_sessions(
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        rows = stores.runs.list(tenant_id, kind="research")
        return {
            "sessions": [
                _session_summary(row, stores.trace.events(tenant_id, row["run_id"]))
                for row in rows
            ]
        }

    @app.post("/api/sessions", status_code=201)
    def create_session(
        body: CreateSessionBody,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        tenant_id: str | None = Query(default=None),
        x_actor_kind: str | None = Header(default=None, alias="X-Actor-Kind"),
        x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        """Open a research-session run.

        The web UI may start a realtime run before the user prompt exists in this service.
        In that flow the agent later calls MCP ``session_context`` with the actual prompt,
        and the trace updates live under the same run id.
        """
        prompt = body.prompt.strip()

        principal = _verify_bearer(request, authorization)
        if principal is not None:
            resolved_tenant = principal["tenant_id"]
            actor_kind = (principal.get("actor_kind") or "user").strip().lower()
            actor_id = (principal.get("key_id") or "ui").strip() or "ui"
        else:
            resolved_tenant = x_tenant_id or tenant_id
            if not resolved_tenant:
                raise HTTPException(
                    status_code=400,
                    detail="X-Tenant-Id header (or ?tenant_id=) is required",
                )
            resolved_tenant = _validate_tenant_id(resolved_tenant)
            actor_kind = (x_actor_kind or "user").strip().lower()
            actor_id = (x_actor_id or "ui").strip() or "ui"

        if actor_kind not in {"agent", "user", "system"}:
            actor_kind = "user"

        run_id = stores.runs.create_research(resolved_tenant)
        title = (body.title or prompt[:80]).strip()
        data = {
            "createdBy": "web" if actor_kind == "user" else actor_kind,
        }
        if title:
            data["title"] = title
        if prompt:
            data["prompt"] = prompt
        stores.trace.append({
            "run_id": run_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "session_open",
            "tenant_id": resolved_tenant,
            "session_id": run_id,
            "origin_session_id": run_id,
            "actor": {"kind": actor_kind, "id": actor_id},
            "data": data,
        })
        run = stores.runs.get(resolved_tenant, run_id)
        events = stores.trace.events(resolved_tenant, run_id)
        shaped = shape_run(run, events)
        shaped["jobs"] = stores.jobs.list_by_run(resolved_tenant, run_id)
        shaped["artifacts"] = stores.artifacts.list_by_run(resolved_tenant, run_id)
        return shaped

    # ---- reads -------------------------------------------------------------------------
    @app.get("/api/runs")
    def list_runs(
        kind: str | None = None,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return {"runs": [shape_run_row(r) for r in stores.runs.list(tenant_id, kind=kind)]}

    @app.get("/api/runs/{run_id}")
    def get_run(
        run_id: str,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        run = stores.runs.get(tenant_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        events = stores.trace.events(tenant_id, run_id)
        book = stores.books.get(tenant_id, run_id) if run.get("kind") == "paper" else None
        shaped = shape_run(run, events, book=book)
        shaped["jobs"] = stores.jobs.list_by_run(tenant_id, run_id)
        shaped["artifacts"] = stores.artifacts.list_by_run(tenant_id, run_id)
        return shaped

    @app.get("/api/runs/{run_id}/book")
    def get_book(
        run_id: str,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        run = stores.runs.get(tenant_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"book": stores.books.get(tenant_id, run_id)}

    @app.get("/api/strategies")
    def list_strategies(
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return {"strategies": stores.strategies.list(tenant_id)}

    @app.get("/api/jobs")
    def list_jobs(
        run_id: str | None = None,
        state: str | None = None,
        profile: str | None = None,
        limit: int = 100,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return {
            "jobs": stores.jobs.list(
                tenant_id, run_id=run_id, state=state, profile=profile, limit=limit
            )
        }

    @app.get("/api/ops/status")
    def ops_status(
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return _ops_status(stores, tenant_id)

    @app.get("/api/ops/ibkr-smoke")
    def ibkr_smoke(
        symbol: str = "AAPL",
        max_freshness_ms: int | None = Query(default=None, ge=0),
        tenant_id: str = Depends(require_tenant),
    ) -> dict[str, Any]:
        return IbkrEngineClient().diagnose_quote(
            symbol=symbol,
            tenant_id=tenant_id,
            max_freshness_ms=max_freshness_ms,
        )

    @app.get("/api/artifacts")
    def list_artifacts(
        run_id: str | None = None,
        kind: str | None = None,
        limit: int = 100,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "artifacts:read")
        return {"artifacts": stores.artifacts.list(ctx.tenant_id, run_id=run_id, kind=kind, limit=limit)}

    @app.get("/api/artifacts/{artifact_id}")
    def get_artifact(
        artifact_id: str,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "artifacts:read")
        artifact = stores.artifacts.get(ctx.tenant_id, artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return artifact

    @app.get("/api/approvals")
    def list_approvals(
        run_id: str | None = None,
        state: str | None = None,
        limit: int = 100,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "approvals:read")
        return {"approvals": stores.approvals.list(ctx.tenant_id, run_id=run_id, state=state, limit=limit)}

    @app.post("/api/approvals/{approval_id}/decide")
    def decide_approval(
        approval_id: str,
        body: DecideApprovalBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "approvals:decide")
        if ctx.actor_kind not in HUMAN_ACTOR_KINDS:
            raise HTTPException(status_code=403, detail="decide_approval requires a human actor")
        try:
            approval = stores.approvals.decide(
                ctx.tenant_id,
                approval_id,
                decision=body.decision,
                decided_by=ctx.actor_id,
                reason=body.reason,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="approval not found or already decided") from exc
        if approval is None:
            raise HTTPException(status_code=404, detail="approval not found")
        stores.trace.append({
            "run_id": approval["run_id"],
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "approval_decided",
            "tenant_id": ctx.tenant_id,
            "actor": {"kind": ctx.actor_kind, "id": ctx.actor_id},
            "data": {
                "approval_id": approval_id,
                "decision": body.decision,
                "reason": body.reason,
            },
        })
        return approval

    @app.get("/api/providers")
    def list_providers(
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return {
            "connections": [
                _public_provider_connection(connection)
                for connection in stores.providers.list_connections(tenant_id)
            ],
            "snapshots": stores.providers.list_snapshots(tenant_id, limit=25),
        }

    @app.post("/api/providers", status_code=201)
    def upsert_provider_connection(
        body: CreateProviderConnectionBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "providers:write")
        connection = stores.providers.upsert_connection(
            ctx.tenant_id,
            provider=body.provider,
            capabilities=body.capabilities,
            entitlements=body.entitlements,
            state=body.state,
            connection_id=body.connection_id,
            account_ref=body.account_ref,
            credential_ref=body.credential_ref,
            retention_policy=body.retention_policy,
        )
        return _public_provider_connection(connection)

    @app.get("/api/dataset-snapshots")
    def list_dataset_snapshots(
        provider: str | None = None,
        dataset: str | None = None,
        limit: int = 100,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return {
            "snapshots": stores.providers.list_snapshots(
                tenant_id, provider=provider, dataset=dataset, limit=limit
            )
        }

    @app.get("/api/order-intents")
    def list_order_intents(
        run_id: str | None = None,
        state: str | None = None,
        limit: int = 100,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return {"order_intents": stores.execution.list_intents(tenant_id, run_id=run_id, state=state, limit=limit)}

    @app.post("/api/order-intents", status_code=201)
    def create_order_intent(
        body: CreateOrderIntentBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        try:
            return ExecutionGateway(stores).create_intent(
                ctx,
                run_id=body.run_id,
                payload=body.payload,
                strategy_id=body.strategy_id,
                account_ref=body.account_ref,
                idempotency_key=body.idempotency_key,
            )
        except ActionError as err:
            raise HTTPException(status_code=err.status, detail=err.detail) from err

    @app.get("/api/order-intents/{intent_id}")
    def get_order_intent(
        intent_id: str,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        record = stores.execution.get_record(tenant_id, intent_id)
        if record is None:
            raise HTTPException(status_code=404, detail="order intent not found")
        return record

    @app.post("/api/order-intents/{intent_id}/preview")
    def preview_order_intent(
        intent_id: str,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        try:
            return ExecutionGateway(stores).preview(ctx, intent_id)
        except ActionError as err:
            raise HTTPException(status_code=err.status, detail=err.detail) from err

    @app.post("/api/order-intents/{intent_id}/submit")
    def submit_order_intent(
        intent_id: str,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        try:
            return ExecutionGateway(stores).submit(ctx, intent_id)
        except ActionError as err:
            raise HTTPException(status_code=err.status, detail=err.detail) from err

    @app.get("/api/triggers")
    def list_triggers(
        state: str | None = None,
        limit: int = 100,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return {"triggers": stores.triggers.list(tenant_id, state=state, limit=limit)}

    @app.get("/api/trigger-firings")
    def list_trigger_firings(
        trigger_id: str | None = None,
        limit: int = 100,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return {
            "firings": stores.triggers.list_firings(
                tenant_id,
                trigger_id=trigger_id,
                limit=limit,
            )
        }

    @app.post("/api/triggers/dry-run")
    def dry_run_trigger(
        body: DryRunTriggerBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "triggers:write")
        from doomberg_runtime import TriggerEngine, TriggerEvaluationError

        trigger = {
            "tenant_id": ctx.tenant_id,
            "trigger_id": f"dry-run-{uuid.uuid4()}",
            "name": body.name,
            "state": "draft",
            "policy": body.policy,
        }
        try:
            return TriggerEngine(stores, worker_id="rest-trigger-dry-run").dry_run(
                trigger,
                quote=body.quote,
            )
        except TriggerEvaluationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/triggers", status_code=201)
    def create_trigger(
        body: CreateTriggerBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "triggers:write")
        try:
            return stores.triggers.create(
                ctx.tenant_id,
                name=body.name,
                policy=body.policy,
                state=body.state,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/triggers/{trigger_id}/state")
    def set_trigger_state(
        trigger_id: str,
        body: SetTriggerStateBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "triggers:write")
        try:
            return stores.triggers.set_state(ctx.tenant_id, trigger_id, body.state)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="trigger not found") from exc

    # ---- human money-path actions (shared control-plane implementation) ----------------
    @app.post("/api/strategies", status_code=201)
    def propose(
        body: ProposeBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return _do(actions.propose_strategy, stores, ctx, stores.core, body.spec)

    @app.post("/api/runs", status_code=201)
    def create_run(
        body: CreateRunBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        try:
            return actions.create_run(stores, ctx, strategy_id=body.strategy_id,
                                      kind=body.kind, range_=body.range,
                                      idempotency_key=body.idempotency_key)
        except ActionError as err:
            raise HTTPException(status_code=err.status, detail=err.detail) from err

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(
        run_id: str,
        body: CancelRunBody | None = None,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        try:
            return actions.cancel_run(stores, ctx, run_id, reason=body.reason if body else None)
        except ActionError as err:
            raise HTTPException(status_code=err.status, detail=err.detail) from err

    def _action_route(fn):
        def route(run_id: str, ctx: Ctx = Depends(_ctx),
                  stores: Stores = Depends(get_stores)) -> dict[str, Any]:
            return _do(fn, stores, ctx, run_id)
        return route

    for _name, _fn in (
        ("promote", actions.promote_run), ("activate", actions.activate_run),
        ("pause", actions.pause_run), ("resume", actions.resume_run),
        ("retire", actions.retire_run),
    ):
        app.add_api_route(f"/api/runs/{{run_id}}/{_name}", _action_route(_fn),
                          methods=["POST"], name=f"run_{_name}")

    # ---- live trace stream -------------------------------------------------------------
    @app.get("/api/runs/{run_id}/events")
    def stream_events(
        run_id: str,
        request: Request,
        stores: Stores = Depends(get_stores),
        last_event_id: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        tenant_id: str | None = Query(default=None),
        access_token: str | None = Query(default=None),
        sse_ticket: str | None = Query(default=None),
    ) -> StreamingResponse:
        if sse_ticket:
            resolved_tenant_id = _redeem_sse_ticket(stores, sse_ticket, run_id)
        elif access_token:
            raise HTTPException(
                status_code=401,
                detail="use /api/runs/{run_id}/events-ticket instead of access_token query auth",
            )
        else:
            resolved_tenant_id = require_tenant(
                request,
                authorization=authorization,
                x_tenant_id=x_tenant_id,
                tenant_id=tenant_id,
            )

        run = stores.runs.get(resolved_tenant_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")

        after_seq = parse_last_event_id(last_event_id)
        qp = request.query_params.get("after_seq")
        if qp is not None:
            after_seq = parse_last_event_id(qp)

        replay_only = request.query_params.get("replay_only") == "1"
        deadline = request.query_params.get("deadline")
        deadline_seconds = float(deadline) if deadline is not None else None

        stream = event_stream(
            stores.trace, resolved_tenant_id, run_id,
            after_seq=after_seq, deadline_seconds=deadline_seconds, replay_only=replay_only,
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ---- serve the built web UI from the SAME backend (one LB for UI + API) -------------
    # Mounted LAST, so the explicit ``/api/*`` + ``/healthz`` routes above always win; the
    # SPA mount only catches everything else. ``html=True`` serves index.html for unknown
    # client-side routes. Skipped entirely when there is no build (tests / dev), so the
    # gateway still starts without a compiled UI.
    dist = _web_dist_dir()
    if dist is not None:
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")

    return app


# Module-level app for `uvicorn doomberg_rest.app:app`.
app = create_app()
