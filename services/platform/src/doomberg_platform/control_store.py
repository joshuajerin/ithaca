"""Support stores for control-plane observability and governance.

This module intentionally keeps simple CRUD-style records together while the product surface
is still forming. Each method is tenant-scoped and returns plain dicts so REST, MCP, and UI
layers can adopt the same durable rows without importing transport-specific models.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import Db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    return json.loads(raw)


def _trigger_state(state: str) -> str:
    state = str(state).strip().lower()
    if state == "archived":
        return "retired"
    if state not in {"draft", "active", "paused", "retired"}:
        raise ValueError("state must be draft, active, paused, or retired")
    return state


def _notification_state(state: str) -> str:
    state = str(state).strip().lower()
    if state == "open":
        return "open"
    if state not in {"queued", "sending", "sent", "partial", "failed", "acked"}:
        raise ValueError("state must be queued, sending, sent, partial, failed, or acked")
    return state


def _target_state(state: str) -> str:
    state = str(state).strip().lower()
    if state not in {"active", "paused", "retired"}:
        raise ValueError("state must be active, paused, or retired")
    return state


def _order_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "tenant_id": row["tenant_id"],
        "order_id": row["order_id"],
        "intent_id": row["intent_id"],
        "broker": row["broker"],
        "broker_order_id": row["broker_order_id"],
        "client_order_id": row["client_order_id"],
        "state": row["state"],
        "payload": _loads(row["payload"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _fill_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "tenant_id": row["tenant_id"],
        "fill_id": row["fill_id"],
        "order_id": row["order_id"],
        "broker_fill_id": row["broker_fill_id"],
        "payload": _loads(row["payload"], {}),
        "event_time": row["event_time"],
        "created_at": row["created_at"],
    }


class ArtifactStore:
    def __init__(self, db: Db) -> None:
        self._db = db

    def create(
        self,
        tenant_id: str,
        run_id: str,
        *,
        kind: str,
        uri: str,
        job_id: str | None = None,
        media_type: str | None = None,
        bytes_: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact_id = str(uuid.uuid4())
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO artifacts "
                    "(tenant_id, artifact_id, run_id, job_id, kind, uri, media_type, bytes, "
                    " metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(tenant_id),
                        artifact_id,
                        str(run_id),
                        str(job_id) if job_id is not None else None,
                        kind,
                        uri,
                        media_type,
                        bytes_,
                        json.dumps(metadata or {}),
                        now,
                    ),
                )
        return self.get(tenant_id, artifact_id)

    def get(self, tenant_id: str, artifact_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM artifacts WHERE tenant_id = ? AND artifact_id = ?",
            (str(tenant_id), str(artifact_id)),
        ).fetchone()
        if row is None:
            return None
        return {
            "tenant_id": row["tenant_id"],
            "artifact_id": row["artifact_id"],
            "run_id": row["run_id"],
            "job_id": row["job_id"],
            "kind": row["kind"],
            "uri": row["uri"],
            "media_type": row["media_type"],
            "bytes": row["bytes"],
            "metadata": _loads(row["metadata"], {}),
            "created_at": row["created_at"],
        }

    def list_by_run(self, tenant_id: str, run_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn.execute(
            "SELECT * FROM artifacts WHERE tenant_id = ? AND run_id = ? ORDER BY created_at ASC",
            (str(tenant_id), str(run_id)),
        ).fetchall()
        return [a for r in rows if (a := self.get(str(tenant_id), r["artifact_id"])) is not None]

    def list(
        self,
        tenant_id: str,
        *,
        run_id: str | None = None,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["tenant_id = ?"]
        params: list[Any] = [str(tenant_id)]
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(str(run_id))
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.conn.execute(
            "SELECT artifact_id FROM artifacts WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC, artifact_id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [a for r in rows if (a := self.get(str(tenant_id), r["artifact_id"])) is not None]


class ApprovalStore:
    def __init__(self, db: Db) -> None:
        self._db = db

    def create(
        self,
        tenant_id: str,
        run_id: str,
        *,
        kind: str,
        request: dict[str, Any],
        requested_by: str | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        approval_id = str(uuid.uuid4())
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO approvals "
                    "(tenant_id, approval_id, run_id, kind, state, request, requested_by, "
                    " expires_at, created_at, updated_at) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)",
                    (
                        str(tenant_id),
                        approval_id,
                        str(run_id),
                        kind,
                        json.dumps(request),
                        requested_by,
                        expires_at,
                        now,
                        now,
                    ),
                )
        return self.get(tenant_id, approval_id)

    def get(self, tenant_id: str, approval_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM approvals WHERE tenant_id = ? AND approval_id = ?",
            (str(tenant_id), str(approval_id)),
        ).fetchone()
        if row is None:
            return None
        return {
            "tenant_id": row["tenant_id"],
            "approval_id": row["approval_id"],
            "run_id": row["run_id"],
            "kind": row["kind"],
            "state": row["state"],
            "request": _loads(row["request"], {}),
            "decision": _loads(row["decision"], None),
            "requested_by": row["requested_by"],
            "decided_by": row["decided_by"],
            "expires_at": row["expires_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_pending(self, tenant_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn.execute(
            "SELECT approval_id FROM approvals WHERE tenant_id = ? AND state = 'pending' "
            "ORDER BY created_at ASC",
            (str(tenant_id),),
        ).fetchall()
        return [a for r in rows if (a := self.get(str(tenant_id), r["approval_id"])) is not None]

    def list(
        self,
        tenant_id: str,
        *,
        run_id: str | None = None,
        state: str | None = None,
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
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.conn.execute(
            "SELECT approval_id FROM approvals WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC, approval_id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [a for r in rows if (a := self.get(str(tenant_id), r["approval_id"])) is not None]

    def decide(
        self,
        tenant_id: str,
        approval_id: str,
        *,
        decision: str,
        decided_by: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if decision not in {"approved", "denied"}:
            raise ValueError("decision must be 'approved' or 'denied'")
        now = _now()
        decision_body = {"decision": decision, "reason": reason, "decided_at": now}
        with self._db.write_lock:
            with self._db.conn as conn:
                cur = conn.execute(
                    "UPDATE approvals SET state = ?, decision = ?, decided_by = ?, updated_at = ? "
                    "WHERE tenant_id = ? AND approval_id = ? AND state = 'pending'",
                    (
                        decision,
                        json.dumps(decision_body),
                        decided_by,
                        now,
                        str(tenant_id),
                        str(approval_id),
                    ),
                )
                if cur.rowcount == 0:
                    raise KeyError(approval_id)
        return self.get(tenant_id, approval_id)


class ProviderStore:
    def __init__(self, db: Db) -> None:
        self._db = db

    def upsert_connection(
        self,
        tenant_id: str,
        *,
        provider: str,
        capabilities: list[str] | None = None,
        entitlements: list[dict[str, Any]] | None = None,
        state: str = "connected",
        connection_id: str | None = None,
        account_ref: str | None = None,
        credential_ref: str | None = None,
        retention_policy: str | None = None,
    ) -> dict[str, Any]:
        connection_id = connection_id or str(uuid.uuid4())
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO provider_connections "
                    "(tenant_id, connection_id, provider, account_ref, credential_ref, state, "
                    " capabilities, entitlements, retention_policy, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(tenant_id, connection_id) DO UPDATE SET "
                    "provider = excluded.provider, account_ref = excluded.account_ref, "
                    "credential_ref = excluded.credential_ref, state = excluded.state, "
                    "capabilities = excluded.capabilities, entitlements = excluded.entitlements, "
                    "retention_policy = excluded.retention_policy, updated_at = excluded.updated_at",
                    (
                        str(tenant_id),
                        connection_id,
                        provider,
                        account_ref,
                        credential_ref,
                        state,
                        json.dumps(capabilities or []),
                        json.dumps(entitlements or []),
                        retention_policy,
                        now,
                        now,
                    ),
                )
        return self.get_connection(tenant_id, connection_id)

    def get_connection(self, tenant_id: str, connection_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM provider_connections WHERE tenant_id = ? AND connection_id = ?",
            (str(tenant_id), str(connection_id)),
        ).fetchone()
        if row is None:
            return None
        return {
            "tenant_id": row["tenant_id"],
            "connection_id": row["connection_id"],
            "provider": row["provider"],
            "account_ref": row["account_ref"],
            "credential_ref": row["credential_ref"],
            "state": row["state"],
            "capabilities": _loads(row["capabilities"], []),
            "entitlements": _loads(row["entitlements"], []),
            "retention_policy": row["retention_policy"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_connections(self, tenant_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn.execute(
            "SELECT connection_id FROM provider_connections WHERE tenant_id = ? "
            "ORDER BY provider ASC, created_at ASC",
            (str(tenant_id),),
        ).fetchall()
        return [c for r in rows if (c := self.get_connection(str(tenant_id), r["connection_id"])) is not None]

    def create_snapshot(
        self,
        tenant_id: str,
        *,
        provider: str,
        dataset: str,
        entitlement_class: str,
        as_of: str,
        manifest: dict[str, Any],
        uri: str | None = None,
    ) -> dict[str, Any]:
        snapshot_id = str(uuid.uuid4())
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO dataset_snapshots "
                    "(tenant_id, snapshot_id, provider, dataset, entitlement_class, as_of, uri, "
                    " manifest, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(tenant_id),
                        snapshot_id,
                        provider,
                        dataset,
                        entitlement_class,
                        as_of,
                        uri,
                        json.dumps(manifest),
                        now,
                    ),
                )
        return self.get_snapshot(tenant_id, snapshot_id)

    def get_snapshot(self, tenant_id: str, snapshot_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM dataset_snapshots WHERE tenant_id = ? AND snapshot_id = ?",
            (str(tenant_id), str(snapshot_id)),
        ).fetchone()
        if row is None:
            return None
        return {
            "tenant_id": row["tenant_id"],
            "snapshot_id": row["snapshot_id"],
            "provider": row["provider"],
            "dataset": row["dataset"],
            "entitlement_class": row["entitlement_class"],
            "as_of": row["as_of"],
            "uri": row["uri"],
            "manifest": _loads(row["manifest"], {}),
            "created_at": row["created_at"],
        }

    def list_snapshots(
        self,
        tenant_id: str,
        *,
        provider: str | None = None,
        dataset: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["tenant_id = ?"]
        params: list[Any] = [str(tenant_id)]
        if provider is not None:
            clauses.append("provider = ?")
            params.append(provider)
        if dataset is not None:
            clauses.append("dataset = ?")
            params.append(dataset)
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.conn.execute(
            "SELECT snapshot_id FROM dataset_snapshots WHERE "
            + " AND ".join(clauses)
            + " ORDER BY as_of DESC, created_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [s for r in rows if (s := self.get_snapshot(str(tenant_id), r["snapshot_id"])) is not None]


class ExecutionStore:
    def __init__(self, db: Db) -> None:
        self._db = db

    def create_order_intent(
        self,
        tenant_id: str,
        run_id: str,
        *,
        payload: dict[str, Any],
        strategy_id: str | None = None,
        account_ref: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if idempotency_key:
            existing = self.get_intent_by_idempotency(tenant_id, idempotency_key)
            if existing is not None:
                return existing
        intent_id = str(uuid.uuid4())
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO order_intents "
                    "(tenant_id, intent_id, run_id, strategy_id, account_ref, state, payload, "
                    " idempotency_key, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'proposed', ?, ?, ?, ?)",
                    (
                        str(tenant_id),
                        intent_id,
                        str(run_id),
                        strategy_id,
                        account_ref,
                        json.dumps(payload),
                        idempotency_key,
                        now,
                        now,
                    ),
                )
        return self.get_intent(tenant_id, intent_id)

    def get_intent(self, tenant_id: str, intent_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM order_intents WHERE tenant_id = ? AND intent_id = ?",
            (str(tenant_id), str(intent_id)),
        ).fetchone()
        if row is None:
            return None
        return {
            "tenant_id": row["tenant_id"],
            "intent_id": row["intent_id"],
            "run_id": row["run_id"],
            "strategy_id": row["strategy_id"],
            "account_ref": row["account_ref"],
            "state": row["state"],
            "payload": _loads(row["payload"], {}),
            "risk_decision": _loads(row["risk_decision"], None),
            "idempotency_key": row["idempotency_key"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_record(self, tenant_id: str, intent_id: str) -> dict[str, Any] | None:
        intent = self.get_intent(tenant_id, intent_id)
        if intent is None:
            return None
        orders = self.list_orders(tenant_id, intent_id=intent_id)
        fills: list[dict[str, Any]] = []
        for order in orders:
            fills.extend(self.list_fills(tenant_id, order_id=order["order_id"]))
        return {**intent, "orders": orders, "fills": fills}

    def get_intent_by_idempotency(self, tenant_id: str, idempotency_key: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT intent_id FROM order_intents WHERE tenant_id = ? AND idempotency_key = ?",
            (str(tenant_id), str(idempotency_key)),
        ).fetchone()
        return self.get_intent(tenant_id, row["intent_id"]) if row else None

    def list_intents(
        self,
        tenant_id: str,
        *,
        run_id: str | None = None,
        state: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["tenant_id = ?"]
        params: list[Any] = [str(tenant_id)]
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(str(run_id))
        if state is not None:
            clauses.append("state = ?")
            params.append(state)
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.conn.execute(
            "SELECT intent_id FROM order_intents WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC, intent_id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [i for r in rows if (i := self.get_intent(str(tenant_id), r["intent_id"])) is not None]

    def set_intent_state(
        self,
        tenant_id: str,
        intent_id: str,
        *,
        state: str,
        risk_decision: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                cur = conn.execute(
                    "UPDATE order_intents SET state = ?, "
                    "risk_decision = COALESCE(?, risk_decision), updated_at = ? "
                    "WHERE tenant_id = ? AND intent_id = ?",
                    (
                        state,
                        json.dumps(risk_decision) if risk_decision is not None else None,
                        now,
                        str(tenant_id),
                        str(intent_id),
                    ),
                )
                if cur.rowcount == 0:
                    raise KeyError(intent_id)
        intent = self.get_intent(tenant_id, intent_id)
        if intent is None:
            raise KeyError(intent_id)
        return intent

    def create_order(
        self,
        tenant_id: str,
        intent_id: str,
        *,
        broker: str,
        client_order_id: str,
        payload: dict[str, Any],
        state: str = "submitted",
        broker_order_id: str | None = None,
    ) -> dict[str, Any]:
        existing = self.get_order_by_client_order_id(tenant_id, broker, client_order_id)
        if existing is not None:
            return existing
        order_id = str(uuid.uuid4())
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                try:
                    conn.execute(
                        "INSERT INTO orders "
                        "(tenant_id, order_id, intent_id, broker, broker_order_id, client_order_id, "
                        "state, payload, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(tenant_id),
                            order_id,
                            str(intent_id),
                            broker,
                            broker_order_id,
                            client_order_id,
                            state,
                            json.dumps(payload),
                            now,
                            now,
                        ),
                    )
                except Exception:
                    existing = self.get_order_by_client_order_id(tenant_id, broker, client_order_id)
                    if existing is not None:
                        return existing
                    raise
        order = self.get_order(tenant_id, order_id)
        if order is None:
            raise KeyError(order_id)
        return order

    def get_order(self, tenant_id: str, order_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM orders WHERE tenant_id = ? AND order_id = ?",
            (str(tenant_id), str(order_id)),
        ).fetchone()
        return _order_row_to_dict(row) if row else None

    def get_order_by_client_order_id(
        self, tenant_id: str, broker: str, client_order_id: str
    ) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM orders WHERE tenant_id = ? AND broker = ? AND client_order_id = ?",
            (str(tenant_id), broker, client_order_id),
        ).fetchone()
        return _order_row_to_dict(row) if row else None

    def list_orders(
        self,
        tenant_id: str,
        *,
        intent_id: str | None = None,
        state: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["tenant_id = ?"]
        params: list[Any] = [str(tenant_id)]
        if intent_id is not None:
            clauses.append("intent_id = ?")
            params.append(str(intent_id))
        if state is not None:
            clauses.append("state = ?")
            params.append(state)
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.conn.execute(
            "SELECT * FROM orders WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at ASC, order_id ASC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [_order_row_to_dict(row) for row in rows]

    def set_order_state(
        self,
        tenant_id: str,
        order_id: str,
        *,
        state: str,
        broker_order_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.get_order(tenant_id, order_id)
        if current is None:
            raise KeyError(order_id)
        merged_payload = dict(current["payload"])
        if payload is not None:
            merged_payload.update(payload)
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "UPDATE orders SET state = ?, broker_order_id = COALESCE(?, broker_order_id), "
                    "payload = ?, updated_at = ? WHERE tenant_id = ? AND order_id = ?",
                    (
                        state,
                        broker_order_id,
                        json.dumps(merged_payload),
                        now,
                        str(tenant_id),
                        str(order_id),
                    ),
                )
        order = self.get_order(tenant_id, order_id)
        if order is None:
            raise KeyError(order_id)
        return order

    def create_fill(
        self,
        tenant_id: str,
        order_id: str,
        *,
        payload: dict[str, Any],
        event_time: str,
        broker_fill_id: str | None = None,
    ) -> dict[str, Any]:
        fill_id = str(uuid.uuid4())
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO fills "
                    "(tenant_id, fill_id, order_id, broker_fill_id, payload, event_time, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(tenant_id),
                        fill_id,
                        str(order_id),
                        broker_fill_id,
                        json.dumps(payload),
                        event_time,
                        now,
                    ),
                )
        fill = self.get_fill(tenant_id, fill_id)
        if fill is None:
            raise KeyError(fill_id)
        return fill

    def get_fill(self, tenant_id: str, fill_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM fills WHERE tenant_id = ? AND fill_id = ?",
            (str(tenant_id), str(fill_id)),
        ).fetchone()
        return _fill_row_to_dict(row) if row else None

    def list_fills(
        self,
        tenant_id: str,
        *,
        order_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["tenant_id = ?"]
        params: list[Any] = [str(tenant_id)]
        if order_id is not None:
            clauses.append("order_id = ?")
            params.append(str(order_id))
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.conn.execute(
            "SELECT * FROM fills WHERE "
            + " AND ".join(clauses)
            + " ORDER BY event_time ASC, created_at ASC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [_fill_row_to_dict(row) for row in rows]


class TriggerStore:
    def __init__(self, db: Db) -> None:
        self._db = db

    def create(
        self,
        tenant_id: str,
        *,
        name: str,
        policy: dict[str, Any],
        state: str = "draft",
        trigger_id: str | None = None,
    ) -> dict[str, Any]:
        state = _trigger_state(state)
        trigger_id = trigger_id or str(uuid.uuid4())
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO trigger_policies "
                    "(tenant_id, trigger_id, name, state, policy, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(tenant_id), trigger_id, name, state, json.dumps(policy), now, now),
                )
        return self.get(tenant_id, trigger_id)

    def get(self, tenant_id: str, trigger_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM trigger_policies WHERE tenant_id = ? AND trigger_id = ?",
            (str(tenant_id), str(trigger_id)),
        ).fetchone()
        if row is None:
            return None
        return {
            "tenant_id": row["tenant_id"],
            "trigger_id": row["trigger_id"],
            "name": row["name"],
            "state": row["state"],
            "policy": _loads(row["policy"], {}),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list(
        self,
        tenant_id: str,
        *,
        state: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["tenant_id = ?"]
        params: list[Any] = [str(tenant_id)]
        if state is not None:
            clauses.append("state = ?")
            params.append(_trigger_state(state))
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.conn.execute(
            "SELECT trigger_id FROM trigger_policies WHERE "
            + " AND ".join(clauses)
            + " ORDER BY updated_at DESC, name ASC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [t for r in rows if (t := self.get(str(tenant_id), r["trigger_id"])) is not None]

    def list_active_all(self, *, limit: int = 256) -> list[dict[str, Any]]:
        rows = self._db.conn.execute(
            "SELECT tenant_id, trigger_id FROM trigger_policies WHERE state = 'active' "
            "ORDER BY updated_at ASC, trigger_id ASC LIMIT ?",
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
        return [
            t
            for r in rows
            if (t := self.get(str(r["tenant_id"]), r["trigger_id"])) is not None
        ]

    def set_state(self, tenant_id: str, trigger_id: str, state: str) -> dict[str, Any]:
        state = _trigger_state(state)
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                cur = conn.execute(
                    "UPDATE trigger_policies SET state = ?, updated_at = ? "
                    "WHERE tenant_id = ? AND trigger_id = ?",
                    (state, now, str(tenant_id), str(trigger_id)),
                )
                if cur.rowcount == 0:
                    raise KeyError(trigger_id)
        return self.get(tenant_id, trigger_id)

    def record_firing(
        self,
        tenant_id: str,
        trigger_id: str,
        *,
        run_id: str,
        dedupe_key: str | None,
        event_time: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        firing_id = str(uuid.uuid4())
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO trigger_firings "
                    "(tenant_id, firing_id, trigger_id, run_id, dedupe_key, event_time, "
                    " payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(tenant_id),
                        firing_id,
                        str(trigger_id),
                        str(run_id),
                        dedupe_key,
                        event_time,
                        json.dumps(payload),
                        now,
                    ),
                )
        return self.get_firing(tenant_id, firing_id)

    def get_firing(self, tenant_id: str, firing_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM trigger_firings WHERE tenant_id = ? AND firing_id = ?",
            (str(tenant_id), str(firing_id)),
        ).fetchone()
        if row is None:
            return None
        return {
            "tenant_id": row["tenant_id"],
            "firing_id": row["firing_id"],
            "trigger_id": row["trigger_id"],
            "run_id": row["run_id"],
            "dedupe_key": row["dedupe_key"],
            "event_time": row["event_time"],
            "payload": _loads(row["payload"], {}),
            "created_at": row["created_at"],
        }

    def latest_firing(
        self,
        tenant_id: str,
        trigger_id: str,
        *,
        dedupe_key: str | None = None,
    ) -> dict[str, Any] | None:
        if dedupe_key is None:
            row = self._db.conn.execute(
                "SELECT firing_id FROM trigger_firings "
                "WHERE tenant_id = ? AND trigger_id = ? "
                "ORDER BY event_time DESC, created_at DESC LIMIT 1",
                (str(tenant_id), str(trigger_id)),
            ).fetchone()
        else:
            row = self._db.conn.execute(
                "SELECT firing_id FROM trigger_firings "
                "WHERE tenant_id = ? AND trigger_id = ? AND dedupe_key = ? "
                "ORDER BY event_time DESC, created_at DESC LIMIT 1",
                (str(tenant_id), str(trigger_id), dedupe_key),
            ).fetchone()
        return self.get_firing(tenant_id, row["firing_id"]) if row else None

    def count_firings_since(self, tenant_id: str, trigger_id: str, since: str) -> int:
        row = self._db.conn.execute(
            "SELECT COUNT(*) AS n FROM trigger_firings "
            "WHERE tenant_id = ? AND trigger_id = ? AND event_time >= ?",
            (str(tenant_id), str(trigger_id), since),
        ).fetchone()
        return int(row["n"]) if row else 0

    def list_firings(
        self,
        tenant_id: str,
        *,
        trigger_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["tenant_id = ?"]
        params: list[Any] = [str(tenant_id)]
        if trigger_id is not None:
            clauses.append("trigger_id = ?")
            params.append(str(trigger_id))
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.conn.execute(
            "SELECT firing_id FROM trigger_firings WHERE "
            + " AND ".join(clauses)
            + " ORDER BY event_time DESC, created_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [f for r in rows if (f := self.get_firing(str(tenant_id), r["firing_id"])) is not None]


class TriggerBaselineStore:
    def __init__(self, db: Db) -> None:
        self._db = db

    def get(self, tenant_id: str, trigger_id: str, baseline_key: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM trigger_baselines WHERE tenant_id = ? AND trigger_id = ? AND baseline_key = ?",
            (str(tenant_id), str(trigger_id), str(baseline_key)),
        ).fetchone()
        if row is None:
            return None
        return {
            "tenant_id": row["tenant_id"],
            "trigger_id": row["trigger_id"],
            "baseline_key": row["baseline_key"],
            "type": row["baseline_type"],
            "symbol": row["symbol"],
            "price": row["price"],
            "time": row["baseline_time"],
            "trading_day": row["trading_day"],
            "payload": _loads(row["payload"], {}),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def upsert(
        self,
        tenant_id: str,
        trigger_id: str,
        *,
        baseline_key: str,
        baseline_type: str,
        symbol: str,
        price: float,
        baseline_time: str,
        trading_day: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO trigger_baselines "
                    "(tenant_id, trigger_id, baseline_key, baseline_type, symbol, price, "
                    " baseline_time, trading_day, payload, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(tenant_id, trigger_id, baseline_key) DO UPDATE SET "
                    "baseline_type = excluded.baseline_type, symbol = excluded.symbol, "
                    "price = excluded.price, baseline_time = excluded.baseline_time, "
                    "trading_day = excluded.trading_day, payload = excluded.payload, "
                    "updated_at = excluded.updated_at",
                    (
                        str(tenant_id),
                        str(trigger_id),
                        str(baseline_key),
                        str(baseline_type),
                        str(symbol).upper(),
                        float(price),
                        baseline_time,
                        trading_day,
                        json.dumps(payload or {}),
                        now,
                        now,
                    ),
                )
        return self.get(tenant_id, trigger_id, baseline_key)


class DeliveryTargetStore:
    def __init__(self, db: Db) -> None:
        self._db = db

    def upsert(
        self,
        tenant_id: str,
        *,
        kind: str,
        config: dict[str, Any] | None = None,
        target_id: str | None = None,
        state: str = "active",
        secret_ref: str | None = None,
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        target_id = target_id or str(uuid.uuid4())
        state = _target_state(state)
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO delivery_targets "
                    "(tenant_id, target_id, kind, state, config, secret_ref, capabilities, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(tenant_id, target_id) DO UPDATE SET "
                    "kind = excluded.kind, state = excluded.state, config = excluded.config, "
                    "secret_ref = excluded.secret_ref, capabilities = excluded.capabilities, "
                    "updated_at = excluded.updated_at",
                    (
                        str(tenant_id),
                        str(target_id),
                        str(kind),
                        state,
                        json.dumps(config or {}),
                        secret_ref,
                        json.dumps(capabilities or []),
                        now,
                        now,
                    ),
                )
        return self.get(tenant_id, target_id)

    def get(self, tenant_id: str, target_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM delivery_targets WHERE tenant_id = ? AND target_id = ?",
            (str(tenant_id), str(target_id)),
        ).fetchone()
        if row is None:
            return None
        return {
            "tenant_id": row["tenant_id"],
            "target_id": row["target_id"],
            "kind": row["kind"],
            "state": row["state"],
            "config": _loads(row["config"], {}),
            "secret_ref": row["secret_ref"],
            "capabilities": _loads(row["capabilities"], []),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list(
        self,
        tenant_id: str,
        *,
        kinds: list[str] | None = None,
        state: str | None = "active",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["tenant_id = ?"]
        params: list[Any] = [str(tenant_id)]
        if state is not None:
            clauses.append("state = ?")
            params.append(_target_state(state))
        if kinds:
            placeholders = ", ".join(["?"] * len(kinds))
            clauses.append(f"kind IN ({placeholders})")
            params.extend([str(k) for k in kinds])
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.conn.execute(
            "SELECT target_id FROM delivery_targets WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at ASC, target_id ASC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [t for r in rows if (t := self.get(str(tenant_id), r["target_id"])) is not None]


class NotificationStore:
    def __init__(self, db: Db) -> None:
        self._db = db

    def enqueue(
        self,
        tenant_id: str,
        *,
        event_type: str,
        subject_type: str,
        subject_id: str,
        payload: dict[str, Any],
        priority: str = "normal",
        dedupe_key: str | None = None,
        max_attempts: int = 10,
        next_attempt_at: str | None = None,
    ) -> dict[str, Any]:
        notification_id = str(uuid.uuid4())
        now = _now()
        next_attempt_at = next_attempt_at or now
        with self._db.write_lock:
            with self._db.conn as conn:
                if dedupe_key is None:
                    conn.execute(
                        "INSERT INTO notification_outbox "
                        "(tenant_id, notification_id, event_type, subject_type, subject_id, priority, "
                        " state, dedupe_key, payload, attempts, max_attempts, next_attempt_at, "
                        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, 0, ?, ?, ?, ?)",
                        (
                            str(tenant_id),
                            notification_id,
                            event_type,
                            subject_type,
                            str(subject_id),
                            priority,
                            None,
                            json.dumps(payload),
                            int(max_attempts),
                            next_attempt_at,
                            now,
                            now,
                        ),
                    )
                else:
                    conn.execute(
                        "INSERT INTO notification_outbox "
                        "(tenant_id, notification_id, event_type, subject_type, subject_id, priority, "
                        " state, dedupe_key, payload, attempts, max_attempts, next_attempt_at, "
                        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, 0, ?, ?, ?, ?) "
                        "ON CONFLICT(tenant_id, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING",
                        (
                            str(tenant_id),
                            notification_id,
                            event_type,
                            subject_type,
                            str(subject_id),
                            priority,
                            dedupe_key,
                            json.dumps(payload),
                            int(max_attempts),
                            next_attempt_at,
                            now,
                            now,
                        ),
                    )
                    row = conn.execute(
                        "SELECT notification_id FROM notification_outbox WHERE tenant_id = ? AND dedupe_key = ?",
                        (str(tenant_id), dedupe_key),
                    ).fetchone()
                    if row is not None:
                        notification_id = row["notification_id"]
        return self.get(tenant_id, notification_id)

    def get(self, tenant_id: str, notification_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM notification_outbox WHERE tenant_id = ? AND notification_id = ?",
            (str(tenant_id), str(notification_id)),
        ).fetchone()
        if row is None:
            return None
        return {
            "tenant_id": row["tenant_id"],
            "notification_id": row["notification_id"],
            "event_type": row["event_type"],
            "subject_type": row["subject_type"],
            "subject_id": row["subject_id"],
            "priority": row["priority"],
            "state": row["state"],
            "dedupe_key": row["dedupe_key"],
            "payload": _loads(row["payload"], {}),
            "attempts": row["attempts"],
            "max_attempts": row["max_attempts"],
            "next_attempt_at": row["next_attempt_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "sent_at": row["sent_at"],
        }

    def list(
        self,
        tenant_id: str,
        *,
        state: str | None = "open",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["tenant_id = ?"]
        params: list[Any] = [str(tenant_id)]
        if state:
            state = _notification_state(state)
            if state == "open":
                clauses.append("state != 'acked'")
            else:
                clauses.append("state = ?")
                params.append(state)
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.conn.execute(
            "SELECT notification_id FROM notification_outbox WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC, notification_id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [n for r in rows if (n := self.get(str(tenant_id), r["notification_id"])) is not None]

    def ack(self, tenant_id: str, notification_id: str) -> dict[str, Any]:
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                cur = conn.execute(
                    "UPDATE notification_outbox SET state = 'acked', updated_at = ? "
                    "WHERE tenant_id = ? AND notification_id = ?",
                    (now, str(tenant_id), str(notification_id)),
                )
                if cur.rowcount == 0:
                    raise KeyError(notification_id)
        return self.get(tenant_id, notification_id)

    def claim_available(
        self,
        *,
        worker_id: str,
        limit: int = 25,
        now: str | None = None,
    ) -> list[dict[str, Any]]:
        now = now or _now()
        claimed: list[dict[str, Any]] = []
        with self._db.write_lock:
            with self._db.conn as conn:
                rows = conn.execute(
                    "SELECT tenant_id, notification_id FROM notification_outbox "
                    "WHERE state IN ('queued', 'partial', 'failed') "
                    "AND attempts < max_attempts AND next_attempt_at <= ? "
                    "ORDER BY priority DESC, created_at ASC LIMIT ?",
                    (now, max(1, min(int(limit), 100))),
                ).fetchall()
                for row in rows:
                    cur = conn.execute(
                        "UPDATE notification_outbox "
                        "SET state = 'sending', attempts = attempts + 1, updated_at = ? "
                        "WHERE tenant_id = ? AND notification_id = ? "
                        "AND state IN ('queued', 'partial', 'failed')",
                        (now, row["tenant_id"], row["notification_id"]),
                    )
                    if cur.rowcount == 1:
                        item = self.get(row["tenant_id"], row["notification_id"])
                        if item is not None:
                            claimed.append(item)
        return claimed

    def record_attempt(
        self,
        tenant_id: str,
        notification_id: str,
        target_id: str,
        *,
        state: str,
        request: dict[str, Any],
        response: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        attempt_id = str(uuid.uuid4())
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO notification_attempts "
                    "(tenant_id, attempt_id, notification_id, target_id, state, request, response, error, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(tenant_id),
                        attempt_id,
                        str(notification_id),
                        str(target_id),
                        state,
                        json.dumps(request),
                        json.dumps(response) if response is not None else None,
                        error,
                        now,
                    ),
                )
        return self.get_attempt(tenant_id, attempt_id)

    def get_attempt(self, tenant_id: str, attempt_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM notification_attempts WHERE tenant_id = ? AND attempt_id = ?",
            (str(tenant_id), str(attempt_id)),
        ).fetchone()
        if row is None:
            return None
        return {
            "tenant_id": row["tenant_id"],
            "attempt_id": row["attempt_id"],
            "notification_id": row["notification_id"],
            "target_id": row["target_id"],
            "state": row["state"],
            "request": _loads(row["request"], {}),
            "response": _loads(row["response"], None),
            "error": row["error"],
            "created_at": row["created_at"],
        }

    def list_attempts(self, tenant_id: str, notification_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn.execute(
            "SELECT attempt_id FROM notification_attempts "
            "WHERE tenant_id = ? AND notification_id = ? ORDER BY created_at ASC",
            (str(tenant_id), str(notification_id)),
        ).fetchall()
        return [a for r in rows if (a := self.get_attempt(str(tenant_id), r["attempt_id"])) is not None]

    def mark_sent_or_partial(self, tenant_id: str, notification_id: str, *, failures: int = 0) -> dict[str, Any]:
        state = "sent" if failures == 0 else "partial"
        now = _now()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "UPDATE notification_outbox SET state = ?, sent_at = ?, updated_at = ? "
                    "WHERE tenant_id = ? AND notification_id = ?",
                    (state, now if state == "sent" else None, now, str(tenant_id), str(notification_id)),
                )
        return self.get(tenant_id, notification_id)

    def retry_later(
        self,
        tenant_id: str,
        notification_id: str,
        *,
        delay_seconds: int,
        state: str = "failed",
    ) -> dict[str, Any]:
        now_dt = datetime.now(timezone.utc)
        next_attempt = now_dt.timestamp() + max(1, int(delay_seconds))
        next_iso = datetime.fromtimestamp(next_attempt, tz=timezone.utc).isoformat()
        now = now_dt.isoformat()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "UPDATE notification_outbox SET state = ?, next_attempt_at = ?, updated_at = ? "
                    "WHERE tenant_id = ? AND notification_id = ?",
                    (_notification_state(state), next_iso, now, str(tenant_id), str(notification_id)),
                )
        return self.get(tenant_id, notification_id)
