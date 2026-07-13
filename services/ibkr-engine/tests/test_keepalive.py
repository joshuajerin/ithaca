from __future__ import annotations

import json

from doomberg_ibkr_engine import keepalive
from doomberg_ibkr_engine.client_portal import ClientPortalAuthError


def test_keepalive_reports_sanitized_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        keepalive.ClientPortalGateway,
        "ensure_authenticated",
        lambda _self: {
            "authenticated": True,
            "connected": True,
            "repaired": False,
            "repair_action": "none",
            "raw": {"account": "must-not-leak"},
        },
    )

    assert keepalive.main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "raw" not in payload["status"]
    assert "must-not-leak" not in json.dumps(payload)


def test_keepalive_fails_when_disconnected(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        keepalive.ClientPortalGateway,
        "ensure_authenticated",
        lambda _self: {"authenticated": True, "connected": False},
    )

    assert keepalive.main(["--json"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_keepalive_returns_nonzero_on_auth_failure(monkeypatch, capsys) -> None:
    def fail(_self):
        raise ClientPortalAuthError("browser login is required")

    monkeypatch.setattr(keepalive.ClientPortalGateway, "ensure_authenticated", fail)

    assert keepalive.main(["--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["authenticated"] is False
    assert payload["error"] == "browser login is required"
