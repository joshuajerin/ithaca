"""Unit tests for the portfolio optimizer engine (pure numpy).

Runnable two ways:
    python artifacts/api-server/tests/test_optimize.py   # standalone
    pytest artifacts/api-server/tests/test_optimize.py    # if pytest installed

Covers the construction-method identities: budget/box/sector/gross constraints
are respected, risk-parity produces equal risk contributions, min-variance has
the lowest vol of the long-only methods, Black-Litterman collapses to the prior
when views are uninformative, HRP weights are long-only and sum to one, and the
turnover penalty pulls the solution toward the current book.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app.engine import optimize as opt  # noqa: E402


def _spd_cov(seed: int = 0, n: int = 8) -> np.ndarray:
    """A realistic positive-definite annualized covariance matrix."""
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n))
    cov = a @ a.T / n + np.diag(rng.uniform(0.02, 0.10, n))
    return cov


def _mu(seed: int = 1, n: int = 8) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-0.05, 0.25, n)


def test_budget_and_box():
    cov, mu = _spd_cov(), _mu()
    cons = opt.Constraints(long_only=True, max_position=0.25, net=1.0)
    for mode in ("max_sharpe", "min_variance", "target_vol"):
        r = opt.mean_variance(mu, cov, mode=mode, cons=cons, target_vol=0.20)
        w = r.weights
        assert abs(w.sum() - 1.0) < 1e-4, (mode, w.sum())
        assert w.min() >= -1e-6, (mode, w.min())
        assert w.max() <= 0.25 + 1e-4, (mode, w.max())
    print("ok: budget + box constraints respected across modes")


def test_long_short_gross():
    cov, mu = _spd_cov(2), _mu(3)
    cons = opt.Constraints(long_only=False, max_position=0.4, net=0.0, gross=2.0)
    r = opt.mean_variance(mu, cov, mode="max_sharpe", cons=cons)
    w = r.weights
    assert abs(w.sum() - 0.0) < 1e-3, w.sum()
    assert np.abs(w).sum() <= 2.0 + 1e-2, np.abs(w).sum()
    assert w.min() < 0, "expected some shorts in a market-neutral book"
    print("ok: long/short net=0, gross<=200% respected, shorts present")


def test_sector_caps():
    cov, mu = _spd_cov(4), _mu(5)
    sectors = ["tech", "tech", "tech", "tech", "energy", "energy", "fin", "fin"]
    cons = opt.Constraints(long_only=True, max_position=0.5, net=1.0,
                           sector_caps={"tech": 0.4})
    r = opt.mean_variance(mu, cov, mode="max_sharpe", cons=cons, sectors=sectors)
    w = r.weights
    tech = sum(w[i] for i in range(len(w)) if sectors[i] == "tech")
    assert tech <= 0.4 + 5e-3, tech
    assert abs(w.sum() - 1.0) < 1e-3
    print(f"ok: sector cap respected (tech={tech:.3f} <= 0.40)")


def test_min_var_is_lowest():
    cov, mu = _spd_cov(6), _mu(7)
    cons = opt.Constraints(long_only=True, max_position=1.0, net=1.0)
    mv = opt.mean_variance(mu, cov, mode="min_variance", cons=cons).weights
    ms = opt.mean_variance(mu, cov, mode="max_sharpe", cons=cons).weights
    vmv = float(np.sqrt(mv @ cov @ mv))
    vms = float(np.sqrt(ms @ cov @ ms))
    assert vmv <= vms + 1e-6, (vmv, vms)
    print(f"ok: min-variance vol {vmv:.4f} <= max-sharpe vol {vms:.4f}")


def test_risk_parity_equal_contrib():
    cov = _spd_cov(8)
    w = opt.risk_parity(cov)
    assert abs(w.sum() - 1.0) < 1e-6
    assert w.min() > 0, "risk parity is long-only positive"
    rc = opt.risk_contributions(w, cov)
    spread = float(rc.max() - rc.min())
    assert spread < 0.5, f"risk contributions not equal enough: spread={spread}"
    print(f"ok: risk parity equal risk contributions (spread={spread:.3f}%)")


def test_hrp_long_only_sums_one():
    cov = _spd_cov(9, n=10)
    w = opt.hrp(cov)
    assert abs(w.sum() - 1.0) < 1e-6, w.sum()
    assert w.min() >= 0, w.min()
    assert w.size == 10
    print("ok: HRP weights long-only and sum to 1")


def test_black_litterman_prior_collapse():
    cov = _spd_cov(10)
    n = cov.shape[0]
    w_mkt = np.full(n, 1.0 / n)
    delta = 2.5
    pi = delta * (cov @ w_mkt)
    # Views == prior => posterior should equal the prior.
    mu_post, prior = opt.black_litterman(cov, w_mkt, pi, delta=delta, view_confidence=1.0)
    assert np.allclose(prior, pi)
    assert np.max(np.abs(mu_post - pi)) < 1e-6, np.max(np.abs(mu_post - pi))
    print("ok: Black-Litterman collapses to prior when views == prior")


def test_turnover_penalty_pulls_to_book():
    cov, mu = _spd_cov(11), _mu(12)
    cons_free = opt.Constraints(long_only=True, max_position=1.0, net=1.0)
    w_free = opt.mean_variance(mu, cov, mode="max_sharpe", cons=cons_free).weights
    current = np.full(mu.size, 1.0 / mu.size)
    cons_to = opt.Constraints(long_only=True, max_position=1.0, net=1.0,
                              turnover_penalty=2.0)
    w_to = opt.mean_variance(mu, cov, mode="max_sharpe", cons=cons_to,
                             current=current).weights
    d_free = float(np.abs(w_free - current).sum())
    d_to = float(np.abs(w_to - current).sum())
    assert d_to < d_free + 1e-9, (d_to, d_free)
    print(f"ok: turnover penalty reduces trade distance ({d_to:.3f} < {d_free:.3f})")


def test_risk_parity_market_neutral_not_degenerate():
    """Conversationally reachable: 'market-neutral risk parity'. The method is
    inherently long-only, so the bridge must override net=0 to net=1 and report
    it — never return a degenerate all-zero book."""
    from app import portfolio
    cons, _ = portfolio._build_constraints(
        {"long_short": True, "market_neutral": True}, n=8)
    assert cons.net == 0.0 and not cons.long_only  # as requested, pre-reconcile
    cons, notes = portfolio._reconcile_method("risk_parity", cons)
    assert cons.long_only and abs(cons.net - 1.0) < 1e-12, (cons.long_only, cons.net)
    assert any("long-only" in n for n in notes), notes
    # And the actual projection is now a real, non-degenerate portfolio.
    cov = _spd_cov(3)
    w = opt.apply_long_only_constraints(opt.risk_parity(cov), cons, None)
    assert abs(w.sum() - 1.0) < 1e-6 and w.min() >= 0 and float(np.abs(w).sum()) > 0.5
    print("ok: market-neutral risk parity reconciled to long-only (no zero book)")


def test_hrp_market_neutral_reconciled():
    from app import portfolio
    cons, _ = portfolio._build_constraints({"long_short": True, "market_neutral": True}, n=10)
    cons, notes = portfolio._reconcile_method("hrp", cons)
    assert cons.long_only and abs(cons.net - 1.0) < 1e-12
    assert notes and "Hierarchical" in notes[0]
    cov = _spd_cov(5, n=10)
    w = opt.apply_long_only_constraints(opt.hrp(cov), cons, None)
    assert abs(w.sum() - 1.0) < 1e-6 and w.min() >= 0
    print("ok: market-neutral HRP reconciled to long-only")


def test_infeasible_max_position_reported():
    """A 2% per-name cap over 8 long-only names can't sum to 100%: relax + report."""
    from app import portfolio
    cons, notes = portfolio._build_constraints({"max_position": 0.02}, n=8)
    assert cons.max_position > 0.02, cons.max_position
    assert getattr(cons, "requested_max_position", None) == 0.02
    assert any("infeasible" in n.lower() for n in notes), notes
    # A feasible cap (e.g. 20% over 8 names) must NOT be relaxed or flagged.
    cons2, notes2 = portfolio._build_constraints({"max_position": 0.20}, n=8)
    assert abs(cons2.max_position - 0.20) < 1e-12 and not notes2
    print("ok: infeasible max position relaxed and reported (feasible left intact)")


