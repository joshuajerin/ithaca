"""Adaptive dashboard profile store and strict spec validation."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from .db import Db

ADAPTIVE_WIDGET_IDS = (
    "performance_pnl",
    "portfolio_risk",
    "trade_flow",
    "order_book",
    "congress_trades",
    "yield_curve",
    "sentiment",
    "recent_sessions",
    "tool_usage",
    "warning_watch",
    "live_data_status",
)

_ADAPTIVE_WIDGET_ID_SET = set(ADAPTIVE_WIDGET_IDS)

DEFAULT_ADAPTIVE_DASHBOARD_SPEC: dict[str, Any] = {
    "summary": "A default dashboard layout is shown until your daily adaptive profile is ready.",
    "widgets": [
        {
            "id": "performance_pnl",
            "title": "Performance",
            "priority": 1,
            "layout": {"x": 0, "y": 0, "w": 6, "h": 3},
            "reason": "Default performance overview while the adaptive profile is pending.",
        },
        {
            "id": "portfolio_risk",
            "title": "Portfolio Risk",
            "priority": 2,
            "layout": {"x": 6, "y": 0, "w": 6, "h": 3},
            "reason": "Default risk overview while the adaptive profile is pending.",
        },
        {
            "id": "trade_flow",
            "title": "Trade Flow",
            "priority": 3,
            "layout": {"x": 0, "y": 3, "w": 4, "h": 3},
            "reason": "Default activity view while the adaptive profile is pending.",
        },
        {
            "id": "order_book",
            "title": "Order Book",
            "priority": 4,
            "layout": {"x": 4, "y": 3, "w": 4, "h": 3},
            "reason": "Default order activity view while the adaptive profile is pending.",
        },
        {
            "id": "congress_trades",
            "title": "Congress Trades",
            "priority": 5,
            "layout": {"x": 8, "y": 3, "w": 4, "h": 3},
            "reason": "Default market context while the adaptive profile is pending.",
        },
        {
            "id": "yield_curve",
            "title": "Yield Curve",
            "priority": 6,
            "layout": {"x": 0, "y": 6, "w": 6, "h": 3},
            "reason": "Default macro context while the adaptive profile is pending.",
        },
        {
            "id": "sentiment",
            "title": "Sentiment",
            "priority": 7,
            "layout": {"x": 6, "y": 6, "w": 6, "h": 3},
            "reason": "Default sentiment context while the adaptive profile is pending.",
        },
    ],
}


class AdaptiveDashboardSpecError(ValueError):
    """The model returned a dashboard spec outside the closed contract."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    return json.loads(raw)


def _date_str(value: date | str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str) or not value.strip():
        raise ValueError("generated_for_date must be a date string")
    return value.strip()


