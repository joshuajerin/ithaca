#!/usr/bin/env python3
"""Interactive Doomberg MCP installer for local coding agents.

The installer opens the Doomberg web app, receives a one-time key from the signed-in
browser session on a localhost callback, then registers the hosted MCP endpoint with
the selected local agent clients.
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
from urllib import error as urlerror
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

DEFAULT_APP_URL = "https://app.doomberg.me"
DEFAULT_MCP_URL = "https://mcp.doomberg.me/mcp"
ENV_FILE = Path.home() / ".config" / "doomberg" / "mcp.env"
SHELL_MARKER = "# Doomberg MCP environment"
CLIENT_ALIASES = {
    "all": "all",
    "cursor": "cursor",
    "claude": "claude-code",
    "claude-code": "claude-code",
    "claudecode": "claude-code",
    "codex": "codex",
    "openclaw": "openclaw",
    "hermes": "hermes",
}
DEFAULT_CLIENTS = ("cursor", "claude-code", "codex", "openclaw", "hermes")


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


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        backup = path.with_suffix(path.suffix + f".bak.{int(time.time())}")
        path.rename(backup)
        print(f"Could not parse {path}; moved it to {backup}: {exc}")
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_json_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _http_mcp_config(mcp_url: str, api_key: str) -> dict[str, Any]:
    return {
        "type": "http",
        "url": mcp_url,
        "headers": {
            "Authorization": f"Bearer {api_key}",
        },
    }


def _merge_mcp_json(path: Path, name: str, config: dict[str, Any]) -> None:
    data = _read_json_file(path)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers[name] = config
    data["mcpServers"] = servers
    _write_json_file(path, data)


def _install_cursor_mcp(name: str, mcp_url: str, api_key: str) -> str:
    path = Path.home() / ".cursor" / "mcp.json"
    _merge_mcp_json(path, name, _http_mcp_config(mcp_url, api_key))
    return f"Cursor: wrote {path}"


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


def _install_codex_mcp(name: str, mcp_url: str) -> str:
    codex = shutil.which("codex")
    if codex is None:
        return (
            "Codex: codex CLI not found; run manually: "
            f"codex mcp add {name} --url {mcp_url} "
            "--bearer-token-env-var DOOMBERG_MCP_API_KEY"
        )
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
        timeout=30,
    )
    return "Codex: registered with `codex mcp add --url`"


def _install_claude_code_mcp(name: str, mcp_url: str, api_key: str) -> str:
    claude = shutil.which("claude")
    if claude is None:
        path = Path.home() / ".claude" / "mcp.json"
        _merge_mcp_json(path, name, _http_mcp_config(mcp_url, api_key))
        return f"Claude Code: claude CLI not found; wrote {path}"
    subprocess.run([claude, "mcp", "remove", "--scope", "user", name],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    subprocess.run(
        [
            claude,
            "mcp",
            "add",
            "--transport",
            "http",
            "--scope",
            "user",
            "--header",
            f"Authorization: Bearer {api_key}",
            name,
            mcp_url,
        ],
        check=True,
        timeout=30,
    )
    return "Claude Code: registered with `claude mcp add --transport http`"


def _install_openclaw_mcp(name: str, mcp_url: str, api_key: str) -> str:
    path = Path.home() / ".openclaw" / "mcp.json"
    _merge_mcp_json(path, name, _http_mcp_config(mcp_url, api_key))
    return f"OpenClaw: wrote {path}"


def _install_hermes_mcp(name: str, mcp_url: str, api_key: str) -> str:
    path = Path.home() / ".hermes" / "mcp.json"
    _merge_mcp_json(path, name, _http_mcp_config(mcp_url, api_key))
    return f"Hermes: wrote {path}"


def _normalize_client(raw: str) -> str:
    key = raw.strip().lower().replace("_", "-").replace(" ", "-")
    normalized = CLIENT_ALIASES.get(key)
    if normalized is None:
        valid = ", ".join(sorted(CLIENT_ALIASES))
        raise argparse.ArgumentTypeError(f"unsupported client '{raw}'. Expected one of: {valid}")
    return normalized


def _clients_for(client: str) -> tuple[str, ...]:
    return DEFAULT_CLIENTS if client == "all" else (client,)


def _install_client(client: str, name: str, mcp_url: str, api_key: str) -> str:
    if client == "cursor":
        return _install_cursor_mcp(name, mcp_url, api_key)
    if client == "claude-code":
        return _install_claude_code_mcp(name, mcp_url, api_key)
    if client == "codex":
        return _install_codex_mcp(name, mcp_url)
    if client == "openclaw":
        return _install_openclaw_mcp(name, mcp_url, api_key)
    if client == "hermes":
        return _install_hermes_mcp(name, mcp_url, api_key)
    raise SystemExit(f"Unsupported client: {client}")


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


def _mcp_json_from_text(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            continue
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _mcp_post(mcp_url: str, api_key: str, body: dict[str, Any],
              session_id: str | None = None, timeout: int = 20):
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    request = Request(
        mcp_url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    return urlopen(request, timeout=timeout)


def _verify_mcp_initialize(mcp_url: str, api_key: str) -> dict[str, Any]:
    try:
        with _mcp_post(
            mcp_url,
            api_key,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "doomberg-installer", "version": "1"},
                },
            },
        ) as response:
            text = response.read().decode("utf-8", errors="replace")
            session_id = response.headers.get("mcp-session-id")
            body = _mcp_json_from_text(text) or {}
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"MCP initialize returned HTTP {exc.code}: {detail}"}
    except Exception as exc:
        return {"ok": False, "error": f"MCP initialize failed: {exc}"}

    if "error" in body:
        return {"ok": False, "error": f"MCP initialize error: {body['error']}"}
    if not session_id:
        return {"ok": False, "error": "MCP initialize did not return mcp-session-id"}

    try:
        with _mcp_post(
            mcp_url,
            api_key,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            session_id=session_id,
        ) as response:
            response.read()
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"MCP initialized notification returned HTTP {exc.code}: {detail}"}
    except Exception as exc:
        return {"ok": False, "error": f"MCP initialized notification failed: {exc}"}
    return {"ok": True, "session_id": session_id}


def _agent_bootstrap_prompt(name: str) -> str:
    return (
        "After your agent reloads MCP config, call the Doomberg init tool first:\n"
        f"  {name}.doomberg_init(goal=\"<what you want Doomberg to research or build>\")\n"
        "Then use search_skills/describe_skill/run_skill for market data, backtests, "
        "and paper-trading research."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Doomberg MCP into a local agent.")
    parser.add_argument("--app-url", default=os.environ.get("DOOMBERG_APP_URL", DEFAULT_APP_URL))
    parser.add_argument("--mcp-url", default=os.environ.get("DOOMBERG_MCP_URL", DEFAULT_MCP_URL))
    parser.add_argument("--name", default="doomberg")
    parser.add_argument(
        "--client",
        type=_normalize_client,
        default="all",
        help="Agent client to configure: all, cursor, claude-code, codex, openclaw, or hermes.",
    )
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument(
        "--agent-init",
        action="store_true",
        help="Agent-driven onboarding: print the approval URL, wait, install, and verify MCP initialize.",
    )
    args = parser.parse_args(argv)

    state_token = secrets.token_urlsafe(24)
    callback_state = CallbackState(state_token)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(callback_state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    callback_url = f"http://127.0.0.1:{server.server_port}/callback"
    link = _agent_link_url(args.app_url, callback_url, state_token, args.mcp_url,
                           args.name, args.client)
    if args.agent_init:
        print("Send this URL to the user so they can sign in or create an account and approve Doomberg MCP:")
    else:
        print("Open this URL to sign in and approve Doomberg MCP:")
    print(link)
    if not args.no_open and not args.agent_init:
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
    results: list[str] = []
    failures: list[str] = []
    for client in _clients_for(args.client):
        try:
            results.append(_install_client(client, args.name, mcp_url, api_key))
        except Exception as exc:
            failure = f"{client}: failed: {exc}"
            failures.append(failure)
            results.append(failure)

    key_id = payload.get("key_id", "")
    print(f"Doomberg MCP installed as '{args.name}'.")
    for result in results:
        print(f"- {result}")
    if key_id:
        print(f"Key id: {key_id}")
    print(f"Token env: {ENV_FILE}")
    if args.agent_init:
        init = _verify_mcp_initialize(mcp_url, api_key)
        if init.get("ok"):
            print(f"MCP initialize: ok (session {init['session_id']})")
        else:
            print(f"MCP initialize: {init.get('error')}")
            failures.append(str(init.get("error")))
        print(_agent_bootstrap_prompt(args.name))
    print("Restart any already-open agent app so it picks up the new MCP config/env.")
    if failures and (args.client != "all" or args.agent_init):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
