"""Shared client for the user-run IBKR engine.

The IBKR engine is a connected-account boundary. This client intentionally exposes only
read-only account/market-data routes and explicit order-submission calls used by the execution
gateway.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


class IbkrEngineError(RuntimeError):
    """Base error for the user-run IBKR engine adapter."""


class IbkrEngineConnectionError(IbkrEngineError):
    """The engine could not be reached."""


class IbkrEngineHttpError(IbkrEngineError):
    """The engine returned a non-2xx HTTP response."""

    def __init__(self, status: int, detail: str = "") -> None:
        self.status = int(status)
        self.detail = detail[:1000]
        super().__init__(f"IBKR engine HTTP {self.status}")


class IbkrQuoteInvariantError(IbkrEngineError):
    """A quote response did not satisfy the minimum provider contract."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any, *, default: datetime | None = None) -> datetime:
    return _coerce_time(value) or default or _now()


def _coerce_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return _epoch_to_datetime(float(value))
    if isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            return _epoch_to_datetime(float(text))
        except ValueError:
            pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _epoch_to_datetime(value: float) -> datetime:
    if value > 10_000_000_000:
        value = value / 1000.0
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _first_number(data: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = data.get(name)
        if value is None:
            continue
        try:
            out = float(value)
        except (TypeError, ValueError):
            continue
        if out == out:
            return out
    return None


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return max(0, value)


def normalize_quote(raw: dict[str, Any], *, symbol: str, source: str = "ibkr-engine") -> dict[str, Any]:
    """Normalize common IBKR-engine quote shapes into the canonical trigger quote contract."""

    payload = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    payload = payload.get("quote") if isinstance(payload.get("quote"), dict) else payload
    if not isinstance(payload, dict):
        raise IbkrQuoteInvariantError(f"quote for {symbol.upper()} did not include a JSON object")
    price = _first_number(
        payload,
        (
            "price",
            "last",
            "last_price",
            "lastPrice",
            "marketPrice",
            "mark",
            "close",
        ),
    )
    if price is None:
        raise IbkrQuoteInvariantError(f"quote for {symbol.upper()} did not include a price")
    event_value = (
        payload.get("event_time")
        or payload.get("as_of")
        or payload.get("asOf")
        or payload.get("timestamp")
        or payload.get("time")
    )
    received_value = (
        payload.get("received_time")
        or payload.get("receivedTime")
        or payload.get("received_at")
        or payload.get("receivedAt")
    )
    event_time = _coerce_time(event_value)
    received_time = _coerce_time(received_value)
    quality_flags = []
    if event_time is None:
        quality_flags.append("EVENT_TIME_DEFAULTED")
        event_time = _now()
    if received_time is None:
        quality_flags.append("RECEIVED_TIME_DEFAULTED")
        received_time = _now()
    freshness_ms = max(0, int((received_time - event_time).total_seconds() * 1000))
    return {
        "symbol": str(payload.get("symbol") or symbol).upper(),
        "price": price,
        "last": price,
        "bid": _first_number(payload, ("bid", "bid_price", "bidPrice")),
        "ask": _first_number(payload, ("ask", "ask_price", "askPrice")),
        "source": str(payload.get("source") or source),
        "source_account": payload.get("source_account") or payload.get("account") or "ibkr-vps",
        "entitlement_class": payload.get("entitlement_class") or "connected_account",
        "event_time": event_time.isoformat(),
        "received_time": received_time.isoformat(),
        "freshness_ms": freshness_ms,
        "quality_flags": quality_flags,
        "raw": raw,
    }


def public_quote(quote: dict[str, Any]) -> dict[str, Any]:
    """Return a non-secret quote view suitable for diagnostics and UI display."""

    return {k: v for k, v in quote.items() if k != "raw"}


def _payload_list(raw: Any, *names: str) -> list[Any]:
    """Extract common list shapes from an IBKR engine response."""

    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []
    for container in (raw, raw.get("data") if isinstance(raw.get("data"), dict) else None):
        if not isinstance(container, dict):
            continue
        for name in names:
            value = container.get(name)
            if isinstance(value, list):
                return value
    return []


def _redacted_item(item: Any) -> dict[str, Any]:
    """Return a JSON-safe item view without common credential/session fields."""

    if not isinstance(item, dict):
        return {"value": item}
    blocked = {
        "authorization",
        "cookie",
        "cookies",
        "credential",
        "credential_ref",
        "password",
        "secret",
        "session",
        "session_id",
        "token",
    }
    return {
        str(key): value
        for key, value in item.items()
        if str(key).lower() not in blocked
    }


class IbkrEngineClient:
    """Small HTTP client for the user-run IBKR engine."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        quote_path: str | None = None,
        order_path: str | None = None,
        accounts_path: str | None = None,
        positions_path: str | None = None,
        orders_path: str | None = None,
        timeout_s: float = 5.0,
    ) -> None:
        resolved_url = base_url if base_url is not None else os.environ.get("DOOMBERG_IBKR_ENGINE_URL")
        self.base_url = (resolved_url or "").rstrip("/")
        self.token = token if token is not None else os.environ.get("DOOMBERG_IBKR_ENGINE_TOKEN")
        self.quote_path = quote_path or os.environ.get("DOOMBERG_IBKR_QUOTE_PATH") or "/quote?symbol={symbol}"
        self.order_path = order_path or os.environ.get("DOOMBERG_IBKR_ORDER_PATH") or "/orders"
        self.accounts_path = (
            accounts_path or os.environ.get("DOOMBERG_IBKR_ACCOUNTS_PATH") or "/accounts"
        )
        self.positions_path = (
            positions_path or os.environ.get("DOOMBERG_IBKR_POSITIONS_PATH")
            or "/positions?account={account}"
        )
        self.orders_path = (
            orders_path or os.environ.get("DOOMBERG_IBKR_ORDERS_PATH")
            or "/orders?account={account}"
        )
        self.timeout_s = float(timeout_s)

    @property
    def host(self) -> str | None:
        if not self.base_url:
            return None
        parsed = urllib.parse.urlparse(self.base_url)
        return parsed.netloc or "configured"

    def configured(self) -> bool:
        return bool(self.base_url)

    def url_for_path(
        self,
        path: str,
        *,
        symbol: str | None = None,
        account: str | None = None,
    ) -> str:
        if not self.base_url:
            raise IbkrEngineConnectionError("DOOMBERG_IBKR_ENGINE_URL is not configured")
        resolved = path
        if symbol is not None:
            encoded = urllib.parse.quote(symbol.upper())
            if "{symbol}" in resolved:
                resolved = resolved.replace("{symbol}", encoded)
            else:
                sep = "&" if "?" in resolved else "?"
                resolved = f"{resolved}{sep}symbol={encoded}"
        if account is not None:
            encoded = urllib.parse.quote(str(account))
            if "{account}" in resolved:
                resolved = resolved.replace("{account}", encoded)
            else:
                sep = "&" if "?" in resolved else "?"
                resolved = f"{resolved}{sep}account={encoded}"
        if urllib.parse.urlparse(resolved).scheme:
            return resolved
        return f"{self.base_url}{resolved if resolved.startswith('/') else '/' + resolved}"

    def quote(self, symbol: str, *, tenant_id: str | None = None) -> dict[str, Any]:
        raw = self._request_json(
            "GET",
            self.url_for_path(self.quote_path, symbol=symbol),
            tenant_id=tenant_id,
            user_agent="doomberg-ibkr-quote",
        )
        if not isinstance(raw, dict):
            raise IbkrQuoteInvariantError(f"quote for {symbol.upper()} did not include a JSON object")
        return normalize_quote(raw, symbol=symbol, source="ibkr-engine")

    def accounts(self, *, tenant_id: str | None = None) -> dict[str, Any]:
        """Return a redacted read-only account summary from the user-run IBKR engine."""

        raw = self._request_json(
            "GET",
            self.url_for_path(self.accounts_path),
            tenant_id=tenant_id,
            user_agent="doomberg-ibkr-accounts",
        )
        accounts = [_redacted_item(item) for item in _payload_list(raw, "accounts", "accountSummaries")]
        if not accounts and isinstance(raw, dict):
            account_id = raw.get("account") or raw.get("account_id") or raw.get("accountId")
            if account_id:
                accounts = [_redacted_item(raw)]
        return {
            "provider": "ibkr-engine",
            "source": "ibkr-engine",
            "entitlement_class": "connected_account",
            "accounts": accounts,
            "raw_count": len(accounts),
        }

    def positions(self, *, account: str | None = None, tenant_id: str | None = None) -> dict[str, Any]:
        """Return redacted read-only positions from the user-run IBKR engine."""

        raw = self._request_json(
            "GET",
            self.url_for_path(self.positions_path, account=account),
            tenant_id=tenant_id,
            user_agent="doomberg-ibkr-positions",
        )
        positions = [_redacted_item(item) for item in _payload_list(raw, "positions", "items")]
        return {
            "provider": "ibkr-engine",
            "source": "ibkr-engine",
            "source_account": account,
            "entitlement_class": "connected_account",
            "positions": positions,
            "raw_count": len(positions),
        }

    def orders(self, *, account: str | None = None, tenant_id: str | None = None) -> dict[str, Any]:
        """Return redacted read-only order state from the user-run IBKR engine."""

        raw = self._request_json(
            "GET",
            self.url_for_path(self.orders_path, account=account),
            tenant_id=tenant_id,
            user_agent="doomberg-ibkr-orders",
        )
        orders = [_redacted_item(item) for item in _payload_list(raw, "orders", "items")]
        return {
            "provider": "ibkr-engine",
            "source": "ibkr-engine",
            "source_account": account,
            "entitlement_class": "connected_account",
            "orders": orders,
            "raw_count": len(orders),
        }

    def submit_order(
        self,
        *,
        tenant_id: str,
        intent_id: str,
        client_order_id: str,
        order: dict[str, Any],
    ) -> dict[str, Any]:
        body = {
            "tenant_id": tenant_id,
            "intent_id": intent_id,
            "client_order_id": client_order_id,
            "order": order,
        }
        raw = self._request_json(
            "POST",
            self.url_for_path(self.order_path),
            body=body,
            tenant_id=tenant_id,
            user_agent="doomberg-execution-gateway",
        )
        return raw if isinstance(raw, dict) else {"raw": raw}

    def diagnose_quote(
        self,
        symbol: str = "AAPL",
        *,
        tenant_id: str | None = None,
        max_freshness_ms: int | None = None,
    ) -> dict[str, Any]:
        """Run a read-only quote smoke and validate the minimum live-data invariants."""

        symbol = (symbol or "AAPL").strip().upper()
        enforced_freshness = (
            max_freshness_ms
            if max_freshness_ms is not None
            else _env_int("DOOMBERG_IBKR_SMOKE_MAX_FRESHNESS_MS")
        )
        base = {
            "configured": self.configured(),
            "host": self.host,
            "quote_path": self.quote_path,
            "symbol": symbol,
            "latency_ms": None,
            "quote": None,
            "invariants": [],
        }
        if not self.configured():
            return {
                **base,
                "ok": False,
                "status": "not_configured",
                "code": "BROKER_CONNECTION_REQUIRED",
                "error": "DOOMBERG_IBKR_ENGINE_URL is not configured",
                "recovery_action": "Set DOOMBERG_IBKR_ENGINE_URL and rerun the IBKR smoke.",
            }

        started = time.perf_counter()
        try:
            quote = self.quote(symbol, tenant_id=tenant_id)
        except IbkrQuoteInvariantError as exc:
            return {
                **base,
                "ok": False,
                "status": "invariant_failed",
                "code": "PROVIDER_DEGRADED",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": str(exc),
                "recovery_action": "Inspect the IBKR engine quote response shape and normalizer contract.",
            }
        except IbkrEngineError as exc:
            return {
                **base,
                "ok": False,
                "status": "request_failed",
                "code": "PROVIDER_DEGRADED",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": str(exc),
                "recovery_action": "Check the VPS health, network path, token, and quote route.",
            }

        latency_ms = int((time.perf_counter() - started) * 1000)
        checks = self._quote_invariants(
            quote,
            requested_symbol=symbol,
            max_freshness_ms=enforced_freshness,
        )
        ok = all(check["ok"] for check in checks)
        failed = [check["name"] for check in checks if not check["ok"]]
        return {
            **base,
            "ok": ok,
            "status": "ok" if ok else "invariant_failed",
            "code": "OK" if ok else "DATA_STALE" if "freshness_within_limit" in failed else "PROVIDER_DEGRADED",
            "latency_ms": latency_ms,
            "quote": public_quote(quote),
            "invariants": checks,
            "recovery_action": "No action required." if ok else "Fix failed quote invariants before enabling live triggers.",
        }

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None = None,
        tenant_id: str | None = None,
        user_agent: str,
    ) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", user_agent)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if tenant_id:
            req.add_header("X-Tenant-Id", str(tenant_id))
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise IbkrEngineHttpError(exc.code, detail) from exc
        except urllib.error.URLError as exc:
            raise IbkrEngineConnectionError(f"IBKR engine unreachable: {exc.reason}") from exc
        except Exception as exc:
            raise IbkrEngineError(f"IBKR engine request failed: {exc}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise IbkrEngineError("IBKR engine returned invalid JSON") from exc

    def _quote_invariants(
        self,
        quote: dict[str, Any],
        *,
        requested_symbol: str,
        max_freshness_ms: int | None,
    ) -> list[dict[str, Any]]:
        now = _now()
        checks: list[dict[str, Any]] = []

        def check(name: str, ok: bool, detail: str, **extra: Any) -> None:
            checks.append({"name": name, "ok": bool(ok), "detail": detail, **extra})

        symbol = str(quote.get("symbol") or "").upper()
        price = quote.get("price")
        freshness_ms = quote.get("freshness_ms")
        event_time = _parse_time(quote.get("event_time"))
        quality_flags = set(quote.get("quality_flags") or [])
        check("symbol_matches", symbol == requested_symbol, f"{symbol or 'missing'} vs {requested_symbol}")
        check("price_positive", isinstance(price, (int, float)) and price > 0, str(price))
        check(
            "event_time_present",
            "EVENT_TIME_DEFAULTED" not in quality_flags,
            "defaulted" if "EVENT_TIME_DEFAULTED" in quality_flags else quote.get("event_time"),
        )
        check(
            "received_time_present",
            "RECEIVED_TIME_DEFAULTED" not in quality_flags,
            "defaulted" if "RECEIVED_TIME_DEFAULTED" in quality_flags else quote.get("received_time"),
        )
        check(
            "event_time_not_future",
            event_time <= now + timedelta(minutes=5),
            event_time.isoformat(),
        )
        check(
            "freshness_nonnegative",
            isinstance(freshness_ms, int) and freshness_ms >= 0,
            str(freshness_ms),
        )
        if max_freshness_ms is None:
            check(
                "freshness_limit_configured",
                True,
                "not enforced; set DOOMBERG_IBKR_SMOKE_MAX_FRESHNESS_MS or pass a limit",
                enforced=False,
            )
        else:
            check(
                "freshness_within_limit",
                isinstance(freshness_ms, int) and freshness_ms <= max_freshness_ms,
                f"{freshness_ms}ms <= {max_freshness_ms}ms",
                enforced=True,
                max_freshness_ms=max_freshness_ms,
            )
        check("source_present", bool(quote.get("source")), str(quote.get("source") or "missing"))
        check(
            "connected_account_entitlement",
            quote.get("entitlement_class") == "connected_account",
            str(quote.get("entitlement_class") or "missing"),
        )
        return checks