def test_gross_below_net_not_violated():
    """A gross budget below |net| is infeasible (gross = sum|w| >= |net| always).
    The engine must floor it so it is never silently violated, and the bridge
    must relax + report it."""
    from app import portfolio
    # Engine: long-only net=1, gross=0.8 must not yield a gross<1 violation.
    cov, mu = _spd_cov(7), _mu(8)
    cons = opt.Constraints(long_only=True, max_position=1.0, net=1.0, gross=0.8)
    assert abs(cons.gross_limit() - 1.0) < 1e-12, cons.gross_limit()
    w = opt.mean_variance(mu, cov, mode="max_sharpe", cons=cons).weights
    assert abs(w.sum() - 1.0) < 1e-6 and abs(float(np.abs(w).sum()) - 1.0) < 1e-3
    # Bridge: the infeasible gross is reported.
    c2, notes = portfolio._build_constraints({"gross_limit": 0.8}, n=8)
    assert abs(c2.gross_limit() - 1.0) < 1e-12
    assert any("gross" in n.lower() for n in notes), notes
    # A feasible long/short gross (net=0, gross=1.5) is left intact, no note.
    c3, notes3 = portfolio._build_constraints(
        {"long_short": True, "market_neutral": True, "gross_limit": 1.5}, n=8)
    assert abs(c3.gross_limit() - 1.5) < 1e-12 and not any("gross" in n.lower() for n in notes3)
    print("ok: gross < |net| floored by engine and reported by bridge")


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nAll {len(fns)} optimizer tests passed.")


if __name__ == "__main__":
    main()
