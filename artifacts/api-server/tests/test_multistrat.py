"""Unit tests for the multi-strategy capital allocation & firm-level risk pillar.

Runnable two ways:
    python artifacts/api-server/tests/test_multistrat.py   # standalone
    pytest artifacts/api-server/tests/test_multistrat.py    # if pytest installed

Everything runs offline: real prices/closes are stubbed and the strategy store
is forced to its in-memory fallback, so nothing touches the network or a live
database. Synthetic-but-realistic daily NAV snapshots are injected directly into
the store so the cross-strategy correlation / covariance / risk-decomposition /
allocation math is genuinely exercised (the dev DB rarely has snapshot history).
"""
from __future__ import annotations

import contextlib
import datetime
import math
import os
import sys

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import multistrat, repo, strategy_store  # noqa: E402
from app.strategy_store import db as _store_db  # noqa: E402

_PRICES = {"AAA": 100.0, "BBB": 50.0, "CCC": 200.0, "DDD": 75.0}


def _stub_get_company(symbol):
    s = (symbol or "").upper()
    if s in _PRICES:
        return {"symbol": s, "name": f"{s} Corp", "price": _PRICES[s]}
    return None


def _stub_all_companies():
    return {s: {"name": f"{s} Corp", "price": p} for s, p in _PRICES.items()}


def _stub_series(sym, n=8):
    base = _PRICES.get(sym.upper(), 100.0)
    d0 = datetime.date.today()
    pts, px = [], base
    for i in range(n):
        pts.append({"t": (d0 + datetime.timedelta(days=i)).isoformat(), "c": round(px, 4)})
        px *= 1.01
    return pts


def _stub_price_closes_bulk(symbols, days=220):
    return {
        "series": {s.upper(): _stub_series(s) for s in symbols},
        "source": "mock",
        "asOf": datetime.date.today().isoformat(),
    }


@contextlib.contextmanager
def store_env():
    """Force the in-memory store + price stubs; restore globals on exit."""
    saved = {
        "get_company": repo.get_company,
        "all_symbols": repo.all_symbols,
        "get_all_companies": repo.get_all_companies,
        "price_closes_bulk": repo.price_closes_bulk,
        "db_available": _store_db.db_available,
        "schema_ready": strategy_store._schema_ready,
        "snap_schema_ready": strategy_store._snap_schema_ready,
    }
    repo.get_company = _stub_get_company
    repo.all_symbols = lambda: list(_PRICES.keys())
    repo.get_all_companies = _stub_all_companies
    repo.price_closes_bulk = _stub_price_closes_bulk
    _store_db.db_available = lambda: False
    strategy_store._mem.clear()
    strategy_store._snap_mem.clear()
    strategy_store._schema_ready = False
    strategy_store._snap_schema_ready = False
    try:
        yield
    finally:
        repo.get_company = saved["get_company"]
        repo.all_symbols = saved["all_symbols"]
        repo.get_all_companies = saved["get_all_companies"]
        repo.price_closes_bulk = saved["price_closes_bulk"]
        _store_db.db_available = saved["db_available"]
        strategy_store._schema_ready = saved["schema_ready"]
        strategy_store._snap_schema_ready = saved["snap_schema_ready"]
        strategy_store._mem.clear()
        strategy_store._snap_mem.clear()


def _add_sleeve(sid, name, stage, positions, capital=1_000_000.0):
    cost = sum(p["shares"] * p["entryPrice"] for p in positions)
    strategy_store.upsert({
        "id": sid, "name": name, "signal": "momentum", "stage": stage,
        "capital": capital, "cash": capital - cost,
        "inception_date": datetime.date.today().isoformat(),
        "positions": positions, "construction": {"universe": "U"},
        "target_weights": None, "promotion_criteria": None,
        "stage_history": [{"stage": stage, "at": "2026-01-01"}], "notes": None,
    })


def _inject_navs(sid, navs, start_capital=1_000_000.0, days_back=None):
    """Write a daily NAV series for a sleeve into the store."""
    n = len(navs)
    d0 = datetime.date.today() - datetime.timedelta(days=(days_back or n))
    for i, nav in enumerate(navs):
        d = (d0 + datetime.timedelta(days=i)).isoformat()
        pnl = round(nav - start_capital, 2)
        strategy_store.record_snapshot(
            sid, d, nav=float(nav), pnl=pnl,
            pnl_pct=round((nav / start_capital - 1.0) * 100.0, 2),
            cash=0.0, capital=start_capital, stage="paper", source="live",
        )


def _nav_path(start, daily_rets):
    out, lvl = [start], float(start)
    for r in daily_rets:
        lvl *= (1.0 + r)
        out.append(round(lvl, 2))
    return out


