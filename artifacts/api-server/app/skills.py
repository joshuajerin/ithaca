"""Skill registry. Each panel type is a skill with a descriptive setup and
subskills, plus a builder that turns resolved params into panel `data`.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

from . import ai, data

RANGE_DAYS = {"1M": 30, "3M": 90, "6M": 180, "1Y": 250, "YTD": 120}


# ----------------------------- formatting helpers -----------------------------
def fmt_usd(n: Optional[float]) -> str:
    if n is None:
        return "—"
    a = abs(n)
    if a >= 1_000_000_000_000:
        return f"${n/1_000_000_000_000:.2f}T"
    if a >= 1_000_000_000:
        return f"${n/1_000_000_000:.1f}B"
    if a >= 1_000_000:
        return f"${n/1_000_000:.1f}M"
    return f"${n:,.0f}"


def fmt_int(n: Optional[float]) -> str:
    if n is None:
        return "—"
    return f"{n:,.0f}"


# ----------------------------- builders -----------------------------
def build_price_chart(params: dict) -> dict:
    symbol = (params.get("symbol") or "NVDA").upper()
    company = data.get_company(symbol)
    if not company:
        raise ValueError(f"Unknown symbol: {symbol}")
    rng = (params.get("range") or "3M").upper()
    days = RANGE_DAYS.get(rng, 90)
    points = data.price_series(symbol, days=days)
    first = points[0]["c"] if points else company["price"]
    last = company["price"]
    change = round(last - first, 2)
    change_pct = round((change / first) * 100, 2) if first else 0.0
    return {
        "symbol": symbol,
        "name": company["name"],
        "currency": "USD",
        "last": last,
        "change": change,
        "changePct": change_pct,
        "range": rng,
        "points": points,
    }


def build_news(params: dict) -> dict:
    scope_type = params.get("scope_type") or ("symbol" if params.get("symbol") else "sector")
    scope = params.get("scope") or params.get("symbol") or params.get("sector") or "ai_tech"
    items = data.news_for(scope_type, scope)
    if scope_type == "symbol":
        company = data.get_company(scope.upper())
        label = company["name"] if company else scope.upper()
    else:
        sid = data.resolve_sector(scope) or scope
        label = data.sector_name(sid)
    return {"scope": label, "items": items}


def _fallback_analysis(scope_type: str, scope: str) -> dict:
    if scope_type == "symbol":
        company = data.get_company(scope.upper())
        name = company["name"] if company else scope.upper()
        chg = company["changePct"] if company else 0.0
        news = data.news_for("symbol", scope)
    else:
        sid = data.resolve_sector(scope) or scope
        name = data.sector_name(sid)
        syms = data.symbols_in_sector(sid)
        chg = round(sum(data.get_company(s)["changePct"] for s in syms) / max(len(syms), 1), 2) if syms else 0.0
        news = data.news_for("sector", scope)
    pos = sum(1 for n in news if n["sentiment"] == "positive")
    neg = sum(1 for n in news if n["sentiment"] == "negative")
    if chg > 0.5 and pos >= neg:
        stance, conf = "bullish", 0.66
    elif chg < -0.5 and neg >= pos:
        stance, conf = "bearish", 0.62
    else:
        stance, conf = "neutral", 0.55
    bullets = [n["headline"] for n in news[:4]] or [f"{name} trading roughly flat on light news flow."]
    summary = (
        f"{name} is screening {stance} today. Aggregate price action is "
        f"{'up' if chg >= 0 else 'down'} {abs(chg):.2f}% and recent headlines skew "
        f"{'positive' if pos > neg else 'negative' if neg > pos else 'mixed'}. "
        f"This is a mock, curated read for demonstration purposes."
    )
    return {
        "scope": name,
        "headline": f"{name}: {stance.capitalize()} on current flow",
        "summary": summary,
        "bullets": bullets,
        "stance": stance,
        "confidence": conf,
    }


def build_analysis(params: dict) -> dict:
    scope_type = params.get("scope_type") or ("symbol" if params.get("symbol") else "sector")
    scope = params.get("scope") or params.get("symbol") or params.get("sector") or "ai_tech"
    if not ai.ai_available():
        return _fallback_analysis(scope_type, scope)

    # Build grounding context from curated data.
    if scope_type == "symbol":
        company = data.get_company(scope.upper())
        if not company:
            return _fallback_analysis(scope_type, scope)
        name = company["name"]
        ctx = {
            "name": name,
            "symbol": company["symbol"],
            "sector": data.sector_name(company["sector"]),
            "price": company["price"],
            "dayChangePct": company["changePct"],
            "peRatio": company["peRatio"],
            "revenueUSD": company["revenue"],
            "netMarginPct": company["netMargin"],
            "description": company["description"],
        }
        news = data.news_for("symbol", scope)
    else:
        sid = data.resolve_sector(scope) or scope
        name = data.sector_name(sid)
        syms = data.symbols_in_sector(sid)
        ctx = {
            "sector": name,
            "constituents": [
                {"symbol": s, "changePct": data.get_company(s)["changePct"]} for s in syms
            ],
        }
        news = data.news_for("sector", scope)
    ctx["recentHeadlines"] = [{"headline": n["headline"], "sentiment": n["sentiment"]} for n in news[:6]]

    prompt = (
        "You are an equity analyst writing for a market terminal. Using ONLY the "
        "curated mock data provided, write a concise analytic read. Respond with a "
        "single JSON object and nothing else, matching exactly this shape: "
        '{"headline": string (max ~8 words), "summary": string (2-3 sentences), '
        '"bullets": array of 3-5 short strings, "stance": one of '
        '"bullish"|"neutral"|"bearish", "confidence": number between 0 and 1}. '
        "Do not invent precise figures beyond what is given.\n\nDATA:\n"
        + json.dumps(ctx)
    )
    msg = ai.chat(
        [
            {"role": "system", "content": "You output only valid JSON. No prose, no code fences."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    content = (msg.content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
    parsed = json.loads(content)
    parsed["scope"] = name
    # clamp/normalize
    parsed["stance"] = parsed.get("stance", "neutral")
    if parsed["stance"] not in ("bullish", "neutral", "bearish"):
        parsed["stance"] = "neutral"
    try:
        parsed["confidence"] = max(0.0, min(1.0, float(parsed.get("confidence", 0.6))))
    except (TypeError, ValueError):
        parsed["confidence"] = 0.6
    return parsed


def build_fundamentals(params: dict) -> dict:
    symbol = (params.get("symbol") or "NVDA").upper()
    company = data.get_company(symbol)
    if not company:
        raise ValueError(f"Unknown symbol: {symbol}")
    metrics = [
        {"label": "Last Price", "value": f"${company['price']:.2f}", "change": company["changePct"], "hint": "Day change %"},
        {"label": "Market Cap", "value": fmt_usd(company["marketCap"]), "change": None, "hint": None},
        {"label": "P/E (TTM)", "value": f"{company['peRatio']:.1f}" if company["peRatio"] else "N/A", "change": None, "hint": "Not meaningful if unprofitable" if not company["peRatio"] else None},
        {"label": "Revenue (TTM)", "value": fmt_usd(company["revenue"]), "change": None, "hint": None},
        {"label": "Net Margin", "value": f"{company['netMargin']:.1f}%", "change": None, "hint": None},
        {"label": "EPS (TTM)", "value": f"${company['eps']:.2f}", "change": None, "hint": None},
        {"label": "Dividend Yield", "value": f"{company['dividendYield']:.2f}%", "change": None, "hint": None},
        {"label": "Beta", "value": f"{company['beta']:.2f}", "change": None, "hint": None},
        {"label": "52W High", "value": f"${company['week52High']:.2f}", "change": None, "hint": None},
        {"label": "52W Low", "value": f"${company['week52Low']:.2f}", "change": None, "hint": None},
    ]
    return {"symbol": symbol, "name": company["name"], "metrics": metrics}


def build_screener(params: dict) -> dict:
    sector = params.get("sector")
    sid = data.resolve_sector(sector) if sector else None
    if sid:
        syms = data.symbols_in_sector(sid)
        title = f"{data.sector_name(sid)} Screener"
    else:
        syms = data.all_symbols()
        title = "Market Screener"
    rows = []
    for s in syms:
        c = data.get_company(s)
        rows.append({
            "symbol": s,
            "name": c["name"],
            "price": c["price"],
            "changePct": c["changePct"],
            "marketCap": c["marketCap"],
            "peRatio": c["peRatio"],
            "volume": c["volume"],
            "sector": data.sector_name(c["sector"]),
        })
    rows.sort(key=lambda r: r["marketCap"], reverse=True)
    return {"title": title, "rows": rows}


def build_heatmap(params: dict) -> dict:
    sector = params.get("sector") or params.get("scope")
    sid = data.resolve_sector(sector) if sector else None
    if sid:
        syms = data.symbols_in_sector(sid)
        title = f"{data.sector_name(sid)} Heatmap"
    else:
        syms = data.all_symbols()
        title = "Market Overview"
    cells = []
    for s in syms:
        c = data.get_company(s)
        cells.append({
            "symbol": s,
            "name": c["name"],
            "changePct": c["changePct"],
            "marketCap": c["marketCap"],
            "sector": data.sector_name(c["sector"]),
        })
    cells.sort(key=lambda x: x["marketCap"], reverse=True)
    return {"title": title, "cells": cells}


def build_sentiment(params: dict) -> dict:
    scope_type = params.get("scope_type") or ("symbol" if params.get("symbol") else "sector")
    scope = params.get("scope") or params.get("symbol") or params.get("sector") or "ai_tech"
    if scope_type == "symbol":
        company = data.get_company(scope.upper())
        name = company["name"] if company else scope.upper()
        news = data.news_for("symbol", scope)
        seed = data._seed(scope.upper())
    else:
        sid = data.resolve_sector(scope) or scope
        name = data.sector_name(sid)
        news = data.news_for("sector", scope)
        seed = data._seed(sid)
    pos = sum(1 for n in news if n["sentiment"] == "positive")
    neg = sum(1 for n in news if n["sentiment"] == "negative")
    total = max(len(news), 1)
    overall = round((pos - neg) / total, 2)
    if overall >= 0.5:
        label = "very_bullish"
    elif overall >= 0.15:
        label = "bullish"
    elif overall <= -0.5:
        label = "very_bearish"
    elif overall <= -0.15:
        label = "bearish"
    else:
        label = "neutral"

    def rnd(n):
        nonlocal seed
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    channels = ["Reddit", "X", "StockTwits", "News Wire"]
    sources = []
    for ch in channels:
        score = round(max(-1.0, min(1.0, overall + (rnd(0) - 0.5) * 0.5)), 2)
        sources.append({
            "channel": ch,
            "score": score,
            "volume": int(400 + rnd(0) * 5200),
            "change": round((rnd(0) - 0.5) * 40, 1),
        })
    trend = []
    today = date.today()
    base = overall
    for i in range(14):
        base = max(-1.0, min(1.0, base + (rnd(0) - 0.5) * 0.18))
        d = today - timedelta(days=13 - i)
        trend.append({"t": d.isoformat(), "score": round(base, 2)})
    # ensure trend ends near overall
    trend[-1]["score"] = overall
    return {"scope": name, "overall": overall, "label": label, "sources": sources, "trend": trend}


def build_comparison(params: dict) -> dict:
    symbols = params.get("symbols") or []
    symbols = [s.upper() for s in symbols if data.get_company(s.upper())]
    if len(symbols) < 2:
        # default to top semiconductors if not enough valid symbols
        symbols = ["NVDA", "AMD", "TSM"]
    metric_labels = ["Price", "Mkt Cap", "P/E", "Rev (TTM)", "Net Margin", "EPS", "Div Yield", "Beta"]
    companies = []
    for s in symbols:
        c = data.get_company(s)
        values = [
            {"label": "Price", "value": f"${c['price']:.2f}"},
            {"label": "Mkt Cap", "value": fmt_usd(c["marketCap"])},
            {"label": "P/E", "value": f"{c['peRatio']:.1f}" if c["peRatio"] else "N/A"},
            {"label": "Rev (TTM)", "value": fmt_usd(c["revenue"])},
            {"label": "Net Margin", "value": f"{c['netMargin']:.1f}%"},
            {"label": "EPS", "value": f"${c['eps']:.2f}"},
            {"label": "Div Yield", "value": f"{c['dividendYield']:.2f}%"},
            {"label": "Beta", "value": f"{c['beta']:.2f}"},
        ]
        companies.append({"symbol": s, "name": c["name"], "values": values})
    title = "Peer Comparison: " + " vs ".join(symbols)
    return {"title": title, "metricLabels": metric_labels, "companies": companies}


# ----------------------------- registry -----------------------------
class SkillDef:
    def __init__(self, id, name, panel_type, description, subskills, builder, default_title):
        self.id = id
        self.name = name
        self.panel_type = panel_type
        self.description = description
        self.subskills = subskills
        self.builder = builder
        self.default_title = default_title


SKILLS: Dict[str, SkillDef] = {}


def _reg(skill: SkillDef):
    SKILLS[skill.panel_type] = skill


_reg(SkillDef(
    "price-chart", "Live Price Charts", "price_chart",
    "Renders an OHLCV price history for a single ticker over a chosen window, "
    "with last price and net change. Use when the user wants to see how a stock has moved.",
    [
        {"name": "resolve_symbol", "description": "Map a company name or ticker to a known symbol.", "expectedOutput": "A valid ticker in the dataset."},
        {"name": "fetch_ohlcv", "description": "Produce the open/high/low/close/volume series for the window.", "expectedOutput": "An ordered list of daily OHLCV points."},
        {"name": "compute_change", "description": "Compute net and percent change over the window.", "expectedOutput": "Last price plus absolute and percent change."},
    ],
    build_price_chart, "Price Chart",
))
_reg(SkillDef(
    "news", "Company & Sector News", "news",
    "Surfaces recent curated headlines for a ticker or sector, each tagged with a "
    "source and sentiment. Use when the user asks what's happening or for the latest news.",
    [
        {"name": "resolve_scope", "description": "Decide whether the request targets a symbol or a sector.", "expectedOutput": "A scope type and scope value."},
        {"name": "rank_headlines", "description": "Order curated headlines by recency and relevance.", "expectedOutput": "A list of news items with sentiment tags."},
    ],
    build_news, "News",
))
_reg(SkillDef(
    "analysis", "AI Analysis & Summaries", "analysis",
    "Generates a concise analytic read (headline, summary, key points, stance, confidence) "
    "for a ticker or sector grounded in the curated data. Use when the user wants a take, "
    "opinion, or summary.",
    [
        {"name": "gather_context", "description": "Assemble price, fundamentals and headlines for the scope.", "expectedOutput": "A compact context object."},
        {"name": "synthesize", "description": "Use the language model to write a grounded analysis as strict JSON.", "expectedOutput": "Headline, summary, bullets, stance, confidence."},
        {"name": "validate_stance", "description": "Normalize stance and confidence to allowed values.", "expectedOutput": "A clean analysis payload."},
    ],
    build_analysis, "AI Analysis",
))
_reg(SkillDef(
    "fundamentals", "Fundamentals", "fundamentals",
    "Lists the key financial metrics for a single company (market cap, P/E, revenue, "
    "margins, EPS, yield, beta, 52-week range). Use when the user asks about valuation or financials.",
    [
        {"name": "resolve_symbol", "description": "Map the request to a known ticker.", "expectedOutput": "A valid ticker."},
        {"name": "assemble_metrics", "description": "Format the company's metrics for display.", "expectedOutput": "A labeled list of metric values."},
    ],
    build_fundamentals, "Fundamentals",
))
_reg(SkillDef(
    "screener", "Stock Screener / Watchlist", "screener",
    "Returns a sortable table of tickers (price, change, market cap, P/E, volume) for a "
    "sector or the whole universe. Use when the user wants to scan or compare many names at once.",
    [
        {"name": "select_universe", "description": "Choose the sector or full universe to scan.", "expectedOutput": "A set of tickers."},
        {"name": "build_rows", "description": "Assemble one row per ticker with key columns.", "expectedOutput": "A ranked table of rows."},
    ],
    build_screener, "Screener",
))
_reg(SkillDef(
    "heatmap", "Sector Heatmap / Market Overview", "heatmap",
    "Returns cells sized by market cap and shaded by daily change for a sector or the whole "
    "market. Use when the user wants a bird's-eye view of what's moving.",
    [
        {"name": "select_scope", "description": "Choose a sector or the full market.", "expectedOutput": "A set of tickers."},
        {"name": "build_cells", "description": "Produce cells with size and change inputs.", "expectedOutput": "A list of heatmap cells."},
    ],
    build_heatmap, "Heatmap",
))
_reg(SkillDef(
    "sentiment", "Sentiment / Social Buzz", "sentiment",
    "Aggregates a curated sentiment read for a ticker or sector across social and news "
    "channels, with an overall score and a short trend. Use when the user asks about mood, "
    "buzz, or sentiment.",
    [
        {"name": "score_sources", "description": "Derive per-channel sentiment scores and volume.", "expectedOutput": "A list of channel sources."},
        {"name": "compose_trend", "description": "Build a short sentiment time series ending at the current read.", "expectedOutput": "A 14-point trend and overall label."},
    ],
    build_sentiment, "Sentiment",
))
_reg(SkillDef(
    "comparison", "Peer Comparison Tables", "comparison",
    "Builds a side-by-side metric table comparing two or more companies across valuation and "
    "profitability metrics. Use when the user wants to compare names head-to-head.",
    [
        {"name": "resolve_symbols", "description": "Map the requested names to valid tickers.", "expectedOutput": "A list of at least two tickers."},
        {"name": "align_metrics", "description": "Compute the same metric set for each company.", "expectedOutput": "Aligned metric rows per company."},
    ],
    build_comparison, "Comparison",
))


def skill_catalog() -> dict:
    return {
        "skills": [
            {
                "id": s.id,
                "name": s.name,
                "panelType": s.panel_type,
                "description": s.description,
                "subskills": s.subskills,
            }
            for s in SKILLS.values()
        ]
    }
