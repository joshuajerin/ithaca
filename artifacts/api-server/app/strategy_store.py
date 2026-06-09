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

from . import db, tenant

log = logging.getLogger(__name__)

_JSON_FIELDS = ("construction", "positions", "target_weights", "promotion_criteria", "stage_history")
_COLUMNS = (
    "id", "firm_id", "name", "signal", "construction", "stage", "capital", "cash",
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
                    firm_id text NOT NULL DEFAULT 'default',
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
            # Idempotently add firm scoping to pre-multi-tenant deployments and
            # backfill existing rows to the default firm.
            db.execute(
                "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS firm_id text NOT NULL DEFAULT 'default'"
            )
            db.execute("UPDATE strategies SET firm_id = 'default' WHERE firm_id IS NULL")
            db.execute("CREATE INDEX IF NOT EXISTS strategies_firm_idx ON strategies (firm_id)")
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
    out["firmId"] = out.pop("firm_id", None)
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


def list_strategies(firm_id: Optional[str] = None) -> List[dict]:
    """Strategies owned by the caller's firm (or an explicit ``firm_id``)."""
    _ensure_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            rows = db.query(
                "SELECT * FROM strategies WHERE firm_id = %s ORDER BY created_at ASC",
                (fid,),
            )
            return [_row_to_dict(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.warning("list_strategies DB error: %s", exc)
    with _mem_lock:
        rows = [v for v in _mem.values() if (v.get("firmId") or tenant.DEFAULT_FIRM_ID) == fid]
        return [dict(v) for v in sorted(rows, key=lambda r: r.get("createdAt") or "")]


def list_all_strategies() -> List[dict]:
    """Every strategy across all firms — for the background worker only.

    The worker marks and rebalances books on every tenant's behalf; it enters a
    per-strategy firm context (see ``tenant.firm_context``) before touching any
    other store, so this is the one read that is intentionally cross-firm.
    """
    _ensure_schema()
    if db.db_available():
        try:
            rows = db.query("SELECT * FROM strategies ORDER BY created_at ASC")
            return [_row_to_dict(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.warning("list_all_strategies DB error: %s", exc)
    with _mem_lock:
        return [dict(v) for v in sorted(_mem.values(), key=lambda r: r.get("createdAt") or "")]


def get_strategy(key: str, firm_id: Optional[str] = None) -> Optional[dict]:
    """Look up by id (exact) or case-insensitive name, scoped to the caller's firm.

    Cross-firm access is denied: a Firm A caller passing a Firm B id/name gets
    ``None`` because the firm filter excludes it.
    """
    if not key:
        return None
    _ensure_schema()
    k = key.strip()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT * FROM strategies WHERE firm_id = %s "
                "AND (id = %s OR lower(name) = lower(%s)) "
                "ORDER BY (id = %s) DESC LIMIT 1",
                (fid, k, k, k),
            )
            return _row_to_dict(row) if row else None
        except Exception as exc:  # noqa: BLE001
            log.warning("get_strategy DB error: %s", exc)
    with _mem_lock:
        rec = _mem.get(k)
        if rec and (rec.get("firmId") or tenant.DEFAULT_FIRM_ID) == fid:
            return dict(rec)
        for v in _mem.values():
            if (v.get("firmId") or tenant.DEFAULT_FIRM_ID) == fid and (v.get("name") or "").lower() == k.lower():
                return dict(v)
    return None


def upsert(record: dict, firm_id: Optional[str] = None) -> dict:
    """Insert or update a full strategy record (keyed by id), stamped with the
    owning firm. The firm comes from the record itself (re-persisting an existing
    book), then an explicit ``firm_id``, then the current request's firm."""
    _ensure_schema()
    now = _now_iso()
    record = dict(record)
    record["firm_id"] = record.get("firm_id") or record.get("firmId") or tenant.resolve_firm(firm_id)
    record.pop("firmId", None)
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
        "firmId": record.get("firm_id"),
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


def delete(strategy_id: str, firm_id: Optional[str] = None) -> bool:
    """Delete a strategy and its snapshots, scoped to the caller's firm so a
    Firm A caller can never delete a Firm B book by id."""
    _ensure_schema()
    _ensure_snapshot_schema()  # so the cascade delete can't fail on a missing table
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            db.execute(
                "DELETE FROM strategy_snapshots WHERE strategy_id = %s AND firm_id = %s",
                (strategy_id, fid),
            )
            res = db.query_one(
                "DELETE FROM strategies WHERE id = %s AND firm_id = %s RETURNING id",
                (strategy_id, fid),
            )
            return bool(res)
        except Exception as exc:  # noqa: BLE001
            log.warning("delete strategy DB error: %s", exc)
    with _mem_lock:
        rec = _mem.get(strategy_id)
        removed = False
        if rec and (rec.get("firmId") or tenant.DEFAULT_FIRM_ID) == fid:
            _mem.pop(strategy_id, None)
            removed = True
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
                    firm_id text NOT NULL DEFAULT 'default',
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
            db.execute(
                "ALTER TABLE strategy_snapshots ADD COLUMN IF NOT EXISTS firm_id text NOT NULL DEFAULT 'default'"
            )
            db.execute("UPDATE strategy_snapshots SET firm_id = 'default' WHERE firm_id IS NULL")
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
    firm_id: Optional[str] = None,
) -> None:
    """Persist (or refresh) one strategy's mark for trading day ``d``.

    Idempotent: the (strategy_id, d) primary key means re-running for the same
    day updates that day's row rather than appending a duplicate point. Stamped
    with the owning firm (current request/worker firm context).
    """
    _ensure_snapshot_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            db.execute(
                """
                INSERT INTO strategy_snapshots
                    (strategy_id, firm_id, d, nav, pnl, pnl_pct, cash, capital, stage, source, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (strategy_id, d) DO UPDATE SET
                    firm_id = EXCLUDED.firm_id,
                    nav = EXCLUDED.nav,
                    pnl = EXCLUDED.pnl,
                    pnl_pct = EXCLUDED.pnl_pct,
                    cash = EXCLUDED.cash,
                    capital = EXCLUDED.capital,
                    stage = EXCLUDED.stage,
                    source = EXCLUDED.source,
                    updated_at = now()
                """,
                (strategy_id, fid, d, nav, pnl, pnl_pct, cash, capital, stage, source),
            )
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("record_snapshot DB error: %s", exc)
    with _snap_mem_lock:
        _snap_mem[(strategy_id, d)] = {
            "t": d, "firmId": fid, "nav": nav, "pnl": pnl, "pnlPct": pnl_pct,
            "cash": cash, "capital": capital, "stage": stage, "source": source,
        }


def snapshot_series(strategy_id: str, firm_id: Optional[str] = None) -> List[dict]:
    """Ascending persisted daily NAV series for a strategy, scoped to its firm.

    Returns ``[{"t", "nav", "pnl", "pnlPct", "source"}, ...]`` shaped like the
    reconstructed nav_curve so the realized-stat block can consume it directly.
    """
    _ensure_snapshot_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            rows = db.query(
                "SELECT d, nav, pnl, pnl_pct, source FROM strategy_snapshots "
                "WHERE strategy_id = %s AND firm_id = %s ORDER BY d ASC",
                (strategy_id, fid),
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
        rows = [v for k, v in _snap_mem.items()
                if k[0] == strategy_id and (v.get("firmId") or tenant.DEFAULT_FIRM_ID) == fid]
    rows.sort(key=lambda r: r.get("t") or "")
    return [{"t": r["t"], "nav": r["nav"], "pnl": r["pnl"],
             "pnlPct": r["pnlPct"], "source": r.get("source")} for r in rows]


def snapshot_count(strategy_id: str, firm_id: Optional[str] = None) -> int:
    """Number of distinct audited trading-day snapshots for a strategy."""
    _ensure_snapshot_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT count(*) AS n FROM strategy_snapshots WHERE strategy_id = %s AND firm_id = %s",
                (strategy_id, fid),
            )
            return int(row["n"]) if row else 0
        except Exception as exc:  # noqa: BLE001
            log.warning("snapshot_count DB error: %s", exc)
    with _snap_mem_lock:
        return sum(1 for k, v in _snap_mem.items()
                   if k[0] == strategy_id and (v.get("firmId") or tenant.DEFAULT_FIRM_ID) == fid)


def latest_snapshot_date(strategy_id: str, firm_id: Optional[str] = None) -> Optional[str]:
    """ISO date of the most recent persisted snapshot, or None."""
    _ensure_snapshot_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT max(d) AS d FROM strategy_snapshots WHERE strategy_id = %s AND firm_id = %s",
                (strategy_id, fid),
            )
            d = row.get("d") if row else None
            if d is None:
                return None
            return d.isoformat() if hasattr(d, "isoformat") else str(d)
        except Exception as exc:  # noqa: BLE001
            log.warning("latest_snapshot_date DB error: %s", exc)
    with _snap_mem_lock:
        dates = [k[1] for k, v in _snap_mem.items()
                 if k[0] == strategy_id and (v.get("firmId") or tenant.DEFAULT_FIRM_ID) == fid]
    return max(dates) if dates else None
