"""Persistence for saved (named) dashboard layouts.

Users compose a dashboard and save it under a name so it survives sessions and
restarts. The source of truth is Postgres (an idempotent ``CREATE TABLE IF NOT
EXISTS`` here — there is no Drizzle migration for this table, matching the
strategy store's runtime-create approach). When no database is configured the
store degrades to an in-process dict so the feature still works in a stateless
environment — it just will not persist across a restart.

The ``panels`` JSON column holds the full panel list (each panel carries all of
its rendered data inline), so restoring a dashboard never needs to recompute
anything.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import db, tenant

log = logging.getLogger(__name__)

_schema_ready = False
_schema_lock = threading.Lock()

# In-memory fallback (only used when no DB is available).
_mem: Dict[str, dict] = {}
_mem_lock = threading.Lock()


def _ensure_schema() -> None:
    global _schema_ready
    if _schema_ready or not db.db_available():
        return
    with _schema_lock:
        if _schema_ready:
            return
        try:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_dashboards (
                    id text PRIMARY KEY,
                    firm_id text NOT NULL DEFAULT 'default',
                    name text NOT NULL,
                    summary text,
                    panels jsonb NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            db.execute(
                "ALTER TABLE saved_dashboards ADD COLUMN IF NOT EXISTS firm_id text NOT NULL DEFAULT 'default'"
            )
            db.execute("UPDATE saved_dashboards SET firm_id = 'default' WHERE firm_id IS NULL")
            db.execute(
                "CREATE INDEX IF NOT EXISTS saved_dashboards_firm_idx ON saved_dashboards (firm_id)"
            )
            _schema_ready = True
        except Exception as exc:  # noqa: BLE001
            log.warning("saved_dashboards schema ensure failed: %s", exc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta(row: dict) -> dict:
    """Lightweight view for the list endpoint (no heavy panel payload)."""
    panels = row.get("panels") or []
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "summary": row.get("summary") or "",
        "panelCount": len(panels),
        "createdAt": _iso(row.get("createdAt") or row.get("created_at")),
        "updatedAt": _iso(row.get("updatedAt") or row.get("updated_at")),
    }


def _iso(v) -> Optional[str]:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else v


def list_dashboards(firm_id: Optional[str] = None) -> List[dict]:
    """Return metadata for all saved dashboards in the caller's firm, newest first."""
    _ensure_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            rows = db.query(
                "SELECT id, name, summary, panels, created_at, updated_at "
                "FROM saved_dashboards WHERE firm_id = %s ORDER BY updated_at DESC",
                (fid,),
            )
            return [_meta(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.warning("list_dashboards DB error: %s", exc)
    with _mem_lock:
        rows = sorted(
            (r for r in _mem.values() if (r.get("firmId") or tenant.DEFAULT_FIRM_ID) == fid),
            key=lambda r: r.get("updatedAt") or "", reverse=True,
        )
        return [_meta(r) for r in rows]


def get_dashboard(dash_id: str, firm_id: Optional[str] = None) -> Optional[dict]:
    """Return the full saved dashboard (including panels) by id, scoped to firm."""
    if not dash_id:
        return None
    _ensure_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT id, name, summary, panels, created_at, updated_at "
                "FROM saved_dashboards WHERE id = %s AND firm_id = %s",
                (dash_id, fid),
            )
            if not row:
                return None
            return {
                "id": row["id"],
                "name": row["name"],
                "summary": row.get("summary") or "",
                "panels": row.get("panels") or [],
                "createdAt": _iso(row.get("created_at")),
                "updatedAt": _iso(row.get("updated_at")),
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("get_dashboard DB error: %s", exc)
    with _mem_lock:
        rec = _mem.get(dash_id)
        return dict(rec) if rec else None


def save_dashboard(name: str, summary: str, panels: List[dict], firm_id: Optional[str] = None) -> dict:
    """Persist a new named dashboard in the caller's firm. Saving the same name
    (within that firm) overwrites the prior layout so the saved list does not
    fill with duplicates; the same name in a different firm is independent."""
    _ensure_schema()
    fid = tenant.resolve_firm(firm_id)
    name = (name or "").strip()
    summary = summary or ""
    panels = list(panels or [])
    now = _now_iso()

    if db.db_available():
        try:
            existing = db.query_one(
                "SELECT id FROM saved_dashboards WHERE lower(name) = lower(%s) AND firm_id = %s LIMIT 1",
                (name, fid),
            )
            dash_id = existing["id"] if existing else uuid.uuid4().hex[:12]
            db.execute(
                """
                INSERT INTO saved_dashboards (id, firm_id, name, summary, panels, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    summary = EXCLUDED.summary,
                    panels = EXCLUDED.panels,
                    updated_at = EXCLUDED.updated_at
                """,
                (dash_id, fid, name, summary, json.dumps(panels), now, now),
            )
            return get_dashboard(dash_id, firm_id=fid) or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("save_dashboard DB error: %s", exc)

    # In-memory fallback.
    with _mem_lock:
        dash_id = None
        for rid, rec in _mem.items():
            if (rec.get("name") or "").lower() == name.lower() and \
               (rec.get("firmId") or tenant.DEFAULT_FIRM_ID) == fid:
                dash_id = rid
                break
        created = now
        if dash_id is None:
            dash_id = uuid.uuid4().hex[:12]
        else:
            created = _mem[dash_id].get("createdAt") or now
        _mem[dash_id] = {
            "id": dash_id,
            "firmId": fid,
            "name": name,
            "summary": summary,
            "panels": panels,
            "createdAt": created,
            "updatedAt": now,
        }
        return dict(_mem[dash_id])


def delete_dashboard(dash_id: str, firm_id: Optional[str] = None) -> bool:
    _ensure_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            res = db.query_one(
                "DELETE FROM saved_dashboards WHERE id = %s AND firm_id = %s RETURNING id",
                (dash_id, fid),
            )
            return bool(res)
        except Exception as exc:  # noqa: BLE001
            log.warning("delete_dashboard DB error: %s", exc)
    with _mem_lock:
        rec = _mem.get(dash_id)
        if rec and (rec.get("firmId") or tenant.DEFAULT_FIRM_ID) == fid:
            _mem.pop(dash_id, None)
            return True
        return False
