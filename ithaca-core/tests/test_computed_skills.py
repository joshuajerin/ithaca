"""Tests for the COMPUTED skill catalog (source="computed").

These skills run real, deterministic math — Black-Scholes, realized vol, correlation,
factor exposures, mean-variance optimization, Monte-Carlo (fixed seed), DCF, stress and
scenario projections. Agent-supplied inputs carry ``inputs="agent"``; computations over real
archive series carry ``inputs="ithaca-v1-archive"`` and the archive freshness. Numeric
assertions (put-call parity, IV round-trips, realized_vol>0, symmetric correlation, weights
sum to 1) verify the math, not just the envelope shape.
"""
from __future__ import annotations

import math

import pytest

from ithaca_core import SkillSet
from ithaca_core.skills import compute
from fake_archive import FakeArchive


@pytest.fixture
def skills() -> SkillSet:
    return SkillSet(FakeArchive())


def _assert_computed(out: dict, *, inputs: str | None = None) -> None:
    assert set(out) >= {"data", "provenance", "partial", "warnings"}
    prov = out["provenance"]
    assert prov["source"] == "computed"
    assert prov["pit"] == "false"
    assert prov["freshness"] in {"live", "stale"}
    assert "as_of" in prov
    assert "coverage" in prov
    assert "cost" in prov
    if inputs is not None:
        assert prov.get("inputs") == inputs
    assert isinstance(out["warnings"], list)


# ----------------------------- options.* (agent inputs) -----------------------------
def test_options_greeks_call_price_and_delta(skills):
    out = skills.options_greeks({"S": 100, "K": 100, "T": 1.0, "r": 0.05, "sigma": 0.2, "type": "call"})
    _assert_computed(out, inputs="agent")
    d = out["data"]
    # Reference BS ATM 1y call value ~10.45.
    assert d["price"] == pytest.approx(10.4506, abs=1e-3)
    assert 0.0 < d["greeks"]["delta"] < 1.0
    assert d["greeks"]["gamma"] > 0
    assert d["greeks"]["vega"] > 0


def test_options_greeks_put_call_parity(skills):
    args = {"S": 120, "K": 100, "T": 0.75, "r": 0.03, "sigma": 0.35}
    call = skills.options_greeks({**args, "type": "call"})["data"]["price"]
    put = skills.options_greeks({**args, "type": "put"})["data"]["price"]
    # C - P == S - K e^{-rT}
    parity = 120 - 100 * math.exp(-0.03 * 0.75)
    assert (call - put) == pytest.approx(parity, abs=1e-3)


def test_options_implied_vol_round_trips(skills):
    # Price a known option, then recover its sigma from that price.
    price = compute.bs_price(100, 95, 0.5, 0.02, 0.28, "call")
    out = skills.options_implied_vol({"price": price, "S": 100, "K": 95, "T": 0.5, "r": 0.02, "type": "call"})
    _assert_computed(out, inputs="agent")
    assert out["data"]["impliedVol"] == pytest.approx(0.28, abs=1e-3)


def test_options_implied_vol_below_intrinsic_warns(skills):
    # A call priced below intrinsic (S-K=10) has no implied vol.
    out = skills.options_implied_vol({"price": 1.0, "S": 110, "K": 100, "T": 0.5, "r": 0.0, "type": "call"})
    assert out["data"]["impliedVol"] is None
    assert out["warnings"][0]["code"] == "NO_SOLUTION"


# ----------------------------- vol.* (archive series) -----------------------------
def test_vol_realized_is_positive(skills):
    out = skills.vol_realized({"symbol": "LONG"})
    _assert_computed(out, inputs="ithaca-v1-archive")
    assert out["data"]["realizedVol"] > 0
    assert out["data"]["observations"] > 200
    assert out["provenance"]["freshness"]  # archive freshness rides along


def test_vol_realized_respects_lookback(skills):
    full = skills.vol_realized({"symbol": "LONG"})["data"]["observations"]
    short = skills.vol_realized({"symbol": "LONG", "lookback": 30})["data"]["observations"]
    assert short == 30 < full


