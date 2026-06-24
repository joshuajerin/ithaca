"""Trace-event emission helpers for the workers.

Workers are observable: every meaningful step appends a :class:`TraceEvent` to the
platform ``TraceStore``. The store assigns the gap-free per-run ``seq`` (any seq we
pass is ignored), validates against the closed ``TraceEvent`` contract, and returns
the assigned seq.

CRITICAL (v1 lesson, restated in INTERFACES.md): never ``except: pass`` on an audited
path. On any failure the worker emits a ``denial`` or ``error`` event rather than
swallowing it. These helpers keep that disciplined and uniform.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

__all__ = ["emit", "now_iso"]

# A `seq` is required by the contract (ge=0) but is server-assigned by the store,
# so we pass a placeholder 0 and let TraceStore.append overwrite it.
_SEQ_PLACEHOLDER = 0

# The worker is a system actor (not a user, not the agent).
_WORKER_ACTOR = {"kind": "system", "id": "doomberg_runtime"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(
    trace: Any,
    *,
    tenant_id: str,
    run_id: str,
    type: str,
    data: dict[str, Any],
    actor: dict[str, str] | None = None,
    session_id: str | None = None,
    origin_session_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
) -> int:
    """Build a contract-shaped event dict and append it via the TraceStore.

    Returns the store-assigned seq. Raises whatever the store raises (e.g. a
    contract ValidationError) — callers must not swallow it on an audited path.
    """
    event: dict[str, Any] = {
        "run_id": str(run_id),
        "seq": _SEQ_PLACEHOLDER,
        "ts": now_iso(),
        "type": type,
        "tenant_id": str(tenant_id),
        "actor": dict(actor or _WORKER_ACTOR),
        "data": data,
    }
    if session_id is not None:
        event["session_id"] = str(session_id)
    if origin_session_id is not None:
        event["origin_session_id"] = str(origin_session_id)
    if span_id is not None:
        event["span_id"] = span_id
    if parent_span_id is not None:
        event["parent_span_id"] = parent_span_id
    return trace.append(event)
