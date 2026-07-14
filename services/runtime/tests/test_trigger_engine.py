"""Trigger engine: active policies evaluate live quotes and create durable runs."""

from __future__ import annotations

import datetime as dt
import threading
import time
import urllib.error

from ithaca_runtime import (
    NotificationDispatcher,
    StaticQuoteClient,
    TriggerEngine,
    TriggerJobWorker,
    webhook_signature,
)
from ithaca_runtime.notifications import PermanentDeliveryError, WebhookAdapter


def _policy(*, cooldown="20m", require_live=True, approval_required=False):
    return {
        "when": {"event": "price.threshold", "universe": ["NVDA"]},
        "condition": {
            "all": [
                {"price": {"gte": 900}},
                {"data_freshness_seconds": {"lte": 10}},
            ]
        },
        "controls": {
            "dedupe_key": "${symbol}",
            "cooldown": cooldown,
            "max_runs_per_day": 8,
            "require_connected_live_data": require_live,
            "approval_required": approval_required,
        },
        "action": {"run_skill": "market.quote", "mode": "analyze"},
    }


def _quote(now, *, price=950, entitlement_class="ithaca_live"):
    return {
        "symbol": "NVDA",
        "price": price,
        "as_of": now.isoformat(),
        "received_time": now.isoformat(),
        "source": "ithaca-live-data",
        "entitlement_class": entitlement_class,
    }


def _active_trigger(platform, tenant_id, policy):
    trigger = platform.triggers.create(
        tenant_id,
        name="nvda-live-review",
        policy=policy,
        state="active",
    )
    return trigger


def test_trigger_engine_fires_quote_run_and_cooldown_blocks_repeat(durable_platform, tenant_id):
    tenant = durable_platform.auth.create_tenant("trigger tenant")
    now = dt.datetime(2026, 6, 24, 13, 30, tzinfo=dt.timezone.utc)
    trigger = _active_trigger(durable_platform, tenant, _policy())
    engine = TriggerEngine(
        durable_platform,
        quote_client=StaticQuoteClient(
            {
                "NVDA": {
                    "symbol": "NVDA",
                    "price": 950,
                    "as_of": now.isoformat(),
                    "received_time": now.isoformat(),
                    "source": "ithaca-live-data",
                    "entitlement_class": "ithaca_live",
                }
            }
        ),
    )

    first = engine.poll_once(now=now)

    assert first["evaluated"] == 1
    assert first["fired"][0]["trigger_id"] == trigger["trigger_id"]
    run_id = first["fired"][0]["run_id"]
    run = durable_platform.runs.get(tenant, run_id)
    assert run["kind"] == "trigger"
    assert run["state"] == "succeeded"
    assert run["result"]["data"]["symbol"] == "NVDA"
    assert run["result"]["provenance"]["source"] == "ithaca-live-data"
    types = [event["type"] for event in durable_platform.trace.events(tenant, run_id)]
    assert types == [
        "trigger_fired",
        "tool_call",
        "tool_result",
        "run_transition",
        "notification_queued",
    ]
    assert (
        durable_platform.triggers.latest_firing(tenant, trigger["trigger_id"], dedupe_key="NVDA")[
            "run_id"
        ]
        == run_id
    )
    alerts = durable_platform.notifications.list(tenant)
    assert len(alerts) == 1
    assert alerts[0]["event_type"] == "trigger.fired"
    assert alerts[0]["payload"]["run_id"] == run_id

    second = engine.poll_once(now=now + dt.timedelta(minutes=5))

    assert second["fired"] == []
    assert second["skipped"][0]["reason"] == "COOLDOWN"


