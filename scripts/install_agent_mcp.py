#!/usr/bin/env python3
"""Install Ithaca MCP using native OAuth, with scoped API keys as an explicit fallback.

The normal path never writes a global environment variable and never mints a key.  It records
only the hosted MCP URL, then lets the client complete Clerk's OAuth browser flow.
"""
import argparse
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
import webbrowser
from dataclasses import dataclass
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

DEFAULT_APP_URL = "https://app.tradeithaca.com"
DEFAULT_MCP_URL = "https://mcp.tradeithaca.com/mcp"
SHELL_MARKER = "# Ithaca MCP environment"


@dataclass(frozen=True)
class ClientSpec:
    id: str
    label: str
    native_oauth: bool
    supports_cli_login: bool
    supports_headless_login: bool
    config_kind: str


CLIENT_SPECS: dict[str, ClientSpec] = {
    "codex": ClientSpec("codex", "Codex", True, True, True, "cli"),
    "claude-code": ClientSpec("claude-code", "Claude Code", True, True, True, "cli"),
    "cursor": ClientSpec("cursor", "Cursor", True, False, False, "cursor-json"),
    "openclaw": ClientSpec("openclaw", "OpenClaw", False, False, False, "json"),
    "hermes": ClientSpec("hermes", "Hermes", False, False, False, "json"),
}
CLIENT_ALIASES = {"all": "all", "claude": "claude-code", "claudecode": "claude-code", **{k: k for k in CLIENT_SPECS}}


class SetupStatus(str, Enum):
    CONFIGURED = "configured"
    AUTHENTICATION_REQUIRED = "authentication_required"
    AUTHENTICATED = "authenticated"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass(frozen=True)
class SetupResult:
    client: str
    status: SetupStatus
    detail: str


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
                payload = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))).decode())
            except Exception:
                _json_response(self, 400, {"error": "invalid json"})
                return
            if payload.get("state") != state.expected_state:
                state.error = "state mismatch"
                state.event.set()
                _json_response(self, 403, {"error": state.error})
                return
            if payload.get("denied") or payload.get("error"):
                state.error = str(payload.get("error") or "User denied compatibility key creation")
                state.event.set()
                _json_response(self, 200, {"ok": True})
                return
            key = str(payload.get("api_key") or "")
            if not key.startswith(("ak_", "dmbg_", "ith_")):
                state.error = "approval did not return an API key"
                state.event.set()
                _json_response(self, 400, {"error": state.error})
                return
            state.payload = payload
            state.event.set()
            _json_response(self, 200, {"ok": True})

    return Handler


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"could not parse {path}: {exc}") from exc
    return value if isinstance(value, dict) else {}


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_suffix(path.suffix + f".ithaca-backup.{int(time.time())}")
    shutil.copy2(path, backup)
    return backup


def _write_json_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _oauth_config(mcp_url: str) -> dict[str, Any]:
    return {"type": "http", "url": mcp_url}


def _api_key_config(mcp_url: str, api_key: str) -> dict[str, Any]:
    return {"type": "http", "url": mcp_url, "headers": {"Authorization": f"Bearer {api_key}"}}


def _merge_mcp_json(path: Path, name: str, config: dict[str, Any]) -> Path | None:
    backup = _backup(path)
    data = _read_json_file(path)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers[name] = config
    data["mcpServers"] = servers
    try:
        _write_json_file(path, data)
    except Exception:
        if backup:
            shutil.copy2(backup, path)
        raise
    return backup


def _protected_resource_url(mcp_url: str) -> str:
    parts = urlsplit(mcp_url)
    path = parts.path.lstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, f"/.well-known/oauth-protected-resource/{path}", "", ""))


