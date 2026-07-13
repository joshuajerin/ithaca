"""Endpoint tests for the control plane via FastAPI TestClient."""
from __future__ import annotations

import uuid

from control_helpers import agent_headers, human_headers, valid_spec
from doomberg_platform import TransitionConflict


# ----------------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------------
def _propose(client, tenant_id, spec=None, *, actor="human"):
    headers = human_headers(tenant_id) if actor == "human" else agent_headers(tenant_id)
    return client.post("/strategies", json={"spec": spec or valid_spec()}, headers=headers)


def _create_run(client, tenant_id, strategy_id, kind="paper", *, actor="human"):
    headers = human_headers(tenant_id) if actor == "human" else agent_headers(tenant_id)
    return client.post(
        "/runs",
        json={"strategy_id": strategy_id, "kind": kind, "range": "1y"},
        headers=headers,
    )


# ----------------------------------------------------------------------------------------
# propose
# ----------------------------------------------------------------------------------------
def test_propose_persists_draft_and_emits_event(client, platform, tenant_a):
    resp = _propose(client, tenant_a)
    assert resp.status_code == 201
    body = resp.json()
    assert body["state"] == "draft"
    assert body["version"] == 1
    strategy_id = body["id"]

    # Persisted under the tenant.
    stored = platform.strategies.get(tenant_a, strategy_id)
    assert stored is not None
    assert stored["spec"]["tenant_id"] == tenant_a  # server-stamped
    assert stored["spec"]["id"] == strategy_id

    # strategy_proposed trace event was emitted.
    run_id = body["trace"]["run_id"]
    events = platform.traces.events(tenant_a, run_id)
    assert len(events) == 1
    assert events[0]["type"] == "strategy_proposed"
    assert events[0]["data"]["strategy_id"] == strategy_id
    assert events[0]["seq"] == 0


def test_propose_rejects_invalid_spec_and_emits_denial(client, platform, tenant_a):
    bad = valid_spec()
    bad["construction"]["gross"] = 99.0  # > 4.0 max => closed-schema violation
    resp = _propose(client, tenant_a, bad)
    assert resp.status_code == 422
    # Nothing persisted.
    assert platform.strategies.list(tenant_a) == []


def test_propose_rejects_smuggled_freeform_field(client, tenant_a):
    bad = valid_spec()
    bad["custom_code"] = "import os; os.system('rm -rf /')"  # extra=forbid
    resp = _propose(client, tenant_a, bad)
    assert resp.status_code == 422


def test_propose_requires_tenant_header(client):
    resp = client.post("/strategies", json={"spec": valid_spec()})
    assert resp.status_code == 401


def test_propose_rejects_non_uuid_tenant(client):
    resp = client.post(
        "/strategies", json={"spec": valid_spec()},
        headers={"X-Tenant-Id": "not-a-uuid", "X-Actor-Kind": "human"},
    )
    assert resp.status_code == 400


# ----------------------------------------------------------------------------------------
# create run
# ----------------------------------------------------------------------------------------
def test_create_run_returns_queued(client, tenant_a):
    sid = _propose(client, tenant_a).json()["id"]
    resp = _create_run(client, tenant_a, sid, kind="backtest")
    assert resp.status_code == 201
    body = resp.json()
    assert body["state"] == "queued"
    assert body["kind"] == "backtest"
    assert body["job_id"]
    assert body["profile"] == "backtest"
    assert uuid.UUID(body["run_id"])  # valid UUID


def test_create_run_unknown_strategy_404(client, tenant_a):
    resp = _create_run(client, tenant_a, str(uuid.uuid4()))
    assert resp.status_code == 404


def test_create_run_emits_transition_trace(client, platform, tenant_a):
    sid = _propose(client, tenant_a).json()["id"]
    body = _create_run(client, tenant_a, sid, kind="paper").json()
    run_id = body["run_id"]
    assert platform.jobs.get(tenant_a, body["job_id"])["run_id"] == run_id
    events = platform.traces.events(tenant_a, run_id)
    assert [e["type"] for e in events] == ["run_transition"]
    assert events[0]["data"]["to"] == "queued"


