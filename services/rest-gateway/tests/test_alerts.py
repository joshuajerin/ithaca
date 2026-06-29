"""Tenant-level alert API and SSE replay."""

from __future__ import annotations


def test_alerts_list_ack_and_replay_sse(client, stores, tenant_a):
    alert = stores.notifications.enqueue(
        tenant_a,
        event_type="trigger.fired",
        subject_type="trigger_firing",
        subject_id="fir_1",
        priority="high",
        payload={"symbol": "NVDA", "channels": ["doomberg_ui"]},
    )

    listed = client.get("/api/alerts", headers={"X-Tenant-Id": tenant_a})

    assert listed.status_code == 200
    assert listed.json()["alerts"][0]["notification_id"] == alert["notification_id"]

    replay = client.get(
        "/api/alerts/events",
        params={"replay_only": "1"},
        headers={"X-Tenant-Id": tenant_a},
    )
    assert replay.status_code == 200
    assert replay.headers["content-type"].startswith("text/event-stream")
    assert f"id: {alert['notification_id']}" in replay.text
    assert "event: trigger.fired" in replay.text

    acked = client.post(f"/api/alerts/{alert['notification_id']}/ack", headers={"X-Tenant-Id": tenant_a})
    assert acked.status_code == 200
    assert acked.json()["state"] == "acked"

    listed = client.get("/api/alerts", headers={"X-Tenant-Id": tenant_a})
    assert listed.json()["alerts"] == []


def test_alert_events_ticket_can_be_redeemed_once(client, stores, tenant_a):
    alert = stores.notifications.enqueue(
        tenant_a,
        event_type="trigger.fired",
        subject_type="trigger_firing",
        subject_id="fir_1",
        payload={"symbol": "NVDA", "channels": ["doomberg_ui"]},
    )

    ticket = client.post("/api/alerts/events-ticket", headers={"X-Tenant-Id": tenant_a})
    assert ticket.status_code == 201
    token = ticket.json()["sse_ticket"]

    first = client.get(
        "/api/alerts/events",
        params={"sse_ticket": token, "replay_only": "1"},
    )
    assert first.status_code == 200
    assert alert["notification_id"] in first.text

    second = client.get(
        "/api/alerts/events",
        params={"sse_ticket": token, "replay_only": "1"},
    )
    assert second.status_code == 401