def test_trigger_engine_fires_percent_change_from_previous_close(durable_platform, tenant_id):
    tenant = durable_platform.auth.create_tenant("trigger tenant")
    now = dt.datetime(2026, 6, 24, 13, 30, tzinfo=dt.timezone.utc)
    policy = _policy(cooldown="0s")
    policy["when"] = {
        "event": "market.quote",
        "universe": ["NVDA"],
        "baseline": {"type": "previous_close"},
    }
    policy["condition"] = {"change_pct": {"lte": -2.0}}
    policy["controls"]["dedupe_key"] = "${symbol}:${trading_day}:down2"
    trigger = _active_trigger(durable_platform, tenant, policy)

    engine = TriggerEngine(
        durable_platform,
        quote_client=StaticQuoteClient(
            {
                "NVDA": {
                    "symbol": "NVDA",
                    "price": 97.99,
                    "previous_close": 100,
                    "as_of": now.isoformat(),
                    "received_time": now.isoformat(),
                    "source": "ithaca-live-data",
                    "entitlement_class": "ithaca_live",
                }
            }
        ),
    )

    result = engine.poll_once(now=now)

    assert result["fired"][0]["trigger_id"] == trigger["trigger_id"]
    firing = durable_platform.triggers.list_firings(tenant)[0]
    ctx = firing["payload"]["context"]
    assert ctx["baseline_price"] == 100
    assert ctx["change_pct"] < -2.0
    assert ctx["dedupe_key"] if "dedupe_key" in ctx else True
    alert = durable_platform.notifications.list(tenant)[0]
    assert alert["payload"]["change_pct"] < -2.0


def test_trigger_engine_percent_change_does_not_fire_above_threshold(durable_platform, tenant_id):
    tenant = durable_platform.auth.create_tenant("trigger tenant")
    now = dt.datetime(2026, 6, 24, 13, 30, tzinfo=dt.timezone.utc)
    policy = _policy(cooldown="0s")
    policy["when"] = {
        "event": "market.quote",
        "universe": ["NVDA"],
        "baseline": {"type": "previous_close"},
    }
    policy["condition"] = {"change_pct": {"lte": -2.0}}
    _active_trigger(durable_platform, tenant, policy)
    engine = TriggerEngine(
        durable_platform,
        quote_client=StaticQuoteClient(
            {
                "NVDA": {
                    "symbol": "NVDA",
                    "price": 98.01,
                    "previous_close": 100,
                    "as_of": now.isoformat(),
                    "received_time": now.isoformat(),
                    "source": "ithaca-live-data",
                    "entitlement_class": "ithaca_live",
                }
            }
        ),
    )

    result = engine.poll_once(now=now)

    assert result["fired"] == []
    assert result["skipped"][0]["reason"] == "CONDITION_FALSE"
    assert durable_platform.notifications.list(tenant) == []


def test_trigger_engine_run_forever_requires_leadership(durable_platform, monkeypatch):
    tenant = durable_platform.auth.create_tenant("trigger tenant")
    now = dt.datetime(2026, 6, 24, 13, 30, tzinfo=dt.timezone.utc)
    _active_trigger(durable_platform, tenant, _policy(cooldown="9999d"))
    quote_client = StaticQuoteClient({"NVDA": _quote(now)})
    monkeypatch.setenv("ITHACA_TRIGGER_LEASE_TTL_S", "30")

    assert durable_platform.leases.acquire("trigger-engine", "owner-1", ttl_seconds=30) is not None
    blocked = TriggerEngine(durable_platform, quote_client=quote_client, worker_id="owner-2")
    stop = threading.Event()
    blocked_thread = threading.Thread(
        target=blocked.run_forever,
        kwargs={"interval_s": 0.01, "stop": stop},
        daemon=True,
    )
    blocked_thread.start()
    time.sleep(0.05)
    stop.set()
    blocked_thread.join(timeout=1)

    assert durable_platform.triggers.list_firings(tenant) == []

    assert durable_platform.leases.release("trigger-engine", "owner-1") is True
    leader = TriggerEngine(durable_platform, quote_client=quote_client, worker_id="owner-2")
    stop = threading.Event()
    leader_thread = threading.Thread(
        target=leader.run_forever,
        kwargs={"interval_s": 0.01, "stop": stop},
        daemon=True,
    )
    leader_thread.start()
    for _ in range(50):
        if durable_platform.triggers.list_firings(tenant):
            break
        time.sleep(0.01)
    stop.set()
    leader_thread.join(timeout=1)

    assert len(durable_platform.triggers.list_firings(tenant)) == 1
    assert durable_platform.leases.get("trigger-engine") is None


