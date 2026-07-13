from __future__ import annotations

from datetime import datetime, timezone

from rest_helpers import seed_run


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-Id": tenant_id}


def _succeed(stores, tenant_id: str, run_id: str) -> None:
    for state in ("queued", "running", "succeeded"):
        run = stores.runs.get(tenant_id, run_id)
        stores.runs.transition(tenant_id, run_id, state, expect=run["version"])


def test_dashboard_endpoints_return_explicit_empty_contracts(client, tenant_a):
    for path in (
        "/api/dashboard/summary",
        "/api/dashboard/risk",
        "/api/dashboard/activity",
        "/api/dashboard/market",
        "/api/providers/status",
    ):
        response = client.get(path, headers=_headers(tenant_a))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "empty"
        assert body["as_of"] is None
        assert body["freshness_ms"] is None
        assert body["error"] is None
        assert isinstance(body["data"], dict)


def test_dashboard_summary_uses_only_tenant_backtest_evidence(client, stores, tenant_a, tenant_b):
    run_id = seed_run(stores, tenant_a, kind="backtest")
    stores.runs.set_result(
        tenant_a,
        run_id,
        {
            "data": {
                "equityCurve": [{"d": "2026-07-01", "v": 100}, {"d": "2026-07-02", "v": 103}],
                "stats": {"sharpe": 1.25, "vol": 0.12},
            }
        },
    )
    _succeed(stores, tenant_a, run_id)
    other_id = seed_run(stores, tenant_b, kind="backtest")
    stores.runs.set_result(tenant_b, other_id, {"data": {"stats": {"sharpe": 99}}})

    body = client.get("/api/dashboard/summary", headers=_headers(tenant_a)).json()

    assert body["status"] in {"ready", "stale"}
    assert body["source"] == "doomberg-platform"
    assert body["data"]["run_counts"]["total"] == 1
    assert body["data"]["latest_backtest"]["run_id"] == run_id
    assert body["data"]["latest_backtest"]["stats"] == {"sharpe": 1.25, "vol": 0.12}
    assert body["data"]["latest_backtest"]["stats"]["sharpe"] != 99


def test_dashboard_active_count_excludes_drafts_and_terminal_runs(client, stores, tenant_a):
    seed_run(stores, tenant_a, kind="research")
    queued_id = seed_run(stores, tenant_a, kind="backtest")
    queued = stores.runs.get(tenant_a, queued_id)
    stores.runs.transition(tenant_a, queued_id, "queued", expect=queued["version"])
    succeeded_id = seed_run(stores, tenant_a, kind="backtest")
    _succeed(stores, tenant_a, succeeded_id)

    body = client.get("/api/dashboard/summary", headers=_headers(tenant_a)).json()

    assert body["data"]["run_counts"]["total"] == 3
    assert body["data"]["run_counts"]["active"] == 1


def test_dashboard_summary_uses_latest_run_that_has_real_evidence(client, stores, tenant_a):
    evidence_id = seed_run(stores, tenant_a, kind="backtest")
    stores.runs.set_result(
        tenant_a,
        evidence_id,
        {"data": {"equityCurve": [{"d": "2026-07-01", "v": 100}], "stats": {}}},
    )
    _succeed(stores, tenant_a, evidence_id)
    seed_run(stores, tenant_a, kind="backtest")

    body = client.get("/api/dashboard/summary", headers=_headers(tenant_a)).json()

    assert body["data"]["latest_backtest"]["run_id"] == evidence_id


def test_dashboard_risk_does_not_invent_missing_metrics(client, stores, tenant_a):
    first_id = seed_run(stores, tenant_a, kind="backtest")
    stores.runs.set_result(
        tenant_a,
        first_id,
        {"data": {"stats": {"sharpe": 1.1, "totalReturn": 12.0}}},
    )
    _succeed(stores, tenant_a, first_id)

    body = client.get("/api/dashboard/risk", headers=_headers(tenant_a)).json()

    assert body["data"]["backtest"] == {"run_id": first_id, "metrics": {"sharpe": 1.1}}
    assert "totalReturn" not in str(body)
    assert "var95" not in str(body)


