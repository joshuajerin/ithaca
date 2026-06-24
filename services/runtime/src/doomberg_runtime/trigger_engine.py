"""Stateful trigger engine.

The trigger engine is deliberately separate from MCP: it polls active trigger policies,
observes live market data through a provider client, evaluates typed conditions, and creates
durable Doomberg runs when a policy fires. A trigger never submits a broker order directly.
If a policy asks for execution, the engine creates an approval request around the proposed
action; the execution gateway is the only broker-write path.
"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from ._trace import emit
from .leader import acquire_loop_lease, process_owner, release_loop_lease

__all__ = [
    "HttpQuoteClient",
    "StaticQuoteClient",
    "TriggerEngine",
    "TriggerEvaluationError",
    "parse_duration_seconds",
]


class TriggerEvaluationError(RuntimeError):
    """A trigger could not be evaluated because required policy/data was missing."""


class QuoteClient(Protocol):
    def quote(self, symbol: str, *, tenant_id: str | None = None) -> dict[str, Any]:
        """Return one quote as a dict with at least symbol, price, source, and event_time."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat()


def _parse_time(value: Any, *, default: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        # IBKR-style timestamps may be epoch seconds or milliseconds.
        n = float(value)
        if n > 10_000_000_000:
            n = n / 1000.0
        return datetime.fromtimestamp(n, tz=timezone.utc)
    if isinstance(value, str) and value.strip():
        s = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(s)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return default or _now()


def _first_number(data: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = data.get(name)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _dig(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def parse_duration_seconds(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip().lower()
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    match = re.fullmatch(r"(\d+)\s*([smhd])", text)
    if not match:
        raise TriggerEvaluationError(f"invalid duration: {value!r}")
    amount = int(match.group(1))
    unit = match.group(2)
    return amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


class HttpQuoteClient:
    """HTTP adapter for a user-run IBKR engine.

    Defaults assume the VPS exposes ``GET /quote?symbol=NVDA`` and returns a JSON object.
    Set ``DOOMBERG_IBKR_QUOTE_PATH`` to override, e.g. ``/v1/market/quote/{symbol}``.
    The response normalizer accepts common shapes: ``price``, ``last``, ``last_price``,
    ``marketPrice``, or nested ``data``/``quote`` objects.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        quote_path: str | None = None,
        timeout_s: float = 5.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("DOOMBERG_IBKR_ENGINE_URL") or "").rstrip("/")
        self.token = token if token is not None else os.environ.get("DOOMBERG_IBKR_ENGINE_TOKEN")
        self.quote_path = quote_path or os.environ.get("DOOMBERG_IBKR_QUOTE_PATH") or "/quote?symbol={symbol}"
        self.timeout_s = float(timeout_s)

    def quote(self, symbol: str, *, tenant_id: str | None = None) -> dict[str, Any]:
        if not self.base_url:
            raise TriggerEvaluationError("DOOMBERG_IBKR_ENGINE_URL is not configured")
        url = self._url(symbol)
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "doomberg-trigger-engine")
        if tenant_id:
            req.add_header("X-Tenant-Id", str(tenant_id))
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise TriggerEvaluationError(f"IBKR engine HTTP {exc.code}") from exc
        except Exception as exc:
            raise TriggerEvaluationError(f"IBKR engine request failed: {exc}") from exc
        return normalize_quote(raw, symbol=symbol, source="ibkr-engine")

    def _url(self, symbol: str) -> str:
        encoded = urllib.parse.quote(symbol.upper())
        if "{symbol}" in self.quote_path:
            path = self.quote_path.replace("{symbol}", encoded)
        else:
            sep = "&" if "?" in self.quote_path else "?"
            path = f"{self.quote_path}{sep}symbol={encoded}"
        return f"{self.base_url}{path if path.startswith('/') else '/' + path}"


class StaticQuoteClient:
    """Deterministic quote client for tests and local demos."""

    def __init__(self, quotes: dict[str, dict[str, Any]]) -> None:
        self.quotes = {k.upper(): dict(v) for k, v in quotes.items()}

    def quote(self, symbol: str, *, tenant_id: str | None = None) -> dict[str, Any]:
        try:
            raw = self.quotes[symbol.upper()]
        except KeyError as exc:
            raise TriggerEvaluationError(f"no quote for {symbol.upper()}") from exc
        return normalize_quote(raw, symbol=symbol, source=raw.get("source") or "static")


def normalize_quote(raw: dict[str, Any], *, symbol: str, source: str) -> dict[str, Any]:
    payload = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    payload = payload.get("quote") if isinstance(payload.get("quote"), dict) else payload
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
        raise TriggerEvaluationError(f"quote for {symbol.upper()} did not include a price")
    event_time = _parse_time(
        payload.get("event_time")
        or payload.get("as_of")
        or payload.get("asOf")
        or payload.get("timestamp")
        or payload.get("time")
    )
    received_time = _parse_time(
        payload.get("received_time")
        or payload.get("receivedTime")
        or payload.get("received_at")
        or payload.get("receivedAt")
    )
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
        "raw": raw,
    }


@dataclass(frozen=True)
class _Decision:
    ok: bool
    reason: str
    context: dict[str, Any]


class TriggerEngine:
    def __init__(
        self,
        platform: Any,
        *,
        quote_client: QuoteClient | None = None,
        worker_id: str = "trigger-engine",
    ) -> None:
        self.platform = platform
        self.quote_client = quote_client or HttpQuoteClient()
        self.worker_id = worker_id

    def poll_once(self, *, now: datetime | None = None, limit: int = 256) -> dict[str, Any]:
        now = now or _now()
        triggers = self.platform.triggers.list_active_all(limit=limit)
        fired: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for trigger in triggers:
            try:
                outcome = self.evaluate(trigger, now=now)
                if outcome.get("fired"):
                    fired.append(outcome)
                else:
                    skipped.append(outcome)
            except Exception as exc:  # noqa: BLE001 - one bad policy must not stop the loop.
                errors.append({
                    "trigger_id": trigger.get("trigger_id"),
                    "tenant_id": trigger.get("tenant_id"),
                    "error": type(exc).__name__,
                    "detail": str(exc)[:300],
                })
        return {"evaluated": len(triggers), "fired": fired, "skipped": skipped, "errors": errors}

    def evaluate(self, trigger: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        now = now or _now()
        tenant_id = str(trigger["tenant_id"])
        policy = trigger.get("policy") or {}
        when = policy.get("when") or {}
        event = when.get("event") or "price.threshold"
        if event not in {"price.threshold", "market.price", "market.quote"}:
            return self._skip(trigger, "UNSUPPORTED_EVENT", {"event": event})

        symbol = self._symbol(policy)
        quote = self.quote_client.quote(symbol, tenant_id=tenant_id)
        context = self._context(trigger, policy, quote, now)
        decision = self._condition(policy.get("condition") or {}, context)
        if not decision.ok:
            return self._skip(trigger, "CONDITION_FALSE", decision.context)

        controls = policy.get("controls") or {}
        controls_check = self._controls(trigger, controls, context, now)
        if controls_check is not None:
            return controls_check

        return self._fire(trigger, policy, context, now)

    def _symbol(self, policy: dict[str, Any]) -> str:
        when = policy.get("when") or {}
        universe = when.get("universe")
        if isinstance(universe, list) and universe:
            return str(universe[0]).upper()
        for path in ("symbol", "when.symbol", "condition.symbol"):
            value = _dig(policy, path)
            if isinstance(value, str) and value:
                return value.upper()
        raise TriggerEvaluationError("trigger policy must include when.universe or symbol")

    def _context(
        self,
        trigger: dict[str, Any],
        policy: dict[str, Any],
        quote: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        freshness_seconds = max(0.0, float(quote.get("freshness_ms") or 0) / 1000.0)
        return {
            "tenant_id": trigger["tenant_id"],
            "trigger_id": trigger["trigger_id"],
            "trigger_name": trigger["name"],
            "symbol": quote["symbol"],
            "price": quote["price"],
            "last": quote["last"],
            "bid": quote.get("bid"),
            "ask": quote.get("ask"),
            "source": quote.get("source"),
            "source_account": quote.get("source_account"),
            "entitlement_class": quote.get("entitlement_class"),
            "event_time": quote.get("event_time"),
            "received_time": quote.get("received_time"),
            "freshness_seconds": freshness_seconds,
            "data_freshness_seconds": freshness_seconds,
            "quote": quote,
            "policy": policy,
            "now": now.isoformat(),
        }

    def _condition(self, condition: dict[str, Any], context: dict[str, Any]) -> _Decision:
        if not condition:
            return _Decision(True, "no condition", context)
        ok = self._eval_node(condition, context)
        return _Decision(ok, "condition matched" if ok else "condition false", context)

    def _eval_node(self, node: Any, context: dict[str, Any]) -> bool:
        if isinstance(node, dict):
            if "all" in node:
                return all(self._eval_node(x, context) for x in (node.get("all") or []))
            if "any" in node:
                return any(self._eval_node(x, context) for x in (node.get("any") or []))
            results: list[bool] = []
            for key, spec in node.items():
                actual = context.get(key)
                if key == "data_freshness_seconds":
                    actual = context.get("data_freshness_seconds")
                results.append(self._compare(actual, spec))
            return all(results)
        return bool(node)

    def _compare(self, actual: Any, spec: Any) -> bool:
        if isinstance(spec, dict):
            for op, expected in spec.items():
                if op in {"gte", "ge"} and not self._number_compare(actual, expected, lambda a, b: a >= b):
                    return False
                if op in {"lte", "le"} and not self._number_compare(actual, expected, lambda a, b: a <= b):
                    return False
                if op == "gt" and not self._number_compare(actual, expected, lambda a, b: a > b):
                    return False
                if op == "lt" and not self._number_compare(actual, expected, lambda a, b: a < b):
                    return False
                if op == "eq" and actual != expected:
                    return False
                if op == "neq" and actual == expected:
                    return False
                if op == "between":
                    lo, hi = expected
                    if actual is None:
                        return False
                    try:
                        actual_f = float(actual)
                        lo_f = float(lo)
                        hi_f = float(hi)
                    except (TypeError, ValueError):
                        return False
                    if not (lo_f <= actual_f <= hi_f):
                        return False
                if op == "in":
                    try:
                        if actual not in expected:
                            return False
                    except TypeError:
                        return False
                if op not in {"gte", "ge", "lte", "le", "gt", "lt", "eq", "neq", "between", "in"}:
                    raise TriggerEvaluationError(f"unsupported condition operator: {op}")
            return True
        return actual == spec

    def _number_compare(self, actual: Any, expected: Any, compare: Any) -> bool:
        if actual is None:
            return False
        try:
            return bool(compare(float(actual), float(expected)))
        except (TypeError, ValueError):
            return False

    def _controls(
        self,
        trigger: dict[str, Any],
        controls: dict[str, Any],
        context: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any] | None:
        if controls.get("require_connected_live_data") and context.get("entitlement_class") != "connected_account":
            return self._skip(trigger, "ENTITLEMENT_REQUIRED", context)
        freshness_limit = controls.get("data_freshness_seconds") or controls.get("max_freshness_seconds")
        if freshness_limit is not None and context["data_freshness_seconds"] > float(freshness_limit):
            return self._skip(trigger, "DATA_STALE", context)
        dedupe_key = self._dedupe_key(controls, context)
        cooldown_seconds = parse_duration_seconds(
            controls.get("cooldown_seconds") if controls.get("cooldown_seconds") is not None else controls.get("cooldown")
        )
        if cooldown_seconds:
            latest = self.platform.triggers.latest_firing(
                trigger["tenant_id"],
                trigger["trigger_id"],
                dedupe_key=dedupe_key,
            )
            if latest is not None:
                last_time = _parse_time(latest["event_time"], default=now)
                elapsed = (now - last_time).total_seconds()
                if elapsed < cooldown_seconds:
                    return self._skip(
                        trigger,
                        "COOLDOWN",
                        {**context, "dedupe_key": dedupe_key, "cooldown_seconds": cooldown_seconds},
                    )
        max_runs = controls.get("max_runs_per_day")
        if max_runs is not None:
            since = (now - timedelta(days=1)).isoformat()
            count = self.platform.triggers.count_firings_since(
                trigger["tenant_id"], trigger["trigger_id"], since
            )
            if count >= int(max_runs):
                return self._skip(trigger, "MAX_RUNS_PER_DAY", {**context, "count_24h": count})
        return None

    def _dedupe_key(self, controls: dict[str, Any], context: dict[str, Any]) -> str:
        template = controls.get("dedupe_key") or "${trigger_id}:${symbol}"

        def repl(match: re.Match[str]) -> str:
            return str(context.get(match.group(1), ""))

        return re.sub(r"\$\{([a-zA-Z0-9_.-]+)\}", repl, str(template))

    def _fire(
        self,
        trigger: dict[str, Any],
        policy: dict[str, Any],
        context: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        tenant_id = str(trigger["tenant_id"])
        trigger_id = str(trigger["trigger_id"])
        controls = policy.get("controls") or {}
        action = policy.get("action") or {}
        run_skill = action.get("run_skill") or "market.quote"
        mode = action.get("mode") or "analyze"
        dedupe_key = self._dedupe_key(controls, context)
        spec = {
            "trigger_id": trigger_id,
            "trigger_name": trigger["name"],
            "policy": policy,
            "event": {
                "symbol": context["symbol"],
                "price": context["price"],
                "source": context["source"],
                "entitlement_class": context["entitlement_class"],
                "event_time": context["event_time"],
                "freshness_seconds": context["data_freshness_seconds"],
            },
            "action": {"run_skill": run_skill, "mode": mode},
        }
        run_id = self.platform.runs.create(tenant_id, "trigger", None, spec)
        queued = self.platform.runs.transition(tenant_id, run_id, "queued", expect=0)
        emit(
            self.platform.trace,
            tenant_id=tenant_id,
            run_id=run_id,
            type="trigger_fired",
            actor={"kind": "system", "id": self.worker_id},
            data={
                "trigger_id": trigger_id,
                "name": trigger["name"],
                "dedupe_key": dedupe_key,
                "symbol": context["symbol"],
                "price": context["price"],
                "source": context["source"],
                "entitlement_class": context["entitlement_class"],
                "action": action,
            },
        )
        approval = None
        approval_required = bool(controls.get("approval_required")) or mode == "execute"
        if approval_required:
            approval = self.platform.approvals.create(
                tenant_id,
                run_id,
                kind="trigger_action",
                request={"trigger_id": trigger_id, "action": action, "event": spec["event"]},
                requested_by=self.worker_id,
            )
            emit(
                self.platform.trace,
                tenant_id=tenant_id,
                run_id=run_id,
                type="approval_requested",
                actor={"kind": "system", "id": self.worker_id},
                data={"approval_id": approval["approval_id"], "kind": "trigger_action"},
            )
        job = None
        if run_skill in {"market.quote", "market.snapshot", "market.get_quote"}:
            self._complete_quote_run(tenant_id, run_id, queued, run_skill, context)
        else:
            job = self.platform.jobs.create_for_run(
                tenant_id,
                run_id,
                kind="trigger",
                profile="interactive",
                payload={"trigger": trigger, "context": context, "action": action},
                idempotency_key=f"trigger:{trigger_id}:{dedupe_key}:{now.date().isoformat()}",
            )
            emit(
                self.platform.trace,
                tenant_id=tenant_id,
                run_id=run_id,
                type="job_queued",
                actor={"kind": "system", "id": self.worker_id},
                data={"job_id": job["job_id"], "profile": job["profile"], "kind": job["kind"]},
            )
        firing = self.platform.triggers.record_firing(
            tenant_id,
            trigger_id,
            run_id=run_id,
            dedupe_key=dedupe_key,
            event_time=context["event_time"] or now.isoformat(),
            payload={"context": self._safe_context(context), "action": action},
        )
        return {
            "fired": True,
            "trigger_id": trigger_id,
            "tenant_id": tenant_id,
            "run_id": run_id,
            "job_id": job["job_id"] if job else None,
            "approval_id": approval["approval_id"] if approval else None,
            "firing_id": firing["firing_id"],
            "state": self.platform.runs.get(tenant_id, run_id)["state"],
        }

    def _complete_quote_run(
        self,
        tenant_id: str,
        run_id: str,
        queued: dict[str, Any],
        run_skill: str,
        context: dict[str, Any],
    ) -> None:
        running = self.platform.runs.transition(tenant_id, run_id, "running", expect=queued["version"])
        span_id = f"trigger:{context['trigger_id']}:quote"
        emit(
            self.platform.trace,
            tenant_id=tenant_id,
            run_id=run_id,
            type="tool_call",
            span_id=span_id,
            actor={"kind": "system", "id": self.worker_id},
            data={"name": run_skill, "args": {"symbol": context["symbol"]}},
        )
        result = {
            "data": {
                "symbol": context["symbol"],
                "price": context["price"],
                "bid": context.get("bid"),
                "ask": context.get("ask"),
            },
            "provenance": {
                "source": context["source"],
                "source_account": context.get("source_account"),
                "entitlement_class": context["entitlement_class"],
                "as_of": context["event_time"],
                "freshness_ms": int(context["data_freshness_seconds"] * 1000),
            },
            "partial": False,
            "warnings": [],
        }
        emit(
            self.platform.trace,
            tenant_id=tenant_id,
            run_id=run_id,
            type="tool_result",
            span_id=span_id,
            actor={"kind": "system", "id": self.worker_id},
            data={"name": run_skill, **result},
        )
        self.platform.runs.set_result(tenant_id, run_id, result)
        self.platform.runs.transition(tenant_id, run_id, "succeeded", expect=running["version"])
        emit(
            self.platform.trace,
            tenant_id=tenant_id,
            run_id=run_id,
            type="run_transition",
            actor={"kind": "system", "id": self.worker_id},
            data={"from": "running", "to": "succeeded", "trigger_id": context["trigger_id"]},
        )

    def _skip(self, trigger: dict[str, Any], reason: str, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "fired": False,
            "trigger_id": trigger.get("trigger_id"),
            "tenant_id": trigger.get("tenant_id"),
            "reason": reason,
            "context": self._safe_context(context),
        }

    def _safe_context(self, context: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in context.items() if k not in {"raw", "policy", "quote"}}

    def run_forever(self, *, interval_s: float = 5.0, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        ttl_s = float(os.environ.get("DOOMBERG_TRIGGER_LEASE_TTL_S", str(max(60.0, interval_s * 3.0))))
        lease_name = os.environ.get("DOOMBERG_TRIGGER_LEASE_NAME", "trigger-engine")
        try:
            while not stop.is_set():
                if acquire_loop_lease(
                    self.platform,
                    lease_name=lease_name,
                    owner_id=self.worker_id,
                    ttl_seconds=ttl_s,
                    role="trigger-engine",
                ):
                    self.poll_once()
                stop.wait(interval_s)
        finally:
            with suppress(Exception):
                release_loop_lease(self.platform, lease_name=lease_name, owner_id=self.worker_id)


def main() -> None:
    from doomberg_platform import Platform

    db_path = os.environ.get("DOOMBERG_DB", ":memory:")
    interval_s = float(os.environ.get("DOOMBERG_TRIGGER_INTERVAL_S", "5"))
    platform = Platform(db_path)
    worker_id = process_owner("trigger-engine")
    print(
        "doomberg trigger engine up — "
        f"db={db_path}, interval={interval_s}s, "
        f"lease_ttl={os.environ.get('DOOMBERG_TRIGGER_LEASE_TTL_S') or max(60.0, interval_s * 3.0)}s, "
        f"owner={worker_id}, "
        f"ibkr_url={'set' if os.environ.get('DOOMBERG_IBKR_ENGINE_URL') else 'unset'}",
        flush=True,
    )
    TriggerEngine(platform, worker_id=worker_id).run_forever(interval_s=interval_s)


if __name__ == "__main__":
    main()
