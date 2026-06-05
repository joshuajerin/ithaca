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

_snap_schema_ready = False
_snap_schema_lock = threading.Lock()

# In-memory fallback (only used when no DB is available).
_mem: Dict[str, dict] = {}
_mem_lock = threading.Lock()

# In-memory snapshot fallback keyed by (strategy_id, iso-date).
_snap_mem: Dict[tuple, dict] = {}
_snap_mem_lock = threading.Lock()


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
    _ensure_snapshot_schema()  # so the cascade delete can't fail on a missing table
    if db.db_available():
        try:
            db.execute("DELETE FROM strategy_snapshots WHERE strategy_id = %s", (strategy_id,))
            db.execute("DELETE FROM strategies WHERE id = %s", (strategy_id,))
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("delete strategy DB error: %s", exc)
    with _mem_lock:
        removed = _mem.pop(strategy_id, None) is not None
    with _snap_mem_lock:
        for key in [k for k in _snap_mem if k[0] == strategy_id]:
            _snap_mem.pop(key, None)
    return removed


# --------------------------- daily snapshots ---------------------------
def _ensure_snapshot_schema() -> None:
    """Idempotent DDL for the daily mark snapshot table (mirrors the Drizzle
    ``strategy_snapshots`` definition so it works without ``drizzle push``)."""
    global _snap_schema_ready
    if _snap_schema_ready or not db.db_available():
        return
    with _snap_schema_lock:
        if _snap_schema_ready:
            return
        try:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_snapshots (
                    strategy_id text NOT NULL,
                    d date NOT NULL,
                    nav double precision,
                    pnl double precision,
                    pnl_pct double precision,
                    cash double precision,
                    capital double precision,
                    stage text,
                    source text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (strategy_id, d)
                )
                """
            )
            _snap_schema_ready = True
        except Exception as exc:  # noqa: BLE001
            log.warning("snapshot schema ensure failed: %s", exc)


def record_snapshot(
    strategy_id: str,
    d: str,
    nav: Optional[float],
    pnl: Optional[float],
    pnl_pct: Optional[float],
    cash: Optional[float] = None,
    capital: Optional[float] = None,
    stage: Optional[str] = None,
    source: Optional[str] = None,
) -> None:
    """Persist (or refresh) one strategy's mark for trading day ``d``.

    Idempotent: the (strategy_id, d) primary key means re-running for the same
    day updates that day's row rather than appending a duplicate point.
    """
    _ensure_snapshot_schema()
    if db.db_available():
        try:
            db.execute(
                """
                INSERT INTO strategy_snapshots
                    (strategy_id, d, nav, pnl, pnl_pct, cash, capital, stage, source, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (strategy_id, d) DO UPDATE SET
                    nav = EXCLUDED.nav,
                    pnl = EXCLUDED.pnl,
                    pnl_pct = EXCLUDED.pnl_pct,
                    cash = EXCLUDED.cash,
                    capital = EXCLUDED.capital,
                    stage = EXCLUDED.stage,
                    source = EXCLUDED.source,
                    updated_at = now()
                """,
                (strategy_id, d, nav, pnl, pnl_pct, cash, capital, stage, source),
            )
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("record_snapshot DB error: %s", exc)
    with _snap_mem_lock:
        _snap_mem[(strategy_id, d)] = {
            "t": d, "nav": nav, "pnl": pnl, "pnlPct": pnl_pct,
            "cash": cash, "capital": capital, "stage": stage, "source": source,
        }


def snapshot_series(strategy_id: str) -> List[dict]:
    """Ascending persisted daily NAV series for a strategy.

    Returns ``[{"t", "nav", "pnl", "pnlPct", "source"}, ...]`` shaped like the
    reconstructed nav_curve so the realized-stat block can consume it directly.
    """
    _ensure_snapshot_schema()
    if db.db_available():
        try:
            rows = db.query(
                "SELECT d, nav, pnl, pnl_pct, source FROM strategy_snapshots "
                "WHERE strategy_id = %s ORDER BY d ASC",
                (strategy_id,),
            )
            out: List[dict] = []
            for r in rows:
                d = r["d"]
                out.append({
                    "t": d.isoformat() if hasattr(d, "isoformat") else str(d),
                    "nav": r.get("nav"),
                    "pnl": r.get("pnl"),
                    "pnlPct": r.get("pnl_pct"),
                    "source": r.get("source"),
                })
            return out
        except Exception as exc:  # noqa: BLE001
            log.warning("snapshot_series DB error: %s", exc)
    with _snap_mem_lock:
        rows = [v for k, v in _snap_mem.items() if k[0] == strategy_id]
    rows.sort(key=lambda r: r.get("t") or "")
    return [{"t": r["t"], "nav": r["nav"], "pnl": r["pnl"],
             "pnlPct": r["pnlPct"], "source": r.get("source")} for r in rows]


def snapshot_count(strategy_id: str) -> int:
    """Number of distinct audited trading-day snapshots for a strategy."""
    _ensure_snapshot_schema()
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT count(*) AS n FROM strategy_snapshots WHERE strategy_id = %s",
                (strategy_id,),
            )
            return int(row["n"]) if row else 0
        except Exception as exc:  # noqa: BLE001
            log.warning("snapshot_count DB error: %s", exc)
    with _snap_mem_lock:
        return sum(1 for k in _snap_mem if k[0] == strategy_id)


def latest_snapshot_date(strategy_id: str) -> Optional[str]:
    """ISO date of the most recent persisted snapshot, or None."""
    _ensure_snapshot_schema()
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT max(d) AS d FROM strategy_snapshots WHERE strategy_id = %s",
                (strategy_id,),
            )
            d = row.get("d") if row else None
            if d is None:
                return None
            return d.isoformat() if hasattr(d, "isoformat") else str(d)
        except Exception as exc:  # noqa: BLE001
            log.warning("latest_snapshot_date DB error: %s", exc)
    with _snap_mem_lock:
        dates = [k[1] for k in _snap_mem if k[0] == strategy_id]
    return max(dates) if dates else None
