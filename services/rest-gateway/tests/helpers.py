"""Shared test helpers: seed runs, strategies, and trace events via the platform stores."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_run(stores: Any, tenant_id: str, *, kind: str = "backtest") -> str:
    """Create a draft run for the tenant; returns its run_id."""
    return stores.runs.create(tenant_id, kind, None, {"name": "demo"})


def seed_strategy(stores: Any, tenant_id: str, name: str = "alpha") -> dict[str, Any]:
    return stores.strategies.create(tenant_id, {"name": name})


def append_event(
    stores: Any,
    tenant_id: str,
    run_id: str,
    *,
    type: str,
    data: dict[str, Any] | None = None,
    span_id: str | None = None,
    session_id: str | None = None,
) -> int:
    """Append a minimal-but-valid TraceEvent; returns the server-assigned seq."""
    event: dict[str, Any] = {
        "run_id": run_id,
        "ts": _now_iso(),
        "type": type,
        "tenant_id": tenant_id,
        "data": data or {},
    }
    if span_id is not None:
        event["span_id"] = span_id
    event["session_id"] = session_id or str(uuid.uuid4())
    return stores.trace.append(event)
