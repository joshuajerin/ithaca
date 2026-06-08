"""Trade-flow alert rules: schema, evaluation, and dashboard scanning.

An alert rule watches one metric on a single symbol's trade-flow panel and fires
when the metric crosses the user's threshold. Rules are persisted per session in
``state``; evaluation happens whenever a ``trade_flow`` panel is (re)built so a
fired event lands in the session's notification feed.
"""
from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional

from . import state

# Supported alert metrics. The frontend mirrors these labels/units.
METRICS: List[dict] = [
    {
        "id": "block_size",
        "label": "Block print size",
        "unit": "shares",
        "help": "Fires when a single block print prints at or above this many shares.",
    },
    {
        "id": "dark_pool_pct",
        "label": "Dark pool share",
        "unit": "%",
        "help": "Fires when dark-pool volume reaches this percentage of total flow.",
    },
    {
        "id": "buy_imbalance",
        "label": "Buy imbalance",
        "unit": "%",
        "help": "Fires when net buy pressure reaches this percentage of two-sided flow.",
    },
]
_METRIC_IDS = {m["id"] for m in METRICS}
_METRIC_LABELS = {m["id"]: m["label"] for m in METRICS}


def normalize_rule(payload: dict) -> dict:
    """Validate and normalize an incoming rule payload. Raises ``ValueError``."""
    symbol = (payload.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    metric = (payload.get("metric") or "").strip().lower()
    if metric not in _METRIC_IDS:
        raise ValueError(f"metric must be one of {sorted(_METRIC_IDS)}")
    try:
        threshold = float(payload.get("threshold"))
    except (TypeError, ValueError):
        raise ValueError("threshold must be a number")
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    return {
        "id": uuid.uuid4().hex[:12],
        "symbol": symbol,
        "metric": metric,
        "metricLabel": _METRIC_LABELS[metric],
        "threshold": threshold,
        "createdAt": _now_iso(),
    }


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _fmt_shares(n: float) -> str:
    n = float(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return f"{n:.0f}"


def evaluate_rule(rule: dict, flow: dict) -> List[dict]:
    """Return the events a single rule produces against one trade-flow payload."""
    metric = rule.get("metric")
    threshold = float(rule.get("threshold", 0))
    symbol = rule.get("symbol")
    events: List[dict] = []

    if metric == "block_size":
        for p in flow.get("prints", []):
            if not p.get("isBlock"):
                continue
            size = float(p.get("size") or 0)
            if size >= threshold:
                t = p.get("time", "")
                events.append(_event(
                    rule, flow,
                    value=size,
                    signature=f"{rule['id']}:block:{t}:{int(size)}",
                    message=(
                        f"{symbol} block {p.get('side', '')} of {_fmt_shares(size)} shares "
                        f"at {t} (\u2265 {_fmt_shares(threshold)})"
                    ),
                ))
    elif metric == "dark_pool_pct":
        value = float(flow.get("darkPoolPct") or 0)
        if value >= threshold:
            events.append(_event(
                rule, flow,
                value=value,
                signature=f"{rule['id']}:dark:{value:.1f}",
                message=f"{symbol} dark-pool flow at {value:.1f}% (\u2265 {threshold:.0f}%)",
            ))
    elif metric == "buy_imbalance":
        value = float(flow.get("buyImbalance") or 0) * 100.0
        if value >= threshold:
            events.append(_event(
                rule, flow,
                value=value,
                signature=f"{rule['id']}:imb:{value:.1f}",
                message=f"{symbol} buy imbalance at {value:.0f}% (\u2265 {threshold:.0f}%)",
            ))
    return events


def _event(rule: dict, flow: dict, value: float, signature: str, message: str) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "ruleId": rule.get("id"),
        "symbol": rule.get("symbol"),
        "metric": rule.get("metric"),
        "metricLabel": rule.get("metricLabel"),
        "threshold": rule.get("threshold"),
        "value": round(value, 2),
        "message": message,
        "signature": signature,
        "at": _now_iso(),
    }


def evaluate_flow(session_id: str, flow: dict) -> List[dict]:
    """Evaluate every rule for ``flow``'s symbol and record any new events.

    Returns only the genuinely new events (de-duplicated by signature)."""
    symbol = (flow.get("symbol") or "").upper()
    if not symbol:
        return []
    rules = [r for r in state.get_alert_rules(session_id) if r.get("symbol") == symbol]
    if not rules:
        return []
    produced: List[dict] = []
    for rule in rules:
        produced.extend(evaluate_rule(rule, flow))
    if not produced:
        return []
    return state.add_alert_events(session_id, produced)


def evaluate_dashboard(session_id: str, panels: List[dict]) -> List[dict]:
    """Scan a freshly-built dashboard for trade-flow panels and fire alerts."""
    if not session_id or not panels:
        return []
    added: List[dict] = []
    for panel in panels:
        if panel.get("type") != "trade_flow":
            continue
        data = panel.get("data")
        if isinstance(data, dict):
            added.extend(evaluate_flow(session_id, data))
    return added
