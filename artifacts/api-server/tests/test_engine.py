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
