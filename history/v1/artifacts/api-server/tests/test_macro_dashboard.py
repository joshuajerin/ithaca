"""Macro dashboard asset-customization (pin/add/remove) tests.

Covers the heuristic refine path (used when the AI client is unavailable) and
the build_macro_dashboard overrides contract:
  - add / remove a named asset
  - theme resolution from natural-language instructions ("risk view")
  - overrides accumulate across multiple refines (latest op per symbol wins)
  - overrides survive pydantic model validation (so they persist on the panel)

Runnable two ways:
    python artifacts/api-server/tests/test_macro_dashboard.py   # standalone
    pytest artifacts/api-server/tests/test_macro_dashboard.py    # if pytest installed
"""
from __future__ import annotations

import os
import sys

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import agent, data, models, skills  # noqa: E402


def _panel(theme="global", overrides=None):
    return {
        "type": "macro_dashboard",
        "data": skills.build_macro_dashboard({"theme": theme, "overrides": overrides or []}),
    }


def _symbols(built):
    return {t["symbol"] for g in built["groups"] for t in g["tiles"]}


def test_add_asset_to_theme():
    p = _panel("inflation")
    assert "EURUSD" not in _symbols(p["data"])
    params = agent._refine_macro_heuristic(p, "add EURUSD to this dashboard")
    assert params["theme"] == "inflation"  # plain add must not reset the theme
    built = skills.build_macro_dashboard(params)
    assert "EURUSD" in _symbols(built)


def test_remove_asset_from_risk_view():
    p = _panel("risk")
    assert "VIX" in _symbols(p["data"])
    params = agent._refine_macro_heuristic(p, "remove VIX from the risk view")
    # "risk view" names the theme explicitly; theme stays risk, VIX removed.
    assert params["theme"] == "risk"
    built = skills.build_macro_dashboard(params)
    assert "VIX" not in _symbols(built)


def test_switch_theme_without_assets():
    p = _panel("global")
    params = agent._refine_macro_heuristic(p, "switch to the risk dashboard")
    assert params["theme"] == "risk"


def test_plain_add_keeps_current_theme():
    # No theme word in the instruction must NOT reset theme to the global default.
    p = _panel("china")
    params = agent._refine_macro_heuristic(p, "add gold")
    assert params["theme"] == "china"


def test_overrides_accumulate_latest_op_wins():
    p = _panel("global")
    s1 = agent._refine_macro_heuristic(p, "swap in iron ore")
    p2 = _panel("global", s1["overrides"])
    s2 = agent._refine_macro_heuristic(p2, "remove gold")
    built = skills.build_macro_dashboard(s2)
    assert "IRON" in _symbols(built)
    assert "GOLD" not in _symbols(built)
    # Now re-add gold: latest op for GOLD wins, list stays compact.
    p3 = _panel("global", s2["overrides"])
    s3 = agent._refine_macro_heuristic(p3, "add gold back")
    assert len([o for o in s3["overrides"] if o["symbol"] == "GOLD"]) == 1
    built3 = skills.build_macro_dashboard(s3)
    assert "GOLD" in _symbols(built3)


def test_overrides_persist_through_model_validation():
    built = skills.build_macro_dashboard({"theme": "global", "overrides": [{"op": "add", "symbol": "EURUSD"}]})
    validated = models.MacroDashboardData.model_validate(built).model_dump()
    assert validated["overrides"] == [{"op": "add", "symbol": "EURUSD"}]


def test_unknown_symbol_is_ignored():
    built = skills.build_macro_dashboard({"theme": "global", "overrides": [{"op": "add", "symbol": "NOTREAL"}]})
    assert built["overrides"] == []


def test_alias_resolution():
    assert data.resolve_macro_symbols("add EUR/USD") == ["EURUSD"]
    assert data.resolve_macro_symbols("drop the dollar index") == ["DXY"]
    # longest-alias-first + consumption: "2y-10y" must not also yield "2y".
    assert data.resolve_macro_symbols("add 2y-10y spread") == ["US2Y10Y"]


def _run_standalone():
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failures.append((name, repr(exc)))
                print(f"FAIL {name}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        sys.exit(1)
    print("\nall macro dashboard tests passed")


if __name__ == "__main__":
    _run_standalone()
