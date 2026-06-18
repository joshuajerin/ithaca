"""Persistence for user-saved strategy templates (the marketplace).

User-configured templates are reusable presets of an alpha signal + universe +
sizing. Like the strategy registry, the source of truth is Postgres (an
idempotent ``CREATE TABLE IF NOT EXISTS`` mirroring the Drizzle schema) with an
in-process dict fallback when no database is configured, so the feature works in
a stateless environment — it just will not persist across a restart.

Built-in templates are NOT stored here; they live in ``templates.py``. This
store only holds the templates a user explicitly saves.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import db

log = logging.getLogger(__name__)

_JSON_FIELDS = ("params",)
_COLUMNS = (
    "id", "name", "description", "category", "signal", "sector",
    "params", "created_at", "updated_at",
)

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
                CREATE TABLE IF NOT EXISTS strategy_templates (
                    id text PRIMARY KEY,
                    name text NOT NULL,
                    description text,
                    category text,
                    signal text,
                    sector text,
                    params jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            _schema_ready = True
        except Exception as exc:  # noqa: BLE001
            log.warning("template schema ensure failed: %s", exc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: dict) -> dict:
    out = dict(row)
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if v is not None and hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    out["createdAt"] = out.pop("created_at", None)
    out["updatedAt"] = out.pop("updated_at", None)
    out["builtIn"] = False
    return out


def _to_db_value(field: str, value):
    if field in _JSON_FIELDS:
        return json.dumps(value) if value is not None else None
    return value


def list_templates() -> List[dict]:
    _ensure_schema()
    if db.db_available():
        try:
            rows = db.query("SELECT * FROM strategy_templates ORDER BY created_at ASC")
            return [_row_to_dict(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.warning("list_templates DB error: %s", exc)
    with _mem_lock:
        return [dict(v) for v in sorted(_mem.values(), key=lambda r: r.get("createdAt") or "")]


def get_template(key: str) -> Optional[dict]:
    """Look up by id (exact) or by case-insensitive name match."""
    if not key:
        return None
    _ensure_schema()
    k = key.strip()
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT * FROM strategy_templates WHERE id = %s OR lower(name) = lower(%s) "
                "ORDER BY (id = %s) DESC LIMIT 1",
                (k, k, k),
            )
            return _row_to_dict(row) if row else None
        except Exception as exc:  # noqa: BLE001
            log.warning("get_template DB error: %s", exc)
    with _mem_lock:
        if k in _mem:
            return dict(_mem[k])
        for v in _mem.values():
            if (v.get("name") or "").lower() == k.lower():
                return dict(v)
    return None


def upsert(record: dict) -> dict:
    """Insert or update a full user template record (keyed by id)."""
    _ensure_schema()
    now = _now_iso()
    record = dict(record)
    record.setdefault("created_at", now)
    record["updated_at"] = now

    if db.db_available():
        try:
            cols = list(_COLUMNS)
            placeholders = []
            values = []
            for c in cols:
                values.append(_to_db_value(c, record.get(c)))
                placeholders.append("%s::jsonb" if c in _JSON_FIELDS else "%s")
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("id", "created_at"))
            sql = (
                f"INSERT INTO strategy_templates ({', '.join(cols)}) "
                f"VALUES ({', '.join(placeholders)}) "
                f"ON CONFLICT (id) DO UPDATE SET {updates}"
            )
            db.execute(sql, tuple(values))
            return get_template(record["id"]) or record
        except Exception as exc:  # noqa: BLE001
            log.warning("upsert template DB error: %s", exc)

    mem_view = {
        "id": record.get("id"),
        "name": record.get("name"),
        "description": record.get("description"),
        "category": record.get("category"),
        "signal": record.get("signal"),
        "sector": record.get("sector"),
        "params": record.get("params"),
        "createdAt": record.get("created_at"),
        "updatedAt": record.get("updated_at"),
        "builtIn": False,
    }
    with _mem_lock:
        _mem[record["id"]] = mem_view
        return dict(mem_view)


def delete(template_id: str) -> bool:
    """Delete a user template. Returns True only if a row actually existed."""
    _ensure_schema()
    if db.db_available():
        try:
            existed = (
                db.query_one("SELECT id FROM strategy_templates WHERE id = %s", (template_id,))
                is not None
            )
            if existed:
                db.execute("DELETE FROM strategy_templates WHERE id = %s", (template_id,))
            return existed
        except Exception as exc:  # noqa: BLE001
            log.warning("delete template DB error: %s", exc)
    with _mem_lock:
        return _mem.pop(template_id, None) is not None
