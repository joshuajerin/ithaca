"""Unit tests for the compliance + risk gate (pure, no HTTP)."""
from __future__ import annotations

from control_helpers import valid_spec

from doomberg_control.gate import DEFAULT_RESTRICTED, evaluate_spec_gate


def test_feasible_spec_passes():
    decision = evaluate_spec_gate(valid_spec())
    assert decision.ok is True
    assert decision.violations == []
    assert decision.attestation["ok"] is True
    # gross 1.0 spread over 4 names => 0.25 each, well under per-name cap 0.5.
    assert decision.target_weights == {"AAPL": 0.25, "MSFT": 0.25, "NVDA": 0.25, "AMZN": 0.25}


def test_restricted_name_hard_blocks():
    spec = valid_spec(symbols=["AAPL", "GME", "MSFT"])  # GME is in DEFAULT_RESTRICTED
    assert "GME" in DEFAULT_RESTRICTED
    decision = evaluate_spec_gate(spec)
    assert decision.ok is False
    assert decision.restricted_hits == ["GME"]
    assert any("Restricted" in v for v in decision.violations)


def test_explicit_restricted_list_overrides_default():
    # MSFT is not in the default list; pass it explicitly to block.
    spec = valid_spec(symbols=["AAPL", "MSFT"])
    decision = evaluate_spec_gate(spec, restricted=["MSFT"])
    assert decision.ok is False
    assert decision.restricted_hits == ["MSFT"]


def test_per_name_breach_is_relaxed_not_blocked():
    # gross 1.0 over a single name => 100% in one name, but per-name cap is 0.5. The
    # projection relaxes it to a feasible book; relaxed is a warning, not a block.
    spec = valid_spec(symbols=["AAPL"])
    spec["construction"]["gross"] = 1.0
    spec["risk"]["max_name_pct"] = 0.5
    decision = evaluate_spec_gate(spec)
    assert decision.ok is True
    assert decision.relaxed is True
    assert decision.attestation["ok"] is True
    assert decision.attestation["maxName"] <= 0.5 + 1e-9
    assert any("relaxed" in w.lower() for w in decision.warnings)


def test_watch_list_warns_but_passes():
    spec = valid_spec(symbols=["AAPL", "MSFT"])
    decision = evaluate_spec_gate(spec, watch=["AAPL"])
    assert decision.ok is True
    assert any("Watch-list" in w for w in decision.warnings)


def test_gate_reuses_core_attestation_gross():
    # The attestation gross must equal sum|w| of the projected book (core math, not ours).
    spec = valid_spec(symbols=["AAPL", "MSFT", "NVDA", "AMZN"])
    decision = evaluate_spec_gate(spec)
    assert abs(decision.attestation["gross"] - 1.0) < 1e-9


def test_saved_firm_limits_are_hard_and_expose_dashboard_check_rows():
    decision = evaluate_spec_gate(
        valid_spec(),
        firm_limits={
            "maxPositionPct": 20.0,
            "maxNetPct": 120.0,
            "maxLeverage": 2.0,
            "maxConcentrationPct": 100.0,
        },
    )
    assert decision.ok is False
    assert any("Firm max position" in violation for violation in decision.violations)
    assert next(row for row in decision.checks if row["key"] == "maxPositionPct")["status"] == "breach"


def test_gate_kill_switch_is_a_hard_block():
    decision = evaluate_spec_gate(
        valid_spec(),
        kill_switch=True,
        kill_reason="operator halt",
    )
    assert decision.ok is False
    assert decision.kill_switch is True
    assert "operator halt" in decision.violations[-1]
