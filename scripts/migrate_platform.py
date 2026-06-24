#!/usr/bin/env python
"""Apply the platform system-of-record schema.

The platform DB adapter applies idempotent DDL on open. Keeping this as a deploy role lets
Kubernetes run the migration in an init container before the API/worker containers start.
"""

from __future__ import annotations

import os

from doomberg_platform import open_db


def main() -> int:
    dsn = os.environ.get("DOOMBERG_DB", "")
    if not dsn:
        raise SystemExit("DOOMBERG_DB must be set")
    db = open_db(dsn)
    db.close()
    print("platform schema ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
