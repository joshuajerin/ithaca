"""Adaptive dashboard worker scheduling and model response handling."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from ithaca_runtime import (
    AdaptiveDashboardWorker,
    AnthropicDashboardClient,
    AnthropicDashboardError,
    DashboardGenerationError,
    OpenAICompatibleDashboardClient,
    create_adaptive_dashboard_client,
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


def test_usage_signals_do_not_forward_raw_user_or_tool_payloads(durable_platform):
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    _append_session(durable_platform, tenant_id, user_id, prompt="private NVDA thesis")

    signals = usage_signals_for_user(durable_platform, tenant_id, user_id)

    assert signals["session_count"] == 1
    assert signals["top_tools"] == [{"name": "market_news", "count": 1}]
    serialized = json.dumps(signals)
    assert "private NVDA thesis" not in serialized
    assert "NVDA" not in serialized
    assert "args" not in serialized


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


def test_openai_compatible_client_accepts_chat_completion_json(monkeypatch):
    captured: dict[str, Any] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": json.dumps(_profile_spec())}}]}
            ).encode("utf-8")

    def _urlopen(request, **_kwargs):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)

    result = OpenAICompatibleDashboardClient(
        api_key="modal-key",
        base_url="https://example.test/v1/",
    ).generate({"session_count": 1})

    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer modal-key"
    assert captured["body"]["model"] == "google/gemma-4-E4B-it"
    assert result["widgets"][0]["id"] == "performance_pnl"


def test_openai_compatible_client_rejects_invalid_json(monkeypatch):
    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"not json"}}]}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response())

    with pytest.raises(DashboardGenerationError, match="invalid JSON"):
        OpenAICompatibleDashboardClient(api_key="modal-key", base_url="https://example.test/v1").generate(
            {"session_count": 1}
        )


def test_modal_client_sends_proxy_token_headers(monkeypatch):
    captured: dict[str, Any] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": json.dumps(_profile_spec())}}]}
            ).encode("utf-8")

    def _urlopen(request, **_kwargs):
        captured["headers"] = dict(request.header_items())
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)

    OpenAICompatibleDashboardClient(
        base_url="https://example.test/v1",
        auth_mode="modal-proxy",
        modal_key="wk-test",
        modal_secret="ws-test",
    ).generate({"session_count": 1})

    assert captured["headers"]["Modal-key"] == "wk-test"
    assert captured["headers"]["Modal-secret"] == "ws-test"


def test_default_client_prefers_modal_provider(monkeypatch):
    monkeypatch.delenv("ITHACA_ADAPTIVE_DASHBOARD_PROVIDER", raising=False)
    monkeypatch.setenv("ITHACA_ADAPTIVE_DASHBOARD_MODAL_KEY", "wk-test")
    monkeypatch.setenv("ITHACA_ADAPTIVE_DASHBOARD_MODAL_SECRET", "ws-test")
    monkeypatch.setenv("ITHACA_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL", "https://example.test/v1")

    client = create_adaptive_dashboard_client()

    assert isinstance(client, OpenAICompatibleDashboardClient)
    assert client.auth_mode == "modal-proxy"
