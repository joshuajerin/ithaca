"""Paper position-book store — the deployed book a live paper run holds.

A paper deployment owns ONE book row keyed by ``(tenant_id, run_id)``: the target
weights it currently holds, the notional capital, the derived cash sleeve, and the marks
the last apply priced on. The control plane is the SINGLE writer of this row (the money
path); the runtime worker only *proposes* deltas. Every write bumps an integer ``version``
and ``apply`` takes ``expect=version`` so a concurrent writer cannot clobber the book —
the same optimistic-concurrency guard the run state machine uses.

Tenant isolation is a hard invariant: ``tenant_id`` is the first argument and a column on
the row, and every query filters by it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .db import Db
from .db_scope import tenant_scoped_store


class BookConflict(RuntimeError):
    """Optimistic version mismatch: the book changed since ``expect`` was read."""


class BookNotFound(KeyError):
    """No book row for that (tenant, run)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: Any) -> dict[str, Any]:
    weights = json.loads(row["weights"]) if row["weights"] else {}
    marks = json.loads(row["marks"]) if row["marks"] else {}
    capital = float(row["capital"])
    gross = sum(abs(float(w)) for w in weights.values())
    return {
        "tenant_id": row["tenant_id"],
        "run_id": row["run_id"],
        "capital": capital,
        "weights": weights,
        "gross": round(gross, 6),
        "cash": round(capital * (1.0 - gross), 2),
        "marks": marks,
        "version": int(row["version"]),
        "updated_at": row["updated_at"],
    }


@tenant_scoped_store()
class BookStore:
    """The paper book row: target weights + capital, tenant-scoped, version-guarded."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def get(self, tenant_id: str, run_id: str) -> dict[str, Any] | None:
        tenant_id = str(tenant_id)
        run_id = str(run_id)
        row = self._db.conn.execute(
            "SELECT * FROM books WHERE tenant_id = ? AND run_id = ?",
            (tenant_id, run_id),
        ).fetchone()
        return _row_to_dict(row) if row else None

    def ensure(self, tenant_id: str, run_id: str, *, capital: float = 100_000.0) -> dict[str, Any]:
        """Return the book, creating a flat all-cash book at ``capital`` if none exists."""
        tenant_id = str(tenant_id)
        run_id = str(run_id)
        existing = self.get(tenant_id, run_id)
        if existing is not None:
            return existing
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                # Another writer may have created it between our read and this insert; ignore.
                conn.execute(
                    "INSERT INTO books "
                    "(tenant_id, run_id, capital, weights, marks, version, updated_at) "
                    "VALUES (?, ?, ?, '{}', '{}', 0, ?) "
                    "ON CONFLICT(tenant_id, run_id) DO NOTHING",
                    (tenant_id, run_id, float(capital), now),
                )
        return self.get(tenant_id, run_id)  # type: ignore[return-value]

    def apply(
        self,
        tenant_id: str,
        run_id: str,
        *,
        target_weights: dict[str, float],
        marks: dict[str, float] | None = None,
        expect: int | None = None,
    ) -> dict[str, Any]:
        """Set the book to ``target_weights`` (the post-trade book), version-guarded.

        Raises :class:`BookNotFound` if there is no book (call :meth:`ensure` first), and
        :class:`BookConflict` if ``expect`` no longer matches the stored version.
        """
        tenant_id = str(tenant_id)
        run_id = str(run_id)
        weights = {str(s).upper(): round(float(w), 6) for s, w in target_weights.items()
                   if abs(float(w)) > 1e-9}
        marks_json = json.dumps({str(s).upper(): float(m) for s, m in (marks or {}).items()})
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                row = conn.execute(
                    "SELECT version FROM books WHERE tenant_id = ? AND run_id = ?",
                    (tenant_id, run_id),
                ).fetchone()
                if row is None:
                    raise BookNotFound(run_id)
                current_version = int(row["version"])
                if expect is not None and expect != current_version:
                    raise BookConflict(
                        f"book version mismatch: expected {expect}, found {current_version}"
                    )
                cur = conn.execute(
                    "UPDATE books SET weights = ?, marks = ?, version = ?, updated_at = ? "
                    "WHERE tenant_id = ? AND run_id = ? AND version = ?",
                    (json.dumps(weights), marks_json, current_version + 1, now,
                     tenant_id, run_id, current_version),
                )
                if cur.rowcount == 0:
                    latest = conn.execute(
                        "SELECT version FROM books WHERE tenant_id = ? AND run_id = ?",
                        (tenant_id, run_id),
                    ).fetchone()
                    if latest is None:
                        raise BookNotFound(run_id)
                    raise BookConflict(
                        f"book version mismatch: expected {current_version}, "
                        f"found {int(latest['version'])}"
                    )
        return self.get(tenant_id, run_id)  # type: ignore[return-value]