# =========================================================================
# Tests
# =========================================================================
def test_no_sleeves_degrades_cleanly():
    with store_env():
        p = multistrat.firm_payload()
        assert p["count"] == 0
        assert p["sleeves"] == []
        assert p["combined"] is None and p["risk"] is None and p["allocation"] is None
        assert p["note"] and "No paper or live" in p["note"]
        # Methods metadata is always present so the UI can render the toggle.
        assert {m["id"] for m in p["methods"]} == {"equal_weight", "risk_parity", "target_risk"}
    print("OK no_sleeves_degrades_cleanly")


def test_combined_book_aggregates_real_marks():
    with store_env():
        _add_sleeve("s-a", "Alpha", "paper",
                    [{"symbol": "AAA", "shares": 1000, "entryPrice": 90.0}])
        _add_sleeve("s-b", "Beta", "live",
                    [{"symbol": "AAA", "shares": 500, "entryPrice": 95.0},
                     {"symbol": "BBB", "shares": 2000, "entryPrice": 48.0}])
        # A research sleeve must NOT be treated as a firm sleeve.
        _add_sleeve("s-c", "Gamma", "research",
                    [{"symbol": "CCC", "shares": 100, "entryPrice": 100.0}])

        p = multistrat.firm_payload()
        assert p["count"] == 2  # only paper + live
        names = {s["name"] for s in p["sleeves"]}
        assert names == {"Alpha", "Beta"}

        c = p["combined"]
        assert c is not None and c["sleeveCount"] == 2
        # Firm NAV = sum of each sleeve's book value (marks + cash).
        # Alpha: 1000*100 + (1,000,000-90,000) cash = 100,000 + 910,000 = 1,010,000
        # Beta:  500*100 + 2000*50 + (1,000,000 - (47,500+96,000)) cash
        #        = 50,000 + 100,000 + 856,500 = 1,006,500
        assert abs(c["nav"] - (1_010_000 + 1_006_500)) < 1.0
        # Exposures are NETTED by symbol across sleeves: AAA appears in both.
        aaa = [e for e in c["exposures"] if e["symbol"] == "AAA"]
        assert len(aaa) == 1
        assert abs(aaa[0]["marketValue"] - (1000 * 100 + 500 * 100)) < 1.0
        assert c["source"] if False else p["source"] in ("live", "mock")
    print("OK combined_book_aggregates_real_marks")


def test_thin_history_sleeve_is_held_out_not_faked():
    with store_env():
        _add_sleeve("s-a", "Alpha", "paper",
                    [{"symbol": "AAA", "shares": 1000, "entryPrice": 90.0}])
        _add_sleeve("s-b", "Beta", "paper",
                    [{"symbol": "BBB", "shares": 2000, "entryPrice": 48.0}])
        _add_sleeve("s-thin", "Newbie", "paper",
                    [{"symbol": "CCC", "shares": 100, "entryPrice": 190.0}])

        # Two sleeves with plenty of overlapping history...
        ra = [0.004, -0.002, 0.006, -0.001, 0.003, 0.002, -0.004, 0.005, 0.001]
        rb = [-0.003, 0.005, -0.002, 0.004, -0.001, 0.003, 0.002, -0.005, 0.002]
        _inject_navs("s-a", _nav_path(1_000_000, ra))
        _inject_navs("s-b", _nav_path(1_000_000, rb))
        # ...and one with only 2 points (below MIN_POINTS).
        _inject_navs("s-thin", _nav_path(1_000_000, [0.01]))

        p = multistrat.firm_payload(method="risk_parity")
        # All three still appear in the firm book.
        assert p["count"] == 3
        # The thin sleeve is flagged and excluded from the risk/alloc math.
        excl_names = {e["name"] for e in p["excluded"]}
        assert "Newbie" in excl_names
        # The risk model is built only from the eligible, overlapping sleeves.
        assert p["risk"] is not None and p["allocation"] is not None
        assert p["allocation"]["investableSleeves"] == 2
        newbie = next(s for s in p["sleeves"] if s["name"] == "Newbie")
        assert newbie["recommended"] is None  # never imputed
        assert not newbie["eligible"]
    print("OK thin_history_sleeve_is_held_out_not_faked")


