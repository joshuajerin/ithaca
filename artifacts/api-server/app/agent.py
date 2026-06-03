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

from . import ai, data, harness, repo, skills, state


# ----------------------------- tool schemas -----------------------------
def _tools() -> list:
    syms = ", ".join(repo.all_symbols())
    secs = ", ".join(data.SECTORS.keys())
    sizing = "Width is grid columns 3-12 (12 = full row). Height is row units 2-6."
    strategies = "iron_condor, straddle, strangle, bull_call_spread, bear_put_spread, covered_call, long_call, long_put"
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
        {"type": "function", "function": {
            "name": "add_macro_dashboard",
            "description": (
                f"Add a macro/cross-asset dashboard panel. {sizing} "
                "Use when the user asks for a macro view, global dashboard, risk-on/risk-off view, "
                "or a theme-specific cross-asset panel. Themes: global (default), inflation, china, risk."
            ),
            "parameters": {"type": "object", "properties": {
                "theme": {"type": "string", "enum": ["global", "inflation", "china", "risk"],
                          "description": "Macro theme: global (rates/FX/commodities/equities), "
                                         "inflation (rates/breakevens/commodities), "
                                         "china (China equities/CNH/iron ore), "
                                         "risk (risk-on/off: SPX/VIX/gold/dollar)."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_yield_curve",
            "description": f"Add a yield curve panel (spot + historical overlays, inversion highlights). {sizing}",
            "parameters": {"type": "object", "properties": {
                "region": {"type": "string", "enum": ["US", "UK", "DE", "JP"], "description": "Sovereign issuer. Default US."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_bond_rv",
            "description": f"Add a bond relative-value panel: Z-spread, OAS and asset-swap vs peers. {sizing}",
            "parameters": {"type": "object", "properties": {
                "ticker": {"type": "string", "description": "Bond issuer ticker (e.g. AAPL, MSFT, F, INTC, META, XOM, AMZN, GOOGL, NVDA, CVX)."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["ticker"]},
        }},
        {"type": "function", "function": {
            "name": "add_cds_pricer",
            "description": f"Price a credit default swap on a reference entity. {sizing}",
            "parameters": {"type": "object", "properties": {
                "ticker": {"type": "string", "description": "Reference entity ticker (e.g. F, INTC, OXY, META, AMZN, AAPL, MSFT, XOM, NVDA, GOOGL)."},
                "tenor": {"type": "string", "enum": ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y"]},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["ticker"]},
        }},
        {"type": "function", "function": {
            "name": "add_cashflow_duration",
            "description": f"Show bond cash flows, duration, convexity, and rate-shock scenario table. {sizing}",
            "parameters": {"type": "object", "properties": {
                "bond": {"type": "string", "description": "Bond key: UST10Y, UST30Y, UST5Y, UST2Y, AAPL30, MSFT10, F7Y."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_portfolio_risk",
            "description": f"Add a portfolio risk breakdown (VaR histogram, factor exposures, risk summary) for a list of tickers. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio tickers. Valid: {syms}"},
                "portfolio_name": {"type": "string", "description": "Optional display name for the portfolio."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_backtest",
            "description": f"Add a strategy backtest (equity curve vs benchmark, drawdown chart, Sharpe/CAGR stats) for one ticker. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "strategy": {"type": "string", "description": "Strategy name, e.g. 'momentum', 'mean_reversion', 'buy_and_hold'."},
                "range": {"type": "string", "enum": ["1M", "3M", "6M", "1Y", "YTD"]},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_correlation_matrix",
            "description": f"Add a pairwise correlation heatmap with beta/hedge-ratio table for a list of tickers. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Tickers. Valid: {syms}"},
                "window": {"type": "integer", "description": "Rolling window in days: 30 or 90.", "enum": [30, 90]},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_factor_analysis",
            "description": f"Add a factor return attribution (momentum, value, size, quality) with monthly breakdown and factor loading table for one ticker. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_iv_surface",
            "description": f"Add an implied volatility surface heatmap for a ticker. {sizing} Use for vol surface, IV surface, or skew requests.",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_options_strategy",
            "description": f"Add an options strategy payoff diagram with Greeks. {sizing} Use for options trades, straddles, condors, spreads etc.",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Underlying ticker. One of: {syms}"},
                "strategy": {"type": "string", "description": f"Strategy type. One of: {strategies}"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol", "strategy"]},
        }},
        {"type": "function", "function": {
            "name": "add_vol_term_structure",
            "description": f"Add a volatility term structure chart across expiries. {sizing} Use for VIX curve, vol term structure, contango/backwardation requests.",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker or 'VIX'. One of: {syms}, VIX"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_structured_product",
            "description": f"Add a structured/exotic product pricer (barrier options). {sizing} Use for barrier options, down-and-out, up-and-out, exotic products.",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Underlying ticker. One of: {syms}"},
                "productType": {"type": "string", "description": "Product type: down_and_out_call, up_and_out_call, down_and_in_put, up_and_in_call"},
                "tenor": {"type": "number", "description": "Tenor in years (e.g. 0.5 for 6M)"},
                "notional": {"type": "number", "description": "Notional in USD"},
                "barrier_pct": {"type": "number", "description": "Barrier as fraction of spot (e.g. 0.85 for 85%)"},
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
    "add_macro_dashboard": "macro_dashboard",
    "add_yield_curve": "yield_curve",
    "add_bond_rv": "bond_rv",
    "add_cds_pricer": "cds_pricer",
    "add_cashflow_duration": "cashflow_duration",
    "add_portfolio_risk": "portfolio_risk",
    "add_backtest": "backtest",
    "add_correlation_matrix": "correlation_matrix",
    "add_factor_analysis": "factor_analysis",
    "add_iv_surface": "iv_surface",
    "add_options_strategy": "options_strategy",
    "add_vol_term_structure": "vol_term_structure",
    "add_structured_product": "structured_product",
}


def _system_prompt() -> str:
    return (
        "You are the orchestrator of an agentic market terminal that tracks live market "
        "data across three sectors: semiconductors, energy, and AI/tech. When the user sends a "
        "request, you compose a focused dashboard by calling the panel tools. Rules:\n"
        "- Call multiple tools in one turn to build a coherent dashboard (typically 2-5 panels).\n"
        "- Choose panel types that actually answer the request. For a single stock deep-dive, a "
        "price chart + fundamentals + news + analysis works well. For 'what's moving', use a "
        "heatmap + screener. For comparisons, use the comparison tool.\n"
        "- For derivatives requests: vol surface → add_iv_surface; options strategy → add_options_strategy; "
        "VIX/vol curve → add_vol_term_structure; barrier/exotic → add_structured_product.\n"
        "- For macro and fixed income: global view → add_macro_dashboard; yield curve → add_yield_curve; "
        "bond RV → add_bond_rv; CDS → add_cds_pricer; duration/cash flows → add_cashflow_duration.\n"
        "- For microstructure/execution requests: order book → add_order_book; trade flow/unusual activity → add_trade_flow; "
        "TCA/slippage → add_tca_report.\n"
        "- Decide each panel's width (3-12 grid columns) and height (2-6 row units). Make the "
        "primary panel larger; supporting panels narrower. A full-width hero is width 12.\n"
        "- Only use tickers and sectors that exist in the dataset.\n"
        "- After the tool calls, the panels are rendered for the user; your text content should be "
        "a one or two sentence summary of what you assembled and why. Keep it crisp.\n"
        f"- Valid tickers: {', '.join(repo.all_symbols())}.\n"
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
    if reset:
        base = []
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
    "macro_dashboard": "a macro dashboard",
    "yield_curve": "a yield curve",
    "bond_rv": "bond relative value",
    "cds_pricer": "a CDS pricer",
    "cashflow_duration": "cash flow & duration",
    "portfolio_risk": "a portfolio risk breakdown",
    "backtest": "a backtest",
    "correlation_matrix": "a correlation matrix",
    "factor_analysis": "a factor analysis",
    "iv_surface": "an IV surface",
    "options_strategy": "an options strategy",
    "vol_term_structure": "a vol term structure",
    "structured_product": "a structured product pricer",
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
    for s in repo.all_symbols():
        if s in tokens or s in dollar:
            if s in _AMBIGUOUS_TICKERS and s not in explicit_upper and s not in dollar:
                continue
            found.append(s)
    # also match by leading company-name word (whole word only)
    if not found:
        low = q.lower()
        for s, c in repo.get_all_companies().items():
            short = c["name"].split()[0].lower()
            if len(short) > 3 and re.search(r"\b" + re.escape(short) + r"\b", low):
                found.append(s)
    return found


def _extract_strategy(q: str) -> str:
    q = q.lower()
    if "iron condor" in q or "condor" in q:
        return "iron_condor"
    if "straddle" in q:
        return "straddle"
    if "strangle" in q:
        return "strangle"
    if "bull" in q and ("spread" in q or "call" in q):
        return "bull_call_spread"
    if "bear" in q and ("spread" in q or "put" in q):
        return "bear_put_spread"
    if "covered call" in q or "buy write" in q:
        return "covered_call"
    if " put" in q or "put " in q:
        return "long_put"
    if " call" in q or "call " in q:
        return "long_call"
    return "straddle"


def _orchestrate_heuristic(query: str, start_y: int = 0):
    q = query.lower()
    cursor = {"x": 0, "y": start_y, "rowH": 0}
    panels: List[dict] = []

    def add(panel_type, params, w, h, title=None):
        layout = harness.pack_layout(w, h, cursor)
        panels.append(harness.run_skill(panel_type, params, layout, title=title))

    symbols = _extract_symbols(query)
    sector = repo.resolve_sector(query)

    wants_compare = any(k in q for k in ["compare", "vs", "versus", "against"]) or len(symbols) >= 2
    wants_news = "news" in q or "headline" in q or "happening" in q
    wants_sentiment = any(k in q for k in ["sentiment", "buzz", "mood", "social"])
    wants_overview = any(k in q for k in ["overview", "moving", "market", "movers", "heatmap", "today"])
    wants_screen = any(k in q for k in ["screen", "screener", "scan", "list", "top "])
    wants_order_book = any(k in q for k in ["order book", "orderbook", "bid", "ask", "depth", "level 2", "l2"])
    wants_trade_flow = any(k in q for k in ["unusual", "block", "sweep", "dark pool", "flow", "activity"])
    wants_tca = any(k in q for k in ["tca", "transaction cost", "slippage", "vwap", "twap", "execution", "impl"])
    wants_macro = any(k in q for k in [
        "macro", "cross-asset", "cross asset", "global dashboard", "risk-on", "risk-off",
        "risk on", "risk off", "roro", "rates fx", "inflation dashboard", "china macro",
        "global risk", "mosaic",
    ])
    wants_yield_curve = any(k in q for k in ["yield curve", "treasury curve", "rates curve", "rate curve", "interest rate", "treasury yield", "yield spread", "2s10s", "inversion"])
    wants_bond_rv = any(k in q for k in ["bond rv", "bond relative value", "z-spread", "z spread", "oas", "asset swap", "asset-swap", "corporate bond", "credit spread"])
    wants_cds = any(k in q for k in ["cds", "credit default swap", "credit risk", "default swap", "survival prob"])
    wants_cashflow = any(k in q for k in ["cash flow", "cashflow", "duration", "convexity", "dv01", "rate sensitivity", "bond cash", "modified duration"])
    wants_risk = any(k in q for k in ["risk", "var", "value at risk", "tracking error", "factor exposure", "portfolio risk"])
    wants_backtest = any(k in q for k in ["backtest", "back test", "back-test", "momentum strategy", "strategy", "sharpe", "cagr", "drawdown"])
    wants_correlation = any(k in q for k in ["correlation", "correlat", "hedge ratio", "co-movement", "diversif", "beta table"])
    wants_factor = any(k in q for k in ["factor analysis", "factor", "attribution", "alpha", "loading", "momentum factor", "value factor"])

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

    if wants_macro:
        # Detect theme from query
        theme = "global"
        if any(k in q for k in ["inflation", "breakeven", "tips", "cpi"]):
            theme = "inflation"
        elif any(k in q for k in ["china", "chinese", "csi", "hscei", "cnh"]):
            theme = "china"
        elif any(k in q for k in ["risk-on", "risk-off", "risk on", "risk off", "roro", "vix"]):
            theme = "risk"
        add("macro_dashboard", {"theme": theme}, 12, 6)
        theme_labels = {"global": "Global Macro", "inflation": "Inflation", "china": "China Macro", "risk": "Risk-On/Off"}
        return panels, f"{theme_labels.get(theme, 'Macro')} dashboard: rates, FX, commodities, and equity indices in one view."

    # --- Fixed income heuristics ---
    if wants_yield_curve:
        region = "US"
        for r in ["UK", "DE", "JP"]:
            if r.lower() in q:
                region = r
        add("yield_curve", {"region": region}, 8, 5)
        add("news", {"scope_type": "sector", "scope": "energy"}, 4, 5)
        return panels, f"{region} Treasury yield curve with historical overlays and spread analysis."

    if wants_cds:
        cds_entities = {"ford": "F", "intel": "INTC", "occidental": "OXY", "oxy": "OXY",
                        "meta": "META", "amazon": "AMZN", "apple": "AAPL",
                        "microsoft": "MSFT", "exxon": "XOM", "nvidia": "NVDA",
                        "alphabet": "GOOGL", "google": "GOOGL"}
        ticker = "F"
        for name, sym in cds_entities.items():
            if name in q:
                ticker = sym
                break
        if symbols:
            cds_tickers = {"F", "INTC", "OXY", "META", "AMZN", "AAPL", "MSFT", "XOM", "NVDA", "GOOGL"}
            for s in symbols:
                if s in cds_tickers:
                    ticker = s
                    break
        add("cds_pricer", {"ticker": ticker}, 7, 5)
        add("bond_rv", {"ticker": ticker}, 5, 5)
        return panels, f"CDS pricer for {ticker} with survival curve, default probabilities, and bond RV context."

    if wants_bond_rv:
        ticker = "AAPL"
        bond_tickers = {"AAPL", "MSFT", "META", "AMZN", "GOOGL", "NVDA", "INTC", "F", "XOM", "CVX"}
        for s in symbols:
            if s in bond_tickers:
                ticker = s
                break
        add("bond_rv", {"ticker": ticker}, 8, 5)
        add("yield_curve", {"region": "US"}, 4, 5)
        return panels, f"Bond relative value for {ticker}: Z-spread, OAS, and asset-swap vs peers."

    if wants_cashflow:
        bond_map = {"30y": "UST30Y", "30-year": "UST30Y", "30 year": "UST30Y",
                    "10y": "UST10Y", "10-year": "UST10Y", "10 year": "UST10Y",
                    "5y": "UST5Y", "5-year": "UST5Y", "5 year": "UST5Y",
                    "2y": "UST2Y", "2-year": "UST2Y", "2 year": "UST2Y",
                    "aapl": "AAPL30", "apple": "AAPL30",
                    "msft": "MSFT10", "microsoft": "MSFT10",
                    "ford": "F7Y", " f ": "F7Y"}
        bond_key = "UST10Y"
        for kw, bk in bond_map.items():
            if kw in q:
                bond_key = bk
                break
        add("cashflow_duration", {"bond": bond_key}, 8, 6)
        add("yield_curve", {"region": "US"}, 4, 5)
        return panels, f"Cash flow schedule, duration/convexity, and rate-shock scenarios for {bond_key}."

    if wants_risk:
        port_syms = symbols if symbols else ["NVDA", "MSFT", "GOOGL", "META", "AMZN"]
        add("portfolio_risk", {"symbols": port_syms}, 12, 5)
        summary = f"Portfolio risk breakdown for {', '.join(port_syms[:3])}{'...' if len(port_syms) > 3 else ''}: VaR, factor exposures, and risk metrics."
        return panels, summary

    if wants_backtest and symbols:
        sym = symbols[0]
        strategy = "momentum"
        if "mean" in q or "reversion" in q:
            strategy = "mean_reversion"
        elif "buy" in q and "hold" in q:
            strategy = "buy_and_hold"
        add("backtest", {"symbol": sym, "strategy": strategy}, 12, 6)
        name = data.get_company(sym)["name"]
        summary = f"Backtest of {strategy.replace('_', ' ')} strategy on {name}: equity curve, drawdown, and performance stats."
        return panels, summary

    if wants_correlation and (len(symbols) >= 2 or sector):
        if len(symbols) < 2 and sector:
            symbols = data.symbols_in_sector(sector)[:5]
        if len(symbols) < 2:
            symbols = ["NVDA", "AMD", "MSFT", "GOOGL", "META"]
        add("correlation_matrix", {"symbols": symbols[:6], "window": 90}, 12, 5)
        summary = f"Pairwise correlation matrix for {', '.join(symbols[:4])}{'...' if len(symbols) > 4 else ''} with beta/hedge-ratio table."
        return panels, summary

    if wants_factor and symbols:
        sym = symbols[0]
        name = data.get_company(sym)["name"]
        add("factor_analysis", {"symbol": sym}, 12, 5)
        summary = f"Factor attribution analysis for {name}: momentum, value, size, and quality decomposition."
        return panels, summary

    # --- derivatives / volatility heuristics ---
    wants_iv_surface = any(k in q for k in ["vol surface", "iv surface", "implied vol", "volatility surface", "skew"])
    wants_options = any(k in q for k in [
        "iron condor", "straddle", "strangle", "condor", "options strategy",
        "bull spread", "bear spread", "covered call", "build a", "long call", "long put",
    ])
    wants_vol_ts = any(k in q for k in ["vix", "vol term", "term structure", "contango", "backwardation", "vol curve"])
    wants_structured = any(k in q for k in [
        "barrier", "down-and-out", "up-and-out", "knock out", "knock in",
        "structured", "exotic", "pricer",
    ])

    if wants_iv_surface and symbols:
        sym = symbols[0]
        add("iv_surface", {"symbol": sym}, 8, 5)
        add("vol_term_structure", {"symbol": sym}, 4, 5)
        name = data.get_company(sym)["name"]
        return panels, f"{name} implied vol surface with 1M skew strip and term structure."

    if wants_iv_surface:
        add("iv_surface", {"symbol": "NVDA"}, 8, 5)
        add("vol_term_structure", {"symbol": "NVDA"}, 4, 5)
        return panels, "NVDA implied vol surface and term structure (default)."

    if wants_options and symbols:
        sym = symbols[0]
        strategy = _extract_strategy(query)
        add("options_strategy", {"symbol": sym, "strategy": strategy}, 8, 5)
        add("price_chart", {"symbol": sym, "range": "1M"}, 4, 5)
        name = data.get_company(sym)["name"]
        return panels, f"{name} {strategy.replace('_', ' ').title()} strategy with payoff diagram and Greeks."

    if wants_vol_ts:
        sym = symbols[0] if symbols else "VIX"
        add("vol_term_structure", {"symbol": sym}, 8, 5)
        if symbols:
            add("iv_surface", {"symbol": sym}, 4, 5)
        name = sym
        return panels, f"{name} volatility term structure with contango/backwardation regime."

    if wants_structured and symbols:
        sym = symbols[0]
        add("structured_product", {"symbol": sym, "productType": "down_and_out_call"}, 8, 5)
        add("price_chart", {"symbol": sym, "range": "3M"}, 4, 5)
        name = data.get_company(sym)["name"]
        return panels, f"{name} down-and-out barrier option pricer with scenario table."

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
        name = repo.get_company(sym)["name"]
        return panels, f"Deep-dive on {name}: price, fundamentals, news and an AI read."

    if sector:
        add("heatmap", {"sector": sector}, 7, 4)
        add("screener", {"sector": sector}, 5, 4)
        if wants_news or True:
            add("news", {"scope_type": "sector", "scope": sector}, 6, 4)
        add("analysis", {"scope_type": "sector", "scope": sector}, 6, 4)
        return panels, f"{repo.sector_name(sector)} overview: heatmap, screener, news and analysis."

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
    tool = next(
        (t for t in _tools() if _TOOL_TO_TYPE.get(t["function"]["name"]) == panel_type),
        None
    )
    if tool is None:
        raise RuntimeError(f"no tool for panel type {panel_type}")
    current = {"type": panel_type, "title": panel.get("title")}
    sys = (
        "You update a single dashboard panel in a market terminal. Keep the panel the SAME "
        "type. Call the provided tool exactly once with the parameters that satisfy the user's "
        "instruction. Use only valid tickers and sectors.\n"
        f"Valid tickers: {', '.join(repo.all_symbols())}. Valid sectors: {', '.join(data.SECTORS.keys())}."
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
    sector = repo.resolve_sector(instruction)
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
    if panel_type in ("iv_surface", "vol_term_structure") and syms:
        return {"symbol": syms[0]}
    if panel_type == "options_strategy" and syms:
        return {"symbol": syms[0], "strategy": _extract_strategy(instruction)}
    if panel_type == "structured_product" and syms:
        return {"symbol": syms[0]}
    # fall back: rebuild from current data identity
    d = panel.get("data") or {}
    if panel_type in ("price_chart", "fundamentals") and d.get("symbol"):
        return {"symbol": d["symbol"]}
    if panel_type in ("iv_surface", "vol_term_structure", "options_strategy", "structured_product") and d.get("symbol"):
        params = {"symbol": d["symbol"]}
        if panel_type == "options_strategy":
            params["strategy"] = _extract_strategy(instruction)
        return params
    return {}