def _require_int(value: Any, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise AdaptiveDashboardSpecError(f"{field} must be an integer")
    return int(value)


def validate_adaptive_dashboard_spec(raw: Any) -> dict[str, Any]:
    """Validate the closed JSON contract stored and sent to the browser.

    Claude may choose priority and placement only. Widget ids are a server-side allowlist,
    and the returned object is reduced to the exact fields the UI renders.
    """
    if not isinstance(raw, dict):
        raise AdaptiveDashboardSpecError("spec must be a JSON object")
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise AdaptiveDashboardSpecError("summary must be a non-empty string")
    widgets_raw = raw.get("widgets")
    if not isinstance(widgets_raw, list) or not widgets_raw:
        raise AdaptiveDashboardSpecError("widgets must be a non-empty array")

    seen: set[str] = set()
    widgets: list[dict[str, Any]] = []
    for index, item in enumerate(widgets_raw):
        if not isinstance(item, dict):
            raise AdaptiveDashboardSpecError(f"widgets[{index}] must be an object")
        widget_id = item.get("id")
        if widget_id not in _ADAPTIVE_WIDGET_ID_SET:
            raise AdaptiveDashboardSpecError(f"unknown widget id: {widget_id!r}")
        if widget_id in seen:
            raise AdaptiveDashboardSpecError(f"duplicate widget id: {widget_id}")
        seen.add(str(widget_id))

        title = item.get("title")
        reason = item.get("reason")
        layout = item.get("layout")
        if not isinstance(title, str) or not title.strip():
            raise AdaptiveDashboardSpecError(f"{widget_id}.title must be a non-empty string")
        if not isinstance(reason, str) or not reason.strip():
            raise AdaptiveDashboardSpecError(f"{widget_id}.reason must be a non-empty string")
        if not isinstance(layout, dict):
            raise AdaptiveDashboardSpecError(f"{widget_id}.layout must be an object")
        x = _require_int(layout.get("x"), field=f"{widget_id}.layout.x")
        y = _require_int(layout.get("y"), field=f"{widget_id}.layout.y")
        w = _require_int(layout.get("w"), field=f"{widget_id}.layout.w")
        h = _require_int(layout.get("h"), field=f"{widget_id}.layout.h")
        if x < 0 or y < 0 or w < 1 or h < 1:
            raise AdaptiveDashboardSpecError(f"{widget_id}.layout has negative or empty bounds")
        if x > 11 or w > 12 or x + w > 12:
            raise AdaptiveDashboardSpecError(f"{widget_id}.layout must fit a 12-column grid")
        if y > 48 or h > 12 or y + h > 60:
            raise AdaptiveDashboardSpecError(f"{widget_id}.layout height is out of bounds")

        priority = _require_int(item.get("priority"), field=f"{widget_id}.priority")
        if priority < 1 or priority > 100:
            raise AdaptiveDashboardSpecError(f"{widget_id}.priority is out of bounds")

        widgets.append(
            {
                "id": widget_id,
                "title": title.strip()[:80],
                "priority": priority,
                "layout": {"x": x, "y": y, "w": w, "h": h},
                "reason": reason.strip()[:240],
            }
        )

    widgets.sort(key=lambda widget: (widget["priority"], widget["layout"]["y"], widget["layout"]["x"]))
    return {"summary": summary.strip()[:500], "widgets": widgets}


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "tenant_id": row["tenant_id"],
        "user_id": row["user_id"],
        "spec": _loads(row["spec"], {}),
        "model": row["model"],
        "source_session_count": int(row["source_session_count"]),
        "source_event_count": int(row["source_event_count"]),
        "generated_for_date": row["generated_for_date"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class AdaptiveDashboardProfileStore:
    """Tenant- and user-scoped adaptive dashboard profiles."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def get(self, tenant_id: str, user_id: str) -> dict[str, Any] | None:
        row = self._db.conn.execute(
            "SELECT * FROM adaptive_dashboard_profiles WHERE tenant_id = ? AND user_id = ?",
            (str(tenant_id), str(user_id)),
        ).fetchone()
        return _row_to_dict(row) if row else None

    def upsert(
        self,
        tenant_id: str,
        user_id: str,
        spec: dict[str, Any],
        *,
        model: str,
        source_session_count: int,
        source_event_count: int,
        generated_for_date: date | str,
    ) -> dict[str, Any]:
        cleaned = validate_adaptive_dashboard_spec(spec)
        now = _now()
        day = _date_str(generated_for_date)
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO adaptive_dashboard_profiles "
                    "(tenant_id, user_id, spec, model, source_session_count, source_event_count, "
                    " generated_for_date, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(tenant_id, user_id) DO UPDATE SET "
                    "spec = excluded.spec, "
                    "model = excluded.model, "
                    "source_session_count = excluded.source_session_count, "
                    "source_event_count = excluded.source_event_count, "
                    "generated_for_date = excluded.generated_for_date, "
                    "updated_at = excluded.updated_at",
                    (
                        str(tenant_id),
                        str(user_id),
                        json.dumps(cleaned),
                        str(model),
                        int(source_session_count),
                        int(source_event_count),
                        day,
                        now,
                        now,
                    ),
                )
        row = self.get(tenant_id, user_id)
        if row is None:
            raise RuntimeError("adaptive dashboard profile upsert failed")
        return row
