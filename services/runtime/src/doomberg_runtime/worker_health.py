"""Kubernetes readiness check for dedicated backtest workers."""

from __future__ import annotations

import os

from doomberg_platform import open_db

from .artifact_storage import object_storage_configured


def main() -> int:
    db_url = os.environ.get("DOOMBERG_DB", "").strip()
    if not db_url:
        return 1
    handle = open_db(db_url)
    try:
        handle.conn.execute("SELECT 1").fetchone()
    finally:
        handle.close()
    if os.environ.get("DOOMBERG_ENV", "").lower() in {"prod", "production"}:
        if not object_storage_configured():
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
