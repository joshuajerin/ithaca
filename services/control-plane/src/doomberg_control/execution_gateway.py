"""Deterministic execution gateway.

Agents and triggers may create order intents. Only this module can turn an intent into
orders/fills, and every path runs through the same policy, idempotency, and audit events.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from doomberg_core.providers import (
    IbkrEngineClient,
    IbkrEngineConnectionError,
    IbkrEngineError,
    IbkrEngineHttpError,
)
from doomberg_platform import ExecutionControlConflict

from .actions import ActionError
from .deps import HUMAN_ACTOR_KINDS, Ctx

BROKER_PAPER = "paper"
BROKER_IBKR = "ibkr-engine"
TERMINAL_ORDER_STATES = {"filled", "cancelled", "rejected"}

__all__ = [
    "ExecutionGateway",
    "ExecutionPolicy",
    "PaperBrokerAdapter",
    "IBKREngineBrokerAdapter",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _SubmissionOutcomeUnknown(RuntimeError):
    """The broker may have accepted the request; only read-back may resolve it."""


def _actor(ctx: Ctx) -> dict[str, str]:
    kind = ctx.actor_kind if ctx.actor_kind in {"agent", "user", "system"} else "user"
    return {"kind": kind, "id": ctx.actor_id}


def _emit(platform: Any, *, ctx: Ctx, run_id: str, event_type: str, data: dict[str, Any]) -> None:
    platform.trace.append(
        {
            "run_id": run_id,
            "ts": _now_iso(),
            "type": event_type,
            "tenant_id": ctx.tenant_id,
            "actor": _actor(ctx),
            "data": data,
        }
    )


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _canonical_state(raw: str | None) -> str:
    value = (raw or "submitted").strip().lower().replace(" ", "_")
    aliases = {
        "presubmitted": "submitted",
        "submitted": "submitted",
        "open": "submitted",
        "pendingsubmit": "submitted",
        "pending_submit": "submitted",
        "apipending": "submitted",
        "pendingcancel": "submitted",
        "pending_cancel": "submitted",
        "partiallyfilled": "partially_filled",
        "partially_filled": "partially_filled",
        "partial": "partially_filled",
        "filled": "filled",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "expired": "cancelled",
        "inactive": "rejected",
        "rejected": "rejected",
    }
    # Unknown broker states remain non-terminal so the reconciler keeps polling
    # instead of silently treating an unfamiliar value as final.
    return aliases.get(value, "submitted")


def _first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
    return None


def _normalize_broker_order(raw: dict[str, Any]) -> dict[str, Any]:
    broker_order_id = _first_value(raw, "broker_order_id", "order_id", "orderId", "id")
    client_order_id = _first_value(
        raw,
        "client_order_id",
        "clientOrderId",
        "cOID",
        "order_ref",
        "orderRef",
    )
    fills = raw.get("fills") if isinstance(raw.get("fills"), list) else []
    return {
        "broker_order_id": str(broker_order_id) if broker_order_id is not None else None,
        "client_order_id": str(client_order_id) if client_order_id is not None else None,
        "state": _canonical_state(str(_first_value(raw, "state", "status", "order_status") or "submitted")),
        "filled_quantity": _float_or_none(
            _first_value(raw, "filled_quantity", "filledQuantity", "filled", "cum_qty")
        ),
        "avg_fill_price": _float_or_none(
            _first_value(raw, "avg_fill_price", "avgPrice", "avg_price", "price")
        ),
        "event_time": _first_value(raw, "event_time", "lastExecutionTime", "updated_at"),
        "fills": fills,
        "raw": raw,
    }


@dataclass(frozen=True)
class ExecutionPolicy:
    max_notional_usd: float = 10_000.0
    max_quantity: float = 10_000.0
    max_freshness_ms: int = 10_000
    live_enabled: bool = False
    require_connected_provider_for_live: bool = True

    @classmethod
    def from_env(cls) -> "ExecutionPolicy":
        return cls(
            max_notional_usd=float(os.environ.get("DOOMBERG_EXECUTION_MAX_NOTIONAL_USD", "10000")),
            max_quantity=float(os.environ.get("DOOMBERG_EXECUTION_MAX_QUANTITY", "10000")),
            max_freshness_ms=int(os.environ.get("DOOMBERG_EXECUTION_MAX_FRESHNESS_MS", "10000")),
            live_enabled=_env_flag("DOOMBERG_ENABLE_LIVE_EXECUTION"),
            require_connected_provider_for_live=not _env_flag(
                "DOOMBERG_ALLOW_LIVE_WITHOUT_PROVIDER_CONNECTION"
            ),
        )


class PaperBrokerAdapter:
    broker = BROKER_PAPER

    def submit(
        self,
        *,
        tenant_id: str,
        intent_id: str,
        client_order_id: str,
        order: dict[str, Any],
    ) -> dict[str, Any]:
        price = _float_or_none(order.get("limit_price") or order.get("reference_price") or order.get("price"))
        qty = float(order["quantity"])
        if price is None or price <= 0:
            return {
                "broker_order_id": client_order_id,
                "state": "submitted",
                "fills": [],
                "raw": {"paper": True, "reason": "no fill price supplied"},
            }
        fill = {
            "broker_fill_id": f"{client_order_id}-fill-1",
            "event_time": _now_iso(),
            "payload": {
                "symbol": order["symbol"],
                "side": order["side"],
                "quantity": qty,
                "price": price,
                "notional_usd": round(qty * price, 2),
                "paper": True,
            },
        }
        return {
            "broker_order_id": client_order_id,
            "state": "filled",
            "fills": [fill],
            "raw": {"paper": True},
        }

    def snapshot(self, *, tenant_id: str, account_ref: str | None = None) -> list[dict[str, Any]]:
        del tenant_id, account_ref
        return []


class IBKREngineBrokerAdapter:
    broker = BROKER_IBKR

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        order_path: str | None = None,
    ) -> None:
        self.client = IbkrEngineClient(base_url=base_url, token=token, order_path=order_path, timeout_s=15)
        self.base_url = self.client.base_url
        self.token = self.client.token
        self.order_path = self.client.order_path

    def configured(self) -> bool:
        return self.client.configured()

    def submit(
        self,
        *,
        tenant_id: str,
        intent_id: str,
        client_order_id: str,
        order: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.client.configured():
            raise ActionError(503, "IBKR engine is not configured")
        try:
            raw = self.client.submit_order(
                tenant_id=tenant_id,
                intent_id=intent_id,
                client_order_id=client_order_id,
                order=order,
            )
        except IbkrEngineHttpError as exc:
            if exc.status >= 500 or exc.status == 409:
                raise _SubmissionOutcomeUnknown(str(exc)) from exc
            if exc.status not in {400, 403, 422}:
                raise ActionError(503, str(exc)) from exc
            return {
                "broker_order_id": None,
                "state": "rejected",
                "fills": [],
                "raw": {"status": exc.status, "detail": exc.detail},
            }
        except IbkrEngineConnectionError as exc:
            raise _SubmissionOutcomeUnknown(str(exc)) from exc
        except IbkrEngineError as exc:
            raise _SubmissionOutcomeUnknown(f"IBKR engine request failed: {exc}") from exc
        state = _canonical_state(str(raw.get("state") or raw.get("status") or "submitted"))
        broker_order_id = raw.get("broker_order_id") or raw.get("order_id") or raw.get("id")
        fills = raw.get("fills") if isinstance(raw.get("fills"), list) else []
        if not fills and state == "filled":
            price = _float_or_none(raw.get("avg_fill_price") or raw.get("price"))
            qty = _float_or_none(raw.get("filled_quantity") or raw.get("quantity"))
            if price and qty:
                fills = [
                    {
                        "broker_fill_id": raw.get("fill_id"),
                        "event_time": raw.get("event_time") or _now_iso(),
                        "payload": {"price": price, "quantity": qty, "raw": raw},
                    }
                ]
        return {
            "broker_order_id": str(broker_order_id) if broker_order_id is not None else None,
            "state": state,
            "fills": fills,
            "raw": raw,
        }

    def snapshot(
        self, *, tenant_id: str, account_ref: str | None = None
    ) -> list[dict[str, Any]]:
        if not self.client.configured():
            raise ActionError(503, "IBKR engine is not configured")
        try:
            response = self.client.orders(account=account_ref, tenant_id=tenant_id)
        except IbkrEngineConnectionError as exc:
            raise ActionError(503, str(exc)) from exc
        except IbkrEngineError as exc:
            raise ActionError(503, f"IBKR engine request failed: {exc}") from exc
        return [
            _normalize_broker_order(item)
            for item in response.get("orders") or []
            if isinstance(item, dict)
        ]


class ExecutionGateway:
    def __init__(
        self,
        platform: Any,
        *,
        policy: ExecutionPolicy | None = None,
        adapters: dict[str, Any] | None = None,
    ) -> None:
        self.platform = platform
        self.policy = policy or ExecutionPolicy.from_env()
        self.adapters = adapters or {
            BROKER_PAPER: PaperBrokerAdapter(),
            BROKER_IBKR: IBKREngineBrokerAdapter(),
        }

    def get_kill_switch(self, ctx: Ctx) -> dict[str, Any]:
        return self._execution_control(ctx.tenant_id)

    def set_kill_switch(
        self,
        ctx: Ctx,
        *,
        enabled: bool,
        expect_version: int,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if ctx.actor_kind not in HUMAN_ACTOR_KINDS:
            raise ActionError(403, "execution kill switch requires a human actor")
        if not ctx.has_scope("deploy:paper"):
            raise ActionError(403, "execution kill switch requires the deploy:paper scope")
        try:
            self.platform.execution_controls.set_tenant(
                ctx.tenant_id,
                enabled=bool(enabled),
                reason=reason,
                actor_id=ctx.actor_id,
                expect_version=expect_version,
            )
        except ExecutionControlConflict as exc:
            raise ActionError(409, str(exc)) from exc
        return self._execution_control(ctx.tenant_id)

    def create_intent(
        self,
        ctx: Ctx,
        *,
        run_id: str,
        payload: dict[str, Any],
        strategy_id: str | None = None,
        account_ref: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not ctx.has_scope("runs:write"):
            raise ActionError(403, "create_order_intent requires the runs:write scope")
        run = self.platform.runs.get(ctx.tenant_id, run_id)
        if run is None:
            raise ActionError(404, "run not found")
        intent = self.platform.execution.create_order_intent(
            ctx.tenant_id,
            run_id,
            payload=payload,
            strategy_id=strategy_id,
            account_ref=account_ref,
            idempotency_key=idempotency_key,
        )
        _emit(
            self.platform,
            ctx=ctx,
            run_id=run_id,
            event_type="order_intent",
            data={"intent_id": intent["intent_id"], "state": intent["state"], "payload": payload},
        )
        return self.platform.execution.get_record(ctx.tenant_id, intent["intent_id"])

    def preview(self, ctx: Ctx, intent_id: str) -> dict[str, Any]:
        intent = self._intent(ctx, intent_id)
        decision = self.evaluate(ctx, intent)
        state = "policy_denied" if decision["decision"] == "denied" else "approved"
        if state == "approved" and ctx.actor_kind not in HUMAN_ACTOR_KINDS:
            state = "approval_required"
            self._ensure_approval(ctx, intent, decision)
        self.platform.execution.set_intent_state(
            ctx.tenant_id,
            intent_id,
            state=state,
            risk_decision=decision,
        )
        _emit(
            self.platform,
            ctx=ctx,
            run_id=intent["run_id"],
            event_type="order_intent",
            data={"intent_id": intent_id, "state": state, "risk_decision": decision},
        )
        record = self.platform.execution.get_record(ctx.tenant_id, intent_id)
        if record is None:
            raise ActionError(404, "order intent not found")
        return record

    def submit(self, ctx: Ctx, intent_id: str) -> dict[str, Any]:
        intent = self._intent(ctx, intent_id)
        if ctx.actor_kind not in HUMAN_ACTOR_KINDS:
            self.preview(ctx, intent_id)
            raise ActionError(403, "execution submit requires a human actor")
        if not ctx.has_scope("deploy:paper"):
            raise ActionError(403, "execution submit requires the deploy:paper scope")

        existing = self.platform.execution.get_record(ctx.tenant_id, intent_id)
        if existing and existing["orders"] and not any(
            order["state"] == "pending_submission" for order in existing["orders"]
        ):
            return existing

        decision = self.evaluate(ctx, intent)
        if decision["decision"] == "denied":
            self.platform.execution.set_intent_state(
                ctx.tenant_id,
                intent_id,
                state="policy_denied",
                risk_decision=decision,
            )
            _emit(
                self.platform,
                ctx=ctx,
                run_id=intent["run_id"],
                event_type="denial",
                data={"action": "execution.submit", "intent_id": intent_id, "risk_decision": decision},
            )
            raise ActionError(409, {"reason": "policy denied", "risk_decision": decision})

        broker = decision["broker"]
        adapter = self.adapters.get(broker)
        if adapter is None:
            raise ActionError(422, f"unsupported broker: {broker}")

        for idx, normalized in enumerate(decision["normalized_orders"], start=1):
            client_order_id = self._client_order_id(intent_id, idx)
            order = self.platform.execution.create_order(
                ctx.tenant_id,
                intent_id,
                broker=broker,
                client_order_id=client_order_id,
                state="pending_submission",
                payload={
                    **normalized,
                    "risk_decision_id": decision["decision_id"],
                },
            )
            if order["state"] != "pending_submission":
                continue
            if not self.platform.execution.claim_order_submission(
                ctx.tenant_id, order["order_id"]
            ):
                continue
            response: dict[str, Any] | None = None
            try:
                with self._submission_guard(ctx.tenant_id):
                    execution_control = self._execution_control(ctx.tenant_id)
                    if not execution_control["enabled"]:
                        response = adapter.submit(
                            tenant_id=ctx.tenant_id,
                            intent_id=intent_id,
                            client_order_id=client_order_id,
                            order=normalized,
                        )
            except _SubmissionOutcomeUnknown as exc:
                self.platform.execution.set_order_state(
                    ctx.tenant_id,
                    order["order_id"],
                    state="submitting",
                    payload={
                        "submission_error": f"{type(exc).__name__}: {exc}"[:500],
                        "submission_outcome": "unknown",
                    },
                )
                raise ActionError(
                    503,
                    "broker submission outcome is unknown; reconciliation is required",
                ) from exc
            except Exception as exc:
                self.platform.execution.release_order_submission(
                    ctx.tenant_id,
                    order["order_id"],
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
            if execution_control["enabled"]:
                denied = {
                    **decision,
                    "decision": "denied",
                    "reasons": list(
                        dict.fromkeys(
                            [*decision["reasons"], "EXECUTION_KILL_SWITCH_ACTIVE"]
                        )
                    ),
                    "execution_control": execution_control,
                    "evaluated_at": _now_iso(),
                }
                self.platform.execution.set_order_state(
                    ctx.tenant_id,
                    order["order_id"],
                    state="cancelled",
                    payload={"cancel_reason": "execution kill switch activated before send"},
                )
                stopped_record = self.platform.execution.get_record(ctx.tenant_id, intent_id)
                stopped_state = "policy_denied"
                if stopped_record and any(
                    existing_order["order_id"] != order["order_id"]
                    and existing_order["state"] not in {"pending_submission", "cancelled"}
                    for existing_order in stopped_record["orders"]
                ):
                    stopped_state = self._intent_state_after_submit(
                        stopped_record["orders"], stopped_record["fills"]
                    )
                self.platform.execution.set_intent_state(
                    ctx.tenant_id,
                    intent_id,
                    state=stopped_state,
                    risk_decision=denied,
                )
                _emit(
                    self.platform,
                    ctx=ctx,
                    run_id=intent["run_id"],
                    event_type="denial",
                    data={
                        "action": "execution.submit",
                        "intent_id": intent_id,
                        "risk_decision": denied,
                    },
                )
                raise ActionError(409, {"reason": "policy denied", "risk_decision": denied})
            if response is None:
                raise RuntimeError("broker submission produced no response")
            order = self.platform.execution.set_order_state(
                ctx.tenant_id,
                order["order_id"],
                broker_order_id=response.get("broker_order_id"),
                state=_canonical_state(response.get("state")),
                payload={"broker_response": response.get("raw"), "submission_error": None},
            )
            _emit(
                self.platform,
                ctx=ctx,
                run_id=intent["run_id"],
                event_type="order_submitted",
                data={
                    "intent_id": intent_id,
                    "order_id": order["order_id"],
                    "broker": broker,
                    "client_order_id": client_order_id,
                    "state": order["state"],
                },
            )
            self._record_fills(
                ctx,
                intent=intent,
                order=order,
                fills=response.get("fills") or [],
            )

        record = self.platform.execution.get_record(ctx.tenant_id, intent_id)
        if record is None:
            raise ActionError(404, "order intent not found")
        intent_state = self._intent_state_after_submit(record["orders"], record["fills"])
        self.platform.execution.set_intent_state(
            ctx.tenant_id,
            intent_id,
            state=intent_state,
            risk_decision=decision,
        )
        record = self.platform.execution.get_record(ctx.tenant_id, intent_id)
        if record is None:
            raise ActionError(404, "order intent not found")
        return record

    def reconcile_intent(self, ctx: Ctx, intent_id: str) -> dict[str, Any]:
        """Refresh durable order/fill state from the broker's read-only snapshot."""

        intent = self._intent(ctx, intent_id)
        record = self.platform.execution.get_record(ctx.tenant_id, intent_id)
        if record is None:
            raise ActionError(404, "order intent not found")
        open_orders = [
            order
            for order in record["orders"]
            if order["state"] not in TERMINAL_ORDER_STATES
        ]
        snapshots: dict[str, list[dict[str, Any]]] = {}
        reconciled: list[str] = []
        missing: list[str] = []
        errors: list[dict[str, str]] = []
        for order in open_orders:
            broker = order["broker"]
            adapter = self.adapters.get(broker)
            if adapter is None or not hasattr(adapter, "snapshot"):
                continue
            if broker not in snapshots:
                try:
                    snapshots[broker] = adapter.snapshot(
                        tenant_id=ctx.tenant_id,
                        account_ref=intent.get("account_ref"),
                    )
                except Exception as exc:  # broker outage must not corrupt durable state
                    errors.append(
                        {"broker": broker, "error": type(exc).__name__, "detail": str(exc)[:300]}
                    )
                    snapshots[broker] = []
            snapshot = self._match_snapshot(order, snapshots[broker])
            if snapshot is None:
                missing.append(order["order_id"])
                continue
            previous_state = order["state"]
            updated = self.platform.execution.set_order_state(
                ctx.tenant_id,
                order["order_id"],
                state=snapshot["state"],
                broker_order_id=snapshot.get("broker_order_id"),
                payload={
                    "broker_snapshot": snapshot.get("raw"),
                    "last_reconciled_at": _now_iso(),
                },
            )
            broker_fills = list(snapshot.get("fills") or [])
            if not broker_fills:
                cumulative = _float_or_none(snapshot.get("filled_quantity"))
                existing_fills = self.platform.execution.list_fills(
                    ctx.tenant_id, order_id=order["order_id"]
                )
                existing_quantity = sum(
                    _float_or_none(fill.get("payload", {}).get("quantity")) or 0.0
                    for fill in existing_fills
                )
                if cumulative is not None and cumulative > existing_quantity + 1e-9:
                    delta = cumulative - existing_quantity
                    average_price = snapshot.get("avg_fill_price")
                    known_notional = sum(
                        (_float_or_none(fill.get("payload", {}).get("quantity")) or 0.0)
                        * (_float_or_none(fill.get("payload", {}).get("price")) or 0.0)
                        for fill in existing_fills
                    )
                    incremental_price = average_price
                    if average_price is not None and known_notional > 0:
                        incremental_price = max(
                            0.0,
                            ((cumulative * average_price) - known_notional) / delta,
                        )
                    broker_identity = (
                        snapshot.get("broker_order_id")
                        or order.get("broker_order_id")
                        or order["client_order_id"]
                    )
                    broker_fills = [
                        {
                            "broker_fill_id": (
                                f"{broker}:{broker_identity}:cumulative:{cumulative:.8f}"
                            ),
                            "event_time": snapshot.get("event_time") or _now_iso(),
                            "payload": {
                                "symbol": order["payload"].get("symbol"),
                                "side": order["payload"].get("side"),
                                "quantity": delta,
                                "cumulative_quantity": cumulative,
                                "price": incremental_price,
                                "reconciled": True,
                            },
                        }
                    ]
            self._record_fills(
                ctx,
                intent=intent,
                order=updated,
                fills=broker_fills,
            )
            reconciled.append(order["order_id"])
            if previous_state != updated["state"]:
                _emit(
                    self.platform,
                    ctx=ctx,
                    run_id=intent["run_id"],
                    event_type="provider_status",
                    data={
                        "provider": broker,
                        "order_id": order["order_id"],
                        "from": previous_state,
                        "to": updated["state"],
                    },
                )

        current = self.platform.execution.get_record(ctx.tenant_id, intent_id)
        if current is None:
            raise ActionError(404, "order intent not found")
        intent_state = self._intent_state_after_submit(current["orders"], current["fills"])
        self.platform.execution.set_intent_state(
            ctx.tenant_id,
            intent_id,
            state=intent_state,
            risk_decision=intent.get("risk_decision"),
        )
        result = self.platform.execution.get_record(ctx.tenant_id, intent_id)
        if result is None:
            raise ActionError(404, "order intent not found")
        return {
            **result,
            "reconciliation": {
                "reconciled_order_ids": reconciled,
                "missing_order_ids": missing,
                "errors": errors,
            },
        }

    def reconcile_open_orders(self, *, limit: int = 500) -> dict[str, Any]:
        """Reconcile each open IBKR intent once; safe for repeated worker polls."""

        open_orders = self.platform.execution.list_open_orders(
            broker=BROKER_IBKR,
            limit=limit,
        )
        identities = list(
            dict.fromkeys((order["tenant_id"], order["intent_id"]) for order in open_orders)
        )
        reconciled: list[str] = []
        failed: list[dict[str, str]] = []
        for tenant_id, intent_id in identities:
            ctx = Ctx(tenant_id, "system", "execution-reconciler")
            try:
                result = self.reconcile_intent(ctx, intent_id)
                reconciliation = result.get("reconciliation", {})
                errors = reconciliation.get("errors") or []
                missing = reconciliation.get("missing_order_ids") or []
                if errors or missing:
                    failed.append(
                        {
                            "tenant_id": tenant_id,
                            "intent_id": intent_id,
                            "error": "BrokerSnapshotError" if errors else "BrokerOrderMissing",
                            "detail": str(errors or missing)[:300],
                        }
                    )
                else:
                    reconciled.append(intent_id)
            except Exception as exc:  # one account/broker failure must not stop the loop
                failed.append(
                    {
                        "tenant_id": tenant_id,
                        "intent_id": intent_id,
                        "error": type(exc).__name__,
                        "detail": str(exc)[:300],
                    }
                )
        return {
            "open_orders": len(open_orders),
            "reconciled_intents": reconciled,
            "failed": failed,
        }

    def _record_fills(
        self,
        ctx: Ctx,
        *,
        intent: dict[str, Any],
        order: dict[str, Any],
        fills: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        created: list[dict[str, Any]] = []
        for index, fill_payload in enumerate(fills, start=1):
            payload = fill_payload.get("payload") or fill_payload
            broker_fill_id = _first_value(
                fill_payload,
                "broker_fill_id",
                "fill_id",
                "execId",
                "execution_id",
                "trade_id",
            )
            if broker_fill_id is None:
                broker_fill_id = (
                    f"{order['broker']}:{order['client_order_id']}:submission:{index}"
                )
            broker_fill_id = str(broker_fill_id)
            broker_prefix = f"{order['broker']}:"
            if not broker_fill_id.startswith(broker_prefix):
                broker_fill_id = broker_prefix + broker_fill_id
            if self.platform.execution.get_fill_by_broker_fill_id(
                ctx.tenant_id, broker_fill_id
            ) is not None:
                continue
            fill = self.platform.execution.create_fill(
                ctx.tenant_id,
                order["order_id"],
                broker_fill_id=broker_fill_id,
                payload=payload,
                event_time=fill_payload.get("event_time") or _now_iso(),
            )
            created.append(fill)
            _emit(
                self.platform,
                ctx=ctx,
                run_id=intent["run_id"],
                event_type="fill_reconciled",
                data={
                    "intent_id": intent["intent_id"],
                    "order_id": order["order_id"],
                    "fill_id": fill["fill_id"],
                    "payload": fill["payload"],
                },
            )
        return created

    @staticmethod
    def _match_snapshot(
        order: dict[str, Any], snapshots: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        broker_order_id = order.get("broker_order_id")
        client_order_id = order.get("client_order_id")
        for snapshot in snapshots:
            if broker_order_id and snapshot.get("broker_order_id") == broker_order_id:
                return snapshot
            if client_order_id and snapshot.get("client_order_id") == client_order_id:
                return snapshot
        return None

    def evaluate(self, ctx: Ctx, intent: dict[str, Any]) -> dict[str, Any]:
        payload = intent["payload"]
        broker = str(payload.get("broker") or payload.get("provider") or BROKER_PAPER).strip().lower()
        live = bool(payload.get("live")) or broker != BROKER_PAPER
        normalized, errors, warnings = self._normalize_orders(payload)

        total_notional = sum(float(o.get("notional_usd") or 0.0) for o in normalized)
        max_freshness_ms = int(payload.get("max_freshness_ms") or self.policy.max_freshness_ms)
        freshness_ms = payload.get("freshness_ms")
        if freshness_ms is not None and float(freshness_ms) > max_freshness_ms:
            errors.append("DATA_STALE")

        if live and not self.policy.live_enabled:
            errors.append("LIVE_EXECUTION_DISABLED")
        execution_control = self._execution_control(ctx.tenant_id)
        if execution_control["enabled"]:
            errors.append("EXECUTION_KILL_SWITCH_ACTIVE")
        if live and "UNKNOWN_NOTIONAL" in warnings:
            errors.append("UNKNOWN_NOTIONAL")
        if broker == BROKER_IBKR and not self._ibkr_configured():
            errors.append("BROKER_CONNECTION_REQUIRED")
        if live and self.policy.require_connected_provider_for_live:
            if not self._has_connected_execution_provider(ctx.tenant_id, broker):
                errors.append("BROKER_CONNECTION_REQUIRED")

        if total_notional > self.policy.max_notional_usd:
            errors.append("MAX_NOTIONAL_EXCEEDED")
        for order in normalized:
            if float(order["quantity"]) > self.policy.max_quantity:
                errors.append("MAX_QUANTITY_EXCEEDED")

        decision = "denied" if errors else "approved"
        return {
            "decision_id": f"risk_{intent['intent_id']}",
            "decision": decision,
            "reasons": list(dict.fromkeys(errors)),
            "warnings": warnings,
            "broker": broker,
            "live": live,
            "total_notional_usd": round(total_notional, 2),
            "normalized_orders": normalized,
            "policy": {
                "max_notional_usd": self.policy.max_notional_usd,
                "max_quantity": self.policy.max_quantity,
                "max_freshness_ms": self.policy.max_freshness_ms,
                "live_enabled": self.policy.live_enabled,
                "require_connected_provider_for_live": self.policy.require_connected_provider_for_live,
            },
            "execution_control": execution_control,
            "evaluated_at": _now_iso(),
        }

    def _intent(self, ctx: Ctx, intent_id: str) -> dict[str, Any]:
        intent = self.platform.execution.get_intent(ctx.tenant_id, intent_id)
        if intent is None:
            raise ActionError(404, "order intent not found")
        return intent

    def _normalize_orders(self, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        raw_orders = payload.get("orders")
        if not isinstance(raw_orders, list):
            raw_orders = [payload]
        normalized: list[dict[str, Any]] = []
        errors: list[str] = []
        warnings: list[str] = []
        for raw in raw_orders:
            if not isinstance(raw, dict):
                errors.append("INVALID_ORDER")
                continue
            symbol = str(raw.get("symbol") or raw.get("contract") or "").strip().upper()
            side = str(raw.get("side") or raw.get("action") or "").strip().lower()
            quantity = _float_or_none(raw.get("quantity") or raw.get("qty") or raw.get("shares"))
            notional = _float_or_none(raw.get("notional_usd") or raw.get("notional"))
            limit_price = _float_or_none(raw.get("limit_price") or raw.get("limitPrice"))
            reference_price = _float_or_none(raw.get("reference_price") or raw.get("price"))
            order_type = str(raw.get("order_type") or raw.get("orderType") or "market").strip().lower()
            tif = str(raw.get("time_in_force") or raw.get("tif") or "day").strip().lower()
            if not symbol:
                errors.append("INVALID_SYMBOL")
            if side not in {"buy", "sell"}:
                errors.append("INVALID_SIDE")
            if quantity is None:
                if notional and (limit_price or reference_price):
                    quantity = notional / float(limit_price or reference_price)
                else:
                    errors.append("INVALID_QUANTITY")
                    quantity = 0.0
            if quantity <= 0:
                errors.append("INVALID_QUANTITY")
            price_for_notional = limit_price or reference_price
            if notional is None and price_for_notional is not None:
                notional = quantity * price_for_notional
            if notional is None:
                warnings.append("UNKNOWN_NOTIONAL")
                notional = 0.0
            if order_type not in {"market", "limit"}:
                errors.append("INVALID_ORDER_TYPE")
            if order_type == "limit" and not limit_price:
                errors.append("LIMIT_PRICE_REQUIRED")
            normalized.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "quantity": round(float(quantity), 8),
                    "order_type": order_type,
                    "time_in_force": tif,
                    "limit_price": limit_price,
                    "reference_price": reference_price,
                    "notional_usd": round(float(notional), 2),
                    "asset_class": str(raw.get("asset_class") or raw.get("assetClass") or "equity"),
                }
            )
        if not normalized:
            errors.append("EMPTY_ORDER_INTENT")
        return normalized, errors, warnings

    def _ensure_approval(
        self,
        ctx: Ctx,
        intent: dict[str, Any],
        decision: dict[str, Any],
    ) -> None:
        existing = self.platform.approvals.list(
            ctx.tenant_id,
            run_id=intent["run_id"],
            state="pending",
            limit=100,
        )
        if any((a.get("request") or {}).get("intent_id") == intent["intent_id"] for a in existing):
            return
        approval = self.platform.approvals.create(
            ctx.tenant_id,
            intent["run_id"],
            kind="order_intent",
            request={"intent_id": intent["intent_id"], "risk_decision": decision},
            requested_by=ctx.actor_id,
        )
        _emit(
            self.platform,
            ctx=ctx,
            run_id=intent["run_id"],
            event_type="approval_requested",
            data={"approval_id": approval["approval_id"], "intent_id": intent["intent_id"]},
        )

    def _has_connected_execution_provider(self, tenant_id: str, broker: str) -> bool:
        names = {broker, "ibkr", "interactive_brokers"} if broker == BROKER_IBKR else {broker}
        for conn in self.platform.providers.list_connections(tenant_id):
            if conn["state"] != "connected" or conn["provider"] not in names:
                continue
            caps = {str(c).lower() for c in conn.get("capabilities") or []}
            if caps.intersection({"orders", "trading", "execution"}):
                return True
        return False

    def _ibkr_configured(self) -> bool:
        adapter = self.adapters.get(BROKER_IBKR)
        return bool(adapter and getattr(adapter, "configured", lambda: True)())

    def _execution_control(self, tenant_id: str) -> dict[str, Any]:
        if _env_flag("DOOMBERG_EXECUTION_KILL_SWITCH"):
            return {
                "enabled": True,
                "source": "environment",
                "reason": "DOOMBERG_EXECUTION_KILL_SWITCH is active",
                "version": 0,
                "tenant_version": 0,
                "tenant_control": None,
                "global_control": None,
            }
        controls = getattr(self.platform, "execution_controls", None)
        if controls is None:
            return {
                "enabled": True,
                "source": "missing_control_store",
                "reason": "execution control store is unavailable",
                "version": 0,
                "tenant_version": 0,
                "tenant_control": None,
                "global_control": None,
            }
        return controls.get_effective(str(tenant_id))

    @contextmanager
    def _submission_guard(self, tenant_id: str) -> Iterator[None]:
        controls = getattr(self.platform, "execution_controls", None)
        if controls is None:
            yield
            return
        with controls.submission_guard(str(tenant_id)):
            yield

    def _client_order_id(self, intent_id: str, idx: int) -> str:
        return f"dmbg-{intent_id.replace('-', '')[:20]}-{idx:02d}"

    def _intent_state_after_submit(self, orders: list[dict[str, Any]], fills: list[dict[str, Any]]) -> str:
        if orders and all(order["state"] == "rejected" for order in orders):
            return "rejected"
        if any(order["state"] == "filled" for order in orders) or fills:
            if orders and all(order["state"] == "filled" for order in orders):
                return "filled"
            return "partially_filled"
        if orders and all(order["state"] in TERMINAL_ORDER_STATES for order in orders):
            if any(order["state"] == "cancelled" for order in orders):
                return "cancelled"
        return "submitted"