def test_vol_term_structure_windows(skills):
    out = skills.vol_term_structure({"symbol": "LONG"})
    _assert_computed(out, inputs="ithaca-v1-archive")
    windows = [p["window"] for p in out["data"]["points"]]
    assert windows == [20, 60, 120, 252]
    solved = [p for p in out["data"]["points"] if p["realizedVol"] is not None]
    assert solved and all(p["realizedVol"] > 0 for p in solved)


def test_vol_realized_short_history_warns(skills):
    # NVDA has only 4 closes — realized vol still solves, but a 252-window does not.
    out = skills.vol_term_structure({"symbol": "NVDA"})
    big = next(p for p in out["data"]["points"] if p["window"] == 252)
    assert big["realizedVol"] is None


# ----------------------------- correlation.matrix -----------------------------
def test_correlation_matrix_symmetric_unit_diagonal(skills):
    out = skills.correlation_matrix({"symbols": ["LONG", "LONG2"]})
    _assert_computed(out, inputs="ithaca-v1-archive")
    syms = out["data"]["symbols"]
    m = out["data"]["matrix"]
    assert syms == ["LONG", "LONG2"]
    for i in range(len(syms)):
        assert m[i][i] == pytest.approx(1.0)
        for j in range(len(syms)):
            assert m[i][j] == pytest.approx(m[j][i])  # symmetric
            assert -1.0 - 1e-9 <= m[i][j] <= 1.0 + 1e-9
    assert out["data"]["pairs"][0]["a"] == "LONG" and out["data"]["pairs"][0]["b"] == "LONG2"


def test_correlation_matrix_needs_two_symbols(skills):
    with pytest.raises(ValueError):
        skills.correlation_matrix({"symbols": ["LONG"]})


# ----------------------------- factor.exposures -----------------------------
def test_factor_exposures_zscored_matrix(skills):
    out = skills.factor_exposures({"symbols": ["NVDA", "AMD", "TSM"]})
    _assert_computed(out, inputs="ithaca-v1-archive")
    assert out["data"]["factors"] == ["Market", "Size", "Value", "Momentum", "Quality"]
    rows = out["data"]["rows"]
    assert len(rows) == 3
    # cross-sectional z-scores: each factor column is centered (mean ~ 0) and winsorized to +/-3.
    for factor in out["data"]["factors"]:
        col = [r["exposures"][factor] for r in rows]
        assert sum(col) == pytest.approx(0.0, abs=1e-5)
        assert all(-3.0 - 1e-9 <= v <= 3.0 + 1e-9 for v in col)


def test_factor_exposures_reports_missing(skills):
    out = skills.factor_exposures({"symbols": ["NVDA", "AMD", "ZZZZ"]})
    assert out["warnings"] and out["warnings"][0]["code"] == "PARTIAL_COVERAGE"
    assert "ZZZZ" in out["warnings"][0]["scope"]


# ----------------------------- dcf.value -----------------------------
def test_dcf_value_implied_price_and_upside(skills):
    out = skills.dcf_value({"symbol": "NVDA"})
    _assert_computed(out, inputs="ithaca-v1-archive")
    val = out["data"]["valuation"]
    assert val["impliedPrice"] > 0
    assert len(val["projections"]) == 5
    assert val["sensitivity"]  # WACC x exit-multiple grid
    assert out["data"]["impliedUpsidePct"] is not None


def test_dcf_value_honors_agent_assumptions(skills):
    low = skills.dcf_value({"symbol": "NVDA", "assumptions": {"wacc": 15.0, "revenueGrowth": 2.0}})
    high = skills.dcf_value({"symbol": "NVDA", "assumptions": {"wacc": 7.0, "revenueGrowth": 25.0}})
    # Lower discount rate + higher growth => higher implied price.
    assert high["data"]["valuation"]["impliedPrice"] > low["data"]["valuation"]["impliedPrice"]


def test_dcf_value_seeds_shares_from_mcap_over_price(skills):
    out = skills.dcf_value({"symbol": "NVDA"})
    # NVDA fixture: mcap 3.5e12 / price 150 = ~2.333e10 shares.
    assert out["data"]["inputs"]["shares"] == pytest.approx(3.5e12 / 150.0, rel=1e-6)


