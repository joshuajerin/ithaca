"""Unit tests for the stress-testing primitives (app.engine.stress).

Runnable two ways:
    python artifacts/api-server/tests/test_stress.py   # standalone
    pytest artifacts/api-server/tests/test_stress.py    # if pytest installed

Covers: the factor/asset shock identity (book pnl == Sigma exposure*shock),
ignoring of unknown factors/names, and historical replay coverage/missing
accounting plus the point-to-point P&L and drawdown arithmetic.
"""
from __future__ import annotations

import math
import os
import sys

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app.engine import stress  # noqa: E402


# --------------------------- factor shocks ---------------------------
def test_factor_shock_identity():
    exposures = {"Market": 1.2, "Momentum": -0.4, "Value": 0.3}
    shocks = {"Market": -10.0, "Momentum": -8.0}
    out = stress.factor_shock_pnl(exposures, shocks)
    # 1.2 * -10% + -0.4 * -8% = -12% + 3.2% = -8.8%
    assert math.isclose(out["totalPnlPct"], -8.8, abs_tol=1e-6)
    assert len(out["contributions"]) == 2


def test_factor_shock_ignores_unknown_factor():
    out = stress.factor_shock_pnl({"Market": 1.0}, {"Nonexistent": -50.0})
    assert out["totalPnlPct"] == 0.0
    assert out["contributions"] == []


def test_asset_shock_identity_and_case_insensitive():
    weights = {"NVDA": 0.2, "AAPL": -0.1}
    out = stress.asset_shock_pnl(weights, {"nvda": -20.0, "aapl": -20.0})
    # 0.2 * -20% + -0.1 * -20% = -4% + 2% = -2%
    assert math.isclose(out["totalPnlPct"], -2.0, abs_tol=1e-6)


# --------------------------- historical replay ---------------------------
def _ramp(start_price, daily, days, start_iso="2020-03-01"):
    """A simple deterministic close series stepping by a fixed daily return."""
    import datetime

    d0 = datetime.date.fromisoformat(start_iso)
    out = {}
    px = float(start_price)
    for i in range(days):
        out[(d0 + datetime.timedelta(days=i)).isoformat()] = round(px, 6)
        px *= 1.0 + daily
    return out


def test_replay_covered_and_missing():
    weights = {"AAA": 0.5, "BBB": 0.5, "CCC": 0.5}
    closes = {
        "AAA": _ramp(100, -0.02, 10),   # falls ~ -2%/day
        "BBB": _ramp(100, 0.01, 10),    # rises ~ +1%/day
        # CCC: only a couple of points in window -> uncovered
        "CCC": {"2020-03-01": 100.0, "2020-03-02": 99.0},
    }
    out = stress.replay_window(weights, closes, "2020-03-01", "2020-03-31")
    assert out is not None
    assert set(out["covered"]) == {"AAA", "BBB"}
    assert out["missing"] == ["CCC"]
    # Book point-to-point P&L = 0.5*ret_AAA + 0.5*ret_BBB
    ds_a = sorted(closes["AAA"])
    ret_a = closes["AAA"][ds_a[-1]] / closes["AAA"][ds_a[0]] - 1.0
    ret_b = closes["BBB"][ds_a[-1]] / closes["BBB"][ds_a[0]] - 1.0
    expected = (0.5 * ret_a + 0.5 * ret_b) * 100.0
    assert math.isclose(out["bookPnlPct"], round(expected, 2), abs_tol=0.05)
    # A falling-heavy book should show a non-zero drawdown.
    assert out["maxDrawdownPct"] <= 0.0
    # perHolding sorted most-negative first.
    assert out["perHolding"][0]["symbol"] == "AAA"


def test_replay_returns_none_when_no_coverage():
    weights = {"AAA": 1.0}
    closes = {"AAA": {"2019-01-01": 100.0}}
    assert stress.replay_window(weights, closes, "2020-01-01", "2020-12-31") is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok   {t.__name__}")
        except AssertionError as exc:  # noqa: PERF203
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
