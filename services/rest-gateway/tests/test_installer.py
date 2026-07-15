from __future__ import annotations

import importlib.util
from pathlib import Path


def _installer_module():
    root = Path(__file__).resolve().parents[3]
    script = root / "scripts" / "install_agent_mcp.py"
    spec = importlib.util.spec_from_file_location("ithaca_install_agent_mcp", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_install_script_is_served(client):
    response = client.get("/install.py")
    assert response.status_code == 200
    assert "Install Ithaca MCP" in response.text


def test_installer_writes_bare_oauth_cursor_config(tmp_path, monkeypatch):
    installer = _installer_module()
    path = tmp_path / "mcp.json"
    path.write_text('{"mcpServers":{"other":{"type":"http","url":"https://other"}}}')
    installer._merge_mcp_json(path, "ithaca", installer._oauth_config("https://mcp.tradeithaca.com/mcp"))
    value = installer._read_json_file(path)
    assert value["mcpServers"]["other"]["url"] == "https://other"
    assert value["mcpServers"]["ithaca"] == {"type": "http", "url": "https://mcp.tradeithaca.com/mcp"}
    assert "Authorization" not in str(value)


def test_installer_client_aliases_and_statuses():
    installer = _installer_module()
    assert installer._normalize_client("claude") == "claude-code"
    assert installer.SetupStatus.AUTHENTICATION_REQUIRED.value == "authentication_required"
    assert installer.CLIENT_SPECS["codex"].native_oauth
    assert not installer.CLIENT_SPECS["openclaw"].native_oauth


def test_oauth_metadata_url_is_canonical():
    installer = _installer_module()
    assert installer._protected_resource_url("https://mcp.tradeithaca.com/mcp") == "https://mcp.tradeithaca.com/.well-known/oauth-protected-resource/mcp"
