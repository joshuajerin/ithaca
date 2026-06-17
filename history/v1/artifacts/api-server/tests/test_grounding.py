"""Unit tests for the Console's data-grounded answer serialization.

Runnable two ways:
    python artifacts/api-server/tests/test_grounding.py     # standalone
    pytest artifacts/api-server/tests/test_grounding.py      # if pytest installed

The Console answers questions about on-screen panels by feeding the model a
bounded text summary of each panel's underlying data (agent._serialize_panel /
_panels_context). These tests lock in that contract WITHOUT a live AI key — they
exercise the serializers directly, not the LLM:

  * A real backtest panel's exact Sharpe / max drawdown / win rate / total return
    and worst-drawdown date all survive into the serialized context.
  * Missing metrics are NOT fabricated — a stat absent from the data never shows
    up in the summary.
  * Generic panels (fundamentals, comparison) surface their label/value rows.
  * Every summary stays within the per-panel and total size caps, so latency and
    token use stay bounded even with many large panels on screen.
"""
from __future__ import annotations

import os
import sys

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import agent, harness  # noqa: E402


def _build(panel_type: str, params: dict) -> dict:
    """Build one real, validated panel via the harness (no LLM involved)."""
    panel = harness.run_skill(panel_type, params, {"x": 0, "y": 0, "w": 6, "h": 4})
    assert panel["status"] == "ok", f"{panel_type} failed to build: {panel.get('note')}"
    assert isinstance(panel["data"], dict) and panel["data"], f"{panel_type} has no data"
    return panel


# --------------------------- backtest grounding ---------------------------
def test_backtest_serialization_contains_exact_stats():
    panel = _build("backtest", {"symbol": "NVDA", "strategy": "momentum", "range": "1Y"})
    body = agent._serialize_panel(panel)

    # Header carries the panel type so the model knows what it is reading.
    assert "[backtest]" in body
    # Subject of the backtest is grounded, not guessed.
    assert "symbol=NVDA" in body
    assert "strategy=momentum" in body

    stats = panel["data"]["stats"]
    assert stats, "backtest produced no stats block"
    # Every stat the user can see must appear with its EXACT serialized value.
    # We format each value the same way the serializer does so the assertion
    # tracks the real contract rather than a hand-typed number.
    for key in ("sharpe", "maxDD", "winRate", "totalReturn", "sortino", "cagr"):
        assert key in stats, f"expected stat {key} in backtest stats"
        expected = f"{key}={agent._ser_scalar(stats[key])}"
        assert expected in body, f"missing exact stat in summary: {expected}\nbody={body}"


def test_backtest_serialization_contains_worst_drawdown_date():
    panel = _build("backtest", {"symbol": "AMD", "strategy": "momentum", "range": "1Y"})
    body = agent._serialize_panel(panel)

    dd = panel["data"]["drawdown"]
    assert dd, "backtest produced no drawdown series"
    worst = min(
        (d for d in dd if isinstance(d.get("dd"), (int, float))),
        key=lambda d: d["dd"],
    )
    # The exact worst-drawdown value and its date both land in the summary.
    assert f"worst drawdown {agent._ser_scalar(worst['dd'])}% on {worst['t']}" in body, body


def test_backtest_does_not_fabricate_missing_metrics():
    panel = _build("backtest", {"symbol": "NVDA", "strategy": "momentum", "range": "1Y"})

    # Drop a real stat from the data; it must then be ABSENT from the summary —
    # the serializer reports only what's present, it never invents a value.
    assert "sortino" in panel["data"]["stats"]
    panel["data"]["stats"].pop("sortino")
    body = agent._serialize_panel(panel)
    assert "sortino=" not in body, "serializer fabricated a dropped stat"

    # A metric that was never in the data must likewise never appear.
    assert "calmar=" not in body
    assert "informationRatio=" not in body


# ----------------------- generic label/value panels -----------------------
def test_fundamentals_serializes_label_value_rows():
    panel = _build("fundamentals", {"symbol": "NVDA"})
    body = agent._serialize_panel(panel)

    metrics = panel["data"]["metrics"]
    assert metrics, "fundamentals produced no metrics"
    # The label/value rows the user sees are surfaced verbatim (label=value),
    # so the model can quote real figures rather than estimate them.
    for row in metrics[: agent._SER_MAX_LABELVAL]:
        assert f"{row['label']}={row['value']}" in body, f"missing metric row: {row}\nbody={body}"
    # The list length is announced so truncation is visible, not silent.
    assert f"metrics[{len(metrics)}]" in body


def test_comparison_serializes_rows_within_caps():
    panel = _build("comparison", {"symbols": ["NVDA", "AMD", "TSM"]})
    body = agent._serialize_panel(panel)

    data = panel["data"]
    # The compared companies are grounded by symbol and name.
    for comp in data["companies"]:
        assert comp["symbol"] in body
    # The metric axis (the label side of every value row) is surfaced too.
    assert "metricLabels[" in body
    first_label = data["metricLabels"][0]
    assert first_label in body
    # And the whole summary stays within the per-panel size budget.
    assert len(body) <= agent._SER_MAX_PANEL_CHARS + 256


# ------------------------------- size caps -------------------------------
def test_per_panel_char_cap_truncates_large_data():
    # A panel whose data is far larger than the cap must be truncated, not
    # dumped wholesale into the prompt.
    huge = {
        "id": "x-1",
        "type": "fundamentals",
        "title": "Huge",
        "status": "ok",
        "data": {"metrics": [{"label": f"row{i}", "value": "v" * 50} for i in range(500)]},
    }
    body = agent._serialize_panel(huge)
    # Body is capped (+ a bounded header/tail), and truncation is marked.
    assert len(body) <= agent._SER_MAX_PANEL_CHARS + 256
    assert body.endswith("…") or "…" in body


def test_total_context_budget_caps_many_panels():
    # Many sizeable panels must not blow the total budget; once the cap is hit
    # the rest are explicitly noted as omitted.
    panels = []
    for i in range(40):
        panels.append({
            "id": f"p-{i}",
            "type": "fundamentals",
            "title": f"P{i}",
            "status": "ok",
            "data": {"metrics": [{"label": f"m{j}", "value": "x" * 20} for j in range(16)]},
        })
    ctx = agent._panels_context(panels)
    assert "omitted to save space" in ctx, "expected an omission marker once the budget is hit"
    # The joined context honours the total budget (allow a small per-line margin).
    assert len(ctx) <= agent._SER_MAX_TOTAL_CHARS + agent._SER_MAX_PANEL_CHARS + 256


def test_error_panel_serializes_note_not_data():
    # An error panel must serialize its note and never pretend to have figures.
    panel = harness.run_skill("backtest", {"symbol": "NVDA"}, {"x": 0, "y": 0, "w": 6, "h": 4})
    panel["status"] = "error"
    panel["note"] = "This panel could not be built: boom"
    panel["data"] = None
    body = agent._serialize_panel(panel)
    assert "could not be built" in body
    assert "stats:" not in body


def _run_all():
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in funcs:
        fn()
        passed += 1
        print(f"  PASS {fn.__name__}")
    print(f"\n{passed}/{len(funcs)} grounding tests passed")


if __name__ == "__main__":
    _run_all()