def test_trigger_engine_requires_connected_live_data_when_policy_says_so(
    durable_platform, tenant_id
):
    tenant = durable_platform.auth.create_tenant("trigger tenant")
    now = dt.datetime(2026, 6, 24, 13, 30, tzinfo=dt.timezone.utc)
    _active_trigger(durable_platform, tenant, _policy(require_live=True))
    engine = TriggerEngine(
        durable_platform,
        quote_client=StaticQuoteClient(
            {
                "NVDA": {
                    "symbol": "NVDA",
                    "price": 950,
                    "as_of": now.isoformat(),
                    "received_time": now.isoformat(),
                    "source": "community",
                    "entitlement_class": "public_delayed",
                }
            }
        ),
    )

    result = engine.poll_once(now=now)

    assert result["fired"] == []
    assert result["skipped"][0]["reason"] == "ENTITLEMENT_REQUIRED"


def test_trigger_dry_run_predicts_fire_without_side_effects(durable_platform, tenant_id):
    tenant = durable_platform.auth.create_tenant("trigger tenant")
    now = dt.datetime(2026, 6, 24, 13, 30, tzinfo=dt.timezone.utc)
    trigger = {
        "tenant_id": tenant,
        "trigger_id": "dry-nvda",
        "name": "dry-run",
        "state": "draft",
        "policy": _policy(cooldown="0s"),
    }
    engine = TriggerEngine(durable_platform)

    result = engine.dry_run(trigger, now=now, quote=_quote(now))

    assert result["dry_run"] is True
    assert result["would_fire"] is True
    assert result["reason"] == "WOULD_FIRE"
    assert result["would_create"] == {
        "run": True,
        "job": False,
        "approval": False,
        "broker_order": False,
    }
    assert result["context"]["symbol"] == "NVDA"
    assert result["context"]["entitlement_class"] == "ithaca_live"
    assert durable_platform.runs.list(tenant) == []
    assert durable_platform.jobs.list(tenant) == []
    assert durable_platform.approvals.list(tenant) == []
    assert durable_platform.triggers.list_firings(tenant) == []


def test_trigger_dry_run_reports_controls_block_without_writes(durable_platform, tenant_id):
    tenant = durable_platform.auth.create_tenant("trigger tenant")
    now = dt.datetime(2026, 6, 24, 13, 30, tzinfo=dt.timezone.utc)
    trigger = {
        "tenant_id": tenant,
        "trigger_id": "dry-nvda",
        "name": "dry-run",
        "state": "draft",
        "policy": _policy(cooldown="0s", require_live=True),
    }
    engine = TriggerEngine(durable_platform)

    result = engine.dry_run(
        trigger,
        now=now,
        quote=_quote(now, entitlement_class="public_delayed"),
    )

    assert result["dry_run"] is True
    assert result["would_fire"] is False
    assert result["reason"] == "ENTITLEMENT_REQUIRED"
    assert result["would_create"]["run"] is False
    assert durable_platform.runs.list(tenant) == []
    assert durable_platform.triggers.list_firings(tenant) == []


def test_trigger_engine_rejects_unknown_condition_operator(durable_platform, tenant_id):
    tenant = durable_platform.auth.create_tenant("trigger tenant")
    now = dt.datetime(2026, 6, 24, 13, 30, tzinfo=dt.timezone.utc)
    policy = _policy(cooldown="0s")
    policy["condition"] = {"price": {"gteq": 900}}
    trigger = _active_trigger(durable_platform, tenant, policy)
    engine = TriggerEngine(
        durable_platform,
        quote_client=StaticQuoteClient({"NVDA": _quote(now)}),
    )

    result = engine.poll_once(now=now)

    assert result["fired"] == []
    assert result["errors"][0]["trigger_id"] == trigger["trigger_id"]
    assert result["errors"][0]["error"] == "TriggerEvaluationError"
    assert "unsupported condition operator" in result["errors"][0]["detail"]


