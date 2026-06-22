"""Research session creation: prompt capture + tenant scoping."""

from __future__ import annotations


def _bearer(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def _signup(client, email="founder@sessions.test", name="Founder", password="hunter2hunter2"):
    r = client.post("/api/auth/signup", json={"email": email, "name": name, "password": password})
    assert r.status_code == 201, r.text
    body = r.json()
    return body["token"], body["user"]["tenantId"], body["user"]["id"]


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


def test_create_session_uses_signed_in_users_tenant(client):
    token, tenant_id, user_id = _signup(client)

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


def test_create_session_requires_prompt(client, tenant_a):
    resp = client.post("/api/sessions", json={"prompt": "  "}, headers={"X-Tenant-Id": tenant_a})
    assert resp.status_code == 422

