"""Unit tests for the strategy lifecycle pillar.

Runnable two ways:
    python artifacts/api-server/tests/test_strategy.py   # standalone
    pytest artifacts/api-server/tests/test_strategy.py    # if pytest installed

Covers, all offline (real prices/closes are stubbed so nothing hits the network
or the live data layer):
  * strategy_store CRUD round-trip — the in-memory fallback always, and the
    Postgres path opportunistically when a database happens to be configured;
  * the paper-book mark-to-market math (engine.paperbook): position marks,
    book value, exposures, NAV reconstruction from real closes, realized stats;
  * the lifecycle service gating — promotion criteria evaluation, the
    paper→live promotion block + force override, free/blocked transitions and
    the demotion ladder;
  * the deterministic agent lifecycle intent handler for
    create / paper / promote (blocked + forced) / demote / retire.
"""
from __future__ import annotations

import contextlib
import datetime
import math
import os
import sys
import uuid

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import agent, harness, repo, strategy, strategy_store  # noqa: E402
from app.engine import paperbook  # noqa: E402
from app.strategy_store import db as _store_db  # noqa: E402


# =========================================================================
# Test doubles: a tiny deterministic price/close universe so the lifecycle
# service runs without the DB or any network. AAA..DDD have real-looking
# prices and an upward close ramp since today.
# =========================================================================
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
def lifecycle_env(use_memory=True):
    """Install the price/close stubs and (optionally) force the in-memory store,
    restoring everything on exit so tests don't leak global state."""
    saved = {
        "get_company": repo.get_company,
        "all_symbols": repo.all_symbols,
        "get_all_companies": repo.get_all_companies,
        "price_closes_bulk": repo.price_closes_bulk,
        "db_available": _store_db.db_available,
        "schema_ready": strategy_store._schema_ready,
    }
    repo.get_company = _stub_get_company
    repo.all_symbols = lambda: list(_PRICES.keys())
    repo.get_all_companies = _stub_all_companies
    repo.price_closes_bulk = _stub_price_closes_bulk
    if use_memory:
        _store_db.db_available = lambda: False
        strategy_store._mem.clear()
        strategy_store._schema_ready = False
    try:
        yield
    finally:
        repo.get_company = saved["get_company"]
        repo.all_symbols = saved["all_symbols"]
        repo.get_all_companies = saved["get_all_companies"]
        repo.price_closes_bulk = saved["price_closes_bulk"]
        _store_db.db_available = saved["db_available"]
        strategy_store._schema_ready = saved["schema_ready"]
        if use_memory:
            strategy_store._mem.clear()


@contextlib.contextmanager
def stub_panels():
    """Stub the panel-rendering harness so the agent handler tests exercise the
    lifecycle logic, not the (data-heavy) panel builders."""
    saved = harness.run_skill

    def _fake(panel_type, params, layout, title=None, panel_id=None, retries=2):
        return {"id": panel_id or panel_type, "type": panel_type, "layout": layout,
                "status": "ok", "data": {}, "title": title or panel_type}

    harness.run_skill = _fake
    try:
        yield
    finally:
        harness.run_skill = saved


# =========================================================================
# strategy_store CRUD
# =========================================================================
def test_store_memory_round_trip():
    with lifecycle_env(use_memory=True):
        rec = {
            "id": "mem-1", "name": "Mem Strategy", "signal": "momentum",
            "stage": "research", "capital": 1_000_000.0, "cash": None,
            "inception_date": None, "positions": None,
            "construction": {"universe": "U", "picks": [{"symbol": "AAA"}]},
            "target_weights": {"AAA": 0.5, "BBB": 0.5},
            "promotion_criteria": {"minDays": 5}, "stage_history": [{"stage": "research", "at": "2026-01-01"}],
            "notes": "hello",
        }
        saved = strategy_store.upsert(rec)
        # snake_case in -> camelCase view out, JSON fields preserved as objects.
        assert saved["targetWeights"] == {"AAA": 0.5, "BBB": 0.5}
        assert saved["promotionCriteria"] == {"minDays": 5}
        assert saved["construction"]["picks"][0]["symbol"] == "AAA"

        assert strategy_store.get_strategy("mem-1")["name"] == "Mem Strategy"
        # name lookup is case-insensitive.
        assert strategy_store.get_strategy("mem strategy")["id"] == "mem-1"
        assert any(s["id"] == "mem-1" for s in strategy_store.list_strategies())

        # update in place (same id) does not duplicate.
        rec["stage"] = "backtest"
        strategy_store.upsert(rec)
        rows = [s for s in strategy_store.list_strategies() if s["id"] == "mem-1"]
        assert len(rows) == 1 and rows[0]["stage"] == "backtest"

        assert strategy_store.delete("mem-1") is True
        assert strategy_store.get_strategy("mem-1") is None


