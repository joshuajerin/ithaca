"""End-to-end backtest through the Core, on a deterministic network-free panel."""
from __future__ import annotations

import pytest
import numpy as np
from pydantic import ValidationError

from doomberg_core import Core, DataGateway
from doomberg_core.accounting import run_backtest
from doomberg_core.api import Core as CoreCls

from core_helpers import make_fetch


def _spec(**over):
    spec = {
        "spec_version": "1.0",
        "name": "test-momentum",
        "universe": {"symbols": ["AAA", "BBB", "CCC"], "source": "prices"},
        "strategy": {"id": "momentum", "params": {"lookback": 60}},
        "construction": {"scheme": "rank_weight", "long_only": True, "gross": 1.0},
        "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.5},
        "execution": {"cost_bps": 5, "slippage_bps": 2, "algo": "vwap", "rebalance": "monthly@close"},
        "seed": 42,
    }
    spec.update(over)
    return spec


def _core(panel):
    dates, series = panel
    return Core(DataGateway(fetch_history=make_fetch(series, dates))), dates


def test_backtest_runs_end_to_end(panel_3x250):
    core, dates = _core(panel_3x250)
    out = core.backtest_run({"spec": _spec(), "range": "1y"})
    assert out["data"] is not None
    res = out["data"]
    assert len(res["equityCurve"]) == 250
    assert {"sharpe", "cagr", "maxDD", "totalReturn", "vol"} <= set(res["stats"])
    assert res["benchmark"]["name"] == "equal_weight_universe"
    assert {"trackingErrorPct", "informationRatio", "activeTotalReturnPct"} <= set(res["comparison"])
    assert res["execution"]["all_in_cost_bps"] == 7
    assert res["integrity"]["noLookahead"] is True
    assert res["integrity"]["decisionLagBars"] == 1
    assert res["dataQuality"]["pointInTime"] is False
    assert out["provenance"]["source"] == "yahoo-chart"
    assert out["provenance"]["pit"] == "false"  # honest: free data is not point-in-time


def test_backtest_respects_gross_limit(panel_3x250):
    core, _ = _core(panel_3x250)
    out = core.backtest_run({"spec": _spec(construction={"scheme": "equal_weight", "long_only": True, "gross": 1.0},
                                           risk={"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 1.0})})
    final = out["data"]["finalWeights"]
    gross = sum(abs(v) for v in final.values())
    assert gross <= 1.0 + 1e-6
    assert out["data"]["risk"]["ok"] is True


def test_backtest_reports_missing_symbol_not_imputed(panel_3x250):
    core, _ = _core(panel_3x250)
    out = core.backtest_run({"spec": _spec(universe={"symbols": ["AAA", "BBB", "ZZZ"], "source": "prices"})})
    # ZZZ has no data -> reported in coverage, never faked
    assert "ZZZ" in out["provenance"]["coverage"]["missing"]
    assert out["provenance"]["coverage"]["resolved"] == 2


def test_spec_rejects_free_form_code():
    bad = _spec()
    bad["code"] = "import os"
    with pytest.raises(ValidationError):
        CoreCls.validate_spec(bad)


def test_run_tool_dispatch(panel_3x250):
    core, dates = _core(panel_3x250)
    out = core.run_tool("market.get_ohlcv", {"symbol": "AAA", "range": "1y"})
    assert out["provenance"]["source"] == "yahoo-chart"
    assert out["data"]["symbol"] == "AAA"
    with pytest.raises(ValueError):
        core.run_tool("market.nonexistent", {})


def test_market_ohlcv_is_cleaned_and_cached():
    calls = 0

    def fetch(symbol: str, range_: str = "1y", interval: str = "1d") -> dict:
        nonlocal calls
        calls += 1
        assert symbol.upper() == "AAA"
        return {
            "points": [
                {"d": "2024-01-03", "c": 104, "v": 10},
                {"d": "2024-01-02", "c": 102, "v": 10},
                {"d": "2024-01-02", "c": 103, "v": 10},
                {"d": "2024-01-01", "c": 100, "v": 10},
                {"d": "2024-01-04", "c": -1, "v": 10},
            ],
            "quote": {"symbol": "AAA", "price": 104, "asOf": "2024-01-03T20:00:00Z"},
        }

    core = Core(DataGateway(fetch_history=fetch))
    first = core.market_get_ohlcv({"symbol": "AAA", "range": "1y"})
    second = core.market_get_ohlcv({"symbol": "AAA", "range": "1y"})

    assert calls == 1
    assert first["provenance"]["cache_hit"] is False
    assert second["provenance"]["cache_hit"] is True
    assert [p["d"] for p in first["data"]["points"]] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert first["data"]["points"][1]["c"] == 103
    assert first["data"]["quality"] == {
        "raw": 5,
        "clean": 3,
        "dropped": 1,
        "deduped": 1,
        "sorted": True,
        "input_sorted": False,
    }
    assert first["warnings"][0]["code"] == "OHLCV_CLEANED"


def test_slippage_is_applied_as_additional_turnover_cost():
    dates = [f"2024-01-{i:02d}" for i in range(1, 13)]
    a = np.array([100, 110, 100, 110, 100, 110, 100, 110, 100, 110, 100, 110], dtype=float)
    b = np.array([100, 90, 100, 90, 100, 90, 100, 90, 100, 90, 100, 90], dtype=float)
    closes = np.column_stack([a, b])
    spec = _spec(
        universe={"symbols": ["AAA", "BBB"], "source": "prices"},
        strategy={"id": "rank_returns", "params": {"lookback": 1, "top": 1}},
        construction={"scheme": "equal_weight", "long_only": True, "gross": 1.0},
        risk={"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 1.0},
        execution={"cost_bps": 0, "slippage_bps": 0, "algo": "vwap", "rebalance": "daily@close"},
    )

    no_cost = run_backtest(spec, dates, closes, ["AAA", "BBB"])
    spec["execution"]["slippage_bps"] = 100
    with_slippage = run_backtest(spec, dates, closes, ["AAA", "BBB"])

    assert with_slippage["execution"]["all_in_cost_bps"] == 100
    assert with_slippage["execution"]["total_cost_pct"] > 0
    assert with_slippage["equityCurve"][-1]["v"] < no_cost["equityCurve"][-1]["v"]


def test_backtest_accounting_does_not_react_to_future_bars_before_they_arrive():
    dates = [f"2024-02-{i:02d}" for i in range(1, 29)]
    base = np.linspace(100, 130, len(dates))
    closes = np.column_stack([base, 200 - base])
    perturbed = closes.copy()
    future_idx = 18
    perturbed[future_idx:] *= np.array([4.0, 0.25])
    spec = _spec(
        universe={"symbols": ["AAA", "BBB"], "source": "prices"},
        strategy={"id": "rank_returns", "params": {"lookback": 3, "top": 1}},
        construction={"scheme": "equal_weight", "long_only": True, "gross": 1.0},
        risk={"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 1.0},
        execution={"cost_bps": 0, "slippage_bps": 0, "algo": "vwap", "rebalance": "daily@close"},
    )

    original = run_backtest(spec, dates, closes, ["AAA", "BBB"])
    shocked = run_backtest(spec, dates, perturbed, ["AAA", "BBB"])

    assert original["integrity"]["noLookahead"] is True
    assert original["equityCurve"][:future_idx] == shocked["equityCurve"][:future_idx]
    assert original["comparisonCurve"][:future_idx] == shocked["comparisonCurve"][:future_idx]
