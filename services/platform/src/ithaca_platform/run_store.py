"""Run state machine row store, tenant-scoped, with an optimistic version guard.

State machine (per INTERFACES.md / MASTER-PLAN):
    draft -> queued -> running -> (succeeded | failed | timeout | cancelled)
    paper deployments:  promoted -> live -> paused -> retired

Every row carries an integer ``version`` bumped on each accepted transition.
``transition(..., expect=version)`` raises :class:`TransitionConflict` if the stored
version no longer matches — this is the optimistic concurrency guard the control plane
relies on to remain the single writer of the money path.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import Db
from .db_scope import tenant_scoped_store


class TransitionError(ValueError):
    """An illegal state transition (not allowed by the state machine)."""


class TransitionConflict(RuntimeError):
    """Optimistic version mismatch: the run changed since `expect` was read."""


class RunNotFound(KeyError):
    """No run with that id for the given tenant."""


# Allowed transitions. Keys are source states; values are the set of legal targets.
_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"queued", "cancelled"},
    "queued": {"running", "failed", "cancelled"},
    "running": {"succeeded", "failed", "timeout", "cancelled", "promoted"},
    # Terminal backtest states.
    "succeeded": {"promoted"},
    "failed": set(),
    "timeout": set(),
    "cancelled": set(),
    # Paper deployment lifecycle.
    "promoted": {"live", "retired"},
    "live": {"paused", "retired"},
    "paused": {"live", "retired"},
    "retired": set(),
}

_VALID_STATES = set(_TRANSITIONS.keys())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "tenant_id": row["tenant_id"],
        "run_id": row["run_id"],
        "kind": row["kind"],
        "strategy_id": row["strategy_id"],
        "state": row["state"],
        "version": row["version"],
        "spec": json.loads(row["spec"]) if row["spec"] else None,
        "result": json.loads(row["result"]) if row["result"] else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@tenant_scoped_store(system_methods={"claim_queued", "list_by_state"})
class RunStore:
    """The run state-machine row, tenant-scoped, optimistic-version guarded."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def create(
        self,
        tenant_id: str,
        kind: str,
        strategy_id: str | None,
        spec: dict[str, Any] | None,
    ) -> str:
        """Create a run in the initial ``draft`` state; returns its run_id (UUID str)."""
        tenant_id = str(tenant_id)
        run_id = str(uuid.uuid4())
        now = _now()
        spec_json = json.dumps(spec) if spec is not None else None
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO runs "
                    "(tenant_id, run_id, kind, strategy_id, state, version, spec, "
                    " result, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 'draft', 0, ?, NULL, ?, ?)",
                    (
                        tenant_id,
                        run_id,
                        kind,
                        str(strategy_id) if strategy_id is not None else None,
                        spec_json,
                        now,
                        now,
                    ),
                )
        return run_id

    def create_research(self, tenant_id: str) -> str:
        """Open a research-session run (kind ``research``) directly in ``running``.

        A research session is not a queued job — it has no spec to execute; it is the
        lineage a BYO agent's tool calls attach to so the observability UI can list and
        render the session. It rests in ``running`` (session active) and is closed with the
        normal ``running -> succeeded`` transition.
        """
        tenant_id = str(tenant_id)
        run_id = str(uuid.uuid4())
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO runs "
                    "(tenant_id, run_id, kind, strategy_id, state, version, spec, "
                    " result, created_at, updated_at) "
                    "VALUES (?, ?, 'research', NULL, 'running', 0, NULL, NULL, ?, ?)",
                    (tenant_id, run_id, now, now),
                )
        return run_id

    def get(self, tenant_id: str, run_id: str) -> dict[str, Any] | None:
        tenant_id = str(tenant_id)
        run_id = str(run_id)
        cur = self._db.conn.execute(
            "SELECT * FROM runs WHERE tenant_id = ? AND run_id = ?",
            (tenant_id, run_id),
        )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None

    # ---- conductor-only, CROSS-TENANT reads --------------------------------------------
    # These power the deploy-layer conductor (the queue poller / paper scheduler), which is
    # infrastructure, not a tenant request. They are NOT exposed on any tenant API; every
    # row they return carries its own ``tenant_id`` so the caller stays tenant-aware when it
    # acts on the row (the optimistic version guard on ``transition`` is the real claim).

    def claim_queued(
        self, kinds: tuple[str, ...] = ("backtest",), limit: int = 16
    ) -> list[dict[str, Any]]:
        """Return up to ``limit`` ``queued`` runs of the given kinds, oldest first.

        A pure read: the worker claims a run by winning the optimistic ``queued -> running``
        transition; a loser simply moves on. No lease column is needed for the single- or
        few-worker local deploy.
        """
        if not kinds:
            return []
        placeholders = ",".join("?" for _ in kinds)
        cur = self._db.conn.execute(
            f"SELECT * FROM runs WHERE state = 'queued' AND kind IN ({placeholders}) "
            "ORDER BY created_at ASC, run_id ASC LIMIT ?",
            (*kinds, int(limit)),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def list_by_state(
        self, state: str, kind: str | None = None, limit: int = 256
    ) -> list[dict[str, Any]]:
        """Return runs in ``state`` (optionally filtered by kind) across all tenants."""
        if kind is None:
            cur = self._db.conn.execute(
                "SELECT * FROM runs WHERE state = ? "
                "ORDER BY created_at ASC, run_id ASC LIMIT ?",
                (state, int(limit)),
            )
        else:
            cur = self._db.conn.execute(
                "SELECT * FROM runs WHERE state = ? AND kind = ? "
                "ORDER BY created_at ASC, run_id ASC LIMIT ?",
                (state, kind, int(limit)),
            )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def list(self, tenant_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        tenant_id = str(tenant_id)
        if kind is None:
            cur = self._db.conn.execute(
                "SELECT * FROM runs WHERE tenant_id = ? ORDER BY created_at ASC, run_id ASC",
                (tenant_id,),
            )
        else:
            cur = self._db.conn.execute(
                "SELECT * FROM runs WHERE tenant_id = ? AND kind = ? "
                "ORDER BY created_at ASC, run_id ASC",
                (tenant_id, kind),
            )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def transition(
        self,
        tenant_id: str,
        run_id: str,
        to_state: str,
        *,
        expect: int | None = None,
    ) -> dict[str, Any]:
        """Move a run to `to_state`, bumping version.

        - Raises :class:`RunNotFound` if the run does not exist for the tenant.
        - Raises :class:`TransitionError` if `to_state` is unknown or illegal from the
          current state.
        - Raises :class:`TransitionConflict` if `expect` is given and does not match the
          stored version (optimistic concurrency).
        """
        tenant_id = str(tenant_id)
        run_id = str(run_id)
        if to_state not in _VALID_STATES:
            raise TransitionError(f"unknown target state: {to_state!r}")

        with self._db.write_lock:
            with self._db.conn as conn:
                cur = conn.execute(
                    "SELECT state, version FROM runs WHERE tenant_id = ? AND run_id = ?",
                    (tenant_id, run_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise RunNotFound(run_id)
                current_state = row["state"]
                current_version = int(row["version"])

                if expect is not None and expect != current_version:
                    raise TransitionConflict(
                        f"version mismatch: expected {expect}, found {current_version}"
                    )

                if to_state not in _TRANSITIONS.get(current_state, set()):
                    raise TransitionError(
                        f"illegal transition {current_state!r} -> {to_state!r}"
                    )

                new_version = current_version + 1
                now = _now()
                cur = conn.execute(
                    "UPDATE runs SET state = ?, version = ?, updated_at = ? "
                    "WHERE tenant_id = ? AND run_id = ? AND state = ? AND version = ?",
                    (
                        to_state,
                        new_version,
                        now,
                        tenant_id,
                        run_id,
                        current_state,
                        current_version,
                    ),
                )
                if cur.rowcount == 0:
                    latest = conn.execute(
                        "SELECT state, version FROM runs WHERE tenant_id = ? AND run_id = ?",
                        (tenant_id, run_id),
                    ).fetchone()
                    if latest is None:
                        raise RunNotFound(run_id)
                    raise TransitionConflict(
                        f"version mismatch: expected {current_version}, "
                        f"found {int(latest['version'])}"
                    )
                updated = conn.execute(
                    "SELECT * FROM runs WHERE tenant_id = ? AND run_id = ?",
                    (tenant_id, run_id),
                ).fetchone()
        return _row_to_dict(updated)

    def set_result(
        self, tenant_id: str, run_id: str, result: dict[str, Any]
    ) -> None:
        """Attach a result payload to a run (tenant-scoped). Raises if not found."""
        tenant_id = str(tenant_id)
        run_id = str(run_id)
        result_json = json.dumps(result)
        with self._db.write_lock:
            with self._db.conn as conn:
                cur = conn.execute(
                    "UPDATE runs SET result = ?, updated_at = ? "
                    "WHERE tenant_id = ? AND run_id = ?",
                    (result_json, _now(), tenant_id, run_id),
                )
                if cur.rowcount == 0:
                    raise RunNotFound(run_id)

    def cancel(self, tenant_id: str, run_id: str, *, expect: int | None = None) -> dict[str, Any]:
        """Move a cancellable run to ``cancelled``.

        This is the durable user/API cancellation state. Workers are expected to check their
        associated job row and stop cooperatively; this run transition gives observers an
        immediate, auditable state even before a worker sees the cancel request.
        """
        return self.transition(tenant_id, run_id, "cancelled", expect=expect)
