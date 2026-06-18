"""Contract consistency gate (Python side).

For every domain with golden fixtures we assert that BOTH the raw JSON Schema and the
generated pydantic model agree: valid fixtures pass both, invalid fixtures fail both.
The TS/zod test (../../ts) runs the identical fixtures, so agreement here + there means
pydantic and zod stay in lockstep with the single schema source of truth.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

import doomberg_contracts as contracts

CONTRACTS_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = CONTRACTS_ROOT / "schema"
FIXTURE_DIR = CONTRACTS_ROOT / "fixtures"

# domain -> pydantic model
DOMAINS = {
    "provenance": contracts.ProvenanceEnvelope,
    "strategy_spec": contracts.StrategySpec,
    "events": contracts.TraceEvent,
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _schema_validator(domain: str) -> Draft202012Validator:
    schema = _load(SCHEMA_DIR / f"{domain}.schema.json")
    return Draft202012Validator(schema)


@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_valid_fixture_passes_both(domain: str) -> None:
    payload = _load(FIXTURE_DIR / f"{domain}.valid.json")
    # raw JSON Schema accepts it
    _schema_validator(domain).validate(payload)
    # generated pydantic model accepts it
    DOMAINS[domain].model_validate(payload)


@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_invalid_fixture_fails_both(domain: str) -> None:
    payload = _load(FIXTURE_DIR / f"{domain}.invalid.json")
    validator = _schema_validator(domain)
    assert validator.is_valid(payload) is False, "raw schema wrongly accepted invalid fixture"
    with pytest.raises(ValidationError):
        DOMAINS[domain].model_validate(payload)


def test_strategy_spec_rejects_free_form_code() -> None:
    """The core security invariant: a StrategySpec can never smuggle a code field.

    additionalProperties:false -> pydantic extra='forbid'. This is the structural reason
    v2 'never runs agent-authored code'.
    """
    spec = _load(FIXTURE_DIR / "strategy_spec.valid.json")
    spec["code"] = "import os; os.system('rm -rf /')"
    with pytest.raises(ValidationError):
        contracts.StrategySpec.model_validate(spec)


def test_models_importable() -> None:
    assert set(contracts.__all__) == {
        "AuthPrincipal",
        "ProvenanceEnvelope",
        "StrategySpec",
        "TenantContext",
        "TraceEvent",
    }