def test_dashboard_rejects_malformed_run_metrics(client, stores, tenant_a):
    run_id = seed_run(stores, tenant_a, kind="backtest")
    stores.runs.set_result(
        tenant_a,
        run_id,
        {
            "data": {
                "equityCurve": [
                    {"d": "2026-07-01", "v": 100},
                    {"d": "bad", "v": "not-a-number"},
                    {"v": 101},
                ],
                "stats": {"sharpe": 1.2, "vol": "high", "enabled": True},
                "risk": {"var95": -1.4, "beta": {"unexpected": "object"}},
            }
        },
    )
    _succeed(stores, tenant_a, run_id)

    summary = client.get("/api/dashboard/summary", headers=_headers(tenant_a)).json()
    risk = client.get("/api/dashboard/risk", headers=_headers(tenant_a)).json()

    assert summary["data"]["latest_backtest"]["equity_curve"] == [{"d": "2026-07-01", "v": 100}]
    assert summary["data"]["latest_backtest"]["stats"] == {"sharpe": 1.2}
    assert risk["data"]["backtest"]["metrics"] == {"sharpe": 1.2, "var95": -1.4}


def test_dashboard_bounds_large_equity_curves(client, stores, tenant_a):
    run_id = seed_run(stores, tenant_a, kind="backtest")
    curve = [{"d": f"point-{index}", "v": index} for index in range(5_000)]
    stores.runs.set_result(tenant_a, run_id, {"data": {"equityCurve": curve, "stats": {}}})
    _succeed(stores, tenant_a, run_id)

    body = client.get("/api/dashboard/summary", headers=_headers(tenant_a)).json()
    returned = body["data"]["latest_backtest"]["equity_curve"]

    assert len(returned) <= 1_000
    assert returned[0] == curve[0]
    assert returned[-1] == curve[-1]


def test_dashboard_ignores_newer_nonterminal_backtest_evidence(client, stores, tenant_a):
    completed_id = seed_run(stores, tenant_a, kind="backtest")
    stores.runs.set_result(
        tenant_a,
        completed_id,
        {"data": {"stats": {"sharpe": 1.2}, "equityCurve": []}},
    )
    _succeed(stores, tenant_a, completed_id)
    partial_id = seed_run(stores, tenant_a, kind="backtest")
    stores.runs.set_result(tenant_a, partial_id, {"data": {"stats": {"sharpe": 99}}})

    summary = client.get("/api/dashboard/summary", headers=_headers(tenant_a)).json()

    assert summary["data"]["latest_backtest"]["run_id"] == completed_id
    assert summary["data"]["latest_backtest"]["stats"]["sharpe"] == 1.2


def test_newer_empty_paper_run_does_not_hide_existing_exposure(client, stores, tenant_a):
    invested_id = seed_run(stores, tenant_a, kind="paper")
    stores.books.ensure(tenant_a, invested_id, capital=10_000)
    stores.books.apply(tenant_a, invested_id, target_weights={"AAPL": 0.5})
    seed_run(stores, tenant_a, kind="paper")

    risk = client.get("/api/dashboard/risk", headers=_headers(tenant_a)).json()

    assert risk["data"]["paper_exposure"]["run_id"] == invested_id
    assert risk["data"]["paper_exposure"]["weights"] == {"AAPL": 0.5}


def test_corrupt_paper_book_returns_stable_unavailable_contract(client, stores, tenant_a):
    run_id = seed_run(stores, tenant_a, kind="paper")
    stores.books.ensure(tenant_a, run_id, capital=10_000)
    with stores.db.write_lock:
        with stores.db.conn as conn:
            conn.execute(
                "UPDATE books SET weights = ? WHERE tenant_id = ? AND run_id = ?",
                ("not-json", tenant_a, run_id),
            )

    risk = client.get("/api/dashboard/risk", headers=_headers(tenant_a)).json()

    assert risk["status"] == "unavailable"
    assert risk["error"]["code"] == "PAPER_BOOK_INVALID"