def test_store_db_round_trip():
    """Opportunistic Postgres round-trip; skipped cleanly when no DB is configured."""
    with lifecycle_env(use_memory=False):
        if not _store_db.db_available():
            print("   (skipped — no DATABASE_URL)")
            return
        sid = f"test-strat-{uuid.uuid4().hex[:8]}"
        rec = {
            "id": sid, "name": "DB Round Trip", "signal": "value",
            "stage": "research", "capital": 500_000.0, "cash": None,
            "inception_date": None, "positions": None,
            "construction": {"universe": "U"}, "target_weights": {"AAA": 1.0},
            "promotion_criteria": {"minSharpe": 0.5}, "stage_history": [{"stage": "research", "at": "2026-01-01"}],
            "notes": None,
        }
        try:
            saved = strategy_store.upsert(rec)
            assert saved["id"] == sid
            # JSON columns come back already parsed by psycopg.
            assert saved["targetWeights"] == {"AAA": 1.0}
            assert saved["promotionCriteria"] == {"minSharpe": 0.5}
            got = strategy_store.get_strategy(sid)
            assert got is not None and got["name"] == "DB Round Trip"
            assert got["createdAt"] is not None  # timestamps serialized to ISO
        finally:
            strategy_store.delete(sid)
        assert strategy_store.get_strategy(sid) is None


# =========================================================================
# paper-book math (engine.paperbook)
# =========================================================================
def test_position_marks_and_book_value():
    positions = [
        {"symbol": "AAA", "shares": 10, "entryPrice": 100.0},
        {"symbol": "BBB", "shares": 20, "entryPrice": 50.0},
    ]
    price_map = {"AAA": 110.0, "BBB": 45.0}
    marks = paperbook.position_marks(positions, price_map)
    by = {m["symbol"]: m for m in marks}
    # AAA: 10*110 = 1100 mv, cost 1000 -> +100 (+10%)
    assert math.isclose(by["AAA"]["marketValue"], 1100.0)
    assert math.isclose(by["AAA"]["pnl"], 100.0)
    assert math.isclose(by["AAA"]["pnlPct"], 10.0)
    assert by["AAA"]["priced"] is True
    # BBB: 20*45 = 900 mv, cost 1000 -> -100 (-10%)
    assert math.isclose(by["BBB"]["pnl"], -100.0)
    # marks sorted by market value descending
    assert marks[0]["symbol"] == "AAA"
    # book value = cash + sum(shares*price)
    bv = paperbook.book_value(positions, 500.0, price_map)
    assert math.isclose(bv, 500.0 + 1100.0 + 900.0)


def test_unpriced_position_falls_back_to_entry():
    positions = [{"symbol": "ZZZ", "shares": 5, "entryPrice": 40.0}]
    marks = paperbook.position_marks(positions, {})  # no price available
    assert marks[0]["priced"] is False
    assert math.isclose(marks[0]["price"], 40.0)
    assert math.isclose(marks[0]["pnl"], 0.0)
    assert math.isclose(paperbook.book_value(positions, 0.0, {}), 200.0)


def test_exposures_weight_to_book():
    marks = [
        {"symbol": "AAA", "marketValue": 600.0},
        {"symbol": "BBB", "marketValue": 400.0},
    ]
    ex = paperbook.exposures(marks, 1000.0)
    by = {e["symbol"]: e["weight"] for e in ex}
    assert math.isclose(by["AAA"], 60.0)
    assert math.isclose(by["BBB"], 40.0)
    # most-weighted name first
    assert ex[0]["symbol"] == "AAA"
    assert paperbook.exposures(marks, 0.0) == []


