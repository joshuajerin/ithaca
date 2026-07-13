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

import hashlib
import hmac
import asyncio
import json
import os
import secrets
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from jwt import InvalidTokenError, PyJWKClient
from pydantic import BaseModel

from doomberg_control import actions
from doomberg_control.actions import ActionError
from doomberg_control.deps import HUMAN_ACTOR_KINDS, Ctx
from doomberg_control.execution_gateway import ExecutionGateway
from doomberg_core import Core
from doomberg_core.providers import PUBLIC_DATA_SOURCE, IbkrEngineClient
from doomberg_mcp import Toolset
from doomberg_platform import (
    AdaptiveDashboardProfileStore,
    ClerkApiError,
    ClerkApiUnavailable,
    AuthStore,
    ApprovalStore,
    ArtifactStore,
    BookStore,
    DeliveryTargetStore,
    ExecutionStore,
    FeedbackStore,
    JobStore,
    LeaseStore,
    NotificationStore,
    ProviderStore,
    RunStore,
    StrategyStore,
    TraceStore,
    TriggerBaselineStore,
    TriggerStore,
    UserStore,
    build_agent_key_store,
    open_db,
)
from doomberg_runtime import (
    default_adaptive_dashboard_spec,
    object_storage_configured,
    open_artifact,
    usage_signals_for_user,
)

from .dashboard_readmodels import (
    dashboard_activity,
    dashboard_market,
    dashboard_risk,
    dashboard_summary,
    provider_status,
    public_provider_connection,
)
from .dashboard_models import (
    DashboardActivityData,
    DashboardEnvelope,
    DashboardMarketData,
    DashboardRiskData,
    DashboardSummaryData,
    ProviderStatusData,
)
from .dashboard_store import DashboardReadStore
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
        self.agent_keys = build_agent_key_store(db)
        self.adaptive_dashboards = AdaptiveDashboardProfileStore(db)
        self.users = UserStore(db)
        self.jobs = JobStore(db)
        self.leases = LeaseStore(db)
        self.artifacts = ArtifactStore(db)
        self.approvals = ApprovalStore(db)
        self.providers = ProviderStore(db)
        self.execution = ExecutionStore(db)
        self.feedback = FeedbackStore(db)
        self.triggers = TriggerStore(db)
        self.baselines = TriggerBaselineStore(db)
        self.notifications = NotificationStore(db)
        self.delivery_targets = DeliveryTargetStore(db)
        self.dashboard = DashboardReadStore(db)
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


class MintKeyBody(BaseModel):
    # Optional scope selection; defaults to the full issuable agent set (deploy:live is
    # unissuable by the AuthStore). The UI lets the user narrow it.
    scopes: list[str] | None = None


class MintSseTicketBody(BaseModel):
    after_seq: int | None = None


class FeedbackBody(BaseModel):
    message: str


MAX_FEEDBACK_LENGTH = 5000


