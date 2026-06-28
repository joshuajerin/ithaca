#!/usr/bin/env python3
"""Interactive Doomberg MCP installer for local coding agents.

The installer opens the Doomberg web app, receives a one-time key from the signed-in
browser session on a localhost callback, then registers the hosted MCP endpoint with
Codex using its supported streamable-HTTP MCP config.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import shlex
import shutil
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

DEFAULT_APP_URL = "https://app.doomberg.me"
DEFAULT_MCP_URL = "https://mcp.doomberg.me/mcp"
ENV_FILE = Path.home() / ".config" / "doomberg" / "mcp.env"
SHELL_MARKER = "# Doomberg MCP environment"


class CallbackState:
    def __init__(self, expected_state: str) -> None:
        self.expected_state = expected_state
        self.event = threading.Event()
        self.payload: dict[str, Any] | None = None
        self.error: str | None = None


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "content-type")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def _handler(state: CallbackState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_OPTIONS(self) -> None:  # noqa: N802
            _json_response(self, 200, {"ok": True})

        def do_POST(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] != "/callback":
                _json_response(self, 404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("content-length", "0"))
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                _json_response(self, 400, {"error": f"invalid json: {exc}"})
                return

            if payload.get("state") != state.expected_state:
                state.error = "state mismatch"
                state.event.set()
                _json_response(self, 403, {"error": "state mismatch"})
                return
            api_key = str(payload.get("api_key") or "")
            if not api_key.startswith("dmbg_"):
                state.error = "approval did not return a Doomberg API key"
                state.event.set()
                _json_response(self, 400, {"error": state.error})
                return
            state.payload = payload
            state.event.set()
            _json_response(self, 200, {"ok": True})

    return Handler


def _agent_link_url(app_url: str, callback_url: str, state: str, mcp_url: str,
                    name: str, client: str) -> str:
    parts = urlsplit(app_url)
    base = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") or "", "", ""))
    params = urlencode(
        {
            "callback": callback_url,
            "state": state,
            "mcp_url": mcp_url,
            "name": name,
            "client": client,
        },
        quote_via=quote,
    )
    return f"{base}/#/agent-link?{params}"


def _write_env_file(api_key: str, mcp_url: str) -> None:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Written by Doomberg MCP installer. Keep this file private.",
        f"export DOOMBERG_MCP_API_KEY={shlex.quote(api_key)}",
        f"export DOOMBERG_MCP_URL={shlex.quote(mcp_url)}",
        "",
    ]
    ENV_FILE.write_text("\n".join(lines), encoding="utf-8")
    os.chmod(ENV_FILE, 0o600)


def _ensure_shell_sources_env() -> None:
    source_line = f'{SHELL_MARKER}\n[ -f "{ENV_FILE}" ] && . "{ENV_FILE}"\n'
    candidates = [Path.home() / ".zshrc", Path.home() / ".bashrc"]
    shell = os.environ.get("SHELL", "")
    preferred = Path.home() / (".zshrc" if shell.endswith("zsh") else ".bashrc")
    if preferred not in candidates:
        candidates.insert(0, preferred)
    for rc in candidates:
        if rc.exists() or rc == preferred:
            current = rc.read_text(encoding="utf-8") if rc.exists() else ""
            if str(ENV_FILE) not in current:
                with rc.open("a", encoding="utf-8") as fh:
                    if current and not current.endswith("\n"):
                        fh.write("\n")
                    fh.write("\n" + source_line)
            return


def _set_launchctl_env(api_key: str, mcp_url: str) -> None:
    if platform.system() != "Darwin" or shutil.which("launchctl") is None:
        return
    subprocess.run(["launchctl", "setenv", "DOOMBERG_MCP_API_KEY", api_key], check=False)
    subprocess.run(["launchctl", "setenv", "DOOMBERG_MCP_URL", mcp_url], check=False)


def _install_codex_mcp(name: str, mcp_url: str) -> None:
    codex = shutil.which("codex")
    if codex is None:
        print("codex CLI not found on PATH; wrote the token env but did not update Codex MCP config.")
        print(f"Run manually: codex mcp add {name} --url {mcp_url} "
              "--bearer-token-env-var DOOMBERG_MCP_API_KEY")
        return
    subprocess.run([codex, "mcp", "remove", name], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=False)
    subprocess.run(
        [
            codex,
            "mcp",
            "add",
            name,
            "--url",
            mcp_url,
            "--bearer-token-env-var",
            "DOOMBERG_MCP_API_KEY",
        ],
        check=True,
    )


def _wait_for_payload(state: CallbackState, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        if state.event.wait(min(1.0, remaining)):
            if state.error:
                raise SystemExit(state.error)
            if state.payload:
                return state.payload
    raise SystemExit("Timed out waiting for browser approval.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Doomberg MCP into a local agent.")
    parser.add_argument("--app-url", default=os.environ.get("DOOMBERG_APP_URL", DEFAULT_APP_URL))
    parser.add_argument("--mcp-url", default=os.environ.get("DOOMBERG_MCP_URL", DEFAULT_MCP_URL))
    parser.add_argument("--name", default="doomberg")
    parser.add_argument("--client", choices=["codex"], default="codex")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)

    state_token = secrets.token_urlsafe(24)
    callback_state = CallbackState(state_token)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(callback_state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    callback_url = f"http://127.0.0.1:{server.server_port}/callback"
    link = _agent_link_url(args.app_url, callback_url, state_token, args.mcp_url,
                           args.name, args.client)
    print("Open this URL to sign in and approve Doomberg MCP:")
    print(link)
    if not args.no_open:
        webbrowser.open(link)

    try:
        payload = _wait_for_payload(callback_state, args.timeout)
    finally:
        server.shutdown()
        server.server_close()

    api_key = str(payload["api_key"])
    mcp_url = str(payload.get("mcp_url") or args.mcp_url)
    _write_env_file(api_key, mcp_url)
    _ensure_shell_sources_env()
    _set_launchctl_env(api_key, mcp_url)
    _install_codex_mcp(args.name, mcp_url)

    key_id = payload.get("key_id", "")
    print(f"\nDoomberg MCP installed as '{args.name}' for Codex.")
    if key_id:
        print(f"Key id: {key_id}")
    print(f"Token env: {ENV_FILE}")
    print("\nNext step: open your agent and ask it to research something, e.g.:")
    print('  "Use Doomberg to research NVDA — pull price history, screen peers,')
    print('   propose a momentum strategy, and backtest it."')
    print("\nThe agent will stream its work into the Doomberg web UI as a live trace.")
    print("Restart Codex desktop if it was already open so it picks up the launchd env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
