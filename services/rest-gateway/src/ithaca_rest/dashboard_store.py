"""Bounded SQL projections used only by dashboard read models."""

from __future__ import annotations

import json
from typing import Any


def _loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _bounded_limit(limit: int, maximum: int = 500) -> int:
    return max(1, min(int(limit), maximum))


class DashboardReadStore:
    """Small, bounded projections that avoid loading full persistence rows."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def run_counts(self, tenant_id: str) -> dict[str, int]:
        rows = self._db.conn.execute(
            "SELECT state, COUNT(*) AS count FROM runs WHERE tenant_id = ? GROUP BY state",
            (str(tenant_id),),
        ).fetchall()
        return {str(row["state"]): int(row["count"]) for row in rows}

    def recent_runs(
        self,
        tenant_id: str,
        *,
        kind: str | None = None,
        state: str | None = None,
        limit: int = 20,
        with_result: bool = False,
    ) -> list[dict[str, Any]]:
        columns = "run_id, kind, strategy_id, state, created_at, updated_at" + (
            ", result" if with_result else ""
        )
        clauses = ["tenant_id = ?"]
        params: list[Any] = [str(tenant_id)]
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if state is not None:
            clauses.append("state = ?")
            params.append(state)
        if with_result:
            clauses.append("result IS NOT NULL")
        params.append(_bounded_limit(limit))
        rows = self._db.conn.execute(
            f"SELECT {columns} FROM runs WHERE "
            + " AND ".join(clauses)
            + " ORDER BY updated_at DESC, run_id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [
            {
                "run_id": row["run_id"],
                "kind": row["kind"],
                "strategy_id": row["strategy_id"],
                "state": row["state"],
                "result": _loads(row["result"], None) if with_result else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def latest_paper_book(self, tenant_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT r.run_id, r.kind, r.strategy_id, r.state, r.created_at, r.updated_at, "
            "b.capital, b.weights, b.updated_at AS book_updated_at "
            "FROM runs r JOIN books b ON b.tenant_id = r.tenant_id AND b.run_id = r.run_id "
            "WHERE r.tenant_id = ? AND r.kind = 'paper' "
            "ORDER BY b.updated_at DESC, r.run_id DESC LIMIT 1",
            (str(tenant_id),),
        ).fetchone()
        if row is None:
            return None
        return {
            "run": {
                "run_id": row["run_id"],
                "kind": row["kind"],
                "strategy_id": row["strategy_id"],
                "state": row["state"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
            "book": {
                "run_id": row["run_id"],
                "capital": row["capital"],
                "weights": _loads(row["weights"], None),
                "updated_at": row["book_updated_at"],
            },
        }

    def recent_triggers(self, tenant_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._db.conn.execute(
            "SELECT trigger_id, name, state, created_at, updated_at "
            "FROM trigger_policies WHERE tenant_id = ? "
            "ORDER BY updated_at DESC, trigger_id DESC LIMIT ?",
            (str(tenant_id), _bounded_limit(limit)),
        ).fetchall()
        return [dict(row) for row in rows]

    def recent_alerts(self, tenant_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._db.conn.execute(
            "SELECT notification_id, event_type, subject_type, subject_id, priority, state, "
            "payload, created_at, updated_at FROM notification_outbox "
            "WHERE tenant_id = ? AND state != 'acked' "
            "ORDER BY created_at DESC, notification_id DESC LIMIT ?",
            (str(tenant_id), _bounded_limit(limit)),
        ).fetchall()
        return [{**dict(row), "payload": _loads(row["payload"], {})} for row in rows]

    def provider_counts(self, tenant_id: str) -> dict[str, int]:
        row = self._db.conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN state = 'connected' THEN 1 ELSE 0 END) AS connected "
            "FROM provider_connections WHERE tenant_id = ?",
            (str(tenant_id),),
        ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "connected": int(row["connected"] or 0),
        }

    def provider_connections(self, tenant_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.conn.execute(
            "SELECT tenant_id, connection_id, provider, credential_ref, state, capabilities, "
            "entitlements, retention_policy, created_at, updated_at "
            "FROM provider_connections WHERE tenant_id = ? "
            "ORDER BY provider ASC, created_at ASC LIMIT ?",
            (str(tenant_id), _bounded_limit(limit)),
        ).fetchall()
        return [
            {
                **dict(row),
                "capabilities": _loads(row["capabilities"], []),
                "entitlements": _loads(row["entitlements"], []),
            }
            for row in rows
        ]

    def snapshots(self, tenant_id: str, *, limit: int = 25) -> list[dict[str, Any]]:
        rows = self._db.conn.execute(
            "SELECT snapshot_id, provider, dataset, entitlement_class, as_of, created_at "
            "FROM dataset_snapshots WHERE tenant_id = ? "
            "ORDER BY as_of DESC, created_at DESC LIMIT ?",
            (str(tenant_id), _bounded_limit(limit)),
        ).fetchall()
        return [dict(row) for row in rows]
