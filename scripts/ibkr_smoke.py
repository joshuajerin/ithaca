#!/usr/bin/env python3
"""Read-only IBKR engine quote smoke."""

from __future__ import annotations

import argparse
import json
import sys

from doomberg_core.providers import IbkrEngineClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a read-only IBKR engine quote smoke.")
    parser.add_argument("--symbol", default="AAPL", help="Symbol to request from the quote route.")
    parser.add_argument("--tenant-id", default=None, help="Optional tenant id sent as X-Tenant-Id.")
    parser.add_argument(
        "--max-freshness-ms",
        type=int,
        default=None,
        help="Fail if quote freshness exceeds this limit. Env fallback: DOOMBERG_IBKR_SMOKE_MAX_FRESHNESS_MS.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full sanitized JSON diagnosis.")
    args = parser.parse_args(argv)

    result = IbkrEngineClient().diagnose_quote(
        symbol=args.symbol,
        tenant_id=args.tenant_id,
        max_freshness_ms=args.max_freshness_ms,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        status = "ok" if result.get("ok") else "failed"
        host = result.get("host") or "unconfigured"
        latency = result.get("latency_ms")
        quote = result.get("quote") or {}
        price = quote.get("price")
        freshness = quote.get("freshness_ms")
        print(
            f"IBKR smoke {status}: symbol={result.get('symbol')} host={host} "
            f"status={result.get('status')} price={price} freshness_ms={freshness} "
            f"latency_ms={latency}"
        )
        if not result.get("ok") and result.get("error"):
            print(f"error: {result['error']}", file=sys.stderr)
            print(f"recovery: {result.get('recovery_action')}", file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
