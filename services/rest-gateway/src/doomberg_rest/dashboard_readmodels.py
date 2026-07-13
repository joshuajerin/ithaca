"""Tenant-scoped, provenance-carrying read models for the personalized dashboard.

These adapters only summarize durable tenant rows. They never manufacture market,
performance, or risk values when the underlying result does not contain them.
"""

from __future__ import annotations

import os
import math
from datetime import datetime, timezone
from typing import Any, Iterable

from doomberg_core.providers import PUBLIC_DATA_SOURCE, PUBLIC_ENTITLEMENT_CLASS

_TERMINAL_STATES = {"succeeded", "failed", "timeout", "cancelled", "retired"}
_RISK_KEYS = {
    "alpha",
    "beta",
    "calmar",
    "correlation",
    "factorExposures",
    "factor_exposures",
    "informationRatio",
    "information_ratio",
    "maxDD",
    "max_drawdown",
    "risk",
    "sharpe",
    "sortino",
    "trackingError",
    "tracking_error",
    "var",
    "var95",
    "vol",
    "volatility",
}
_PRIVATE_LIVE_NAMES = {
    "ibkr",
    "ibkr-engine",
    "interactive_brokers",
    "interactive-brokers",
    PUBLIC_DATA_SOURCE,
}
_BACKTEST_SCAN_LIMIT = 50
_MAX_EQUITY_CURVE_POINTS = 1_000
_MAX_EQUITY_DATE_LENGTH = 64
_PERFORMANCE_KEYS = {
    "cagr",
    "maxDD",
    "sharpe",
    "sortino",
    "totalReturn",
    "vol",
    "winRate",
}


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest_timestamp(rows: Iterable[dict[str, Any]]) -> str | None:
    candidates: list[tuple[datetime, str]] = []
    for row in rows:
        for key in ("as_of", "updated_at", "created_at"):
            raw = row.get(key)
            parsed = _timestamp(raw)
            if parsed is not None:
                candidates.append((parsed, str(raw)))
                break
    return max(candidates, default=(None, None), key=lambda item: item[0])[1]


def _freshness_ms(as_of: str | None) -> int | None:
    parsed = _timestamp(as_of)
    if parsed is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds() * 1000))


def _stale_after_ms() -> int:
    raw = os.environ.get("DOOMBERG_DASHBOARD_STALE_AFTER_MS", "86400000")
    try:
        return max(60_000, int(raw))
    except ValueError:
        return 86_400_000


def _envelope(
    *,
    data: dict[str, Any],
    source: str,
    as_of: str | None,
    entitlement_class: str | None = None,
    empty: bool = False,
    unavailable: tuple[str, str] | None = None,
) -> dict[str, Any]:
    freshness = _freshness_ms(as_of)
    if unavailable is not None:
        status = "unavailable"
        error: dict[str, str] | None = {"code": unavailable[0], "message": unavailable[1]}
    elif empty:
        status = "empty"
        error = None
    elif freshness is not None and freshness > _stale_after_ms():
        status = "stale"
        error = None
    else:
        status = "ready"
        error = None
    return {
        "status": status,
        "as_of": as_of,
        "source": source,
        "entitlement_class": entitlement_class,
        "freshness_ms": freshness,
        "data": data,
        "error": error,
    }


def _result_data(run: dict[str, Any]) -> dict[str, Any]:
    result = run.get("result")
    if not isinstance(result, dict):
        return {}
    nested = result.get("data")
    return nested if isinstance(nested, dict) else result


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(
        rows,
        default=None,
        key=lambda row: (
            _timestamp(row.get("updated_at"))
            or _timestamp(row.get("created_at"))
            or datetime.min.replace(tzinfo=timezone.utc),
            str(row.get("run_id") or ""),
        ),
    )


def _public_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run.get("run_id"),
        "kind": run.get("kind"),
        "state": run.get("state"),
        "strategy_id": run.get("strategy_id"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
    }


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(float(value)) else None


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _numeric_dict(value: Any, *, allowed: set[str] | None = None) -> dict[str, int | float]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): number
        for key, raw in value.items()
        if (allowed is None or str(key) in allowed) and (number := _number(raw)) is not None
    }


