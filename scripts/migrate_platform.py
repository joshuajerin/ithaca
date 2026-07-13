#!/usr/bin/env python
"""Apply the ordered platform system-of-record migrations."""

from __future__ import annotations

import os

from doomberg_platform import open_db


def main() -> int:
    dsn = os.environ.get("DOOMBERG_DB", "")
    if not dsn:
        raise SystemExit("DOOMBERG_DB must be set")
    os.environ["DOOMBERG_DB_MIGRATION_MODE"] = "apply"
    db = open_db(dsn)
    status = getattr(db, "migration_status", None)
    db.close()
    if status is None:
        print("platform SQLite schema ready")
    else:
        print(f"platform schema ready at migration {status.current_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
