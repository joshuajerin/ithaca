"""Persistence for real IEX DEEP order-book replays + their reconstruction jobs.

Reconstructing a session is slow (a full DEEP day is ~13 GB gzipped, ~20 min to
stream-parse), so it must never run in the request path. Instead:

  - the order-book skill serves a cached **real** replay when one exists, else it
    enqueues a job and returns a clearly-labelled synthetic fallback;
  - the background worker drains pending jobs, reconstructs in one streaming pass,
    persists the result here, and flips the job status.

Storage mirrors the rest of the backend: a Postgres table when ``DATABASE_URL``
is set (JSON written as ``json.dumps(...)::jsonb``), with an in-process
dict fallback so the feature still works (within the running process) when the
DB is unavailable.

Multi-tenancy note: order-book replays are **shared by design** and intentionally
NOT firm-scoped. A reconstructed session is firm-agnostic market data (real venue
depth for a symbol/date), identical for every firm and expensive to rebuild, so it
is cached once and served to all tenants. This is the deliberate exception to the
per-firm isolation applied to every user-owned store.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import db

log = logging.getLogger("terminal.orderbook_store")

_schema_ready = False
_schema_lock = threading.Lock()

# In-process fallbacks (used only when the DB is unavailable). Keyed appropriately.
_replay_mem: Dict[tuple, dict] = {}        # (symbol, session) -> record
_job_mem: Dict[str, dict] = {}             # symbol -> {status, session, detail, updated_at}
_mem_lock = threading.Lock()

_ACTIVE = ("pending", "running")


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
                CREATE TABLE IF NOT EXISTS order_book_replay (
                    symbol text NOT NULL,
                    session text NOT NULL,
                    payload jsonb NOT NULL,
                    source text,
                    as_of text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (symbol, session)
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS order_book_jobs (
                    symbol text PRIMARY KEY,
                    session text,
                    status text NOT NULL DEFAULT 'pending',
                    detail text,
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            _schema_ready = True
        except Exception as exc:  # noqa: BLE001
            log.warning("order-book schema ensure failed: %s", exc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Replays
# --------------------------------------------------------------------------- #
def save_replay(symbol: str, session: str, payload: dict, source: str, as_of: str) -> None:
    sym = symbol.upper()
    _ensure_schema()
    if db.db_available():
        try:
            db.execute(
                """
                INSERT INTO order_book_replay (symbol, session, payload, source, as_of)
                VALUES (%s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (symbol, session) DO UPDATE
                SET payload = EXCLUDED.payload, source = EXCLUDED.source,
                    as_of = EXCLUDED.as_of, created_at = now()
                """,
                (sym, session, json.dumps(payload), source, as_of),
            )
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("save_replay DB error for %s: %s", sym, exc)
    with _mem_lock:
        _replay_mem[(sym, session)] = {
            "symbol": sym, "session": session, "payload": payload,
            "source": source, "asOf": as_of,
        }


def latest_replay(symbol: str) -> Optional[dict]:
    """Most recent stored real replay for ``symbol`` as
    ``{session, payload, source, asOf}`` (or ``None``)."""
    sym = symbol.upper()
    _ensure_schema()
    if db.db_available():
        try:
            row = db.query_one(
                "SELECT session, payload, source, as_of FROM order_book_replay "
                "WHERE symbol = %s ORDER BY session DESC LIMIT 1",
                (sym,),
            )
            if row:
                payload = row["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return {
                    "session": row["session"], "payload": payload,
                    "source": row["source"], "asOf": row["as_of"],
                }
            return None
        except Exception as exc:  # noqa: BLE001
            log.warning("latest_replay DB error for %s: %s", sym, exc)
    with _mem_lock:
        recs = [v for (s, _), v in _replay_mem.items() if s == sym]
    if not recs:
        return None
    best = max(recs, key=lambda r: r["session"])
    return {"session": best["session"], "payload": best["payload"],
            "source": best["source"], "asOf": best["asOf"]}


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
def request_job(symbol: str) -> str:
    """Ensure a reconstruction job exists for ``symbol``; return its status.

    A brand-new symbol is enqueued ``pending``. A previously ``error``ed job is
    re-armed to ``pending`` (so re-opening the panel retries). ``done`` /
    ``unavailable`` / in-flight jobs are left untouched and their status is
    returned so the caller can word the fallback honestly."""
    sym = symbol.upper()
    _ensure_schema()
    if db.db_available():
        try:
            db.execute(
                """
                INSERT INTO order_book_jobs (symbol, status, updated_at)
                VALUES (%s, 'pending', now())
                ON CONFLICT (symbol) DO UPDATE
                SET status = 'pending', updated_at = now()
                WHERE order_book_jobs.status = 'error'
                """,
                (sym,),
            )
            row = db.query_one("SELECT status FROM order_book_jobs WHERE symbol = %s", (sym,))
            return row["status"] if row else "pending"
        except Exception as exc:  # noqa: BLE001
            log.warning("request_job DB error for %s: %s", sym, exc)
    with _mem_lock:
        cur = _job_mem.get(sym)
        if cur is None or cur.get("status") == "error":
            _job_mem[sym] = {"status": "pending", "session": None, "detail": None,
                             "updated_at": _now_iso()}
        return _job_mem[sym]["status"]


def job_status(symbol: str) -> Optional[str]:
    sym = symbol.upper()
    _ensure_schema()
    if db.db_available():
        try:
            row = db.query_one("SELECT status FROM order_book_jobs WHERE symbol = %s", (sym,))
            return row["status"] if row else None
        except Exception as exc:  # noqa: BLE001
            log.warning("job_status DB error for %s: %s", sym, exc)
    with _mem_lock:
        rec = _job_mem.get(sym)
        return rec["status"] if rec else None


def pending_jobs(limit: int = 8) -> List[str]:
    _ensure_schema()
    if db.db_available():
        try:
            rows = db.query(
                "SELECT symbol FROM order_book_jobs WHERE status = 'pending' "
                "ORDER BY updated_at ASC LIMIT %s",
                (limit,),
            )
            return [r["symbol"] for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.warning("pending_jobs DB error: %s", exc)
    with _mem_lock:
        return [s for s, r in _job_mem.items() if r.get("status") == "pending"][:limit]


def mark_job(symbol: str, status: str, session: Optional[str] = None,
             detail: Optional[str] = None) -> None:
    sym = symbol.upper()
    _ensure_schema()
    if db.db_available():
        try:
            db.execute(
                """
                INSERT INTO order_book_jobs (symbol, status, session, detail, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (symbol) DO UPDATE
                SET status = EXCLUDED.status, session = EXCLUDED.session,
                    detail = EXCLUDED.detail, updated_at = now()
                """,
                (sym, status, session, detail),
            )
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("mark_job DB error for %s: %s", sym, exc)
    with _mem_lock:
        _job_mem[sym] = {"status": status, "session": session, "detail": detail,
                         "updated_at": _now_iso()}
