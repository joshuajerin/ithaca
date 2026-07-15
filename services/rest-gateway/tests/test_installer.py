"""Installer handoff route."""

from __future__ import annotations

import importlib.util
import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread


def test_install_script_is_served(client):
    resp = client.get("/install.py")
    assert resp.status_code == 200
    assert "Interactive Ithaca MCP installer" in resp.text
    for agent_client in ["cursor", "claude-code", "codex", "openclaw", "hermes"]:
        assert agent_client in resp.text
    assert "codex" in resp.text
    assert "--agent-init" in resp.text


def _installer_module():
    root = Path(__file__).resolve().parents[3]
    script = root / "scripts" / "install_agent_mcp.py"
    spec = importlib.util.spec_from_file_location("ithaca_install_agent_mcp", script)
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
        "ithaca",
        installer._http_mcp_config("https://mcp.tradeithaca.com/mcp", "ith_test_secret"),
    )

    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["mcpServers"]["existing"]["command"] == "uv"
    assert data["mcpServers"]["ithaca"] == {
        "type": "http",
        "url": "https://mcp.tradeithaca.com/mcp",
        "headers": {"Authorization": "Bearer ith_test_secret"},
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


def test_installer_uses_path_based_agent_approval_url():
    installer = _installer_module()

    link = installer._agent_link_url(
        "https://app.tradeithaca.com",
        "http://127.0.0.1:4242/callback",
        "approval-state",
        "https://mcp.tradeithaca.com/mcp",
        "ithaca",
        "claude-code",
    )

    assert link.startswith("https://app.tradeithaca.com/agent-link?")
    assert "/#/agent-link" not in link
    assert "callback=http%3A%2F%2F127.0.0.1%3A4242%2Fcallback" in link
    assert "state=approval-state" in link


def test_installer_callback_accepts_clerk_managed_api_key():
    installer = _installer_module()
    state = installer.CallbackState("approval-state")
    server = ThreadingHTTPServer(("127.0.0.1", 0), installer._handler(state))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        connection = HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request(
            "POST",
            "/callback",
            body=json.dumps({"state": "approval-state", "api_key": "ak_live_secret"}),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read()) == {"ok": True}
        assert state.payload == {"state": "approval-state", "api_key": "ak_live_secret"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_installer_agent_bootstrap_prompt():
    installer = _installer_module()
    prompt = installer._agent_bootstrap_prompt("ithaca")
    assert "ithaca.ithaca_init" in prompt
    assert "search_skills" in prompt


def test_installer_uses_env_backed_claude_http_config():
    installer = _installer_module()
    assert installer._http_mcp_env_config("https://mcp.tradeithaca.com/mcp") == {
        "type": "http",
        "url": "https://mcp.tradeithaca.com/mcp",
        "headers": {"Authorization": "Bearer ${ITHACA_MCP_API_KEY}"},
    }


def test_installer_agent_init_smoke_calls_ithaca_init(monkeypatch):
    installer = _installer_module()
    calls = []

    def fake_call(mcp_url, api_key, session_id, tool_name, arguments=None, mid=10):
        calls.append((mcp_url, api_key, session_id, tool_name, arguments, mid))
        return {"status": "ready", "session_id": "run_123"}

    monkeypatch.setattr(installer, "_call_mcp_tool", fake_call)

    out = installer._run_agent_init_smoke(
        "https://mcp.tradeithaca.com/mcp",
        "ith_test_secret",
        "mcp-session",
        "research AAPL",
    )

    assert out["session_id"] == "run_123"
    assert calls == [
        (
            "https://mcp.tradeithaca.com/mcp",
            "ith_test_secret",
            "mcp-session",
            "ithaca_init",
            {"goal": "research AAPL"},
            40,
        )
    ]


def test_installer_builds_generated_tools_markdown():
    installer = _installer_module()
    markdown = installer._build_tools_markdown(
        mcp_url="https://mcp.tradeithaca.com/mcp",
        init_result={
            "session_id": "run_123",
            "boundaries": {"can": ["read market data"], "cannot": ["move money"]},
        },
        tools=[{"name": "ithaca_init", "description": "Initialize Ithaca."}],
        toolkits=[
            {
                "toolkit_id": "market-research",
                "name": "Market Research",
                "description": "Market context.",
                "required_first_tool": "start_research_session",
                "direct_tools": ["market_get_ohlcv"],
                "skills": [{"skill_id": "market.news"}],
            }
        ],
        skills_catalog={
            "count": 1,
            "skills": [
                {
                    "skill_id": "market.news",
                    "runtime_profile": "interactive",
                    "description": "Recent news.",
                }
            ],
        },
    )

    assert "Generated by the Ithaca installer" in markdown
    assert "ithaca_init" in markdown
    assert "Market Research" in markdown
    assert "market_get_ohlcv" in markdown
    assert "market.news" in markdown
    assert "ith_test_secret" not in markdown


def test_installer_parses_streamable_http_json():
    installer = _installer_module()
    assert installer._mcp_json_from_text('{"jsonrpc":"2.0","id":1,"result":{}}') == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {},
    }
    assert installer._mcp_json_from_text('event: message\ndata: {"jsonrpc":"2.0","result":{"ok":true}}\n\n') == {
        "jsonrpc": "2.0",
        "result": {"ok": True},
    }
    assert installer._mcp_json_from_text('event: message\ndata: {"jsonrpc":"2.0",\ndata: "result":{"ok":true}}\n\n') == {
        "jsonrpc": "2.0",
        "result": {"ok": True},
    }
