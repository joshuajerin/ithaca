"""Installer handoff route."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def test_install_script_is_served(client):
    resp = client.get("/install.py")
    assert resp.status_code == 200
    assert "Interactive Doomberg MCP installer" in resp.text
    for agent_client in ["cursor", "claude-code", "codex", "openclaw", "hermes"]:
        assert agent_client in resp.text
    assert "codex" in resp.text


def _installer_module():
    root = Path(__file__).resolve().parents[3]
    script = root / "scripts" / "install_agent_mcp.py"
    spec = importlib.util.spec_from_file_location("doomberg_install_agent_mcp", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installer_merges_cursor_style_mcp_json(tmp_path):
    installer = _installer_module()
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps({"mcpServers": {"existing": {"command": "uv", "args": ["run"]}}}),
        encoding="utf-8",
    )

    installer._merge_mcp_json(
        config,
        "doomberg",
        installer._http_mcp_config("https://mcp.doomberg.me/mcp", "dmbg_test_secret"),
    )

    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["mcpServers"]["existing"]["command"] == "uv"
    assert data["mcpServers"]["doomberg"] == {
        "type": "http",
        "url": "https://mcp.doomberg.me/mcp",
        "headers": {"Authorization": "Bearer dmbg_test_secret"},
    }


def test_installer_client_aliases():
    installer = _installer_module()
    assert installer._normalize_client("claude code") == "claude-code"
    assert installer._normalize_client("all") == "all"
    assert installer._clients_for("all") == (
        "cursor",
        "claude-code",
        "codex",
        "openclaw",
        "hermes",
    )
