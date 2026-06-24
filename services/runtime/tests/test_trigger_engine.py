"""Trigger engine: active policies evaluate live quotes and create durable runs."""

from __future__ import annotations

import datetime as dt

from doomberg_runtime import StaticQuoteClient, TriggerEngine, TriggerJobWorker


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


def _quote(now, *, price=950, entitlement_class="connected_account"):
    return {
        "symbol": "NVDA",
        "price": price,
        "as_of": now.isoformat(),
        "received_time": now.isoformat(),
        "source": "ibkr-engine",
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
                    "source": "ibkr-engine",
                    "entitlement_class": "connected_account",
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
    assert run["result"]["provenance"]["source"] == "ibkr-engine"
    types = [event["type"] for event in durable_platform.trace.events(tenant, run_id)]
    assert types == ["trigger_fired", "tool_call", "tool_result", "run_transition"]
    assert durable_platform.triggers.latest_firing(
        tenant, trigger["trigger_id"], dedupe_key="NVDA"
    )["run_id"] == run_id

    second = engine.poll_once(now=now + dt.timedelta(minutes=5))

    assert second["fired"] == []
    assert second["skipped"][0]["reason"] == "COOLDOWN"


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
                    "source": "ibkr-engine",
                    "entitlement_class": "connected_account",
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
