from __future__ import annotations

import importlib
import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ithaca_ibkr_engine.app import app
from ithaca_ibkr_engine.client_portal import (
    ClientPortalAuthError,
    ClientPortalGateway,
    ClientPortalHttpError,
)

app_module = importlib.import_module("ithaca_ibkr_engine.app")


class _Gateway:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                owner.requests.append({"method": "GET", "path": self.path})
                if self.path == "/v1/api/iserver/auth/status":
                    self._json({"authenticated": True, "connected": True})
                    return
                if self.path == "/v1/api/portfolio/accounts":
                    self._json([{"accountId": "DU12345", "type": "PAPER", "token": "secret"}])
                    return
                if self.path.startswith("/v1/api/iserver/marketdata/snapshot"):
                    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    self._json([{"conid": 265598, "31": "212.45", "84": "212.44", "86": "212.46", "_updated": now_ms}])
                    return
                if self.path.startswith("/v1/api/iserver/marketdata/history"):
                    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    self._json({
                        "symbol": "AAPL",
                        "data": [
                            {"t": now_ms - 300_000, "o": 211, "h": 213, "l": 210, "c": 212, "v": 1000},
                            {"t": now_ms, "o": 212, "h": 214, "l": 211, "c": 213, "v": 1200},
                        ],
                    })
                    return
                if self.path.startswith("/v1/api/iserver/news/briefing"):
                    self._json({
                        "provider": "Briefing.com General Market Columns",
                        "source": "BRFG",
                        "title": "Apple leads a mixed technology tape",
                        "content": "<html><body><p><strong>Apple</strong> traded higher as software strength offset chip weakness.</p></body></html>",
                    })
                    return
                if self.path == "/v1/api/portfolio/DU12345/positions/0":
                    self._json([{"contractDesc": "AAPL", "position": 2, "session": "secret"}])
                    return
                if self.path == "/v1/api/iserver/account/orders":
                    self._json({"orders": [{"orderId": "100", "ticker": "AAPL", "secret": "x"}]})
                    return
                self._json({"error": "not found"}, status=404)

            def do_POST(self) -> None:  # noqa: N802
                owner.requests.append({"method": "POST", "path": self.path})
                if self.path == "/v1/api/tickle":
                    self._json(
                        {
                            "session_id": "must-not-leak",
                            "iserver": {
                                "authStatus": {
                                    "authenticated": True,
                                    "connected": True,
                                    "account": "must-not-leak",
                                }
                            },
                        }
                    )
                    return
                if self.path == "/v1/api/iserver/secdef/search":
                    self._json([{"symbol": "AAPL", "conid": 265598, "secType": "STK"}])
                    return
                if self.path == "/v1/api/iserver/scanner/run":
                    self._json({
                        "contracts": [
                            {
                                "server_id": "0",
                                "symbol": "AAPL",
                                "con_id": 265598,
                                "company_name": "APPLE INC",
                                "listing_exchange": "NASDAQ.NMS",
                                "sec_type": "STK",
                            }
                        ]
                    })
                    return
                self._json({"error": "not found"}, status=404)

            def log_message(self, *_args: Any) -> None:
                return

            def _json(self, payload: Any, *, status: int = 200) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self._handler = Handler
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url = ""

    def __enter__(self) -> "_Gateway":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler)
        host, port = self._server.server_address
        self.url = f"http://{host}:{port}/v1/api"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


class _PreLoginGateway:
    def __init__(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self.send_response(401)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_args: Any) -> None:
                return

        self._handler = Handler
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url = ""

    def __enter__(self) -> "_PreLoginGateway":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler)
        host, port = self._server.server_address
        self.url = f"http://{host}:{port}/v1/api"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


