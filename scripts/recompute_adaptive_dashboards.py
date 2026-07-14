#!/usr/bin/env python
"""Manually recompute stored adaptive dashboard profiles."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from typing import Any

from ithaca_platform import Platform
from ithaca_runtime import AdaptiveDashboardWorker, recompute_user_profile


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    return date.fromisoformat(raw).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("ITHACA_DB", ":memory:"))
    parser.add_argument("--tenant-id")
    parser.add_argument("--user-id")
    parser.add_argument("--date", dest="generated_for_date")
    args = parser.parse_args(argv)

    generated_for_date = _parse_date(args.generated_for_date)
    platform = Platform(args.db)
    try:
        if args.tenant_id or args.user_id:
            if not args.tenant_id or not args.user_id:
                raise SystemExit("--tenant-id and --user-id must be provided together")
            profile = recompute_user_profile(
                platform,
                args.tenant_id,
                args.user_id,
                generated_for_date=generated_for_date,
            )
            result: dict[str, Any] = {"updated": [profile] if profile else [], "failed": []}
        else:
            result = AdaptiveDashboardWorker(platform).recompute_all(
                generated_for_date=generated_for_date
            )
    finally:
        platform.db.close()

    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
