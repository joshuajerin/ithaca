"""doomberg-platform — Local system-of-record (SQLite).

Trace events (append-only, gap-free seq per run), runs (state machine with optimistic
version guard), strategies (immutable versioned specs), plus in-process pub/sub for SSE.
``tenant_id`` is a hard isolation invariant: it is the first argument and a column on
every table, and every query filters by it.

See ``docs/plans/doomberg-v2/INTERFACES.md`` for the seam this package conforms to.
"""

from __future__ import annotations

from .book_store import BookConflict, BookNotFound, BookStore
from .db import Db, open_db
from .platform import Platform
from .run_store import (
    RunNotFound,
    RunStore,
    TransitionConflict,
    TransitionError,
)
from .strategy_store import StrategyStore
from .trace_store import TraceStore

__all__ = [
    "open_db",
    "Db",
    "Platform",
    "TraceStore",
    "RunStore",
    "StrategyStore",
    "BookStore",
    "TransitionError",
    "TransitionConflict",
    "RunNotFound",
    "BookConflict",
    "BookNotFound",
]