def _equity_curve(value: Any) -> list[dict[str, str | int | float]]:
    if not isinstance(value, list):
        return []
    if len(value) > _MAX_EQUITY_CURVE_POINTS:
        step = (len(value) - 1) / (_MAX_EQUITY_CURVE_POINTS - 1)
        value = [value[round(index * step)] for index in range(_MAX_EQUITY_CURVE_POINTS)]
    curve: list[dict[str, str | int | float]] = []
    for point in value:
        if (
            not isinstance(point, dict)
            or not isinstance(point.get("d"), str)
            or len(point["d"]) > _MAX_EQUITY_DATE_LENGTH
        ):
            continue
        number = _number(point.get("v"))
        if number is not None:
            curve.append({"d": point["d"], "v": number})
    return curve


def _backtest_evidence(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if run is None:
        return None
    data = _result_data(run)
    curve = _equity_curve(data.get("equityCurve"))
    stats = _numeric_dict(data.get("stats"), allowed=_PERFORMANCE_KEYS)
    if not curve and not stats:
        return None
    return {
        **_public_run(run),
        "equity_curve": curve,
        "stats": stats,
    }


def _latest_backtest_evidence(
    runs: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    candidates = [
        (run, evidence)
        for run in runs
        if run.get("kind") == "backtest" and (evidence := _backtest_evidence(run)) is not None
    ]
    if not candidates:
        return None, None
    run, evidence = max(
        candidates,
        key=lambda pair: (
            _timestamp(pair[0].get("updated_at"))
            or _timestamp(pair[0].get("created_at"))
            or datetime.min.replace(tzinfo=timezone.utc),
            str(pair[0].get("run_id") or ""),
        ),
    )
    return run, evidence


def dashboard_summary(stores: Any, tenant_id: str) -> dict[str, Any]:
    counts = stores.dashboard.run_counts(tenant_id)
    recent = stores.dashboard.recent_runs(tenant_id, limit=1)
    latest_run = recent[0] if recent else None
    backtests = stores.dashboard.recent_runs(
        tenant_id,
        kind="backtest",
        state="succeeded",
        limit=_BACKTEST_SCAN_LIMIT,
        with_result=True,
    )
    latest_backtest, backtest_evidence = _latest_backtest_evidence(backtests)
    paper_evidence = stores.dashboard.latest_paper_book(tenant_id)
    latest_paper = paper_evidence["run"] if paper_evidence else None
    book = paper_evidence["book"] if paper_evidence else None
    book_view = _public_book(book)
    total = sum(counts.values())
    data = {
        "run_counts": {
            "total": total,
            "active": sum(
                count for state, count in counts.items() if state not in _TERMINAL_STATES
            ),
            "by_state": counts,
        },
        "latest_run": _public_run(latest_run) if latest_run else None,
        "latest_backtest": backtest_evidence,
        "latest_paper": (
            {**_public_run(latest_paper), "book": book_view} if latest_paper else None
        ),
    }
    as_of = _latest_timestamp([row for row in (latest_run, book) if row is not None])
    return _envelope(
        data=data,
        source="doomberg-platform",
        as_of=as_of,
        empty=not total,
        unavailable=(
            "PAPER_BOOK_INVALID",
            "The latest paper book could not be read safely.",
        )
        if book is not None and book_view is None
        else None,
    )


def dashboard_risk(stores: Any, tenant_id: str) -> dict[str, Any]:
    runs = stores.dashboard.recent_runs(
        tenant_id,
        kind="backtest",
        state="succeeded",
        limit=_BACKTEST_SCAN_LIMIT,
        with_result=True,
    )
    risk_candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for run in runs:
        if run.get("kind") != "backtest":
            continue
        backtest_risk: dict[str, Any] = {}
        result = _result_data(run)
        backtest_risk = _numeric_dict(result.get("stats"), allowed=_RISK_KEYS)
        nested_risk = result.get("risk")
        if isinstance(nested_risk, dict):
            backtest_risk = {
                **backtest_risk,
                **_numeric_dict(nested_risk, allowed=_RISK_KEYS),
            }
        if backtest_risk:
            risk_candidates.append((run, backtest_risk))
    latest_backtest, backtest_risk = max(
        risk_candidates,
        default=(None, {}),
        key=lambda pair: (
            _timestamp(pair[0].get("updated_at"))
            or _timestamp(pair[0].get("created_at"))
            or datetime.min.replace(tzinfo=timezone.utc),
            str(pair[0].get("run_id") or ""),
        ),
    )

    paper_evidence = stores.dashboard.latest_paper_book(tenant_id)
    book = paper_evidence["book"] if paper_evidence else None
    paper_exposure = _public_book(book)
    data = {
        "backtest": {
            "run_id": latest_backtest.get("run_id"),
            "metrics": backtest_risk,
        }
        if latest_backtest and backtest_risk
        else None,
        "paper_exposure": paper_exposure,
    }
    evidence_rows = [row for row in (latest_backtest if backtest_risk else None, book) if row]
    return _envelope(
        data=data,
        source="doomberg-platform",
        as_of=_latest_timestamp(evidence_rows),
        empty=not backtest_risk and book is None,
        unavailable=(
            "PAPER_BOOK_INVALID",
            "The latest paper book could not be read safely.",
        )
        if book is not None and paper_exposure is None
        else None,
    )


def dashboard_activity(stores: Any, tenant_id: str, *, limit: int = 20) -> dict[str, Any]:
    runs = stores.dashboard.recent_runs(tenant_id, limit=limit)
    triggers = stores.dashboard.recent_triggers(tenant_id, limit=limit)
    alerts = stores.dashboard.recent_alerts(tenant_id, limit=limit)
    data = {
        "runs": [_public_run(run) for run in runs],
        "triggers": [_public_trigger(trigger) for trigger in triggers],
        "alerts": [_public_alert(alert) for alert in alerts],
    }
    rows = [*runs, *triggers, *alerts]
    return _envelope(
        data=data,
        source="doomberg-platform",
        as_of=_latest_timestamp(rows),
        empty=not rows,
    )


def public_provider_connection(connection: dict[str, Any]) -> dict[str, Any]:
    provider = str(connection.get("provider") or "")
    private_live = provider.strip().lower() in _PRIVATE_LIVE_NAMES
    return {
        "tenant_id": connection.get("tenant_id"),
        "connection_id": connection.get("connection_id"),
        "provider": PUBLIC_DATA_SOURCE if private_live else provider,
        "state": connection.get("state"),
        "capabilities": [
            capability
            for capability in connection.get("capabilities") or []
            if str(capability).strip().lower() not in {"orders", "trading", "execution"}
        ],
        "entitlements": [
            {**entitlement, "entitlement_class": PUBLIC_ENTITLEMENT_CLASS}
            if private_live
            else entitlement
            for entitlement in connection.get("entitlements") or []
            if isinstance(entitlement, dict)
        ],
        "retention_policy": connection.get("retention_policy"),
        "credential_configured": bool(connection.get("credential_ref")),
        "created_at": connection.get("created_at"),
        "updated_at": connection.get("updated_at"),
    }


def _public_entitlement(entitlement: dict[str, Any], *, private_live: bool) -> dict[str, Any]:
    permitted_use = entitlement.get("permitted_use")
    return {
        "dataset": _optional_string(entitlement.get("dataset")),
        "entitlement_class": (
            PUBLIC_ENTITLEMENT_CLASS
            if private_live
            else _optional_string(entitlement.get("entitlement_class"))
        ),
        "permitted_use": [str(value) for value in permitted_use]
        if isinstance(permitted_use, list)
        else [],
        "freshness_class": _optional_string(entitlement.get("freshness_class")),
        "as_of": _optional_string(entitlement.get("as_of")),
    }


def _dashboard_provider_connection(connection: dict[str, Any]) -> dict[str, Any]:
    public = public_provider_connection(connection)
    dashboard = {
        key: public[key]
        for key in (
            "connection_id",
            "provider",
            "state",
            "capabilities",
            "entitlements",
            "credential_configured",
            "created_at",
            "updated_at",
        )
    }
    dashboard["capabilities"] = [str(value) for value in dashboard["capabilities"]]
    private_live = str(connection.get("provider") or "").strip().lower() in _PRIVATE_LIVE_NAMES
    dashboard["entitlements"] = [
        _public_entitlement(entitlement, private_live=private_live)
        for entitlement in connection.get("entitlements") or []
        if isinstance(entitlement, dict)
    ]
    return dashboard


def _public_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    provider = str(snapshot.get("provider") or "")
    private_live = provider.strip().lower() in _PRIVATE_LIVE_NAMES
    return {
        "snapshot_id": snapshot.get("snapshot_id"),
        "provider": PUBLIC_DATA_SOURCE if private_live else provider,
        "dataset": snapshot.get("dataset"),
        "entitlement_class": (
            PUBLIC_ENTITLEMENT_CLASS if private_live else snapshot.get("entitlement_class")
        ),
        "as_of": snapshot.get("as_of"),
        "created_at": snapshot.get("created_at"),
    }


def _public_book(book: dict[str, Any] | None) -> dict[str, Any] | None:
    if book is None:
        return None
    capital = _number(book.get("capital"))
    raw_weights = book.get("weights")
    if capital is None or not isinstance(raw_weights, dict):
        return None
    weights = {
        str(symbol)[:32]: number
        for symbol, value in list(raw_weights.items())[:500]
        if (number := _number(value)) is not None
    }
    gross = round(sum(abs(float(weight)) for weight in weights.values()), 6)
    return {
        "run_id": book.get("run_id"),
        "capital": capital,
        "gross": gross,
        "cash": round(float(capital) * (1.0 - gross), 2),
        "weights": weights,
        "updated_at": book.get("updated_at"),
    }


def _public_trigger(trigger: dict[str, Any]) -> dict[str, Any]:
    return {
        "trigger_id": trigger.get("trigger_id"),
        "name": trigger.get("name"),
        "state": trigger.get("state"),
        "created_at": trigger.get("created_at"),
        "updated_at": trigger.get("updated_at"),
    }


def _public_alert(alert: dict[str, Any]) -> dict[str, Any]:
    payload = alert.get("payload")
    public_payload_keys = {
        "code",
        "message",
        "reason",
        "run_id",
        "state",
        "symbol",
        "title",
        "trigger_id",
    }
    public_payload = (
        {
            key: value
            for key, value in payload.items()
            if key in public_payload_keys and isinstance(value, (str, int, float, bool))
        }
        if isinstance(payload, dict)
        else {}
    )
    return {
        "notification_id": alert.get("notification_id"),
        "event_type": alert.get("event_type"),
        "subject_type": alert.get("subject_type"),
        "subject_id": alert.get("subject_id"),
        "priority": alert.get("priority"),
        "state": alert.get("state"),
        "payload": public_payload,
        "created_at": alert.get("created_at"),
        "updated_at": alert.get("updated_at"),
    }


def provider_status(stores: Any, tenant_id: str) -> dict[str, Any]:
    connections = stores.dashboard.provider_connections(tenant_id)
    counts = stores.dashboard.provider_counts(tenant_id)
    public = [_dashboard_provider_connection(connection) for connection in connections]
    connected = [connection for connection in public if connection.get("state") == "connected"]
    entitlement_classes = {
        str(entitlement.get("entitlement_class"))
        for connection in connected
        for entitlement in connection.get("entitlements") or []
        if isinstance(entitlement, dict) and entitlement.get("entitlement_class")
    }
    entitlement = next(iter(entitlement_classes)) if len(entitlement_classes) == 1 else None
    data = {
        "connections": public,
        "counts": counts,
        "live_engine_configured": bool(os.environ.get("DOOMBERG_IBKR_ENGINE_URL")),
    }
    return _envelope(
        data=data,
        source="provider-registry",
        as_of=_latest_timestamp(connections),
        entitlement_class=entitlement,
        empty=not counts["total"],
    )


def dashboard_market(stores: Any, tenant_id: str) -> dict[str, Any]:
    snapshots = stores.dashboard.snapshots(tenant_id, limit=25)
    public_snapshots = [_public_snapshot(snapshot) for snapshot in snapshots]
    connections = stores.dashboard.provider_connections(tenant_id)
    quote_connections = [
        connection
        for connection in connections
        if connection.get("state") == "connected"
        and {
            str(capability).strip().lower() for capability in connection.get("capabilities") or []
        }.intersection({"quote", "quotes", "market_data", "market-data", "data"})
    ]
    public_quote_connections = [_dashboard_provider_connection(row) for row in quote_connections]
    entitlement = None
    if public_snapshots:
        entitlement = public_snapshots[0].get("entitlement_class")
    elif public_quote_connections:
        first_entitlements = public_quote_connections[0].get("entitlements") or []
        if first_entitlements and isinstance(first_entitlements[0], dict):
            entitlement = first_entitlements[0].get("entitlement_class")
    data = {
        "snapshots": public_snapshots,
        "quote_providers": public_quote_connections,
    }
    engine_configured = bool(os.environ.get("DOOMBERG_IBKR_ENGINE_URL"))
    unavailable = None
    if not snapshots and quote_connections:
        unavailable = (
            "MARKET_OBSERVATION_UNAVAILABLE",
            "A market-data provider is connected, but no market observation is available.",
        )
    elif not snapshots and engine_configured:
        unavailable = (
            "MARKET_DATA_NOT_REGISTERED",
            "The live-data engine is configured but no tenant market-data source is registered.",
        )
    return _envelope(
        data=data,
        source="provider-registry",
        as_of=_latest_timestamp(snapshots),
        entitlement_class=str(entitlement) if entitlement else None,
        empty=not snapshots and unavailable is None,
        unavailable=unavailable,
    )
