#!/usr/bin/env python3
"""Local IBKR OAuth 1.0a setup helper.

This is intentionally a client-side setup utility. It does not persist tokens
unless --out is supplied, and it never reads Doomberg service env files.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import secrets
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zlib
from pathlib import Path
from typing import Any


DEFAULT_API_BASE_URL = "https://api.ibkr.com/v1/api"
DEFAULT_AUTHORIZE_URL = "https://interactivebrokers.com/authorize"
SIGNATURE_METHOD = "RSA-SHA256"


class IbkrOAuthError(RuntimeError):
    pass


def _env(name: str, value: str | None) -> str | None:
    return value if value is not None else os.environ.get(name)


def _require(name: str, value: str | None) -> str:
    if value:
        return value
    raise IbkrOAuthError(f"missing {name}")


def _rfc3986(value: str) -> str:
    return urllib.parse.quote(value, safe="~")


def _nonce() -> str:
    return secrets.token_hex(16)


def _realm(consumer_key: str, override: str | None) -> str:
    if override:
        return override
    return "test_realm" if consumer_key == "TESTCONS" else "limited_poa"


def _base_url(raw: str | None) -> str:
    return (raw or DEFAULT_API_BASE_URL).rstrip("/")


def _endpoint(base_url: str, path: str) -> str:
    return f"{base_url}{path}"


def _signature_base_string(method: str, url: str, params: dict[str, str]) -> str:
    param_string = "&".join(f"{_rfc3986(k)}={_rfc3986(v)}" for k, v in sorted(params.items()))
    return "&".join((_rfc3986(method.upper()), _rfc3986(url), _rfc3986(param_string)))


def _rsa_sha256_signature(base_string: str, private_key_path: str) -> str:
    key = Path(private_key_path).expanduser()
    if not key.exists():
        raise IbkrOAuthError(f"signature key does not exist: {key}")
    try:
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(key), "-binary"],
            input=base_string.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise IbkrOAuthError("openssl is required for RSA-SHA256 signing") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise IbkrOAuthError(f"openssl signing failed: {detail}")
    return base64.b64encode(proc.stdout).decode("ascii")


def _authorization_header(params: dict[str, str], realm: str) -> str:
    header_params = {**params, "realm": realm}
    encoded = ", ".join(
        f'{_rfc3986(k)}="{_rfc3986(v)}"' for k, v in sorted(header_params.items())
    )
    return f"OAuth {encoded}"


def _signed_header(
    *,
    method: str,
    url: str,
    params: dict[str, str],
    realm: str,
    private_key_path: str,
) -> str:
    signing_params = dict(params)
    base_string = _signature_base_string(method, url, signing_params)
    signing_params["oauth_signature"] = _rsa_sha256_signature(base_string, private_key_path)
    return _authorization_header(signing_params, realm)


def _post_json(url: str, authorization: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=b"",
        method="POST",
        headers={
            "Accept": "*/*",
            "Accept-Encoding": "gzip,deflate",
            "Authorization": authorization,
            "Connection": "keep-alive",
            "Content-Length": "0",
            "User-Agent": "doomberg-ibkr-oauth/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read()
            encoding = resp.headers.get("Content-Encoding", "").lower()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise IbkrOAuthError(f"IBKR HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise IbkrOAuthError(f"IBKR request failed: {exc.reason}") from exc

    if encoding == "gzip":
        payload = gzip.decompress(payload)
    elif encoding == "deflate":
        payload = zlib.decompress(payload)

    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise IbkrOAuthError(f"IBKR returned non-JSON response: {payload[:200]!r}") from exc


def request_token(
    *,
    consumer_key: str,
    signature_key: str,
    callback: str,
    realm: str,
    api_base_url: str,
) -> dict[str, Any]:
    url = _endpoint(api_base_url, "/oauth/request_token")
    params = {
        "oauth_callback": callback,
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": _nonce(),
        "oauth_signature_method": SIGNATURE_METHOD,
        "oauth_timestamp": str(int(time.time())),
    }
    auth_header = _signed_header(
        method="POST",
        url=url,
        params=params,
        realm=realm,
        private_key_path=signature_key,
    )
    return _post_json(url, auth_header)


def access_token(
    *,
    consumer_key: str,
    signature_key: str,
    callback: str,
    realm: str,
    api_base_url: str,
    request_token_value: str,
    verifier: str,
) -> dict[str, Any]:
    url = _endpoint(api_base_url, "/oauth/access_token")
    params = {
        "oauth_callback": callback,
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": _nonce(),
        "oauth_signature_method": SIGNATURE_METHOD,
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": request_token_value,
        "oauth_verifier": verifier,
    }
    auth_header = _signed_header(
        method="POST",
        url=url,
        params=params,
        realm=realm,
        private_key_path=signature_key,
    )
    return _post_json(url, auth_header)


def _token_from_callback_url(value: str) -> tuple[str | None, str | None]:
    parsed = urllib.parse.urlparse(value)
    query = urllib.parse.parse_qs(parsed.query)
    token = (query.get("oauth_token") or [None])[0]
    verifier = (query.get("oauth_verifier") or [None])[0]
    return token, verifier


def _write_json(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    out.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"wrote {out}")


def _common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--consumer-key", default=None, help="Env fallback: IBKR_OAUTH_CONSUMER_KEY")
    parser.add_argument(
        "--signature-key",
        default=None,
        help="Path to RSA private signing key. Env fallback: IBKR_OAUTH_SIGNATURE_KEY",
    )
    parser.add_argument("--callback", default=None, help="Env fallback: IBKR_OAUTH_CALLBACK; default: oob")
    parser.add_argument("--realm", default=None, help="Env fallback: IBKR_OAUTH_REALM")
    parser.add_argument(
        "--api-base-url",
        default=None,
        help=f"Env fallback: IBKR_OAUTH_API_BASE_URL; default: {DEFAULT_API_BASE_URL}",
    )
    parser.add_argument(
        "--authorize-url",
        default=None,
        help=f"Env fallback: IBKR_OAUTH_AUTHORIZE_URL; default: {DEFAULT_AUTHORIZE_URL}",
    )


def _config(args: argparse.Namespace) -> dict[str, str]:
    consumer_key = _require(
        "IBKR_OAUTH_CONSUMER_KEY or --consumer-key",
        _env("IBKR_OAUTH_CONSUMER_KEY", args.consumer_key),
    )
    signature_key = _require(
        "IBKR_OAUTH_SIGNATURE_KEY or --signature-key",
        _env("IBKR_OAUTH_SIGNATURE_KEY", args.signature_key),
    )
    callback = _env("IBKR_OAUTH_CALLBACK", args.callback) or "oob"
    return {
        "api_base_url": _base_url(_env("IBKR_OAUTH_API_BASE_URL", args.api_base_url)),
        "authorize_url": _env("IBKR_OAUTH_AUTHORIZE_URL", args.authorize_url)
        or DEFAULT_AUTHORIZE_URL,
        "callback": callback,
        "consumer_key": consumer_key,
        "realm": _realm(consumer_key, _env("IBKR_OAUTH_REALM", args.realm)),
        "signature_key": signature_key,
    }


def cmd_request_token(args: argparse.Namespace) -> int:
    config = _config(args)
    payload = request_token(
        **{
            k: config[k]
            for k in ("consumer_key", "signature_key", "callback", "realm", "api_base_url")
        }
    )
    token = _require("oauth_token in IBKR response", str(payload.get("oauth_token") or ""))
    authorize = f"{config['authorize_url']}?oauth_token={urllib.parse.quote(token)}"
    out = {"authorize_url": authorize, "oauth_token": token}
    _write_json(args.out, out)
    if args.open:
        webbrowser.open(authorize)
    return 0


def cmd_access_token(args: argparse.Namespace) -> int:
    config = _config(args)
    callback_token = callback_verifier = None
    if args.callback_url:
        callback_token, callback_verifier = _token_from_callback_url(args.callback_url)
    request_token_value = _require(
        "--request-token or oauth_token in --callback-url",
        args.request_token or callback_token,
    )
    verifier = _require(
        "--verifier or oauth_verifier in --callback-url",
        args.verifier or callback_verifier,
    )
    payload = access_token(
        **{
            k: config[k]
            for k in ("consumer_key", "signature_key", "callback", "realm", "api_base_url")
        },
        request_token_value=request_token_value,
        verifier=verifier,
    )
    _write_json(args.out, payload)
    return 0


def cmd_flow(args: argparse.Namespace) -> int:
    config = _config(args)
    initial = request_token(
        **{
            k: config[k]
            for k in ("consumer_key", "signature_key", "callback", "realm", "api_base_url")
        }
    )
    request_token_value = _require("oauth_token in IBKR response", str(initial.get("oauth_token") or ""))
    authorize = f"{config['authorize_url']}?oauth_token={urllib.parse.quote(request_token_value)}"
    print(f"Open this URL and approve IBKR access:\n{authorize}\n")
    if args.open:
        webbrowser.open(authorize)
    callback_value = input("Paste the full callback URL or oauth_verifier: ").strip()
    callback_token, callback_verifier = _token_from_callback_url(callback_value)
    if callback_token and callback_token != request_token_value:
        raise IbkrOAuthError("callback oauth_token does not match the request token")
    verifier = callback_verifier or callback_value
    payload = access_token(
        **{
            k: config[k]
            for k in ("consumer_key", "signature_key", "callback", "realm", "api_base_url")
        },
        request_token_value=request_token_value,
        verifier=verifier,
    )
    _write_json(args.out, payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local IBKR OAuth 1.0a request-token and access-token setup."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    request_parser = sub.add_parser("request-token", help="Create an IBKR OAuth request token.")
    _common_args(request_parser)
    request_parser.add_argument("--open", action="store_true", help="Open the authorize URL.")
    request_parser.add_argument("--out", default=None, help="Optional 0600 JSON output path.")
    request_parser.set_defaults(func=cmd_request_token)

    access_parser = sub.add_parser("access-token", help="Exchange request token + verifier.")
    _common_args(access_parser)
    access_parser.add_argument("--request-token", default=None, help="Request token from request-token.")
    access_parser.add_argument("--verifier", default=None, help="oauth_verifier from IBKR approval.")
    access_parser.add_argument("--callback-url", default=None, help="Full callback URL containing both values.")
    access_parser.add_argument("--out", default=None, help="Optional 0600 JSON output path.")
    access_parser.set_defaults(func=cmd_access_token)

    flow_parser = sub.add_parser("flow", help="Run request-token, browser approval, and access-token.")
    _common_args(flow_parser)
    flow_parser.add_argument("--open", action="store_true", help="Open the authorize URL.")
    flow_parser.add_argument("--out", default=None, help="Optional 0600 JSON output path.")
    flow_parser.set_defaults(func=cmd_flow)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except IbkrOAuthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