class _ExpiredIserverGateway:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.init_bodies: list[dict[str, Any]] = []
        self.authenticated = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                owner.requests.append({"method": "GET", "path": self.path})
                if self.path == "/v1/api/iserver/auth/status":
                    self._json({"authenticated": owner.authenticated, "connected": True})
                    return
                if self.path.startswith("/v1/api/iserver/marketdata/snapshot"):
                    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    self._json([{"conid": 265598, "31": "212.45", "_updated": now_ms}])
                    return
                self._json({"error": "not found"}, status=404)

            def do_POST(self) -> None:  # noqa: N802
                owner.requests.append({"method": "POST", "path": self.path})
                length = int(self.headers.get("Content-Length") or "0")
                body = self.rfile.read(length) if length else b"{}"
                payload = json.loads(body.decode("utf-8") or "{}")
                if self.path == "/v1/api/tickle":
                    self._json(
                        {"iserver": {"authStatus": {"authenticated": False, "connected": True}}}
                    )
                    return
                if self.path == "/v1/api/iserver/auth/ssodh/init":
                    owner.init_bodies.append(payload)
                    owner.authenticated = payload == {"publish": True, "compete": True}
                    self._json({"authenticated": owner.authenticated, "connected": True})
                    return
                if self.path == "/v1/api/iserver/secdef/search":
                    self._json([{"symbol": "AAPL", "conid": 265598, "secType": "STK"}])
                    return
                self._json({"error": "not found"}, status=404)

            def log_message(self, *_args: Any) -> None:
                return

            def _json(self, payload: Any, *, status: int = 200) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self._handler = Handler
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url = ""

    def __enter__(self) -> "_ExpiredIserverGateway":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler)
        host, port = self._server.server_address
        self.url = f"http://{host}:{port}/v1/api"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


class _AfterHoursGateway:
    def __init__(self) -> None:
        self.requests: list[str] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                owner.requests.append(self.path)
                if self.path == "/v1/api/iserver/auth/status":
                    self._json({"authenticated": True, "connected": True})
                    return
                if self.path.startswith("/v1/api/iserver/marketdata/snapshot"):
                    self._json([{"conid": 265598, "84": "214.20", "86": "214.30"}])
                    return
                if self.path.startswith("/v1/api/iserver/marketdata/history"):
                    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    self._json({
                        "data": [
                            {"t": now_ms - 60_000, "c": 214.10},
                            {"t": now_ms, "c": 214.25},
                        ],
                    })
                    return
                self._json({"error": "not found"}, status=404)

            def do_POST(self) -> None:  # noqa: N802
                owner.requests.append(self.path)
                if self.path == "/v1/api/iserver/secdef/search":
                    self._json([{"symbol": "AAPL", "conid": 265598, "secType": "STK"}])
                    return
                self._json({"error": "not found"}, status=404)

            def log_message(self, *_args: Any) -> None:
                return

            def _json(self, payload: Any, *, status: int = 200) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self._handler = Handler
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url = ""

    def __enter__(self) -> "_AfterHoursGateway":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler)
        host, port = self._server.server_address
        self.url = f"http://{host}:{port}/v1/api"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


