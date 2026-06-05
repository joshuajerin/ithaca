"""Persistence for the strategy lifecycle registry.

Strategies (and their paper/live books) must survive sessions and restarts, so
the source of truth is Postgres (the ``strategies`` table defined in the Drizzle
schema and mirrored by an idempotent ``CREATE TABLE IF NOT EXISTS`` here). When
no database is configured the store degrades to an in-process dict so the
feature still works in a stateless environment — it just will not persist across
a restart.

JSON columns are written as ``json.dumps(...)::jsonb`` text casts (avoiding any
adapter import) and come back already parsed by psycopg.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import db

log = logging.getLogger(__name__)

_JSON_FIELDS = ("construction", "positions", "target_weights", "promotion_criteria", "stage_history")
_COLUMNS = (
    "id", "name", "signal", "construction", "stage", "capital", "cash",
    "inception_date", "positions", "target_weights", "promotion_criteria",
    "stage_history", "notes", "created_at", "updated_at",
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
                CREATE TABLE IF NOT EXISTS strategies (
                    id text PRIMARY KEY,
                    name text NOT NULL,
                    signal text,
                    construction jsonb,
                    stage text NOT NULL DEFAULT 'research',
                    capital double precision,
                    cash double precision,
                    inception_date date,
                    positions jsonb,
                    target_weights jsonb,
                    promotion_criteria jsonb,
                    stage_history jsonb,
                    notes text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            _schema_ready = True
        except Exception as exc:  # noqa: BLE001
            log.warning("strategy schema ensure failed: %s", exc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: dict) -> dict:
    out = dict(row)
    for k in ("created_at", "updated_at", "inception_date"):
        v = out.get(k)
        if v is not None and hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    # camelCase the few fields the API/panel consume directly.
    out["targetWeights"] = out.pop("target_weights", None)
    out["promotionCriteria"] = out.pop("promotion_criteria", None)
    out["stageHistory"] = out.pop("stage_history", None)
    out["inceptionDate"] = out.pop("inception_date", None)
    out["createdAt"] = out.pop("created_at", None)
    out["updatedAt"] = out.pop("updated_at", None)
    return out


def _to_db_value(field: str, value):
    if field in _JSON_FIELDS:
        return json.dumps(value) if value is not None else None
    return value


def list_strategies() -> List[dict]:
    _ensure_schema()
    if db.db_available():
        try:
            rows = db.query("SELECT * FROM strategies ORDER BY created_at ASC")
            return [_row_to_dict(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.warning("list_strategies DB error: %s", exc)
    with _mem_lock:
        return [dict(v) for v in sorted(_mem.values(), key=lambda r: r.get("createdAt") or "")]


def get_strategy(key: str) -> Optional[dict]:
    """Look up by id (exact) or by case-insensitive name match."""
    if not key:
        return None
    _ensure_schema()
    k = key.strip()
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT * FROM strategies WHERE id = %s OR lower(name) = lower(%s) "
                "ORDER BY (id = %s) DESC LIMIT 1",
                (k, k, k),
            )
            return _row_to_dict(row) if row else None
        except Exception as exc:  # noqa: BLE001
            log.warning("get_strategy DB error: %s", exc)
    with _mem_lock:
        if k in _mem:
            return dict(_mem[k])
        for v in _mem.values():
            if (v.get("name") or "").lower() == k.lower():
                return dict(v)
    return None


def upsert(record: dict) -> dict:
    """Insert or update a full strategy record (keyed by id)."""
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
                f"INSERT INTO strategies ({', '.join(cols)}) "
                f"VALUES ({', '.join(placeholders)}) "
                f"ON CONFLICT (id) DO UPDATE SET {updates}"
            )
            db.execute(sql, tuple(values))
            return get_strategy(record["id"]) or record
        except Exception as exc:  # noqa: BLE001
            log.warning("upsert strategy DB error: %s", exc)

    # In-memory fallback: store the already-camelCased view for read parity.
    mem_view = {
        "id": record.get("id"),
        "name": record.get("name"),
        "signal": record.get("signal"),
        "construction": record.get("construction"),
        "stage": record.get("stage"),
        "capital": record.get("capital"),
        "cash": record.get("cash"),
        "inceptionDate": record.get("inception_date"),
        "positions": record.get("positions"),
        "targetWeights": record.get("target_weights"),
        "promotionCriteria": record.get("promotion_criteria"),
        "stageHistory": record.get("stage_history"),
        "notes": record.get("notes"),
        "createdAt": record.get("created_at"),
        "updatedAt": record.get("updated_at"),
    }
    with _mem_lock:
        _mem[record["id"]] = mem_view
        return dict(mem_view)


def delete(strategy_id: str) -> bool:
    _ensure_schema()
    if db.db_available():
        try:
            db.execute("DELETE FROM strategies WHERE id = %s", (strategy_id,))
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("delete strategy DB error: %s", exc)
    with _mem_lock:
        return _mem.pop(strategy_id, None) is not None
