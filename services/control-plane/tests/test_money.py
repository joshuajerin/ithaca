"""apply_paper_delta — the single-writer paper money path: re-gates, then writes the book."""

from __future__ import annotations

import threading
import uuid

import pytest

from control_helpers import valid_spec

from ithaca_control.money import apply_paper_delta, make_applier


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


def test_apply_blocks_saved_firm_limit_breach(platform, tenant):
    run_id = _live_paper(platform, tenant)
    platform.compliance_policies.set(
        tenant,
        limits={
            "maxPositionPct": 40.0,
            "maxNetPct": 120.0,
            "maxLeverage": 2.0,
            "maxConcentrationPct": 100.0,
        },
        limits_enforced=True,
        restricted=["GME", "AMC", "SDNY"],
        watch=[],
        action="Strict position limit",
        actor_id="risk-officer",
        expect_version=0,
    )
    out = apply_paper_delta(
        platform,
        tenant,
        run_id,
        {"targetWeights": {"AAPL": 0.5, "MSFT": 0.5}},
    )
    assert out["applied"] is False
    assert out["reason"] == "compliance"
    assert platform.books.get(tenant, run_id) is None


def test_list_only_policy_does_not_silently_activate_reference_limits(platform, tenant):
    run_id = _live_paper(platform, tenant)
    platform.compliance_policies.set(
        tenant,
        limits={
            "maxPositionPct": 15.0,
            "maxNetPct": 120.0,
            "maxLeverage": 2.0,
            "maxConcentrationPct": 50.0,
        },
        limits_enforced=False,
        restricted=["GME", "AMC", "SDNY"],
        watch=["AAPL"],
        action="Watch list only",
        actor_id="risk-officer",
        expect_version=0,
    )
    out = apply_paper_delta(
        platform,
        tenant,
        run_id,
        {"targetWeights": {"AAPL": 0.5, "MSFT": 0.5}},
    )
    assert out["applied"] is True
    assert out["compliance"]["warnings"] == ["Watch-list name(s): AAPL"]


def test_apply_blocks_when_execution_halt_is_active(platform, tenant):
    run_id = _live_paper(platform, tenant)
    platform.execution_controls.set_tenant(
        tenant,
        enabled=True,
        reason="operator halt",
        actor_id="operator",
        expect_version=0,
    )
    out = apply_paper_delta(
        platform,
        tenant,
        run_id,
        {"targetWeights": {"AAPL": 0.5, "MSFT": 0.5}},
    )
    assert out["applied"] is False
    assert out["reason"] == "compliance"
    assert "operator halt" in out["gate"]["reason"]


def test_apply_missing_compliance_store_fails_closed(platform, tenant):
    run_id = _live_paper(platform, tenant)
    platform.compliance_policies = None
    out = apply_paper_delta(
        platform,
        tenant,
        run_id,
        {"targetWeights": {"AAPL": 0.5, "MSFT": 0.5}},
    )
    assert out["applied"] is False
    assert out["reason"] == "compliance"
    assert "Compliance policy store is unavailable" in out["gate"]["violations"]


def test_paper_apply_fence_serializes_policy_change_with_book_write(
    monkeypatch: pytest.MonkeyPatch, platform, tenant
):
    run_id = _live_paper(platform, tenant)
    entered_write = threading.Event()
    release_write = threading.Event()
    policy_done = threading.Event()
    original_apply = platform.books.apply

    def blocking_apply(*args, **kwargs):
        entered_write.set()
        assert release_write.wait(timeout=2)
        return original_apply(*args, **kwargs)

    monkeypatch.setattr(platform.books, "apply", blocking_apply)
    result: list[dict] = []
    apply_thread = threading.Thread(
        target=lambda: result.append(
            apply_paper_delta(
                platform,
                tenant,
                run_id,
                {"targetWeights": {"AAPL": 0.5, "MSFT": 0.5}},
            )
        ),
        daemon=True,
    )
    apply_thread.start()
    assert entered_write.wait(timeout=2)

    def restrict_symbol() -> None:
        platform.compliance_policies.set(
            tenant,
            limits={
                "maxPositionPct": 15.0,
                "maxNetPct": 120.0,
                "maxLeverage": 2.0,
                "maxConcentrationPct": 50.0,
            },
            limits_enforced=False,
            restricted=["AAPL"],
            watch=[],
            action="Restrict AAPL",
            actor_id="risk-officer",
            expect_version=0,
        )
        policy_done.set()

    policy_thread = threading.Thread(target=restrict_symbol, daemon=True)
    policy_thread.start()
    assert not policy_done.wait(timeout=0.05)
    release_write.set()
    apply_thread.join(timeout=2)
    policy_thread.join(timeout=2)
    assert result[0]["applied"] is True
    assert policy_done.is_set()

    denied = apply_paper_delta(
        platform,
        tenant,
        run_id,
        {"targetWeights": {"AAPL": 0.5, "MSFT": 0.5}},
    )
    assert denied["applied"] is False
    assert denied["reason"] == "restricted"
