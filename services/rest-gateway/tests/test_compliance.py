from __future__ import annotations


def _headers(tenant_id: str, *, actor_kind: str = "user") -> dict[str, str]:
    return {
        "X-Tenant-Id": tenant_id,
        "X-Actor-Kind": actor_kind,
        "X-Actor-Id": "compliance-user",
    }


def _spec(name: str, symbols: list[str]) -> dict:
    return {
        "spec_version": "1.0",
        "name": name,
        "universe": {"symbols": symbols, "source": "prices"},
        "strategy": {"id": "momentum", "params": {"lookback": 60, "top": 2}},
        "construction": {"scheme": "equal_weight", "long_only": True, "gross": 1.0},
        "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.5},
        "execution": {"cost_bps": 5.0, "algo": "vwap", "rebalance": "weekly@close"},
        "seed": 42,
    }


def test_compliance_kill_switch_is_live_tenant_state(client, tenant_a, tenant_b):
    initial = client.get("/api/compliance", headers=_headers(tenant_a))
    assert initial.status_code == 200, initial.text
    assert initial.json()["killSwitch"] is False
    assert initial.json()["killSource"] == "none"

    engaged = client.post(
        "/api/compliance/kill-switch",
        json={"on": True, "reason": "compliance halt", "expect_version": 0},
        headers=_headers(tenant_a),
    )
    assert engaged.status_code == 200, engaged.text
    body = engaged.json()
    assert body["killSwitch"] is True
    assert body["killReason"] == "compliance halt"
    assert body["killSource"] == "tenant"
    assert body["killVersion"] == 1
    assert body["audit"][0]["decision"] == "blocked"

    released = client.post(
        "/api/compliance/kill-switch",
        json={"on": False, "reason": "cleared", "expect_version": body["killVersion"]},
        headers=_headers(tenant_a),
    )
    assert released.status_code == 200, released.text
    assert released.json()["killSwitch"] is False
    assert released.json()["killVersion"] == 2

    reengaged = client.post(
        "/api/compliance/kill-switch",
        json={"on": True, "reason": "again", "expect_version": released.json()["killVersion"]},
        headers=_headers(tenant_a),
    )
    assert reengaged.status_code == 200, reengaged.text
    assert reengaged.json()["killVersion"] == 3

    other = client.get("/api/compliance", headers=_headers(tenant_b)).json()
    assert other["killSwitch"] is False
    assert other["audit"] == []


def test_compliance_kill_switch_rejects_agents_and_stale_writes(client, tenant_a):
    agent = client.post(
        "/api/compliance/kill-switch",
        json={"on": True, "expect_version": 0},
        headers=_headers(tenant_a, actor_kind="agent"),
    )
    assert agent.status_code == 403

    first = client.post(
        "/api/compliance/kill-switch",
        json={"on": True, "expect_version": 0},
        headers=_headers(tenant_a),
    )
    assert first.status_code == 200
    stale = client.post(
        "/api/compliance/kill-switch",
        json={"on": False, "expect_version": 0},
        headers=_headers(tenant_a),
    )
    assert stale.status_code == 409


def test_compliance_includes_global_kill_switch_audit(client, stores, tenant_a):
    stores.execution_controls.set_global(
        enabled=True,
        reason="site incident",
        actor_id="site-admin",
        expect_version=0,
    )

    body = client.get("/api/compliance", headers=_headers(tenant_a)).json()
    assert body["killSource"] == "global"
    assert body["audit"][0]["scope"] == "global"
    assert body["audit"][0]["summary"] == "site incident"


