"""Tests for the durable, firm-scoped session-state store (app.state).

Runnable two ways:
    python artifacts/api-server/tests/test_state_persistence.py   # standalone
    pytest artifacts/api-server/tests/test_state_persistence.py    # if pytest installed

The store externalizes the app's per-session working state (active dashboards,
conversation history, saved DCF models, trade-flow alert rules/events) so it
survives a restart and is shared across instances. These tests cover, all
offline:

  * the in-memory fallback path (no DATABASE_URL) — every public operation;
  * firm isolation — two firms with the same session id never see each other's
    dashboards, history, DCF models, alerts or session owner;
  * the global watchlist is shared (not firm-scoped);
  * read-modify-write semantics (append_history cap, dedup of alert events,
    set-once session owner, panel update-in-place);
  * an opportunistic Postgres round-trip (durability across a fresh read),
    skipped cleanly when no database is configured.
"""
from __future__ import annotations

import contextlib
import os
import sys
import uuid

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import state, tenant  # noqa: E402
from app.state import db as _state_db  # noqa: E402


@contextlib.contextmanager
def memory_store():
    """Force the in-memory fallback and start from a clean slate, restoring the
    real ``db_available`` and schema flag on exit."""
    saved_db_available = _state_db.db_available
    saved_schema = state._schema_ready
    _state_db.db_available = lambda: False
    state._schema_ready = False
    state.reset_for_tests()
    try:
        yield
    finally:
        _state_db.db_available = saved_db_available
        state._schema_ready = saved_schema
        state.reset_for_tests()


@contextlib.contextmanager
def as_firm(firm_id: str):
    with tenant.firm_context(firm_id):
        yield


# =========================================================================
# in-memory fallback — basic round-trips
# =========================================================================
def test_dashboard_round_trip_and_panel_ops():
    with memory_store(), as_firm("firmA"):
        assert state.get_dashboard("s1") == []
        panels = [{"id": "p1", "type": "chart"}, {"id": "p2", "type": "table"}]
        state.set_dashboard("s1", panels)
        got = state.get_dashboard("s1")
        assert [p["id"] for p in got] == ["p1", "p2"]

        # returned copies must not alias internal storage
        got[0]["type"] = "MUTATED"
        assert state.get_dashboard("s1")[0]["type"] == "chart"

        # update_panel replaces in place by id
        state.update_panel("s1", {"id": "p2", "type": "heatmap"})
        assert state.get_panel("s1", "p2")["type"] == "heatmap"
        # unknown id is a no-op
        state.update_panel("s1", {"id": "nope", "type": "x"})
        assert state.get_panel("s1", "nope") is None


def test_history_append_and_cap():
    with memory_store(), as_firm("firmA"):
        for i in range(state._MAX_HISTORY + 5):
            state.append_history("s1", "user", f"msg{i}")
        hist = state.get_history("s1")
        assert len(hist) == state._MAX_HISTORY
        # keeps the most recent ones
        assert hist[-1]["content"] == f"msg{state._MAX_HISTORY + 4}"


def test_dcf_models_crud():
    with memory_store(), as_firm("firmA"):
        assert state.list_dcf_models("s1") == []
        models = state.save_dcf_model("s1", "Base", "nvda", {"wacc": 0.09})
        assert len(models) == 1 and models[0]["symbol"] == "NVDA"
        # overwrite same (name, symbol) does not duplicate
        models = state.save_dcf_model("s1", "Base", "NVDA", {"wacc": 0.10})
        assert len(models) == 1 and models[0]["assumptions"]["wacc"] == 0.10
        # second name coexists
        state.save_dcf_model("s1", "Bull", "NVDA", {"wacc": 0.07})
        assert {m["name"] for m in state.list_dcf_models("s1", "NVDA")} == {"Base", "Bull"}
        # symbol filter
        state.save_dcf_model("s1", "Base", "MSFT", {"wacc": 0.08})
        assert {m["name"] for m in state.list_dcf_models("s1", "NVDA")} == {"Base", "Bull"}
        # delete
        remaining = state.delete_dcf_model("s1", "Base", "NVDA")
        assert {m["name"] for m in remaining} == {"Bull"}


