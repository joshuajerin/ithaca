"""Persisted product-feedback submission."""

from __future__ import annotations


def test_submit_feedback_persists_for_local_user(client, db, tenant_a):
    response = client.post(
        "/api/feedback",
        json={"message": "  Add saved dashboard filters.  "},
        headers={"X-Tenant-Id": tenant_a},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "received"
    row = db.conn.execute(
        "SELECT * FROM feedback WHERE feedback_id = ?",
        (body["feedback_id"],),
    ).fetchone()
    assert row["tenant_id"] == tenant_a
    assert row["user_id"] == "ui"
    assert row["message"] == "Add saved dashboard filters."


def test_submit_feedback_rejects_blank_message(client, tenant_a):
    response = client.post(
        "/api/feedback",
        json={"message": "   "},
        headers={"X-Tenant-Id": tenant_a},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "feedback message is required"


def test_submit_feedback_rejects_message_over_limit(client, tenant_a):
    response = client.post(
        "/api/feedback",
        json={"message": "x" * 5001},
        headers={"X-Tenant-Id": tenant_a},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "feedback message must be 5000 characters or fewer"


def test_submit_feedback_accepts_message_at_limit(client, tenant_a):
    response = client.post(
        "/api/feedback",
        json={"message": "x" * 5000},
        headers={"X-Tenant-Id": tenant_a},
    )

    assert response.status_code == 201


def test_submit_feedback_rejects_agent_key(client, stores):
    tenant_id = stores.auth.create_tenant("Feedback agent")
    key, _ = stores.auth.mint_key(tenant_id, ["data:read"])

    response = client.post(
        "/api/feedback",
        json={"message": "agent generated feedback"},
        headers={"Authorization": f"Bearer {key}"},
    )

    assert response.status_code == 403
