"""Regression tests for the orchestrator's keyword heuristic routing.

Runnable two ways:
    python artifacts/api-server/tests/test_routing.py     # standalone
    pytest artifacts/api-server/tests/test_routing.py      # if pytest installed

Guards intent dispatch where multiple routes share keywords. In particular a
signal-driven "build a portfolio from <signal>" must construct a signal_portfolio
book, not fall through to the generic portfolio_optimizer (both match "build a
portfolio").
"""
from __future__ import annotations

import os
import sys

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import agent  # noqa: E402


def _types(query: str):
    panels, _summary = agent._orchestrate_heuristic(query)
    return [p.get("type") for p in panels]


def test_signal_portfolio_wins_over_optimizer():
    # "build a portfolio" also matches wants_optimizer; the signal mention must
    # route to the signal_portfolio construction panel instead.
    assert _types("build a portfolio from the momentum signal") == ["signal_portfolio"]
    assert _types("build a long-short portfolio from the momentum signal") == ["signal_portfolio"]
    assert _types("turn the value signal into a portfolio") == ["signal_portfolio"]


def test_generic_portfolio_still_routes_to_optimizer():
    # No signal mention → the classic optimizer flow is preserved.
    assert _types("build a portfolio") == ["portfolio_optimizer"]
    assert _types("optimize a max sharpe portfolio of NVDA, AMD, TSM") == ["portfolio_optimizer"]


def test_long_short_phrasing_selects_long_short_scheme():
    # Routing must pick the long_short scheme. The data build hits live prices, so
    # only assert the scheme when the panel built successfully (engine tests cover
    # construction itself); the type assertion is unconditional.
    panels, _ = agent._orchestrate_heuristic(
        "build a long-short portfolio from the momentum signal"
    )
    assert panels and panels[0]["type"] == "signal_portfolio"
    data = panels[0].get("data")
    if data is not None:
        assert data["scheme"] == "long_short"


def test_default_scheme_is_top_quantile():
    panels, _ = agent._orchestrate_heuristic("build a portfolio from the momentum signal")
    assert panels and panels[0]["type"] == "signal_portfolio"
    data = panels[0].get("data")
    if data is not None:
        assert data["scheme"] == "top_quantile"


def _run_all():
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in funcs:
        fn()
        passed += 1
        print(f"  PASS {fn.__name__}")
    print(f"\n{passed}/{len(funcs)} routing tests passed")


if __name__ == "__main__":
    _run_all()
