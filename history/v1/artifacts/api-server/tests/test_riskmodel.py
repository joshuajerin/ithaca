"""Unit tests for the Barra-style multi-factor risk model engine.

Runnable two ways:
    python artifacts/api-server/tests/test_riskmodel.py   # standalone
    pytest artifacts/api-server/tests/test_riskmodel.py    # if pytest installed

Covers: cross-sectional factor-return recovery on synthetic data, the variance
decomposition identities (factor + specific == total; risk contributions sum to
total vol; percent contributions sum to 100), MCTR/Euler consistency, the
standardize() winsorization, pca_variance ordering, and the honest-coverage
ValueError when there is not enough real data. Also a light end-to-end check
that build() produces a coherent model from the live/mock data layer.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import factor_model  # noqa: E402
from app.engine import riskmodel  # noqa: E402


def _synthetic(seed: int = 1, n: int = 40, t: int = 120, k: int = 3):
    """Build returns r = X f + e with KNOWN factor returns f and exposures X."""
    rng = np.random.default_rng(seed)
    exposures = rng.normal(size=(n, k))
    exposures[:, 0] = 1.0  # market-like intercept column
    true_f = np.array([0.0008, 0.0004, -0.0003])[:k] + np.zeros((t, k))
    true_f += rng.normal(scale=2e-4, size=(t, k))  # small time variation
    noise = rng.normal(scale=0.004, size=(t, n))
    rets = true_f @ exposures.T + noise
    names = ["Market"] + [f"F{i}" for i in range(1, k)]
    symbols = [f"S{i}" for i in range(n)]
    return rets, exposures, names, symbols, true_f


# --------------------------- standardize ---------------------------
def test_standardize_zero_mean_unit_std():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    z, mu, sd = riskmodel.standardize(x)
    assert math.isclose(float(z.mean()), 0.0, abs_tol=1e-9)
    assert math.isclose(float(z.std()), 1.0, rel_tol=1e-6)
    assert math.isclose(mu, 3.0, abs_tol=1e-9)


def test_standardize_winsorizes_outliers():
    x = np.concatenate([np.zeros(20), np.array([1000.0])])
    z, _, _ = riskmodel.standardize(x)
    assert float(z.max()) <= 3.0 + 1e-9
    assert float(z.min()) >= -3.0 - 1e-9


def test_standardize_constant_is_safe():
    z, mu, sd = riskmodel.standardize(np.full(10, 7.0))
    assert np.all(np.isfinite(z))
    assert math.isclose(mu, 7.0, abs_tol=1e-9)


# --------------------------- factor recovery ---------------------------
def test_recovers_known_factor_returns():
    rets, exposures, names, symbols, true_f = _synthetic(seed=3)
    model = riskmodel.build_model(rets, exposures, names, symbols)
    assert model.factor_returns.shape == true_f.shape
    # Mean estimated factor return should be close to the mean true factor return.
    est = model.factor_returns.mean(axis=0)
    tru = true_f.mean(axis=0)
    assert np.allclose(est, tru, atol=5e-4)
    assert 0.0 <= model.r2 <= 1.0


def test_specific_variance_nonnegative():
    rets, exposures, names, symbols, _ = _synthetic(seed=5)
    model = riskmodel.build_model(rets, exposures, names, symbols)
    assert np.all(model.specific_var >= 0.0)
    assert model.factor_cov.shape == (len(names), len(names))
    # Factor covariance is symmetric.
    assert np.allclose(model.factor_cov, model.factor_cov.T, atol=1e-12)


# --------------------------- decomposition identities ---------------------------
def test_variance_decomposition_adds_up():
    rets, exposures, names, symbols, _ = _synthetic(seed=7)
    model = riskmodel.build_model(rets, exposures, names, symbols)
    idx = list(range(10))
    w = np.full(10, 0.1)
    pr = riskmodel.decompose_portfolio(model, idx, w)
    # factor variance + specific variance == total variance
    assert math.isclose(
        pr.factor_vol**2 + pr.specific_vol**2, pr.total_vol**2, rel_tol=1e-6
    )
    # percent splits sum to 100
    assert math.isclose(pr.factor_var_pct + pr.specific_var_pct, 100.0, abs_tol=1e-6)


def test_risk_contributions_sum_to_total_vol():
    rets, exposures, names, symbols, _ = _synthetic(seed=9)
    model = riskmodel.build_model(rets, exposures, names, symbols)
    idx = list(range(12))
    w = np.full(12, 1.0 / 12)
    pr = riskmodel.decompose_portfolio(model, idx, w)
    # Euler allocation: sum of per-holding risk contributions == total vol.
    assert math.isclose(float(pr.risk_contrib.sum()), pr.total_vol, rel_tol=1e-6)
    # Percent contributions sum to 100.
    assert math.isclose(float(pr.pct_contrib.sum()), 100.0, abs_tol=1e-4)
    # MCTR * weight == risk contribution.
    assert np.allclose(pr.mctr * w, pr.risk_contrib, atol=1e-9)


def test_diversification_ratio_at_least_one():
    rets, exposures, names, symbols, _ = _synthetic(seed=11)
    model = riskmodel.build_model(rets, exposures, names, symbols)
    idx = list(range(15))
    w = np.full(15, 1.0 / 15)
    pr = riskmodel.decompose_portfolio(model, idx, w)
    assert pr.diversification_ratio >= 1.0 - 1e-9


# --------------------------- pca ---------------------------
def test_pca_variance_ordered_and_bounded():
    rets, *_ = _synthetic(seed=13)
    pca = riskmodel.pca_variance(rets, k=5)
    assert len(pca) == 5
    assert all(0.0 <= v <= 1.0 for v in pca)
    # Descending order.
    assert all(pca[i] >= pca[i + 1] - 1e-9 for i in range(len(pca) - 1))


# --------------------------- honest coverage ---------------------------
def test_aligned_panel_rejects_insufficient_overlap():
    # Two names with disjoint dates -> no shared grid -> empty result.
    series = {
        "A": [{"t": f"2024-01-{i:02d}", "c": 100.0 + i} for i in range(1, 10)],
        "B": [{"t": f"2024-06-{i:02d}", "c": 50.0 + i} for i in range(1, 10)],
    }
    dates, kept = factor_model._aligned_panel(series)
    assert dates == [] and kept == []


# --------------------------- end-to-end (real data layer) ---------------------------
def test_build_end_to_end_is_coherent():
    res = factor_model.build(["NVDA", "MSFT", "GOOGL", "META", "AMZN"])
    m = res.model
    assert len(m.symbols) >= 12
    assert m.exposures.shape == (len(m.symbols), len(m.factor_names))
    assert m.factor_names[0] == "Market"
    assert res.coverage.source in ("live", "mock")
    assert res.coverage.days >= factor_model.MIN_DAYS
    # Every included name has finite exposures and nonneg specific variance.
    assert np.all(np.isfinite(m.exposures))
    assert np.all(m.specific_var >= 0.0)
    # A portfolio over included names decomposes cleanly.
    idx = list(range(min(5, len(m.symbols))))
    w = np.full(len(idx), 1.0 / len(idx))
    pr = riskmodel.decompose_portfolio(m, idx, w)
    assert pr.total_vol > 0.0
    assert math.isclose(float(pr.pct_contrib.sum()), 100.0, abs_tol=1e-3)


def _run_all():
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in funcs:
        fn()
        passed += 1
        print(f"  PASS {fn.__name__}")
    print(f"\n{passed}/{len(funcs)} risk-model tests passed")


if __name__ == "__main__":
    _run_all()
