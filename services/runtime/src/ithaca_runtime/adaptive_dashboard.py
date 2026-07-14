"""Adaptive dashboard recompute worker.

The worker sends only usage-derived metadata to the configured dashboard model and
persists the strict dashboard spec. It never sends credentials, raw market data,
or arbitrary browser code.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any

from ithaca_platform import (
    ADAPTIVE_WIDGET_IDS,
    DEFAULT_ADAPTIVE_DASHBOARD_SPEC,
    AdaptiveDashboardSpecError,
    validate_adaptive_dashboard_spec,
)

from .leader import acquire_loop_lease, process_owner

ANTHROPIC_HAIKU_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_OPENAI_COMPATIBLE_MODEL = "google/gemma-4-E4B-it"
DEFAULT_ADAPTIVE_DASHBOARD_PROVIDER = "modal"


class DashboardGenerationError(RuntimeError):
    """The configured dashboard model did not return a usable profile."""


class AnthropicDashboardError(DashboardGenerationError):
    """Anthropic did not return a usable dashboard profile."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _loads(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default
    return default


def _text(value: Any, limit: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned[:limit] if cleaned else None


def _event_tool_name(event: dict[str, Any]) -> str | None:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    for key in ("name", "tool", "tool_name", "toolName"):
        value = _text(data.get(key), 120)
        if value:
            return value
    return None


def _event_widget_hint(event: dict[str, Any]) -> str | None:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    for key in ("panelType", "panel_type", "widget", "widget_id"):
        value = _text(data.get(key), 120)
        if value:
            return value
    return None


def _session_actor(events: list[dict[str, Any]]) -> tuple[str, str] | None:
    for event in events:
        if event.get("type") != "session_open":
            continue
        actor = event.get("actor")
        if isinstance(actor, dict) and actor.get("kind") == "user" and actor.get("id"):
            return str(actor["kind"]), str(actor["id"])
    for event in events:
        actor = event.get("actor")
        if isinstance(actor, dict) and actor.get("kind") == "user" and actor.get("id"):
            return str(actor["kind"]), str(actor["id"])
    return None


def _events_by_research_run(platform: Any) -> dict[tuple[str, str], list[dict[str, Any]]]:
    with platform.db.system_scope():
        rows = platform.db.conn.execute(
            "SELECT r.tenant_id, r.run_id, r.created_at AS run_created_at, "
            "t.seq, t.ts, t.type, t.actor, t.data "
            "FROM runs r LEFT JOIN trace_events t "
            "ON r.tenant_id = t.tenant_id AND r.run_id = t.run_id "
            "WHERE r.kind = 'research' "
            "ORDER BY r.created_at ASC, r.run_id ASC, t.seq ASC"
        ).fetchall()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (str(row["tenant_id"]), str(row["run_id"]))
        if row["seq"] is None:
            grouped.setdefault(key, [])
            continue
        grouped[key].append(
            {
                "seq": int(row["seq"]),
                "ts": row["ts"],
                "type": row["type"],
                "actor": _loads(row["actor"], None),
                "data": _loads(row["data"], {}),
            }
        )
    return grouped


def usage_signals_for_user(platform: Any, tenant_id: str, user_id: str) -> dict[str, Any]:
    """Return only the usage-derived context for one signed-in user."""
    all_events = _events_by_research_run(platform)
    sessions: list[dict[str, Any]] = []
    tool_counts: Counter[str] = Counter()
    widget_counts: Counter[str] = Counter()
    warning_count = 0
    event_count = 0

    for (row_tenant, run_id), events in all_events.items():
        if row_tenant != str(tenant_id):
            continue
        actor = _session_actor(events)
        if actor is None or actor[1] != str(user_id):
            continue
        event_count += len(events)
        for event in events:
            if event.get("type") == "tool_call":
                name = _event_tool_name(event)
                if name:
                    tool_counts[name] += 1
            widget = _event_widget_hint(event)
            if widget:
                widget_counts[widget] += 1
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            warnings = data.get("warnings")
            if isinstance(warnings, list):
                warning_count += len(warnings)
        sessions.append(
            {
                "run_id": run_id,
                "opened_at": events[0]["ts"] if events else None,
                "event_count": len(events),
                "tool_calls": sum(1 for event in events if event.get("type") == "tool_call"),
            }
        )

    sessions.sort(key=lambda item: item.get("opened_at") or "", reverse=True)
    return {
        "tenant_id": str(tenant_id),
        "user_id": str(user_id),
        "session_count": len(sessions),
        "event_count": event_count,
        "recent_sessions": sessions[:12],
        "top_tools": [{"name": name, "count": count} for name, count in tool_counts.most_common(20)],
        "top_widgets": [
            {"name": name, "count": count} for name, count in widget_counts.most_common(20)
        ],
        "warning_count": warning_count,
    }


def all_users_with_session_history(platform: Any) -> list[dict[str, str]]:
    users: dict[tuple[str, str], dict[str, str]] = {}
    for (tenant_id, _run_id), events in _events_by_research_run(platform).items():
        actor = _session_actor(events)
        if actor is None:
            continue
        user_id = actor[1]
        users[(tenant_id, user_id)] = {"tenant_id": tenant_id, "user_id": user_id}
    return sorted(users.values(), key=lambda row: (row["tenant_id"], row["user_id"]))


def user_has_session_history(platform: Any, tenant_id: str, user_id: str) -> bool:
    return usage_signals_for_user(platform, tenant_id, user_id)["session_count"] > 0


def default_adaptive_dashboard_spec() -> dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_ADAPTIVE_DASHBOARD_SPEC))


