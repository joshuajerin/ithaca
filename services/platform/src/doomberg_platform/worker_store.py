"""Durable worker-process heartbeats used by readiness and operator surfaces."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import Db
from .db_scope import system_scoped_store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _row(row: Any) -> dict[str, Any]:
    return {
        "worker_id": row["worker_id"],
        "role": row["role"],
        "status": row["status"],
        "detail": row["detail"],
        "metadata": json.loads(row["metadata"] or "{}"),
        "started_at": row["started_at"],
        "heartbeat_at": row["heartbeat_at"],
        "expires_at": row["expires_at"],
        "updated_at": row["updated_at"],
    }


@system_scoped_store
class WorkerHeartbeatStore:
    """Current process-role heartbeats; expired rows remain visible for diagnosis."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def heartbeat(
        self,
        worker_id: str,
        role: str,
        *,
        ttl_seconds: float = 30.0,
        status: str = "healthy",
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        worker_id = str(worker_id).strip()
        role = str(role).strip()
        status = str(status).strip().lower()
        if not worker_id or not role:
            raise ValueError("worker_id and role are required")
        if status not in {"starting", "healthy", "standby", "degraded", "stopped"}:
            raise ValueError(f"invalid worker heartbeat status: {status}")
        now_dt = now or _now()
        now_s = _iso(now_dt)
        expires_s = _iso(now_dt + timedelta(seconds=max(1.0, float(ttl_seconds))))
        payload = json.dumps(metadata or {}, sort_keys=True)
        with self._db.write_lock:
            with self._db.conn as conn:
                row = conn.execute(
                    "INSERT INTO worker_heartbeats "
                    "(worker_id, role, status, detail, metadata, started_at, heartbeat_at, "
                    " expires_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(worker_id, role) DO UPDATE SET status = excluded.status, "
                    "detail = excluded.detail, metadata = excluded.metadata, "
                    "heartbeat_at = excluded.heartbeat_at, expires_at = excluded.expires_at, "
                    "updated_at = excluded.updated_at RETURNING *",
                    (
                        worker_id,
                        role,
                        status,
                        str(detail)[:500] if detail else None,
                        payload,
                        now_s,
                        now_s,
                        expires_s,
                        now_s,
                    ),
                ).fetchone()
        return _row(row)

    def stop(
        self, worker_id: str, role: str, *, detail: str | None = None
    ) -> dict[str, Any] | None:
        now_s = _iso(_now())
        with self._db.write_lock:
            with self._db.conn as conn:
                row = conn.execute(
                    "UPDATE worker_heartbeats SET status = 'stopped', detail = ?, "
                    "heartbeat_at = ?, expires_at = ?, updated_at = ? "
                    "WHERE worker_id = ? AND role = ? RETURNING *",
                    (detail, now_s, now_s, now_s, str(worker_id), str(role)),
                ).fetchone()
        return _row(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        rows = self._db.conn.execute(
            "SELECT * FROM worker_heartbeats ORDER BY role, worker_id"
        ).fetchall()
        return [_row(row) for row in rows]
