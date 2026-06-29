"""Research session creation: prompt capture + tenant scoping."""

from __future__ import annotations


def _bearer(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def _clerk_session(client, clerk_auth, email="founder@sessions.test", name="Founder"):
    token = clerk_auth(email=email, name=name)
    r = client.get("/api/auth/me", headers=_bearer(token))
    assert r.status_code == 200, r.text
    body = r.json()
    return token, body["tenantId"], body["id"]


def test_create_session_captures_prompt_for_dev_tenant(client, stores, tenant_a):
    resp = client.post(
        "/api/sessions",
        json={"prompt": "what does nvda look like", "title": "NVDA scan"},
        headers={"X-Tenant-Id": tenant_a},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "research"
    assert body["state"] == "running"
    assert body["tenant_id"] == tenant_a

    events = stores.trace.events(tenant_a, body["id"])
    assert [e["type"] for e in events] == ["session_open"]
    assert events[0]["data"]["prompt"] == "what does nvda look like"
    assert events[0]["data"]["title"] == "NVDA scan"
    assert events[0]["actor"] == {"kind": "user", "id": "ui"}


def test_create_session_uses_signed_in_users_tenant(client, clerk_auth):
    token, tenant_id, user_id = _clerk_session(client, clerk_auth)

    resp = client.post(
        "/api/sessions",
        json={"prompt": "screen semis with unusual volume"},
        headers=_bearer(token),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tenant_id"] == tenant_id
    event = body["events"][0]
    assert event["actor"] == {"kind": "user", "id": user_id}
    assert event["data"]["prompt"] == "screen semis with unusual volume"


def test_signed_in_event_stream_uses_one_time_ticket(client, clerk_auth):
    token, tenant_id, _user_id = _clerk_session(client, clerk_auth, email="stream@sessions.test")
    created = client.post(
        "/api/sessions",
        json={"prompt": "stream this session"},
        headers=_bearer(token),
    ).json()

    minted = client.post(
        f"/api/runs/{created['id']}/events-ticket",
        json={},
        headers=_bearer(token),
    )
    assert minted.status_code == 201, minted.text
    ticket = minted.json()["sse_ticket"]

    resp = client.get(
        f"/api/runs/{created['id']}/events",
        params={"sse_ticket": ticket, "replay_only": "1", "deadline": "0"},
    )

    assert resp.status_code == 200, resp.text
    assert "stream this session" in resp.text
    assert tenant_id in resp.text

    replay = client.get(
        f"/api/runs/{created['id']}/events",
        params={"sse_ticket": ticket, "replay_only": "1", "deadline": "0"},
    )
    assert replay.status_code == 401


def test_signed_in_event_stream_rejects_query_access_token(client, clerk_auth):
    token, _tenant_id, _user_id = _clerk_session(
        client, clerk_auth, email="query-token@sessions.test"
    )
    created = client.post(
        "/api/sessions",
        json={"prompt": "do not leak token in url"},
        headers=_bearer(token),
    ).json()

    resp = client.get(
        f"/api/runs/{created['id']}/events",
        params={"access_token": token, "replay_only": "1", "deadline": "0"},
    )

    assert resp.status_code == 401
    assert "events-ticket" in resp.json()["detail"]


def test_create_session_can_start_realtime_without_prompt(client, stores, tenant_a):
    resp = client.post("/api/sessions", json={"prompt": "  "}, headers={"X-Tenant-Id": tenant_a})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    events = stores.trace.events(tenant_a, body["id"])
    assert "title" not in events[0]["data"]
    assert "prompt" not in events[0]["data"]


def test_create_session_dev_tenant_fallback_disabled_in_prod(client, monkeypatch, tenant_a):
    monkeypatch.setenv("DOOMBERG_ENV", "prod")

    resp = client.post(
        "/api/sessions",
        json={"prompt": "should require auth"},
        headers={"X-Tenant-Id": tenant_a},
    )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "authentication required"


def test_create_session_dev_tenant_fallback_disabled_when_env_missing(
    client, monkeypatch, tenant_a
):
    monkeypatch.delenv("DOOMBERG_ENV", raising=False)

    resp = client.post(
        "/api/sessions",
        json={"prompt": "should require auth"},
        params={"tenant_id": tenant_a},
    )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "authentication required"
