from __future__ import annotations

from doomberg_contracts import SkillManifest
from doomberg_core import ALL_SKILL_MANIFESTS, CORE_SKILL_MANIFESTS, SKILL_MANIFESTS, SKILLS


def test_every_implemented_skill_has_contract_manifest():
    assert set(SKILLS) == set(SKILL_MANIFESTS)
    assert {"market.get_ohlcv", "backtest.run"} <= set(CORE_SKILL_MANIFESTS)
    for manifest in ALL_SKILL_MANIFESTS.values():
        SkillManifest.model_validate(manifest)


def test_manifest_catalog_is_sorted_and_discovery_ready():
    ids = list(ALL_SKILL_MANIFESTS)
    assert ids == sorted(ids)
    for skill_id, manifest in ALL_SKILL_MANIFESTS.items():
        assert manifest["skill_id"] == skill_id
        assert manifest["runtime"]["profile"] in {
            "interactive",
            "scan",
            "backtest",
            "optimization",
            "stream",
        }
        assert set(manifest["permissions"]["broker"]) <= {"read"}
    assert ALL_SKILL_MANIFESTS["market.quote"]["permissions"]["broker"] == ["read"]
    assert ALL_SKILL_MANIFESTS["market.quote"]["source_classes"] == ["connected_account"]
    assert ALL_SKILL_MANIFESTS["broker.positions"]["permissions"]["network"] == ["ibkr-engine"]
