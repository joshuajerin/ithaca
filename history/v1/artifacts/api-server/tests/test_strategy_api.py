"""FastAPI TestClient tests for the strategy lifecycle REST endpoints.

Runnable two ways:
    python artifacts/api-server/tests/test_strategy_api.py   # standalone
    pytest artifacts/api-server/tests/test_strategy_api.py    # if pytest installed

Covers GET/POST /api/strategies and POST
/api/strategies/{id}/transition — the create round-trip, the desk roster, a
paper-trade transition, the promotion-criteria block (and force override), the
demote alias, and the 404 for an unknown strategy. All offline: real prices and
closes are stubbed and the store is forced in-memory so nothing touches the
network or the live database.
"""
from __future__ import annotations

import contextlib
import datetime
import os
import sys

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from app import repo, strategy_store  # noqa: E402
from app.main import app  # noqa: E402
from app.strategy_store import db as _store_db  # noqa: E402

_PRICES = {"AAA": 100.0, "BBB": 50.0}


def _stub_get_company(symbol):
    s = (symbol or "").upper()
    if s in _PRICES:
        return {"symbol": s, "name": f"{s} Corp", "price": _PRICES[s]}
    return None


def _stub_price_closes_bulk(symbols, days=220):
    d0 = datetime.date.today()
    series = {}
    for sym in symbols:
        base = _PRICES.get(sym.upper(), 100.0)
        pts, px = [], base
        for i in range(8):
            pts.append({"t": (d0 + datetime.timedelta(days=i)).isoformat(), "c": round(px, 4)})
            px *= 1.01
        series[sym.upper()] = pts
    return {"series": series, "source": "mock", "asOf": d0.isoformat()}


@contextlib.contextmanager
def api_env():
    saved = {
        "get_company": repo.get_company,
        "all_symbols": repo.all_symbols,
        "price_closes_bulk": repo.price_closes_bulk,
        "db_available": _store_db.db_available,
        "schema_ready": strategy_store._schema_ready,
    }
    repo.get_company = _stub_get_company
    repo.all_symbols = lambda: list(_PRICES.keys())
    repo.price_closes_bulk = _stub_price_closes_bulk
    _store_db.db_available = lambda: False
    strategy_store._mem.clear()
    strategy_store._schema_ready = False
    try:
        # No `with` block: skip the app lifespan (background worker) — the
        # strategy routes and skill registry are import-time, not startup-time.
        yield TestClient(app)
    finally:
        repo.get_company = saved["get_company"]
        repo.all_symbols = saved["all_symbols"]
        repo.price_closes_bulk = saved["price_closes_bulk"]
        _store_db.db_available = saved["db_available"]
        strategy_store._schema_ready = saved["schema_ready"]
        strategy_store._mem.clear()


def _create(client, **body):
    body.setdefault("name", "API Strategy")
    body.setdefault("symbols", ["AAA", "BBB"])
    body.setdefault("weights", [0.5, 0.5])
    r = client.post("/api/strategies", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_create_and_list_strategies():
    with api_env() as client:
        view = _create(client)
        assert view["stage"] == "research"
        assert view["name"] == "API Strategy"

        r = client.get("/api/strategies")
        assert r.status_code == 200
        desk = r.json()
        # desk_payload shape: roster + stages + count.
        assert desk["count"] >= 1
        assert any(s["name"] == "API Strategy" for s in desk["strategies"])
        assert "research" in desk["stages"] and "live" in desk["stages"]


def test_create_with_paper_flag_builds_book():
    with api_env() as client:
        view = _create(client, name="Paper Now", paper=True)
        assert view["stage"] == "paper"
        assert view["positions"]
        assert view["inceptionDate"] == datetime.date.today().isoformat()


def test_transition_to_paper():
    with api_env() as client:
        view = _create(client)
        r = client.post(f"/api/strategies/{view['id']}/transition", json={"stage": "paper"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["strategy"]["stage"] == "paper"


def test_transition_to_live_blocked_then_forced():
    with api_env() as client:
        view = _create(client, paper=True)  # straight to paper
        sid = view["id"]
        # Fresh book: track record too short -> blocked.
        blocked = client.post(f"/api/strategies/{sid}/transition", json={"stage": "live"})
        assert blocked.status_code == 200
        bb = blocked.json()
        assert bb["ok"] is False
        assert "promotion criteria" in bb["message"].lower()
        assert bb["strategy"]["stage"] == "paper"

        # force override promotes.
        forced = client.post(f"/api/strategies/{sid}/transition",
                             json={"stage": "live", "force": True})
        assert forced.status_code == 200
        fb = forced.json()
        assert fb["ok"] is True and fb["strategy"]["stage"] == "live"


def test_transition_demote_alias():
    with api_env() as client:
        view = _create(client, paper=True)
        sid = view["id"]
        client.post(f"/api/strategies/{sid}/transition", json={"stage": "live", "force": True})
        r = client.post(f"/api/strategies/{sid}/transition", json={"stage": "demote"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True and body["strategy"]["stage"] == "paper"


def test_transition_unknown_strategy_404():
    with api_env() as client:
        r = client.post("/api/strategies/does-not-exist/transition", json={"stage": "paper"})
        assert r.status_code == 404


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
