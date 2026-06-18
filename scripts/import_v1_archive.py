#!/usr/bin/env python
"""Bulk-load the v1 market-data archive into Postgres.

Reads ``data/v1_archive.json`` (240,220 rows across 15 tables) and loads each into
``archive.<tbl>``. Idempotent: each table is truncated then COPYed.

Usage:
    export DOOMBERG_ARCHIVE_URL=postgresql://user:pass@host:5432/dbname
    python scripts/import_v1_archive.py [--json PATH] [--no-truncate]

The DSN is read from ``DOOMBERG_ARCHIVE_URL``. For the cloud load, point it at the
DigitalOcean Managed Postgres connection string. See
``services/data-archive/RUNBOOK.md`` for the one-command production runbook.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from doomberg_archive.loader import load_archive

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_JSON = _REPO_ROOT / "data" / "v1_archive.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load the v1 archive into Postgres.")
    parser.add_argument(
        "--json", default=str(_DEFAULT_JSON),
        help="path to v1_archive.json (default: data/v1_archive.json)",
    )
    parser.add_argument(
        "--no-truncate", action="store_true",
        help="append instead of truncate-then-load (default: truncate for idempotency)",
    )
    parser.add_argument(
        "--no-create-schema", action="store_true",
        help="skip CREATE SCHEMA/TABLE (assume they already exist)",
    )
    args = parser.parse_args(argv)

    dsn = os.environ.get("DOOMBERG_ARCHIVE_URL")
    if not dsn:
        print(
            "ERROR: DOOMBERG_ARCHIVE_URL is not set.\n"
            "  export DOOMBERG_ARCHIVE_URL=postgresql://user:pass@host:5432/dbname",
            file=sys.stderr,
        )
        return 2

    json_path = Path(args.json)
    if not json_path.exists():
        print(f"ERROR: archive JSON not found at {json_path}", file=sys.stderr)
        return 2

    print(f"Loading {json_path} -> archive.* (truncate={not args.no_truncate})")
    started = time.monotonic()
    counts = load_archive(
        dsn,
        json_path,
        create_schema=not args.no_create_schema,
        truncate=not args.no_truncate,
        log=lambda msg: print(f"  {msg}"),
    )
    elapsed = time.monotonic() - started
    total = sum(counts.values())
    print(f"\nDone: {total} rows across {len(counts)} tables in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
