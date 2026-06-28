from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from doomberg_core.providers import IbkrEngineClient


class _Server:
    def __init__(self, quote_payload: dict[str, Any], post_payload: dict[str, Any] | None = None) -> None:
        self.quote_payload = quote_payload
        self.post_payload = post_payload or {"status": "submitted", "id": "order-1"}
        self.requests: list[dict[str, Any]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                owner.requests.append({
                    "method": "GET",
                    "path": self.path,
                    "tenant": self.headers.get("X-Tenant-Id"),
                    "authorization": self.headers.get("Authorization"),
                })
                self._json(200, owner.quote_payload)

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or "0")
                body = json.loads(self.rfile.read(length) or b"{}")
                owner.requests.append({
                    "method": "POST",
                    "path": self.path,
                    "tenant": self.headers.get("X-Tenant-Id"),
                    "authorization": self.headers.get("Authorization"),
                    "body": body,
                })
                self._json(200, owner.post_payload)

            def log_message(self, *_args: Any) -> None:
                return

            def _json(self, status: int, payload: dict[str, Any]) -> None:
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

    def __enter__(self) -> "_Server":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler)
        host, port = self._server.server_address
        self.url = f"http://{host}:{port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


class _RouteServer:
    def __init__(self, routes: dict[str, dict[str, Any]]) -> None:
        self.routes = routes
        self.requests: list[dict[str, Any]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                owner.requests.append({
                    "method": "GET",
                    "path": self.path,
                    "tenant": self.headers.get("X-Tenant-Id"),
                    "authorization": self.headers.get("Authorization"),
                })
                payload = owner.routes.get(self.path, {})
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_args: Any) -> None:
                return

        self._handler = Handler
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url = ""

    def __enter__(self) -> "_RouteServer":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler)
        host, port = self._server.server_address
        self.url = f"http://{host}:{port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


def _quote_payload(
    event_time: datetime,
    *,
    price: float = 212.45,
    received_time: datetime | None = None,
) -> dict[str, Any]:
    received_time = received_time or event_time
    return {
        "data": {
            "quote": {
                "symbol": "AAPL",
                "lastPrice": price,
                "bidPrice": price - 0.01,
                "askPrice": price + 0.01,
                "event_time": event_time.isoformat(),
                "received_time": received_time.isoformat(),
                "source": "doomberg-live-data",
                "source_account": "ibkr-paper",
                "entitlement_class": "doomberg_live",
            }
        }
    }


def test_ibkr_quote_client_normalizes_smoke_and_submit_order() -> None:
    now = datetime.now(timezone.utc)
    with _Server(
        _quote_payload(now),
        post_payload={
            "status": "filled",
            "order_id": "ibkr-1",
            "avg_fill_price": 212.45,
            "filled_quantity": 1,
        },
    ) as server:
        client = IbkrEngineClient(
            base_url=server.url,
            token="secret-token",
            quote_path="/v1/quote/{symbol}",
            order_path="/v1/orders",
        )

        quote = client.quote("aapl", tenant_id="tenant-1")
        diagnosis = client.diagnose_quote("AAPL", tenant_id="tenant-1", max_freshness_ms=10_000)
        order = client.submit_order(
            tenant_id="tenant-1",
            intent_id="intent-1",
            client_order_id="client-1",
            order={"symbol": "AAPL", "side": "buy", "quantity": 1},
        )

    assert quote["symbol"] == "AAPL"
    assert quote["price"] == 212.45
    assert diagnosis["ok"] is True
    assert diagnosis["quote"]["source"] == "doomberg-live-data"
    assert diagnosis["quote"]["entitlement_class"] == "doomberg_live"
    assert "source_account" not in diagnosis["quote"]
    assert "raw" not in diagnosis["quote"]
    assert order["order_id"] == "ibkr-1"
    assert [request["method"] for request in server.requests] == ["GET", "GET", "POST"]
    assert server.requests[0]["path"] == "/v1/quote/AAPL"
    assert server.requests[0]["tenant"] == "tenant-1"
    assert server.requests[0]["authorization"] == "Bearer secret-token"
    assert server.requests[-1]["body"]["client_order_id"] == "client-1"


