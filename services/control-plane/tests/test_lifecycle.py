"""Paper deployment lifecycle endpoints: activate/pause/resume/retire (human-gated)."""

from __future__ import annotations

from conftest import agent_headers, human_headers, valid_spec


def _promoted_paper(client, tenant) -> str:
    sid = client.post("/strategies", json={"spec": valid_spec()},
                      headers=human_headers(tenant)).json()["id"]
    run_id = client.post("/runs", json={"strategy_id": sid, "kind": "paper", "range": "1y"},
                         headers=human_headers(tenant)).json()["run_id"]
    client.post(f"/runs/{run_id}/promote", headers=human_headers(tenant))
    return run_id


def test_full_lifecycle_promote_activate_pause_resume_retire(client, platform, tenant_a):
    run_id = _promoted_paper(client, tenant_a)

    assert client.post(f"/runs/{run_id}/activate", headers=human_headers(tenant_a)).json()["state"] == "live"
    assert client.post(f"/runs/{run_id}/pause", headers=human_headers(tenant_a)).json()["state"] == "paused"
    assert client.post(f"/runs/{run_id}/resume", headers=human_headers(tenant_a)).json()["state"] == "live"
    assert client.post(f"/runs/{run_id}/retire", headers=human_headers(tenant_a)).json()["state"] == "retired"
    assert platform.runs.get(tenant_a, run_id)["state"] == "retired"


def test_activate_requires_human(client, platform, tenant_a):
    run_id = _promoted_paper(client, tenant_a)
    resp = client.post(f"/runs/{run_id}/activate", headers=agent_headers(tenant_a))
    assert resp.status_code == 403
    assert platform.runs.get(tenant_a, run_id)["state"] == "promoted"  # unchanged
    assert "denial" in [e["type"] for e in platform.traces.events(tenant_a, run_id)]


def test_pause_illegal_from_promoted(client, tenant_a):
    run_id = _promoted_paper(client, tenant_a)  # promoted, not live
    resp = client.post(f"/runs/{run_id}/pause", headers=human_headers(tenant_a))
    assert resp.status_code == 409


def test_activate_missing_run_404(client, tenant_a):
    import uuid
    resp = client.post(f"/runs/{uuid.uuid4()}/activate", headers=human_headers(tenant_a))
    assert resp.status_code == 404


def test_lifecycle_tenant_isolation(client, tenant_a, tenant_b):
    run_id = _promoted_paper(client, tenant_a)
    resp = client.post(f"/runs/{run_id}/activate", headers=human_headers(tenant_b))
    assert resp.status_code == 404  # tenant B cannot see/act on A's run