def test_quote_and_read_models(monkeypatch) -> None:
    monkeypatch.setenv("ITHACA_IBKR_ENGINE_TOKEN", "engine-token")
    with _Gateway() as gateway:
        monkeypatch.setenv("IBKR_CLIENT_PORTAL_URL", gateway.url)
        client = TestClient(app)
        headers = {"Authorization": "Bearer engine-token"}

        status = client.get("/auth/status", headers=headers)
        tickle = client.post("/auth/tickle", headers=headers)
        ensure = client.post("/auth/ensure", headers=headers)
        data_health = client.get("/data/healthz")
        quote = client.get("/quote?symbol=aapl", headers=headers)
        extended_quote = client.get("/quote?symbol=aapl&include_extended_hours=true", headers=headers)
        history = client.get("/history?symbol=aapl&period=1d&bar=5min", headers=headers)
        news = client.get("/news?ticker=aapl&limit=2", headers=headers)
        scanner = client.get("/scanner?scan_type=most_active&limit=1", headers=headers)
        accounts = client.get("/accounts", headers=headers)
        positions = client.get("/positions?account=DU12345", headers=headers)
        orders = client.get("/orders?account=DU12345", headers=headers)

    assert status.status_code == 200
    assert status.json()["authenticated"] is True
    assert tickle.status_code == 200
    assert tickle.json() == {
        "authenticated": True,
        "connected": True,
        "established": False,
        "competing": False,
        "requires_login": False,
    }
    assert ensure.status_code == 200
    assert ensure.json()["authenticated"] is True
    assert data_health.status_code == 200
    assert data_health.json()["gateway"]["authenticated"] is True
    assert quote.status_code == 200
    assert quote.json()["data"]["quote"]["symbol"] == "AAPL"
    assert quote.json()["data"]["quote"]["price"] == 212.45
    assert quote.json()["data"]["quote"]["source"] == "ithaca-live-data"
    assert quote.json()["data"]["quote"]["entitlement_class"] == "ithaca_live"
    assert extended_quote.status_code == 200
    assert extended_quote.json()["data"]["quote"]["extended_hours_requested"] is True
    assert any("outsideRth=true" in request["path"] for request in gateway.requests)
    assert history.status_code == 200
    assert history.json()["points"][-1]["c"] == 213.0
    assert news.status_code == 200
    assert news.json()["items"][0]["source"] == "Briefing.com General Market Columns"
    assert scanner.status_code == 200
    assert scanner.json()["rows"][0]["symbol"] == "AAPL"
    assert accounts.json()["accounts"] == [
        {"label": "Account 1", "type": "PAPER", "currency": None, "status": "connected"}
    ]
    assert positions.json()["positions"] == [{"contractDesc": "AAPL", "position": 2}]
    assert orders.json()["orders"] == [{"orderId": "100", "ticker": "AAPL"}]


def test_expired_iserver_is_repaired_before_quote(monkeypatch) -> None:
    monkeypatch.setenv("ITHACA_IBKR_ENGINE_TOKEN", "engine-token")
    monkeypatch.setenv("IBKR_AUTH_INIT_ATTEMPTS", "1")
    with _ExpiredIserverGateway() as gateway:
        monkeypatch.setenv("IBKR_CLIENT_PORTAL_URL", gateway.url)
        client = TestClient(app)
        quote = client.get("/quote?symbol=aapl", headers={"Authorization": "Bearer engine-token"})

    assert quote.status_code == 200
    assert quote.json()["data"]["quote"]["price"] == 212.45
    assert gateway.init_bodies == [{"publish": True, "compete": True}]


def test_data_health_fails_when_iserver_is_not_authenticated(monkeypatch) -> None:
    monkeypatch.setenv("ITHACA_IBKR_ENGINE_TOKEN", "engine-token")
    monkeypatch.delenv("IBKR_DATA_HEALTH_AUTO_REPAIR", raising=False)
    with _ExpiredIserverGateway() as gateway:
        monkeypatch.setenv("IBKR_CLIENT_PORTAL_URL", gateway.url)
        client = TestClient(app)
        response = client.get("/data/healthz")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "IBKR_DATA_UNAVAILABLE"
    assert response.json()["detail"]["details"]["authenticated"] is False


def test_auth_repair_stops_immediately_when_browser_login_is_required(monkeypatch) -> None:
    gateway = ClientPortalGateway("http://login-required.invalid")
    monkeypatch.setattr(
        gateway,
        "auth_status",
        lambda **_kwargs: {
            "authenticated": False,
            "connected": False,
            "requires_login": True,
        },
    )
    tickle_called = False

    def tickle() -> dict[str, Any]:
        nonlocal tickle_called
        tickle_called = True
        return {"authenticated": False}

    monkeypatch.setattr(gateway, "tickle", tickle)

    with pytest.raises(ClientPortalAuthError, match="browser login is required"):
        gateway.ensure_authenticated()

    assert tickle_called is False


