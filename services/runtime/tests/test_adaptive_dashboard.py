"""Adaptive dashboard worker scheduling and Anthropic response handling."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from doomberg_runtime import (
    AdaptiveDashboardWorker,
    AnthropicDashboardClient,
    AnthropicDashboardError,
    recompute_user_profile,
    usage_signals_for_user,
)


def _profile_spec(title: str = "Performance") -> dict[str, Any]:
    return {
        "summary": "Performance-heavy usage.",
        "widgets": [
            {
                "id": "performance_pnl",
                "title": title,
                "priority": 1,
                "layout": {"x": 0, "y": 0, "w": 6, "h": 3},
                "reason": "The user watches performance.",
            }
        ],
    }


def _append_session(platform, tenant_id: str, user_id: str, *, prompt: str = "check NVDA") -> str:
    run_id = platform.runs.create_research(tenant_id)
    now = datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc).isoformat()
    platform.trace.append(
        {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "ts": now,
            "type": "session_open",
            "session_id": run_id,
            "origin_session_id": run_id,
            "actor": {"kind": "user", "id": user_id},
            "data": {"prompt": prompt, "title": "NVDA"},
        }
    )
    platform.trace.append(
        {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "ts": now,
            "type": "tool_call",
            "session_id": run_id,
            "actor": {"kind": "user", "id": user_id},
            "data": {"name": "market_news", "args": {"symbol": "NVDA"}},
        }
    )
    return run_id


class _FakeClient:
    model = "fake-haiku"

    def __init__(self, spec: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.spec = spec or _profile_spec()
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def generate(self, signals: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(signals)
        if self.error:
            raise self.error
        return self.spec


def test_usage_signals_do_not_forward_raw_tool_args(durable_platform):
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    _append_session(durable_platform, tenant_id, user_id)

    signals = usage_signals_for_user(durable_platform, tenant_id, user_id)

    assert signals["session_count"] == 1
    assert signals["top_tools"] == [{"name": "market_news", "count": 1}]
    assert "args" not in json.dumps(signals)


def test_worker_runs_only_at_midnight_utc_and_uses_lease(durable_platform):
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    _append_session(durable_platform, tenant_id, user_id)

    worker = AdaptiveDashboardWorker(durable_platform, client=_FakeClient(), owner_id="worker-a")

    skipped = worker.poll_once(now=datetime(2026, 6, 29, 1, 0, tzinfo=timezone.utc))
    assert skipped["reason"] == "not-midnight-utc"

    ran = worker.poll_once(now=datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc))
    assert ran["status"] == "ran"
    assert ran["updated"][0]["user_id"] == user_id

    other = AdaptiveDashboardWorker(durable_platform, client=_FakeClient(), owner_id="worker-b")
    held = other.poll_once(now=datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc))
    assert held["reason"] == "lease-held"


def test_worker_records_anthropic_failure_and_continues(durable_platform):
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    _append_session(durable_platform, tenant_id, user_id)
    worker = AdaptiveDashboardWorker(
        durable_platform,
        client=_FakeClient(error=AnthropicDashboardError("model down")),
        owner_id="worker-fail",
    )

    result = worker.poll_once(now=datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc))

    assert result["status"] == "ran"
    assert result["updated"] == []
    assert result["failed"][0]["user_id"] == user_id
    assert "model down" in result["failed"][0]["error"]


def test_recompute_replaces_same_user_date_idempotently(durable_platform):
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    _append_session(durable_platform, tenant_id, user_id)

    first = recompute_user_profile(
        durable_platform,
        tenant_id,
        user_id,
        client=_FakeClient(_profile_spec("Performance")),
        generated_for_date="2026-06-29",
    )
    second = recompute_user_profile(
        durable_platform,
        tenant_id,
        user_id,
        client=_FakeClient(_profile_spec("Risk")),
        generated_for_date="2026-06-29",
    )

    assert first["created_at"] == second["created_at"]
    assert second["spec"]["widgets"][0]["title"] == "Risk"


def test_anthropic_client_rejects_empty_output(monkeypatch):
    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"content":[{"type":"text","text":""}]}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response())

    with pytest.raises(AnthropicDashboardError, match="empty"):
        AnthropicDashboardClient(api_key="test-key").generate({"session_count": 1})


def test_anthropic_client_rejects_invalid_json(monkeypatch):
    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"content":[{"type":"text","text":"not json"}]}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response())

    with pytest.raises(AnthropicDashboardError, match="invalid JSON"):
        AnthropicDashboardClient(api_key="test-key").generate({"session_count": 1})
