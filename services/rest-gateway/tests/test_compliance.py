from __future__ import annotations


def _headers(tenant_id: str, *, actor_kind: str = "user") -> dict[str, str]:
    return {
        "X-Tenant-Id": tenant_id,
        "X-Actor-Kind": actor_kind,
        "X-Actor-Id": "compliance-user",
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