def test_auth_repair_maps_init_unauthorized_to_login_required(monkeypatch) -> None:
    gateway = ClientPortalGateway("http://init-unauthorized.invalid")
    monkeypatch.setattr(
        gateway,
        "auth_status",
        lambda **_kwargs: {
            "authenticated": False,
            "connected": True,
            "requires_login": False,
        },
    )
    monkeypatch.setattr(
        gateway,
        "tickle",
        lambda **_kwargs: {
            "authenticated": False,
            "connected": True,
            "requires_login": False,
        },
    )

    def unauthorized_init(**_kwargs: Any) -> dict[str, Any]:
        raise ClientPortalHttpError(401, '{"error":"login required"}')

    monkeypatch.setattr(gateway, "initialize_brokerage_session", unauthorized_init)

    with pytest.raises(ClientPortalAuthError, match="browser login is required"):
        gateway.ensure_authenticated()


def test_auth_repair_attempts_are_bounded(monkeypatch) -> None:
    gateway = ClientPortalGateway("http://bounded-repair.invalid")
    status_calls = 0
    init_calls = 0

    def status(**_kwargs: Any) -> dict[str, Any]:
        nonlocal status_calls
        status_calls += 1
        return {"authenticated": False, "connected": True, "requires_login": False}

    def initialize(**_kwargs: Any) -> dict[str, Any]:
        nonlocal init_calls
        init_calls += 1
        return {"authenticated": False, "connected": True, "requires_login": False}

    monkeypatch.setenv("IBKR_AUTH_INIT_ATTEMPTS", "999")
    monkeypatch.setenv("IBKR_AUTH_INIT_RETRY_DELAY_S", "0")
    monkeypatch.setenv("IBKR_AUTH_REPAIR_TIMEOUT_S", "120")
    monkeypatch.setattr(gateway, "auth_status", status)
    monkeypatch.setattr(
        gateway,
        "tickle",
        lambda **_kwargs: {
            "authenticated": False,
            "connected": True,
            "requires_login": False,
        },
    )
    monkeypatch.setattr(gateway, "initialize_brokerage_session", initialize)

    with pytest.raises(ClientPortalAuthError, match="not authenticated after"):
        gateway.ensure_authenticated()

    assert init_calls == 1
    assert status_calls == 12  # initial, after acquiring the lock, and ten bounded polls


def test_auth_repair_observes_delayed_authentication(monkeypatch) -> None:
    gateway = ClientPortalGateway("http://delayed-repair.invalid")
    statuses = iter(
        [
            {"authenticated": False, "connected": True, "requires_login": False},
            {"authenticated": False, "connected": True, "requires_login": False},
            {"authenticated": False, "connected": True, "requires_login": False},
            {"authenticated": True, "connected": True, "requires_login": False},
        ]
    )
    monkeypatch.setenv("IBKR_AUTH_INIT_ATTEMPTS", "5")
    monkeypatch.setenv("IBKR_AUTH_INIT_RETRY_DELAY_S", "0")
    monkeypatch.setattr(gateway, "auth_status", lambda **_kwargs: next(statuses))
    monkeypatch.setattr(
        gateway,
        "tickle",
        lambda **_kwargs: {
            "authenticated": False,
            "connected": True,
            "requires_login": False,
        },
    )
    monkeypatch.setattr(
        gateway,
        "initialize_brokerage_session",
        lambda **_kwargs: {
            "authenticated": False,
            "connected": True,
            "requires_login": False,
        },
    )

    result = gateway.ensure_authenticated()

    assert result["authenticated"] is True
    assert result["repair_action"] == "ssodh_init"