def _prompt(signals: dict[str, Any]) -> str:
    contract = {
        "summary": "Short explanation of the user's dashboard pattern.",
        "widgets": [
            {
                "id": "performance_pnl",
                "title": "Performance",
                "priority": 1,
                "layout": {"x": 0, "y": 0, "w": 6, "h": 3},
                "reason": "Why this widget fits the user's usage.",
            }
        ],
    }
    return (
        "You are generating a Ithaca adaptive dashboard layout. Return strict JSON only, "
        "with no markdown, prose, comments, or trailing text.\n\n"
        f"Allowed widget ids: {json.dumps(list(ADAPTIVE_WIDGET_IDS))}\n\n"
        "Rules:\n"
        "- Use only the allowed widget ids.\n"
        "- Choose 4 to 8 widgets.\n"
        "- Use a 12-column grid. x >= 0, y >= 0, w >= 1, h >= 1, and x + w <= 12.\n"
        "- priority is an integer where 1 is most important.\n"
        "- Do not invent widgets, component names, code, URLs, secrets, or market data.\n\n"
        f"Required JSON shape: {json.dumps(contract)}\n\n"
        f"Usage context: {json.dumps(signals, separators=(',', ':'))}"
    )


def _extract_json_text(text: str, *, provider: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise DashboardGenerationError(f"{provider} returned empty dashboard output")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DashboardGenerationError(f"{provider} returned invalid JSON") from exc
    try:
        return validate_adaptive_dashboard_spec(raw)
    except AdaptiveDashboardSpecError as exc:
        raise DashboardGenerationError(str(exc)) from exc


def _openai_message_text(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if isinstance(part.get("text"), str):
                parts.append(part["text"])
            elif isinstance(part.get("content"), str):
                parts.append(part["content"])
        return "\n".join(parts)
    return ""


class OpenAICompatibleDashboardClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = DEFAULT_OPENAI_COMPATIBLE_MODEL,
        auth_mode: str = "bearer",
        modal_key: str | None = None,
        modal_secret: str | None = None,
        timeout_s: float = 20.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get(
            "ITHACA_ADAPTIVE_DASHBOARD_API_KEY", ""
        )
        self.modal_key = modal_key if modal_key is not None else os.environ.get(
            "ITHACA_ADAPTIVE_DASHBOARD_MODAL_KEY", ""
        )
        self.modal_secret = modal_secret if modal_secret is not None else os.environ.get(
            "ITHACA_ADAPTIVE_DASHBOARD_MODAL_SECRET", ""
        )
        configured_base_url = (
            base_url
            if base_url is not None
            else os.environ.get("ITHACA_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL", "")
        )
        self.base_url = configured_base_url.rstrip("/")
        self.model = os.environ.get("ITHACA_ADAPTIVE_DASHBOARD_MODEL", model)
        self.auth_mode = auth_mode
        self.timeout_s = float(timeout_s)

    def generate(self, signals: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url:
            raise DashboardGenerationError(
                "ITHACA_ADAPTIVE_DASHBOARD_OPENAI_BASE_URL is not configured"
            )
        headers = {"content-type": "application/json"}
        if self.auth_mode == "modal-proxy":
            if not self.modal_key:
                raise DashboardGenerationError(
                    "ITHACA_ADAPTIVE_DASHBOARD_MODAL_KEY is not configured"
                )
            if not self.modal_secret:
                raise DashboardGenerationError(
                    "ITHACA_ADAPTIVE_DASHBOARD_MODAL_SECRET is not configured"
                )
            headers["Modal-Key"] = self.modal_key
            headers["Modal-Secret"] = self.modal_secret
        else:
            if not self.api_key:
                raise DashboardGenerationError(
                    "ITHACA_ADAPTIVE_DASHBOARD_API_KEY is not configured"
                )
            headers["authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 1200,
            "messages": [{"role": "user", "content": _prompt(signals)}],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise DashboardGenerationError(f"Dashboard model request failed: {exc}") from exc
        choices = payload.get("choices")
        message = choices[0].get("message") if isinstance(choices, list) and choices else {}
        return _extract_json_text(_openai_message_text(message), provider="Dashboard model")


class AnthropicDashboardClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = ANTHROPIC_HAIKU_MODEL,
        timeout_s: float = 20.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.timeout_s = float(timeout_s)

    def generate(self, signals: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise AnthropicDashboardError("ANTHROPIC_API_KEY is not configured")
        body = {
            "model": self.model,
            "max_tokens": 1200,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": _prompt(signals)}],
        }
        request = urllib.request.Request(
            ANTHROPIC_MESSAGES_URL,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_VERSION,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise AnthropicDashboardError(f"Anthropic request failed: {exc}") from exc
        text_parts = [
            part.get("text", "")
            for part in payload.get("content", [])
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        try:
            return _extract_json_text("\n".join(part for part in text_parts if part), provider="Anthropic")
        except DashboardGenerationError as exc:
            raise AnthropicDashboardError(str(exc)) from exc


def create_adaptive_dashboard_client() -> Any:
    provider = os.environ.get(
        "ITHACA_ADAPTIVE_DASHBOARD_PROVIDER",
        DEFAULT_ADAPTIVE_DASHBOARD_PROVIDER,
    ).strip().lower()
    if provider in {"modal", "modal-openai"}:
        return OpenAICompatibleDashboardClient(auth_mode="modal-proxy")
    if provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleDashboardClient()
    if provider == "anthropic":
        return AnthropicDashboardClient()
    raise DashboardGenerationError(f"Unsupported adaptive dashboard provider: {provider}")


def recompute_user_profile(
    platform: Any,
    tenant_id: str,
    user_id: str,
    *,
    client: Any | None = None,
    generated_for_date: date | str | None = None,
) -> dict[str, Any] | None:
    signals = usage_signals_for_user(platform, tenant_id, user_id)
    if signals["session_count"] < 1:
        return None
    generator = client or create_adaptive_dashboard_client()
    spec = generator.generate(signals)
    model = getattr(generator, "model", DEFAULT_OPENAI_COMPATIBLE_MODEL)
    return platform.adaptive_dashboards.upsert(
        tenant_id,
        user_id,
        spec,
        model=model,
        source_session_count=int(signals["session_count"]),
        source_event_count=int(signals["event_count"]),
        generated_for_date=generated_for_date or _utc_now().date(),
    )


class AdaptiveDashboardWorker:
    def __init__(
        self,
        platform: Any,
        *,
        client: Any | None = None,
        owner_id: str | None = None,
        lease_ttl_seconds: float = 90000.0,
    ) -> None:
        self.platform = platform
        self.client = client or create_adaptive_dashboard_client()
        self.owner_id = owner_id or process_owner("adaptive-dashboard")
        self.lease_ttl_seconds = float(lease_ttl_seconds)
        self._last_daily_run: str | None = None

    def poll_once(self, *, now: datetime | None = None, force: bool = False) -> dict[str, Any]:
        now_dt = now or _utc_now()
        day = now_dt.date().isoformat()
        if not force and (now_dt.hour != 0 or now_dt.minute != 0):
            return {"status": "skipped", "reason": "not-midnight-utc", "date": day}
        if not force and self._last_daily_run == day:
            return {"status": "skipped", "reason": "already-ran", "date": day}
        lease_name = f"adaptive-dashboard-daily-{day}"
        if not acquire_loop_lease(
            self.platform,
            lease_name=lease_name,
            owner_id=self.owner_id,
            ttl_seconds=self.lease_ttl_seconds,
            role="adaptive-dashboard",
        ):
            return {"status": "skipped", "reason": "lease-held", "date": day}

        result = self.recompute_all(generated_for_date=day)
        self._last_daily_run = day
        return {"status": "ran", "date": day, **result}

    def recompute_all(self, *, generated_for_date: date | str | None = None) -> dict[str, Any]:
        users = all_users_with_session_history(self.platform)
        updated: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for user in users:
            try:
                profile = recompute_user_profile(
                    self.platform,
                    user["tenant_id"],
                    user["user_id"],
                    client=self.client,
                    generated_for_date=generated_for_date,
                )
                if profile is not None:
                    updated.append(
                        {
                            "tenant_id": profile["tenant_id"],
                            "user_id": profile["user_id"],
                            "generated_for_date": profile["generated_for_date"],
                        }
                    )
            except Exception as exc:  # keep the daily job going for other users
                failed.append(
                    {
                        "tenant_id": user["tenant_id"],
                        "user_id": user["user_id"],
                        "error": str(exc),
                    }
                )
        return {
            "considered": len(users),
            "updated": updated,
            "failed": failed,
        }
