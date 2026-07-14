"""The risk gate is the money-path boundary. Headline test = the v1 311%-gross regression."""
from __future__ import annotations

import numpy as np

from ithaca_core.risk import RiskLimits, attest, project_feasible


def test_v1_311_percent_gross_regression():
    """v1 returned a 'gross 200%' book at ~311% gross as 'optimal'. Here projection must
    re-check the L1 ball and the final attest must confirm feasibility."""
    limits = RiskLimits(max_gross=2.0, max_net=2.0, max_name_pct=1.0)
    raw = np.array([1.5, 1.0, 0.61])  # gross 3.11 — the bug case
    assert attest(raw, limits).ok is False  # raw is a violation

    projected, att = project_feasible(raw, limits)
    assert att.ok is True
    assert att.gross <= limits.max_gross + 1e-9
    # never silently report a breaching book as feasible
    assert attest(projected, limits).ok is True


def test_per_name_cap_enforced():
    limits = RiskLimits(max_gross=10.0, max_net=10.0, max_name_pct=0.25)
    raw = np.array([0.9, 0.05, 0.05])
    projected, att = project_feasible(raw, limits)
    assert att.max_name <= 0.25 + 1e-9


def test_long_only_gross_matches_target_after_construction():
    limits = RiskLimits(max_gross=1.0, max_net=1.0, max_name_pct=1.0)
    raw = np.array([0.5, 0.3, 0.2])  # already feasible, gross 1.0
    projected, att = project_feasible(raw, limits)
    assert abs(att.gross - 1.0) < 1e-9
    assert att.ok
