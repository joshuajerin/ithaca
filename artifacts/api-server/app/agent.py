"""Top-level orchestration agent.

Given a natural-language query, the agent uses LLM tool-calling to decide which
panel skills to dispatch and how wide/tall each should be. Each tool call is run
through the validation harness. If the LLM is unavailable, a keyword heuristic
composes a reasonable dashboard instead.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import List, Optional

from . import ai, data, harness, skills, state


# ----------------------------- tool schemas -----------------------------
def _tools() -> list:
    syms = ", ".join(data.all_symbols())
    secs = ", ".join(data.SECTORS.keys())
    sizing = "Width is grid columns 3-12 (12 = full row). Height is row units 2-6."
    return [
        {"type": "function", "function": {
            "name": "add_price_chart",
            "description": f"Add a price chart for one ticker. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "range": {"type": "string", "enum": ["1M", "3M", "6M", "1Y", "YTD"]},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_news",
            "description": f"Add curated news for a ticker or sector. {sizing}",
            "parameters": {"type": "object", "properties": {
                "scope_type": {"type": "string", "enum": ["symbol", "sector"]},
                "scope": {"type": "string", "description": f"A ticker ({syms}) or sector ({secs})."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["scope_type", "scope"]},
        }},
        {"type": "function", "function": {
            "name": "add_analysis",
            "description": f"Add an AI analytic read for a ticker or sector. {sizing}",
            "parameters": {"type": "object", "properties": {
                "scope_type": {"type": "string", "enum": ["symbol", "sector"]},
                "scope": {"type": "string"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["scope_type", "scope"]},
        }},
        {"type": "function", "function": {
            "name": "add_fundamentals",
            "description": f"Add fundamentals for one ticker. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_screener",
            "description": f"Add a screener table for a sector (omit sector for whole market). {sizing}",
            "parameters": {"type": "object", "properties": {
                "sector": {"type": "string", "description": f"Sector ({secs}) or omit."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_heatmap",
            "description": f"Add a market/sector heatmap (omit sector for whole market). {sizing}",
            "parameters": {"type": "object", "properties": {
                "sector": {"type": "string"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_sentiment",
            "description": f"Add a sentiment read for a ticker or sector. {sizing}",
            "parameters": {"type": "object", "properties": {
                "scope_type": {"type": "string", "enum": ["symbol", "sector"]},
                "scope": {"type": "string"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["scope_type", "scope"]},
        }},
        {"type": "function", "function": {
            "name": "add_comparison",
            "description": f"Add a side-by-side comparison of 2+ tickers. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_order_book",
            "description": f"Add an order book depth ladder and tape of recent prints for one ticker. Use when the user asks about the order book, bid/ask depth, or level 2 data. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_trade_flow",
            "description": f"Add a trade flow / unusual activity panel showing block prints, dark pool activity and buy/sell imbalance for one ticker. Use when the user asks about unusual activity, block trades, sweeps, or dark pool flow. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_tca_report",
            "description": f"Add a Transaction Cost Analysis (TCA) report comparing execution price to VWAP/TWAP benchmarks and showing implementation shortfall for one ticker. Use when the user asks about TCA, execution quality, slippage, or benchmark comparison. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
    ]


_TOOL_TO_TYPE = {
    "add_price_chart": "price_chart",
    "add_news": "news",
    "add_analysis": "analysis",
    "add_fundamentals": "fundamentals",
    "add_screener": "screener",
    "add_heatmap": "heatmap",
    "add_sentiment": "sentiment",
    "add_comparison": "comparison",
    "add_order_book": "order_book",
    "add_trade_flow": "trade_flow",
    "add_tca_report": "tca_report",
}


def _system_prompt() -> str:
    return (
        "You are the orchestrator of an agentic market terminal that runs on curated MOCK "
        "data across three sectors: semiconductors, energy, and AI/tech. When the user sends a "
        "request, you compose a focused dashboard by calling the panel tools. Rules:\n"
        "- Call multiple tools in one turn to build a coherent dashboard (typically 2-5 panels).\n"
        "- Choose panel types that actually answer the request. For a single stock deep-dive, a "
        "price chart + fundamentals + news + analysis works well. For 'what's moving', use a "
        "heatmap + screener. For comparisons, use the comparison tool.\n"
        "- Decide each panel's width (3-12 grid columns) and height (2-6 row units). Make the "
        "primary panel larger; supporting panels narrower. A full-width hero is width 12.\n"
        "- Only use tickers and sectors that exist in the dataset.\n"
        "- After the tool calls, the panels are rendered for the user; your text content should be "
        "a one or two sentence summary of what you assembled and why. Keep it crisp.\n"
        f"- Valid tickers: {', '.join(data.all_symbols())}.\n"
        f"- Valid sectors: {', '.join(data.SECTORS.keys())}."
    )


def orchestrate(query: str, session_id: Optional[str]) -> dict:
    # New queries ADD to the existing dashboard for the session rather than
    # replacing it, so asking a follow-up keeps the panels already on screen.
    reset = _wants_reset(query)
    # A reset (or the "default" placeholder) starts a brand-new session so that
    # BOTH the panels and the prior conversation context start fresh.
    if reset or not session_id or session_id == "default":
        sid = uuid.uuid4().hex[:12]
    else:
        sid = session_id
    base: List[dict] = state.get_dashboard(sid)
    start_y = _next_row(base)

    panels: List[dict] = []
    summary = ""

    if ai.ai_available():
        try:
            panels, summary = _orchestrate_llm(query, sid, base, start_y)
        except Exception:
            panels, summary = [], ""

    if not panels:
        panels, summary = _orchestrate_heuristic(query, start_y)

    combined = base + panels
    state.set_dashboard(sid, combined)
    state.append_history(sid, "user", query)
    state.append_history(sid, "assistant", summary)
    return {"sessionId": sid, "summary": summary, "panels": combined}


# Phrases that mean "throw away what's there and start a fresh dashboard".
# Matched on word boundaries to avoid false positives (e.g. "preset", "swipe").
_RESET_PATTERNS = (
    r"\breset\b", r"\bwipe\b", r"\bclear the\b", r"\bclear everything\b",
    r"\bstart over\b", r"\bstart fresh\b", r"\bnew dashboard\b",
    r"\bclean slate\b", r"\bblank slate\b", r"\bremove everything\b",
)


def _wants_reset(query: str) -> bool:
    q = query.lower()
    return any(re.search(p, q) for p in _RESET_PATTERNS)


def _next_row(panels: List[dict]) -> int:
    """Grid row at which new panels should begin (just below existing ones)."""
    if not panels:
        return 0
    return max(p["layout"]["y"] + p["layout"]["h"] for p in panels)


def _orchestrate_llm(query: str, sid: str, existing: List[dict], start_y: int):
    messages = [{"role": "system", "content": _system_prompt()}]
    for h in state.get_history(sid)[-4:]:
        messages.append({"role": h["role"], "content": h["content"]})
    if existing:
        shown = ", ".join(f'{p.get("title")} ({p["type"]})' for p in existing)
        messages.append({"role": "system", "content": (
            "The dashboard ALREADY shows these panels: " + shown + ". "
            "The user is making a follow-up request — ADD new panels that answer it and "
            "complement what is already shown. Do NOT recreate panels that already exist. "
            "Your text summary should describe only what you just added."
        )})
    messages.append({"role": "user", "content": query})

    msg = ai.chat(messages, tools=_tools(), tool_choice="auto")
    tool_calls = getattr(msg, "tool_calls", None) or []
    panels: List[dict] = []
    cursor = {"x": 0, "y": start_y, "rowH": 0}
    for tc in tool_calls:
        name = tc.function.name
        panel_type = _TOOL_TO_TYPE.get(name)
        if not panel_type:
            continue
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        layout = harness.pack_layout(args.get("width"), args.get("height"), cursor)
        panels.append(harness.run_skill(panel_type, args, layout))
    summary = (msg.content or "").strip()
    if not summary and panels:
        summary = _describe(panels)
    return panels, summary


_TYPE_LABELS = {
    "price_chart": "a price chart",
    "news": "news",
    "analysis": "an AI analysis",
    "fundamentals": "fundamentals",
    "screener": "a screener",
    "heatmap": "a heatmap",
    "sentiment": "a sentiment read",
    "comparison": "a comparison",
    "order_book": "an order book",
    "trade_flow": "a trade flow panel",
    "tca_report": "a TCA report",
}


def _describe(panels: List[dict]) -> str:
    parts: List[str] = []
    for p in panels:
        label = _TYPE_LABELS.get(p["type"], p["type"])
        if label not in parts:
            parts.append(label)
    if not parts:
        return "Composed your dashboard."
    if len(parts) == 1:
        body = parts[0]
    else:
        body = ", ".join(parts[:-1]) + " and " + parts[-1]
    return f"Assembled {body}."


# ----------------------------- heuristic fallback -----------------------------
# Tickers that are also common English words; only match these when the user
# wrote them in uppercase or with a $ prefix (an explicit ticker signal).
_AMBIGUOUS_TICKERS = {"NOW", "COP"}


def _extract_symbols(q: str) -> List[str]:
    up = q.upper()
    # whole-word uppercase tokens only — avoids substring collisions (e.g. "scope" -> COP)
    tokens = set(re.findall(r"\b[A-Z]{1,6}\b", up))
    explicit_upper = set(re.findall(r"\b[A-Z]{2,6}\b", q))  # uppercase in the ORIGINAL text
    dollar = {d.upper() for d in re.findall(r"\$([A-Za-z]{1,6})", q)}
    found: List[str] = []
    for s in data.all_symbols():
        if s in tokens or s in dollar:
            if s in _AMBIGUOUS_TICKERS and s not in explicit_upper and s not in dollar:
                continue
            found.append(s)
    # also match by leading company-name word (whole word only)
    if not found:
        low = q.lower()
        for s, c in data.COMPANIES.items():
            short = c["name"].split()[0].lower()
            if len(short) > 3 and re.search(r"\b" + re.escape(short) + r"\b", low):
                found.append(s)
    return found


def _orchestrate_heuristic(query: str, start_y: int = 0):
    q = query.lower()
    cursor = {"x": 0, "y": start_y, "rowH": 0}
    panels: List[dict] = []

    def add(panel_type, params, w, h, title=None):
        layout = harness.pack_layout(w, h, cursor)
        panels.append(harness.run_skill(panel_type, params, layout, title=title))

    symbols = _extract_symbols(query)
    sector = data.resolve_sector(query)

    wants_compare = any(k in q for k in ["compare", "vs", "versus", "against"]) or len(symbols) >= 2
    wants_news = "news" in q or "headline" in q or "happening" in q
    wants_sentiment = any(k in q for k in ["sentiment", "buzz", "mood", "social"])
    wants_overview = any(k in q for k in ["overview", "moving", "market", "movers", "heatmap", "today"])
    wants_screen = any(k in q for k in ["screen", "screener", "scan", "list", "top "])
    wants_order_book = any(k in q for k in ["order book", "orderbook", "bid", "ask", "depth", "level 2", "l2"])
    wants_trade_flow = any(k in q for k in ["unusual", "block", "sweep", "dark pool", "flow", "activity"])
    wants_tca = any(k in q for k in ["tca", "transaction cost", "slippage", "vwap", "twap", "execution", "impl"])

    if wants_order_book and symbols:
        sym = symbols[0]
        add("order_book", {"symbol": sym}, 6, 5)
        add("price_chart", {"symbol": sym, "range": "1M"}, 6, 4)
        name = data.get_company(sym)["name"]
        return panels, f"{name} order book depth ladder and tape."

    if wants_trade_flow and symbols:
        sym = symbols[0]
        add("trade_flow", {"symbol": sym}, 8, 5)
        add("price_chart", {"symbol": sym, "range": "1M"}, 4, 4)
        name = data.get_company(sym)["name"]
        return panels, f"{name} trade flow: block prints, dark pool activity and buy/sell imbalance."

    if wants_tca and symbols:
        sym = symbols[0]
        add("tca_report", {"symbol": sym}, 12, 5)
        name = data.get_company(sym)["name"]
        return panels, f"TCA report for {name}: arrival price vs VWAP/TWAP benchmarks with intraday participation."

    if wants_compare and len(symbols) >= 2:
        add("comparison", {"symbols": symbols}, 12, 4)
        add("price_chart", {"symbol": symbols[0]}, 6, 4)
        add("price_chart", {"symbol": symbols[1]}, 6, 4)
        summary = f"Comparing {', '.join(symbols)} side by side with price context."
        return panels, summary

    if symbols:
        sym = symbols[0]
        add("price_chart", {"symbol": sym, "range": "3M"}, 8, 4)
        add("fundamentals", {"symbol": sym}, 4, 4)
        if wants_sentiment:
            add("sentiment", {"scope_type": "symbol", "scope": sym}, 6, 4)
        add("news", {"scope_type": "symbol", "scope": sym}, 6, 4)
        add("analysis", {"scope_type": "symbol", "scope": sym}, 6, 4)
        name = data.get_company(sym)["name"]
        return panels, f"Deep-dive on {name}: price, fundamentals, news and an AI read."

    if sector:
        add("heatmap", {"sector": sector}, 7, 4)
        add("screener", {"sector": sector}, 5, 4)
        if wants_news or True:
            add("news", {"scope_type": "sector", "scope": sector}, 6, 4)
        add("analysis", {"scope_type": "sector", "scope": sector}, 6, 4)
        return panels, f"{data.sector_name(sector)} overview: heatmap, screener, news and analysis."

    if wants_sentiment:
        add("sentiment", {"scope_type": "sector", "scope": "ai_tech"}, 6, 4)
        add("news", {"scope_type": "sector", "scope": "ai_tech"}, 6, 4)
        return panels, "Current sentiment and news flow across AI/tech."

    # generic market overview
    add("heatmap", {}, 8, 4)
    add("screener", {}, 4, 5)
    add("news", {"scope_type": "sector", "scope": "ai_tech"}, 6, 4)
    add("analysis", {"scope_type": "sector", "scope": "semiconductors"}, 6, 4)
    return panels, "Market overview: a full heatmap, a screener, latest news and an AI read."


# ----------------------------- refine a single panel -----------------------------
def refine(session_id: str, panel_id: str, instruction: str) -> Optional[dict]:
    panel = state.get_panel(session_id, panel_id)
    if panel is None:
        return None
    panel_type = panel["type"]
    layout = panel["layout"]
    title = panel.get("title")

    params = _refine_params(panel_type, panel, instruction)
    updated = harness.run_skill(panel_type, params, layout, title=None, panel_id=panel_id)
    state.update_panel(session_id, updated)
    return updated


def _refine_params(panel_type: str, panel: dict, instruction: str) -> dict:
    """Decide new builder params for an existing panel given an instruction."""
    if ai.ai_available():
        try:
            return _refine_params_llm(panel_type, panel, instruction)
        except Exception:
            pass
    return _refine_params_heuristic(panel_type, panel, instruction)


def _refine_params_llm(panel_type: str, panel: dict, instruction: str) -> dict:
    tool = next(t for t in _tools() if _TOOL_TO_TYPE[t["function"]["name"]] == panel_type)
    current = {"type": panel_type, "title": panel.get("title")}
    sys = (
        "You update a single dashboard panel in a market terminal. Keep the panel the SAME "
        "type. Call the provided tool exactly once with the parameters that satisfy the user's "
        "instruction. Use only valid tickers and sectors.\n"
        f"Valid tickers: {', '.join(data.all_symbols())}. Valid sectors: {', '.join(data.SECTORS.keys())}."
    )
    msg = ai.chat(
        [
            {"role": "system", "content": sys},
            {"role": "user", "content": f"Current panel: {json.dumps(current)}\nInstruction: {instruction}"},
        ],
        tools=[tool],
        tool_choice={"type": "function", "function": {"name": tool["function"]["name"]}},
    )
    tcs = getattr(msg, "tool_calls", None) or []
    if not tcs:
        raise RuntimeError("no tool call")
    return json.loads(tcs[0].function.arguments or "{}")


def _refine_params_heuristic(panel_type: str, panel: dict, instruction: str) -> dict:
    syms = _extract_symbols(instruction)
    sector = data.resolve_sector(instruction)
    if panel_type in ("price_chart", "fundamentals") and syms:
        params = {"symbol": syms[0]}
        for r in ["1M", "3M", "6M", "1Y", "YTD"]:
            if r.lower() in instruction.lower():
                params["range"] = r
        return params
    if panel_type == "comparison" and len(syms) >= 2:
        return {"symbols": syms}
    if panel_type in ("news", "analysis", "sentiment"):
        if syms:
            return {"scope_type": "symbol", "scope": syms[0]}
        if sector:
            return {"scope_type": "sector", "scope": sector}
    if panel_type in ("screener", "heatmap") and sector:
        return {"sector": sector}
    # fall back: rebuild from current data identity
    d = panel.get("data") or {}
    if panel_type in ("price_chart", "fundamentals") and d.get("symbol"):
        return {"symbol": d["symbol"]}
    return {}
