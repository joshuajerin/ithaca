"""Unit tests for the cost-aware construction & automated rebalancing pipeline.

Runnable two ways:
    python artifacts/api-server/tests/test_rebalance.py   # standalone
    pytest artifacts/api-server/tests/test_rebalance.py    # if pytest installed

All offline — real prices/closes/ADV are stubbed so nothing hits the network or
the live data layer. Covers:
  * engine.estimate_trade_costs — modeled square-root impact per order, with
    aggregate roll-up, and missing-ADV/vol orders flagged (never faked);
  * the cost-aware optimizer term reducing churn vs the current book;
  * strategy.compute_trade_list — read-only trade list (no mutation) with expected
    cost and navAfter;
  * strategy.rebalance — applies trades, debits real modeled cost from cash;
  * strategy.resolve / set_schedule / is_due / run_scheduled_rebalances;
  * skills.build_rebalance_plan — preview vs apply, empty/no-trade shapes;
  * agent routing — rebalance/preview phrasings resolve to the rebalance_plan.
"""
from __future__ import annotations

import contextlib
import datetime
import os
import sys

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import agent, compliance_store, engine, harness, repo, skills, strategy, strategy_store  # noqa: E402
from app.strategy_store import db as _store_db  # noqa: E402


# =========================================================================
# Test doubles
# =========================================================================
_PRICES = {"AAA": 100.0, "BBB": 50.0, "CCC": 200.0, "DDD": 75.0}
_ADV = {"AAA": 5_000_000.0, "BBB": 4_000_000.0, "CCC": 3_000_000.0, "DDD": 2_000_000.0}


def _stub_get_company(symbol):
    s = (symbol or "").upper()
    if s in _PRICES:
        return {"symbol": s, "name": f"{s} Corp", "price": _PRICES[s], "volume": _ADV[s]}
    return None


def _stub_all_companies():
    return {s: {"name": f"{s} Corp", "price": p, "volume": _ADV[s]} for s, p in _PRICES.items()}


def _stub_series(sym, n=120):
    base = _PRICES.get(sym.upper(), 100.0)
    d0 = datetime.date.today() - datetime.timedelta(days=n)
    pts, px = [], base * 0.6
    for i in range(n):
        pts.append({"t": (d0 + datetime.timedelta(days=i)).isoformat(), "c": round(px, 4)})
        px *= 1.004
    return pts


def _stub_price_closes_bulk(symbols, days=220):
    return {
        "series": {s.upper(): _stub_series(s) for s in symbols},
        "source": "mock",
        "asOf": datetime.date.today().isoformat(),
    }


def _stub_price_series_meta(sym, days=90):
    return {"points": _stub_series(sym, n=min(days, 120)), "source": "mock"}


@contextlib.contextmanager
def env(use_memory=True):
    saved = {
        "get_company": repo.get_company,
        "all_symbols": repo.all_symbols,
        "get_all_companies": repo.get_all_companies,
        "price_closes_bulk": repo.price_closes_bulk,
        "price_series_meta": repo.price_series_meta,
        "db_available": _store_db.db_available,
        "schema_ready": strategy_store._schema_ready,
    }
    repo.get_company = _stub_get_company
    repo.all_symbols = lambda: list(_PRICES.keys())
    repo.get_all_companies = _stub_all_companies
    repo.price_closes_bulk = _stub_price_closes_bulk
    repo.price_series_meta = _stub_price_series_meta
    if use_memory:
        _store_db.db_available = lambda: False
        strategy_store._mem.clear()
        strategy_store._schema_ready = False
        # Permissive compliance limits so these tests exercise rebalance mechanics
        # in isolation — the synthetic 4-name universe would otherwise trip the
        # default firm limits (compliance has its own dedicated tests).
        compliance_store._mem_cfg = None
        compliance_store._mem_audit.clear()
        compliance_store.set_limits({
            "maxPositionPct": 100.0,
            "maxConcentrationPct": 100.0,
            "maxNetPct": 1000.0,
            "maxLeverage": 100.0,
        })
    try:
        yield
    finally:
        for k, v in saved.items():
            if k == "db_available":
                _store_db.db_available = v
            elif k == "schema_ready":
                strategy_store._schema_ready = v
            else:
                setattr(repo, k, v)
        if use_memory:
            strategy_store._mem.clear()
            compliance_store._mem_cfg = None
            compliance_store._mem_audit.clear()


def _ok(name):
    print(f"  ok - {name}")


