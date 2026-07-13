#!/usr/bin/env python3
"""Approve email addresses for Doomberg through Clerk's managed waitlist."""

from __future__ import annotations

import argparse
import json
import os
import sys

from doomberg_platform import ClerkApiError, ClerkWaitlistService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Invite approved email addresses from the Clerk waitlist."
    )
    parser.add_argument("emails", nargs="+", help="Email addresses to approve")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    secret_key = os.environ.get("CLERK_SECRET_KEY", "").strip()
    if not secret_key:
        print("CLERK_SECRET_KEY is required", file=sys.stderr)
        return 2

    service = ClerkWaitlistService(
        secret_key,
        api_url=os.environ.get("CLERK_API_URL", "https://api.clerk.com/v1"),
        api_version=os.environ.get("CLERK_API_VERSION", "2026-05-12"),
        timeout_s=float(os.environ.get("CLERK_API_TIMEOUT_S", "5")),
    )
    failed = False
    for email in args.emails:
        try:
            result = service.approve(email)
        except (ClerkApiError, ValueError) as exc:
            failed = True
            print(json.dumps({"email_address": email, "error": str(exc)}), file=sys.stderr)
        else:
            print(json.dumps(result, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