def test_dashboard_risk_exposes_real_paper_book(client, stores, tenant_a):
    run_id = seed_run(stores, tenant_a, kind="paper")
    stores.books.ensure(tenant_a, run_id, capital=50_000)
    stores.books.apply(
        tenant_a,
        run_id,
        target_weights={"AAPL": 0.3, "MSFT": -0.1},
        marks={"AAPL": 210, "MSFT": 490},
    )

    body = client.get("/api/dashboard/risk", headers=_headers(tenant_a)).json()

    assert body["data"]["paper_exposure"]["weights"] == {"AAPL": 0.3, "MSFT": -0.1}
    assert body["data"]["paper_exposure"]["gross"] == 0.4
    assert body["data"]["paper_exposure"]["cash"] == 30_000


def test_activity_is_tenant_scoped_and_limit_is_enforced(client, stores, tenant_a, tenant_b):
    first_id = seed_run(stores, tenant_a, kind="research")
    second_id = seed_run(stores, tenant_a, kind="backtest")
    seed_run(stores, tenant_b, kind="research")
    stores.notifications.enqueue(
        tenant_a,
        event_type="run.warning",
        subject_type="run",
        subject_id=second_id,
        payload={"message": "review"},
    )

    response = client.get("/api/dashboard/activity?limit=1", headers=_headers(tenant_a))
    body = response.json()

    assert response.status_code == 200
    assert len(body["data"]["runs"]) == 1
    assert body["data"]["runs"][0]["run_id"] in {first_id, second_id}
    assert len(body["data"]["alerts"]) == 1
    assert tenant_b not in str(body)


def test_market_and_provider_status_redact_private_connection_details(
    client, stores, tenant_a, monkeypatch
):
    monkeypatch.setenv("DOOMBERG_IBKR_ENGINE_URL", "https://private-engine.example")
    stores.providers.upsert_connection(
        tenant_a,
        provider="ibkr",
        capabilities=["quotes", " orders ", "TRADING"],
        entitlements=[{"dataset": "us_equities", "entitlement_class": "connected_account"}],
        account_ref="U123456",
        credential_ref="secret://tenant/ibkr",
        retention_policy="tenant-default",
    )
    stores.providers.create_snapshot(
        tenant_a,
        provider="ibkr",
        dataset="prices",
        entitlement_class="connected_account",
        as_of="2026-07-12T00:00:00Z",
        uri="https://objects.example/snapshot?token=secret",
        manifest={"account_ref": "U123456", "credential": "secret"},
    )

    provider = client.get("/api/providers/status", headers=_headers(tenant_a)).json()
    market = client.get("/api/dashboard/market", headers=_headers(tenant_a)).json()
    legacy_provider = client.get("/api/providers", headers=_headers(tenant_a)).json()
    serialized = str({"provider": provider, "market": market})

    assert provider["data"]["counts"] == {"total": 1, "connected": 1}
    assert provider["data"]["connections"][0]["provider"] == "doomberg-live-data"
    assert provider["data"]["connections"][0]["capabilities"] == ["quotes"]
    assert provider["data"]["connections"][0]["credential_configured"] is True
    assert market["data"]["quote_providers"][0]["provider"] == "doomberg-live-data"
    assert legacy_provider["connections"][0]["tenant_id"] == tenant_a
    assert legacy_provider["connections"][0]["retention_policy"] == "tenant-default"
    assert market["data"]["snapshots"][0] == {
        "snapshot_id": market["data"]["snapshots"][0]["snapshot_id"],
        "provider": "doomberg-live-data",
        "dataset": "prices",
        "entitlement_class": "doomberg_live",
        "as_of": "2026-07-12T00:00:00Z",
        "created_at": market["data"]["snapshots"][0]["created_at"],
    }
    assert "U123456" not in serialized
    assert "secret://" not in serialized
    assert "orders" not in serialized
    assert "TRADING" not in serialized
    assert "private-engine.example" not in serialized
    assert "objects.example" not in serialized
    assert "?token=secret" not in serialized
    assert "'credential': 'secret'" not in serialized


