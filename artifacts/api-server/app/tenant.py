"""Per-request tenant (firm) scoping context.

Multi-tenant isolation hinges on one question every store must answer: *which
firm is this call acting on behalf of?* Rather than thread a ``firm_id``
argument through dozens of deep call sites (agent → skills → strategy → store),
the answer lives in a :class:`contextvars.ContextVar` that is set once per
request from the authenticated identity and read by the stores when they scope a
read or stamp a write.

Why a context var (not a function argument):
- The request path is deep and mostly firm-agnostic in shape; only the storage
  layer truly needs the firm. A context var keeps that plumbing invisible to the
  business logic while still being correct.
- ``contextvars`` are copied per asyncio task (one per request) and propagated
  into the threadpool that runs sync endpoints, so a value set in the request's
  identity dependency is visible to the handler and everything it calls — and
  never leaks across concurrent requests.

The background worker runs outside any request, so it explicitly enters a
firm scope per item with :func:`firm_context` (e.g. when marking or rebalancing
each firm's books), which is the only place the var is reset.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator, Optional

# The firm that owns any state created outside an authenticated request: the
# backfill target for rows that predate multi-tenancy and the default scope the
# background worker falls back to when no firm context is active.
DEFAULT_FIRM_ID = "default"

_current_firm: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_firm_id", default=DEFAULT_FIRM_ID
)


def set_current_firm(firm_id: Optional[str]) -> None:
    """Bind the active firm for the current request/context (identity dependency)."""
    _current_firm.set(firm_id or DEFAULT_FIRM_ID)


def current_firm_id() -> str:
    """The firm the current call is acting on behalf of (``default`` if unset)."""
    return _current_firm.get() or DEFAULT_FIRM_ID


def resolve_firm(firm_id: Optional[str]) -> str:
    """An explicit ``firm_id`` if given, else the current context's firm."""
    return firm_id or current_firm_id()


@contextmanager
def firm_context(firm_id: Optional[str]) -> Iterator[str]:
    """Temporarily act as ``firm_id`` within the block, restoring on exit.

    Used by the background worker to scope each cross-firm iteration (marking,
    rebalancing) to the firm that owns the book being processed, so every store
    call inside the block isolates to that firm without explicit arguments.
    """
    fid = firm_id or DEFAULT_FIRM_ID
    token = _current_firm.set(fid)
    try:
        yield fid
    finally:
        _current_firm.reset(token)
