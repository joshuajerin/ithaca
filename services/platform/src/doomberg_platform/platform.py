"""Canonical Platform handle — one shared db + the three stores.

Both the control plane (writer) and the runtime (worker) take a "platform" object; this is
the single shared shape so they interoperate. Exposes ``.trace`` (the name the runtime uses)
with a ``.traces`` alias (the name the control plane used) so neither has to change.
"""
from __future__ import annotations

from .auth_store import AuthStore
from .book_store import BookStore
from .db import Db, open_db
from .run_store import RunStore
from .strategy_store import StrategyStore
from .trace_store import TraceStore

__all__ = ["Platform"]


class Platform:
    def __init__(self, db: Db | str = ":memory:") -> None:
        self.db: Db = db if isinstance(db, Db) else open_db(db)
        self.runs = RunStore(self.db)
        self.strategies = StrategyStore(self.db)
        self.trace = TraceStore(self.db)
        self.books = BookStore(self.db)
        self.auth = AuthStore(self.db)

    # the control plane referred to this store as `.traces`; keep both names valid.
    @property
    def traces(self) -> TraceStore:
        return self.trace
