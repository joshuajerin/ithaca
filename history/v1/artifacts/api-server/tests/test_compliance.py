"""Unit tests for the pre-trade compliance gate engine (pure stdlib).

Runnable two ways:
    python artifacts/api-server/tests/test_compliance.py   # standalone
    pytest artifacts/api-server/tests/test_compliance.py    # if pytest installed

Covers: book metrics (gross/net/leverage/concentration), each limit family's
ok/warn/breach status, restricted (hard) vs watch (soft) list handling, the
global kill switch, and that a clean book passes while a violating one blocks.
"""
from __future__ import annotations

import os
import sys

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app.engine import compliance as comp  # noqa: E402


def test_book_metrics_long_short():
    w = {"AAPL": 0.5, "MSFT": 0.5, "TSLA": -0.5, "NVDA": -0.5}
    m = comp.book_metrics(w)
    assert abs(m["gross"] - 2.0) < 1e-9
    assert abs(m["net"] - 0.0) < 1e-9
    assert abs(m["leverage"] - 2.0) < 1e-9
    assert abs(m["maxPositionPct"] - 50.0) < 1e-9
    assert m["names"] == 4


def test_clean_book_passes():
    # Equal-weight 12-name long-only book: 8.3% each, gross 1.0, net 1.0,
    # top-5 concentration ~41.7% — inside every default limit.
    syms = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META",
            "JPM", "XOM", "JNJ", "PG", "V", "HD"]
    w = {s: 1.0 / len(syms) for s in syms}
    res = comp.evaluate_gate(weights=w)
    assert res["ok"] is True
    assert res["blocked"] is False
    assert res["violations"] == []


def test_position_limit_breach():
    w = {"AAPL": 0.4, "MSFT": 0.6}
    res = comp.evaluate_gate(weights=w, limits={"maxPositionPct": 15.0})
    assert res["blocked"] is True
    pos = next(c for c in res["checks"] if c["key"] == "maxPositionPct")
    assert pos["status"] == "breach"
    assert any("Max position" in v for v in res["violations"])


def test_leverage_breach():
    # Gross 3.0x against a 2.0x cap.
    w = {"AAPL": 1.5, "MSFT": -1.5}
    res = comp.evaluate_gate(weights=w, limits={"maxLeverage": 2.0, "maxPositionPct": 200.0,
                                                "maxNetPct": 500.0, "maxConcentrationPct": 500.0})
    lev = next(c for c in res["checks"] if c["key"] == "maxLeverage")
    assert lev["status"] == "breach"
    assert res["blocked"] is True


def test_net_exposure_breach():
    w = {"AAPL": 0.8, "MSFT": 0.8}  # net 160%
    res = comp.evaluate_gate(weights=w, limits={"maxNetPct": 120.0, "maxPositionPct": 200.0,
                                                "maxLeverage": 5.0, "maxConcentrationPct": 500.0})
    net = next(c for c in res["checks"] if c["key"] == "maxNetPct")
    assert net["status"] == "breach"


def test_concentration_breach():
    # 6 names, top-5 sum to 95% vs a 50% concentration cap.
    w = {"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.2, "E": 0.15, "F": 0.05}
    res = comp.evaluate_gate(weights=w, limits={"maxConcentrationPct": 50.0, "maxPositionPct": 200.0,
                                                "maxNetPct": 500.0, "maxLeverage": 5.0})
    conc = next(c for c in res["checks"] if c["key"] == "maxConcentrationPct")
    assert conc["status"] == "breach"
    assert abs(conc["value"] - 95.0) < 1e-6


def test_warn_band():
    # Position at 14% against a 15% cap -> >= 90% utilization -> warn, not breach.
    w = {"AAPL": 0.14, "MSFT": 0.14, "NVDA": 0.14, "AMZN": 0.14,
         "GOOGL": 0.14, "META": 0.14, "JPM": 0.16}
    res = comp.evaluate_gate(weights=w, limits={"maxPositionPct": 16.5, "maxNetPct": 500.0,
                                                "maxLeverage": 5.0, "maxConcentrationPct": 500.0})
    pos = next(c for c in res["checks"] if c["key"] == "maxPositionPct")
    assert pos["status"] == "warn"
    assert res["ok"] is True  # warnings never block
    assert res["warnings"]


def test_restricted_blocks_watch_warns():
    w = {"AAPL": 0.5, "TSLA": 0.5}
    # Roomy limits so only the list checks are exercised.
    roomy = {"maxPositionPct": 200.0, "maxNetPct": 500.0,
             "maxLeverage": 5.0, "maxConcentrationPct": 500.0}
    res = comp.evaluate_gate(weights=w, limits=roomy, restricted=["tsla"], watch=["aapl"])
    assert res["blocked"] is True
    assert res["restricted"] == ["TSLA"]
    assert res["watch"] == ["AAPL"]
    # Watch alone does not block.
    res2 = comp.evaluate_gate(weights=w, limits=roomy, watch=["aapl"])
    assert res2["ok"] is True
    assert res2["watch"] == ["AAPL"]


def test_kill_switch_blocks_everything():
    syms = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "XOM"]
    w = {s: 1.0 / len(syms) for s in syms}
    res = comp.evaluate_gate(weights=w, kill_switch=True, kill_reason="desk halt")
    assert res["blocked"] is True
    assert res["killSwitch"] is True
    assert any("Kill switch" in v for v in res["violations"])


def test_merge_limits_ignores_bad_values():
    merged = comp.merge_limits({"maxPositionPct": 10.0, "bogus": 1, "maxLeverage": None})
    assert merged["maxPositionPct"] == 10.0
    assert merged["maxLeverage"] == comp.DEFAULT_LIMITS["maxLeverage"]
    assert "bogus" not in merged


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} compliance engine tests passed")


if __name__ == "__main__":
    _run_all()
