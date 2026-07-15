#!/usr/bin/env python3
"""Interactive Ithaca MCP installer for local coding agents.

The installer opens the Ithaca web app, receives a one-time key from the signed-in
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

DEFAULT_APP_URL = "https://app.tradeithaca.com"
DEFAULT_MCP_URL = "https://mcp.tradeithaca.com/mcp"
CONFIG_DIR = Path.home() / ".config" / "ithaca"
ENV_FILE = CONFIG_DIR / "mcp.env"
TOOLS_GUIDE_FILE = CONFIG_DIR / "TOOLS.md"
SHELL_MARKER = "# Ithaca MCP environment"
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
            if not api_key.startswith("ith_"):
                state.error = "approval did not return a Ithaca API key"
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
    return f"{base}/agent-link?{params}"


def _write_env_file(api_key: str, mcp_url: str) -> None:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Written by Ithaca MCP installer. Keep this file private.",
        f"export ITHACA_MCP_API_KEY={shlex.quote(api_key)}",
        f"export ITHACA_MCP_URL={shlex.quote(mcp_url)}",
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


def _http_mcp_env_config(mcp_url: str) -> dict[str, Any]:
    return {
        "type": "http",
        "url": mcp_url,
        "headers": {
            "Authorization": "Bearer ${ITHACA_MCP_API_KEY}",
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
    subprocess.run(["launchctl", "setenv", "ITHACA_MCP_API_KEY", api_key], check=False)
    subprocess.run(["launchctl", "setenv", "ITHACA_MCP_URL", mcp_url], check=False)


def _install_codex_mcp(name: str, mcp_url: str) -> str:
    codex = shutil.which("codex")
    if codex is None:
        return (
            "Codex: codex CLI not found; run manually: "
            f"codex mcp add {name} --url {mcp_url} "
            "--bearer-token-env-var ITHACA_MCP_API_KEY"
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
            "ITHACA_MCP_API_KEY",
        ],
        check=True,
        timeout=30,
    )
    return "Codex: registered with `codex mcp add --url`"


def _install_claude_code_mcp(name: str, mcp_url: str, _api_key: str) -> str:
    claude = shutil.which("claude")
    if claude is None:
        path = Path.home() / ".claude" / "mcp.json"
        _merge_mcp_json(path, name, _http_mcp_env_config(mcp_url))
        return f"Claude Code: claude CLI not found; wrote {path} with ITHACA_MCP_API_KEY env reference"
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
            "Authorization: Bearer ${ITHACA_MCP_API_KEY}",
            name,
            mcp_url,
        ],
        check=True,
        timeout=30,
    )
    return "Claude Code: registered with `claude mcp add --transport http` using ITHACA_MCP_API_KEY"


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
    data_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            continue
        data_lines.append(data)
    for data in ["\n".join(data_lines), *data_lines]:
        if not data:
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


def _header(headers: dict[str, str], name: str) -> str | None:
    expected = name.lower()
    for key, value in headers.items():
        if key.lower() == expected:
            return value
    return None


def _mcp_exchange(mcp_url: str, api_key: str, body: dict[str, Any],
                  session_id: str | None = None, timeout: int = 20) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        with _mcp_post(mcp_url, api_key, body, session_id=session_id, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            headers = dict(response.headers.items())
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        method = body.get("method", "request")
        raise RuntimeError(f"MCP {method} returned HTTP {exc.code}: {detail}") from exc
    parsed = _mcp_json_from_text(text)
    if parsed is None:
        method = body.get("method", "request")
        raise RuntimeError(f"MCP {method} response was not parseable JSON")
    if parsed.get("error"):
        method = body.get("method", "request")
        raise RuntimeError(f"MCP {method} error: {parsed['error']}")
    return parsed, headers


def _verify_mcp_initialize(mcp_url: str, api_key: str) -> dict[str, Any]:
    try:
        body, headers = _mcp_exchange(
            mcp_url,
            api_key,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "ithaca-installer", "version": "1"},
                },
            },
        )
    except Exception as exc:
        return {"ok": False, "error": f"MCP initialize failed: {exc}"}

    session_id = _header(headers, "mcp-session-id")
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


def _mcp_tool_json(body: dict[str, Any]) -> dict[str, Any] | None:
    result = body.get("result") or {}
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    contents = result.get("content") or []
    if not contents:
        return None
    text = contents[0].get("text")
    if not isinstance(text, str):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _mcp_content_json(body: dict[str, Any]) -> dict[str, Any] | None:
    contents = ((body.get("result") or {}).get("contents") or [])
    if not contents:
        return None
    text = contents[0].get("text")
    if not isinstance(text, str):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _call_mcp_tool(mcp_url: str, api_key: str, session_id: str, tool_name: str,
                   arguments: dict[str, Any] | None = None, mid: int = 10) -> dict[str, Any]:
    body, _headers = _mcp_exchange(
        mcp_url,
        api_key,
        {
            "jsonrpc": "2.0",
            "id": mid,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments or {}},
        },
        session_id=session_id,
    )
    result = body.get("result") or {}
    if result.get("isError"):
        raise RuntimeError(f"MCP tool {tool_name} returned an error: {body}")
    parsed = _mcp_tool_json(body)
    if parsed is None:
        raise RuntimeError(f"MCP tool {tool_name} response was not parseable JSON")
    return parsed


def _read_mcp_resource(mcp_url: str, api_key: str, session_id: str, uri: str,
                       mid: int = 20) -> dict[str, Any]:
    body, _headers = _mcp_exchange(
        mcp_url,
        api_key,
        {
            "jsonrpc": "2.0",
            "id": mid,
            "method": "resources/read",
            "params": {"uri": uri},
        },
        session_id=session_id,
    )
    parsed = _mcp_content_json(body)
    if parsed is None:
        raise RuntimeError(f"MCP resource {uri} response was not parseable JSON")
    return parsed


def _list_mcp_tools(mcp_url: str, api_key: str, session_id: str) -> list[dict[str, Any]]:
    body, _headers = _mcp_exchange(
        mcp_url,
        api_key,
        {"jsonrpc": "2.0", "id": 30, "method": "tools/list"},
        session_id=session_id,
    )
    tools = (body.get("result") or {}).get("tools") or []
    return [tool for tool in tools if isinstance(tool, dict)]


def _run_agent_init_smoke(mcp_url: str, api_key: str, session_id: str, goal: str) -> dict[str, Any]:
    result = _call_mcp_tool(
        mcp_url,
        api_key,
        session_id,
        "ithaca_init",
        {"goal": goal},
        mid=40,
    )
    if result.get("status") != "ready" or not result.get("session_id"):
        raise RuntimeError(f"ithaca_init did not return a ready session: {result}")
    return result


def _md_cell(value: Any) -> str:
    text = str(value or "").replace("\n", " ").replace("|", "\\|").strip()
    return text or "-"


def _build_tools_markdown(
    *,
    mcp_url: str,
    init_result: dict[str, Any],
    tools: list[dict[str, Any]],
    toolkits: list[dict[str, Any]],
    skills_catalog: dict[str, Any],
) -> str:
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        "# Ithaca MCP Tools",
        "",
        f"Generated by the Ithaca installer at {generated_at}.",
        f"Endpoint: `{mcp_url}`",
        "",
        "This file intentionally does not contain bearer tokens. The installer stores the token in `~/.config/ithaca/mcp.env`.",
        "",
        "## First-call workflow",
        "",
        "1. Call `ithaca_init(goal=\"<user goal>\")` first. The installer has already smoke-tested this call.",
        "2. Use `list_toolkits` or `search_skills` to pick the smallest relevant surface.",
        "3. Use `describe_toolkit` or `describe_skill` before uncertain calls.",
        "4. Use direct tools for interactive answers and `run_skill` for durable backtests or longer work.",
        "",
        f"Installer init session: `{init_result.get('session_id', '-')}`",
        "",
        "## Toolkits",
        "",
    ]
    if toolkits:
        for toolkit in toolkits:
            direct_tools = toolkit.get("direct_tools") or []
            skills = toolkit.get("skills") or []
            lines.extend(
                [
                    f"### {toolkit.get('name') or toolkit.get('toolkit_id')}",
                    "",
                    _md_cell(toolkit.get("description")),
                    "",
                    f"- Toolkit id: `{toolkit.get('toolkit_id')}`",
                    f"- Required first tool: `{toolkit.get('required_first_tool')}`",
                    "- Direct tools: "
                    + (", ".join(f"`{tool}`" for tool in direct_tools) if direct_tools else "-"),
                    "- Related skills: "
                    + (
                        ", ".join(f"`{skill.get('skill_id')}`" for skill in skills[:12])
                        if skills
                        else "-"
                    ),
                    "",
                ]
            )
    else:
        lines.extend(["No toolkits were returned by the server.", ""])

    lines.extend(
        [
            "## Direct MCP tools",
            "",
            "| Tool | Description |",
            "| --- | --- |",
        ]
    )
    for tool in sorted(tools, key=lambda t: str(t.get("name") or "")):
        lines.append(f"| `{_md_cell(tool.get('name'))}` | {_md_cell(tool.get('description'))} |")

    skills = skills_catalog.get("skills") or []
    lines.extend(
        [
            "",
            "## Skill catalog",
            "",
            f"The server catalog currently reports {skills_catalog.get('count', len(skills))} skills.",
            "",
            "| Skill | Runtime | Description |",
            "| --- | --- | --- |",
        ]
    )
    for skill in skills:
        if not isinstance(skill, dict):
            continue
        lines.append(
            f"| `{_md_cell(skill.get('skill_id'))}` | {_md_cell(skill.get('runtime_profile'))} | "
            f"{_md_cell(skill.get('description'))} |"
        )

    lines.extend(
        [
            "",
            "## Operating boundaries",
            "",
        ]
    )
    boundaries = init_result.get("boundaries") or {}
    for key in ("can", "cannot"):
        values = boundaries.get(key) or []
        lines.append(f"- {key}: " + (", ".join(str(value) for value in values) if values else "-"))
    lines.append("")
    return "\n".join(lines)


def _write_tools_guide(mcp_url: str, api_key: str, session_id: str,
                       init_result: dict[str, Any]) -> Path:
    tools = _list_mcp_tools(mcp_url, api_key, session_id)
    catalog = _read_mcp_resource(mcp_url, api_key, session_id, "ithaca://toolkits/catalog", mid=31)
    toolkit_entries = catalog.get("toolkits") or []
    toolkits: list[dict[str, Any]] = []
    for index, entry in enumerate(toolkit_entries):
        if not isinstance(entry, dict) or not entry.get("toolkit_id"):
            continue
        toolkits.append(
            _call_mcp_tool(
                mcp_url,
                api_key,
                session_id,
                "describe_toolkit",
                {"toolkit_id": str(entry["toolkit_id"])},
                mid=32 + index,
            )
        )
    skills_catalog = _read_mcp_resource(mcp_url, api_key, session_id, "ithaca://skills/catalog", mid=50)
    markdown = _build_tools_markdown(
        mcp_url=mcp_url,
        init_result=init_result,
        tools=tools,
        toolkits=toolkits,
        skills_catalog=skills_catalog,
    )
    TOOLS_GUIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOOLS_GUIDE_FILE.write_text(markdown, encoding="utf-8")
    try:
        os.chmod(TOOLS_GUIDE_FILE, 0o600)
    except OSError:
        pass
    return TOOLS_GUIDE_FILE


def _agent_bootstrap_prompt(name: str) -> str:
    return (
        "After your agent reloads MCP config, call the Ithaca init tool first. "
        "It opens the visible research session with the user's prompt:\n"
        f"  {name}.ithaca_init(goal=\"<what you want Ithaca to research or build>\")\n"
        "Then call direct tools or search_skills/describe_skill/run_skill inside that session. "
        "Every MCP request is still authenticated with the installed key."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Ithaca MCP into a local agent.")
    parser.add_argument("--app-url", default=os.environ.get("ITHACA_APP_URL", DEFAULT_APP_URL))
    parser.add_argument("--mcp-url", default=os.environ.get("ITHACA_MCP_URL", DEFAULT_MCP_URL))
    parser.add_argument("--name", default="ithaca")
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
    parser.add_argument(
        "--init-goal",
        default="Initialize Ithaca MCP after install and show the first-call workflow.",
        help="Goal passed to ithaca_init during the post-auth MCP smoke.",
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
        print("Send this URL to the user so they can sign in or create an account and approve Ithaca MCP:")
    else:
        print("Open this URL to sign in and approve Ithaca MCP:")
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
    print(f"Ithaca MCP installed as '{args.name}'.")
    for result in results:
        print(f"- {result}")
    if key_id:
        print(f"Key id: {key_id}")
    print(f"Token env: {ENV_FILE}")
    print("Each MCP request is authenticated with this key automatically.")
    print("Agent flow: call ithaca_init with the user prompt; it opens the visible session.")
    print("Then use list_toolkits/search_skills, describe the relevant surface, and call direct tools or run_skill.")

    init = _verify_mcp_initialize(mcp_url, api_key)
    init_result: dict[str, Any] | None = None
    if init.get("ok"):
        session_id = str(init["session_id"])
        print(f"MCP initialize: ok (session {session_id})")
        try:
            init_result = _run_agent_init_smoke(mcp_url, api_key, session_id, str(args.init_goal))
            print(f"ithaca_init: ok (research session {init_result['session_id']})")
        except Exception as exc:
            print(f"ithaca_init: {exc}")
            failures.append(str(exc))
        if init_result is not None:
            try:
                guide = _write_tools_guide(mcp_url, api_key, session_id, init_result)
                print(f"Generated tools guide: {guide}")
            except Exception as exc:
                print(f"Generated tools guide: failed: {exc}")
                if args.agent_init:
                    failures.append(str(exc))
    else:
        print(f"MCP initialize: {init.get('error')}")
        if args.agent_init:
            failures.append(str(init.get("error")))

    print("Direct tools include: market_tide, sentiment_get, market_news, vix_term_structure, backtest_run.")
    if args.agent_init:
        print(_agent_bootstrap_prompt(args.name))
    print("Restart any already-open agent app so it picks up the new MCP config/env.")
    if failures and (args.client != "all" or args.agent_init):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