def test_ibkr_read_models_are_redacted_and_account_scoped() -> None:
    routes = {
        "/v1/accounts": {
            "accounts": [
                {"account_id": "DU12345", "type": "paper", "token": "secret"},
            ],
        },
        "/v1/positions?account=DU12345": {
            "positions": [
                {"symbol": "AAPL", "quantity": 2, "session": "secret-session"},
            ],
        },
        "/v1/orders?account=DU12345": {
            "orders": [
                {"order_id": "100", "symbol": "AAPL", "status": "Submitted", "secret": "x"},
            ],
        },
        "/v1/history?symbol=AAPL&period=1d&bar=5min": {
            "symbol": "AAPL",
            "points": [{"d": "2026-06-27T18:00:00+00:00", "c": 282.5}],
        },
        "/v1/news?limit=3&ticker=AAPL": {
            "scope": "AAPL",
            "items": [{"headline": "Apple moves higher", "source": "Doomberg"}],
        },
        "/v1/scanner?scan_type=MOST_ACTIVE&limit=2": {
            "rows": [{"symbol": "AAPL", "rank": 1}],
        },
    }
    with _RouteServer(routes) as server:
        client = IbkrEngineClient(
            base_url=server.url,
            token="secret-token",
            accounts_path="/v1/accounts",
            positions_path="/v1/positions?account={account}",
            orders_path="/v1/orders?account={account}",
            history_path="/v1/history?symbol={symbol}",
            news_path="/v1/news",
            scanner_path="/v1/scanner",
        )

        accounts = client.accounts(tenant_id="tenant-1")
        positions = client.positions(account="DU12345", tenant_id="tenant-1")
        orders = client.orders(account="DU12345", tenant_id="tenant-1")
        history = client.history("aapl", tenant_id="tenant-1")
        news = client.news(ticker="aapl", limit=3, tenant_id="tenant-1")
        scanner = client.scanner(scan_type="MOST_ACTIVE", limit=2, tenant_id="tenant-1")

    assert accounts["accounts"] == [
        {"label": "Account 1", "type": "paper", "currency": None, "status": "connected"}
    ]
    assert positions["positions"] == [{"symbol": "AAPL", "quantity": 2}]
    assert orders["orders"] == [{"order_id": "100", "symbol": "AAPL", "status": "Submitted"}]
    assert history["points"][0]["c"] == 282.5
    assert news["items"][0]["source"] == "Doomberg"
    assert scanner["rows"][0]["symbol"] == "AAPL"
    assert [request["path"] for request in server.requests] == [
        "/v1/accounts",
        "/v1/positions?account=DU12345",
        "/v1/orders?account=DU12345",
        "/v1/history?symbol=AAPL&period=1d&bar=5min",
        "/v1/news?limit=3&ticker=AAPL",
        "/v1/scanner?scan_type=MOST_ACTIVE&limit=2",
    ]
    assert {request["tenant"] for request in server.requests} == {"tenant-1"}


def test_ibkr_diagnose_reports_stale_quote_when_limit_is_enforced() -> None:
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    with _Server(_quote_payload(old, received_time=datetime.now(timezone.utc))) as server:
        result = IbkrEngineClient(base_url=server.url).diagnose_quote(
            "AAPL",
            max_freshness_ms=1_000,
        )

    assert result["ok"] is False
    assert result["status"] == "invariant_failed"
    assert result["code"] == "DATA_STALE"
    failed = {row["name"] for row in result["invariants"] if not row["ok"]}
    assert "freshness_within_limit" in failed


def test_ibkr_diagnose_fails_when_quote_timestamps_are_missing() -> None:
    payload = {
        "quote": {
            "symbol": "AAPL",
            "last": 212.45,
            "source": "doomberg-live-data",
            "entitlement_class": "doomberg_live",
        }
    }
    with _Server(payload) as server:
        result = IbkrEngineClient(base_url=server.url).diagnose_quote("AAPL")

    assert result["ok"] is False
    failed = {row["name"] for row in result["invariants"] if not row["ok"]}
    assert {"event_time_present", "received_time_present"} <= failed


def test_ibkr_diagnose_reports_not_configured() -> None:
    result = IbkrEngineClient(base_url="").diagnose_quote("AAPL")

    assert result["ok"] is False
    assert result["status"] == "not_configured"
    assert result["code"] == "BROKER_CONNECTION_REQUIRED"
