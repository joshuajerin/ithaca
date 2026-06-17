"""Persistence for the pre-trade compliance configuration and audit trail.

Two pieces of state must survive sessions and restarts:

  * a single GLOBAL config row (``id = 'global'``) holding the firm limits, the
    restricted + watch lists, the global kill switch and a per-strategy kill map;
  * an append-only audit trail of every pre-trade gate decision.

The source of truth is Postgres via idempotent ``CREATE TABLE IF NOT EXISTS``
DDL (no ``drizzle push`` needed). When no database is configured the store
degrades to in-process state so the feature still works statelessly — it just
will not persist across a restart. JSON columns are written as
``json.dumps(...)::jsonb`` text casts and come back already parsed by psycopg.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import db, tenant
from .engine import compliance as comp

log = logging.getLogger(__name__)

_schema_ready = False
_schema_lock = threading.Lock()

# In-memory fallbacks (only used when no DB is available). Both are keyed by
# firm_id so Firm A's config and audit trail are isolated from Firm B's.
_mem_cfg: Dict[str, dict] = {}
_mem_audit: Dict[str, List[dict]] = {}
_mem_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_config() -> dict:
    return {
        "limits": dict(comp.DEFAULT_LIMITS),
        "restricted": [],
        "watch": [],
        "killSwitch": False,
        "killReason": None,
        "strategyKills": {},
    }


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
                CREATE TABLE IF NOT EXISTS compliance_config (
                    id text PRIMARY KEY,
                    limits jsonb,
                    restricted jsonb,
                    watch jsonb,
                    kill_switch boolean NOT NULL DEFAULT false,
                    kill_reason text,
                    strategy_kills jsonb,
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS compliance_audit (
                    id text PRIMARY KEY,
                    firm_id text NOT NULL DEFAULT 'default',
                    at timestamptz NOT NULL DEFAULT now(),
                    action text,
                    strategy_id text,
                    strategy_name text,
                    decision text,
                    summary text,
                    detail jsonb
                )
                """
            )
            # Per-firm scoping: the config PK *is* the firm_id. Rename the legacy
            # single global row, and stamp the audit trail with its owning firm.
            db.execute("UPDATE compliance_config SET id = 'default' WHERE id = 'global'")
            db.execute(
                "ALTER TABLE compliance_audit ADD COLUMN IF NOT EXISTS firm_id text NOT NULL DEFAULT 'default'"
            )
            db.execute("UPDATE compliance_audit SET firm_id = 'default' WHERE firm_id IS NULL")
            # Firm-wide, user-attributed audit trail: the compliance gate is just
            # one category of recorded action now. These columns widen the same
            # append-only table into a unified audit log without a new table.
            db.execute("ALTER TABLE compliance_audit ADD COLUMN IF NOT EXISTS category text")
            db.execute("ALTER TABLE compliance_audit ADD COLUMN IF NOT EXISTS target text")
            db.execute("ALTER TABLE compliance_audit ADD COLUMN IF NOT EXISTS actor_user_id text")
            db.execute("ALTER TABLE compliance_audit ADD COLUMN IF NOT EXISTS actor_name text")
            # Existing rows predate categories — they are all gate decisions.
            db.execute("UPDATE compliance_audit SET category = 'compliance' WHERE category IS NULL")
            db.execute(
                "CREATE INDEX IF NOT EXISTS compliance_audit_firm_idx ON compliance_audit (firm_id, at DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS compliance_audit_cat_idx ON compliance_audit (firm_id, category, at DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS compliance_audit_actor_idx ON compliance_audit (firm_id, actor_user_id, at DESC)"
            )
            _schema_ready = True
        except Exception as exc:  # noqa: BLE001
            log.warning("compliance schema ensure failed: %s", exc)


def _norm_syms(items) -> List[str]:
    out: List[str] = []
    for it in items or []:
        s = (str(it) or "").strip().upper()
        if s and s not in out:
            out.append(s)
    return out


