"""Stateful trigger engine.

The trigger engine is deliberately separate from MCP: it polls active trigger policies,
observes live market data through a provider client, evaluates typed conditions, and creates
durable Doomberg runs when a policy fires. Trading is disabled in this deployment.
"""

from __future__ import annotations

import os
import re
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from doomberg_core.providers import (
    IbkrEngineClient,
    IbkrEngineConnectionError,
    IbkrEngineError,
    IbkrEngineHttpError,
    IbkrQuoteInvariantError,
    PUBLIC_DATA_SOURCE,
    PUBLIC_ENTITLEMENT_CLASS,
    normalize_quote,
)

from ._trace import emit
from .baselines import BaselineResolver
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
        # Upstream timestamps may be epoch seconds or milliseconds.
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
    """HTTP adapter for the private live market-data engine.

    Defaults assume the VPS exposes ``GET /quote?symbol=NVDA`` and returns a JSON object.
    Set the private quote-path env var to override, e.g. ``/v1/market/quote/{symbol}``.
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
        self.client = IbkrEngineClient(
            base_url=base_url,
            token=token,
            quote_path=quote_path,
            timeout_s=timeout_s,
        )
        self.base_url = self.client.base_url
        self.token = self.client.token
        self.quote_path = self.client.quote_path
        self.timeout_s = self.client.timeout_s

    def quote(self, symbol: str, *, tenant_id: str | None = None) -> dict[str, Any]:
        if not self.client.configured():
            raise TriggerEvaluationError("live market-data engine is not configured")
        try:
            return self.client.quote(symbol, tenant_id=tenant_id)
        except IbkrEngineHttpError as exc:
            raise TriggerEvaluationError(f"live market-data engine HTTP {exc.status}") from exc
        except IbkrQuoteInvariantError as exc:
            raise TriggerEvaluationError(str(exc)) from exc
        except IbkrEngineConnectionError as exc:
            raise TriggerEvaluationError(f"live market-data engine request failed: {exc}") from exc
        except IbkrEngineError as exc:
            raise TriggerEvaluationError(f"live market-data engine request failed: {exc}") from exc

    def _url(self, symbol: str) -> str:
        return self.client.url_for_path(self.quote_path, symbol=symbol)


class StaticQuoteClient:
    """Deterministic quote client for tests and local demos."""

    def __init__(self, quotes: dict[str, dict[str, Any]]) -> None:
        self.quotes = {k.upper(): dict(v) for k, v in quotes.items()}

    def quote(self, symbol: str, *, tenant_id: str | None = None) -> dict[str, Any]:
        try:
            raw = self.quotes[symbol.upper()]
        except KeyError as exc:
            raise TriggerEvaluationError(f"no quote for {symbol.upper()}") from exc
        try:
            return normalize_quote(raw, symbol=symbol, source=raw.get("source") or "static")
        except IbkrQuoteInvariantError as exc:
            raise TriggerEvaluationError(str(exc)) from exc


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
        self.baselines = BaselineResolver(platform)

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

    def dry_run(
        self,
        trigger: dict[str, Any],
        *,
        now: datetime | None = None,
        quote: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate a trigger policy without creating runs, jobs, approvals, or firings."""
        now = now or _now()
        tenant_id = str(trigger["tenant_id"])
        policy = trigger.get("policy") or {}
        when = policy.get("when") or {}
        event = when.get("event") or "price.threshold"
        if event not in {"price.threshold", "market.price", "market.quote"}:
            return self._dry_skip(trigger, "UNSUPPORTED_EVENT", {"event": event})

        symbol = self._symbol(policy)
        if quote is None:
            normalized_quote = self.quote_client.quote(symbol, tenant_id=tenant_id)
            quote_mode = "live"
        else:
            try:
                normalized_quote = normalize_quote(
                    quote,
                    symbol=symbol,
                    source=str(quote.get("source") or "dry-run"),
                )
            except IbkrQuoteInvariantError as exc:
                raise TriggerEvaluationError(str(exc)) from exc
            quote_mode = "provided"
        context = self._context(trigger, policy, normalized_quote, now)
        decision = self._condition(policy.get("condition") or {}, context)
        if not decision.ok:
            return self._dry_skip(trigger, "CONDITION_FALSE", decision.context, quote_mode=quote_mode)

        controls = policy.get("controls") or {}
        controls_check = self._controls(trigger, controls, context, now)
        if controls_check is not None:
            return self._dry_skip(
                trigger,
                str(controls_check.get("reason") or "CONTROLS_BLOCKED"),
                controls_check.get("context") or context,
                quote_mode=quote_mode,
            )

        action = policy.get("action") or {}
        mode = action.get("mode") or "analyze"
        run_skill = action.get("run_skill") or "market.quote"
        approval_required = bool(controls.get("approval_required")) or mode == "execute"
        dedupe_key = self._dedupe_key(controls, context)
        return {
            "dry_run": True,
            "would_fire": True,
            "reason": "WOULD_FIRE",
            "trigger_id": trigger.get("trigger_id"),
            "tenant_id": tenant_id,
            "dedupe_key": dedupe_key,
            "quote_mode": quote_mode,
            "would_create": {
                "run": True,
                "job": run_skill not in {"market.quote", "market.snapshot", "market.get_quote"},
                "approval": approval_required,
                "broker_order": False,
            },
            "action": {"run_skill": run_skill, "mode": mode},
            "context": self._safe_context(context),
        }

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
        context = {
            "tenant_id": trigger["tenant_id"],
            "trigger_id": trigger["trigger_id"],
            "trigger_name": trigger["name"],
            "symbol": quote["symbol"],
            "price": quote["price"],
            "last": quote["last"],
            "bid": quote.get("bid"),
            "ask": quote.get("ask"),
            "source": PUBLIC_DATA_SOURCE,
            "entitlement_class": quote.get("entitlement_class") or PUBLIC_ENTITLEMENT_CLASS,
            "event_time": quote.get("event_time"),
            "received_time": quote.get("received_time"),
            "freshness_seconds": freshness_seconds,
            "data_freshness_seconds": freshness_seconds,
            "quote": quote,
            "policy": policy,
            "now": now.isoformat(),
        }
        try:
            baseline = self.baselines.resolve(
                tenant_id=str(trigger["tenant_id"]),
                trigger_id=str(trigger["trigger_id"]),
                policy=policy,
                quote=quote,
                now=now,
            )
        except ValueError as exc:
            raise TriggerEvaluationError(str(exc)) from exc
        if baseline is not None:
            baseline_price = float(baseline["price"])
            price = float(quote["price"])
            change_abs = price - baseline_price
            change_pct = (change_abs / baseline_price) * 100.0
            context.update(
                {
                    "baseline_type": baseline["type"],
                    "baseline_price": baseline_price,
                    "baseline_time": baseline["time"],
                    "change_abs": change_abs,
                    "change_pct": change_pct,
                    "trading_day": baseline["trading_day"],
                }
            )
        else:
            event_time = _parse_time(quote.get("event_time"), default=now)
            context["trading_day"] = event_time.date().isoformat()
        return context

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
        if controls.get("require_connected_live_data") and context.get("entitlement_class") != PUBLIC_ENTITLEMENT_CLASS:
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
        if mode == "notify":
            firing = self.platform.triggers.record_firing(
                tenant_id,
                trigger_id,
                run_id="",
                dedupe_key=dedupe_key,
                event_time=context["event_time"] or now.isoformat(),
                payload={"context": self._safe_context(context), "action": action},
            )
            notification = self._enqueue_notification(
                trigger,
                policy,
                context,
                action,
                firing=firing,
                run_id=None,
                approval=None,
                dedupe_key=dedupe_key,
            )
            return {
                "fired": True,
                "trigger_id": trigger_id,
                "tenant_id": tenant_id,
                "run_id": None,
                "job_id": None,
                "approval_id": None,
                "firing_id": firing["firing_id"],
                "notification_id": notification.get("notification_id") if notification else None,
                "state": "notified",
            }
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
                "baseline_price": context.get("baseline_price"),
                "baseline_type": context.get("baseline_type"),
                "change_pct": context.get("change_pct"),
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
        notification = self._enqueue_notification(
            trigger,
            policy,
            context,
            action,
            firing=firing,
            run_id=run_id,
            approval=approval,
            dedupe_key=dedupe_key,
        )
        if notification is not None:
            emit(
                self.platform.trace,
                tenant_id=tenant_id,
                run_id=run_id,
                type="notification_queued",
                actor={"kind": "system", "id": self.worker_id},
                data={
                    "notification_id": notification["notification_id"],
                    "channels": (policy.get("notify") or {}).get("channels", []),
                },
            )
        return {
            "fired": True,
            "trigger_id": trigger_id,
            "tenant_id": tenant_id,
            "run_id": run_id,
            "job_id": job["job_id"] if job else None,
            "approval_id": approval["approval_id"] if approval else None,
            "firing_id": firing["firing_id"],
            "notification_id": notification.get("notification_id") if notification else None,
            "state": self.platform.runs.get(tenant_id, run_id)["state"],
        }

    def _allowed_agent_actions(self, policy: dict[str, Any]) -> dict[str, list[str]]:
        mode = ((policy.get("action") or {}).get("mode") or "analyze").strip().lower()
        allowed = ["market_quote", "market_news", "vol_realized", "run_skill", "get_run", "alerts_ack"]
        if mode == "notify":
            allowed = ["get_run", "alerts_ack"]
        if mode == "propose":
            allowed.append("propose_strategy")
        return {
            "allowed": allowed,
            "blocked": ["broker_order", "approval_decide", "live_execution"],
        }

    def _enqueue_notification(
        self,
        trigger: dict[str, Any],
        policy: dict[str, Any],
        context: dict[str, Any],
        action: dict[str, Any],
        *,
        firing: dict[str, Any],
        run_id: str | None,
        approval: dict[str, Any] | None,
        dedupe_key: str,
    ) -> dict[str, Any] | None:
        notifications = getattr(self.platform, "notifications", None)
        if notifications is None:
            return None
        tenant_id = str(trigger["tenant_id"])
        notify = policy.get("notify") or {}
        actions = self._allowed_agent_actions(policy)
        payload = {
            "type": "trigger.fired",
            "trigger_id": str(trigger["trigger_id"]),
            "trigger_name": trigger["name"],
            "firing_id": firing["firing_id"],
            "run_id": run_id,
            "symbol": context["symbol"],
            "price": context["price"],
            "baseline_price": context.get("baseline_price"),
            "baseline_type": context.get("baseline_type"),
            "change_pct": context.get("change_pct"),
            "event_time": context["event_time"],
            "freshness_seconds": context["data_freshness_seconds"],
            "action": action,
            "approval_id": approval["approval_id"] if approval else None,
            "allowed_agent_actions": actions["allowed"],
            "blocked_agent_actions": actions["blocked"],
            "channels": notify.get("channels") or ["doomberg_ui"],
        }
        return notifications.enqueue(
            tenant_id,
            event_type="trigger.fired",
            subject_type="trigger_firing",
            subject_id=firing["firing_id"],
            priority=notify.get("priority") or "normal",
            dedupe_key=f"trigger:{trigger['trigger_id']}:{dedupe_key}:{context.get('trading_day')}",
            payload=payload,
        )

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
                "source": PUBLIC_DATA_SOURCE,
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

    def _dry_skip(
        self,
        trigger: dict[str, Any],
        reason: str,
        context: dict[str, Any],
        *,
        quote_mode: str | None = None,
    ) -> dict[str, Any]:
        return {
            "dry_run": True,
            "would_fire": False,
            "reason": reason,
            "trigger_id": trigger.get("trigger_id"),
            "tenant_id": trigger.get("tenant_id"),
            "quote_mode": quote_mode,
            "would_create": {
                "run": False,
                "job": False,
                "approval": False,
                "broker_order": False,
            },
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
        f"live_data_url={'set' if os.environ.get('DOOMBERG_IBKR_ENGINE_URL') else 'unset'}",
        flush=True,
    )
    TriggerEngine(platform, worker_id=worker_id).run_forever(interval_s=interval_s)


if __name__ == "__main__":
    main()
