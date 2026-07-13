"""Durable job and worker-lease store.

Runs are the user-facing audit object. Jobs are the worker-facing execution object:
profile, payload, lease owner, heartbeat, checkpoint, attempts, idempotency, and terminal
state. SQLite handles local/dev, while the Postgres adapter uses row locks for production
worker leases.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import Db
from .job_profiles import admission_metadata, get_job_profile

TERMINAL_STATES = {"succeeded", "failed", "cancelled", "timed_out"}


class JobNotFound(KeyError):
    """No job exists for the given tenant/id."""


class JobConflict(RuntimeError):
    """The job cannot transition because ownership/state changed."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    return json.loads(raw)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "tenant_id": row["tenant_id"],
        "job_id": row["job_id"],
        "run_id": row["run_id"],
        "kind": row["kind"],
        "profile": row["profile"],
        "state": row["state"],
        "payload": _loads(row["payload"], {}),
        "idempotency_key": row["idempotency_key"],
        "attempts": int(row["attempts"]),
        "max_attempts": int(row["max_attempts"]),
        "worker_id": row["worker_id"],
        "lease_expires_at": row["lease_expires_at"],
        "heartbeat_at": row["heartbeat_at"],
        "checkpoint_ref": row["checkpoint_ref"],
        "result": _loads(row["result"], None),
        "error": _loads(row["error"], None),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class JobStore:
    """Durable worker queue with leases and idempotent enqueue."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def create_for_run(
        self,
        tenant_id: str,
        run_id: str,
        *,
        kind: str,
        profile: str,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        """Create a queued job, or return the existing job for an idempotency key."""
        tenant_id = str(tenant_id)
        run_id = str(run_id)
        if idempotency_key:
            existing = self.get_by_idempotency(tenant_id, idempotency_key)
            if existing is not None:
                return existing

        profile_manifest = get_job_profile(profile)
        profile = profile_manifest.name
        job_id = str(uuid.uuid4())
        now = _now()
        payload_with_admission = dict(payload or {})
        payload_with_admission.setdefault("admission", admission_metadata(profile))
        payload_json = json.dumps(payload_with_admission)
        with self._db.write_lock:
            with self._db.conn as conn:
                try:
                    conn.execute(
                        "INSERT INTO jobs "
                        "(tenant_id, job_id, run_id, kind, profile, state, payload, "
                        " idempotency_key, attempts, max_attempts, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, 0, ?, ?, ?)",
                        (
                            tenant_id,
                            job_id,
                            run_id,
                            kind,
                            profile,
                            payload_json,
                            idempotency_key,
                            int(max_attempts),
                            now,
                            now,
                        ),
                    )
                except Exception:
                    if idempotency_key:
                        existing = self.get_by_idempotency(tenant_id, idempotency_key)
                        if existing is not None:
                            return existing
                    raise
        return self.get(tenant_id, job_id)

    def get(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        cur = self._db.conn.execute(
            "SELECT * FROM jobs WHERE tenant_id = ? AND job_id = ?",
            (str(tenant_id), str(job_id)),
        )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None

    def get_by_idempotency(self, tenant_id: str, idempotency_key: str) -> dict[str, Any] | None:
        cur = self._db.conn.execute(
            "SELECT * FROM jobs WHERE tenant_id = ? AND idempotency_key = ?",
            (str(tenant_id), str(idempotency_key)),
        )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None

    def list_by_run(self, tenant_id: str, run_id: str) -> list[dict[str, Any]]:
        cur = self._db.conn.execute(
            "SELECT * FROM jobs WHERE tenant_id = ? AND run_id = ? ORDER BY created_at ASC",
            (str(tenant_id), str(run_id)),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def list(
        self,
        tenant_id: str,
        *,
        run_id: str | None = None,
        state: str | None = None,
        profile: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["tenant_id = ?"]
        params: list[Any] = [str(tenant_id)]
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(str(run_id))
        if state is not None:
            clauses.append("state = ?")
            params.append(str(state))
        if profile is not None:
            clauses.append("profile = ?")
            params.append(str(profile))
        params.append(max(1, min(int(limit), 500)))
        cur = self._db.conn.execute(
            "SELECT * FROM jobs WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC, job_id DESC LIMIT ?",
            tuple(params),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def claim_available(
        self,
        *,
        profiles: tuple[str, ...] = ("backtest",),
        kinds: tuple[str, ...] = ("backtest",),
        worker_id: str | None = None,
        lease_seconds: int = 60,
        limit: int = 16,
    ) -> list[dict[str, Any]]:
        """Lease queued or expired jobs for a worker.

        SQLite uses the local write lock. Postgres uses row locks with
        ``FOR UPDATE SKIP LOCKED`` so multiple workers cannot lease the same job.
        """
        if not profiles or not kinds:
            return []
        worker_id = worker_id or f"worker-{uuid.uuid4().hex[:12]}"
        now = _now()
        lease_until = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat()
        profile_marks = ",".join("?" for _ in profiles)
        kind_marks = ",".join("?" for _ in kinds)
        with self._db.write_lock:
            with self._db.conn as conn:
                lock_clause = " FOR UPDATE SKIP LOCKED" if getattr(self._db, "is_postgres", False) else ""
                rows = conn.execute(
                    f"SELECT * FROM jobs "
                    f"WHERE profile IN ({profile_marks}) AND kind IN ({kind_marks}) "
                    "AND attempts < max_attempts "
                    "AND (state = 'queued' OR "
                    "     (state IN ('leased', 'running') AND lease_expires_at IS NOT NULL "
                    "      AND lease_expires_at <= ?)) "
                    "ORDER BY created_at ASC, job_id ASC LIMIT ?"
                    f"{lock_clause}",
                    (*profiles, *kinds, now, int(limit)),
                ).fetchall()
                leased: list[dict[str, Any]] = []
                for row in rows:
                    conn.execute(
                        "UPDATE jobs SET state = 'leased', attempts = attempts + 1, "
                        "worker_id = ?, lease_expires_at = ?, heartbeat_at = ?, updated_at = ? "
                        "WHERE tenant_id = ? AND job_id = ?",
                        (
                            worker_id,
                            lease_until,
                            now,
                            now,
                            row["tenant_id"],
                            row["job_id"],
                        ),
                    )
                    leased.append(self.get(row["tenant_id"], row["job_id"]))
        return [j for j in leased if j is not None]

    def fail_exhausted(
        self,
        *,
        profiles: tuple[str, ...] = ("backtest",),
        kinds: tuple[str, ...] = ("backtest",),
    ) -> list[dict[str, Any]]:
        """Fail expired leases that consumed every retry instead of stranding them forever."""
        if not profiles or not kinds:
            return []
        now = _now()
        profile_marks = ",".join("?" for _ in profiles)
        kind_marks = ",".join("?" for _ in kinds)
        with self._db.write_lock:
            with self._db.conn as conn:
                lock_clause = " FOR UPDATE SKIP LOCKED" if getattr(self._db, "is_postgres", False) else ""
                rows = conn.execute(
                    f"SELECT tenant_id, job_id FROM jobs "
                    f"WHERE profile IN ({profile_marks}) AND kind IN ({kind_marks}) "
                    "AND state IN ('leased', 'running') AND attempts >= max_attempts "
                    "AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?"
                    f"{lock_clause}",
                    (*profiles, *kinds, now),
                ).fetchall()
                for row in rows:
                    conn.execute(
                        "UPDATE jobs SET state = 'failed', error = ?, updated_at = ? "
                        "WHERE tenant_id = ? AND job_id = ?",
                        (
                            json.dumps(
                                {
                                    "code": "RETRY_EXHAUSTED",
                                    "detail": "worker lease expired after maximum attempts",
                                }
                            ),
                            now,
                            row["tenant_id"],
                            row["job_id"],
                        ),
                    )
        return [
            job
            for row in rows
            if (job := self.get(row["tenant_id"], row["job_id"])) is not None
        ]

    def mark_running(self, tenant_id: str, job_id: str, *, worker_id: str | None = None) -> dict[str, Any]:
        return self._update_state(tenant_id, job_id, "running", worker_id=worker_id)

    def heartbeat(
        self,
        tenant_id: str,
        job_id: str,
        *,
        worker_id: str | None = None,
        lease_seconds: int = 60,
        checkpoint_ref: str | None = None,
    ) -> dict[str, Any]:
        tenant_id = str(tenant_id)
        job_id = str(job_id)
        now = _now()
        lease_until = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat()
        with self._db.write_lock:
            with self._db.conn as conn:
                row = conn.execute(
                    "SELECT * FROM jobs WHERE tenant_id = ? AND job_id = ?",
                    (tenant_id, job_id),
                ).fetchone()
                if row is None:
                    raise JobNotFound(job_id)
                if row["state"] in TERMINAL_STATES:
                    raise JobConflict(f"job is terminal: {row['state']}")
                if worker_id is not None and row["worker_id"] not in {None, worker_id}:
                    raise JobConflict("job is leased by another worker")
                conn.execute(
                    "UPDATE jobs SET state = CASE WHEN state = 'leased' THEN 'running' ELSE state END, "
                    "worker_id = COALESCE(worker_id, ?), lease_expires_at = ?, heartbeat_at = ?, "
                    "checkpoint_ref = COALESCE(?, checkpoint_ref), updated_at = ? "
                    "WHERE tenant_id = ? AND job_id = ?",
                    (worker_id, lease_until, now, checkpoint_ref, now, tenant_id, job_id),
                )
        return self.get(tenant_id, job_id)

    def complete(
        self,
        tenant_id: str,
        job_id: str,
        *,
        worker_id: str | None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._update_state(
            tenant_id,
            job_id,
            "succeeded",
            worker_id=worker_id,
            result=result or {},
            require_worker=True,
        )

    def fail(
        self,
        tenant_id: str,
        job_id: str,
        *,
        worker_id: str | None,
        error: dict[str, Any],
    ) -> dict[str, Any]:
        return self._update_state(
            tenant_id,
            job_id,
            "failed",
            worker_id=worker_id,
            error=error,
            require_worker=True,
        )

    def time_out(
        self,
        tenant_id: str,
        job_id: str,
        *,
        worker_id: str | None,
        error: dict[str, Any],
    ) -> dict[str, Any]:
        return self._update_state(
            tenant_id,
            job_id,
            "timed_out",
            worker_id=worker_id,
            error=error,
            require_worker=True,
        )

    def cancel(self, tenant_id: str, job_id: str, *, reason: str | None = None) -> dict[str, Any]:
        return self._update_state(
            tenant_id,
            job_id,
            "cancelled",
            error={"code": "CANCELLED", "detail": reason},
        )

    def cancel_by_run(self, tenant_id: str, run_id: str, *, reason: str | None = None) -> list[dict[str, Any]]:
        jobs = self.list_by_run(tenant_id, run_id)
        cancelled: list[dict[str, Any]] = []
        for job in jobs:
            if job["state"] not in TERMINAL_STATES:
                cancelled.append(self.cancel(tenant_id, job["job_id"], reason=reason))
        return cancelled

    def should_cancel(self, tenant_id: str, job_id: str) -> bool:
        job = self.get(tenant_id, job_id)
        return bool(job and job["state"] == "cancelled")

    def _update_state(
        self,
        tenant_id: str,
        job_id: str,
        state: str,
        *,
        worker_id: str | None = None,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        require_worker: bool = False,
    ) -> dict[str, Any]:
        tenant_id = str(tenant_id)
        job_id = str(job_id)
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                row = conn.execute(
                    "SELECT * FROM jobs WHERE tenant_id = ? AND job_id = ?",
                    (tenant_id, job_id),
                ).fetchone()
                if row is None:
                    raise JobNotFound(job_id)
                if row["state"] in TERMINAL_STATES and row["state"] != state:
                    raise JobConflict(f"job is terminal: {row['state']}")
                if require_worker:
                    if not worker_id:
                        raise JobConflict("worker_id is required for terminal job writes")
                    if row["state"] not in {"leased", "running"}:
                        raise JobConflict(f"job must be leased/running before {state}: {row['state']}")
                    if row["worker_id"] != worker_id:
                        raise JobConflict("job is leased by another worker")
                elif worker_id is not None and row["worker_id"] not in {None, worker_id}:
                    raise JobConflict("job is leased by another worker")
                conn.execute(
                    "UPDATE jobs SET state = ?, worker_id = COALESCE(?, worker_id), "
                    "result = COALESCE(?, result), error = COALESCE(?, error), "
                    "updated_at = ? WHERE tenant_id = ? AND job_id = ?",
                    (
                        state,
                        worker_id,
                        json.dumps(result) if result is not None else None,
                        json.dumps(error) if error is not None else None,
                        now,
                        tenant_id,
                        job_id,
                    ),
                )
        updated = self.get(tenant_id, job_id)
        if updated is None:
            raise JobNotFound(job_id)
        return updated