def _coerce_config(raw: Optional[dict]) -> dict:
    cfg = _default_config()
    if not raw:
        return cfg
    if isinstance(raw.get("limits"), dict):
        cfg["limits"] = comp.merge_limits(raw["limits"])
    cfg["restricted"] = _norm_syms(raw.get("restricted"))
    cfg["watch"] = _norm_syms(raw.get("watch"))
    cfg["killSwitch"] = bool(raw.get("killSwitch") or raw.get("kill_switch"))
    cfg["killReason"] = raw.get("killReason") or raw.get("kill_reason")
    sk = raw.get("strategyKills") or raw.get("strategy_kills") or {}
    if isinstance(sk, dict):
        cfg["strategyKills"] = {str(k): v for k, v in sk.items() if v}
    return cfg


# ------------------------------- config -------------------------------
def get_config(firm_id: Optional[str] = None) -> dict:
    _ensure_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT * FROM compliance_config WHERE id = %s", (fid,)
            )
            if not row:
                return _default_config()
            return _coerce_config({
                "limits": row.get("limits"),
                "restricted": row.get("restricted"),
                "watch": row.get("watch"),
                "kill_switch": row.get("kill_switch"),
                "kill_reason": row.get("kill_reason"),
                "strategy_kills": row.get("strategy_kills"),
            })
        except Exception as exc:  # noqa: BLE001
            log.warning("get_config DB error: %s", exc)
    with _mem_lock:
        return dict(_coerce_config(_mem_cfg.get(fid)))


def save_config(cfg: dict, firm_id: Optional[str] = None) -> dict:
    """Persist a full config dict (already coerced) for the caller's firm and
    return the stored view."""
    cfg = _coerce_config(cfg)
    _ensure_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            db.execute(
                """
                INSERT INTO compliance_config
                    (id, limits, restricted, watch, kill_switch, kill_reason, strategy_kills, updated_at)
                VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb, now())
                ON CONFLICT (id) DO UPDATE SET
                    limits = EXCLUDED.limits,
                    restricted = EXCLUDED.restricted,
                    watch = EXCLUDED.watch,
                    kill_switch = EXCLUDED.kill_switch,
                    kill_reason = EXCLUDED.kill_reason,
                    strategy_kills = EXCLUDED.strategy_kills,
                    updated_at = now()
                """,
                (
                    fid,
                    json.dumps(cfg["limits"]),
                    json.dumps(cfg["restricted"]),
                    json.dumps(cfg["watch"]),
                    cfg["killSwitch"],
                    cfg["killReason"],
                    json.dumps(cfg["strategyKills"]),
                ),
            )
            return cfg
        except Exception as exc:  # noqa: BLE001
            log.warning("save_config DB error: %s", exc)
    with _mem_lock:
        _mem_cfg[fid] = dict(cfg)
        return dict(cfg)


def _mutate(fn) -> dict:
    """Read config, apply ``fn`` (mutates in place), persist, return new config."""
    cfg = get_config()
    fn(cfg)
    return save_config(cfg)


def set_limits(limits: dict) -> dict:
    return _mutate(lambda c: c.__setitem__("limits", comp.merge_limits({**c["limits"], **(limits or {})})))


def add_restricted(symbol: str) -> dict:
    sym = (symbol or "").strip().upper()

    def _f(c):
        if sym and sym not in c["restricted"]:
            c["restricted"].append(sym)
    return _mutate(_f)


def remove_restricted(symbol: str) -> dict:
    sym = (symbol or "").strip().upper()
    return _mutate(lambda c: c.__setitem__("restricted", [s for s in c["restricted"] if s != sym]))


def add_watch(symbol: str) -> dict:
    sym = (symbol or "").strip().upper()

    def _f(c):
        if sym and sym not in c["watch"]:
            c["watch"].append(sym)
    return _mutate(_f)


def remove_watch(symbol: str) -> dict:
    sym = (symbol or "").strip().upper()
    return _mutate(lambda c: c.__setitem__("watch", [s for s in c["watch"] if s != sym]))


