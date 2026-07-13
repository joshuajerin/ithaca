"""Request-context resolution + platform wiring for the control plane.

Two front-door principal resolvers, same ``Ctx`` seam:

- **Production / BYO agent:** an ``Authorization: Bearer <api-key>`` credential is verified
  by Clerk, with legacy ``dmbg_`` verification during migration. The
  resolved principal carries ``tenant_id`` + capability ``scopes``; an API key is an *agent*
  actor (it can author + request, never self-promote — the money-path actor rule still binds).
- **Local dev/test only:** when no bearer key is present we can fall back to the
  ``X-Tenant-Id`` header (a UUID) + optional ``X-Actor-Kind`` / ``X-Actor-Id``. Deployed
  environments must opt in with ``DOOMBERG_ALLOW_DEV_TENANT_HEADER=1``; otherwise public
  callers need real bearer/session auth.

A bad / revoked bearer key is a hard 401 (it does NOT silently fall back to dev mode).

The platform stores (the system-of-record) are created once and shared. ``open_db`` returns
a handle the stores share; the path is taken from ``DOOMBERG_DB`` (default in-memory for
tests / a single-process local gateway).
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from functools import lru_cache

from fastapi import Depends, Header, HTTPException

from doomberg_core import Core
from doomberg_platform import (
    VALID_SCOPES,
    ApprovalStore,
    ArtifactStore,
    AuthStore,
    BookStore,
    CompliancePolicyStore,
    DeliveryTargetStore,
    ExecutionControlStore,
    ExecutionStore,
    JobStore,
    LeaseStore,
    NotificationStore,
    ProviderStore,
    RunStore,
    StrategyStore,
    TraceStore,
    TriggerBaselineStore,
    TriggerStore,
    WorkerHeartbeatStore,
    build_agent_key_store,
    open_db,
)

__all__ = [
    "Ctx",
    "Platform",
    "get_ctx",
    "get_platform",
    "get_core",
    "HUMAN_ACTOR_KINDS",
    "require_scope",
    "resolve_ctx",
]

# Actor kinds permitted to take the human control actions (promote). The agent (BYO host)
# holds at most ``deploy:paper`` which is "may REQUEST a deployment that requires human
# acceptance" — it can never self-promote. This is the absence-of-self-promote rule from the
# master plan, expressed as an actor check on the money-path endpoint.
HUMAN_ACTOR_KINDS = frozenset({"human", "user"})

# Dev mode (X-Tenant-Id header, no bearer key) grants the full launch scope set so the
# existing local flows are unchanged. Scope enforcement only bites authenticated agents.
_DEV_SCOPES: frozenset[str] = VALID_SCOPES


def _allow_dev_tenant_header() -> bool:
    override = os.environ.get("DOOMBERG_ALLOW_DEV_TENANT_HEADER")
    if override is not None:
        return override.strip().lower() in {"1", "true", "yes", "on"}
    env = (os.environ.get("DOOMBERG_ENV") or "").strip().lower()
    return env in {"test", "local", "dev", "development"}


@dataclass(frozen=True)
class Ctx:
    tenant_id: str
    actor_kind: str
    actor_id: str
    # Capability scopes for THIS principal. Defaults to the full dev set so a Ctx built
    # directly (tests, scripts, the dev header path) is unrestricted; an authed agent key
    # carries exactly the scopes it was minted with.
    scopes: frozenset[str] = field(default=_DEV_SCOPES)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def require_scope(ctx: Ctx, scope: str) -> None:
    """Raise 403 if ``ctx`` lacks ``scope``. The transport maps it to an HTTP error."""
    if not ctx.has_scope(scope):
        raise HTTPException(status_code=403, detail=f"missing required scope: {scope}")


class Platform:
    """The shared system-of-record handle + the stores."""

    def __init__(self, db_path: str) -> None:
        self.db = open_db(db_path)
        self.runs = RunStore(self.db)
        self.strategies = StrategyStore(self.db)
        self.traces = TraceStore(self.db)
        self.books = BookStore(self.db)
        self.auth = AuthStore(self.db)
        self.agent_keys = build_agent_key_store(self.db)
        self.jobs = JobStore(self.db)
        self.leases = LeaseStore(self.db)
        self.worker_heartbeats = WorkerHeartbeatStore(self.db)
        self.artifacts = ArtifactStore(self.db)
        self.approvals = ApprovalStore(self.db)
        self.providers = ProviderStore(self.db)
        self.execution = ExecutionStore(self.db)
        self.execution_controls = ExecutionControlStore(self.db)
        self.compliance_policies = CompliancePolicyStore(self.db)
        self.triggers = TriggerStore(self.db)
        self.baselines = TriggerBaselineStore(self.db)
        self.notifications = NotificationStore(self.db)
        self.delivery_targets = DeliveryTargetStore(self.db)
        # the runtime worker expects the trace store as `.trace`; expose both names so a
        # control-plane Platform can be handed straight to run_backtest_job/run_paper_tick.
        self.trace = self.traces


@lru_cache(maxsize=1)
def get_platform() -> Platform:
    return Platform(os.environ.get("DOOMBERG_DB", ":memory:"))


@lru_cache(maxsize=1)
def get_core() -> Core:
    return Core()


def _require_uuid(value: str, field: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail=f"{field} must be a UUID string")


def _bearer_key(authorization: str | None) -> str | None:
    """Extract the ``dmbg_...`` token from an ``Authorization: Bearer <key>`` header."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1].strip()
        return token or None
    return None


def resolve_ctx(
    platform: Platform,
    *,
    authorization: str | None,
    x_tenant_id: str | None,
    x_actor_kind: str | None,
    x_actor_id: str | None,
) -> Ctx:
    """Resolve a :class:`Ctx` from a bearer key (prod) or the dev tenant header.

    Bearer key present  -> verify it (401 on bad/revoked); principal is an *agent* actor
                           carrying exactly its minted scopes.
    No bearer key       -> local/test dev fallback on ``X-Tenant-Id``; deployed envs 401.
    """
    key = _bearer_key(authorization)
    if key is not None:
        principal = platform.agent_keys.verify(key)
        if principal is None:
            raise HTTPException(status_code=401, detail="invalid or revoked API key")
        # An API key is a BYO agent principal: it may author + request but never self-promote.
        # Do not honor actor override headers for bearer credentials; those are a dev-only
        # convenience and would let an agent spoof the human-only money path.
        actor_kind = "agent"
        actor_id = principal["key_id"]
        return Ctx(
            tenant_id=principal["tenant_id"],
            actor_kind=actor_kind,
            actor_id=actor_id,
            scopes=frozenset(principal["scopes"]),
        )

    if not _allow_dev_tenant_header():
        raise HTTPException(status_code=401, detail="authentication required")
    if not x_tenant_id:
        raise HTTPException(status_code=401, detail="X-Tenant-Id header is required")
    tenant_id = _require_uuid(x_tenant_id, "X-Tenant-Id")
    actor_kind = (x_actor_kind or "agent").strip().lower()
    actor_id = (x_actor_id or "").strip() or "unknown"
    return Ctx(tenant_id=tenant_id, actor_kind=actor_kind, actor_id=actor_id)


def get_ctx(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_actor_kind: str | None = Header(default=None, alias="X-Actor-Kind"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
    platform: Platform = Depends(get_platform),
) -> Ctx:
    """Resolve the request context. Bearer key (prod) or ``X-Tenant-Id`` (local dev)."""
    return resolve_ctx(
        platform,
        authorization=authorization,
        x_tenant_id=x_tenant_id,
        x_actor_kind=x_actor_kind,
        x_actor_id=x_actor_id,
    )