# =========================================================================
# engine.estimate_trade_costs
# =========================================================================
def test_estimate_trade_costs_models_and_flags():
    orders = [
        {"symbol": "AAA", "side": "buy", "shares": 10_000.0, "notional": 1_000_000.0, "price": 100.0},
        {"symbol": "ZZZ", "side": "sell", "shares": 5_000.0, "notional": 250_000.0, "price": 50.0},
    ]
    advs = {"AAA": 5_000_000.0}            # ZZZ deliberately missing
    vols = {"AAA": 0.02}                   # ZZZ deliberately missing
    enriched, agg = engine.estimate_trade_costs(orders, advs, vols)

    aaa = next(o for o in enriched if o["symbol"] == "AAA")
    zzz = next(o for o in enriched if o["symbol"] == "ZZZ")
    assert aaa["costSupported"] is True
    assert aaa["impactBps"] > 0 and aaa["costUsd"] > 0
    # Missing ADV/vol -> flagged, never faked.
    assert zzz["costSupported"] is False
    assert (zzz.get("costUsd") or 0.0) == 0.0

    assert agg["supportedCount"] == 1
    assert agg["unsupportedCount"] == 1
    # gross notional + summed cost only roll up the supported (modeled) orders.
    assert agg["grossNotional"] == 1_000_000.0
    assert abs(agg["totalCostUsd"] - aaa["costUsd"]) < 1e-6
    assert agg["impactBps"] > 0
    _ok("estimate_trade_costs models supported orders and flags missing ones")


def test_cost_term_reduces_churn():
    from app.engine import optimize
    from app.engine.optimize import Constraints
    import numpy as np

    rng = np.random.default_rng(0)
    n = 4
    mu = np.array([0.10, 0.09, 0.08, 0.07])
    A = rng.standard_normal((n, n))
    cov = A @ A.T / n + np.eye(n) * 0.05
    current = np.array([0.25, 0.25, 0.25, 0.25])
    cons = Constraints()

    w_free = optimize._solve_utility(mu, cov, 5.0, cons, None, current, kappa=None)
    kappa = np.full(n, 0.5)
    w_cost = optimize._solve_utility(mu, cov, 5.0, cons, None, current, kappa=kappa)

    churn_free = float(np.abs(w_free - current).sum())
    churn_cost = float(np.abs(w_cost - current).sum())
    assert churn_cost <= churn_free + 1e-9
    # The impact penalty must actually value the churn it discourages.
    assert optimize.impact_cost(w_free, current, kappa) >= optimize.impact_cost(w_cost, current, kappa) - 1e-9
    _ok("cost-aware optimizer term does not increase churn vs current")


# =========================================================================
# strategy.compute_trade_list / rebalance
# =========================================================================
def _make_research_strategy(name="Rebal Test"):
    # Research stage = no positions yet, so a rebalance establishes the book and
    # the trade list shows the full set of establishing trades.
    return strategy.create_strategy(name=name, signal="momentum", paper=False)


def _make_paper_strategy(name="Rebal Paper"):
    return strategy.create_strategy(name=name, signal="momentum", paper=True)


def test_compute_trade_list_is_read_only():
    with env():
        s = _make_research_strategy()
        before_positions = s.get("positions")
        before_cash = s.get("cash")
        plan = strategy.compute_trade_list(s)

        assert plan["hasTrades"] is True
        assert plan["orders"], "research book should produce establishing trades"
        assert plan["navBefore"] >= plan["navAfter"]   # cost is non-negative
        assert plan["expectedCostUsd"] >= 0.0
        # No mutation of the view.
        assert s.get("positions") == before_positions
        assert s.get("cash") == before_cash
        _ok("compute_trade_list returns a plan without mutating the book")


def test_rebalance_applies_and_debits_real_cost():
    with env():
        s = _make_research_strategy()
        # No positions yet -> establishing rebalance.
        s2, info = strategy.rebalance(s)
        assert info["applied"] is True
        assert info["established"] is True
        assert info["trades"] > 0
        assert info["costModel"] == "square_root_impact"
        assert s2.get("positions"), "book should hold positions after establishing"
        assert info["costUsd"] >= 0.0
        assert info["navAfter"] <= info["navBefore"] + 1e-6

        # Immediately rebalancing again should be a no-op (already at target).
        _s3, info2 = strategy.rebalance(s2)
        assert info2["applied"] is False
        _ok("rebalance applies trades, debits real modeled cost, idempotent at target")


