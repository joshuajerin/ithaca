"""Durable cross-process leadership leases.

The queue has per-job worker leases. This store covers singleton background loops
such as trigger policy polling and paper deployment scheduling. It uses an
explicit row version and conditional upsert so the same implementation works for
local SQLite and production Postgres.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import Db


class LeaseConflict(RuntimeError):
    """Another worker currently owns the lease."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    return json.loads(raw)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "lease_name": row["lease_name"],
        "owner_id": row["owner_id"],
        "lease_expires_at": row["lease_expires_at"],
        "heartbeat_at": row["heartbeat_at"],
        "metadata": _loads(row["metadata"], {}),
        "version": int(row["version"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class LeaseStore:
    """Small compare-and-set lease store for active infrastructure loops."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def get(self, lease_name: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM worker_leases WHERE lease_name = ?",
            (str(lease_name),),
        ).fetchone()
        return _row_to_dict(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        rows = self._db.conn.execute(
            "SELECT * FROM worker_leases ORDER BY lease_name ASC"
        ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def acquire(
        self,
        lease_name: str,
        owner_id: str,
        *,
        ttl_seconds: float = 30.0,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Acquire or renew a lease.

        Returns the owned lease row on success, or ``None`` when another owner
        holds an unexpired lease. The conflict path is deliberately non-throwing
        so active loops can skip one tick without noisy logs.
        """
        lease_name = str(lease_name)
        owner_id = str(owner_id)
        now_dt = now or _now()
        now_s = _iso(now_dt)
        expires_s = _iso(now_dt + timedelta(seconds=max(1.0, float(ttl_seconds))))
        metadata_json = json.dumps(metadata or {})

        with self._db.write_lock:
            with self._db.conn as conn:
                cur = conn.execute(
                    "INSERT INTO worker_leases "
                    "(lease_name, owner_id, lease_expires_at, heartbeat_at, metadata, "
                    " version, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 0, ?, ?) "
                    "ON CONFLICT(lease_name) DO UPDATE SET "
                    "owner_id = excluded.owner_id, "
                    "lease_expires_at = excluded.lease_expires_at, "
                    "heartbeat_at = excluded.heartbeat_at, "
                    "metadata = excluded.metadata, "
                    "version = worker_leases.version + 1, "
                    "updated_at = excluded.updated_at "
                    "WHERE worker_leases.owner_id = excluded.owner_id "
                    "OR worker_leases.lease_expires_at <= ?",
                    (
                        lease_name,
                        owner_id,
                        expires_s,
                        now_s,
                        metadata_json,
                        now_s,
                        now_s,
                        now_s,
                    ),
                )
                if cur.rowcount == 0:
                    return None
                row = conn.execute(
                    "SELECT * FROM worker_leases WHERE lease_name = ?",
                    (lease_name,),
                ).fetchone()
        return _row_to_dict(row)

    def heartbeat(
        self,
        lease_name: str,
        owner_id: str,
        *,
        ttl_seconds: float = 30.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        lease = self.acquire(
            lease_name,
            owner_id,
            ttl_seconds=ttl_seconds,
            metadata=metadata,
        )
        if lease is None:
            raise LeaseConflict(f"lease is owned by another worker: {lease_name}")
        return lease

    def release(self, lease_name: str, owner_id: str) -> bool:
        """Release a lease only if ``owner_id`` is still the current owner."""
        with self._db.write_lock:
            with self._db.conn as conn:
                cur = conn.execute(
                    "DELETE FROM worker_leases WHERE lease_name = ? AND owner_id = ?",
                    (str(lease_name), str(owner_id)),
                )
        return bool(cur.rowcount)