def test_trigger_engine_supports_combined_numeric_bounds(durable_platform, tenant_id):
    tenant = durable_platform.auth.create_tenant("trigger tenant")
    now = dt.datetime(2026, 6, 24, 13, 30, tzinfo=dt.timezone.utc)
    policy = _policy(cooldown="0s")
    policy["condition"] = {"price": {"gte": 900, "lte": 1000}}
    trigger = _active_trigger(durable_platform, tenant, policy)
    engine = TriggerEngine(
        durable_platform,
        quote_client=StaticQuoteClient({"NVDA": _quote(now)}),
    )

    result = engine.poll_once(now=now)

    assert result["errors"] == []
    assert result["fired"][0]["trigger_id"] == trigger["trigger_id"]


def test_trigger_engine_creates_approval_when_requested(durable_platform, tenant_id):
    tenant = durable_platform.auth.create_tenant("trigger tenant")
    now = dt.datetime(2026, 6, 24, 13, 30, tzinfo=dt.timezone.utc)
    _active_trigger(durable_platform, tenant, _policy(approval_required=True, cooldown="0s"))
    engine = TriggerEngine(
        durable_platform,
        quote_client=StaticQuoteClient(
            {
                "NVDA": {
                    "symbol": "NVDA",
                    "price": 950,
                    "as_of": now.isoformat(),
                    "received_time": now.isoformat(),
                    "source": "ithaca-live-data",
                    "entitlement_class": "ithaca_live",
                }
            }
        ),
    )

    result = engine.poll_once(now=now)

    approval_id = result["fired"][0]["approval_id"]
    assert approval_id
    approvals = durable_platform.approvals.list_pending(tenant)
    assert approvals[0]["approval_id"] == approval_id
    assert approvals[0]["request"]["trigger_id"]


def test_trigger_job_worker_completes_non_quote_trigger_action(durable_platform, core):
    tenant = durable_platform.auth.create_tenant("trigger tenant")
    now = dt.datetime(2026, 6, 24, 13, 30, tzinfo=dt.timezone.utc)
    policy = _policy(cooldown="0s")
    policy["action"] = {
        "run_skill": "options.greeks",
        "mode": "analyze",
        "input": {"S": 100, "K": 100, "T": 0.5, "r": 0.04, "sigma": 0.25, "type": "call"},
    }
    _active_trigger(durable_platform, tenant, policy)
    engine = TriggerEngine(
        durable_platform,
        quote_client=StaticQuoteClient({"NVDA": _quote(now)}),
    )

    fired = engine.poll_once(now=now)

    run_id = fired["fired"][0]["run_id"]
    run = durable_platform.runs.get(tenant, run_id)
    assert run["state"] == "queued"
    jobs = durable_platform.jobs.list_by_run(tenant, run_id)
    assert jobs[0]["kind"] == "trigger"

    result = TriggerJobWorker(durable_platform, core).poll_once()

    assert result["succeeded"] == [run_id]
    run = durable_platform.runs.get(tenant, run_id)
    assert run["state"] == "succeeded"
    assert run["result"]["provenance"]["source"] == "computed"
    assert durable_platform.jobs.list_by_run(tenant, run_id)[0]["state"] == "succeeded"


def test_notification_dispatcher_marks_implicit_ui_delivery_sent(durable_platform, tenant_id):
    tenant = durable_platform.auth.create_tenant("trigger tenant")
    alert = durable_platform.notifications.enqueue(
        tenant,
        event_type="trigger.fired",
        subject_type="trigger_firing",
        subject_id="fir_1",
        priority="high",
        payload={"channels": ["ithaca_ui"], "symbol": "NVDA"},
    )

    result = NotificationDispatcher(durable_platform).poll_once()

    assert result["delivered"] == [alert["notification_id"]]
    updated = durable_platform.notifications.get(tenant, alert["notification_id"])
    assert updated["state"] == "sent"
    attempts = durable_platform.notifications.list_attempts(tenant, alert["notification_id"])
    assert attempts[0]["target_id"] == "ithaca_ui:implicit"
    assert attempts[0]["state"] == "succeeded"


def test_webhook_signature_is_stable():
    body = b'{"type":"trigger.fired"}'
    sig = webhook_signature("secret", "2026-06-24T13:30:00+00:00", body)
    assert sig.startswith("hmac-sha256=")
    assert sig == webhook_signature("secret", "2026-06-24T13:30:00+00:00", body)