# =========================================================================
# resolve + scheduling
# =========================================================================
def test_resolve_and_schedule_due():
    with env():
        s = _make_paper_strategy("Sched Book")
        assert strategy.resolve("Sched Book")["id"] == s["id"]
        assert strategy.resolve(signal="momentum")["id"] == s["id"]
        assert strategy.resolve()["id"] == s["id"]          # single book fallback

        # Not due until scheduled.
        assert strategy.is_due(s) is False
        s = strategy.set_schedule(s, every_days=7)
        assert s["construction"]["autoRebalance"] is True
        # Inception is today: due only once the cadence has elapsed.
        today = datetime.date.fromisoformat(s["inceptionDate"])
        assert strategy.is_due(s, as_of=today + datetime.timedelta(days=1)) is False
        assert strategy.is_due(s, as_of=today + datetime.timedelta(days=8)) is True
        _ok("resolve finds the book; set_schedule + is_due gate the cadence")


def test_run_scheduled_rebalances_runs_due_books():
    with env():
        # An active (paper) book that has drifted to all-cash with a past inception
        # is due and re-establishes its positions on the scheduled run.
        s = _make_paper_strategy("Due Book")
        s["positions"] = []
        s["cash"] = s["capital"]
        s["inceptionDate"] = (datetime.date(2026, 6, 8) - datetime.timedelta(days=30)).isoformat()
        s = strategy._persist(s)
        s = strategy.set_schedule(s, every_days=7)

        day = datetime.date(2026, 6, 8)  # Monday — weekday, past the weekend guard
        res = strategy.run_scheduled_rebalances(as_of=day)
        assert res["date"] == day.isoformat()
        assert res["rebalanced"] >= 1
        _ok("run_scheduled_rebalances rebalances due active books")


def test_weekend_is_skipped():
    with env():
        s = _make_paper_strategy("Weekend Book")
        strategy.set_schedule(s, every_days=1)
        sat = datetime.date(2026, 6, 6)  # Saturday
        res = strategy.run_scheduled_rebalances(as_of=sat)
        assert res.get("weekend") is True
        assert res["rebalanced"] == 0
        _ok("run_scheduled_rebalances skips weekends")


# =========================================================================
# skills.build_rebalance_plan
# =========================================================================
def test_build_rebalance_plan_empty():
    with env():
        out = skills.build_rebalance_plan({})
        assert out["status"] == "empty"
        assert out["applied"] is False
        _ok("build_rebalance_plan returns an empty shape with no strategies")


def test_build_rebalance_plan_preview_then_apply():
    with env():
        s = _make_research_strategy()
        preview = skills.build_rebalance_plan({"strategy": s["name"], "apply": False})
        assert preview["status"] == "ok"
        assert preview["applied"] is False
        assert preview["hasTrades"] is True
        assert preview["tradeCount"] == len(preview["orders"])
        assert preview["expected"]["costUsd"] >= 0.0
        # Realized block present; supported/unsupported add up to the order count.
        r = preview["realized"]
        assert r["supportedCount"] + r["unsupportedCount"] == len(preview["orders"])

        # Preview must not have mutated the book.
        assert not (strategy_store.get_strategy(s["id"]).get("positions") or [])

        applied = skills.build_rebalance_plan({"strategy": s["name"], "apply": True})
        assert applied["applied"] is True
        assert strategy_store.get_strategy(s["id"]).get("positions"), "apply should populate the book"
        _ok("build_rebalance_plan previews without mutation, then applies")


# =========================================================================
# agent routing
# =========================================================================
def test_routing_rebalance_and_preview():
    # Lifecycle action detection: both an explicit rebalance and a preview phrasing
    # resolve to the rebalance lifecycle action.
    assert agent._lifecycle_action("rebalance my momentum strategy") == "rebalance"
    assert agent._lifecycle_action("what trades to get to target for my book") == "rebalance"
    assert agent._lifecycle_action("show me the rebalance plan") == "rebalance"
    # A generic portfolio optimization must NOT be captured as a strategy rebalance.
    assert agent._lifecycle_action("rebalance a portfolio to target vol") is None

    # Apply vs preview decisioning.
    assert agent._rebalance_should_apply("rebalance my strategy") is True
    assert agent._rebalance_should_apply("rebalance my strategy and apply it") is True
    assert agent._rebalance_should_apply("what trades to get to target") is False
    assert agent._rebalance_should_apply("preview the rebalance plan") is False
    _ok("agent routing maps rebalance/preview phrasings + apply decisioning")


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    print(f"running {len(tests)} rebalance tests")
    for t in tests:
        t()
    print("all rebalance tests passed")


if __name__ == "__main__":
    _run_all()