def test_alert_rules_and_event_dedup():
    with memory_store(), as_firm("firmA"):
        rule = {"id": "r1", "kind": "flow"}
        state.add_alert_rule("s1", rule)
        assert [r["id"] for r in state.get_alert_rules("s1")] == ["r1"]

        added = state.add_alert_events("s1", [
            {"signature": "a", "msg": "x"},
            {"signature": "b", "msg": "y"},
        ])
        assert len(added) == 2
        # re-adding an already-seen signature is skipped
        added2 = state.add_alert_events("s1", [
            {"signature": "a", "msg": "dup"},
            {"signature": "c", "msg": "z"},
        ])
        assert [e["signature"] for e in added2] == ["c"]
        assert len(state.get_alert_events("s1")) == 3

        state.clear_alert_events("s1")
        assert state.get_alert_events("s1") == []

        state.remove_alert_rule("s1", "r1")
        assert state.get_alert_rules("s1") == []


def test_session_owner_set_once():
    with memory_store(), as_firm("firmA"):
        state.set_session_owner("s1", "user1", "firmA")
        assert state.get_session_owner("s1") == {"userId": "user1", "firmId": "firmA"}
        # second writer does not steal ownership
        state.set_session_owner("s1", "user2", "firmA")
        assert state.get_session_owner("s1")["userId"] == "user1"


# =========================================================================
# firm isolation
# =========================================================================
def test_firm_isolation_same_session_id():
    with memory_store():
        with as_firm("firmA"):
            state.set_dashboard("shared-sid", [{"id": "a1"}])
            state.append_history("shared-sid", "user", "secretA")
            state.save_dcf_model("shared-sid", "MA", "NVDA", {"wacc": 0.09})
            state.add_alert_rule("shared-sid", {"id": "ra"})
            state.set_session_owner("shared-sid", "ua", "firmA")
        with as_firm("firmB"):
            # firm B uses the SAME session id but sees nothing from firm A
            assert state.get_dashboard("shared-sid") == []
            assert state.get_history("shared-sid") == []
            assert state.list_dcf_models("shared-sid") == []
            assert state.get_alert_rules("shared-sid") == []
            assert state.get_session_owner("shared-sid") is None
            # firm B writes its own
            state.set_dashboard("shared-sid", [{"id": "b1"}])
        # firm A still sees only its own data
        with as_firm("firmA"):
            assert [p["id"] for p in state.get_dashboard("shared-sid")] == ["a1"]
            assert state.get_history("shared-sid")[0]["content"] == "secretA"


def test_watchlist_is_global_across_firms():
    with memory_store():
        with as_firm("firmA"):
            assert state.get_watchlist() == list(state.DEFAULT_WATCHLIST)
            state.add_watchlist("tsla")
        with as_firm("firmB"):
            # global, so firm B sees firm A's addition
            assert "TSLA" in state.get_watchlist()
            state.remove_watchlist("TSLA")
        with as_firm("firmA"):
            assert "TSLA" not in state.get_watchlist()


# =========================================================================
# opportunistic Postgres durability round-trip
# =========================================================================
def test_db_round_trip_durability():
    """If a DB is configured, a write must be visible on a fresh read with the
    in-memory fallback cleared (proving it came from Postgres, not process
    memory). Skipped cleanly when no DATABASE_URL."""
    if not _state_db.db_available():
        print("   (skipped — no DATABASE_URL)")
        return
    state._schema_ready = False  # force schema ensure
    fid = f"firm-{uuid.uuid4().hex[:8]}"
    sid = f"sess-{uuid.uuid4().hex[:8]}"
    try:
        with as_firm(fid):
            state.set_dashboard(sid, [{"id": "db-panel", "type": "chart"}])
            state.save_dcf_model(sid, "DBModel", "NVDA", {"wacc": 0.09})
            # wipe the in-memory fallback so the next read MUST hit Postgres
            state.reset_for_tests()
            got = state.get_dashboard(sid)
            assert [p["id"] for p in got] == ["db-panel"], got
            models = state.list_dcf_models(sid, "NVDA")
            assert {m["name"] for m in models} == {"DBModel"}, models
    finally:
        # best-effort cleanup of the rows we created
        try:
            _state_db.execute(
                "DELETE FROM session_state WHERE firm_id = %s", (fid,))
        except Exception:  # noqa: BLE001
            pass


# =========================================================================
# runner
# =========================================================================
def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