def _discover_oauth(mcp_url: str, timeout: int = 15) -> dict[str, Any]:
    metadata_url = _protected_resource_url(mcp_url)
    try:
        with urlopen(Request(metadata_url, headers={"Accept": "application/json"}), timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urlerror.URLError, urlerror.HTTPError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"OAuth discovery failed at {metadata_url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("OAuth discovery returned an invalid document")
    resource = str(payload.get("resource") or "").rstrip("/")
    expected = mcp_url.rstrip("/")
    if resource != expected or not resource.startswith("https://"):
        raise RuntimeError("OAuth metadata does not advertise this canonical HTTPS MCP URL")
    servers = payload.get("authorization_servers")
    if not isinstance(servers, list) or not all(isinstance(item, str) and item.startswith("https://") for item in servers):
        raise RuntimeError("OAuth metadata does not advertise an HTTPS authorization server")
    scopes = payload.get("scopes_supported") or []
    if "openid" not in scopes:
        raise RuntimeError("OAuth metadata does not advertise the required openid scope")
    return payload


def _remove_shell_marker() -> None:
    for path in (Path.home() / ".zshrc", Path.home() / ".bashrc"):
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        output: list[str] = []
        skip = False
        for line in lines:
            if line.rstrip("\n") == SHELL_MARKER:
                skip = True
                continue
            if skip and "Ithaca/mcp.env" in line:
                skip = False
                continue
            skip = False
            output.append(line)
        if output != lines:
            path.write_text("".join(output), encoding="utf-8")


def _remove_owned_legacy_env() -> None:
    path = Path.home() / ".config" / "ithaca" / "mcp.env"
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8")
    if content.startswith("# Written by Ithaca MCP installer.") and "ITHACA_MCP_API_KEY" in content:
        path.unlink()


def _cleanup_legacy_install() -> None:
    _remove_shell_marker()
    _remove_owned_legacy_env()
    if shutil.which("launchctl"):
        subprocess.run(["launchctl", "unsetenv", "ITHACA_MCP_API_KEY"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _codex_install(name: str, mcp_url: str, login: bool, headless: bool) -> SetupResult:
    codex = shutil.which("codex")
    if not codex:
        return SetupResult("codex", SetupStatus.CONFIGURED, f"Run: codex mcp add {name} --url {mcp_url}")
    subprocess.run([codex, "mcp", "remove", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([codex, "mcp", "add", name, "--url", mcp_url], check=True, timeout=30)
    if not login:
        return SetupResult("codex", SetupStatus.AUTHENTICATION_REQUIRED, f"Run: codex mcp login {name} --scopes openid offline_access")
    command = [codex, "mcp", "login", name, "--scopes", "openid", "offline_access"]
    if headless:
        command.append("--headless")
    subprocess.run(command, check=True, timeout=180)
    return SetupResult("codex", SetupStatus.AUTHENTICATED, "Clerk login completed; restart Codex if it is running.")


def _claude_install(name: str, mcp_url: str, login: bool, headless: bool) -> SetupResult:
    claude = shutil.which("claude")
    if not claude:
        path = Path.home() / ".claude" / "mcp.json"
        _merge_mcp_json(path, name, _oauth_config(mcp_url))
        return SetupResult("claude-code", SetupStatus.AUTHENTICATION_REQUIRED, f"Wrote {path}; use Claude Code Connect/Login.")
    subprocess.run([claude, "mcp", "remove", "--scope", "user", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([claude, "mcp", "add", "--transport", "http", "--scope", "user", name, mcp_url], check=True, timeout=30)
    if not login:
        return SetupResult("claude-code", SetupStatus.AUTHENTICATION_REQUIRED, "Run Claude Code's MCP login for Ithaca.")
    command = [claude, "mcp", "login", name, "--scopes", "openid", "offline_access"]
    if headless:
        command.append("--headless")
    subprocess.run(command, check=True, timeout=180)
    return SetupResult("claude-code", SetupStatus.AUTHENTICATED, "Clerk login completed; restart Claude Code if it is running.")


def _cursor_install(name: str, mcp_url: str) -> SetupResult:
    path = Path.home() / ".cursor" / "mcp.json"
    _merge_mcp_json(path, name, _oauth_config(mcp_url))
    return SetupResult("cursor", SetupStatus.AUTHENTICATION_REQUIRED, "Open Cursor and choose Connect/Login for Ithaca MCP.")


def _compat_install(client: str, name: str, mcp_url: str, api_key: str) -> SetupResult:
    paths = {"openclaw": Path.home() / ".openclaw" / "mcp.json", "hermes": Path.home() / ".hermes" / "mcp.json"}
    path = paths[client]
    _merge_mcp_json(path, name, _api_key_config(mcp_url, api_key))
    return SetupResult(client, SetupStatus.CONFIGURED, f"Wrote protected configuration {path}")


def _agent_link_url(app_url: str, callback_url: str, state: str, mcp_url: str, name: str, client: str) -> str:
    parts = urlsplit(app_url)
    params = urlencode({"callback": callback_url, "state": state, "mcp_url": mcp_url, "name": name, "client": client, "auth": "api-key"}, quote_via=quote)
    return f"{urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip('/'), '', ''))}/#/agent-link?{params}"


def _wait_for_payload(state: CallbackState, timeout: int) -> dict[str, Any]:
    if not state.event.wait(timeout):
        raise RuntimeError("Timed out waiting for compatibility-key approval.")
    if state.error:
        raise RuntimeError(state.error)
    if not state.payload:
        raise RuntimeError("compatibility-key approval returned no credential")
    return state.payload


def _native_clients_detected() -> tuple[str, ...]:
    clients: list[str] = []
    if shutil.which("codex"):
        clients.append("codex")
    if shutil.which("claude"):
        clients.append("claude-code")
    if (Path.home() / ".cursor").exists():
        clients.append("cursor")
    return tuple(clients)


def _normalize_client(raw: str) -> str:
    value = raw.strip().lower().replace("_", "-").replace(" ", "-")
    if value not in CLIENT_ALIASES:
        raise argparse.ArgumentTypeError(f"unsupported client '{raw}'")
    return CLIENT_ALIASES[value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Ithaca MCP into a local agent.")
    parser.add_argument("--app-url", default=os.environ.get("ITHACA_APP_URL", DEFAULT_APP_URL))
    parser.add_argument("--mcp-url", default=os.environ.get("ITHACA_MCP_URL", DEFAULT_MCP_URL))
    parser.add_argument("--name", default="ithaca")
    parser.add_argument("--client", type=_normalize_client, help="codex, claude-code, cursor, openclaw, hermes, or all")
    parser.add_argument("--auth", choices=("oauth", "api-key"), default="oauth")
    parser.add_argument("--login", action="store_true", help="Run the client native OAuth login after registration.")
    parser.add_argument("--headless", action="store_true", help="Ask supported client CLIs for a no-browser login flow.")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--agent-init", action="store_true", help="Complete supported native login and then invoke ithaca_init from the agent.")
    args = parser.parse_args(argv)

    if args.client == "all":
        clients = tuple(CLIENT_SPECS) if args.auth == "api-key" else tuple(
            spec.id for spec in CLIENT_SPECS.values() if spec.native_oauth
        )
    else:
        clients = (args.client,) if args.client else _native_clients_detected()
    if not clients:
        print("No supported native OAuth client detected. Add this URL manually:")
        print(args.mcp_url)
        return 0
    if args.auth == "oauth" and any(not CLIENT_SPECS[client].native_oauth for client in clients):
        parser.error("OpenClaw and Hermes require --auth api-key for compatibility setup")

    if args.auth == "oauth":
        # Do this before a single configuration file is touched.
        _discover_oauth(args.mcp_url)
        results: list[SetupResult] = []
        for client in clients:
            spec = CLIENT_SPECS[client]
            try:
                if client == "codex":
                    results.append(_codex_install(args.name, args.mcp_url, args.login or args.agent_init, args.headless))
                elif client == "claude-code":
                    results.append(_claude_install(args.name, args.mcp_url, args.login or args.agent_init, args.headless))
                else:
                    results.append(_cursor_install(args.name, args.mcp_url))
            except Exception as exc:
                results.append(SetupResult(client, SetupStatus.FAILED, str(exc)))
        if any(result.status != SetupStatus.FAILED for result in results):
            _cleanup_legacy_install()
        for result in results:
            print(f"{result.client}: {result.status.value} — {result.detail}")
        if args.agent_init:
            print("After the agent reloads, invoke ithaca_init with the user’s research goal.")
        return 1 if any(result.status == SetupStatus.FAILED for result in results) else 0

    # Explicit legacy compatibility mode.  It is intentionally the only code path that mints
    # a long-lived key and only writes that key into the selected client config.
    state = CallbackState(secrets.token_urlsafe(24))
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    link = _agent_link_url(args.app_url, f"http://127.0.0.1:{server.server_port}/callback", state.expected_state, args.mcp_url, args.name, args.client or "all")
    print("Open this URL to create a scoped compatibility key:")
    print(link)
    if not args.no_open:
        webbrowser.open(link)
    try:
        payload = _wait_for_payload(state, args.timeout)
    finally:
        server.shutdown()
        server.server_close()
    key = str(payload["api_key"])
    mcp_url = str(payload.get("mcp_url") or args.mcp_url)
    for client in clients:
        try:
            print(f"{_compat_install(client, args.name, mcp_url, key).client}: configured")
        except Exception as exc:
            print(f"{client}: failed — {exc}")
    key_id = str(payload.get("key_id") or "")
    print(f"Compatibility key stored in client configuration{f' ({key_id})' if key_id else ''}. Revoke it in Settings when no longer needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
