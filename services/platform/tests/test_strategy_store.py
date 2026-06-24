"""StrategyStore: immutable versioning (same name -> new version), tenant isolation."""

from __future__ import annotations

import pytest
from platform_helpers import new_uuid, strategy_spec


def test_create_returns_id_and_version(strategy_store):
    tenant = new_uuid()
    out = strategy_store.create(tenant, strategy_spec())
    assert set(out) == {"id", "version"}
    assert out["version"] == 1
    assert isinstance(out["id"], str)


def test_same_name_mints_new_version_same_id(strategy_store):
    tenant = new_uuid()
    v1 = strategy_store.create(tenant, strategy_spec("Alpha"))
    v2 = strategy_store.create(tenant, strategy_spec("Alpha"))
    assert v1["id"] == v2["id"]
    assert v1["version"] == 1
    assert v2["version"] == 2


def test_different_name_gets_new_id(strategy_store):
    tenant = new_uuid()
    a = strategy_store.create(tenant, strategy_spec("Alpha"))
    b = strategy_store.create(tenant, strategy_spec("Beta"))
    assert a["id"] != b["id"]
    assert a["version"] == 1
    assert b["version"] == 1


def test_get_returns_latest_version_and_stamps_server_fields(strategy_store):
    tenant = new_uuid()
    out1 = strategy_store.create(tenant, strategy_spec("Alpha"))
    strategy_store.create(tenant, strategy_spec("Alpha"))
    row = strategy_store.get(tenant, out1["id"])
    assert row["version"] == 2
    assert row["spec"]["id"] == out1["id"]
    assert row["spec"]["version"] == 2
    assert row["spec"]["tenant_id"] == tenant


def test_get_specific_version_is_immutable(strategy_store):
    tenant = new_uuid()
    out = strategy_store.create(tenant, strategy_spec("Alpha"))
    strategy_store.create(tenant, strategy_spec("Alpha"))
    v1 = strategy_store.get_version(tenant, out["id"], 1)
    v2 = strategy_store.get_version(tenant, out["id"], 2)
    assert v1["version"] == 1
    assert v2["version"] == 2
    # v1 still readable and unchanged after v2 was minted.
    assert v1["spec"]["version"] == 1


def test_list_returns_latest_per_strategy(strategy_store):
    tenant = new_uuid()
    strategy_store.create(tenant, strategy_spec("Alpha"))
    strategy_store.create(tenant, strategy_spec("Alpha"))
    strategy_store.create(tenant, strategy_spec("Beta"))
    listed = strategy_store.list(tenant)
    assert len(listed) == 2
    by_name = {s["name"]: s for s in listed}
    assert by_name["Alpha"]["version"] == 2
    assert by_name["Beta"]["version"] == 1


def test_tenant_isolation_on_get_and_list(strategy_store):
    tenant_a, tenant_b = new_uuid(), new_uuid()
    out = strategy_store.create(tenant_a, strategy_spec("Alpha"))
    assert strategy_store.get(tenant_b, out["id"]) is None
    assert strategy_store.list(tenant_b) == []
    assert strategy_store.get(tenant_a, out["id"]) is not None


def test_same_name_across_tenants_is_independent(strategy_store):
    tenant_a, tenant_b = new_uuid(), new_uuid()
    a = strategy_store.create(tenant_a, strategy_spec("Shared"))
    b = strategy_store.create(tenant_b, strategy_spec("Shared"))
    assert a["id"] != b["id"]
    assert a["version"] == 1
    assert b["version"] == 1


def test_missing_name_raises(strategy_store):
    tenant = new_uuid()
    spec = strategy_spec()
    del spec["name"]
    with pytest.raises(ValueError):
        strategy_store.create(tenant, spec)


def test_get_missing_returns_none(strategy_store):
    assert strategy_store.get(new_uuid(), new_uuid()) is None
