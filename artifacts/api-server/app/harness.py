"""Execution harness: runs a skill builder, validates its output against the
panel's pydantic model, and retries on failure. On exhausted retries it
returns an error panel rather than crashing the dashboard.
"""
from __future__ import annotations

import uuid
from typing import Optional

from . import models, skills

DATA_MODELS = {
    "price_chart": models.PriceChartData,
    "news": models.NewsData,
    "analysis": models.AnalysisData,
    "fundamentals": models.FundamentalsData,
    "screener": models.ScreenerData,
    "heatmap": models.HeatmapData,
    "sentiment": models.SentimentData,
    "comparison": models.ComparisonData,
    "order_book": models.OrderBookData,
    "trade_flow": models.TradeFlowData,
    "tca_report": models.TCARportData,
}


def _new_id(panel_type: str) -> str:
    return f"{panel_type}-{uuid.uuid4().hex[:8]}"


def run_skill(
    panel_type: str,
    params: dict,
    layout: dict,
    title: Optional[str] = None,
    panel_id: Optional[str] = None,
    retries: int = 2,
) -> dict:
    """Build a single validated panel dict. Always returns a panel (error panel on failure)."""
    skill = skills.SKILLS.get(panel_type)
    pid = panel_id or _new_id(panel_type)
    if skill is None:
        return _error_panel(pid, panel_type, layout, title or panel_type, "Unknown panel type")

    model = DATA_MODELS[panel_type]
    last_err = ""
    for _ in range(retries + 1):
        try:
            raw = skill.builder(params)
            validated = model.model_validate(raw)
            return {
                "id": pid,
                "type": panel_type,
                "title": title or _derive_title(skill, params),
                "layout": layout,
                "status": "ok",
                "note": None,
                "data": validated.model_dump(),
            }
        except Exception as exc:  # noqa: BLE001 — harness intentionally broad
            last_err = str(exc)
            continue
    return _error_panel(pid, panel_type, layout, title or skill.default_title, last_err)


def _derive_title(skill: "skills.SkillDef", params: dict) -> str:
    sym = params.get("symbol")
    syms = params.get("symbols")
    scope = params.get("scope") or params.get("sector")
    if skill.panel_type == "comparison" and syms:
        return " vs ".join(s.upper() for s in syms)
    if sym:
        return f"{sym.upper()} · {skill.default_title}"
    if scope:
        return f"{scope.title() if isinstance(scope, str) else scope} · {skill.default_title}"
    return skill.default_title


def _error_panel(pid, panel_type, layout, title, message) -> dict:
    return {
        "id": pid,
        "type": panel_type,
        "title": title,
        "layout": layout,
        "status": "error",
        "note": f"This panel could not be built: {message}",
        "data": None,
    }


# --- layout packing on a 12-column grid ---
def pack_layout(width: int, height: int, cursor: dict) -> dict:
    """Flow-pack a panel of (width,height) cols/rows; mutates cursor {x,y,rowH}."""
    w = max(3, min(12, int(width or 6)))
    h = max(2, min(6, int(height or 4)))
    if cursor["x"] + w > 12:
        cursor["x"] = 0
        cursor["y"] += cursor["rowH"]
        cursor["rowH"] = 0
    layout = {"x": cursor["x"], "y": cursor["y"], "w": w, "h": h}
    cursor["x"] += w
    cursor["rowH"] = max(cursor["rowH"], h)
    return layout