# ----------------------------- portfolio.optimize -----------------------------
def test_portfolio_optimize_weights_sum_to_one_long_only(skills):
    out = skills.portfolio_optimize({"symbols": ["LONG", "LONG2"], "mode": "min_variance"})
    _assert_computed(out, inputs="ithaca-v1-archive")
    weights = out["data"]["weights"]
    assert {w["symbol"] for w in weights} == {"LONG", "LONG2"}
    assert out["data"]["sumWeights"] == pytest.approx(1.0, abs=1e-4)
    assert all(w["weight"] >= -1e-9 for w in weights)  # long-only
    assert out["data"]["longOnly"] is True


def test_portfolio_optimize_max_sharpe_default(skills):
    out = skills.portfolio_optimize({"symbols": ["LONG", "LONG2"]})
    assert out["data"]["mode"] == "max_sharpe"
    s = out["data"]["stats"]
    assert {"expReturn", "vol", "sharpe", "gross", "net"} <= set(s)
    assert s["net"] == pytest.approx(1.0, abs=1e-4)


def test_portfolio_optimize_needs_two(skills):
    with pytest.raises(ValueError):
        skills.portfolio_optimize({"symbols": ["LONG"]})


# ----------------------------- montecarlo.simulate -----------------------------
def test_montecarlo_simulate_is_deterministic_with_seed(skills):
    a = skills.montecarlo_simulate({"symbol": "LONG", "seed": 99, "paths": 500, "horizon": 60})
    b = skills.montecarlo_simulate({"symbol": "LONG", "seed": 99, "paths": 500, "horizon": 60})
    _assert_computed(a, inputs="ithaca-v1-archive")
    assert a["data"]["summary"] == b["data"]["summary"]  # same seed => identical
    fan = a["data"]["fan"]
    assert fan[0]["step"] == 0
    # percentile fan is ordered p5 <= p50 <= p95 at the terminal step
    last = fan[-1]
    assert last["p5"] <= last["p50"] <= last["p95"]


def test_montecarlo_simulate_agent_inputs_gbm(skills):
    out = skills.montecarlo_simulate({"sigma": 0.3, "drift": 0.08, "S": 100.0, "seed": 7,
                                      "paths": 400, "horizon": 120})
    _assert_computed(out, inputs="agent")
    assert out["data"]["symbol"] is None
    assert out["data"]["summary"]["paths"] == 400
    assert out["data"]["startValue"] == pytest.approx(100.0)


def test_montecarlo_simulate_short_history_warns(skills):
    out = skills.montecarlo_simulate({"symbol": "NVDA", "seed": 1})  # only 4 closes -> 3 returns
    assert out["data"]["summary"] is None
    assert out["warnings"][0]["code"] == "PARTIAL_COVERAGE"


# ----------------------------- scenario.project -----------------------------
def test_scenario_project_baseline_and_scenario(skills):
    out = skills.scenario_project({"symbol": "LONG", "scenarioDriftPct": 12.0, "seed": 5,
                                   "paths": 400, "horizon": 60})
    _assert_computed(out, inputs="ithaca-v1-archive")
    assert out["data"]["baseline"] is not None and out["data"]["scenario"] is not None
    # A positive incremental drift lifts the scenario terminal above baseline.
    assert out["data"]["scenario"]["deltaPct"] == pytest.approx(
        out["data"]["scenario"]["expectedReturnPct"] - out["data"]["baseline"]["expectedReturnPct"],
        abs=0.5)
    assert out["data"]["scenario"]["endValue"] > out["data"]["baseline"]["endValue"]


def test_scenario_project_deterministic(skills):
    a = skills.scenario_project({"symbol": "LONG", "scenarioDriftPct": 5.0, "seed": 3, "paths": 300})
    b = skills.scenario_project({"symbol": "LONG", "scenarioDriftPct": 5.0, "seed": 3, "paths": 300})
    assert a["data"]["baseline"] == b["data"]["baseline"]