def test_compliance_policy_edits_are_durable_versioned_and_tenant_scoped(
    client, tenant_a, tenant_b
):
    initial = client.get("/api/compliance", headers=_headers(tenant_a)).json()
    assert initial["policyConfigured"] is False
    assert initial["policyVersion"] == 0
    assert initial["limitsEnforced"] is False

    restricted = client.post(
        "/api/compliance/restricted",
        json={"symbol": "tsla", "expect_version": 0},
        headers=_headers(tenant_a),
    )
    assert restricted.status_code == 200, restricted.text
    assert restricted.json()["policyConfigured"] is True
    assert restricted.json()["policyVersion"] == 1
    assert restricted.json()["limitsEnforced"] is False
    assert "TSLA" in restricted.json()["restricted"]

    watch = client.post(
        "/api/compliance/watch",
        json={"symbol": "nvda", "expect_version": 1},
        headers=_headers(tenant_a),
    )
    assert watch.status_code == 200, watch.text
    assert watch.json()["policyVersion"] == 2
    assert watch.json()["watch"] == ["NVDA"]

    limits = client.post(
        "/api/compliance/limits",
        json={
            "limits": {
                "maxPositionPct": 30,
                "maxNetPct": 100,
                "maxLeverage": 1.5,
                "maxConcentrationPct": 100,
            },
            "expect_version": 2,
        },
        headers=_headers(tenant_a),
    )
    assert limits.status_code == 200, limits.text
    assert limits.json()["policyVersion"] == 3
    assert limits.json()["limitsEnforced"] is True
    assert limits.json()["limits"]["maxPositionPct"] == 30
    assert limits.json()["audit"][0]["action"] == "Firm limits updated"

    stale = client.request(
        "DELETE",
        "/api/compliance/watch/NVDA",
        json={"expect_version": 1},
        headers=_headers(tenant_a),
    )
    assert stale.status_code == 409

    removed = client.request(
        "DELETE",
        "/api/compliance/watch/NVDA",
        json={"expect_version": 3},
        headers=_headers(tenant_a),
    )
    assert removed.status_code == 200
    assert removed.json()["policyVersion"] == 4
    assert removed.json()["watch"] == []

    unrestricted = client.request(
        "DELETE",
        "/api/compliance/restricted/TSLA",
        json={"expect_version": 4},
        headers=_headers(tenant_a),
    )
    assert unrestricted.status_code == 200
    assert unrestricted.json()["policyVersion"] == 5
    assert "TSLA" not in unrestricted.json()["restricted"]

    other = client.get("/api/compliance", headers=_headers(tenant_b)).json()
    assert other["policyVersion"] == 0
    assert "TSLA" not in other["restricted"]


def test_compliance_policy_rejects_agents_invalid_symbols_limits_and_stale_writes(
    client, tenant_a
):
    agent = client.post(
        "/api/compliance/restricted",
        json={"symbol": "TSLA", "expect_version": 0},
        headers=_headers(tenant_a, actor_kind="agent"),
    )
    assert agent.status_code == 403

    invalid_symbol = client.post(
        "/api/compliance/watch",
        json={"symbol": "../secret", "expect_version": 0},
        headers=_headers(tenant_a),
    )
    assert invalid_symbol.status_code == 422

    missing_version = client.post(
        "/api/compliance/restricted",
        json={"symbol": "TSLA"},
        headers=_headers(tenant_a),
    )
    assert missing_version.status_code == 422

    missing_limit = client.post(
        "/api/compliance/limits",
        json={"limits": {"maxPositionPct": 10}, "expect_version": 0},
        headers=_headers(tenant_a),
    )
    assert missing_limit.status_code == 422

    out_of_range = client.post(
        "/api/compliance/limits",
        json={
            "limits": {
                "maxPositionPct": 101,
                "maxNetPct": 100,
                "maxLeverage": 1,
                "maxConcentrationPct": 100,
            },
            "expect_version": 0,
        },
        headers=_headers(tenant_a),
    )
    assert out_of_range.status_code == 422

    unknown_limit = client.post(
        "/api/compliance/limits",
        json={
            "limits": {
                "maxPositionPct": 10,
                "maxNetPct": 100,
                "maxLeverage": 1,
                "maxConcentrationPct": 100,
                "maxDailyLossPct": 5,
            },
            "expect_version": 0,
        },
        headers=_headers(tenant_a),
    )
    assert unknown_limit.status_code == 422


def test_compliance_policy_read_requires_data_scope(client, stores):
    tenant = stores.auth.create_tenant("no compliance read")
    key, _ = stores.auth.mint_key(tenant, ["strategy:author"])
    response = client.get(
        "/api/compliance",
        headers={"Authorization": f"Bearer {key}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "missing required scope: data:read"


def test_compliance_check_uses_saved_policy_and_current_kill_switch(client, stores, tenant_a):
    strategy = stores.strategies.create(tenant_a, _spec("Restricted Tesla", ["AAPL", "TSLA"]))
    saved = client.post(
        "/api/compliance/restricted",
        json={"symbol": "TSLA", "expect_version": 0},
        headers=_headers(tenant_a),
    )
    assert saved.status_code == 200

    checked = client.post(
        "/api/compliance/check",
        json={"strategy_id": strategy["id"]},
        headers=_headers(tenant_a),
    )
    assert checked.status_code == 200, checked.text
    result = checked.json()["check"]
    assert result["blocked"] is True
    assert result["restricted"] == ["TSLA"]
    assert result["limitsEnforced"] is False

    stores.execution_controls.set_tenant(
        tenant_a,
        enabled=True,
        reason="operator halt",
        actor_id="operator",
        expect_version=0,
    )
    halted = client.post(
        "/api/compliance/check",
        json={"strategy_id": strategy["id"]},
        headers=_headers(tenant_a),
    ).json()["check"]
    assert halted["killSwitch"] is True
    assert any("Kill switch" in violation for violation in halted["violations"])
