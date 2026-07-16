from __future__ import annotations

import importlib.util
import subprocess
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
    assert installer.CLIENT_SPECS["generic"].native_oauth
    assert not installer.CLIENT_SPECS["openclaw"].native_oauth


def test_oauth_metadata_url_is_canonical():
    installer = _installer_module()
    assert installer._protected_resource_url("https://mcp.tradeithaca.com/mcp") == "https://mcp.tradeithaca.com/.well-known/oauth-protected-resource/mcp"


def test_codex_login_uses_comma_separated_refresh_scope(monkeypatch):
    installer = _installer_module()
    calls: list[list[str]] = []

    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[2] == "get":
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    result = installer._codex_install(
        "ithaca", "https://mcp.tradeithaca.com/mcp", login=True, headless=False
    )

    assert result.status == installer.SetupStatus.AUTHENTICATED
    assert calls[-1] == [
        "/usr/bin/codex", "mcp", "login", "ithaca",
        "--scopes", "openid,offline_access",
    ]


def test_codex_existing_registration_is_not_recreated(monkeypatch):
    installer = _installer_module()
    calls: list[list[str]] = []
    mcp_url = "https://mcp.tradeithaca.com/mcp"

    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, f"url: {mcp_url}", "")

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    result = installer._codex_install("ithaca", mcp_url, login=False, headless=False)

    assert result.status == installer.SetupStatus.AUTHENTICATION_REQUIRED
    assert calls == [["/usr/bin/codex", "mcp", "get", "ithaca"]]


def test_claude_login_uses_supported_no_browser_flag(monkeypatch):
    installer = _installer_module()
    calls: list[list[str]] = []

    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[2] == "get":
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    result = installer._claude_install(
        "ithaca", "https://mcp.tradeithaca.com/mcp", login=True, headless=True
    )

    assert result.status == installer.SetupStatus.AUTHENTICATED
    assert calls[-1] == ["/usr/bin/claude", "mcp", "login", "ithaca", "--no-browser"]


def test_generic_client_preserves_other_mcp_servers(tmp_path):
    installer = _installer_module()
    path = tmp_path / "agent-mcp.json"
    path.write_text('{"mcpServers":{"other":{"url":"https://other"}}}')

    result = installer._generic_install(
        "ithaca", "https://mcp.tradeithaca.com/mcp", path
    )
    value = installer._read_json_file(path)

    assert result.client == "generic"
    assert value["mcpServers"]["other"]["url"] == "https://other"
    assert value["mcpServers"]["ithaca"] == {
        "type": "http",
        "url": "https://mcp.tradeithaca.com/mcp",
    }


def test_app_opens_before_native_oauth(monkeypatch):
    installer = _installer_module()
    opened: list[str] = []
    slept: list[int] = []
    monkeypatch.setattr(installer.webbrowser, "open", opened.append)
    monkeypatch.setattr(installer.time, "sleep", slept.append)

    installer._open_app_before_login("https://app.tradeithaca.com/")

    assert opened == ["https://app.tradeithaca.com/settings#connect-agent"]
    assert slept == [1]
