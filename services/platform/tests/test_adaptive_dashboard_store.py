"""Adaptive dashboard profile validation and storage."""

from __future__ import annotations

import pytest

from ithaca_platform import AdaptiveDashboardSpecError, validate_adaptive_dashboard_spec
from platform_helpers import new_uuid


def _spec(widget_id: str = "performance_pnl") -> dict:
    return {
        "summary": "User mostly watches performance.",
        "widgets": [
            {
                "id": widget_id,
                "title": "Performance",
                "priority": 1,
                "layout": {"x": 0, "y": 0, "w": 6, "h": 3},
                "reason": "The user opens performance views most often.",
            }
        ],
    }


def test_validation_rejects_non_object_json():
    with pytest.raises(AdaptiveDashboardSpecError):
        validate_adaptive_dashboard_spec(["not", "an", "object"])


def test_validation_rejects_unknown_widget_id():
    with pytest.raises(AdaptiveDashboardSpecError, match="unknown widget"):
        validate_adaptive_dashboard_spec(_spec("exec_arbitrary_code"))


def test_validation_rejects_bad_layout_bounds():
    spec = _spec()
    spec["widgets"][0]["layout"] = {"x": 9, "y": 0, "w": 6, "h": 3}

    with pytest.raises(AdaptiveDashboardSpecError, match="12-column"):
        validate_adaptive_dashboard_spec(spec)


def test_valid_profile_upsert(platform):
    tenant_id = new_uuid()
    user_id = new_uuid()

    row = platform.adaptive_dashboards.upsert(
        tenant_id,
        user_id,
        _spec(),
        model="claude-haiku-4-5-20251001",
        source_session_count=2,
        source_event_count=9,
        generated_for_date="2026-06-29",
    )

    assert row["tenant_id"] == tenant_id
    assert row["user_id"] == user_id
    assert row["spec"]["widgets"][0]["id"] == "performance_pnl"
    assert row["source_session_count"] == 2
    assert platform.adaptive_dashboards.get(tenant_id, user_id)["generated_for_date"] == "2026-06-29"
