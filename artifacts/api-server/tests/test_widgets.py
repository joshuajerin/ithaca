"""Unit tests for widget timeframe correctness.

Runnable two ways:
    python artifacts/api-server/tests/test_widgets.py     # standalone
    pytest artifacts/api-server/tests/test_widgets.py      # if pytest installed

Covers the day-vs-period returns fix: the pure period-return math, the repo
return paths (single + bulk), and that each builder exposes correctly-labeled
timeframes so a 1-year figure is never read as a 1-day move.
"""
from __future__ import annotations

import os
import sys

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import repo, returns, skills  # noqa: E402


def _series(closes, start_year=2024, start_month=1):
    """Build a daily {t, c} series of len(closes) calendar days."""
    from datetime import date, timedelta

    d0 = date(start_year, start_month, 1)
    return [
        {"t": (d0 + timedelta(days=i)).isoformat(), "c": float(c)}
        for i, c in enumerate(closes)
    ]


# --------------------------- pure period returns ---------------------------
def test_period_returns_basic_windows():
    # 400 calendar days, +1 unit/day from 100 -> covers 1M / 1Y / YTD.
    closes = [100.0 + i for i in range(400)]
    pts = _series(closes)
    out = returns.compute_period_returns(pts, windows=("1M", "1Y"))
    last = closes[-1]
    # 1M ~ 30 calendar days back.
    ref_1m = closes[-31]
    assert abs(out["1M"] - round((last - ref_1m) / ref_1m * 100, 2)) < 0.5
    # 1Y ~ 365 days back.
    ref_1y = closes[-366]
    assert abs(out["1Y"] - round((last - ref_1y) / ref_1y * 100, 2)) < 0.5
    # The 1Y window must be materially larger than the 1-day move here.
    one_day = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
    assert out["1Y"] > one_day * 10


def test_period_returns_none_when_history_too_short():
    pts = _series([100.0, 101.0, 102.0])  # only 3 days
    out = returns.compute_period_returns(pts, windows=("1M", "1Y"))
    assert out["1M"] is None
    assert out["1Y"] is None


def test_period_returns_ytd_anchors_prior_year_end():
    # Dec 30 .. into Jan: YTD should anchor to the last close of the prior year.
    closes = [50.0, 51.0, 52.0, 60.0, 66.0]  # Dec 30, Dec 31, Jan 1, Jan 2, Jan 3
    pts = _series(closes, start_year=2023, start_month=12)
    pts = pts[:2] + [
        {"t": "2024-01-01", "c": 52.0},
        {"t": "2024-01-02", "c": 60.0},
        {"t": "2024-01-03", "c": 66.0},
    ]
    out = returns.compute_period_returns(pts, windows=("YTD",))
    # last=66 vs prior-year-end close 51 (Dec 31, 2023).
    assert abs(out["YTD"] - round((66.0 - 51.0) / 51.0 * 100, 2)) < 0.01


def test_period_returns_empty_series():
    out = returns.compute_period_returns([], windows=("1M", "YTD", "1Y"))
    assert out == {"1M": None, "YTD": None, "1Y": None}


# --------------------------- repo paths ---------------------------
def test_repo_period_returns_single_is_deterministic():
    a = repo.period_returns("NVDA", windows=("1M", "YTD", "1Y"))
    b = repo.period_returns("NVDA", windows=("1M", "YTD", "1Y"))
    assert a["returns"] == b["returns"]
    assert set(a["returns"].keys()) == {"1M", "YTD", "1Y"}
    assert a["source"] in ("live", "mock")


def test_repo_period_returns_bulk_matches_single():
    syms = repo.symbols_in_sector(repo.resolve_sector("ai_tech"))[:5]
    bulk = repo.period_returns_bulk(syms, windows=("YTD",))
    assert set(bulk.keys()) >= {s.upper() for s in syms}
    for s in syms:
        single = repo.period_returns(s, windows=("YTD",))["returns"]["YTD"]
        assert bulk[s.upper()]["YTD"] == single


# --------------------------- builders ---------------------------
def test_screener_rows_carry_labeled_ytd():
    out = skills.build_screener({"sector": "ai_tech"})
    assert out["rows"], "screener returned no rows"
    for row in out["rows"]:
        assert "changePct" in row  # 1-day move
        assert "retYTD" in row     # explicit year-to-date return field
    # At least some names should have a computable YTD return.
    assert any(r["retYTD"] is not None for r in out["rows"])
    # The YTD figure should generally not equal the 1-day move.
    diffs = [r for r in out["rows"] if r["retYTD"] is not None and abs(r["retYTD"] - r["changePct"]) > 0.01]
    assert diffs, "YTD returns suspiciously identical to 1D changes"


def test_heatmap_cells_carry_labeled_ytd():
    out = skills.build_heatmap({"sector": "ai_tech"})
    assert out["cells"], "heatmap returned no cells"
    for cell in out["cells"]:
        assert "changePct" in cell
        assert "retYTD" in cell
    assert any(c["retYTD"] is not None for c in out["cells"])


def test_fundamentals_has_explicit_return_metrics():
    out = skills.build_fundamentals({"symbol": "NVDA"})
    labels = {m["label"] for m in out["metrics"]}
    assert {"Return (1M)", "Return (YTD)", "Return (1Y)"} <= labels
    # Day change must be labeled as 1D, not an ambiguous "Day change %".
    last_price = next(m for m in out["metrics"] if m["label"] == "Last Price")
    assert "1D" in (last_price["hint"] or "")


def test_company_analytics_exposes_returns_block():
    out = skills.build_company_analytics({"symbol": "NVDA"})
    assert "returns" in out
    assert set(out["returns"].keys()) == {"1D", "1M", "YTD", "1Y"}
    # 1D in the returns block should match the headline day move.
    assert out["returns"]["1D"] == out["priceTrendPct"]


def test_price_chart_change_is_period_return_over_range():
    out = skills.build_price_chart({"symbol": "NVDA", "range": "1Y"})
    assert out["range"] == "1Y"
    pts = out["points"]
    assert pts, "price chart returned no points"
    # changePct must reflect first->last over the range, not a 1-day move.
    expected = round((out["last"] - pts[0]["c"]) / pts[0]["c"] * 100, 2)
    assert abs(out["changePct"] - expected) < 0.02


def _run_all():
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in funcs:
        fn()
        passed += 1
        print(f"  PASS {fn.__name__}")
    print(f"\n{passed}/{len(funcs)} widget tests passed")


if __name__ == "__main__":
    _run_all()