def test_risk_decomposition_and_correlation_real():
    with store_env():
        _add_sleeve("s-a", "Alpha", "paper",
                    [{"symbol": "AAA", "shares": 1000, "entryPrice": 90.0}])
        _add_sleeve("s-b", "Beta", "paper",
                    [{"symbol": "BBB", "shares": 2000, "entryPrice": 48.0}])
        # Anti-correlated return streams => meaningful diversification benefit.
        base = [0.004, -0.002, 0.006, -0.001, 0.003, 0.002, -0.004, 0.005, 0.001]
        ra = base
        rb = [-x for x in base]
        _inject_navs("s-a", _nav_path(1_000_000, ra))
        _inject_navs("s-b", _nav_path(1_000_000, rb))

        p = multistrat.firm_payload(method="risk_parity")
        corr = p["correlation"]
        assert corr is not None
        assert corr["matrix"][0][0] == 1.0 and corr["matrix"][1][1] == 1.0
        assert corr["matrix"][0][1] < -0.5  # strongly anti-correlated

        risk = p["risk"]
        # Diversification: combined vol < weighted-average standalone vol.
        assert risk["combinedVol"] < risk["weightedAvgVol"]
        assert risk["diversificationBenefit"] > 0
        assert risk["diversificationRatio"] > 1.0
        # Risk contributions of the used sleeves sum to ~100%.
        rcs = [s["riskContribPct"] for s in p["sleeves"] if s["riskContribPct"] is not None]
        assert abs(sum(rcs) - 100.0) < 1.0
        # HHI / effective-sleeves sanity for 2 sleeves.
        assert 0.5 <= risk["concentrationHHI"] <= 1.0
        assert 1.0 <= risk["effectiveSleeves"] <= 2.0
    print("OK risk_decomposition_and_correlation_real")


def test_allocation_methods():
    with store_env():
        _add_sleeve("s-a", "Alpha", "paper",
                    [{"symbol": "AAA", "shares": 1000, "entryPrice": 90.0}])
        _add_sleeve("s-b", "Beta", "paper",
                    [{"symbol": "BBB", "shares": 2000, "entryPrice": 48.0}])
        # Beta is roughly 2x as volatile as Alpha.
        ra = [0.003, -0.002, 0.004, -0.001, 0.002, 0.003, -0.002, 0.004, 0.001]
        rb = [0.008, -0.006, 0.010, -0.004, 0.006, 0.007, -0.005, 0.009, 0.002]
        _inject_navs("s-a", _nav_path(1_000_000, ra))
        _inject_navs("s-b", _nav_path(1_000_000, rb))

        # Equal weight => 50/50 across the two investable sleeves.
        eq = multistrat.firm_payload(method="equal_weight")
        recs = {r["name"]: r["recommended"] for r in eq["allocation"]["rows"]}
        assert abs(recs["Alpha"] - 50.0) < 0.01 and abs(recs["Beta"] - 50.0) < 0.01

        # Risk parity => the LOWER-vol sleeve (Alpha) gets the LARGER weight.
        rp = multistrat.firm_payload(method="risk_parity")
        rprecs = {r["name"]: r["recommended"] for r in rp["allocation"]["rows"]}
        assert rprecs["Alpha"] > rprecs["Beta"]
        assert abs(sum(rprecs.values()) - 100.0) < 0.5
        # Equal risk contribution: the two sleeves contribute ~equally to risk.
        rcs = [r["recRiskContribPct"] for r in rp["allocation"]["rows"]]
        assert abs(rcs[0] - rcs[1]) < 10.0

        # Target risk => scale risk-parity to hit the requested firm vol budget.
        tr = multistrat.firm_payload(method="target_risk", target_vol=0.08)
        assert tr["allocation"]["targetVol"] == 8.0
        assert abs(tr["allocation"]["recommendedVol"] - 8.0) < 0.5
        assert tr["allocation"]["leverage"] is not None
    print("OK allocation_methods")


def test_method_aliases_and_percent_target():
    with store_env():
        _add_sleeve("s-a", "Alpha", "paper",
                    [{"symbol": "AAA", "shares": 1000, "entryPrice": 90.0}])
        _add_sleeve("s-b", "Beta", "paper",
                    [{"symbol": "BBB", "shares": 2000, "entryPrice": 48.0}])
        ra = [0.003, -0.002, 0.004, -0.001, 0.002, 0.003, -0.002, 0.004, 0.001]
        rb = [0.005, -0.004, 0.006, -0.002, 0.003, 0.004, -0.003, 0.005, 0.002]
        _inject_navs("s-a", _nav_path(1_000_000, ra))
        _inject_navs("s-b", _nav_path(1_000_000, rb))

        assert multistrat.firm_payload(method="ERC")["method"] == "risk_parity"
        assert multistrat.firm_payload(method="1/N")["method"] == "equal_weight"
        assert multistrat.firm_payload(method="vol_target")["method"] == "target_risk"
        assert multistrat.firm_payload(method="garbage")["method"] == "risk_parity"
        # A percentage like 12 is read as 12%, not 1200%.
        p = multistrat.firm_payload(method="target_risk", target_vol=12)
        assert p["allocation"]["targetVol"] == 12.0
    print("OK method_aliases_and_percent_target")


_TESTS = [
    test_no_sleeves_degrades_cleanly,
    test_combined_book_aggregates_real_marks,
    test_thin_history_sleeve_is_held_out_not_faked,
    test_risk_decomposition_and_correlation_real,
    test_allocation_methods,
    test_method_aliases_and_percent_target,
]


def _run_all():
    failed = 0
    for t in _TESTS:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
            import traceback
            traceback.print_exc()
    print(f"\n{len(_TESTS) - failed}/{len(_TESTS)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