def set_kill_switch(on: bool, reason: Optional[str] = None, strategy_id: Optional[str] = None) -> dict:
    """Engage/release the global kill switch, or a per-strategy one when
    ``strategy_id`` is given."""
    def _f(c):
        if strategy_id:
            kills = dict(c.get("strategyKills") or {})
            if on:
                kills[strategy_id] = reason or "halted"
            else:
                kills.pop(strategy_id, None)
            c["strategyKills"] = kills
        else:
            c["killSwitch"] = bool(on)
            c["killReason"] = reason if on else None
    return _mutate(_f)


def is_killed(strategy_id: Optional[str] = None) -> tuple:
    """Return (killed: bool, reason: str|None) considering the global switch and
    any per-strategy kill for ``strategy_id``."""
    cfg = get_config()
    if cfg.get("killSwitch"):
        return True, cfg.get("killReason")
    if strategy_id:
        reason = (cfg.get("strategyKills") or {}).get(strategy_id)
        if reason:
            return True, reason
    return False, None


# ------------------------------- audit -------------------------------
def append_audit(
    *,
    action: str,
    summary: str,
    decision: Optional[str] = None,
    category: str = "compliance",
    target: Optional[str] = None,
    strategy_id: Optional[str] = None,
    strategy_name: Optional[str] = None,
    detail: Optional[dict] = None,
    actor_user_id: Optional[str] = None,
    actor_name: Optional[str] = None,
    firm_id: Optional[str] = None,
) -> dict:
    """Append one entry to the caller's firm audit trail. Best-effort: never raises.

    The acting user is taken from explicit ``actor_*`` args when given, else from
    the request-scoped :func:`tenant.current_actor` (so a deep gate call is still
    attributed), else recorded as the system. ``category`` groups entries (e.g.
    ``compliance``, ``trade``, ``strategy``, ``auth``); ``target`` is the subject
    the action acted on. The table is append-only — there is no update path."""
    fid = tenant.resolve_firm(firm_id)
    if actor_user_id is None:
        actor = tenant.current_actor()
        if actor:
            actor_user_id = actor.get("userId")
            actor_name = actor_name or actor.get("name")
    # A human action with no resolvable actor still gets a stable system label so
    # the trail never has unattributed rows.
    if not actor_user_id:
        actor_user_id = "system"
        actor_name = actor_name or "System"
    # The compliance gate uses strategy as its subject; carry it into target so
    # the unified viewer has a subject for every row regardless of category.
    if target is None and strategy_name:
        target = strategy_name
    entry = {
        "id": uuid.uuid4().hex[:12],
        "at": _now_iso(),
        "category": category,
        "action": action,
        "target": target,
        "strategyId": strategy_id,
        "strategyName": strategy_name,
        "decision": decision,
        "summary": summary,
        "actorUserId": actor_user_id,
        "actorName": actor_name,
        "detail": detail or {},
    }
    _ensure_schema()
    if db.db_available():
        try:
            db.execute(
                """
                INSERT INTO compliance_audit
                    (id, firm_id, at, category, action, target, strategy_id,
                     strategy_name, decision, summary, actor_user_id, actor_name, detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    entry["id"], fid, entry["at"], category, action, target, strategy_id,
                    strategy_name, decision, summary, actor_user_id, actor_name,
                    json.dumps(entry["detail"]),
                ),
            )
            return entry
        except Exception as exc:  # noqa: BLE001
            log.warning("append_audit DB error: %s", exc)
    with _mem_lock:
        trail = _mem_audit.setdefault(fid, [])
        trail.insert(0, entry)
        del trail[500:]
    return entry


def list_audit(
    limit: int = 50,
    firm_id: Optional[str] = None,
    category: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    action: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> List[dict]:
    """Return the firm's audit entries, newest first, with optional filters.

    ``category``/``actor_user_id``/``action`` are exact matches; ``since``/
    ``until`` bound the ISO timestamp (inclusive)."""
    _ensure_schema()
    fid = tenant.resolve_firm(firm_id)
    limit = max(1, min(int(limit or 50), 500))
    if db.db_available():
        try:
            clauses = ["firm_id = %s"]
            args: List = [fid]
            if category:
                clauses.append("category = %s")
                args.append(category)
            if actor_user_id:
                clauses.append("actor_user_id = %s")
                args.append(actor_user_id)
            if action:
                clauses.append("action = %s")
                args.append(action)
            if since:
                clauses.append("at >= %s")
                args.append(since)
            if until:
                clauses.append("at <= %s")
                args.append(until)
            args.append(limit)
            rows = db.query(
                f"SELECT * FROM compliance_audit WHERE {' AND '.join(clauses)} "
                "ORDER BY at DESC LIMIT %s",
                tuple(args),
            )
            return [_row_to_entry(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.warning("list_audit DB error: %s", exc)
    with _mem_lock:
        out: List[dict] = []
        for e in _mem_audit.get(fid, []):
            if category and e.get("category") != category:
                continue
            if actor_user_id and e.get("actorUserId") != actor_user_id:
                continue
            if action and e.get("action") != action:
                continue
            if since and (e.get("at") or "") < since:
                continue
            if until and (e.get("at") or "") > until:
                continue
            out.append(dict(e))
            if len(out) >= limit:
                break
        return out


def _row_to_entry(r: dict) -> dict:
    at = r.get("at")
    return {
        "id": r.get("id"),
        "at": at.isoformat() if hasattr(at, "isoformat") else str(at),
        "category": r.get("category") or "compliance",
        "action": r.get("action"),
        "target": r.get("target") or r.get("strategy_name"),
        "strategyId": r.get("strategy_id"),
        "strategyName": r.get("strategy_name"),
        "decision": r.get("decision"),
        "summary": r.get("summary"),
        "actorUserId": r.get("actor_user_id") or "system",
        "actorName": r.get("actor_name") or "System",
        "detail": r.get("detail") or {},
    }


def audit_actors(firm_id: Optional[str] = None) -> List[dict]:
    """Distinct (userId, name) pairs that appear in the firm's audit trail —
    used to populate the viewer's user filter."""
    _ensure_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            rows = db.query(
                "SELECT actor_user_id, MAX(actor_name) AS actor_name "
                "FROM compliance_audit WHERE firm_id = %s AND actor_user_id IS NOT NULL "
                "GROUP BY actor_user_id ORDER BY MAX(actor_name)",
                (fid,),
            )
            return [
                {"userId": r.get("actor_user_id"), "name": r.get("actor_name") or r.get("actor_user_id")}
                for r in rows
            ]
        except Exception as exc:  # noqa: BLE001
            log.warning("audit_actors DB error: %s", exc)
    with _mem_lock:
        seen: Dict[str, str] = {}
        for e in _mem_audit.get(fid, []):
            uid = e.get("actorUserId")
            if uid and uid not in seen:
                seen[uid] = e.get("actorName") or uid
        return [{"userId": k, "name": v} for k, v in sorted(seen.items(), key=lambda kv: kv[1])]


def audit_categories(firm_id: Optional[str] = None) -> List[str]:
    """Distinct categories present in the firm's audit trail — for the viewer's
    action-type filter."""
    _ensure_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            rows = db.query(
                "SELECT DISTINCT category FROM compliance_audit "
                "WHERE firm_id = %s AND category IS NOT NULL ORDER BY category",
                (fid,),
            )
            return [r.get("category") for r in rows if r.get("category")]
        except Exception as exc:  # noqa: BLE001
            log.warning("audit_categories DB error: %s", exc)
    with _mem_lock:
        cats = {e.get("category") for e in _mem_audit.get(fid, []) if e.get("category")}
        return sorted(cats)


def clear_audit(firm_id: Optional[str] = None) -> int:
    _ensure_schema()
    fid = tenant.resolve_firm(firm_id)
    if db.db_available():
        try:
            db.execute("DELETE FROM compliance_audit WHERE firm_id = %s", (fid,))
            return 0
        except Exception as exc:  # noqa: BLE001
            log.warning("clear_audit DB error: %s", exc)
    with _mem_lock:
        trail = _mem_audit.get(fid, [])
        n = len(trail)
        _mem_audit[fid] = []
        return n
