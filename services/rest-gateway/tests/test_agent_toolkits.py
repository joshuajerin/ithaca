from __future__ import annotations

import uuid


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_agent_toolkits_returns_live_catalog_for_data_read_key(client, stores):
    tenant = stores.auth.create_tenant("Toolkit Tenant")
    key, _ = stores.auth.mint_key(tenant, ["data:read"])

    response = client.get("/api/agent/toolkits", headers=_bearer(key))

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "toolkits.catalog"
    assert body["source"] == "live"
    market = next(row for row in body["toolkits"] if row["toolkit_id"] == "market-research")
    assert market["required_first_tool"] == "start_research_session"
    assert "market_quote" in market["direct_tools"]
    assert market["direct_tool_count"] == len(market["direct_tools"])
    assert {"name": "market_quote"} in market["tools"]


def test_agent_toolkits_requires_data_read_scope(client, stores):
    tenant = stores.auth.create_tenant("Low Scope Tenant")
    key, _ = stores.auth.mint_key(tenant, ["alerts:read"])

    response = client.get("/api/agent/toolkits", headers=_bearer(key))

    assert response.status_code == 403
    assert response.json()["detail"] == "missing required scope: data:read"


def test_agent_toolkits_supports_local_dev_tenant_header(client):
    response = client.get("/api/agent/toolkits", headers={"X-Tenant-Id": str(uuid.uuid4())})

    assert response.status_code == 200
    assert response.json()["count"] >= 1
