"""Unit tests for the backtesting & simulation engine.

Runnable two ways:
    python artifacts/api-server/tests/test_engine.py     # standalone
    pytest artifacts/api-server/tests/test_engine.py      # if pytest installed

Covers: deterministic strategy signals, the no-lookahead buy-and-hold identity
(strategy equity tracks the price ratio), performance/risk stat correctness,
Monte Carlo output shape + percentile ordering + determinism, and the graceful
failure when there is not enough history.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import engine  # noqa: E402
from app.engine import backtest, montecarlo, stats, strategies  # noqa: E402


def _points(closes):
    return [{"t": f"2024-01-{i + 1:02d}", "c": float(c)} for i, c in enumerate(closes)]


# --------------------------- strategies ---------------------------
def test_normalize_strategy_aliases():
    assert strategies.normalize_strategy("Buy and Hold") == "buy_and_hold"
    assert strategies.normalize_strategy("mean-reversion") == "mean_reversion"
    assert strategies.normalize_strategy("MA Cross") == "ma_crossover"
    assert strategies.normalize_strategy("trend following") == "momentum"
    # Unknown names fall back to a sane default.
    assert strategies.normalize_strategy("nonsense-xyz") == "momentum"


def test_buy_and_hold_is_always_invested():
    closes = np.array([10.0, 11.0, 12.0, 9.0], dtype=float)
    pos = strategies.signal_buy_and_hold(closes, {})
    assert np.all(pos == 1.0)
    assert len(pos) == len(closes)


def test_momentum_signal_is_deterministic_and_no_lookahead():
    # Steadily rising series -> momentum should be long once warmed up.
    closes = np.array([float(100 + i) for i in range(40)], dtype=float)
    pos = strategies.signal_momentum(closes, {"lookback": 10})
    # Before the lookback window is filled there can be no signal.
    assert np.all(pos[:10] == 0.0)
    # After warmup, an uptrend is fully long.
    assert pos[-1] == 1.0
    # Running twice gives identical output (pure function).
    pos2 = strategies.signal_momentum(closes, {"lookback": 10})
    assert np.array_equal(pos, pos2)


# --------------------------- backtest core ---------------------------
def test_buy_and_hold_equity_tracks_price_ratio():
    closes = [100.0, 110.0, 121.0, 108.9]
    result = backtest.run_backtest(_points(closes), "buy_and_hold", cost_bps=0.0)
    curve = result["curve"]
    # Rebased to 100, buy-and-hold equity must equal the cumulative price ratio.
    for i, row in enumerate(curve):
        expected = 100.0 * closes[i] / closes[0]
        assert math.isclose(row["strategy"], round(expected, 2), abs_tol=0.05), (
            f"bar {i}: {row['strategy']} vs {expected}"
        )
    # Benchmark IS buy-and-hold, so the two series coincide here.
    assert all(
        math.isclose(r["strategy"], r["benchmark"], abs_tol=0.01) for r in curve
    )


def test_backtest_requires_minimum_history():
    raised = False
    try:
        backtest.run_backtest(_points([100.0, 101.0]), "momentum")
    except ValueError:
        raised = True
    assert raised, "expected ValueError on insufficient history"


def test_backtest_stats_shape_and_costs():
    closes = [float(100 + math.sin(i / 3) * 5 + i * 0.3) for i in range(120)]
    result = backtest.run_backtest(_points(closes), "ma_crossover", {"fast": 5, "slow": 20})
    st = result["stats"]
    for key in ("sharpe", "sortino", "cagr", "maxDD", "winRate", "vol", "turnover", "var95", "cvar95"):
        assert key in st, f"missing stat {key}"
    assert st["maxDD"] <= 0.0  # drawdown is non-positive
    assert 0.0 <= st["winRate"] <= 100.0
    assert st["turnover"] >= 0.0
    assert len(result["curve"]) == len(closes)


def test_zero_cost_beats_or_equals_cost_for_active_strategy():
    closes = [float(100 + math.sin(i / 2) * 8) for i in range(150)]
    free = backtest.run_backtest(_points(closes), "ma_crossover", {"fast": 3, "slow": 10}, cost_bps=0.0)
    charged = backtest.run_backtest(_points(closes), "ma_crossover", {"fast": 3, "slow": 10}, cost_bps=50.0)
    # Trading costs can only drag on the final equity.
    assert free["curve"][-1]["strategy"] >= charged["curve"][-1]["strategy"] - 1e-6


# --------------------------- stats ---------------------------
def test_max_drawdown_known_value():
    equity = np.array([100.0, 120.0, 60.0, 90.0])
    # Peak 120 -> trough 60 = -50%.
    assert math.isclose(stats.max_drawdown(equity), -0.5, abs_tol=1e-9)


def test_var_cvar_are_positive_loss_fractions():
    rng = np.random.default_rng(0)
    rets = rng.normal(0.0, 0.02, size=2000)
    var = stats.var_historical(rets, 0.95)
    cvar = stats.cvar_historical(rets, 0.95)
    assert var > 0
    # CVaR (expected shortfall) is always at least as large as VaR.
    assert cvar >= var


# --------------------------- monte carlo ---------------------------
def _hist_returns(seed=1):
    rng = np.random.default_rng(seed)
    return rng.normal(0.0005, 0.015, size=300)


def test_monte_carlo_shape_and_percentile_ordering():
    sim = engine.monte_carlo(_hist_returns(), start_value=100.0, horizon=60, n_paths=500, method="bootstrap")
    assert len(sim["fan"]) == 61  # horizon + 1 (includes step 0)
    first = sim["fan"][0]
    assert first["step"] == 0
    # Every step's percentiles are monotonically ordered.
    for f in sim["fan"]:
        assert f["p5"] <= f["p25"] <= f["p50"] <= f["p75"] <= f["p95"] + 1e-6
    # Step 0 starts at the start value for all percentiles.
    assert math.isclose(first["p50"], 100.0, abs_tol=0.01)
    summ = sim["summary"]
    for key in ("expectedTerminal", "medianTerminal", "probLoss", "var95", "cvar95", "paths"):
        assert key in summ
    assert 0.0 <= summ["probLoss"] <= 100.0


def test_monte_carlo_is_deterministic_with_seed():
    r = _hist_returns()
    a = engine.monte_carlo(r, start_value=100.0, horizon=30, n_paths=400, method="gbm", seed=7)
    b = engine.monte_carlo(r, start_value=100.0, horizon=30, n_paths=400, method="gbm", seed=7)
    assert a["summary"] == b["summary"]
    assert a["fan"] == b["fan"]


def test_monte_carlo_requires_history():
    raised = False
    try:
        engine.monte_carlo(np.array([0.01, 0.02]), horizon=10)
    except ValueError:
        raised = True
    assert raised, "expected ValueError on insufficient return history"


def _ramp_series(n=300, start="2024-01-01"):
    """A cross-section where each symbol has a distinct, monotone trend so that
    momentum has a clean, predictable rank ordering."""
    import datetime as _dt
    base = _dt.date.fromisoformat(start)
    dates = [(base + _dt.timedelta(days=i)).isoformat() for i in range(n)]
    series = {}
    for k, drift in enumerate([-0.002, -0.001, 0.0, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007]):
        closes = [100.0]
        for _ in range(1, n):
            closes.append(closes[-1] * (1.0 + drift))
        series[f"S{k}"] = [{"t": d, "c": c} for d, c in zip(dates, closes)]
    return series


def test_normalize_signal_aliases():
    assert engine.normalize_signal("mom") == "momentum"
    assert engine.normalize_signal("mean reversion") == "short_reversal"
    assert engine.normalize_signal("low vol") == "low_volatility"
    assert engine.normalize_signal("earnings yield") == "value"
    assert engine.normalize_signal("profitability") == "quality"
    assert engine.normalize_signal("garbage") == "momentum"


def test_spearman_ic_perfect_and_inverse():
    x = [1, 2, 3, 4, 5]
    assert math.isclose(engine.spearman_ic(x, [10, 20, 30, 40, 50]), 1.0, abs_tol=1e-9)
    assert math.isclose(engine.spearman_ic(x, [50, 40, 30, 20, 10]), -1.0, abs_tol=1e-9)


def test_spearman_ic_insufficient_returns_nan():
    assert math.isnan(engine.spearman_ic([1, 2], [3, 4]))


def test_evaluate_signal_momentum_shape_and_positive_ic():
    series = _ramp_series()
    res = engine.evaluate_signal(series, signal="momentum", holding=21, quantiles=5)
    # Coverage: all names usable, none excluded.
    assert len(res["included"]) == 10
    assert res["excluded"] == []
    # Required keys present.
    for k in ("ic", "decay", "turnover", "turnoverAnnual", "rebalances",
              "quantileReturns", "spread", "spreadStats", "primaryHorizon"):
        assert k in res
    # Persistent trends → momentum should have strongly positive rank IC.
    assert res["ic"]["mean"] > 0.5
    # Decay curve has one point per horizon.
    assert len(res["decay"]) == len(res["horizons"])
    # Spread curve rebased to 100 at inception (first point already after a step).
    assert res["spread"], "expected a non-empty spread curve"
    # Top quantile beats bottom quantile for a working long signal.
    qr = {q["quantile"]: q["ret"] for q in res["quantileReturns"]}
    assert qr[5] > qr[1]


def test_evaluate_signal_excludes_missing_history():
    series = _ramp_series()
    series["BAD"] = [{"t": "2024-01-01", "c": 100.0}]  # too short
    res = engine.evaluate_signal(series, signal="momentum")
    assert "BAD" in [e["symbol"] for e in res["excluded"]]
    assert "BAD" not in res["included"]


def test_evaluate_signal_fundamental_excludes_missing_ctx():
    series = _ramp_series()
    # Provide ctx for only some names; the rest must be excluded (no imputation).
    ctx = {f"S{k}": {"fval": float(k)} for k in range(7)}
    res = engine.evaluate_signal(series, signal="value", ctx_by_symbol=ctx, holding=21)
    excluded = {e["symbol"] for e in res["excluded"]}
    assert {"S7", "S8", "S9"} <= excluded
    assert len(res["included"]) == 7


def test_evaluate_signal_is_deterministic():
    series = _ramp_series()
    a = engine.evaluate_signal(series, signal="momentum", holding=21)
    b = engine.evaluate_signal(series, signal="momentum", holding=21)
    assert a["ic"] == b["ic"]
    assert a["spread"] == b["spread"]
    assert a["quantileReturns"] == b["quantileReturns"]


def test_evaluate_signal_too_few_names_returns_empty_stats():
    series = {k: v for k, v in list(_ramp_series().items())[:3]}
    res = engine.evaluate_signal(series, signal="momentum", quantiles=5, min_names=5)
    assert res["spread"] == []
    assert res["ic"]["n"] == 0


def test_normalize_scheme_aliases():
    assert engine.normalize_scheme(None) == "top_quantile"
    assert engine.normalize_scheme("long short") == "long_short"
    assert engine.normalize_scheme("market-neutral spread") == "long_short"
    assert engine.normalize_scheme("top quantile") == "top_quantile"
    assert engine.normalize_scheme("garbage") == "top_quantile"


def test_construct_portfolio_top_quantile_shape_and_book():
    series = _ramp_series()
    res = engine.construct_portfolio(series, signal="momentum", scheme="top_quantile",
                                     quantiles=5, holding=21)
    for k in ("curve", "drawdown", "stats", "benchStats", "holdings",
              "longCount", "shortCount", "gross", "net", "turnoverAnnual"):
        assert k in res
    # Long-only top quantile: no shorts, weights sum to ~1, net == gross.
    assert res["shortCount"] == 0
    assert res["longCount"] > 0
    assert math.isclose(res["net"], 1.0, abs_tol=1e-6)
    assert math.isclose(res["gross"], 1.0, abs_tol=1e-6)
    # On a clean uptrending cross-section the long book should make money.
    assert res["stats"]["totalReturn"] > 0
    # Equity curve is rebased to 100 at inception.
    assert res["curve"][0]["strategy"] == 100.0
    # Holdings are the top names (highest drift S5..S9 in the ramp).
    longs = {h["symbol"] for h in res["holdings"] if h["side"] == "long"}
    assert "S9" in longs


def test_construct_portfolio_long_short_is_dollar_neutral():
    series = _ramp_series()
    res = engine.construct_portfolio(series, signal="momentum", scheme="long_short",
                                     quantiles=5, holding=21)
    assert res["longCount"] > 0 and res["shortCount"] > 0
    # Dollar-neutral: net ~ 0, gross ~ 2 (1 long + 1 short).
    assert math.isclose(res["net"], 0.0, abs_tol=1e-6)
    assert math.isclose(res["gross"], 2.0, abs_tol=1e-6)
    # Long top / short bottom of a monotone trend → positive realized spread.
    assert res["stats"]["totalReturn"] > 0


def test_construct_portfolio_excludes_missing_and_never_imputes():
    series = _ramp_series()
    series["BAD"] = [{"t": "2024-01-01", "c": 100.0}]  # too short
    res = engine.construct_portfolio(series, signal="momentum", scheme="top_quantile")
    excluded = {e["symbol"] for e in res["excluded"]}
    assert "BAD" in excluded
    assert "BAD" not in res["included"]
    assert "BAD" not in {h["symbol"] for h in res["holdings"]}


def test_construct_portfolio_is_deterministic():
    series = _ramp_series()
    a = engine.construct_portfolio(series, signal="momentum", scheme="long_short", holding=21)
    b = engine.construct_portfolio(series, signal="momentum", scheme="long_short", holding=21)
    assert a["curve"] == b["curve"]
    assert a["stats"] == b["stats"]
    assert a["holdings"] == b["holdings"]


def test_construct_portfolio_too_few_names_returns_empty_curve():
    series = {k: v for k, v in list(_ramp_series().items())[:3]}
    res = engine.construct_portfolio(series, signal="momentum", quantiles=5, min_names=5)
    assert res["curve"] == []
    assert res["holdings"] == []


def test_normalize_combine_method_aliases():
    assert engine.normalize_combine_method("equal") == "equal_weight"
    assert engine.normalize_combine_method("naive") == "equal_weight"
    assert engine.normalize_combine_method("ic weighted") == "ic_weighted"
    assert engine.normalize_combine_method("ic-weighted") == "ic_weighted"
    assert engine.normalize_combine_method("inverse correlation") == "inverse_correlation"
    assert engine.normalize_combine_method("risk weighted") == "inverse_correlation"
    assert engine.normalize_combine_method(None) == "equal_weight"
    assert engine.normalize_combine_method("garbage") == "equal_weight"


def test_combine_signals_shape_and_weights_sum_to_one():
    series = _ramp_series()
    res = engine.combine_signals(series, signals=["momentum", "low_volatility"], method="equal_weight", holding=21)
    # Composite scored with the same scorecard keys as a single signal.
    comp = res["composite"]
    for k in ("ic", "decay", "turnover", "turnoverAnnual", "rebalances",
              "quantileReturns", "spread", "spreadStats"):
        assert k in comp
    # Weights present for every requested component and sum to ~1.
    assert len(res["weights"]) == 2
    assert math.isclose(sum(w["weight"] for w in res["weights"]), 1.0, abs_tol=1e-9)
    # Equal weight is exactly 1/N.
    for w in res["weights"]:
        assert math.isclose(w["weight"], 0.5, abs_tol=1e-9)
    # Correlation matrix is square, symmetric and unit-diagonal.
    M = res["correlation"]["matrix"]
    assert len(M) == 2 and all(len(r) == 2 for r in M)
    assert math.isclose(M[0][0], 1.0, abs_tol=1e-9)
    assert math.isclose(M[0][1], M[1][0], abs_tol=1e-9)


def test_combine_signals_ic_weighted_favors_stronger_component():
    series = _ramp_series()
    # Momentum is the clean trend signal here; short_reversal is its inverse.
    res = engine.combine_signals(series, signals=["momentum", "short_reversal"], method="ic_weighted", holding=21)
    assert res["method"] == "ic_weighted"
    wmap = {w["signal"]: w["weight"] for w in res["weights"]}
    # IC weighting floors negative IC at 0, so the inverse signal gets ~no weight.
    assert wmap["momentum"] >= wmap["short_reversal"]
    assert math.isclose(sum(wmap.values()), 1.0, abs_tol=1e-9)


def test_combine_signals_inverse_correlation_weights_sum_to_one():
    series = _ramp_series()
    res = engine.combine_signals(series, signals=["momentum", "low_volatility", "short_reversal"], method="inverse_correlation", holding=21)
    assert res["method"] == "inverse_correlation"
    assert math.isclose(sum(w["weight"] for w in res["weights"]), 1.0, abs_tol=1e-9)
    assert all(w["weight"] >= 0 for w in res["weights"])


def test_combine_signals_excludes_missing_history():
    series = _ramp_series()
    series["BAD"] = [{"t": "2024-01-01", "c": 100.0}]
    res = engine.combine_signals(series, signals=["momentum", "low_volatility"])
    assert "BAD" in [e["symbol"] for e in res["excluded"]]


def test_combine_signals_strict_intersection_excludes_partial_inputs():
    # value needs per-name fundamentals; provide them for only some names. A name
    # missing ANY selected component's input must be excluded from the composite
    # (strict intersection, real data only — never imputed).
    series = _ramp_series()
    ctx = {"value": {f"S{k}": {"fval": float(k)} for k in range(7)}}
    res = engine.combine_signals(series, signals=["momentum", "value"], ctx_by_signal=ctx, holding=21)
    excluded = {e["symbol"] for e in res["excluded"]}
    assert {"S7", "S8", "S9"} <= excluded
    included = set(res["included"])
    assert not ({"S7", "S8", "S9"} & included)
    # Names that DO have both inputs survive into the composite universe.
    assert "S0" in included
    assert res["composite"]["included"] == len(included)
    # The exclusion is auditable: it names the missing component.
    bad = next(e for e in res["excluded"] if e["symbol"] == "S9")
    assert "value" in bad["reason"].lower()


def test_combine_signals_is_deterministic():
    series = _ramp_series()
    a = engine.combine_signals(series, signals=["momentum", "low_volatility"], method="ic_weighted", holding=21)
    b = engine.combine_signals(series, signals=["momentum", "low_volatility"], method="ic_weighted", holding=21)
    assert a["weights"] == b["weights"]
    assert a["correlation"] == b["correlation"]
    assert a["composite"]["spread"] == b["composite"]["spread"]


from app.engine import attribution as attr


def _attr_panel(T=80, N=6, K=4, seed=7):
    rng = np.random.default_rng(seed)
    asset_returns = rng.normal(0.0005, 0.012, size=(T, N))
    weights = np.full(N, 1.0 / N)
    exposures = rng.normal(0.0, 0.6, size=K)
    factor_returns = rng.normal(0.0002, 0.006, size=(T, K))
    return asset_returns, weights, exposures, factor_returns


def test_brinson_effects_sum_to_active_return():
    sectors = ["Tech", "Health", "Energy"]
    wp = {"Tech": 0.5, "Health": 0.3, "Energy": 0.2}
    wb = {"Tech": 0.4, "Health": 0.4, "Energy": 0.2}
    rp = {"Tech": 0.08, "Health": -0.02, "Energy": 0.05}
    rb = {"Tech": 0.06, "Health": 0.01, "Energy": 0.03}
    out = attr.brinson(sectors, wp, wb, rp, rb)
    t = out["totals"]
    # Outputs are percent rounded to 2dp, so allow a small rounding tolerance.
    assert abs((t["allocation"] + t["selection"] + t["interaction"]) - t["activeReturn"]) < 0.02
    for row in out["rows"]:
        assert abs((row["allocation"] + row["selection"] + row["interaction"]) - row["total"]) < 0.02


def test_brinson_linked_effects_sum_to_geometric_active_return():
    # Multi-period sector returns over a long window; constant weights.
    rng = np.random.default_rng(11)
    sectors = ["Tech", "Health", "Energy", "Financials"]
    T = 252
    wp = {"Tech": 0.45, "Health": 0.25, "Energy": 0.10, "Financials": 0.20}
    wb = {"Tech": 0.35, "Health": 0.30, "Energy": 0.15, "Financials": 0.20}
    rp = {s: rng.normal(0.0006, 0.013, size=T) for s in sectors}
    rb = {s: rng.normal(0.0004, 0.011, size=T) for s in sectors}
    out = attr.brinson_linked(sectors, wp, wb, rp, rb)
    t = out["totals"]
    assert out["linked"] is True
    assert out["subPeriods"] == T
    # Geometric active return from the compounded per-period totals.
    rp_t = sum(np.asarray(rp[s]) * wp[s] for s in sectors)
    rb_t = sum(np.asarray(rb[s]) * wb[s] for s in sectors)
    rp_total = float(np.prod(1.0 + rp_t) - 1.0) * 100.0
    rb_total = float(np.prod(1.0 + rb_t) - 1.0) * 100.0
    active = rp_total - rb_total
    # Linked effects add up exactly (within rounding) to the geometric active return.
    assert abs(t["activeReturn"] - active) < 0.02
    assert abs((t["allocation"] + t["selection"] + t["interaction"]) - active) < 0.02
    assert abs(t["portReturn"] - rp_total) < 0.02
    assert abs(t["benchReturn"] - rb_total) < 0.02
    for row in out["rows"]:
        assert abs((row["allocation"] + row["selection"] + row["interaction"]) - row["total"]) < 0.02


def test_brinson_linked_reduces_single_period_linking_bias():
    # Over a long window with a clear trend, single-period BHB on compounded
    # sector returns drifts from the true geometric active return; the linked
    # version is additive to it by construction.
    rng = np.random.default_rng(3)
    sectors = ["A", "B"]
    T = 252
    wp = {"A": 0.7, "B": 0.3}
    wb = {"A": 0.5, "B": 0.5}
    rp = {"A": rng.normal(0.0010, 0.02, size=T), "B": rng.normal(0.0002, 0.02, size=T)}
    rb = {"A": rng.normal(0.0006, 0.018, size=T), "B": rng.normal(0.0003, 0.018, size=T)}
    rp_t = sum(np.asarray(rp[s]) * wp[s] for s in sectors)
    rb_t = sum(np.asarray(rb[s]) * wb[s] for s in sectors)
    active = (float(np.prod(1.0 + rp_t) - 1.0) - float(np.prod(1.0 + rb_t) - 1.0)) * 100.0
    # Single-period BHB on compounded sector returns.
    rp_c = {s: float(np.prod(1.0 + np.asarray(rp[s])) - 1.0) for s in sectors}
    rb_c = {s: float(np.prod(1.0 + np.asarray(rb[s])) - 1.0) for s in sectors}
    sp = attr.brinson(sectors, wp, wb, rp_c, rb_c)["totals"]
    sp_sum = sp["allocation"] + sp["selection"] + sp["interaction"]
    linked = attr.brinson_linked(sectors, wp, wb, rp, rb)["totals"]
    linked_sum = linked["allocation"] + linked["selection"] + linked["interaction"]
    # Linked sum matches geometric active return; single-period leaves a residual.
    assert abs(linked_sum - active) < 0.02
    assert abs(sp_sum - active) > abs(linked_sum - active)


def test_factor_contributions_plus_specific_reconstruct_realized():
    asset_returns, weights, exposures, factor_returns = _attr_panel()
    book = attr.book_returns(asset_returns, weights)
    names = [f"F{k}" for k in range(factor_returns.shape[1])]
    out = attr.factor_attribution(exposures, factor_returns, names, book)
    # Each field is percent rounded to 2dp; identity holds within rounding.
    assert abs((out["factorReturn"] + out["specificReturn"]) - out["realizedReturn"]) < 0.02
    contrib_sum = sum(r["contribution"] for r in out["rows"])  # includes Specific row
    assert abs(contrib_sum - out["realizedReturn"]) < 0.02


def test_equity_curve_matches_compounded_book_return():
    asset_returns, weights, _, _ = _attr_panel()
    book = attr.book_returns(asset_returns, weights)
    curve = attr.equity_curve(book, base=100.0)
    expected = 100.0 * float(np.prod(1.0 + book))
    assert abs(curve[-1] - expected) < 1e-6
    assert curve.shape[0] == book.shape[0] + 1


def test_active_stats_zero_when_book_equals_bench():
    asset_returns, weights, _, _ = _attr_panel()
    book = attr.book_returns(asset_returns, weights)
    out = attr.active_stats(book, book)
    assert abs(out["activeReturn"]) < 1e-9
    assert abs(out["trackingError"]) < 1e-9
    assert abs(out["beta"] - 1.0) < 1e-6


def test_align_benchmark_returns_date_aligned():
    # A real-style close series keyed by ISO date. The window asks for the last
    # three dates; the first window return must use the close just BEFORE it.
    closes = {
        "2025-01-01": 100.0,
        "2025-01-02": 110.0,
        "2025-01-03": 121.0,
        "2025-01-04": 121.0,
    }
    dates = ["2025-01-02", "2025-01-03", "2025-01-04"]
    out, missing = attr.align_benchmark_returns(closes, dates)
    assert missing == 0
    assert out.shape[0] == 3
    assert abs(out[0] - 0.10) < 1e-9   # 110/100 - 1
    assert abs(out[1] - 0.10) < 1e-9   # 121/110 - 1
    assert abs(out[2] - 0.0) < 1e-9    # flat


def test_align_benchmark_returns_reports_missing_days():
    # The benchmark did not trade on 2025-01-03 (a portfolio trading day).
    closes = {"2025-01-01": 100.0, "2025-01-02": 105.0, "2025-01-04": 105.0}
    dates = ["2025-01-02", "2025-01-03", "2025-01-04"]
    out, missing = attr.align_benchmark_returns(closes, dates)
    assert missing == 1
    assert abs(out[0] - 0.05) < 1e-9   # 105/100 - 1
    assert abs(out[1] - 0.0) < 1e-9    # missing day carried flat
    assert abs(out[2] - 0.0) < 1e-9    # 105/105 - 1 vs last available close


def test_align_benchmark_returns_empty_series():
    out, missing = attr.align_benchmark_returns({}, ["2025-01-02", "2025-01-03"])
    assert missing == 2
    assert out.shape[0] == 2
    assert float(np.sum(np.abs(out))) == 0.0


def test_resolve_benchmark_validates_real_instruments():
    from app import skills
    assert skills._resolve_benchmark({})[0] == "SPY"                     # default
    assert skills._resolve_benchmark({"benchmark": "qqq"})[0] == "QQQ"   # case + valid
    assert skills._resolve_benchmark({"benchmark": "$IWM"})[0] == "IWM"  # strips $
    # An unknown / non-real ticker must NOT be used; fall back to the default.
    assert skills._resolve_benchmark({"benchmark": "FAKE"})[0] == "SPY"
    # A real, tradable instrument is now honored as a user-selected benchmark.
    assert skills._resolve_benchmark({"benchmark": "NVDA"})[0] == "NVDA"


def test_benchmark_closes_degrades_on_source_failure():
    # Both the DB read and the live fetch raise. The function must degrade to
    # None (and log) without raising — guards against the undefined-logger
    # NameError regression on the critical benchmark path.
    from app import skills

    skills._BENCH_CACHE.clear()
    orig_meta = skills.repo.price_series_meta
    orig_fetch = skills.p_src.fetch_price_history

    def boom(*a, **k):
        raise RuntimeError("network down")

    skills.repo.price_series_meta = boom
    skills.p_src.fetch_price_history = boom
    try:
        out = skills._benchmark_closes("SPY", "1Y")
        assert out is None
    finally:
        skills.repo.price_series_meta = orig_meta
        skills.p_src.fetch_price_history = orig_fetch
        skills._BENCH_CACHE.clear()


def test_benchmark_fetch_window_covers_requested_range():
    # For a 1Y request with no DB history, the live fetch must use a period that
    # covers the full window (not a fixed 6mo), or the window stats are biased.
    import datetime as _dt

    from app import skills

    skills._BENCH_CACHE.clear()
    captured = {}
    orig_meta = skills.repo.price_series_meta
    orig_fetch = skills.p_src.fetch_price_history
    orig_note = skills.repo.note_symbol

    def no_db(*a, **k):
        return {"source": "mock", "points": []}

    def fake_fetch(ticker, period, interval):
        captured["period"] = period
        base = _dt.date(2024, 1, 1)
        pts = [
            {"d": (base + _dt.timedelta(days=i)).isoformat(), "c": 100.0 + i}
            for i in range(400)
        ]
        return {"points": pts}

    skills.repo.price_series_meta = no_db
    skills.p_src.fetch_price_history = fake_fetch
    skills.repo.note_symbol = lambda *a, **k: None
    try:
        out = skills._benchmark_closes("SPY", "1Y")
        assert out is not None and out["source"] == "live"
        assert captured["period"] == "2y"   # >= the 1Y window + lookback
        # 3M must stay modest so we don't over-fetch on short windows.
        skills._BENCH_CACHE.clear()
        skills._benchmark_closes("SPY", "3M")
        assert captured["period"] == "6mo"
    finally:
        skills.repo.price_series_meta = orig_meta
        skills.p_src.fetch_price_history = orig_fetch
        skills.repo.note_symbol = orig_note
        skills._BENCH_CACHE.clear()


# --------------------------- signal builder edge cases ---------------------------
# The pure engine is covered above; these exercise the end-to-end builders
# (build_signal_research / build_signal_scorecard) on bad or thin market data so
# the panels degrade gracefully — a clean error/low-coverage state — instead of
# crashing, leaking NaN/Inf, or silently imputing missing data.
import datetime as _dt  # noqa: E402


def _signal_series(symbols, n, drift=0.001, flat=False, base=100.0):
    """A dated close series per symbol. Each name gets a distinct drift unless
    `flat` is set, in which case every close is identical (degenerate)."""
    base_d = _dt.date(2024, 1, 1)
    dates = [(base_d + _dt.timedelta(days=i)).isoformat() for i in range(n)]
    out = {}
    for k, s in enumerate(symbols):
        d = 0.0 if flat else drift * (k + 1)
        closes = [base]
        for _ in range(1, n):
            closes.append(closes[-1] * (1.0 + d))
        out[s] = [{"t": dd, "c": c} for dd, c in zip(dates, closes)]
    return out


def _patch_signal_repo(series, companies=None, label="test universe"):
    """Point the signal builders at an in-memory cross-section. Returns a
    restore() that puts the real repo / universe resolver back."""
    from app import skills

    syms = list(series.keys())
    orig_resolve = skills._resolve_signal_universe
    orig_bulk = skills.repo.price_closes_bulk
    orig_companies = skills.repo.companies_bulk

    skills._resolve_signal_universe = lambda params: (syms, label)
    skills.repo.price_closes_bulk = lambda symbols, days=400: {
        "series": series, "asOf": "2024-06-01", "source": "mock",
    }
    skills.repo.companies_bulk = lambda symbols: (companies or {})

    def restore():
        skills._resolve_signal_universe = orig_resolve
        skills.repo.price_closes_bulk = orig_bulk
        skills.repo.companies_bulk = orig_companies

    return restore


def _all_finite(obj) -> bool:
    if isinstance(obj, float):
        return math.isfinite(obj)
    if isinstance(obj, dict):
        return all(_all_finite(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return all(_all_finite(v) for v in obj)
    return True


def _validate_panel(model_name, payload):
    """Strip the envelope freshness fields and validate the data payload against
    its panel model — the real 'this panel can render' guarantee."""
    from app import models

    data = dict(payload)
    data.pop("asOf", None)
    data.pop("source", None)
    getattr(models, model_name).model_validate(data)


def test_build_signal_research_raises_on_thin_universe():
    from app import skills

    # Fewer names than quantiles: a cross-sectional signal is not defined.
    restore = _patch_signal_repo(_signal_series(["A", "B", "C"], 300))
    try:
        raised = False
        try:
            skills.build_signal_research({"signal": "momentum"})
        except ValueError:
            raised = True
        assert raised, "expected ValueError on a sub-quantile universe"
    finally:
        restore()


def test_build_signal_scorecard_raises_on_thin_universe():
    from app import skills

    restore = _patch_signal_repo(_signal_series(["A", "B", "C"], 300))
    try:
        raised = False
        try:
            skills.build_signal_scorecard({"signals": ["momentum", "value"]})
        except ValueError:
            raised = True
        assert raised, "expected ValueError on a sub-quantile universe"
    finally:
        restore()


def test_build_signal_research_raises_when_all_names_excluded():
    from app import skills

    # A fundamental signal where EVERY name lacks the required field. Nothing may
    # be imputed, so there is no usable cross-section -> clean failure.
    syms = list("ABCDEF")
    series = _signal_series(syms, 300)
    companies = {s: {"peRatio": None, "netMargin": None} for s in syms}
    restore = _patch_signal_repo(series, companies=companies)
    try:
        raised = False
        try:
            skills.build_signal_research({"signal": "value"})
        except ValueError:
            raised = True
        assert raised, "expected ValueError when every name is excluded (no P/E)"
    finally:
        restore()


def test_build_signal_research_raises_on_short_history():
    from app import skills

    # Every name has only a handful of bars — below the engine's minimum.
    restore = _patch_signal_repo(_signal_series(list("ABCDEF"), 3))
    try:
        raised = False
        try:
            skills.build_signal_research({"signal": "momentum"})
        except ValueError:
            raised = True
        assert raised, "expected ValueError on universally short price history"
    finally:
        restore()


def test_build_signal_research_flat_series_is_clean_low_coverage():
    from app import skills

    # Degenerate (perfectly flat) prices: the signal is computable (so names are
    # NOT excluded / imputed) but uninformative. IC must report n=0 and the
    # spread stats must be flat zeros — never NaN, never a fabricated edge.
    restore = _patch_signal_repo(_signal_series(list("ABCDEF"), 300, flat=True))
    try:
        res = skills.build_signal_research({"signal": "momentum"})
        assert res["included"] == 6
        assert res["excluded"] == 0          # nothing imputed, nothing dropped
        assert res["ic"]["n"] == 0           # no informative IC observations
        assert res["spreadStats"] == {"totalReturn": 0.0, "sharpe": 0.0, "cagr": 0.0}
        assert _all_finite(res), "flat-series payload leaked a NaN/Inf"
        _validate_panel("SignalResearchData", res)
    finally:
        restore()


def test_build_signal_scorecard_degrades_on_bad_coverage():
    from app import skills

    # The scorecard must never crash on a bad signal: each uncomputable signal
    # becomes a zeroed, finite row (clean low-coverage), and the panel validates.
    syms = list("ABCDEF")
    cases = [
        ("all-excluded", _signal_series(syms, 300),
         {s: {"peRatio": None, "netMargin": None} for s in syms}, ["value", "quality"]),
        ("short-history", _signal_series(syms, 3), None, ["momentum"]),
        ("flat-series", _signal_series(syms, 300, flat=True), None, ["momentum", "low_volatility"]),
    ]
    for name, series, companies, signals in cases:
        restore = _patch_signal_repo(series, companies=companies)
        try:
            res = skills.build_signal_scorecard({"signals": signals})
            assert len(res["rows"]) == len(signals), name
            for row in res["rows"]:
                assert row["meanIC"] == 0.0, f"{name}: fabricated IC on no coverage"
            assert _all_finite(res), f"{name}: payload leaked a NaN/Inf"
            _validate_panel("SignalScorecardData", res)
        finally:
            restore()


def _run_all():
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in funcs:
        fn()
        passed += 1
        print(f"  PASS {fn.__name__}")
    print(f"\n{passed}/{len(funcs)} engine tests passed")


if __name__ == "__main__":
    _run_all()
