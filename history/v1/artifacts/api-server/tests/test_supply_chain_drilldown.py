"""Unit tests for supply-chain graph drill-down (recenter on a clicked node).

Runnable two ways:
    python artifacts/api-server/tests/test_supply_chain_drilldown.py   # standalone
    pytest artifacts/api-server/tests/test_supply_chain_drilldown.py    # if pytest installed

Covers the click-a-node-to-recenter feature: the canonical recenter instruction
is parsed deterministically (never depends on the LLM), the refine flow rebuilds
the panel centered on the clicked supplier/customer (same panel id, regenerated
title) and recomputes risk scores for the new subject.
"""
from __future__ import annotations

import os
import sys

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import agent, harness, state  # noqa: E402


# --------------------------- canonical instruction parse ---------------------------
def test_recenter_params_parses_symbol():
    assert agent._supply_chain_recenter_params("Recenter supply chain on TSM") == {"symbol": "TSM"}
    # Case-insensitive and lowercases-to-uppercase the ticker.
    assert agent._supply_chain_recenter_params("recenter supply chain on asml") == {"symbol": "ASML"}


def test_recenter_params_returns_none_for_other_instructions():
    assert agent._supply_chain_recenter_params("show me NVDA fundamentals") is None
    assert agent._supply_chain_recenter_params("") is None


# --------------------------- end-to-end refine drill-down ---------------------------
def _make_session(symbol: str):
    panel = harness.run_skill("supply_chain", {"symbol": symbol}, {"x": 0, "y": 0, "w": 6, "h": 4})
    sid = "drilldown-test"
    state.set_dashboard(sid, [panel])
    return sid, panel


def test_drilldown_recenters_panel_in_place():
    sid, panel = _make_session("NVDA")
    assert panel["data"]["symbol"] == "NVDA"

    # Click TSMC (a supplier node with symbol TSM).
    updated = agent.refine(sid, panel["id"], "Recenter supply chain on TSM")
    assert updated is not None
    # Same panel, recomposed on the clicked supplier.
    assert updated["id"] == panel["id"]
    assert updated["data"]["symbol"] == "TSM"
    # Title regenerates to the new subject (not kept from NVDA).
    assert "TSM" in (updated["title"] or "")
    # Risk scores recompute for the new subject.
    assert "riskSummary" in (updated["data"] or {})
    sup_risk = [n.get("riskScore") for n in updated["data"]["nodes"] if n.get("role") == "supplier"]
    assert sup_risk and all(r is not None for r in sup_risk)


def test_drilldown_second_tier_then_back():
    sid, panel = _make_session("NVDA")
    # NVDA -> TSM -> ASML exposes second-tier (TSM depends on ASML).
    agent.refine(sid, panel["id"], "Recenter supply chain on TSM")
    asml = agent.refine(sid, panel["id"], "Recenter supply chain on ASML")
    assert asml["data"]["symbol"] == "ASML"
    asml_suppliers = {n.get("symbol") for n in asml["data"]["nodes"] if n.get("role") == "supplier"}
    # ASML's own supply chain is materially different from NVDA's.
    assert asml_suppliers != {n.get("symbol") for n in panel["data"]["nodes"] if n.get("role") == "supplier"}

    # Back to the original subject.
    back = agent.refine(sid, panel["id"], "Recenter supply chain on NVDA")
    assert back["data"]["symbol"] == "NVDA"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
