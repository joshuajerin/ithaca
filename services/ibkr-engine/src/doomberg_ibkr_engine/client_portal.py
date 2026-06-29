from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape
from typing import Any


PUBLIC_DATA_SOURCE = "doomberg-live-data"
PUBLIC_ENTITLEMENT_CLASS = "doomberg_live"


class ClientPortalError(RuntimeError):
    """Base error for private market-data gateway calls."""


class ClientPortalHttpError(ClientPortalError):
    """The gateway returned a non-2xx response."""

    def __init__(self, status: int, detail: str = "") -> None:
        self.status = int(status)
        self.detail = detail[:1000]
        super().__init__(f"market-data gateway HTTP {self.status}")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_number(data: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = data.get(name)
        if value is None or value == "":
            continue
        if isinstance(value, str):
            value = value.replace(",", "")
        try:
            out = float(value)
        except (TypeError, ValueError):
            continue
        if out == out:
            return out
    return None


class ClientPortalGateway:
    """Small stdlib client for the local private market-data gateway."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_s: float | None = None,
        verify_ssl: bool | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("IBKR_CLIENT_PORTAL_URL")
            or "https://127.0.0.1:5000/v1/api"
        ).rstrip("/")
        self.timeout_s = float(timeout_s or os.environ.get("IBKR_CLIENT_PORTAL_TIMEOUT_S") or "10")
        verify = verify_ssl
        if verify is None:
            verify = _env_bool("IBKR_CLIENT_PORTAL_VERIFY_SSL", default=False)
        self._ssl_context = None if verify else ssl._create_unverified_context()

    def health(self) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            status = self.auth_status()
        except ClientPortalHttpError as exc:
            if exc.status in {401, 403}:
                return {
                    "ok": True,
                    "upstream": "private-market-data",
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "authenticated": False,
                    "connected": False,
                    "requires_login": True,
                }
            raise
        except ClientPortalError as exc:
            return {
                "ok": False,
                "upstream": "private-market-data",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": str(exc),
            }
        return {
            "ok": True,
            "upstream": "private-market-data",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "authenticated": bool(status.get("authenticated")),
            "connected": bool(status.get("connected")),
            "requires_login": bool(status.get("requires_login")),
        }

    def auth_status(self) -> dict[str, Any]:
        try:
            raw = self._request_json("GET", "/iserver/auth/status")
        except ClientPortalHttpError as exc:
            if exc.status in {401, 403}:
                return {
                    "authenticated": False,
                    "connected": False,
                    "requires_login": True,
                    "raw_status": exc.status,
                }
            raise
        if not isinstance(raw, dict):
            return {"authenticated": False, "raw": raw}
        return {
            "authenticated": bool(raw.get("authenticated")),
            "connected": bool(raw.get("connected")),
            "competing": bool(raw.get("competing")),
            "message": raw.get("message"),
            "raw": raw,
        }

    def accounts(self) -> dict[str, Any]:
        raw = self._request_json("GET", "/portfolio/accounts")
        accounts = raw if isinstance(raw, list) else raw.get("accounts") if isinstance(raw, dict) else []
        if not isinstance(accounts, list):
            accounts = []
        return {
            "provider": PUBLIC_DATA_SOURCE,
            "source": PUBLIC_DATA_SOURCE,
            "entitlement_class": PUBLIC_ENTITLEMENT_CLASS,
            "accounts": [_public_account(idx, item) for idx, item in enumerate(accounts, start=1)],
            "raw_count": len(accounts),
        }

    def positions(self, account: str | None = None) -> dict[str, Any]:
        resolved = account or self.default_account()
        if not resolved:
            return {
                "provider": PUBLIC_DATA_SOURCE,
                "source": PUBLIC_DATA_SOURCE,
                "entitlement_class": PUBLIC_ENTITLEMENT_CLASS,
                "positions": [],
                "raw_count": 0,
            }
        raw = self._request_json("GET", f"/portfolio/{urllib.parse.quote(resolved)}/positions/0")
        positions = raw if isinstance(raw, list) else raw.get("positions") if isinstance(raw, dict) else []
        if not isinstance(positions, list):
            positions = []
        return {
            "provider": PUBLIC_DATA_SOURCE,
            "source": PUBLIC_DATA_SOURCE,
            "entitlement_class": PUBLIC_ENTITLEMENT_CLASS,
            "positions": [_redact(item) for item in positions],
            "raw_count": len(positions),
        }

    def orders(self, account: str | None = None) -> dict[str, Any]:
        raw = self._request_json("GET", "/iserver/account/orders")
        orders = raw.get("orders") if isinstance(raw, dict) else raw if isinstance(raw, list) else []
        if not isinstance(orders, list):
            orders = []
        return {
            "provider": PUBLIC_DATA_SOURCE,
            "source": PUBLIC_DATA_SOURCE,
            "entitlement_class": PUBLIC_ENTITLEMENT_CLASS,
            "orders": [_redact(item) for item in orders],
            "raw_count": len(orders),
        }

    def quote(self, symbol: str, *, include_extended_hours: bool = False) -> dict[str, Any]:
        symbol = (symbol or "").strip().upper()
        if not symbol:
            raise ClientPortalError("symbol is required")
        contract = self.find_contract(symbol)
        conid = str(contract.get("conid") or contract.get("conidEx") or "").strip()
        if not conid:
            raise ClientPortalError(f"IBKR contract lookup failed for {symbol}")
        fields = os.environ.get("IBKR_MARKETDATA_FIELDS") or "31,84,86,6509,7059,7068"
        raw: Any = []
        row: dict[str, Any] = {}
        attempts = max(1, int(os.environ.get("IBKR_SNAPSHOT_ATTEMPTS") or "3"))
        delay_s = max(0.0, float(os.environ.get("IBKR_SNAPSHOT_RETRY_DELAY_S") or "1"))
        for attempt in range(attempts):
            query = (
                f"/iserver/marketdata/snapshot?conids={urllib.parse.quote(conid)}"
                f"&fields={fields}"
            )
            if include_extended_hours:
                query = f"{query}&outsideRth=true"
            raw = self._request_json(
                "GET",
                query,
            )
            rows = raw if isinstance(raw, list) else raw.get("data") if isinstance(raw, dict) else []
            candidate = rows[0] if isinstance(rows, list) and rows else raw if isinstance(raw, dict) else {}
            row = candidate if isinstance(candidate, dict) else {}
            if _first_number(row, ("31", "last", "lastPrice", "price")) is not None:
                break
            if attempt < attempts - 1 and delay_s:
                time.sleep(delay_s)
        received = _now_iso()
        price = _first_number(row, ("31", "last", "lastPrice", "price"))
        event_time = _event_time(row)
        if price is None and include_extended_hours:
            fallback = self._latest_extended_history_quote(symbol, conid)
            if fallback is not None:
                price = fallback["price"]
                event_time = fallback["event_time"]
                row = {**row, "extended_hours_fallback": fallback["raw"]}
        return {
            "data": {
                "quote": {
                    "symbol": symbol,
                    "conid": conid,
                    "price": price,
                    "last": price,
                    "bid": _first_number(row, ("84", "bid", "bidPrice")),
                    "ask": _first_number(row, ("86", "ask", "askPrice")),
                    "source": PUBLIC_DATA_SOURCE,
                    "entitlement_class": PUBLIC_ENTITLEMENT_CLASS,
                    "extended_hours_requested": include_extended_hours,
                    "event_time": event_time or received,
                    "received_time": received,
                    "raw": _redact(row),
                }
            }
        }

    def history(self, symbol: str, *, period: str = "1d", bar: str = "5min") -> dict[str, Any]:
        symbol = (symbol or "").strip().upper()
        if not symbol:
            raise ClientPortalError("symbol is required")
        contract = self.find_contract(symbol)
        conid = str(contract.get("conid") or contract.get("conidEx") or "").strip()
        if not conid:
            raise ClientPortalError(f"IBKR contract lookup failed for {symbol}")
        raw = self._request_json(
            "GET",
            "/iserver/marketdata/history?"
            f"conid={urllib.parse.quote(conid)}&period={urllib.parse.quote(period)}&bar={urllib.parse.quote(bar)}",
        )
        rows = raw.get("data") if isinstance(raw, dict) else []
        points: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            ts = _event_time({"t": row.get("t")}) or row.get("t")
            points.append({
                "d": ts,
                "t": ts,
                "o": _first_number(row, ("o", "open")),
                "h": _first_number(row, ("h", "high")),
                "l": _first_number(row, ("l", "low")),
                "c": _first_number(row, ("c", "close")),
                "v": _first_number(row, ("v", "volume")),
            })
        quote = {}
        if points:
            last = points[-1]
            quote = {
                "symbol": symbol,
                "price": last.get("c"),
                "asOf": last.get("t") or _now_iso(),
                "source": PUBLIC_DATA_SOURCE,
            }
        return {
            "provider": PUBLIC_DATA_SOURCE,
            "source": PUBLIC_DATA_SOURCE,
            "entitlement_class": PUBLIC_ENTITLEMENT_CLASS,
            "symbol": symbol,
            "conid": conid,
            "period": period,
            "bar": bar,
            "points": points,
            "quote": quote,
            "raw": _redact(raw) if isinstance(raw, dict) else {},
        }

    def _latest_extended_history_quote(self, symbol: str, conid: str) -> dict[str, Any] | None:
        period = os.environ.get("IBKR_EXTENDED_HISTORY_PERIOD") or "1d"
        bar = os.environ.get("IBKR_EXTENDED_HISTORY_BAR") or "1min"
        raw = self._request_json(
            "GET",
            "/iserver/marketdata/history?"
            f"conid={urllib.parse.quote(conid)}&period={urllib.parse.quote(period)}"
            f"&bar={urllib.parse.quote(bar)}&outsideRth=true",
        )
        rows = raw.get("data") if isinstance(raw, dict) else []
        if not isinstance(rows, list):
            return None
        for row in reversed(rows):
            if not isinstance(row, dict):
                continue
            price = _first_number(row, ("c", "close", "31", "last", "lastPrice", "price"))
            if price is None:
                continue
            return {
                "symbol": symbol,
                "price": price,
                "event_time": _event_time({"t": row.get("t")}) or _now_iso(),
                "raw": row,
            }
        return None

    def news(self, ticker: str | None = None, *, limit: int = 10) -> dict[str, Any]:
        ticker = (ticker or "").strip().upper() or None
        path = "/iserver/news/briefing"
        if ticker:
            contract = self.find_contract(ticker)
            conid = str(contract.get("conid") or contract.get("conidEx") or "").strip()
            if conid:
                path = f"{path}?conid={urllib.parse.quote(conid)}"
        raw = self._request_json("GET", path)
        items = _briefing_items(raw, ticker=ticker, limit=limit)
        return {
            "provider": PUBLIC_DATA_SOURCE,
            "source": PUBLIC_DATA_SOURCE,
            "entitlement_class": PUBLIC_ENTITLEMENT_CLASS,
            "scope": ticker or "Markets",
            "items": items,
            "count": len(items),
            "asOf": items[0].get("publishedAt") if items else _now_iso(),
            "raw": _redact(raw) if isinstance(raw, dict) else {},
        }

    def scanner(self, scan_type: str = "MOST_ACTIVE", *, limit: int = 25) -> dict[str, Any]:
        body = {
            "instrument": os.environ.get("IBKR_SCANNER_INSTRUMENT") or "STK",
            "type": (scan_type or "MOST_ACTIVE").strip().upper(),
            "location": os.environ.get("IBKR_SCANNER_LOCATION") or "STK.US.MAJOR",
            "filter": [],
        }
        raw = self._request_json("POST", "/iserver/scanner/run", body=body)
        contracts = raw.get("contracts") if isinstance(raw, dict) else []
        rows: list[dict[str, Any]] = []
        conids: list[str] = []
        for idx, item in enumerate(contracts if isinstance(contracts, list) else []):
            if not isinstance(item, dict):
                continue
            conid = item.get("con_id") or item.get("conid") or item.get("conidex")
            if conid:
                conids.append(str(conid))
            rows.append({
                "rank": idx + 1,
                "symbol": item.get("symbol") or item.get("contract_description_1"),
                "name": item.get("company_name") or item.get("description"),
                "conid": conid,
                "exchange": item.get("listing_exchange"),
                "secType": item.get("sec_type"),
                "scanType": body["type"],
                "column": item.get("column_name"),
            })
            if len(rows) >= limit:
                break
        snapshots = self._snapshots(conids[: min(len(conids), 25)])
        for row in rows:
            snap = snapshots.get(str(row.get("conid")))
            if not snap:
                continue
            row["price"] = _first_number(snap, ("31", "last", "price"))
            row["change"] = _first_number(snap, ("82", "7295"))
            row["changePct"] = _first_number(snap, ("83", "7296"))
            row["bid"] = _first_number(snap, ("84", "bid"))
            row["ask"] = _first_number(snap, ("86", "ask"))
        return {
            "provider": PUBLIC_DATA_SOURCE,
            "source": PUBLIC_DATA_SOURCE,
            "entitlement_class": PUBLIC_ENTITLEMENT_CLASS,
            "scanType": body["type"],
            "rows": rows,
            "count": len(rows),
            "asOf": _now_iso(),
        }

    def _snapshots(self, conids: list[str]) -> dict[str, dict[str, Any]]:
        if not conids:
            return {}
        fields = "55,31,82,83,84,86,7295,7296,6509,7059,7068"
        raw = self._request_json(
            "GET",
            "/iserver/marketdata/snapshot?"
            f"conids={urllib.parse.quote(','.join(conids))}&fields={urllib.parse.quote(fields)}",
        )
        rows = raw if isinstance(raw, list) else raw.get("data") if isinstance(raw, dict) else []
        out: dict[str, dict[str, Any]] = {}
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and row.get("conid") is not None:
                out[str(row["conid"])] = row
        return out

    def find_contract(self, symbol: str) -> dict[str, Any]:
        body = {"symbol": symbol.upper(), "name": False}
        try:
            raw = self._request_json("POST", "/iserver/secdef/search", body=body)
        except ClientPortalHttpError:
            query = urllib.parse.urlencode(body)
            raw = self._request_json("GET", f"/iserver/secdef/search?{query}")
        rows = raw if isinstance(raw, list) else raw.get("data") if isinstance(raw, dict) else []
        if not isinstance(rows, list):
            rows = []
        stock_rows = [
            row for row in rows
            if isinstance(row, dict)
            and str(row.get("symbol") or "").upper() == symbol.upper()
            and str(row.get("secType") or row.get("assetClass") or "STK").upper() in {"STK", "STOCK"}
        ]
        if stock_rows:
            return stock_rows[0]
        for row in rows:
            if isinstance(row, dict) and (row.get("conid") or row.get("conidEx")):
                return row
        return {}

    def default_account(self) -> str | None:
        raw = self.accounts()
        for account in raw.get("accounts") or []:
            if not isinstance(account, dict):
                continue
            account_id = account.get("accountId") or account.get("account_id") or account.get("id")
            if account_id:
                return str(account_id)
        return None

    def _request_json(self, method: str, path: str, *, body: dict[str, Any] | None = None) -> Any:
        url = path if urllib.parse.urlparse(path).scheme else f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "doomberg-live-data-engine")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s, context=self._ssl_context) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ClientPortalHttpError(exc.code, detail) from exc
        except urllib.error.URLError as exc:
            raise ClientPortalError(f"market-data gateway unreachable: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ClientPortalError("market-data gateway returned invalid JSON") from exc


def _event_time(row: dict[str, Any]) -> str | None:
    for key in ("_updated", "updated", "timestamp", "time"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return str(value)
        if numeric > 10_000_000_000:
            numeric = numeric / 1000.0
        return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()
    return None


def _strip_html(value: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _briefing_items(raw: Any, *, ticker: str | None, limit: int) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    title = str(raw.get("title") or "Market briefing").strip()
    content = str(raw.get("content") or "")
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", content, flags=re.I | re.S)
    if not paragraphs and content:
        paragraphs = [content]
    items: list[dict[str, Any]] = []
    provider = raw.get("provider") or raw.get("source") or "Market data"
    now = _now_iso()
    for idx, paragraph in enumerate(paragraphs[: max(1, limit)]):
        summary = _strip_html(paragraph)
        if not summary:
            continue
        headline = title if idx == 0 else summary[:140]
        items.append({
            "id": f"market-briefing-{idx}",
            "headline": headline,
            "source": provider,
            "summary": summary,
            "url": None,
            "publishedAt": raw.get("published_at") or raw.get("publishedAt") or now,
            "sentiment": None,
            "tickers": [ticker] if ticker else [],
            "sector": None,
        })
    if not items and title:
        items.append({
            "id": "market-briefing",
            "headline": title,
            "source": provider,
            "summary": _strip_html(content),
            "url": None,
            "publishedAt": now,
            "sentiment": None,
            "tickers": [ticker] if ticker else [],
            "sector": None,
        })
    return items[:limit]


def _redact(item: Any) -> dict[str, Any]:
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
        "ssotoken",
        "token",
        "account",
        "accountid",
        "account_id",
        "accountvan",
        "acctid",
        "acct_id",
        "id",
    }
    return {str(key): value for key, value in item.items() if str(key).lower() not in blocked}


def _public_account(idx: int, item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"label": f"Account {idx}", "type": "data"}
    return {
        "label": f"Account {idx}",
        "type": item.get("type") or item.get("tradingType") or "data",
        "currency": item.get("currency"),
        "status": "connected",
    }
