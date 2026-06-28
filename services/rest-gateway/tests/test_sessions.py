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
    token, _tenant_id, _user_id = _clerk_session(client, clerk_auth, email="query-token@sessions.test")
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


def test_seed_demo_creates_replayable_research_session(client, stores, tenant_a):
    """The Welcome landing's first-glimpse: seeding a demo session on demand."""
    resp = client.post("/api/sessions/seed-demo", headers={"X-Tenant-Id": tenant_a})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "research"
    assert body["state"] == "succeeded"
    assert body["tenant_id"] == tenant_a

    events = stores.trace.events(tenant_a, body["id"])
    assert events[0]["type"] == "session_open"
    assert events[-1]["type"] == "session_close"
    # Gap-free seq (the replay scrubber walks this).
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(len(seqs)))


def test_seed_demo_is_idempotent(client, stores, tenant_a):
    """Seeding twice does not create a second demo session."""
    r1 = client.post("/api/sessions/seed-demo", headers={"X-Tenant-Id": tenant_a})
    r2 = client.post("/api/sessions/seed-demo", headers={"X-Tenant-Id": tenant_a})
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
