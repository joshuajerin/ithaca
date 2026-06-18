"""Apply the canonical archive schema to the live Postgres archive DB.

Run idempotently on every deploy (all DDL uses CREATE TABLE/INDEX IF NOT EXISTS)
so new tables appear automatically without manual intervention.

Usage:
    python scripts/migrate_archive.py            # uses DOOMBERG_ARCHIVE_URL
    python scripts/migrate_archive.py <dsn>      # explicit DSN
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "services/data-archive/src/doomberg_archive/schema.sql"
)


def main() -> None:
    dsn = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DOOMBERG_ARCHIVE_URL", "")
    if not dsn:
        print("ERROR: no DSN — set DOOMBERG_ARCHIVE_URL or pass as first arg", file=sys.stderr)
        sys.exit(1)

    sql = SCHEMA.read_text()

    import psycopg  # noqa: PLC0415

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql)

    print(f"migrate_archive: schema applied OK ({SCHEMA})")


if __name__ == "__main__":
    main()
