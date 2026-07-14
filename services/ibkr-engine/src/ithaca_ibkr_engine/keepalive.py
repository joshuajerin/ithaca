from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .client_portal import ClientPortalError, ClientPortalGateway, public_auth_status


def _payload(ok: bool, **extra: Any) -> dict[str, Any]:
    return {"ok": ok, "authenticated": ok, **extra}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Keep the IBKR /iserver brokerage session authenticated."
    )
    parser.add_argument("--json", action="store_true", help="Print a JSON status payload.")
    args = parser.parse_args(argv)

    try:
        status = ClientPortalGateway().ensure_authenticated()
        ok = bool(status.get("authenticated")) and bool(status.get("connected"))
        body = _payload(ok, status=public_auth_status(status))
    except ClientPortalError as exc:
        body = _payload(False, error=str(exc))

    if args.json:
        print(json.dumps(body, sort_keys=True))
    elif body["ok"]:
        print("IBKR /iserver authenticated and connected")
    else:
        print(f"IBKR /iserver unavailable: {body.get('error')}", file=sys.stderr)

    return 0 if body["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
