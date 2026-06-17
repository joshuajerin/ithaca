"""Request-context resolution + platform wiring for the control plane.

Local dev resolves the tenant from an ``X-Tenant-Id`` header (a UUID string) and the actor
from ``X-Actor-Kind`` / ``X-Actor-Id``. In production this becomes a real principal resolved
from the ``dmbg_<env>_<keyid>_<secret>`` credential (role ∩ scope ∩ tenant); the seam is the
same ``Ctx`` object so the endpoints do not change.

The platform stores (the system-of-record) are created once and shared. ``open_db`` returns
a handle the four stores share; the path is taken from ``DOOMBERG_DB`` (default in-memory for
tests / a single-process local gateway).
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Header, HTTPException

from doomberg_core import Core
from doomberg_platform import BookStore, RunStore, StrategyStore, TraceStore, open_db

__all__ = ["Ctx", "Platform", "get_ctx", "get_platform", "get_core", "HUMAN_ACTOR_KINDS"]

# Actor kinds permitted to take the human control actions (promote). The agent (BYO host)
# holds at most ``deploy:paper`` which is "may REQUEST a deployment that requires human
# acceptance" — it can never self-promote. This is the absence-of-self-promote rule from the
# master plan, expressed as an actor check on the money-path endpoint.
HUMAN_ACTOR_KINDS = frozenset({"human", "user"})


@dataclass(frozen=True)
class Ctx:
    tenant_id: str
    actor_kind: str
    actor_id: str


class Platform:
    """The shared system-of-record handle + the three stores."""

    def __init__(self, db_path: str) -> None:
        self.db = open_db(db_path)
        self.runs = RunStore(self.db)
        self.strategies = StrategyStore(self.db)
        self.traces = TraceStore(self.db)
        self.books = BookStore(self.db)
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


def get_ctx(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_actor_kind: str | None = Header(default=None, alias="X-Actor-Kind"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
) -> Ctx:
    """Resolve the request context. ``X-Tenant-Id`` is mandatory in local dev."""
    if not x_tenant_id:
        raise HTTPException(status_code=401, detail="X-Tenant-Id header is required")
    tenant_id = _require_uuid(x_tenant_id, "X-Tenant-Id")
    actor_kind = (x_actor_kind or "agent").strip().lower()
    actor_id = (x_actor_id or "").strip() or "unknown"
    return Ctx(tenant_id=tenant_id, actor_kind=actor_kind, actor_id=actor_id)