def test_auth_repair_waiters_fail_fast_when_repair_is_in_progress(monkeypatch) -> None:
    gateway = ClientPortalGateway("http://concurrent-repair.invalid")
    monkeypatch.setenv("IBKR_AUTH_REPAIR_LOCK_TIMEOUT_S", "0")
    monkeypatch.setattr(
        gateway,
        "auth_status",
        lambda **_kwargs: {
            "authenticated": False,
            "connected": True,
            "requires_login": False,
        },
    )
    monkeypatch.setattr(
        gateway,
        "tickle",
        lambda **_kwargs: {
            "authenticated": False,
            "connected": True,
            "requires_login": False,
        },
    )

    started = time.monotonic()
    ClientPortalGateway._auth_lock.acquire()
    try:
        with pytest.raises(ClientPortalAuthError, match="already in progress"):
            gateway.ensure_authenticated()
    finally:
        ClientPortalGateway._auth_lock.release()

    assert time.monotonic() - started < 0.1


def test_authenticated_but_disconnected_session_is_not_usable(monkeypatch) -> None:
    gateway = ClientPortalGateway("http://disconnected.invalid")
    monkeypatch.setenv("IBKR_AUTH_INIT_ATTEMPTS", "1")
    monkeypatch.setenv("IBKR_AUTH_INIT_RETRY_DELAY_S", "0")
    monkeypatch.setattr(
        gateway,
        "auth_status",
        lambda **_kwargs: {
            "authenticated": True,
            "connected": False,
            "requires_login": False,
        },
    )
    monkeypatch.setattr(
        gateway,
        "tickle",
        lambda **_kwargs: {
            "authenticated": True,
            "connected": False,
            "requires_login": False,
        },
    )
    monkeypatch.setattr(
        gateway,
        "initialize_brokerage_session",
        lambda **_kwargs: {
            "authenticated": True,
            "connected": False,
            "requires_login": False,
        },
    )

    assert gateway.data_health()["ok"] is False
    with pytest.raises(ClientPortalAuthError, match="not authenticated after"):
        gateway.ensure_authenticated()


def test_default_account_positions_authenticates_once(monkeypatch) -> None:
    gateway = ClientPortalGateway("http://positions-auth.invalid")
    auth_checks = 0

    def ensure() -> None:
        nonlocal auth_checks
        auth_checks += 1

    def request(method: str, path: str, **_kwargs: Any) -> Any:
        if path == "/portfolio/accounts":
            return [{"accountId": "DU12345"}]
        if path == "/portfolio/DU12345/positions/0":
            return []
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(gateway, "_ensure_authenticated_if_enabled", ensure)
    monkeypatch.setattr(gateway, "_request_json", request)

    result = gateway.positions()

    assert result["positions"] == []
    assert auth_checks == 1


def test_data_health_never_repairs_auth(monkeypatch) -> None:
    monkeypatch.setenv("IBKR_DATA_HEALTH_AUTO_REPAIR", "true")
    with _ExpiredIserverGateway() as gateway:
        monkeypatch.setenv("IBKR_CLIENT_PORTAL_URL", gateway.url)
        response = TestClient(app).get("/data/healthz")

    assert response.status_code == 503
    assert gateway.init_bodies == []
    assert all(request["path"] != "/v1/api/tickle" for request in gateway.requests)


@pytest.mark.parametrize(
    "detail",
    [
        '{"token":"s3cr3t"}',
        '{"outer":{"password":"s3cr3t"}}',
        "token=s3cr3t",
        "Bearer s3cr3t",
        "PASSWORD: s3cr3t",
        "session_id=s3cr3t",
    ],
)
def test_gateway_error_details_never_expose_secrets(detail: str) -> None:
    error = ClientPortalHttpError(500, detail)

    assert "s3cr3t" not in str(error)
    assert "s3cr3t" not in error.detail


def test_livez_stays_up_when_readyz_cannot_reach_gateway(monkeypatch) -> None:
    monkeypatch.setenv("IBKR_CLIENT_PORTAL_URL", "http://127.0.0.1:1/v1/api")
    monkeypatch.setenv("IBKR_CLIENT_PORTAL_TIMEOUT_S", "0.05")
    client = TestClient(app)

    assert client.get("/livez").status_code == 200
    assert client.get("/readyz").status_code == 503


