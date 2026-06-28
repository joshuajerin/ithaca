"""Installer handoff route."""

from __future__ import annotations


def test_install_script_is_served(client):
    resp = client.get("/install.py")
    assert resp.status_code == 200
    assert "Interactive Doomberg MCP installer" in resp.text
    assert "codex" in resp.text
