"""Signed-in adaptive dashboard API."""

from __future__ import annotations


def _bearer(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def _clerk_session(client, clerk_auth, email: str):
    token = clerk_auth(email=email, name=email.split("@")[0])
    r = client.get("/api/auth/me", headers=_bearer(token))
    assert r.status_code == 200, r.text
    body = r.json()
    return token, body["tenantId"], body["id"]


def _spec(title: str = "Performance") -> dict:
    return {
        "summary": "Performance-heavy usage.",
        "widgets": [
            {
                "id": "performance_pnl",
                "title": title,
                "priority": 1,
                "layout": {"x": 0, "y": 0, "w": 6, "h": 3},
                "reason": "The user watches performance.",
            }
        ],
    }


def test_adaptive_dashboard_requires_signed_in_user(client):
    resp = client.get("/api/dashboard/adaptive")

    assert resp.status_code == 401


def test_adaptive_dashboard_empty_for_user_without_sessions(client, clerk_auth):
    token, _tenant_id, _user_id = _clerk_session(client, clerk_auth, "empty@adaptive.test")

    resp = client.get("/api/dashboard/adaptive", headers=_bearer(token))

    assert resp.status_code == 200
    assert resp.json() == {"status": "empty"}


def test_adaptive_dashboard_pending_for_user_with_sessions(client, clerk_auth):
    token, _tenant_id, _user_id = _clerk_session(client, clerk_auth, "pending@adaptive.test")
    created = client.post(
        "/api/sessions",
        json={"prompt": "screen semis", "title": "Semis"},
        headers=_bearer(token),
    )
    assert created.status_code == 201, created.text

    resp = client.get("/api/dashboard/adaptive", headers=_bearer(token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["source_session_count"] == 1
    assert body["spec"]["widgets"][0]["id"] == "performance_pnl"


def test_adaptive_dashboard_ready_uses_signed_in_users_profile(client, stores, clerk_auth):
    token, tenant_id, user_id = _clerk_session(client, clerk_auth, "ready@adaptive.test")
    client.post("/api/sessions", json={"prompt": "risk review"}, headers=_bearer(token))
    stores.adaptive_dashboards.upsert(
        tenant_id,
        user_id,
        _spec("Risk Layout"),
        model="fake-haiku",
        source_session_count=1,
        source_event_count=1,
        generated_for_date="2026-06-29",
    )

    resp = client.get("/api/dashboard/adaptive", headers=_bearer(token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["spec"]["widgets"][0]["title"] == "Risk Layout"
    assert body["model"] == "fake-haiku"


def test_adaptive_dashboard_does_not_expose_another_users_profile(client, stores, clerk_auth):
    token_a, tenant_a, user_a = _clerk_session(client, clerk_auth, "a@adaptive.test")
    token_b, _tenant_b, _user_b = _clerk_session(client, clerk_auth, "b@adaptive.test")
    client.post("/api/sessions", json={"prompt": "a session"}, headers=_bearer(token_a))
    client.post("/api/sessions", json={"prompt": "b session"}, headers=_bearer(token_b))
    stores.adaptive_dashboards.upsert(
        tenant_a,
        user_a,
        _spec("Private A"),
        model="fake-haiku",
        source_session_count=1,
        source_event_count=1,
        generated_for_date="2026-06-29",
    )

    resp = client.get("/api/dashboard/adaptive", headers=_bearer(token_b))

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert "Private A" not in str(body)