@pytest.mark.parametrize(
    ("path", "method", "code"),
    [
        ("/auth/status", "get", "IBKR_AUTH_STATUS_FAILED"),
        ("/auth/tickle", "post", "IBKR_AUTH_TICKLE_FAILED"),
        ("/auth/ensure", "post", "IBKR_AUTH_REPAIR_FAILED"),
    ],
)
def test_auth_control_endpoint_error_contract(
    monkeypatch,
    path: str,
    method: str,
    code: str,
) -> None:
    class FailingGateway:
        def auth_status(self) -> dict[str, Any]:
            raise ClientPortalHttpError(500, "token=must-not-leak")

        def tickle(self) -> dict[str, Any]:
            raise ClientPortalHttpError(500, "token=must-not-leak")

        def ensure_authenticated(self) -> dict[str, Any]:
            raise ClientPortalHttpError(500, "token=must-not-leak")

    monkeypatch.setenv("ITHACA_IBKR_ENGINE_TOKEN", "engine-token")
    monkeypatch.setattr(app_module, "_gateway", lambda: FailingGateway())
    client = TestClient(app_module.app)

    response = getattr(client, method)(
        path,
        headers={"Authorization": "Bearer engine-token"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == code
    assert isinstance(response.json()["detail"]["message"], str)
    assert "must-not-leak" not in response.text


def test_quote_can_use_extended_hours_history_when_snapshot_has_no_last(monkeypatch) -> None:
    monkeypatch.setenv("ITHACA_IBKR_ENGINE_TOKEN", "engine-token")
    with _AfterHoursGateway() as gateway:
        monkeypatch.setenv("IBKR_CLIENT_PORTAL_URL", gateway.url)
        client = TestClient(app)
        quote = client.get(
            "/quote?symbol=aapl&extended_hours=true",
            headers={"Authorization": "Bearer engine-token"},
        )

    assert quote.status_code == 200
    body = quote.json()["data"]["quote"]
    assert body["symbol"] == "AAPL"
    assert body["price"] == 214.25
    assert any("outsideRth=true" in request for request in gateway.requests)


def test_bearer_token_is_required(monkeypatch) -> None:
    monkeypatch.setenv("ITHACA_IBKR_ENGINE_TOKEN", "engine-token")
    client = TestClient(app)

    assert client.get("/accounts").status_code == 401
    assert client.get("/accounts", headers={"Authorization": "Bearer bad"}).status_code == 403
    assert client.post("/auth/tickle").status_code == 401
    assert client.post("/auth/ensure").status_code == 401


def test_missing_engine_token_fails_closed_outside_local(monkeypatch) -> None:
    monkeypatch.setenv("ITHACA_ENV", "prod")
    monkeypatch.delenv("ITHACA_IBKR_ENGINE_TOKEN", raising=False)
    client = TestClient(app)

    resp = client.get("/accounts")

    assert resp.status_code == 503
    assert resp.json()["detail"] == "IBKR engine token is not configured"


def test_pre_login_gateway_is_reachable_but_requires_auth(monkeypatch) -> None:
    monkeypatch.setenv("ITHACA_IBKR_ENGINE_TOKEN", "engine-token")
    with _PreLoginGateway() as gateway:
        monkeypatch.setenv("IBKR_CLIENT_PORTAL_URL", gateway.url)
        client = TestClient(app)

        health = client.get("/healthz")
        status = client.get("/auth/status", headers={"Authorization": "Bearer engine-token"})

    assert health.status_code == 200
    assert health.json()["gateway"]["requires_login"] is True
    assert status.status_code == 200
    assert status.json()["authenticated"] is False
    assert status.json()["requires_login"] is True


def test_order_submission_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setenv("ITHACA_IBKR_ENGINE_TOKEN", "engine-token")
    monkeypatch.delenv("ITHACA_ENABLE_LIVE_EXECUTION", raising=False)
    client = TestClient(app)

    response = client.post(
        "/orders",
        headers={"Authorization": "Bearer engine-token"},
        json={"symbol": "AAPL", "side": "buy", "quantity": 1},
    )

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]