def test_dashboard_routes_enforce_api_key_read_scopes(client, stores):
    tenant_id = stores.auth.create_tenant("dashboard-scope-test")
    unrelated_key, _ = stores.auth.mint_key(tenant_id, ["strategy:author"])
    data_key, _ = stores.auth.mint_key(tenant_id, ["data:read"])
    full_read_key, _ = stores.auth.mint_key(
        tenant_id,
        ["data:read", "triggers:read", "alerts:read"],
    )

    for path in (
        "/api/dashboard/summary",
        "/api/dashboard/risk",
        "/api/dashboard/activity",
        "/api/dashboard/market",
        "/api/providers/status",
    ):
        response = client.get(path, headers={"Authorization": f"Bearer {unrelated_key}"})
        assert response.status_code == 403, (path, response.text)

    activity = client.get(
        "/api/dashboard/activity",
        headers={"Authorization": f"Bearer {data_key}"},
    )
    assert activity.status_code == 403
    assert activity.json()["detail"] == "missing required scope: triggers:read"

    allowed = client.get(
        "/api/dashboard/activity",
        headers={"Authorization": f"Bearer {full_read_key}"},
    )
    assert allowed.status_code == 200


def test_market_reports_configured_but_unregistered_source(client, tenant_a, monkeypatch):
    monkeypatch.setenv("DOOMBERG_IBKR_ENGINE_URL", "https://private-engine.example")

    body = client.get("/api/dashboard/market", headers=_headers(tenant_a)).json()

    assert body["status"] == "unavailable"
    assert body["error"]["code"] == "MARKET_DATA_NOT_REGISTERED"
    assert "private-engine.example" not in str(body)


def test_market_freshness_uses_observation_time_not_connection_time(
    client, stores, tenant_a, monkeypatch
):
    monkeypatch.setenv("DOOMBERG_DASHBOARD_STALE_AFTER_MS", "60000")
    stores.providers.upsert_connection(
        tenant_a,
        provider="community",
        capabilities=["quotes"],
    )
    stores.providers.create_snapshot(
        tenant_a,
        provider="community",
        dataset="prices",
        entitlement_class="public_delayed",
        as_of="2020-01-01T00:00:00+00:00",
        manifest={},
    )

    body = client.get("/api/dashboard/market", headers=_headers(tenant_a)).json()

    assert body["status"] == "stale"
    assert body["as_of"] == "2020-01-01T00:00:00+00:00"


def test_connected_provider_without_observation_is_unavailable(client, stores, tenant_a):
    stores.providers.upsert_connection(
        tenant_a,
        provider="community",
        capabilities=["quotes"],
    )

    body = client.get("/api/dashboard/market", headers=_headers(tenant_a)).json()

    assert body["status"] == "unavailable"
    assert body["as_of"] is None
    assert body["error"]["code"] == "MARKET_OBSERVATION_UNAVAILABLE"


def test_dashboard_contract_marks_old_data_stale(client, stores, tenant_a, monkeypatch):
    monkeypatch.setenv("DOOMBERG_DASHBOARD_STALE_AFTER_MS", "60000")
    run_id = seed_run(stores, tenant_a, kind="research")
    old = "2020-01-01T00:00:00+00:00"
    with stores.db.write_lock:
        with stores.db.conn as conn:
            conn.execute(
                "UPDATE runs SET created_at = ?, updated_at = ? WHERE tenant_id = ? AND run_id = ?",
                (old, old, tenant_a, run_id),
            )

    body = client.get("/api/dashboard/summary", headers=_headers(tenant_a)).json()

    assert body["status"] == "stale"
    assert body["as_of"] == old
    assert body["freshness_ms"] > 60_000
    assert datetime.fromisoformat(body["as_of"]).tzinfo == timezone.utc


def test_dashboard_openapi_contract_is_typed(client):
    schema = client.get("/openapi.json").json()
    response = schema["paths"]["/api/dashboard/summary"]["get"]["responses"]["200"]
    response_schema = response["content"]["application/json"]["schema"]

    assert response_schema["$ref"].endswith("DashboardEnvelope_DashboardSummaryData_")
    envelope = schema["components"]["schemas"]["DashboardEnvelope_DashboardSummaryData_"]
    assert set(envelope["required"]) == {
        "status",
        "as_of",
        "source",
        "entitlement_class",
        "freshness_ms",
        "data",
        "error",
    }