def _bearer_key(authorization: str | None) -> str | None:
    """Extract the ``dmbg_...`` token from an ``Authorization: Bearer <key>`` header."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


def _csv_env(name: str) -> list[str]:
    return [part.strip() for part in os.environ.get(name, "").split(",") if part.strip()]


def _clerk_public_key() -> str | None:
    raw = os.environ.get("CLERK_PEM_PUBLIC_KEY") or os.environ.get("CLERK_JWT_PUBLIC_KEY")
    if not raw:
        return None
    raw = raw.replace("\\n", "\n").strip()
    if "BEGIN PUBLIC KEY" in raw:
        return raw
    return f"-----BEGIN PUBLIC KEY-----\n{raw}\n-----END PUBLIC KEY-----"


def _clerk_jwks_url() -> str | None:
    explicit = os.environ.get("CLERK_JWKS_URL", "").strip()
    if explicit:
        return explicit
    frontend_api = os.environ.get("CLERK_FRONTEND_API_URL", "").strip().rstrip("/")
    if frontend_api:
        return f"{frontend_api}/.well-known/jwks.json"
    return None


def _clerk_configured() -> bool:
    return bool(_clerk_public_key() or _clerk_jwks_url())


def _strict_clerk_claim_checks_required() -> bool:
    return not _allow_dev_tenant_header()


_CLERK_JWKS_CLIENTS: dict[str, PyJWKClient] = {}


def _decode_clerk_token(token: str) -> dict[str, Any] | None:
    if not _clerk_configured():
        return None

    try:
        public_key = _clerk_public_key()
        if public_key:
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
        else:
            jwks_url = _clerk_jwks_url()
            if not jwks_url:
                return None
            client = _CLERK_JWKS_CLIENTS.setdefault(jwks_url, PyJWKClient(jwks_url))
            signing_key = client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="invalid Clerk token") from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="could not verify Clerk token") from exc

    strict_claims = _strict_clerk_claim_checks_required()
    issuer = os.environ.get("CLERK_ISSUER", "").strip()
    if strict_claims and not issuer:
        raise HTTPException(status_code=503, detail="CLERK_ISSUER is required")
    if issuer and claims.get("iss") != issuer:
        raise HTTPException(status_code=401, detail="invalid Clerk issuer")

    allowed_origins = set(_csv_env("CLERK_ALLOWED_ORIGINS"))
    if strict_claims and not allowed_origins:
        raise HTTPException(status_code=503, detail="CLERK_ALLOWED_ORIGINS is required")
    azp = claims.get("azp")
    if allowed_origins and azp not in allowed_origins:
        raise HTTPException(status_code=401, detail="invalid Clerk authorized party")

    if claims.get("sts") == "pending":
        raise HTTPException(status_code=401, detail="Clerk session is pending")

    if not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Clerk token missing subject")

    return claims


def _upsert_clerk_user(stores: "Stores", claims: dict[str, Any]) -> dict[str, Any]:
    sub = str(claims["sub"])
    email = (
        claims.get("email")
        or claims.get("email_address")
        or claims.get("primary_email_address")
        or f"{sub}@clerk.doomberg.local"
    )
    email = str(email).strip().lower()
    name = (
        claims.get("name")
        or claims.get("full_name")
        or claims.get("username")
        or claims.get("first_name")
        or email
    )
    avatar_url = claims.get("picture") or claims.get("image_url")

    existing_link = stores.db.conn.execute(
        "SELECT user_id FROM oauth_accounts WHERE provider=? AND provider_id=?",
        ("clerk", sub),
    ).fetchone()
    if existing_link:
        existing_user = stores.users.get_by_id(existing_link["user_id"])
        tenant_id = (
            existing_user["tenant_id"] if existing_user else stores.auth.create_tenant(str(name))
        )
    else:
        existing_by_email = stores.db.conn.execute(
            "SELECT id, tenant_id FROM users WHERE email=?",
            (email,),
        ).fetchone()
        tenant_id = (
            existing_by_email["tenant_id"]
            if existing_by_email
            else stores.auth.create_tenant(str(name or email))
        )

    return stores.users.oauth_upsert("clerk", sub, email, str(name), avatar_url, tenant_id)


def _human_scopes() -> list[str]:
    return [
        "data:read",
        "strategy:author",
        "runs:write",
        "runs:cancel",
        "approvals:read",
        "approvals:decide",
        "providers:write",
        "triggers:read",
        "triggers:write",
        "alerts:read",
        "alerts:ack",
        "artifacts:read",
        "deploy:backtest",
        "deploy:paper",
    ]


def _principal_from_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": user["tenant_id"],
        "key_id": user["id"],
        "scopes": _human_scopes(),
        "actor_kind": "user",
    }


def _user_from_human_token(stores: "Stores", token: str) -> dict[str, Any] | None:
    claims = _decode_clerk_token(token)
    if claims is None:
        return None
    return {**_upsert_clerk_user(stores, claims), "clerk_subject": str(claims["sub"])}


def _verify_bearer(request: Request, authorization: str | None) -> dict[str, Any] | None:
    """Verify a bearer token — either a session JWT (human) or an agent API key.

    Returns a principal dict with at least ``tenant_id``, or ``None`` if no bearer
    token was presented (dev / X-Tenant-Id path). Raises 401 on invalid tokens.
    """
    key = _bearer_key(authorization)
    if key is None:
        return None
    stores = request.app.state.stores
    # Clerk-managed ``ak_`` keys and legacy ``dmbg_`` keys for BYO agents.
    if key.startswith(("ak_", "dmbg_")):
        try:
            principal = stores.agent_keys.verify(key)
        except ClerkApiUnavailable as exc:
            raise HTTPException(status_code=503, detail="API key verification unavailable") from exc
        except ClerkApiError as exc:
            raise HTTPException(status_code=401, detail="invalid or revoked token") from exc
        if principal is None:
            raise HTTPException(status_code=401, detail="invalid or revoked token")
        return {**principal, "actor_kind": "agent"}

    # Clerk session JWTs for human users.
    user = _user_from_human_token(stores, key)
    if user is not None:
        return _principal_from_user(user)
    raise HTTPException(status_code=401, detail="invalid or revoked token")


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
    return env in {"test", "local", "dev", "development"}


def _cors_allowed_origins() -> list[str]:
    if _allow_dev_tenant_header():
        return ["*"]
    return _csv_env("CLERK_ALLOWED_ORIGINS")


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


def _mint_alerts_sse_ticket(stores: Stores, ctx: Ctx) -> dict[str, Any]:
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
                    "__alerts__",
                    str(ctx.actor_id),
                    _hash_sse_secret(secret),
                    now.isoformat(),
                    expires.isoformat(),
                ),
            )
    return {
        "sse_ticket": token,
        "tenant_id": ctx.tenant_id,
        "expires_at": expires.isoformat(),
        "single_use": True,
    }


def _alert_sse_frame(notification: dict[str, Any]) -> str:
    event = {
        "id": notification["notification_id"],
        "type": notification["event_type"],
        "notification": notification,
    }
    return (
        f"id: {notification['notification_id']}\n"
        f"event: {notification['event_type']}\n"
        f"data: {json.dumps(event, default=str)}\n\n"
    )


async def _alert_event_stream(
    stores: Stores,
    tenant_id: str,
    *,
    after_id: str | None = None,
    replay_only: bool = False,
    poll_seconds: float = 2.0,
):
    seen: set[str] = set()
    alerts = list(reversed(stores.notifications.list(tenant_id, state="open", limit=500)))
    emit = after_id is None
    for alert in alerts:
        seen.add(alert["notification_id"])
        if not emit:
            emit = alert["notification_id"] == after_id
            continue
        yield _alert_sse_frame(alert)
    if replay_only:
        return
    while True:
        await asyncio.sleep(max(0.5, poll_seconds))
        current = list(reversed(stores.notifications.list(tenant_id, state="open", limit=500)))
        emitted = False
        for alert in current:
            if alert["notification_id"] in seen:
                continue
            seen.add(alert["notification_id"])
            emitted = True
            yield _alert_sse_frame(alert)
        if not emitted:
            yield ": keepalive\n\n"


def _ops_status(stores: Stores, tenant_id: str) -> dict[str, Any]:
    connections = stores.providers.list_connections(tenant_id)
    snapshots = stores.providers.list_snapshots(tenant_id, limit=25)
    jobs = stores.jobs.list(tenant_id, limit=500)
    triggers = stores.triggers.list(tenant_id, limit=500)
    leases = stores.leases.list()

    connected = [c for c in connections if c.get("state") == "connected"]
    private_live_names = {
        "ibkr",
        "ibkr-engine",
        "interactive_brokers",
        "interactive-brokers",
        PUBLIC_DATA_SOURCE,
    }
    private_live_connections = [
        c for c in connected if str(c.get("provider") or "").strip().lower() in private_live_names
    ]
    quote_caps = {"quote", "quotes", "market_data", "market-data", "data"}
    live_quote_provider = any(_has_capability(c, quote_caps) for c in private_live_connections)
    entitlement_records = sum(len(c.get("entitlements") or []) for c in connections)

    live_data_url = os.environ.get("DOOMBERG_IBKR_ENGINE_URL")
    live_data_configured = bool(_configured_host(live_data_url))
    queued_jobs = sum(1 for job in jobs if job.get("state") == "queued")
    active_jobs = sum(1 for job in jobs if job.get("state") in {"leased", "running"})
    failed_jobs = sum(1 for job in jobs if job.get("state") in {"failed", "timed_out", "cancelled"})
    active_triggers = sum(1 for trigger in triggers if trigger.get("state") == "active")

    now = datetime.now(timezone.utc)

    def age_seconds(value: Any) -> float | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (now - parsed).total_seconds())
        except ValueError:
            return None

    backtest_jobs = [job for job in jobs if job.get("profile") == "backtest"]
    queued_backtests = [job for job in backtest_jobs if job.get("state") == "queued"]
    running_backtests = [job for job in backtest_jobs if job.get("state") in {"leased", "running"}]
    failed_backtests = [job for job in backtest_jobs if job.get("state") in {"failed", "timed_out"}]
    queue_ages = [age for job in queued_backtests if (age := age_seconds(job.get("created_at"))) is not None]
    heartbeat_ages = [age for job in running_backtests if (age := age_seconds(job.get("heartbeat_at"))) is not None]
    oldest_queued_s = max(queue_ages, default=None)
    oldest_heartbeat_s = max(heartbeat_ages, default=None)
    backtest_stalled = bool(
        (oldest_queued_s is not None and oldest_queued_s > 120)
        or (oldest_heartbeat_s is not None and oldest_heartbeat_s > 90)
    )

    readiness = [
        {
            "name": "Platform store",
            "state": "succeeded" if getattr(stores.db, "is_postgres", False) else "paused",
            "detail": "Postgres system-of-record"
            if getattr(stores.db, "is_postgres", False)
            else "Local SQLite system-of-record",
        },
        {
            "name": "Live market data",
            "state": "succeeded" if live_data_configured else "warn",
            "detail": "Configured" if live_data_configured else "Live market-data engine is unset",
        },
        {
            "name": "Live data record",
            "state": "succeeded" if live_quote_provider else "warn",
            "detail": "Connected quote capability registered"
            if live_quote_provider
            else "Register live data with quote capability",
        },
        {
            "name": "Trading",
            "state": "succeeded",
            "detail": "Paper handoff enabled; live execution disabled unless explicitly configured",
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
        {
            "name": "Backtest workers",
            "state": "warn" if backtest_stalled else "succeeded",
            "detail": (
                f"{len(queued_backtests)} queued, {len(running_backtests)} running, "
                f"oldest queue {int(oldest_queued_s or 0)}s, "
                f"heartbeat lag {int(oldest_heartbeat_s or 0)}s"
            ),
        },
        {
            "name": "Artifact storage",
            "state": "succeeded" if object_storage_configured() else "warn",
            "detail": (
                "Private object storage configured"
                if object_storage_configured()
                else "Object storage unset; production bundles are not durable"
            ),
        },
    ]

    return {
        "platform": {
            "database": "postgres" if getattr(stores.db, "is_postgres", False) else "sqlite",
            "mcp_allowed_hosts": os.environ.get("DOOMBERG_MCP_ALLOWED_HOSTS") or "",
        },
        "live_data": {
            "engine_configured": live_data_configured,
            "quote_path": os.environ.get("DOOMBERG_IBKR_QUOTE_PATH") or "/quote?symbol={symbol}",
            "connected_quote_provider": live_quote_provider,
        },
        "execution": {
            "paper_enabled": True,
            "live_enabled": _env_flag("DOOMBERG_ENABLE_LIVE_EXECUTION"),
            "disabled": False,
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
            "backtests": {
                "queued": len(queued_backtests),
                "leased_or_running": len(running_backtests),
                "failed_or_timed_out": len(failed_backtests),
                "oldest_queued_seconds": oldest_queued_s,
                "oldest_heartbeat_seconds": oldest_heartbeat_s,
                "stalled": backtest_stalled,
            },
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
        raise HTTPException(
            status_code=400, detail="X-Tenant-Id header (or ?tenant_id=) is required"
        )
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
        raise HTTPException(
            status_code=400, detail="X-Tenant-Id header (or ?tenant_id=) is required"
        )
    resolved = _validate_tenant_id(resolved)
    return Ctx(
        tenant_id=resolved,
        actor_kind=(x_actor_kind or "user").strip().lower(),
        actor_id=(x_actor_id or "ui").strip() or "ui",
    )


def _do(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except ActionError as err:
        raise HTTPException(status_code=err.status, detail=err.detail) from err


def _require_scope(ctx: Ctx, scope: str) -> None:
    if not ctx.has_scope(scope):
        raise HTTPException(status_code=403, detail=f"missing required scope: {scope}")


def _validate_trigger_policy(policy: dict[str, Any]) -> None:
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")
    when = policy.get("when")
    if not isinstance(when, dict):
        raise ValueError("policy.when must be an object")
    event = when.get("event") or "price.threshold"
    if event not in {"price.threshold", "market.price", "market.quote"}:
        raise ValueError(f"unsupported trigger event: {event}")
    universe = when.get("universe")
    if not ((isinstance(universe, list) and universe) or isinstance(when.get("symbol"), str)):
        raise ValueError("policy.when must include universe or symbol")
    baseline = when.get("baseline")
    if baseline is not None:
        if not isinstance(baseline, dict):
            raise ValueError("policy.when.baseline must be an object")
        if baseline.get("type") not in {
            "previous_close",
            "session_open",
            "fixed_price",
            "last_firing",
            "snapshot",
            "snapshot_on_activation",
        }:
            raise ValueError(f"unsupported baseline type: {baseline.get('type')}")
    mode = (policy.get("action") or {}).get("mode") or "analyze"
    if mode not in {"notify", "observe", "analyze", "propose", "execute"}:
        raise ValueError(f"unsupported action mode: {mode}")
    if mode == "execute":
        raise ValueError("execute mode is disabled in v1")


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


def _spa_file_response(dist: Path, full_path: str) -> FileResponse:
    """Serve built files when present, otherwise fall back to the SPA index."""
    shell_headers = {"Cache-Control": "no-store, max-age=0"}
    if full_path == "":
        return FileResponse(dist / "index.html", headers=shell_headers)
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")

    root = dist.resolve()
    target = (root / full_path).resolve()
    if target.is_file() and target.is_relative_to(root):
        headers = (
            {"Cache-Control": "public, max-age=31536000, immutable"}
            if full_path.startswith("assets/")
            else {"Cache-Control": "no-cache"}
        )
        return FileResponse(target, headers=headers)
    # Vite gives bundled assets content-hashed names. If an old SPA shell asks for an
    # asset removed by a newer deployment, returning index.html as JavaScript produces
    # a module MIME error and a blank page. Only client-side routes get the SPA fallback.
    if full_path.startswith("assets/"):
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(root / "index.html", headers=shell_headers)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def create_app(db: Any | None = None) -> FastAPI:
    if db is None:
        db = open_db(os.environ.get("DOOMBERG_DB", ":memory:"))
    stores = Stores(db)

    app = FastAPI(title="doomberg-rest-gateway", version="0.0.0")
    app.state.stores = stores

    # Permissive CORS for local/dev only. Deployed environments use Clerk/app origins.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allowed_origins(),
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

    @app.get("/api/auth/me")
    def me(
        authorization: str | None = Header(default=None, alias="Authorization"),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        key = _bearer_key(authorization)
        if not key:
            raise HTTPException(status_code=401, detail="not authenticated")
        # Clerk API keys are opaque ``ak_`` values, not session JWTs.
        user = None if key.startswith(("ak_", "dmbg_")) else _user_from_human_token(stores, key)
        if user is not None:
            return {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "avatarUrl": user.get("avatar_url"),
                "tenantId": user["tenant_id"],
            }
        # Try a Clerk-managed or legacy API key (BYO agents).
        try:
            principal = stores.agent_keys.verify(key)
        except ClerkApiUnavailable as exc:
            raise HTTPException(status_code=503, detail="API key verification unavailable") from exc
        except ClerkApiError as exc:
            raise HTTPException(status_code=401, detail="invalid token") from exc
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
        if key and not key.startswith(("ak_", "dmbg_")):
            user = _user_from_human_token(stores, key)
            if user is not None:
                return user
        raise HTTPException(status_code=401, detail="sign in to manage API keys")

    @app.get("/api/dashboard/adaptive")
    def get_adaptive_dashboard(
        authorization: str | None = Header(default=None, alias="Authorization"),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        """Return the signed-in user's adaptive dashboard state.

        This route intentionally rejects dev tenant headers and agent API keys. Profiles are
        keyed to the real human user id, not just the tenant.
        """
        user = _session_user(authorization, stores)
        signals = usage_signals_for_user(stores, user["tenant_id"], user["id"])
        if int(signals["session_count"]) < 1:
            return {"status": "empty"}
        profile = stores.adaptive_dashboards.get(user["tenant_id"], user["id"])
        if profile is None:
            return {
                "status": "pending",
                "spec": default_adaptive_dashboard_spec(),
                "source_session_count": int(signals["session_count"]),
                "source_event_count": int(signals["event_count"]),
            }
        return {
            "status": "ready",
            "spec": profile["spec"],
            "model": profile["model"],
            "source_session_count": profile["source_session_count"],
            "source_event_count": profile["source_event_count"],
            "generated_for_date": profile["generated_for_date"],
            "created_at": profile["created_at"],
            "updated_at": profile["updated_at"],
        }

    _DEFAULT_KEY_SCOPES = [
        "data:read",
        "strategy:author",
        "runs:write",
        "runs:cancel",
        "approvals:read",
        "triggers:read",
        "alerts:read",
        "alerts:ack",
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
            plaintext, key_id = stores.agent_keys.mint_key(
                user["tenant_id"], scopes, subject=user.get("clerk_subject")
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ClerkApiUnavailable as exc:
            raise HTTPException(status_code=503, detail="Clerk API key service unavailable") from exc
        except ClerkApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "api_key": plaintext,
            "key_id": key_id,
            "scopes": scopes,
            "tenant_id": user["tenant_id"],
        }

    @app.get("/api/auth/keys")
    def list_api_keys(
        authorization: str | None = Header(default=None, alias="Authorization"),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        """List the signed-in user's tenant's keys (metadata only — secrets are never stored)."""
        user = _session_user(authorization, stores)
        try:
            keys = stores.agent_keys.list_keys(
                user["tenant_id"], subject=user.get("clerk_subject")
            )
        except ClerkApiUnavailable as exc:
            raise HTTPException(status_code=503, detail="Clerk API key service unavailable") from exc
        except ClerkApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"keys": keys}

    @app.delete("/api/auth/keys/{key_id}")
    def revoke_api_key(
        key_id: str,
        authorization: str | None = Header(default=None, alias="Authorization"),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        """Revoke a key — only if it belongs to the signed-in user's tenant (no cross-tenant)."""
        user = _session_user(authorization, stores)
        try:
            revoked = stores.agent_keys.revoke_key(
                key_id,
                tenant_id=user["tenant_id"],
                subject=user.get("clerk_subject"),
            )
        except ClerkApiUnavailable as exc:
            raise HTTPException(status_code=503, detail="Clerk API key service unavailable") from exc
        except ClerkApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not revoked:
            raise HTTPException(status_code=404, detail="key not found")
        return {"key_id": key_id, "revoked": True}

    @app.get("/api/agent/toolkits")
    def agent_toolkits(ctx: Ctx = Depends(_ctx)) -> dict[str, Any]:
        """Return the canonical direct-tool toolkit catalog for the Agent/Codex UI."""
        _require_scope(ctx, "data:read")
        toolset = Toolset()
        catalog = toolset.list_toolkits()
        toolkits = []
        for toolkit in catalog.get("toolkits", []):
            detail = toolset.describe_toolkit(str(toolkit["toolkit_id"]))
            direct_tools = detail.get("direct_tools") or []
            toolkits.append({
                **detail,
                "direct_tool_count": len(direct_tools),
                "skill_count": len(detail.get("skill_ids") or []),
                "tools": [{"name": tool} for tool in direct_tools],
            })
        return {
            "kind": "toolkits.catalog",
            "source": "live",
            "toolkits": toolkits,
            "count": catalog.get("count", 0),
        }

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
                _session_summary(row, stores.trace.events(tenant_id, row["run_id"])) for row in rows
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
        In that flow the agent later calls MCP ``start_research_session`` with the actual
        prompt, and the trace updates live under the same run id.
        """
        prompt = body.prompt.strip()

        principal = _verify_bearer(request, authorization)
        if principal is not None:
            resolved_tenant = principal["tenant_id"]
            actor_kind = (principal.get("actor_kind") or "user").strip().lower()
            actor_id = (principal.get("key_id") or "ui").strip() or "ui"
        else:
            resolved_tenant = require_tenant(
                request=request,
                authorization=None,
                x_tenant_id=x_tenant_id,
                tenant_id=tenant_id,
            )
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
        stores.trace.append(
            {
                "run_id": run_id,
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "session_open",
                "tenant_id": resolved_tenant,
                "session_id": run_id,
                "origin_session_id": run_id,
                "actor": {"kind": actor_kind, "id": actor_id},
                "data": data,
            }
        )
        run = stores.runs.get(resolved_tenant, run_id)
        events = stores.trace.events(resolved_tenant, run_id)
        shaped = shape_run(run, events)
        shaped["jobs"] = stores.jobs.list_by_run(resolved_tenant, run_id)
        shaped["artifacts"] = stores.artifacts.list_by_run(resolved_tenant, run_id)
        return shaped

    @app.post("/api/feedback", status_code=201)
    def submit_feedback(
        body: FeedbackBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        if ctx.actor_kind not in HUMAN_ACTOR_KINDS:
            raise HTTPException(status_code=403, detail="feedback requires a signed-in user")
        message = body.message.strip()
        if not message:
            raise HTTPException(status_code=422, detail="feedback message is required")
        if len(message) > MAX_FEEDBACK_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"feedback message must be {MAX_FEEDBACK_LENGTH} characters or fewer",
            )
        saved = stores.feedback.create(ctx.tenant_id, ctx.actor_id, message)
        return {
            "feedback_id": saved["feedback_id"],
            "status": "received",
            "created_at": saved["created_at"],
        }

    # ---- reads -------------------------------------------------------------------------
    @app.get("/api/runs")
    def list_runs(
        kind: str | None = None,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return {"runs": [shape_run_row(r) for r in stores.runs.list(tenant_id, kind=kind)]}

    @app.get("/api/dashboard/summary")
    def get_dashboard_summary(
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> DashboardEnvelope[DashboardSummaryData]:
        _require_scope(ctx, "data:read")
        return DashboardEnvelope[DashboardSummaryData].model_validate(
            dashboard_summary(stores.dashboard, ctx.tenant_id)
        )

    @app.get("/api/dashboard/risk")
    def get_dashboard_risk(
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> DashboardEnvelope[DashboardRiskData]:
        _require_scope(ctx, "data:read")
        return DashboardEnvelope[DashboardRiskData].model_validate(
            dashboard_risk(stores.dashboard, ctx.tenant_id)
        )

    @app.get("/api/dashboard/activity")
    def get_dashboard_activity(
        limit: int = Query(default=20, ge=1, le=100),
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> DashboardEnvelope[DashboardActivityData]:
        _require_scope(ctx, "data:read")
        _require_scope(ctx, "triggers:read")
        _require_scope(ctx, "alerts:read")
        return DashboardEnvelope[DashboardActivityData].model_validate(
            dashboard_activity(stores.dashboard, ctx.tenant_id, limit=limit)
        )

    @app.get("/api/dashboard/market")
    def get_dashboard_market(
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> DashboardEnvelope[DashboardMarketData]:
        _require_scope(ctx, "data:read")
        return DashboardEnvelope[DashboardMarketData].model_validate(
            dashboard_market(stores.dashboard, ctx.tenant_id)
        )

    @app.get("/api/providers/status")
    def get_provider_status(
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> DashboardEnvelope[ProviderStatusData]:
        _require_scope(ctx, "data:read")
        return DashboardEnvelope[ProviderStatusData].model_validate(
            provider_status(stores.dashboard, ctx.tenant_id)
        )

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

    @app.get("/api/ops/live-data-smoke")
    def live_data_smoke(
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
        return {
            "artifacts": stores.artifacts.list(ctx.tenant_id, run_id=run_id, kind=kind, limit=limit)
        }

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

    @app.get("/api/artifacts/{artifact_id}/download")
    def download_artifact(
        artifact_id: str,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ):
        """Download a tenant-owned artifact without exposing storage credentials."""
        _require_scope(ctx, "artifacts:read")
        artifact = stores.artifacts.get(ctx.tenant_id, artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        uri = str(artifact.get("uri") or "")
        if uri.startswith("s3://"):
            try:
                body, content_length, content_type = open_artifact(uri)
            except (RuntimeError, ValueError) as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except Exception as exc:  # noqa: BLE001 - stable storage boundary
                raise HTTPException(status_code=503, detail="artifact storage unavailable") from exc
            filename = Path(
                str((artifact.get("metadata") or {}).get("filename") or "artifact")
            ).name.replace('"', "").replace("\r", "").replace("\n", "")
            headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
            if content_length is not None:
                headers["Content-Length"] = str(content_length)
            return StreamingResponse(
                body.iter_chunks(),
                media_type=content_type or artifact.get("media_type") or "application/octet-stream",
                headers=headers,
            )
        if uri.startswith("file://"):
            path = Path(urllib.parse.unquote(urllib.parse.urlparse(uri).path))
            if not path.is_file():
                raise HTTPException(status_code=404, detail="artifact bytes not found")
            return FileResponse(
                path,
                media_type=artifact.get("media_type") or "application/octet-stream",
                filename=str((artifact.get("metadata") or {}).get("filename") or path.name),
            )
        raise HTTPException(
            status_code=409,
            detail="artifact bytes were not persisted; rerun after storage is configured",
        )

    @app.get("/api/approvals")
    def list_approvals(
        run_id: str | None = None,
        state: str | None = None,
        limit: int = 100,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "approvals:read")
        return {
            "approvals": stores.approvals.list(
                ctx.tenant_id, run_id=run_id, state=state, limit=limit
            )
        }

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
            raise HTTPException(
                status_code=404, detail="approval not found or already decided"
            ) from exc
        if approval is None:
            raise HTTPException(status_code=404, detail="approval not found")
        stores.trace.append(
            {
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
            }
        )
        return approval

    @app.get("/api/providers")
    def list_providers(
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return {
            "connections": [
                public_provider_connection(connection)
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
        body.capabilities = [
            cap
            for cap in body.capabilities
            if str(cap).strip().lower() not in {"orders", "trading", "execution"}
        ]
        provider_name = str(body.provider or "").strip().lower()
        credential_ref = body.credential_ref
        if (
            provider_name
            in {
                "ibkr",
                "ibkr-engine",
                "interactive_brokers",
                "interactive-brokers",
                PUBLIC_DATA_SOURCE,
            }
            and not credential_ref
        ):
            credential_ref = "env:DOOMBERG_IBKR_ENGINE_TOKEN"
        connection = stores.providers.upsert_connection(
            ctx.tenant_id,
            provider=body.provider,
            capabilities=body.capabilities,
            entitlements=body.entitlements,
            state=body.state,
            connection_id=body.connection_id,
            account_ref=body.account_ref,
            credential_ref=credential_ref,
            retention_policy=body.retention_policy,
        )
        return public_provider_connection(connection)

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
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "data:read")
        intents = stores.execution.list_intents(
            ctx.tenant_id,
            run_id=run_id,
            state=state,
            limit=limit,
        )
        records = [
            record
            for intent in intents
            if (record := stores.execution.get_record(ctx.tenant_id, intent["intent_id"]))
            is not None
        ]
        return {"order_intents": records}

    @app.post("/api/order-intents", status_code=201)
    def create_order_intent(
        body: CreateOrderIntentBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return _do(
            ExecutionGateway(stores).create_intent,
            ctx,
            run_id=body.run_id,
            payload=body.payload,
            strategy_id=body.strategy_id,
            account_ref=body.account_ref,
            idempotency_key=body.idempotency_key,
        )

    @app.get("/api/order-intents/{intent_id}")
    def get_order_intent(
        intent_id: str,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "data:read")
        record = stores.execution.get_record(ctx.tenant_id, intent_id)
        if record is None:
            raise HTTPException(status_code=404, detail="order intent not found")
        return record

    @app.post("/api/order-intents/{intent_id}/preview")
    def preview_order_intent(
        intent_id: str,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return _do(ExecutionGateway(stores).preview, ctx, intent_id)

    @app.post("/api/order-intents/{intent_id}/submit")
    def submit_order_intent(
        intent_id: str,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return _do(ExecutionGateway(stores).submit, ctx, intent_id)

    @app.get("/api/triggers")
    def list_triggers(
        state: str | None = None,
        limit: int = 100,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "triggers:read")
        return {"triggers": stores.triggers.list(ctx.tenant_id, state=state, limit=limit)}

    @app.get("/api/trigger-firings")
    def list_trigger_firings(
        trigger_id: str | None = None,
        limit: int = 100,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "triggers:read")
        return {
            "firings": stores.triggers.list_firings(
                ctx.tenant_id,
                trigger_id=trigger_id,
                limit=limit,
            )
        }

    @app.get("/api/alerts")
    def list_alerts(
        state: str | None = "open",
        limit: int = 100,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "alerts:read")
        return {"alerts": stores.notifications.list(ctx.tenant_id, state=state, limit=limit)}

    @app.post("/api/alerts/events-ticket", status_code=201)
    def mint_alert_events_ticket(
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "alerts:read")
        return _mint_alerts_sse_ticket(stores, ctx)

    @app.get("/api/alerts/events")
    def stream_alert_events(
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
            resolved_tenant_id = _redeem_sse_ticket(stores, sse_ticket, "__alerts__")
        elif access_token:
            raise HTTPException(
                status_code=401,
                detail="use /api/alerts/events-ticket instead of access_token query auth",
            )
        else:
            resolved_tenant_id = require_tenant(
                request,
                authorization=authorization,
                x_tenant_id=x_tenant_id,
                tenant_id=tenant_id,
            )
        after_id = request.query_params.get("after_id") or last_event_id
        replay_only = request.query_params.get("replay_only") == "1"
        stream = _alert_event_stream(
            stores,
            resolved_tenant_id,
            after_id=after_id,
            replay_only=replay_only,
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

    @app.get("/api/alerts/{notification_id}")
    def get_alert(
        notification_id: str,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "alerts:read")
        alert = stores.notifications.get(ctx.tenant_id, notification_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="alert not found")
        return {
            "alert": alert,
            "attempts": stores.notifications.list_attempts(ctx.tenant_id, notification_id),
        }

    @app.post("/api/alerts/{notification_id}/ack")
    def ack_alert(
        notification_id: str,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "alerts:ack")
        try:
            return stores.notifications.ack(ctx.tenant_id, notification_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="alert not found") from exc

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
            _validate_trigger_policy(body.policy)
            return TriggerEngine(stores, worker_id="rest-trigger-dry-run").dry_run(
                trigger,
                quote=body.quote,
            )
        except (ValueError, TriggerEvaluationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/triggers", status_code=201)
    def create_trigger(
        body: CreateTriggerBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        _require_scope(ctx, "triggers:write")
        try:
            _validate_trigger_policy(body.policy)
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
        if body.kind not in {"backtest", "paper"}:
            raise HTTPException(status_code=422, detail="kind must be backtest or paper")
        try:
            return actions.create_run(
                stores,
                ctx,
                strategy_id=body.strategy_id,
                kind=body.kind,
                range_=body.range,
                idempotency_key=body.idempotency_key,
            )
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
        def route(
            run_id: str, ctx: Ctx = Depends(_ctx), stores: Stores = Depends(get_stores)
        ) -> dict[str, Any]:
            return _do(fn, stores, ctx, run_id)

        return route

    for _name, _fn in (
        ("promote", actions.promote_run),
        ("activate", actions.activate_run),
        ("pause", actions.pause_run),
        ("resume", actions.resume_run),
        ("retire", actions.retire_run),
    ):
        app.add_api_route(
            f"/api/runs/{{run_id}}/{_name}",
            _action_route(_fn),
            methods=["POST"],
            name=f"run_{_name}",
        )

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
            stores.trace,
            resolved_tenant_id,
            run_id,
            after_seq=after_seq,
            deadline_seconds=deadline_seconds,
            replay_only=replay_only,
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
    @app.get("/install.py", include_in_schema=False)
    def install_script() -> FileResponse:
        script = _repo_root() / "scripts" / "install_agent_mcp.py"
        if not script.is_file():
            raise HTTPException(status_code=404, detail="installer not found")
        return FileResponse(script, media_type="text/x-python")

    # Registered LAST, so the explicit ``/api/*`` + ``/healthz`` routes above always win.
    # Starlette's ``StaticFiles(html=True)`` does not implement a true BrowserRouter
    # fallback for arbitrary paths like ``/sessions``; serve files explicitly and return
    # ``index.html`` for non-API client-side routes.
    dist = _web_dist_dir()
    if dist is not None:
        @app.get("/", include_in_schema=False)
        def web_index() -> FileResponse:
            return _spa_file_response(dist, "")

        @app.get("/{full_path:path}", include_in_schema=False)
        def web_fallback(full_path: str) -> FileResponse:
            return _spa_file_response(dist, full_path)

    return app


# Module-level app for `uvicorn doomberg_rest.app:app`.
app = create_app()