def test_cancel_run_cancels_run_and_job(client, platform, tenant_a):
    sid = _propose(client, tenant_a).json()["id"]
    body = _create_run(client, tenant_a, sid, kind="backtest").json()
    resp = client.post(
        f"/runs/{body['run_id']}/cancel",
        json={"reason": "user requested"},
        headers=human_headers(tenant_a),
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "cancelled"
    assert platform.runs.get(tenant_a, body["run_id"])["state"] == "cancelled"
    assert platform.jobs.get(tenant_a, body["job_id"])["state"] == "cancelled"


def test_cancel_run_retries_if_worker_advances_version(client, platform, tenant_a, monkeypatch):
    sid = _propose(client, tenant_a).json()["id"]
    body = _create_run(client, tenant_a, sid, kind="backtest").json()
    original_cancel = platform.runs.cancel
    raced = {"done": False}

    def racing_cancel(tenant_id, run_id, *, expect=None):
        if not raced["done"]:
            raced["done"] = True
            platform.runs.transition(tenant_id, run_id, "running", expect=expect)
            raise TransitionConflict("version mismatch: expected 1, found 2")
        return original_cancel(tenant_id, run_id, expect=expect)

    monkeypatch.setattr(platform.runs, "cancel", racing_cancel)

    resp = client.post(
        f"/runs/{body['run_id']}/cancel",
        json={"reason": "launch gate cleanup"},
        headers=human_headers(tenant_a),
    )

    assert resp.status_code == 200
    assert resp.json()["state"] == "cancelled"
    assert platform.runs.get(tenant_a, body["run_id"])["state"] == "cancelled"
    assert platform.jobs.get(tenant_a, body["job_id"])["state"] == "cancelled"


# ----------------------------------------------------------------------------------------
# promote — the money-path authority + gate
# ----------------------------------------------------------------------------------------
def test_promote_blocked_without_human_actor(client, platform, tenant_a):
    sid = _propose(client, tenant_a).json()["id"]
    run_id = _create_run(client, tenant_a, sid, kind="paper").json()["run_id"]
    resp = client.post(f"/runs/{run_id}/promote", headers=agent_headers(tenant_a))
    assert resp.status_code == 403
    # State unchanged; denial emitted.
    assert platform.runs.get(tenant_a, run_id)["state"] == "queued"
    types = [e["type"] for e in platform.traces.events(tenant_a, run_id)]
    assert "denial" in types


def test_promote_human_passes_gate(client, platform, tenant_a):
    sid = _propose(client, tenant_a).json()["id"]
    run_id = _create_run(client, tenant_a, sid, kind="paper").json()["run_id"]
    resp = client.post(f"/runs/{run_id}/promote", headers=human_headers(tenant_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "promoted"
    assert body["gate"]["ok"] is True
    assert platform.runs.get(tenant_a, run_id)["state"] == "promoted"
    # A run_transition to promoted was traced.
    types = [e["type"] for e in platform.traces.events(tenant_a, run_id)]
    assert types[-1] == "run_transition"


def test_promote_blocked_for_backtest_kind(client, tenant_a):
    sid = _propose(client, tenant_a).json()["id"]
    run_id = _create_run(client, tenant_a, sid, kind="backtest").json()["run_id"]
    resp = client.post(f"/runs/{run_id}/promote", headers=human_headers(tenant_a))
    assert resp.status_code == 409


def test_promote_blocked_by_restricted_name(client, platform, tenant_a):
    spec = valid_spec(name="Restricted Book", symbols=["AAPL", "GME"])
    sid = _propose(client, tenant_a, spec).json()["id"]
    run_id = _create_run(client, tenant_a, sid, kind="paper").json()["run_id"]
    resp = client.post(f"/runs/{run_id}/promote", headers=human_headers(tenant_a))
    assert resp.status_code == 409
    assert "GME" in resp.json()["detail"]["gate"]["restricted"]
    # Not promoted; denial traced.
    assert platform.runs.get(tenant_a, run_id)["state"] != "promoted"
    types = [e["type"] for e in platform.traces.events(tenant_a, run_id)]
    assert "denial" in types


def test_promote_uses_saved_tenant_compliance_policy(client, platform, tenant_a):
    platform.compliance_policies.set(
        tenant_a,
        limits={
            "maxPositionPct": 100.0,
            "maxNetPct": 1_000.0,
            "maxLeverage": 10.0,
            "maxConcentrationPct": 100.0,
        },
        limits_enforced=False,
        restricted=["TSLA"],
        watch=[],
        action="Custom restricted list",
        actor_id="risk-officer",
        expect_version=0,
    )
    spec = valid_spec(name="Tenant Restricted", symbols=["AAPL", "TSLA"])
    sid = _propose(client, tenant_a, spec).json()["id"]
    run_id = _create_run(client, tenant_a, sid, kind="paper").json()["run_id"]

    response = client.post(f"/runs/{run_id}/promote", headers=human_headers(tenant_a))

    assert response.status_code == 409
    assert response.json()["detail"]["gate"]["restricted"] == ["TSLA"]
    assert platform.runs.get(tenant_a, run_id)["state"] == "queued"


def test_promote_enforces_saved_firm_limits(client, platform, tenant_a):
    platform.compliance_policies.set(
        tenant_a,
        limits={
            "maxPositionPct": 20.0,
            "maxNetPct": 120.0,
            "maxLeverage": 2.0,
            "maxConcentrationPct": 100.0,
        },
        limits_enforced=True,
        restricted=[],
        watch=[],
        action="Strict firm limits",
        actor_id="risk-officer",
        expect_version=0,
    )
    sid = _propose(client, tenant_a, valid_spec(name="Firm Limit Breach")).json()["id"]
    run_id = _create_run(client, tenant_a, sid, kind="paper").json()["run_id"]
    response = client.post(f"/runs/{run_id}/promote", headers=human_headers(tenant_a))
    assert response.status_code == 409
    assert any(
        "Firm max position" in violation
        for violation in response.json()["detail"]["gate"]["violations"]
    )


def test_promote_watch_only_policy_warns_without_activating_limits(
    client, platform, tenant_a
):
    platform.compliance_policies.set(
        tenant_a,
        limits={
            "maxPositionPct": 15.0,
            "maxNetPct": 120.0,
            "maxLeverage": 2.0,
            "maxConcentrationPct": 50.0,
        },
        limits_enforced=False,
        restricted=[],
        watch=["AAPL"],
        action="Watch only",
        actor_id="risk-officer",
        expect_version=0,
    )
    sid = _propose(client, tenant_a, valid_spec(name="Watched Strategy")).json()["id"]
    run_id = _create_run(client, tenant_a, sid, kind="paper").json()["run_id"]
    response = client.post(f"/runs/{run_id}/promote", headers=human_headers(tenant_a))
    assert response.status_code == 200
    assert any("Watch-list" in warning for warning in response.json()["gate"]["warnings"])


def test_promote_missing_run_404(client, tenant_a):
    resp = client.post(f"/runs/{uuid.uuid4()}/promote", headers=human_headers(tenant_a))
    assert resp.status_code == 404


# ----------------------------------------------------------------------------------------
# reads + tenant isolation
# ----------------------------------------------------------------------------------------
def test_get_run_and_list(client, tenant_a):
    sid = _propose(client, tenant_a).json()["id"]
    run_id = _create_run(client, tenant_a, sid, kind="paper").json()["run_id"]

    got = client.get(f"/runs/{run_id}", headers=human_headers(tenant_a))
    assert got.status_code == 200
    assert got.json()["run_id"] == run_id

    listed = client.get("/runs", headers=human_headers(tenant_a))
    assert listed.status_code == 200
    assert [r["run_id"] for r in listed.json()["runs"]] == [run_id]


def test_list_runs_filter_by_kind(client, tenant_a):
    sid = _propose(client, tenant_a).json()["id"]
    _create_run(client, tenant_a, sid, kind="paper")
    _create_run(client, tenant_a, sid, kind="backtest")
    paper = client.get("/runs?kind=paper", headers=human_headers(tenant_a)).json()["runs"]
    assert len(paper) == 1
    assert paper[0]["kind"] == "paper"


def test_tenant_isolation_run_not_visible_cross_tenant(client, tenant_a, tenant_b):
    sid = _propose(client, tenant_a).json()["id"]
    run_id = _create_run(client, tenant_a, sid, kind="paper").json()["run_id"]

    # Tenant B cannot fetch tenant A's run.
    resp = client.get(f"/runs/{run_id}", headers=human_headers(tenant_b))
    assert resp.status_code == 404
    # And it does not appear in B's list.
    assert client.get("/runs", headers=human_headers(tenant_b)).json()["runs"] == []


def test_tenant_isolation_cannot_create_run_on_other_tenant_strategy(client, tenant_a, tenant_b):
    sid = _propose(client, tenant_a).json()["id"]
    # Tenant B references A's strategy id -> not found for B.
    resp = _create_run(client, tenant_b, sid, kind="paper")
    assert resp.status_code == 404


def test_tenant_isolation_cannot_promote_other_tenant_run(client, tenant_a, tenant_b):
    sid = _propose(client, tenant_a).json()["id"]
    run_id = _create_run(client, tenant_a, sid, kind="paper").json()["run_id"]
    resp = client.post(f"/runs/{run_id}/promote", headers=human_headers(tenant_b))
    assert resp.status_code == 404


def test_strategy_versioning_same_name_bumps_version(client, tenant_a):
    spec = valid_spec(name="Same Name")
    first = _propose(client, tenant_a, spec).json()
    second = _propose(client, tenant_a, spec).json()
    assert first["id"] == second["id"]
    assert first["version"] == 1
    assert second["version"] == 2