def test_webhook_delivery_rejects_private_targets(monkeypatch):
    monkeypatch.setenv("ITHACA_ENV", "prod")
    adapter = WebhookAdapter()
    notification = {
        "event_type": "trigger.fired",
        "notification_id": "notif_1",
        "priority": "high",
        "created_at": "2026-06-24T13:30:00+00:00",
        "payload": {},
    }
    target = {
        "config": {"url": "http://127.0.0.1:8080/hook", "hmac_secret": "secret"},
        "secret_ref": None,
    }

    try:
        adapter.deliver(notification, target)
    except PermanentDeliveryError as exc:
        assert "HTTPS" in str(exc) or "public address" in str(exc)
    else:
        raise AssertionError("private webhook target should be rejected before network I/O")


def test_webhook_delivery_rejects_public_http_targets(monkeypatch):
    monkeypatch.setenv("ITHACA_ENV", "prod")
    adapter = WebhookAdapter()
    notification = {
        "event_type": "trigger.fired",
        "notification_id": "notif_1",
        "priority": "high",
        "created_at": "2026-06-24T13:30:00+00:00",
        "payload": {},
    }
    target = {
        "config": {"url": "http://example.com/hook", "hmac_secret": "secret"},
        "secret_ref": None,
    }

    try:
        adapter.deliver(notification, target)
    except PermanentDeliveryError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("public webhook target should require HTTPS")


def test_webhook_delivery_rejects_userinfo(monkeypatch):
    monkeypatch.setenv("ITHACA_ENV", "prod")
    adapter = WebhookAdapter()
    notification = {
        "event_type": "trigger.fired",
        "notification_id": "notif_1",
        "priority": "high",
        "created_at": "2026-06-24T13:30:00+00:00",
        "payload": {},
    }
    target = {
        "config": {"url": "https://user:pass@example.com/hook", "hmac_secret": "secret"},
        "secret_ref": None,
    }

    try:
        adapter.deliver(notification, target)
    except PermanentDeliveryError as exc:
        assert "userinfo" in str(exc)
    else:
        raise AssertionError("webhook target with userinfo should be rejected")


def test_webhook_delivery_rejects_redirects(monkeypatch):
    monkeypatch.setenv("ITHACA_ENV", "prod")
    adapter = WebhookAdapter()
    notification = {
        "event_type": "trigger.fired",
        "notification_id": "notif_1",
        "priority": "high",
        "created_at": "2026-06-24T13:30:00+00:00",
        "payload": {},
    }
    target = {
        "config": {"url": "https://example.com/hook", "hmac_secret": "secret"},
        "secret_ref": None,
    }

    class FakeRedirectOpener:
        def open(self, req, timeout):
            raise urllib.error.HTTPError(
                req.full_url,
                302,
                "Found",
                {"Location": "http://127.0.0.1:8080/hook"},
                None,
            )

    adapter._opener = FakeRedirectOpener()

    try:
        adapter.deliver(notification, target)
    except PermanentDeliveryError as exc:
        assert "redirect" in str(exc).lower()
    else:
        raise AssertionError("webhook redirects should be rejected")


def test_private_webhook_targets_require_local_explicit_opt_in(monkeypatch, local_server):
    monkeypatch.setenv("ITHACA_ENV", "test")
    monkeypatch.setenv("ITHACA_ALLOW_PRIVATE_WEBHOOKS", "1")
    adapter = WebhookAdapter()
    notification = {
        "event_type": "trigger.fired",
        "notification_id": "notif_1",
        "priority": "high",
        "created_at": "2026-06-24T13:30:00+00:00",
        "payload": {},
    }
    target = {
        "config": {"url": local_server.url, "hmac_secret": "secret"},
        "secret_ref": None,
        "kind": "webhook",
        "target_id": "local",
    }

    delivered = adapter.deliver(notification, target)

    assert delivered["status"] == 200
    assert local_server.requests[0]["headers"]["X-Ithaca-Signature"].startswith("hmac-sha256=")
