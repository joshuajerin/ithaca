from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from fastapi.testclient import TestClient

from doomberg_ibkr_engine.app import app


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


def test_quote_and_read_models(monkeypatch) -> None:
    monkeypatch.setenv("DOOMBERG_IBKR_ENGINE_TOKEN", "engine-token")
    with _Gateway() as gateway:
        monkeypatch.setenv("IBKR_CLIENT_PORTAL_URL", gateway.url)
        client = TestClient(app)
        headers = {"Authorization": "Bearer engine-token"}

        status = client.get("/auth/status", headers=headers)
        quote = client.get("/quote?symbol=aapl", headers=headers)
        history = client.get("/history?symbol=aapl&period=1d&bar=5min", headers=headers)
        news = client.get("/news?ticker=aapl&limit=2", headers=headers)
        scanner = client.get("/scanner?scan_type=most_active&limit=1", headers=headers)
        accounts = client.get("/accounts", headers=headers)
        positions = client.get("/positions?account=DU12345", headers=headers)
        orders = client.get("/orders?account=DU12345", headers=headers)

    assert status.status_code == 200
    assert status.json()["authenticated"] is True
    assert quote.status_code == 200
    assert quote.json()["data"]["quote"]["symbol"] == "AAPL"
    assert quote.json()["data"]["quote"]["price"] == 212.45
    assert quote.json()["data"]["quote"]["source"] == "doomberg-live-data"
    assert quote.json()["data"]["quote"]["entitlement_class"] == "doomberg_live"
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


def test_bearer_token_is_required(monkeypatch) -> None:
    monkeypatch.setenv("DOOMBERG_IBKR_ENGINE_TOKEN", "engine-token")
    client = TestClient(app)

    assert client.get("/accounts").status_code == 401
    assert client.get("/accounts", headers={"Authorization": "Bearer bad"}).status_code == 403


def test_pre_login_gateway_is_reachable_but_requires_auth(monkeypatch) -> None:
    monkeypatch.setenv("DOOMBERG_IBKR_ENGINE_TOKEN", "engine-token")
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
    monkeypatch.setenv("DOOMBERG_IBKR_ENGINE_TOKEN", "engine-token")
    monkeypatch.delenv("DOOMBERG_ENABLE_LIVE_EXECUTION", raising=False)
    client = TestClient(app)

    response = client.post(
        "/orders",
        headers={"Authorization": "Bearer engine-token"},
        json={"symbol": "AAPL", "side": "buy", "quantity": 1},
    )

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]
