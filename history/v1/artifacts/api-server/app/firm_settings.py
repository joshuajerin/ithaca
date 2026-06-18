"""Per-firm security settings (currently: the AI code-execution toggle).

The self-building feature pipeline and the runtime TSX panel compiler are
powerful, AI-driven code-execution paths. An admin must be able to turn the
*build* path off for their firm entirely (institutional kill-switch), so this
store holds a ``codegen_enabled`` flag keyed by firm.

Like the other stores in this app it is Postgres-backed (idempotent
``CREATE TABLE IF NOT EXISTS``; the Drizzle schema documents the shape) and
degrades to an in-process dict when no database is configured. The default is
*enabled* so existing firms keep working until an admin opts out.
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, Optional

from . import db

log = logging.getLogger(__name__)

_schema_ready = False
_schema_lock = threading.Lock()

# In-memory fallback (only used when no DB is available): firm_id -> settings.
_settings: Dict[str, dict] = {}
_mem_lock = threading.Lock()

DEFAULT_CODEGEN_ENABLED = True


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
                CREATE TABLE IF NOT EXISTS firm_settings (
                    firm_id text PRIMARY KEY,
                    codegen_enabled boolean NOT NULL DEFAULT true,
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            _schema_ready = True
        except Exception as exc:  # noqa: BLE001
            log.warning("firm_settings schema ensure failed: %s", exc)


def get_settings(firm_id: str) -> dict:
    """Return the firm's settings, falling back to defaults when unset."""
    _ensure_schema()
    enabled = DEFAULT_CODEGEN_ENABLED
    if firm_id and db.db_available():
        try:
            row = db.query_one(
                "SELECT codegen_enabled FROM firm_settings WHERE firm_id = %s",
                (firm_id,),
            )
            if row is not None:
                enabled = bool(row["codegen_enabled"])
            return {"codegenEnabled": enabled}
        except Exception as exc:  # noqa: BLE001
            log.warning("get_settings DB error: %s", exc)
    with _mem_lock:
        rec = _settings.get(firm_id)
        if rec is not None:
            enabled = bool(rec.get("codegenEnabled", DEFAULT_CODEGEN_ENABLED))
    return {"codegenEnabled": enabled}


def codegen_enabled(firm_id: str) -> bool:
    return bool(get_settings(firm_id).get("codegenEnabled", DEFAULT_CODEGEN_ENABLED))


def set_codegen_enabled(firm_id: str, enabled: bool) -> dict:
    """Persist the firm's code-execution toggle and return the new settings."""
    _ensure_schema()
    enabled = bool(enabled)
    if firm_id and db.db_available():
        try:
            db.execute(
                """
                INSERT INTO firm_settings (firm_id, codegen_enabled, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (firm_id)
                DO UPDATE SET codegen_enabled = EXCLUDED.codegen_enabled,
                              updated_at = now()
                """,
                (firm_id, enabled),
            )
            return {"codegenEnabled": enabled}
        except Exception as exc:  # noqa: BLE001
            log.warning("set_codegen_enabled DB error: %s", exc)
    with _mem_lock:
        _settings[firm_id] = {"codegenEnabled": enabled}
    return {"codegenEnabled": enabled}


def reset_for_tests() -> None:
    """Clear in-memory settings (test helper)."""
    with _mem_lock:
        _settings.clear()