def test_nav_curve_and_realized_stats():
    positions = [{"symbol": "AAA", "shares": 10, "entryPrice": 100.0}]
    # Real closes since inception: 100 -> 101 -> 102 -> 103
    closes = {"AAA": [
        {"t": "2026-01-01", "c": 100.0},
        {"t": "2026-01-02", "c": 101.0},
        {"t": "2026-01-03", "c": 102.0},
        {"t": "2026-01-04", "c": 103.0},
    ]}
    curve = paperbook.nav_curve(positions, cash=0.0, capital=1000.0,
                                closes_by_symbol=closes, inception="2026-01-01")
    assert len(curve) == 4
    # NAV day 1 = 10*100 = 1000 (== capital -> 0 pnl)
    assert math.isclose(curve[0]["nav"], 1000.0)
    assert math.isclose(curve[0]["pnl"], 0.0)
    # NAV last = 10*103 = 1030 -> +3%
    assert math.isclose(curve[-1]["nav"], 1030.0)
    assert math.isclose(curve[-1]["pnlPct"], 3.0)
    stats = paperbook.realized_stats(curve)
    assert isinstance(stats, dict) and stats  # enough points -> non-empty stats


def test_nav_curve_drops_pre_inception_and_empties_without_history():
    positions = [{"symbol": "AAA", "shares": 1, "entryPrice": 100.0}]
    closes = {"AAA": [{"t": "2025-12-31", "c": 100.0}]}  # entirely before inception
    assert paperbook.nav_curve(positions, 0.0, 100.0, closes, "2026-01-01") == []
    # too few points -> empty stats
    assert paperbook.realized_stats([{"nav": 100.0}, {"nav": 101.0}]) == {}


# =========================================================================
# lifecycle service: creation, promotion gating, transitions, demotion
# =========================================================================
def _make_paper_strategy(name="Momentum Strategy"):
    """Create + paper-trade a strategy from explicit names (deterministic)."""
    return strategy.create_strategy(
        name=name, signal="momentum", symbols=["AAA", "BBB"],
        weights=[0.5, 0.5], paper=True,
    )


def test_create_and_paper_trade_builds_book():
    with lifecycle_env():
        view = strategy.create_strategy(
            name="My Strat", signal="momentum", symbols=["AAA", "BBB"], weights=[0.5, 0.5],
        )
        assert view["stage"] == "research"
        assert view["positions"] is None
        # normalized to fractions summing to 1
        assert math.isclose(sum(view["targetWeights"].values()), 1.0, abs_tol=1e-6)

        papered = strategy.paper_trade(view)
        assert papered["stage"] == "paper"
        assert papered["inceptionDate"] == datetime.date.today().isoformat()
        syms = {p["symbol"] for p in papered["positions"]}
        assert syms == {"AAA", "BBB"}
        # cash = capital - invested, both reported and non-negative
        assert papered["cash"] is not None and papered["cash"] >= 0


def test_evaluate_promotion_pass_and_fail():
    crit = {"minSharpe": 0.5, "minReturnPct": 0.0, "maxDrawdownPct": 25.0, "minDays": 5}
    view = {"name": "X", "promotionCriteria": crit}
    good = {"stats": {"sharpe": 1.2, "maxDD": -10.0}, "pnlPct": 5.0, "ageDays": 10}
    ev = strategy.evaluate_promotion(view, good)
    assert ev["pass"] is True and len(ev["checks"]) == 4

    bad = {"stats": {"sharpe": 0.1, "maxDD": -40.0}, "pnlPct": -3.0, "ageDays": 1}
    ev2 = strategy.evaluate_promotion(view, bad)
    assert ev2["pass"] is False
    # every gate fails for this book
    assert all(c["pass"] is False for c in ev2["checks"])


def test_promotion_blocked_then_forced():
    with lifecycle_env():
        view = _make_paper_strategy()
        assert view["stage"] == "paper"
        # Fresh book: ageDays 0 < minDays 5 -> promotion is blocked.
        blocked, ok, msg = strategy.transition(view, "live")
        assert ok is False
        assert blocked["stage"] == "paper"
        assert "promotion criteria" in msg.lower()
        # force overrides every gate.
        promoted, ok2, msg2 = strategy.transition(view, "live", force=True)
        assert ok2 is True
        assert promoted["stage"] == "live"
        assert "promoted to live" in msg2.lower()


def test_promotion_requires_paper_stage():
    with lifecycle_env():
        view = strategy.create_strategy(
            name="Research Only", signal="momentum", symbols=["AAA", "BBB"], weights=[0.5, 0.5],
        )
        assert view["stage"] == "research"
        out, ok, msg = strategy.transition(view, "live")
        assert ok is False
        assert "must be paper-trading" in msg.lower()