# ----------------------------- risk.stress -----------------------------
def test_risk_stress_factor_shocks(skills):
    out = skills.risk_stress({"exposures": {"Market": 1.0, "Momentum": 0.3},
                              "shocks": {"Market": -10.0, "Momentum": -5.0}})
    _assert_computed(out, inputs="agent")
    assert out["data"]["kind"] == "factor"
    # Market: 1.0 * -10% = -10%; Momentum: 0.3 * -5% = -1.5%; total = -11.5%.
    assert out["data"]["totalPnlPct"] == pytest.approx(-11.5, abs=1e-6)


def test_risk_stress_asset_shocks(skills):
    out = skills.risk_stress({"weights": {"NVDA": 0.6, "AMD": 0.4},
                              "shocks": {"NVDA": -20.0, "AMD": 10.0}})
    assert out["data"]["kind"] == "asset"
    # 0.6 * -20% + 0.4 * 10% = -12% + 4% = -8%.
    assert out["data"]["totalPnlPct"] == pytest.approx(-8.0, abs=1e-6)


def test_risk_stress_needs_shocks(skills):
    with pytest.raises(ValueError):
        skills.risk_stress({"exposures": {"Market": 1.0}})


# ----------------------------- market.tide -----------------------------
def test_market_tide_fallback_uses_postgres_safe_interval():
    class RowsOnlyArchive:
        def __init__(self):
            self.calls = []

        def _rows(self, sql, params):
            self.calls.append((sql, params))
            return [
                {"ticker": "AAA", "trade_date": "2024-01-01", "close": 100.0, "volume": 1000.0},
                {"ticker": "AAA", "trade_date": "2024-01-02", "close": 110.0, "volume": 1200.0},
                {"ticker": "BBB", "trade_date": "2024-01-01", "close": 100.0, "volume": 900.0},
                {"ticker": "BBB", "trade_date": "2024-01-02", "close": 90.0, "volume": 800.0},
            ]

    archive = RowsOnlyArchive()
    out = SkillSet(archive).market_tide({"lookback": 5})

    sql, params = archive.calls[0]
    assert "INTERVAL %s" not in sql
    assert "%s::int * INTERVAL '1 day'" in sql
    assert params == (205,)
    assert out["warnings"] == []
    assert out["data"]["advancing"] == 1
    assert out["data"]["declining"] == 1


# ----------------------------- tearsheet -----------------------------
def test_tearsheet_runs_backtest_over_archive(skills):
    out = skills.tearsheet({"symbol": "LONG", "strategy": "buy_and_hold"})
    _assert_computed(out, inputs="ithaca-v1-archive")
    ts = out["data"]
    assert ts["stats"] and ts["curve"]
    assert ts["barCount"] > 200
    assert "drawdown" in ts


def test_tearsheet_short_history_warns(skills):
    out = skills.tearsheet({"symbol": "TSM"})  # only 4 closes -> still >=3, runs
    # 4 closes is enough for run_backtest (>=3), so this should produce a tearsheet.
    assert out["data"]["barCount"] == 4


def test_tearsheet_too_short_warns(skills):
    # A symbol with no archive data at all -> PARTIAL_COVERAGE.
    out = skills.tearsheet({"symbol": "ZZZZ"})
    assert out["data"]["tearsheet"] is None
    assert out["warnings"][0]["code"] == "PARTIAL_COVERAGE"


# ----------------------------- walkforward.run -----------------------------
def test_walkforward_run_has_coverage_block(skills):
    out = skills.walkforward_run({"symbol": "LONG", "strategy": "momentum"})
    _assert_computed(out, inputs="ithaca-v1-archive")
    assert "coverage" in out["data"]
    assert out["data"]["coverage"]["usable"] is True  # 300 bars supports folds


def test_walkforward_run_short_history_coverage_unusable(skills):
    out = skills.walkforward_run({"symbol": "NVDA"})  # 4 bars -> not enough folds
    # run_walk_forward still returns (>=3 bars) but flags coverage.usable False.
    assert out["data"]["coverage"]["usable"] is False
