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
