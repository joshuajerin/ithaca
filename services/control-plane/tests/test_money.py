"""apply_paper_delta — the single-writer paper money path: re-gates, then writes the book."""

from __future__ import annotations

import uuid

import pytest

from conftest import valid_spec

from doomberg_control.money import apply_paper_delta, make_applier


def _live_paper(platform, tenant, spec=None) -> str:
    """Drive a paper run all the way to the live state via the stores."""
    spec = spec or valid_spec()
    sv = platform.strategies.create(tenant, spec)
    stored = platform.strategies.get(tenant, sv["id"])["spec"]
    run_id = platform.runs.create(tenant, "paper", sv["id"], stored)
    platform.runs.transition(tenant, run_id, "queued", expect=0)
    platform.runs.transition(tenant, run_id, "running", expect=1)
    platform.runs.transition(tenant, run_id, "promoted", expect=2)
    platform.runs.transition(tenant, run_id, "live", expect=3)
    return run_id


@pytest.fixture()
def tenant() -> str:
    return str(uuid.uuid4())


def test_apply_writes_book_and_emits_fill(platform, tenant):
    run_id = _live_paper(platform, tenant)
    proposal = {"action": "propose", "targetWeights": {"AAPL": 0.5, "MSFT": 0.5},
                "marks": {"AAPL": 100.0, "MSFT": 200.0}}

    out = apply_paper_delta(platform, tenant, run_id, proposal)

    assert out["applied"] is True
    book = platform.books.get(tenant, run_id)
    assert book["weights"] == {"AAPL": 0.5, "MSFT": 0.5}
    assert book["version"] == 1
    fills = [e for e in platform.traces.events(tenant, run_id) if e["type"] == "fill"]
    assert fills and fills[-1]["data"]["applied"] is True
    assert fills[-1]["data"]["deltas"] == {"AAPL": 0.5, "MSFT": 0.5}


def test_apply_is_idempotent_on_repeat_target(platform, tenant):
    run_id = _live_paper(platform, tenant)
    proposal = {"action": "propose", "targetWeights": {"AAPL": 0.5, "MSFT": 0.5},
                "marks": {"AAPL": 100.0, "MSFT": 200.0}}
    apply_paper_delta(platform, tenant, run_id, proposal)
    out2 = apply_paper_delta(platform, tenant, run_id, proposal)
    # Book re-priced to the same target -> no deltas the second time, version still advances.
    assert out2["deltas"] == {}
    assert platform.books.get(tenant, run_id)["version"] == 2


def test_apply_blocks_restricted_name(platform, tenant):
    spec = valid_spec(name="HasGME", symbols=["AAPL", "GME"])
    run_id = _live_paper(platform, tenant, spec)
    proposal = {"action": "propose", "targetWeights": {"AAPL": 0.5, "GME": 0.5}}

    out = apply_paper_delta(platform, tenant, run_id, proposal)

    assert out["applied"] is False
    assert out["reason"] == "restricted"
    assert platform.books.get(tenant, run_id) is None  # nothing written
    types = [e["type"] for e in platform.traces.events(tenant, run_id)]
    assert "denial" in types and "fill" not in types


def test_apply_blocks_when_risk_breached(platform, tenant):
    run_id = _live_paper(platform, tenant)
    # Target grossly over the spec's max_gross=1.0 -> attestation fails -> denial, no write.
    proposal = {"action": "propose", "targetWeights": {"AAPL": 2.0, "MSFT": 2.0}}

    out = apply_paper_delta(platform, tenant, run_id, proposal)

    assert out["applied"] is False
    assert out["reason"] == "risk"
    assert platform.books.get(tenant, run_id) is None
    assert "denial" in [e["type"] for e in platform.traces.events(tenant, run_id)]


def test_apply_refuses_non_live_run(platform, tenant):
    spec = valid_spec()
    sv = platform.strategies.create(tenant, spec)
    stored = platform.strategies.get(tenant, sv["id"])["spec"]
    run_id = platform.runs.create(tenant, "paper", sv["id"], stored)  # still draft
    out = apply_paper_delta(platform, tenant, run_id, {"targetWeights": {"AAPL": 1.0}})
    assert out["applied"] is False
    assert out["reason"] == "not_live_paper"


def test_make_applier_bound_callable(platform, tenant):
    run_id = _live_paper(platform, tenant)
    apply = make_applier(platform)
    out = apply(tenant, run_id, {"action": "propose", "targetWeights": {"AAPL": 0.5, "MSFT": 0.5}})
    assert out["applied"] is True
