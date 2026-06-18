"""End-to-end backtest through the Core, on a deterministic network-free panel."""
from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from doomberg_core import Core, DataGateway
from doomberg_core.api import Core as CoreCls

from conftest import make_fetch


def _spec(**over):
    spec = {
        "spec_version": "1.0",
        "name": "test-momentum",
        "universe": {"symbols": ["AAA", "BBB", "CCC"], "source": "prices"},
        "strategy": {"id": "momentum", "params": {"lookback": 60}},
        "construction": {"scheme": "rank_weight", "long_only": True, "gross": 1.0},
        "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.5},
        "execution": {"cost_bps": 5, "algo": "vwap", "rebalance": "monthly@close"},
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