def test_transition_entering_paper_and_unknown_and_same_stage():
    with lifecycle_env():
        view = strategy.create_strategy(
            name="Ladder", signal="momentum", symbols=["AAA", "BBB"], weights=[0.5, 0.5],
        )
        # entering paper builds the book
        papered, ok, _ = strategy.transition(view, "paper")
        assert ok is True and papered["stage"] == "paper" and papered["positions"]
        # unknown stage rejected
        _, ok2, msg2 = strategy.transition(papered, "nonsense")
        assert ok2 is False and "unknown stage" in msg2.lower()
        # same stage is a no-op success
        _, ok3, msg3 = strategy.transition(papered, "paper")
        assert ok3 is True and "already in" in msg3.lower()


def test_retire_from_anywhere_and_demotion_ladder():
    with lifecycle_env():
        view = _make_paper_strategy("Demote Me")
        live, ok, _ = strategy.transition(view, "live", force=True)
        assert ok and live["stage"] == "live"
        # demotion ladder: live -> paper -> backtest -> research, then floor.
        s1, ok1, _ = strategy.demote(live)
        assert ok1 and s1["stage"] == "paper"
        s2, ok2, _ = strategy.demote(s1)
        assert ok2 and s2["stage"] == "backtest"
        s3, ok3, _ = strategy.demote(s2)
        assert ok3 and s3["stage"] == "research"
        s4, ok4, msg4 = strategy.demote(s3)
        assert ok4 is False and "cannot be demoted" in msg4.lower()
        # retire is reachable from anywhere.
        retired, okr, _ = strategy.transition(s3, "retired")
        assert okr and retired["stage"] == "retired"


# =========================================================================
# agent lifecycle intent handler (create / paper / promote / demote / retire)
# =========================================================================
def test_agent_create_intent():
    with lifecycle_env(), stub_panels():
        out = agent._handle_lifecycle("create a momentum strategy", "sess-create", voice=False)
        assert out is not None
        assert "created" in out["summary"].lower()
        rows = strategy_store.list_strategies()
        assert len(rows) == 1 and rows[0]["stage"] == "research"


def test_agent_paper_intent():
    with lifecycle_env(), stub_panels():
        strategy.create_strategy(
            name="Momentum Strategy", signal="momentum", symbols=["AAA", "BBB"], weights=[0.5, 0.5],
        )
        out = agent._handle_lifecycle("paper trade the momentum strategy", "sess-paper", voice=False)
        assert out is not None
        assert strategy_store.get_strategy("Momentum Strategy")["stage"] == "paper"


def test_agent_promote_blocked_then_forced():
    with lifecycle_env(), stub_panels():
        _make_paper_strategy("Momentum Strategy")
        blocked = agent._handle_lifecycle("promote the momentum strategy to live", "s", voice=False)
        assert blocked is not None
        assert "does not yet clear" in blocked["summary"].lower()
        assert strategy_store.get_strategy("Momentum Strategy")["stage"] == "paper"

        forced = agent._handle_lifecycle("force promote the momentum strategy to live", "s", voice=False)
        assert forced is not None
        assert strategy_store.get_strategy("Momentum Strategy")["stage"] == "live"


def test_agent_demote_and_retire_intents():
    with lifecycle_env(), stub_panels():
        view = _make_paper_strategy("Momentum Strategy")
        strategy.transition(view, "live", force=True)
        demoted = agent._handle_lifecycle("demote the momentum strategy", "s", voice=False)
        assert demoted is not None
        assert strategy_store.get_strategy("Momentum Strategy")["stage"] == "paper"

        retired = agent._handle_lifecycle("retire the momentum strategy", "s", voice=False)
        assert retired is not None
        assert strategy_store.get_strategy("Momentum Strategy")["stage"] == "retired"


def test_agent_non_lifecycle_query_passes_through():
    with lifecycle_env(), stub_panels():
        # A pure view/question is not a lifecycle ACTION -> handler returns None
        # so orchestrate's normal panel flow takes over.
        assert agent._handle_lifecycle("show me the strategy desk", "s", voice=False) is None
        assert agent._handle_lifecycle("what is the price of AAA", "s", voice=False) is None


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
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ER0R {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
