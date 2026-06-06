"""Skill registry. Each panel type is a skill with a descriptive setup and
subskills, plus a builder that turns resolved params into panel `data`.
"""
from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

from . import ai, cache, data, db, engine, factor_model, quality, repo
from .sources import prices as p_src

log = logging.getLogger(__name__)

RANGE_DAYS = {"1M": 30, "3M": 90, "6M": 180, "1Y": 250, "YTD": 120}

# Common acronyms that should stay upper-cased in free-text topic labels so a
# query like "ai chip shortage" reads as "AI Chip Shortage" rather than the
# default title-case "Ai Chip Shortage". Display-only — never affects matching.
TOPIC_ACRONYMS = {
    "AI", "ML", "EV", "IPO", "GDP", "CPI", "PPI", "PMI", "ETF", "ESG",
    "IoT", "AR", "VR", "GPU", "CPU", "SaaS", "EPS", "FOMC", "ECB", "BOJ",
    "OPEC", "SEC", "FDA", "M&A", "5G", "6G", "API", "EU", "UK", "US",
    "USA", "PCE", "QE", "LLM", "VC", "PE", "REIT", "FX", "NFT",
}
_ACRONYM_LOOKUP = {a.lower(): a for a in TOPIC_ACRONYMS}


def topic_label(scope: Optional[str]) -> str:
    """Title-case a free-text topic, but keep common acronyms upper-cased."""
    if not scope or not scope.strip():
        return "Markets"
    words = []
    for word in scope.strip().split():
        words.append(_ACRONYM_LOOKUP.get(word.lower(), word.title()))
    return " ".join(words)


def _live_source() -> str:
    return "live" if db.db_available() else "mock"


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


# ----------------------------- Black-Scholes helpers -------------------------
def _erf(x: float) -> float:
    """Abramowitz & Stegun approximation of erf."""
    sign = 1 if x >= 0 else -1
    x = abs(x)
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return sign * y


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + _erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    """Black-Scholes option price."""
    if T <= 0 or sigma <= 0:
        intrinsic = max(S - K, 0) if option_type == "call" else max(K - S, 0)
        return intrinsic
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == "call":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def _bs_greeks(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> dict:
    """Return delta, gamma, theta, vega for a single option."""
    if T <= 0 or sigma <= 0:
        delta = (1.0 if S > K else 0.0) if option_type == "call" else (-1.0 if S < K else 0.0)
        return {"delta": delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    pdf_d1 = _norm_pdf(d1)
    delta = _norm_cdf(d1) if option_type == "call" else _norm_cdf(d1) - 1.0
    gamma = pdf_d1 / (S * sigma * math.sqrt(T))
    vega = S * pdf_d1 * math.sqrt(T) / 100.0  # per 1 vol point
    if option_type == "call":
        theta = (-S * pdf_d1 * sigma / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * _norm_cdf(d2)) / 365
    else:
        theta = (-S * pdf_d1 * sigma / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * _norm_cdf(-d2)) / 365
    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 5),
        "theta": round(theta, 4),
        "vega": round(vega, 4),
    }


def _iv_smile(moneyness: float, T_years: float, base_iv: float) -> float:
    """Generate a realistic IV smile: higher wings, mild skew (put skew typical)."""
    skew = -0.15 * moneyness            # negative skew: OTM puts costlier
    smile = 0.35 * moneyness ** 2       # symmetric convexity
    term = 0.04 * math.log(max(T_years, 1/365) * 12 + 1)  # slight upward slope with time
    return max(0.05, base_iv + skew + smile + term)


# ----------------------------- builders -----------------------------
def build_price_chart(params: dict) -> dict:
    symbol = (params.get("symbol") or "NVDA").upper()
    repo.note_symbol(symbol)  # request live data on demand for this symbol
    company = repo.get_company(symbol)
    if not company:
        raise ValueError(f"Unknown symbol: {symbol}")
    rng = (params.get("range") or "3M").upper()
    if rng not in RANGE_DAYS:
        rng = "3M"
    # Pass the selected window straight to the data layer so it slices the stored
    # OHLCV to the requested range (range round-trips: chart picker → skill → repo).
    points = repo.price_series(symbol, rng=rng)
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
        "ranges": list(RANGE_DAYS.keys()),
        "points": points,
        "asOf": company.get("_asOf"),
        "source": company.get("_source"),
    }


NEWS_PANEL_LIMIT = 40


def build_news(params: dict) -> dict:
    topic = params.get("topic") or params.get("query")
    if params.get("scope_type"):
        scope_type = params["scope_type"]
    elif params.get("symbol"):
        scope_type = "symbol"
    elif topic:
        scope_type = "topic"
    else:
        scope_type = "sector"
    scope = (params.get("scope") or params.get("symbol") or params.get("sector")
             or topic or "ai_tech")
    # Pull fresh headlines for the user's actual topic/symbol at query time so the
    # panel reflects what's happening now. Best-effort and bounded — falls back to
    # whatever is already stored (or curated mock) if a source is slow or down.
    repo.refresh_news_live(scope_type, scope)
    items = repo.news_for(scope_type, scope, limit=NEWS_PANEL_LIMIT)
    if scope_type == "symbol":
        company = repo.get_company(scope.upper())
        label = company["name"] if company else scope.upper()
    elif scope_type == "topic":
        label = topic_label(scope)
    else:
        sid = repo.resolve_sector(scope) or scope
        label = repo.sector_name(sid)
    as_of = max((i["publishedAt"] for i in items if i.get("publishedAt")), default=None)
    return {"scope": label, "items": items, "asOf": as_of, "source": _live_source()}


def _fallback_analysis(scope_type: str, scope: str) -> dict:
    if scope_type == "symbol":
        company = repo.get_company(scope.upper())
        name = company["name"] if company else scope.upper()
        chg = company["changePct"] if company else 0.0
        news = repo.news_for("symbol", scope)
    else:
        sid = repo.resolve_sector(scope) or scope
        name = repo.sector_name(sid)
        syms = repo.symbols_in_sector(sid)
        chg = round(sum(repo.get_company(s)["changePct"] for s in syms) / max(len(syms), 1), 2) if syms else 0.0
        news = repo.news_for("sector", scope)
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
        f"This is a rules-based read over the latest available data."
    )
    return {
        "scope": name,
        "headline": f"{name}: {stance.capitalize()} on current flow",
        "summary": summary,
        "bullets": bullets,
        "stance": stance,
        "confidence": conf,
        "source": _live_source(),
    }


def build_analysis(params: dict) -> dict:
    scope_type = params.get("scope_type") or ("symbol" if params.get("symbol") else "sector")
    scope = params.get("scope") or params.get("symbol") or params.get("sector") or "ai_tech"
    if not ai.ai_available():
        return _fallback_analysis(scope_type, scope)

    # Build grounding context from the latest available data.
    as_of = None
    if scope_type == "symbol":
        company = repo.get_company(scope.upper())
        if not company:
            return _fallback_analysis(scope_type, scope)
        name = company["name"]
        as_of = company.get("_asOf")
        ctx = {
            "name": name,
            "symbol": company["symbol"],
            "sector": repo.sector_name(company["sector"]),
            "price": company["price"],
            "dayChangePct": company["changePct"],
            "peRatio": company["peRatio"],
            "revenueUSD": company["revenue"],
            "netMarginPct": company["netMargin"],
            "description": company["description"],
        }
        news = repo.news_for("symbol", scope)
    else:
        sid = repo.resolve_sector(scope) or scope
        name = repo.sector_name(sid)
        syms = repo.symbols_in_sector(sid)
        companies = [repo.get_company(s) for s in syms]
        as_of = repo.as_of(*[c for c in companies if c])
        ctx = {
            "sector": name,
            "constituents": [
                {"symbol": c["symbol"], "changePct": c["changePct"]} for c in companies if c
            ],
        }
        news = repo.news_for("sector", scope)
    ctx["recentHeadlines"] = [{"headline": n["headline"], "sentiment": n["sentiment"]} for n in news[:6]]

    prompt = (
        "You are an equity analyst writing for a market terminal. Using ONLY the "
        "data provided, write a concise analytic read. Respond with a "
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
    parsed["stance"] = parsed.get("stance", "neutral")
    if parsed["stance"] not in ("bullish", "neutral", "bearish"):
        parsed["stance"] = "neutral"
    try:
        parsed["confidence"] = max(0.0, min(1.0, float(parsed.get("confidence", 0.6))))
    except (TypeError, ValueError):
        parsed["confidence"] = 0.6
    parsed["asOf"] = as_of
    parsed["source"] = _live_source()
    return parsed


def build_fundamentals(params: dict) -> dict:
    symbol = (params.get("symbol") or "NVDA").upper()
    repo.note_symbol(symbol)  # request live data on demand for this symbol
    company = repo.get_company(symbol)
    if not company:
        raise ValueError(f"Unknown symbol: {symbol}")
    rets = repo.period_returns(symbol, windows=("1M", "YTD", "1Y"))["returns"]

    def _ret(window: str):
        v = rets.get(window)
        return (f"{v:+.2f}%" if v is not None else "—"), v

    r1m_v, r1m = _ret("1M")
    rytd_v, rytd = _ret("YTD")
    r1y_v, r1y = _ret("1Y")

    metrics = [
        {"label": "Last Price", "value": f"${company['price']:.2f}", "change": company["changePct"], "hint": "1D change %"},
        {"label": "Return (1M)", "value": r1m_v, "change": r1m, "hint": "Price return, 1 month"},
        {"label": "Return (YTD)", "value": rytd_v, "change": rytd, "hint": "Price return, year-to-date"},
        {"label": "Return (1Y)", "value": r1y_v, "change": r1y, "hint": "Price return, 1 year"},
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
    if company.get("exchange"):
        hint = company.get("country")
        metrics.append({"label": "Exchange", "value": company["exchange"],
                        "change": None, "hint": hint})
    return {
        "symbol": symbol,
        "name": company["name"],
        "metrics": metrics,
        "country": company.get("country"),
        "exchange": company.get("exchange"),
        "asOf": company.get("_asOf"),
        "source": company.get("_source"),
    }


def _market_filter(params: dict):
    """Extract a (sector_id, country, exchange) filter from panel params.

    Accepts an explicit sector plus optional country/exchange filters, all
    normalized through the repo resolvers so "SG"/"Singapore"/"sgx" etc. work.
    A free-text sector/scope that isn't a real sector is retried as a market
    (so "Singapore" passed as scope still filters by country)."""
    sector = params.get("sector") or params.get("scope")
    sid = repo.resolve_sector(sector) if sector else None
    country = repo.resolve_country(params.get("country"))
    exchange = repo.resolve_exchange(params.get("exchange"))
    if sector and not sid and not country and not exchange:
        m = repo.resolve_market(sector)
        if m:
            country, exchange = m["country"], m["exchange"]
    return sid, country, exchange


def _market_title(sid, country, exchange, kind: str, default: str) -> str:
    """Compose a panel title from the active sector/market filter."""
    label = repo.market_label(country, exchange)
    parts = []
    if label:
        parts.append(label)
    if sid:
        parts.append(repo.sector_name(sid))
    return f"{' '.join(parts)} {kind}" if parts else default


def build_screener(params: dict) -> dict:
    sid, country, exchange = _market_filter(params)
    syms = repo.symbols_by_market(sid, country, exchange)
    title = _market_title(sid, country, exchange, "Screener", "Market Screener")
    bulk = repo.companies_bulk(syms)
    rets = repo.period_returns_bulk(syms, windows=("YTD",))
    rows = []
    companies = []
    for s in syms:
        c = bulk.get(s)
        if not c:
            continue
        companies.append(c)
        rows.append({
            "symbol": s,
            "name": c["name"],
            "price": c["price"],
            "changePct": c["changePct"],  # 1-day move
            "retYTD": (rets.get(s) or {}).get("YTD"),  # true year-to-date return
            "marketCap": c["marketCap"],
            "peRatio": c["peRatio"],
            "volume": c["volume"],
            "sector": repo.sector_name(c["sector"]),
            "country": c.get("country"),
            "exchange": c.get("exchange"),
        })
    rows.sort(key=lambda r: r["marketCap"], reverse=True)
    return {"title": title, "rows": rows, "asOf": repo.as_of(*companies), "source": repo.source_of(*companies)}


def build_heatmap(params: dict) -> dict:
    sid, country, exchange = _market_filter(params)
    syms = repo.symbols_by_market(sid, country, exchange)
    title = _market_title(sid, country, exchange, "Heatmap", "Market Overview")
    bulk = repo.companies_bulk(syms)
    rets = repo.period_returns_bulk(syms, windows=("YTD",))
    cells = []
    companies = []
    for s in syms:
        c = bulk.get(s)
        if not c:
            continue
        companies.append(c)
        cells.append({
            "symbol": s,
            "name": c["name"],
            "changePct": c["changePct"],  # 1-day move
            "retYTD": (rets.get(s) or {}).get("YTD"),  # true year-to-date return
            "marketCap": c["marketCap"],
            "sector": repo.sector_name(c["sector"]),
            "country": c.get("country"),
            "exchange": c.get("exchange"),
        })
    cells.sort(key=lambda x: x["marketCap"], reverse=True)
    return {"title": title, "cells": cells, "asOf": repo.as_of(*companies), "source": repo.source_of(*companies)}


def build_sentiment(params: dict) -> dict:
    scope_type = params.get("scope_type") or ("symbol" if params.get("symbol") else "sector")
    scope = params.get("scope") or params.get("symbol") or params.get("sector") or "ai_tech"
    if scope_type == "symbol":
        company = repo.get_company(scope.upper())
        name = company["name"] if company else scope.upper()
    else:
        sid = repo.resolve_sector(scope) or scope
        name = repo.sector_name(sid)

    # Prefer the worker-computed, persisted sentiment snapshot when available.
    stored = repo.get_sentiment(scope_type, scope)
    if stored:
        return {
            "scope": name,
            "overall": stored["overall"],
            "label": stored["label"],
            "sources": stored["sources"],
            "trend": stored["trend"],
            "asOf": stored.get("_asOf"),
            "source": "live",
        }

    if scope_type == "symbol":
        news = repo.news_for("symbol", scope)
        seed = data._seed(scope.upper())
    else:
        sid = repo.resolve_sector(scope) or scope
        news = repo.news_for("sector", scope)
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
    trend[-1]["score"] = overall
    return {"scope": name, "overall": overall, "label": label, "sources": sources,
            "trend": trend, "source": _live_source()}


def build_comparison(params: dict) -> dict:
    symbols = params.get("symbols") or []
    symbols = [s.upper() for s in symbols if repo.get_company(s.upper())]
    if len(symbols) < 2:
        symbols = ["NVDA", "AMD", "TSM"]
    metric_labels = ["Price", "Mkt Cap", "P/E", "Rev (TTM)", "Net Margin", "EPS", "Div Yield", "Beta"]
    companies = []
    records = []
    for s in symbols:
        c = repo.get_company(s)
        records.append(c)
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
    return {"title": title, "metricLabels": metric_labels, "companies": companies,
            "asOf": repo.as_of(*records), "source": repo.source_of(*records)}


def build_order_book(params: dict) -> dict:
    symbol = (params.get("symbol") or "NVDA").upper()
    company = data.get_company(symbol)
    if not company:
        raise ValueError(f"Unknown symbol: {symbol}")
    last = company["price"]
    seed = data._seed(symbol)

    def _rnd():
        nonlocal seed
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    tick = round(last * 0.0001, 2) or 0.01
    spread = round(tick * 2, 2)
    levels = 8

    bids = []
    for i in range(levels):
        price = round(last - spread / 2 - tick * i, 2)
        size = round(500 + _rnd() * 9500, 0)
        bids.append({"price": price, "size": size, "depth": 0.0})

    asks = []
    for i in range(levels):
        price = round(last + spread / 2 + tick * i, 2)
        size = round(500 + _rnd() * 9500, 0)
        asks.append({"price": price, "size": size, "depth": 0.0})

    max_bid = max(b["size"] for b in bids)
    max_ask = max(a["size"] for a in asks)
    for b in bids:
        b["depth"] = round(b["size"] / max_bid, 3)
    for a in asks:
        a["depth"] = round(a["size"] / max_ask, 3)

    venues = ["NYSE", "NASDAQ", "BATS", "EDGX", "IEX"]
    tape = []
    for i in range(20):
        side = "buy" if _rnd() > 0.45 else "sell"
        price = round(last + (_rnd() - 0.5) * spread * 4, 2)
        size = round(100 + _rnd() * 4900, 0)
        h = 9 + int(_rnd() * 6)
        m = int(_rnd() * 60)
        s = int(_rnd() * 60)
        venue = venues[int(_rnd() * len(venues))]
        tape.append({"time": f"{h:02d}:{m:02d}:{s:02d}", "price": price, "size": size, "side": side, "venue": venue})

    tape.sort(key=lambda t: t["time"], reverse=True)

    return {
        "symbol": symbol,
        "name": company["name"],
        "lastPrice": last,
        "spread": spread,
        "bids": bids,
        "asks": asks,
        "tape": tape,
    }


def build_portfolio_risk(params: dict) -> dict:
    import numpy as np

    symbols = [s.upper() for s in (params.get("symbols") or []) if repo.get_company(s.upper())]
    if not symbols:
        symbols = ["NVDA", "MSFT", "GOOGL", "META", "AMZN"]
    portfolio_name = params.get("portfolio_name") or (", ".join(symbols[:3]) + " Portfolio")

    # Pull real daily returns per holding and equal-weight them into a single
    # portfolio P&L series; VaR/CVaR come straight from that real distribution.
    return_cols: List[np.ndarray] = []
    sources: List[str] = []
    as_ofs: List[str] = []
    for s in symbols:
        meta = repo.price_series_meta(s, days=250)
        sources.append(meta.get("source", "mock"))
        if meta.get("asOf"):
            as_ofs.append(meta["asOf"])
        closes = np.asarray(
            [float(p["c"]) for p in meta["points"] if p.get("c")], dtype=float
        )
        if closes.size >= 3:
            return_cols.append(closes[1:] / closes[:-1] - 1.0)

    if return_cols:
        min_len = min(len(c) for c in return_cols)
        matrix = np.vstack([c[-min_len:] for c in return_cols])
        port_rets = matrix.mean(axis=0)  # equal-weighted daily returns
    else:
        port_rets = np.array([], dtype=float)

    var95 = engine.var_historical(port_rets, 0.95) if port_rets.size else 0.02
    cvar95 = engine.cvar_historical(port_rets, 0.95) if port_rets.size else 0.03
    ann_vol = (
        float(port_rets.std(ddof=0) * np.sqrt(252)) if port_rets.size >= 2 else 0.10
    )

    # P&L histogram from the real return distribution (20 bins, in %).
    if port_rets.size >= 5:
        counts, edges = np.histogram(port_rets * 100.0, bins=20)
        bins = [
            {"bin": round(float((edges[i] + edges[i + 1]) / 2.0), 2), "count": int(counts[i])}
            for i in range(len(counts))
        ]
    else:
        bins = [{"bin": round(-4.0 + i * 0.4, 2), "count": 1} for i in range(20)]

    # Factor exposures: the portfolio's REAL tilts from the multi-factor model
    # (weighted-average exposure to each factor). Market beta is the average beta
    # of the holdings. If the model can't be estimated we fall back to Market beta
    # alone rather than inventing style tilts.
    betas = {s: repo.get_company(s)["beta"] for s in symbols}
    avg_beta = round(sum(betas.values()) / len(betas), 2)
    try:
        _res = factor_model.build(symbols)
        _idx, _w, _ = factor_model.portfolio_indices(
            _res, symbols, [1.0 / len(symbols)] * len(symbols)
        )
        _pr = engine.decompose_portfolio(_res.model, _idx, _w)
        factor_exposures = [
            {"factor": fn, "exposure": round(float(_pr.factor_exposures[kk]), 2)}
            for kk, fn in enumerate(_res.model.factor_names)
        ]
        avg_beta = round(float(_pr.factor_exposures[0]), 2)
    except Exception:  # noqa: BLE001 — keep the VaR panel even if the model fails
        factor_exposures = [{"factor": "Market", "exposure": avg_beta}]

    summary = {
        "portfolioName": portfolio_name,
        "var95": round(var95 * 100, 2),
        "cvar95": round(cvar95 * 100, 2),
        "trackingError": round(ann_vol * 100, 2),
        "beta": avg_beta,
    }
    source = "live" if any(s == "live" for s in sources) else "mock"
    as_of = max(as_ofs) if as_ofs else None
    return {
        "portfolioName": portfolio_name,
        "symbols": symbols,
        "varHistogram": bins,
        "factorExposures": factor_exposures,
        "summary": summary,
        "asOf": as_of,
        "source": source,
    }


def build_trade_flow(params: dict) -> dict:
    symbol = (params.get("symbol") or "NVDA").upper()
    company = data.get_company(symbol)
    if not company:
        raise ValueError(f"Unknown symbol: {symbol}")
    last = company["price"]
    avg_vol = company["volume"]
    seed = data._seed(symbol + "flow")

    def _rnd():
        nonlocal seed
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    venues = ["NASDAQ", "NYSE", "DARK", "BATS", "IEX", "EDGX"]
    block_threshold = round(avg_vol * 0.002, 0)
    prints = []
    total_buy = 0.0
    total_sell = 0.0
    dark_vol = 0.0
    total_vol = 0.0

    for i in range(40):
        h = 9 + int(_rnd() * 6.5)
        if h < 9:
            h = 9
        m = int(_rnd() * 60)
        side = "buy" if _rnd() > 0.44 else "sell"
        price = round(last * (0.99 + _rnd() * 0.02), 2)
        base_size = avg_vol * 0.0005
        is_block = _rnd() > 0.82
        size = round(base_size * (5 + _rnd() * 15) if is_block else base_size * (0.5 + _rnd() * 2), 0)
        venue_idx = int(_rnd() * len(venues))
        venue = venues[venue_idx]
        is_dark = venue == "DARK" or _rnd() > 0.75

        prints.append({
            "time": f"{h:02d}:{m:02d}",
            "price": price,
            "size": size,
            "side": side,
            "venue": venue if not is_dark else "DARK",
            "isBlock": is_block,
            "isDark": is_dark,
        })

        if side == "buy":
            total_buy += size
        else:
            total_sell += size
        if is_dark:
            dark_vol += size
        total_vol += size

    prints.sort(key=lambda p: p["time"])
    dark_pct = round((dark_vol / total_vol) * 100, 1) if total_vol else 0.0
    buy_imbalance = round(total_buy / (total_buy + total_sell), 3) if (total_buy + total_sell) else 0.5

    return {
        "symbol": symbol,
        "name": company["name"],
        "darkPoolPct": dark_pct,
        "buyImbalance": buy_imbalance,
        "totalVolume": round(total_vol, 0),
        "blockThreshold": block_threshold,
        "prints": prints,
    }


def build_backtest(params: dict) -> dict:
    symbol = (params.get("symbol") or "NVDA").upper()
    company = repo.get_company(symbol)
    if not company:
        symbol = "NVDA"
        company = repo.get_company(symbol)
    strategy = engine.normalize_strategy(params.get("strategy") or "momentum")
    rng_key = (params.get("range") or "1Y").upper()
    days = RANGE_DAYS.get(rng_key, 250)

    # Pull real OHLCV history (falls back to the curated mock series when the DB
    # has insufficient history, so the panel always renders).
    meta = repo.price_series_meta(symbol, days=days)
    points = meta["points"]
    strat_params = {
        k: params[k]
        for k in ("fast", "slow", "lookback", "threshold")
        if params.get(k) is not None
    }

    try:
        result = engine.run_backtest(points, strategy, strat_params)
    except ValueError:
        # Last-resort fallback: synthesize a deterministic series so the panel
        # still has something to show when history is genuinely missing.
        points = data.price_series(symbol, days=max(days, 60))
        meta = {"points": points, "source": "mock", "asOf": None}
        result = engine.run_backtest(points, strategy, strat_params)

    return {
        "symbol": symbol,
        "strategy": result["strategy"],
        "curve": result["curve"],
        "drawdown": result["drawdown"],
        "tradeLog": result["tradeLog"][:50],
        "stats": result["stats"],
        "asOf": meta.get("asOf") or company.get("_asOf"),
        "source": meta.get("source", "mock"),
    }


def build_monte_carlo(params: dict) -> dict:
    import numpy as np

    symbol = (params.get("symbol") or "NVDA").upper()
    company = repo.get_company(symbol)
    if not company:
        symbol = "NVDA"
        company = repo.get_company(symbol)

    method = (params.get("method") or "bootstrap").lower()
    horizon = int(params.get("horizon") or 252)
    n_paths = int(params.get("paths") or 1000)

    # Real historical daily returns drive the simulation; fall back to the
    # curated mock series if the DB has too little history.
    meta = repo.price_series_meta(symbol, days=250)
    closes = np.asarray([float(p["c"]) for p in meta["points"] if p.get("c")], dtype=float)
    if closes.size < 6:
        points = data.price_series(symbol, days=180)
        closes = np.asarray([float(p["c"]) for p in points if p.get("c")], dtype=float)
        meta = {"source": "mock", "asOf": None}
    returns = closes[1:] / closes[:-1] - 1.0 if closes.size >= 2 else np.array([])

    last_price = float(closes[-1]) if closes.size else 100.0
    sim = engine.monte_carlo(
        returns,
        start_value=last_price,
        horizon=horizon,
        n_paths=n_paths,
        method=method,
    )

    return {
        "symbol": symbol,
        "method": sim["method"],
        "horizon": sim["horizon"],
        "startValue": sim["startValue"],
        "fan": sim["fan"],
        "samplePaths": sim["samplePaths"],
        "summary": sim["summary"],
        "asOf": meta.get("asOf") or company.get("_asOf"),
        "source": meta.get("source", "mock"),
    }


# ----------------------------- execution simulation & TCA -----------------------------
# A book NAV used to translate weight deltas into traded notional when the caller
# does not state one. The execution desk diffs current vs target weights into
# orders, simulates VWAP/TWAP/POV against REAL intraday volume, applies a
# transparent square-root impact model, and reports TCA per name + aggregate.
_TCA_DEFAULT_CAPITAL = 10_000_000.0
# When only a single symbol is given with no size, simulate a realistic
# institutional clip: this fraction of the name's average daily volume.
_TCA_DEFAULT_PARTICIPATION = 0.05
_TCA_DEFAULT_INTERVAL = "30m"
_TCA_DEFAULT_RANGE = "1d"
_TCA_MAX_ORDERS = 12
_TCA_VOL_DAYS = 90


def _tca_resolve_orders(params: dict) -> List[dict]:
    """Resolve the order list from one of three input shapes (explicit orders,
    a current-vs-target weight diff, or a single sized/defaulted symbol)."""
    capital = params.get("capital")
    try:
        capital = float(capital) if capital else _TCA_DEFAULT_CAPITAL
    except (TypeError, ValueError):
        capital = _TCA_DEFAULT_CAPITAL

    # 1) Explicit orders: [{symbol, side, shares|notional}]
    raw_orders = params.get("orders")
    if isinstance(raw_orders, list) and raw_orders:
        out: List[dict] = []
        for o in raw_orders:
            if not isinstance(o, dict):
                continue
            sym = (o.get("symbol") or o.get("ticker") or "").upper()
            c = repo.get_company(sym)
            if not c:
                continue
            px = c["price"]
            side = (o.get("side") or "buy").lower()
            shares = o.get("shares")
            notional = o.get("notional")
            if shares:
                shares = abs(float(shares))
                notional = shares * px
            elif notional:
                notional = abs(float(notional))
                shares = notional / px if px else 0.0
            else:
                shares = _TCA_DEFAULT_PARTICIPATION * (c.get("volume") or 0.0)
                notional = shares * px
            if shares < 1:
                continue
            out.append({"symbol": sym, "name": c["name"], "side": side,
                        "shares": shares, "notional": notional, "price": px})
        return out[:_TCA_MAX_ORDERS]

    # 2) Current-vs-target weight diff.
    syms = [s.upper() for s in (params.get("symbols") or []) if s]
    tgt = params.get("target_weights") or params.get("weights")
    if syms and isinstance(tgt, list) and len(tgt) == len(syms):
        cur = params.get("current_weights") or params.get("current")
        prices: Dict[str, float] = {}
        names: Dict[str, str] = {}
        for s in syms:
            c = repo.get_company(s)
            if c:
                prices[s] = c["price"]
                names[s] = c["name"]
        # Auto-normalize weights to fractions if they look like percentages.
        def _norm(ws):
            vals = [float(w) for w in ws]
            tot = sum(abs(v) for v in vals)
            if tot > 1.5:  # given as percents
                vals = [v / 100.0 for v in vals]
            return vals
        targets = dict(zip(syms, _norm(tgt)))
        currents = {}
        if isinstance(cur, list) and len(cur) == len(syms):
            currents = dict(zip(syms, _norm(cur)))
        gen = engine.generate_orders(targets, currents, prices, capital)
        for g in gen:
            g["name"] = names.get(g["symbol"], g["symbol"])
        return gen[:_TCA_MAX_ORDERS]

    # 3) Single symbol — default to a realistic clip sized off ADV.
    symbol = (params.get("symbol") or "NVDA").upper()
    c = repo.get_company(symbol)
    if not c:
        raise ValueError(f"Unknown symbol: {symbol}")
    px = c["price"]
    side = (params.get("side") or "buy").lower()
    shares = params.get("shares")
    notional = params.get("notional")
    participation = params.get("participation")
    if shares:
        shares = abs(float(shares))
        notional = shares * px
    elif notional:
        notional = abs(float(notional))
        shares = notional / px if px else 0.0
    else:
        part = float(participation) if participation else _TCA_DEFAULT_PARTICIPATION
        shares = part * (c.get("volume") or 0.0)
        notional = shares * px
    return [{"symbol": symbol, "name": c["name"], "side": side,
             "shares": shares, "notional": notional, "price": px}]


def _tca_simulate_order(order: dict, interval: str, rng: str,
                        pov_rate: float, chosen: str) -> dict:
    """Simulate one order against real intraday volume and compute TCA.

    Returns a per-order record. If real intraday data is unavailable for the
    name/window the order is marked ``supported: False`` with a reason rather
    than being simulated on fabricated volume.
    """
    sym = order["symbol"]
    base = {
        "symbol": sym, "name": order.get("name", sym), "side": order["side"],
        "shares": order["shares"], "notional": order["notional"],
        "price": order.get("price"),
    }
    for k in ("targetWeight", "currentWeight", "deltaWeight"):
        if k in order:
            base[k] = order[k]

    ysym = data.yahoo_symbol(sym)
    cache_key = f"intraday:{ysym}:{interval}:{rng}"
    try:
        res = cache.cached(cache_key, 60.0,
                           lambda: p_src.fetch_intraday(ysym, interval, rng))
        bars = res.get("points") or []
        sim = engine.simulate_all(bars, order["shares"], order["side"], pov_rate)
    except p_src.IntradayUnavailable as exc:
        return {**base, "supported": False,
                "reason": f"No real intraday volume: {exc}"}
    except ValueError as exc:
        return {**base, "supported": False,
                "reason": f"No real intraday volume: {exc}"}
    except Exception as exc:  # noqa: BLE001 - any upstream failure -> unsupported
        return {**base, "supported": False,
                "reason": f"Intraday fetch failed: {exc}"}

    # Real daily volatility (fraction) and ADV for the modeled impact.
    meta = repo.price_series_meta(sym, days=_TCA_VOL_DAYS)
    closes = [p.get("c") for p in meta.get("points", [])]
    daily_vol = engine.daily_vol_from_closes(closes)
    company = repo.get_company(sym) or {}
    adv = float(company.get("volume") or 0.0)
    impact_bps = engine.square_root_impact(order["shares"], adv, daily_vol)

    algos = sim["algos"]
    chosen_algo = chosen if chosen in algos else "vwap"
    ch = algos[chosen_algo]
    is_bps = ch["isBps"]
    vwap_slip = ch["vwapSlipBps"]
    all_in = is_bps + impact_bps

    return {
        **base,
        "supported": True,
        "arrivalPrice": sim["arrival"],
        "intervalVwap": sim["intervalVwap"],
        "chosenAlgo": chosen_algo,
        "algos": {
            k: {"avgFill": v["avgFill"], "fillRate": v["fillRate"],
                "isBps": v["isBps"], "vwapSlipBps": v["vwapSlipBps"]}
            for k, v in algos.items()
        },
        "schedule": ch["schedule"],
        "isBps": is_bps,
        "vwapSlipBps": vwap_slip,
        "impactBps": impact_bps,
        "allInBps": all_in,
        "costUsd": all_in / 1e4 * order["notional"],
        "fillRate": ch["fillRate"],
        "adv": adv,
        "dailyVol": daily_vol,
        "asOf": res.get("asOf"),
    }


def _tca_round(order: dict) -> dict:
    """Round numeric fields of a per-order record for display."""
    out = dict(order)
    for k in ("shares", "notional", "adv"):
        if isinstance(out.get(k), (int, float)):
            out[k] = round(float(out[k]), 0)
    for k in ("price", "arrivalPrice", "intervalVwap"):
        if isinstance(out.get(k), (int, float)):
            out[k] = round(float(out[k]), 2)
    for k in ("isBps", "vwapSlipBps", "impactBps", "allInBps", "costUsd"):
        if isinstance(out.get(k), (int, float)):
            out[k] = round(float(out[k]), 2)
    if isinstance(out.get("dailyVol"), (int, float)):
        out["dailyVol"] = round(float(out["dailyVol"]) * 100.0, 2)  # as %
    if isinstance(out.get("fillRate"), (int, float)):
        out["fillRate"] = round(float(out["fillRate"]), 4)
    if isinstance(out.get("algos"), dict):
        out["algos"] = {
            k: {"avgFill": round(v["avgFill"], 2),
                "fillRate": round(v["fillRate"], 4),
                "isBps": round(v["isBps"], 2),
                "vwapSlipBps": round(v["vwapSlipBps"], 2)}
            for k, v in out["algos"].items()
        }
    if isinstance(out.get("schedule"), list):
        out["schedule"] = [
            {"time": s["time"], "price": round(s["price"], 2),
             "marketVolume": round(s["marketVolume"], 0),
             "childShares": round(s["childShares"], 0),
             "participation": round(s["participation"], 4),
             "cumPct": round(s["cumPct"], 4)}
            for s in out["schedule"]
        ]
    return out


def build_tca_report(params: dict) -> dict:
    """Execution simulation + transaction-cost analysis.

    Generates orders (from explicit input, a current-vs-target weight diff, or a
    single defaulted symbol), simulates VWAP / TWAP / POV executions against the
    data layer's REAL intraday volume profile, applies a transparent square-root
    market-impact model, and reports implementation shortfall vs arrival, slippage
    vs the interval VWAP, and cost in bps per name + aggregate. Real benchmarks
    (arrival, interval VWAP, bucket prices) are clearly separated from the modeled
    impact estimate; orders without real intraday data are marked unsupported.
    """
    interval = (params.get("interval") or _TCA_DEFAULT_INTERVAL).lower()
    rng = (params.get("range") or _TCA_DEFAULT_RANGE).lower()
    chosen = (params.get("algo") or "vwap").lower()
    try:
        pov_rate = float(params.get("pov_rate") or engine.execution.DEFAULT_POV_RATE)
    except (TypeError, ValueError):
        pov_rate = engine.execution.DEFAULT_POV_RATE

    orders_in = _tca_resolve_orders(params)
    if not orders_in:
        raise ValueError("No tradable orders could be generated from the request")

    sim_orders = [_tca_simulate_order(o, interval, rng, pov_rate, chosen)
                  for o in orders_in]
    agg = engine.aggregate_tca(sim_orders)

    supported = [o for o in sim_orders if o.get("supported")]
    as_ofs = [o["asOf"] for o in supported if o.get("asOf")]
    if supported:
        source = "live" if len(supported) == len(sim_orders) else "mixed"
    else:
        source = "unavailable"

    # Title reflects the workflow scope.
    if len(sim_orders) == 1:
        o0 = sim_orders[0]
        title = f"Execution TCA — {o0['side'].upper()} {o0['symbol']}"
    else:
        title = f"Execution TCA — {len(sim_orders)} orders"

    rounded = [_tca_round(o) for o in sim_orders]
    agg_round = {
        "orderCount": agg["orderCount"],
        "supportedCount": agg["supportedCount"],
        "unsupportedCount": agg["unsupportedCount"],
        "grossNotional": round(agg["grossNotional"], 0),
        "buyNotional": round(agg["buyNotional"], 0),
        "sellNotional": round(agg["sellNotional"], 0),
        "isBps": round(agg["isBps"], 2),
        "vwapSlipBps": round(agg["vwapSlipBps"], 2),
        "impactBps": round(agg["impactBps"], 2),
        "allInBps": round(agg["allInBps"], 2),
        "totalCostUsd": round(agg["totalCostUsd"], 0),
    }

    return {
        "title": title,
        "interval": interval,
        "intervalLabel": _INTERVAL_LABELS.get(interval, interval),
        "range": rng,
        "rangeLabel": _RANGE_LABELS.get(rng, rng),
        "chosenAlgo": chosen if chosen in engine.execution.ALGOS else "vwap",
        "povRate": round(pov_rate, 3),
        "benchmarkNote": (
            "Arrival price, interval VWAP and bucket prices are realized from real "
            "intraday bars. Market impact is a square-root model estimate, shown "
            "separately from the real-data benchmarks."
        ),
        "model": {
            "name": "Square-root market impact (Almgren-style)",
            "formula": "cost(bps) = Y · σ_daily · √(Q / ADV) · 1e4",
            "coef": engine.execution.DEFAULT_IMPACT_COEF,
            "assumptions": [
                f"σ_daily from real daily returns ({_TCA_VOL_DAYS}d)",
                "ADV ≈ latest real daily volume",
                f"Y = {engine.execution.DEFAULT_IMPACT_COEF}",
            ],
        },
        "orders": rounded,
        "aggregate": agg_round,
        "asOf": max(as_ofs) if as_ofs else None,
        "source": source,
    }


def build_macro_dashboard(params: dict) -> dict:
    theme_raw = params.get("theme") or "global"
    theme_key = data.resolve_macro_theme(theme_raw)
    theme_def = data.MACRO_THEMES[theme_key]
    groups = []
    for label, symbols in theme_def["groups"].items():
        tiles = []
        for sym in symbols:
            asset = data.MACRO_ASSETS.get(sym)
            if not asset:
                continue
            tiles.append({
                "symbol": sym,
                "name": asset["name"],
                "price": float(asset["price"]),
                "changePct": float(asset["changePct"]),
                "unit": asset["unit"],
                "sparkline": data.macro_sparkline(sym),
            })
        if tiles:
            groups.append({"label": label, "tiles": tiles})
    return {
        "theme": theme_key,
        "title": theme_def["title"],
        "groups": groups,
    }


# ----------------------------- fixed income builders -----------------------------

_TENORS = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
_TENOR_YEARS = [1/12, 3/12, 6/12, 1, 2, 3, 5, 7, 10, 20, 30]

# Base US Treasury spot curve (mock, plausible as of mid-2025)
_BASE_SPOT = [5.32, 5.28, 5.18, 4.95, 4.62, 4.48, 4.38, 4.42, 4.52, 4.71, 4.68]
# 1Y ago (higher rates environment)
_AGO1Y_SPOT = [5.55, 5.52, 5.45, 5.25, 4.90, 4.75, 4.60, 4.65, 4.72, 4.88, 4.84]
# 2Y ago (early hiking cycle)
_AGO2Y_SPOT = [3.10, 3.55, 4.02, 4.30, 4.15, 3.98, 3.82, 3.85, 3.80, 3.90, 3.88]


def build_yield_curve(params: dict) -> dict:
    region = (params.get("region") or "US").upper()
    title = f"{region} Treasury Yield Curve"

    # Apply small per-region shifts for variety
    shift = {"US": 0.0, "UK": 0.15, "DE": -1.45, "JP": -3.80}.get(region, 0.0)

    points = []
    for i, tenor in enumerate(_TENORS):
        points.append({
            "tenor": tenor,
            "spot": round(_BASE_SPOT[i] + shift, 3),
            "ago1y": round(_AGO1Y_SPOT[i] + shift, 3),
            "ago2y": round(_AGO2Y_SPOT[i] + shift, 3),
        })

    # Key spreads
    spot_2y = _BASE_SPOT[4] + shift
    spot_10y = _BASE_SPOT[8] + shift
    spot_30y = _BASE_SPOT[10] + shift
    spot_3m = _BASE_SPOT[1] + shift

    spreads = [
        {"label": "2Y–10Y", "value": round(spot_10y - spot_2y, 2), "inverted": spot_10y < spot_2y},
        {"label": "2Y–30Y", "value": round(spot_30y - spot_2y, 2), "inverted": spot_30y < spot_2y},
        {"label": "3M–10Y", "value": round(spot_10y - spot_3m, 2), "inverted": spot_10y < spot_3m},
    ]

    inverted = any(s["inverted"] for s in spreads[:2])
    return {"title": title, "points": points, "spreads": spreads, "inverted": inverted}


# Bond peer universe for relative-value comparison
_BOND_PEERS = [
    # issuer, ticker, coupon, mat_year, yield, duration, z_spread, oas, asw, rating
    ("Apple Inc", "AAPL", 3.85, 2031, 4.72, 5.4, 72, 68, 65, "Aaa/AAA"),
    ("Apple Inc", "AAPL", 4.65, 2034, 4.89, 7.8, 88, 84, 82, "Aaa/AAA"),
    ("Microsoft Corp", "MSFT", 3.30, 2030, 4.65, 4.9, 63, 60, 58, "Aaa/AAA"),
    ("Microsoft Corp", "MSFT", 4.20, 2035, 4.82, 8.2, 80, 76, 74, "Aaa/AAA"),
    ("Amazon.com", "AMZN", 3.10, 2029, 4.70, 4.3, 68, 64, 62, "A1/AA"),
    ("Amazon.com", "AMZN", 4.10, 2034, 4.95, 7.5, 93, 88, 86, "A1/AA"),
    ("Alphabet Inc", "GOOGL", 2.25, 2030, 4.68, 5.0, 66, 62, 60, "Aa2/AA+"),
    ("Alphabet Inc", "GOOGL", 3.95, 2033, 4.85, 7.1, 83, 79, 77, "Aa2/AA+"),
    ("Meta Platforms", "META", 5.60, 2030, 5.05, 4.5, 103, 98, 96, "A3/A-"),
    ("Meta Platforms", "META", 5.75, 2033, 5.18, 6.8, 116, 110, 108, "A3/A-"),
    ("NVIDIA Corp", "NVDA", 3.50, 2040, 5.20, 11.2, 118, 112, 110, "A1/A+"),
    ("Intel Corp", "INTC", 5.20, 2033, 5.65, 6.5, 163, 155, 153, "Baa1/BBB+"),
    ("Ford Motor", "F", 6.10, 2032, 6.45, 5.8, 293, 285, 282, "Ba2/BB+"),
    ("Exxon Mobil", "XOM", 2.99, 2030, 4.74, 5.1, 72, 68, 66, "Aa2/AA-"),
    ("Chevron Corp", "CVX", 3.08, 2032, 4.88, 6.2, 86, 82, 80, "Aa2/AA"),
]


def build_bond_rv(params: dict) -> dict:
    ticker = (params.get("ticker") or params.get("symbol") or "AAPL").upper()
    title = f"Bond Relative Value — {ticker} vs Peers"

    # Filter to show the requested issuer + close peers by rating
    focus_rows = [r for r in _BOND_PEERS if r[1] == ticker]
    if not focus_rows:
        focus_rows = _BOND_PEERS[:2]
        ticker = focus_rows[0][1]
        title = f"Bond Relative Value — {ticker} vs Peers"

    focus_rating = focus_rows[0][9]
    peer_rows = [r for r in _BOND_PEERS if r[1] != ticker and r[9][0] == focus_rating[0]][:6]
    all_rows = focus_rows + peer_rows

    rows = []
    for r in all_rows:
        rows.append({
            "issuer": r[0],
            "ticker": r[1],
            "coupon": r[2],
            "maturityYear": r[3],
            "yieldPct": r[4],
            "duration": r[5],
            "zSpread": r[6],
            "oas": r[7],
            "aswSpread": r[8],
            "rating": r[9],
        })

    return {"title": title, "rows": rows, "highlight": ticker}


# CDS entity universe
_CDS_ENTITIES = {
    "F": ("Ford Motor Co", "F", "Ba2/BB+", 0.40, 285.0),
    "INTC": ("Intel Corp", "INTC", "Baa1/BBB+", 0.40, 95.0),
    "AMZN": ("Amazon.com", "AMZN", "A1/AA", 0.40, 38.0),
    "AAPL": ("Apple Inc", "AAPL", "Aaa/AAA", 0.40, 28.0),
    "MSFT": ("Microsoft Corp", "MSFT", "Aaa/AAA", 0.40, 25.0),
    "META": ("Meta Platforms", "META", "A3/A-", 0.40, 58.0),
    "XOM": ("Exxon Mobil", "XOM", "Aa2/AA-", 0.40, 45.0),
    "OXY": ("Occidental Petroleum", "OXY", "Ba1/BB+", 0.40, 175.0),
    "NVDA": ("NVIDIA Corp", "NVDA", "A1/A+", 0.40, 42.0),
    "GOOGL": ("Alphabet Inc", "GOOGL", "Aa2/AA+", 0.40, 30.0),
}

_CDS_TENORS = [("1Y", 1), ("2Y", 2), ("3Y", 3), ("5Y", 5), ("7Y", 7), ("10Y", 10)]


def _cds_survival(spread_bps: float, recovery: float, t: float) -> float:
    """Simple flat-hazard survival probability."""
    lg = spread_bps / 10000.0 / (1.0 - recovery)
    return round(math.exp(-lg * t), 6)


def build_cds_pricer(params: dict) -> dict:
    ticker = (params.get("ticker") or params.get("symbol") or "F").upper()
    entity_data = _CDS_ENTITIES.get(ticker, _CDS_ENTITIES["F"])
    name, ticker, rating, recovery, spread = entity_data

    # Allow tenor override
    req_tenor = (params.get("tenor") or "5Y").upper()

    survival_curve = []
    for label, years in _CDS_TENORS:
        sp = _cds_survival(spread, recovery, years)
        dp = round(1.0 - sp, 6)
        hz = round(spread / 10000.0 / (1.0 - recovery), 6)
        survival_curve.append({
            "tenor": label,
            "years": float(years),
            "survivalProb": sp,
            "hazardRate": hz,
            "defaultProb": dp,
        })

    sp1 = _cds_survival(spread, recovery, 1)
    sp5 = _cds_survival(spread, recovery, 5)
    implied_pd1y = round(1.0 - sp1, 4)
    implied_pd5y = round(1.0 - sp5, 4)

    # Upfront fee approximation (rough risky annuity * (spread - standard 100bps))
    standard_spread = 100.0
    risky_annuity = sum(
        _cds_survival(spread, recovery, t) * t / max(t, 1) for _, t in _CDS_TENORS[:4]
    ) / 4.0
    upfront = round((spread - standard_spread) / 10000.0 * risky_annuity * 100, 4)

    return {
        "entity": name,
        "ticker": ticker,
        "rating": rating,
        "recoveryRate": recovery,
        "runningSpread": spread,
        "upfrontFee": upfront,
        "survivalCurve": survival_curve,
        "impliedPd1y": implied_pd1y,
        "impliedPd5y": implied_pd5y,
    }


# Bond universe for cash-flow analysis
_CF_BONDS = {
    "UST10Y": ("US 10Y Treasury", 4.25, "2034-05-15", 100.0, 4.52),
    "UST30Y": ("US 30Y Treasury", 4.375, "2054-05-15", 100.0, 4.68),
    "UST5Y": ("US 5Y Treasury", 4.50, "2029-05-15", 100.0, 4.38),
    "UST2Y": ("US 2Y Treasury", 5.00, "2026-05-15", 100.0, 4.62),
    "AAPL30": ("Apple 3.85% 2031", 3.85, "2031-08-05", 100.0, 4.72),
    "MSFT10": ("Microsoft 4.20% 2035", 4.20, "2035-11-03", 100.0, 4.82),
    "F7Y": ("Ford 6.10% 2032", 6.10, "2032-08-19", 100.0, 6.45),
}

_SCENARIO_SHIFTS = [-200, -100, -50, 0, 50, 100, 200]


def _bond_price(coupon_rate: float, ytm: float, years: float, freq: int = 2) -> float:
    """Price a bond given coupon, ytm, and years to maturity."""
    n = int(round(years * freq))
    c = coupon_rate / 100.0 / freq
    y = ytm / 100.0 / freq
    if n == 0:
        return 100.0
    pv_coupons = c * (1 - (1 + y) ** (-n)) / y if y != 0 else c * n
    pv_principal = 1.0 / (1 + y) ** n
    return round((pv_coupons + pv_principal) * 100.0, 4)


def build_cashflow_duration(params: dict) -> dict:
    bond_key = (params.get("bond") or params.get("symbol") or "UST10Y").upper()
    bond_data = _CF_BONDS.get(bond_key, _CF_BONDS["UST10Y"])
    issuer, coupon, maturity_str, face, ytm = bond_data

    mat = date.fromisoformat(maturity_str)
    today = date.today()
    years_to_mat = max((mat - today).days / 365.25, 0.5)

    freq = 2
    n_periods = int(round(years_to_mat * freq))
    c = coupon / 100.0 / freq
    y = ytm / 100.0 / freq

    # Build cash-flow schedule
    payments = []
    price_dirty = _bond_price(coupon, ytm, years_to_mat, freq)
    total_pv = 0.0
    weighted_time = 0.0

    for i in range(1, n_periods + 1):
        t_years = i / freq
        cf_date = today + timedelta(days=int(t_years * 365.25))
        cf_coupon = round(face * c, 4)
        cf_principal = face if i == n_periods else 0.0
        cf_total = round(cf_coupon + cf_principal, 4)
        discount = (1 + y) ** i
        cf_pv = round(cf_total / discount, 4)
        total_pv += cf_pv
        weighted_time += cf_pv * t_years
        payments.append({
            "date": cf_date.isoformat(),
            "coupon": cf_coupon,
            "principal": cf_principal,
            "total": cf_total,
            "pv": cf_pv,
        })

    # Duration metrics
    macaulay = weighted_time / total_pv if total_pv else 0.0
    mod_duration = round(macaulay / (1 + y), 4)
    eff_duration = round(mod_duration, 4)

    # Convexity
    conv = 0.0
    for i, pmt in enumerate(payments, 1):
        t_years = i / freq
        discount = (1 + y) ** i
        conv += pmt["total"] / discount * t_years * (t_years + 1 / freq)
    convexity = round(conv / total_pv / (1 + y) ** 2 if total_pv else 0.0, 4)

    dv01 = round(mod_duration * price_dirty / 10000.0, 6)

    # Scenario table
    scenarios = []
    for shift in _SCENARIO_SHIFTS:
        new_ytm = ytm + shift / 100.0
        new_price = _bond_price(coupon, new_ytm, years_to_mat, freq)
        price_chg = round(new_price - price_dirty, 4)
        price_chg_pct = round(price_chg / price_dirty * 100, 4) if price_dirty else 0.0
        scenarios.append({
            "shiftBps": shift,
            "newYield": round(new_ytm, 4),
            "newPrice": new_price,
            "priceChange": price_chg,
            "priceChangePct": price_chg_pct,
        })

    return {
        "issuer": issuer,
        "coupon": coupon,
        "maturityDate": maturity_str,
        "faceValue": face,
        "price": price_dirty,
        "yieldPct": ytm,
        "modifiedDuration": mod_duration,
        "effectiveDuration": eff_duration,
        "convexity": convexity,
        "dv01": dv01,
        "payments": payments,
        "scenarios": scenarios,
    }


# ----------------------------- derivatives builders -------------------------

def build_iv_surface(params: dict) -> dict:
    """Implied volatility surface across strikes and expiries."""
    symbol = (params.get("symbol") or "NVDA").upper()
    company = data.get_company(symbol)
    if not company:
        # fallback to NVDA
        symbol = "NVDA"
        company = data.get_company(symbol)

    S = company["price"]
    beta = company["beta"]
    # Base ATM IV derived from beta and recent vol; roughly 20-60% for typical names
    base_iv = round(0.18 + beta * 0.09 + abs(company["changePct"]) * 0.005, 3)
    base_iv = max(0.15, min(0.80, base_iv))

    # Expiry ladder: label -> years
    expiry_labels = ["1W", "2W", "1M", "2M", "3M", "6M", "1Y"]
    expiry_years = [7/365, 14/365, 30/365, 60/365, 90/365, 180/365, 365/365]

    # Strike grid: 9 strikes from 80% to 120% of spot
    n_strikes = 9
    strike_pcts = [0.80, 0.85, 0.90, 0.925, 0.95, 1.0, 1.05, 1.075, 1.10]
    strikes = [round(S * p, 2) for p in strike_pcts]

    surface = []
    for exp_label, T in zip(expiry_labels, expiry_years):
        for i, (K, pct) in enumerate(zip(strikes, strike_pcts)):
            moneyness = math.log(pct)  # log-moneyness: 0 = ATM
            iv = _iv_smile(moneyness, T, base_iv)
            surface.append({
                "strike": K,
                "expiry": exp_label,
                "iv": round(iv * 100, 2),  # percent
            })

    # Skew strip: 1M slice for the skew indicator
    T_1m = 30 / 365
    skew = []
    for K, pct in zip(strikes, strike_pcts):
        moneyness = math.log(pct)
        iv = _iv_smile(moneyness, T_1m, base_iv)
        skew.append({
            "strike": K,
            "iv": round(iv * 100, 2),
            "moneyness": round(moneyness * 100, 1),  # log-moneyness in pct
        })

    atm_iv = round(base_iv * 100, 2)
    return {
        "symbol": symbol,
        "underlyingPrice": S,
        "expiries": expiry_labels,
        "strikes": strikes,
        "surface": surface,
        "atmIv": atm_iv,
        "skew": skew,
    }


def _parse_strategy(query: str) -> str:
    """Map natural-language or param to a canonical strategy name."""
    q = query.lower().replace("-", " ").replace("_", " ")
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
    if "covered" in q or "buy write" in q:
        return "covered_call"
    if "put" in q:
        return "long_put"
    if "call" in q:
        return "long_call"
    return "straddle"


def build_options_strategy(params: dict) -> dict:
    """Options strategy payoff diagram with Greeks breakdown."""
    symbol = (params.get("symbol") or "NVDA").upper()
    company = data.get_company(symbol)
    if not company:
        symbol = "NVDA"
        company = data.get_company(symbol)

    S = company["price"]
    beta = company["beta"]
    base_iv = max(0.18, min(0.75, 0.20 + beta * 0.08))
    r = 0.05
    T = 45 / 365  # 45 DTE standard

    # Determine strategy
    strategy_raw = params.get("strategy") or params.get("strategyName") or "straddle"
    strategy = _parse_strategy(strategy_raw)

    atm = round(round(S / 5) * 5, 0)  # round to nearest $5

    legs = []
    strategy_name = ""

    if strategy == "iron_condor":
        strategy_name = "Iron Condor"
        # Short put spread + short call spread
        puts_short_k = round(atm * 0.95, 0)
        puts_long_k = round(atm * 0.90, 0)
        calls_short_k = round(atm * 1.05, 0)
        calls_long_k = round(atm * 1.10, 0)
        iv_mod = _iv_smile(math.log(puts_short_k / S), T, base_iv)
        legs = [
            ("put", "short", puts_short_k, iv_mod),
            ("put", "long", puts_long_k, _iv_smile(math.log(puts_long_k / S), T, base_iv)),
            ("call", "short", calls_short_k, _iv_smile(math.log(calls_short_k / S), T, base_iv)),
            ("call", "long", calls_long_k, _iv_smile(math.log(calls_long_k / S), T, base_iv)),
        ]
    elif strategy == "straddle":
        strategy_name = "Long Straddle"
        iv_atm = _iv_smile(0, T, base_iv)
        legs = [
            ("call", "long", atm, iv_atm),
            ("put", "long", atm, iv_atm),
        ]
    elif strategy == "strangle":
        strategy_name = "Long Strangle"
        call_k = round(atm * 1.05, 0)
        put_k = round(atm * 0.95, 0)
        legs = [
            ("call", "long", call_k, _iv_smile(math.log(call_k / S), T, base_iv)),
            ("put", "long", put_k, _iv_smile(math.log(put_k / S), T, base_iv)),
        ]
    elif strategy == "bull_call_spread":
        strategy_name = "Bull Call Spread"
        call_long_k = round(atm * 0.98, 0)
        call_short_k = round(atm * 1.05, 0)
        legs = [
            ("call", "long", call_long_k, _iv_smile(math.log(call_long_k / S), T, base_iv)),
            ("call", "short", call_short_k, _iv_smile(math.log(call_short_k / S), T, base_iv)),
        ]
    elif strategy == "bear_put_spread":
        strategy_name = "Bear Put Spread"
        put_long_k = round(atm * 1.02, 0)
        put_short_k = round(atm * 0.95, 0)
        legs = [
            ("put", "long", put_long_k, _iv_smile(math.log(put_long_k / S), T, base_iv)),
            ("put", "short", put_short_k, _iv_smile(math.log(put_short_k / S), T, base_iv)),
        ]
    elif strategy == "covered_call":
        strategy_name = "Covered Call"
        call_short_k = round(atm * 1.05, 0)
        legs = [
            ("call", "short", call_short_k, _iv_smile(math.log(call_short_k / S), T, base_iv)),
        ]
    elif strategy == "long_put":
        strategy_name = "Long Put"
        put_k = round(atm * 0.95, 0)
        legs = [
            ("put", "long", put_k, _iv_smile(math.log(put_k / S), T, base_iv)),
        ]
    else:  # long_call default
        strategy_name = "Long Call"
        call_k = round(atm * 1.05, 0)
        legs = [
            ("call", "long", call_k, _iv_smile(math.log(call_k / S), T, base_iv)),
        ]

    # Build legs with BS prices + greeks
    expiry_date = (date.today() + timedelta(days=45)).strftime("%b %d '%y")
    built_legs = []
    for opt_type, action, K, sigma in legs:
        price = _bs_price(S, K, T, r, sigma, opt_type)
        greeks = _bs_greeks(S, K, T, r, sigma, opt_type)
        sign = 1 if action == "long" else -1
        built_legs.append({
            "type": opt_type,
            "action": action,
            "strike": float(K),
            "expiry": expiry_date,
            "premium": round(price, 2),
            "delta": round(greeks["delta"] * sign, 4),
            "gamma": round(greeks["gamma"] * sign, 5),
            "theta": round(greeks["theta"] * sign, 4),
            "vega": round(greeks["vega"] * sign, 4),
        })

    # Net greeks + cost
    net_delta = sum(l["delta"] for l in built_legs)
    net_gamma = sum(l["gamma"] for l in built_legs)
    net_theta = sum(l["theta"] for l in built_legs)
    net_vega = sum(l["vega"] for l in built_legs)
    cost_per_share = sum(
        (l["premium"] if l["action"] == "long" else -l["premium"]) for l in built_legs
    )

    # Payoff at expiry
    price_range = [S * p / 100 for p in range(70, 131)]
    payoff_points = []
    for spot in price_range:
        pnl = -cost_per_share  # initial debit/credit
        for leg, (opt_type, action, K, _) in zip(built_legs, legs):
            intrinsic = max(spot - K, 0) if opt_type == "call" else max(K - spot, 0)
            if action == "long":
                pnl += intrinsic
            else:
                pnl -= intrinsic
        # For covered call: also include stock PnL
        if strategy == "covered_call":
            pnl += (spot - S)
        payoff_points.append({"price": round(spot, 2), "pnl": round(pnl, 2)})

    # Breakevens (where payoff crosses zero)
    breakevens = []
    for i in range(1, len(payoff_points)):
        p0, p1 = payoff_points[i - 1], payoff_points[i]
        if p0["pnl"] * p1["pnl"] < 0:
            # linear interpolation
            frac = -p0["pnl"] / (p1["pnl"] - p0["pnl"])
            be = round(p0["price"] + frac * (p1["price"] - p0["price"]), 2)
            breakevens.append(be)

    pnl_values = [p["pnl"] for p in payoff_points]
    max_profit = max(pnl_values)
    max_loss = min(pnl_values)
    # Cap infinite loss/profit labels
    if max_profit > S * 0.5:
        max_profit = None  # effectively unlimited
    if max_loss < -S * 0.5:
        max_loss = None

    return {
        "symbol": symbol,
        "underlyingPrice": S,
        "strategyName": strategy_name,
        "legs": built_legs,
        "netGreeks": {
            "delta": round(net_delta, 4),
            "gamma": round(net_gamma, 5),
            "theta": round(net_theta, 4),
            "vega": round(net_vega, 4),
            "cost": round(cost_per_share, 2),
        },
        "payoff": payoff_points,
        "maxProfit": round(max_profit, 2) if max_profit is not None else None,
        "maxLoss": round(max_loss, 2) if max_loss is not None else None,
        "breakevens": [round(b, 2) for b in breakevens[:4]],
    }


def build_vol_term_structure(params: dict) -> dict:
    """Volatility term structure across monthly expiries."""
    symbol = (params.get("symbol") or params.get("scope") or "VIX").upper()

    # Handle VIX specially
    is_vix = symbol in ("VIX", "^VIX", "VVIX")
    if is_vix:
        symbol = "VIX"
        spot_vix = 18.4
        base_iv = 0.22
        beta = 1.0
    else:
        company = data.get_company(symbol)
        if not company:
            # Try as a known vol index keyword
            is_vix = True
            symbol = "VIX"
            spot_vix = 18.4
            base_iv = 0.22
            beta = 1.0
        else:
            beta = company["beta"]
            base_iv = max(0.15, min(0.75, 0.18 + beta * 0.09))
            spot_vix = round(base_iv * 100 * 0.9, 1)

    # Determine regime from seed
    seed = data._seed(symbol)
    regime_val = (seed % 3)
    if regime_val == 0:
        regime = "contango"
    elif regime_val == 1:
        regime = "backwardation"
    else:
        regime = "flat"

    # Expiry ladder
    expiry_defs = [
        ("1W", 7), ("2W", 14), ("1M", 30), ("2M", 60),
        ("3M", 90), ("4M", 120), ("6M", 180), ("9M", 270), ("1Y", 365),
    ]
    r = 0.05
    expiries = []
    prev_iv = None
    for label, days in expiry_defs:
        T = days / 365
        if regime == "contango":
            # IV rises with term (normal term structure)
            term_bump = 0.03 * math.log(T * 12 + 1)
        elif regime == "backwardation":
            # Front months elevated (stress / event risk)
            term_bump = -0.04 * math.log(T * 12 + 1)
        else:
            term_bump = 0.01 * math.sin(T * math.pi)

        # Add small noise seeded by label
        noise = (data._seed(symbol + label) % 100 - 50) / 1000
        iv = max(0.08, base_iv + term_bump + noise)

        # ATM premium using BS
        atm_premium = _bs_price(100, 100, T, r, iv, "call")

        is_contango = prev_iv is None or iv >= prev_iv
        prev_iv = iv

        expiries.append({
            "label": label,
            "daysToExpiry": days,
            "iv": round(iv * 100, 2),
            "atmPremium": round(atm_premium, 2),
            "isContango": is_contango,
        })

    atm_iv = expiries[2]["iv"]  # 1M as reference ATM IV
    return {
        "symbol": symbol,
        "spotVix": spot_vix,
        "atmIv": atm_iv,
        "regime": regime,
        "expiries": expiries,
    }


def build_structured_product(params: dict) -> dict:
    """Structured/exotic product pricer — down-and-out barrier option."""
    symbol = (params.get("symbol") or "NVDA").upper()
    company = data.get_company(symbol)
    if not company:
        symbol = "NVDA"
        company = data.get_company(symbol)

    S = company["price"]
    beta = company["beta"]
    base_iv = max(0.15, min(0.75, 0.20 + beta * 0.09))
    r = 0.05

    # Parse / default product parameters
    product_type_raw = (params.get("productType") or params.get("product_type") or "down_and_out_call").lower()
    if "up" in product_type_raw and "out" in product_type_raw:
        product_type = "up_and_out_call"
        product_label = "Up-and-Out Call"
    elif "down" in product_type_raw and "in" in product_type_raw:
        product_type = "down_and_in_put"
        product_label = "Down-and-In Put"
    elif "up" in product_type_raw and "in" in product_type_raw:
        product_type = "up_and_in_call"
        product_label = "Up-and-In Call"
    else:
        product_type = "down_and_out_call"
        product_label = "Down-and-Out Call"

    tenor = float(params.get("tenor") or 0.5)  # years
    notional = float(params.get("notional") or 100_000)
    strike_pct = float(params.get("strike_pct") or 1.0)
    barrier_pct = float(params.get("barrier_pct") or 0.85)

    K = round(S * strike_pct, 2)
    barrier = round(S * barrier_pct, 2)

    # Vanilla BS price
    vanilla_price = _bs_price(S, K, tenor, r, base_iv, "call")
    vanilla_greeks = _bs_greeks(S, K, tenor, r, base_iv, "call")

    # Simple barrier adjustment factor using reflection principle approximation
    if product_type == "down_and_out_call":
        # Price = Vanilla - Reflected = C(S) - (H/S)^(2*lambda) * C(H²/S)
        lam = (r + 0.5 * base_iv ** 2) / base_iv ** 2
        refl_S = barrier ** 2 / S
        refl_price = _bs_price(refl_S, K, tenor, r, base_iv, "call")
        barrier_price = vanilla_price - (barrier / S) ** (2 * lam) * refl_price
    elif product_type == "up_and_out_call":
        # Knock out if goes above barrier — reduced value
        barrier_price = vanilla_price * max(0, 1 - max(0, (S / barrier - 0.9)))
    else:
        # Approximate: barrier in = vanilla * knock_in_prob
        knock_in_prob = math.exp(-2 * math.log(S / barrier) ** 2 / (base_iv ** 2 * tenor))
        barrier_price = vanilla_price * min(1, knock_in_prob + 0.3)

    barrier_price = max(0.01, round(barrier_price, 2))

    # Greeks: scale vanilla greeks by barrier discount factor
    ratio = barrier_price / vanilla_price if vanilla_price > 0 else 0.5
    delta = round(vanilla_greeks["delta"] * ratio, 4)
    gamma = round(vanilla_greeks["gamma"] * ratio, 5)
    vega = round(vanilla_greeks["vega"] * ratio, 4)
    theta = round(vanilla_greeks["theta"] * ratio, 4)

    # Scenario table: 9 spot paths
    spot_moves = [-0.30, -0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20]
    scenarios = []
    for move in spot_moves:
        final_spot = round(S * (1 + move), 2)
        # Check barrier breach
        path_min = final_spot if move < 0 else S * 0.99  # simplified path check
        if product_type == "down_and_out_call" and path_min <= barrier:
            intrinsic = 0.0  # knocked out
            prob = 0.5 * math.exp(-abs(move) * 2)
        elif product_type == "up_and_out_call" and final_spot >= barrier:
            intrinsic = 0.0
            prob = 0.3 * math.exp(-abs(move) * 1.5)
        else:
            intrinsic = max(final_spot - K, 0)
            prob = 0.6 * math.exp(-abs(move) * 1.5)

        pnl_per_share = intrinsic - barrier_price
        pnl_total = round(pnl_per_share * notional / S, 0)
        return_pct = round((pnl_per_share / barrier_price) * 100, 1) if barrier_price > 0 else 0.0

        label = f"{'+' if move >= 0 else ''}{int(move * 100)}%"
        scenarios.append({
            "label": label,
            "spotMove": round(move * 100, 1),
            "finalSpot": final_spot,
            "pnl": pnl_total,
            "returnPct": return_pct,
            "probability": round(prob, 3),
        })

    fair_value = round(barrier_price * notional / S, 2)

    return {
        "symbol": symbol,
        "productType": product_label,
        "spotPrice": S,
        "barrier": barrier,
        "barrierPct": round(barrier_pct * 100, 1),
        "tenor": tenor,
        "notional": notional,
        "strike": K,
        "bsPrice": vanilla_price,
        "fairValue": fair_value,
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "theta": theta,
        "impliedVol": round(base_iv * 100, 1),
        "scenarios": scenarios,
    }


def build_correlation_matrix(params: dict) -> dict:
    symbols = [s.upper() for s in (params.get("symbols") or []) if data.get_company(s.upper())]
    if len(symbols) < 2:
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    
    seed = data._seed("_".join(sorted(symbols)) + "corr")

    def rnd():
        nonlocal seed
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    # Symmetric n x n matrix
    matrix = []
    for i, s1 in enumerate(symbols):
        row = []
        for j, s2 in enumerate(symbols):
            if i == j:
                val = 1.0
            elif i > j:
                val = matrix[j][i]
            else:
                # Base correlation 0.3-0.7
                val = round(0.3 + rnd() * 0.4, 2)
                # Boost if same sector
                c1 = data.get_company(s1)
                c2 = data.get_company(s2)
                if c1 and c2 and c1["sector"] == c2["sector"]:
                    val = min(0.99, val + 0.2)
            row.append(val)
        matrix.append(row)

    betas = []
    for s in symbols:
        c = data.get_company(s)
        b = c["beta"] if c else 1.0
        betas.append({
            "symbol": s,
            "beta": b,
            "hedgeRatio": round(1.0 / b, 2) if b > 0 else 0.0
        })

    return {
        "symbols": symbols,
        "matrix": matrix,
        "betas": betas
    }


def build_factor_analysis(params: dict) -> dict:
    """Single-stock factor return attribution from the REAL Barra-style model.

    Loadings are the stock's standardized factor exposures; the t-stat is each
    factor's own return significance over the window and the contribution is the
    exposure times the annualized factor return. Monthly attribution splits the
    stock's realized monthly return into named-factor contributions plus a
    residual that absorbs everything else (market, volatility, idiosyncratic).
    """
    import numpy as np
    from collections import OrderedDict

    symbol = (params.get("symbol") or "AAPL").upper()
    company = data.get_company(symbol)
    if not company:
        symbol = "AAPL"
        company = data.get_company(symbol)

    res = factor_model.build([symbol])
    model = res.model
    if symbol not in model.symbols:
        raise ValueError(
            f"{symbol} lacks the price history or fundamentals needed to factor-model it"
        )
    i = model.symbols.index(symbol)
    names = model.factor_names
    fidx = {n: k for k, n in enumerate(names)}
    expo = model.exposures[i]  # [Market, Size, Value, Momentum, Volatility, Quality]

    # The panel charts these four named factors; residual captures the rest.
    panel_factors = ["Momentum", "Value", "Size", "Quality"]

    stock_rets = res.returns[:, i]  # (T,)
    F = model.factor_returns  # (T, K)
    dates = res.dates  # length T

    # Group daily contributions by calendar month.
    months: "OrderedDict[str, dict]" = OrderedDict()
    for t, d in enumerate(dates):
        ym = d[:7]
        m = months.setdefault(
            ym, {"stock": 0.0, **{f: 0.0 for f in panel_factors}}
        )
        # Compound daily contributions within the month for honest monthly numbers.
        m["stock"] = (1.0 + m["stock"]) * (1.0 + float(stock_rets[t])) - 1.0
        for f in panel_factors:
            contrib = float(expo[fidx[f]] * F[t, fidx[f]])
            m[f] = (1.0 + m[f]) * (1.0 + contrib) - 1.0

    attribution = []
    for ym, m in list(months.items())[-12:]:
        named = {f: round(m[f] * 100.0, 2) for f in panel_factors}
        residual = round((m["stock"] - sum(m[f] for f in panel_factors)) * 100.0, 2)
        attribution.append({
            "month": ym,
            "momentum": named["Momentum"],
            "value": named["Value"],
            "size": named["Size"],
            "quality": named["Quality"],
            "residual": residual,
        })

    loadings = []
    for f in panel_factors:
        k = fidx[f]
        loadings.append({
            "factor": f,
            "loading": round(float(expo[k]), 2),
            "tStat": round(float(res.factor_tstats[f]), 2),
            "contribution": round(float(expo[k] * res.factor_ann_returns[f]) * 100.0, 2),
        })

    return {
        "symbol": symbol,
        "name": company["name"],
        "monthlyAttribution": attribution,
        "loadings": loadings,
        "asOf": res.coverage.as_of,
        "source": res.coverage.source,
    }


def _coverage_payload(res: "factor_model.RiskModelResult", dropped: list) -> dict:
    """Honest coverage block shared by the risk-model panels."""
    excluded = list(res.coverage.excluded)
    seen = {e["symbol"] for e in excluded}
    for s in dropped:
        if s not in seen:
            excluded.append({"symbol": s, "reason": "insufficient overlapping history"})
            seen.add(s)
    return {
        "included": len(res.coverage.included),
        "excluded": len(excluded),
        "excludedNames": excluded[:12],
        "days": res.coverage.days,
        "source": res.coverage.source,
        "pcaVarExplained": [round(x, 4) for x in res.pca],
    }


def _resolve_portfolio(params: dict):
    """Resolve (name, symbols, weights) from params with sane defaults."""
    symbols = [s.upper() for s in (params.get("symbols") or []) if repo.get_company(s.upper())]
    if not symbols:
        symbols = ["NVDA", "MSFT", "GOOGL", "META", "AMZN"]
    pairs = factor_model.resolve_weights(symbols, params.get("weights"))
    syms = [s for s, _ in pairs]
    ws = [w for _, w in pairs]
    name = params.get("portfolio_name") or (
        ", ".join(syms[:3]) + (" + …" if len(syms) > 3 else "") + " Portfolio"
    )
    return name, syms, ws


def build_risk_model(params: dict) -> dict:
    """Portfolio risk decomposition from the real multi-factor model.

    Splits predicted volatility into factor vs specific risk, attributes risk to
    each common factor, and reports the marginal contribution to risk of every
    holding — with an explicit coverage block listing any names that had to be
    excluded for want of history or fundamentals.
    """
    import numpy as np

    name, syms, ws = _resolve_portfolio(params)
    res = factor_model.build(syms)
    model = res.model
    idx, w, dropped = factor_model.portfolio_indices(res, syms, ws)
    pr = engine.decompose_portfolio(model, idx, w)

    holdings = []
    for k, i in enumerate(idx):
        s = model.symbols[i]
        c = data.get_company(s)
        holdings.append({
            "symbol": s,
            "name": c["name"] if c else s,
            "weight": round(float(w[k]) * 100.0, 2),
            "mctr": round(float(pr.mctr[k]) * 100.0, 2),
            "pctOfRisk": round(float(pr.pct_contrib[k]), 2),
            "specificVol": round(float(np.sqrt(model.specific_var[i])) * 100.0, 2),
        })
    holdings.sort(key=lambda h: h["pctOfRisk"], reverse=True)

    factor_contributions = []
    for kk, fn in enumerate(model.factor_names):
        factor_contributions.append({
            "factor": fn,
            "exposure": round(float(pr.factor_exposures[kk]), 3),
            "volContribution": round(float(pr.factor_vol_contrib[kk]) * 100.0, 2),
            "pctOfRisk": round(float(pr.factor_var_contrib[kk]), 2),
        })

    return {
        "portfolioName": name,
        "totalVol": round(pr.total_vol * 100.0, 2),
        "factorVol": round(pr.factor_vol * 100.0, 2),
        "specificVol": round(pr.specific_vol * 100.0, 2),
        "factorVarPct": round(pr.factor_var_pct, 2),
        "specificVarPct": round(pr.specific_var_pct, 2),
        "diversificationRatio": round(pr.diversification_ratio, 2),
        "rSquared": round(model.r2, 3),
        "factorContributions": factor_contributions,
        "holdings": holdings,
        "coverage": _coverage_payload(res, dropped),
        "asOf": res.coverage.as_of,
        "source": res.coverage.source,
    }


# --------------------------- risk monitor ---------------------------
# Real historical crisis windows replayed onto the current book. Each is a
# genuine market dislocation; the book's holdings' REAL returns over the window
# are replayed (no imputation) to estimate the P&L the book would have taken.
RISK_CRISIS_WINDOWS = [
    {"id": "covid2020", "label": "COVID Crash", "start": "2020-02-19", "end": "2020-03-23"},
    {"id": "rateshock2022", "label": "2022 Rate Shock", "start": "2022-01-03", "end": "2022-10-14"},
    {"id": "gfc2008", "label": "GFC 2008 (Lehman)", "start": "2008-09-02", "end": "2008-11-20"},
    {"id": "q4_2018", "label": "Q4 2018 Selloff", "start": "2018-10-01", "end": "2018-12-24"},
    {"id": "vol2015", "label": "Aug 2015 (China)", "start": "2015-08-10", "end": "2015-08-26"},
]

# Default risk limits (fractions of NAV, exposure units for factors, daily VaR
# fraction). Any subset can be overridden via the `limits` param.
DEFAULT_RISK_LIMITS = {
    "maxGross": 2.0,      # gross exposure as multiple of NAV
    "maxNet": 1.2,        # |net| exposure as multiple of NAV
    "maxPosition": 0.15,  # |weight| of any single name
    "maxSector": 0.40,    # |net| exposure to any single sector
    "maxFactor": 1.5,     # |exposure| to any single style/market factor
    "varLimit": 0.035,    # daily 95% VaR as fraction of NAV
}

# Default hypothetical macro shocks, each mapped through the book's REAL factor
# exposures (b · shock). The Market factor is the book's net beta.
DEFAULT_HYPO_SHOCKS = [
    {"id": "equity_selloff", "label": "Equities −10%", "factorShocks": {"Market": -10.0}},
    {"id": "momentum_reversal", "label": "Momentum Reversal −8%", "factorShocks": {"Momentum": -8.0}},
    {"id": "vol_spike", "label": "Volatility Spike +6%", "factorShocks": {"Volatility": 6.0}},
    {"id": "quality_flight", "label": "Flight to Quality +5%", "factorShocks": {"Quality": 5.0}},
    {"id": "value_rotation", "label": "Value Rotation +6%", "factorShocks": {"Value": 6.0}},
]


def _resolve_book(params: dict):
    """Resolve (name, symbols, signed NAV-fraction weights, nav) for a book.

    Provided `weights` are treated as raw NAV fractions (signed, so a long/short
    book keeps its leverage and net), while the default is an equal-weight, fully
    invested long book. `nav`/`capital` set the dollar base (default $10M).
    """
    raw = [s.upper() for s in (params.get("symbols") or [])]
    symbols = [s for s in raw if repo.get_company(s)]
    if not symbols:
        symbols = ["NVDA", "MSFT", "GOOGL", "META", "AMZN"]
    weights = params.get("weights")
    if weights and len(weights) == len(symbols):
        ws = [float(x) for x in weights]
    else:
        ws = [1.0 / len(symbols)] * len(symbols)
    nav = float(params.get("nav") or params.get("capital") or 10_000_000.0)
    if nav <= 0:
        nav = 10_000_000.0
    name = params.get("portfolio_name") or (
        ", ".join(symbols[:3]) + (" +…" if len(symbols) > 3 else "") + " Book"
    )
    return name, symbols, ws, nav


def build_risk_monitor(params: dict) -> dict:
    """Risk desk: live exposures, limits, and stress testing for a real book.

    Combines (1) gross/net/sector/factor exposures and concentrations, (2) real
    historical VaR/CVaR plus the factor model's predicted vol, (3) a configurable
    limits framework with in-limit/breach status, (4) historical stress that
    replays REAL crisis-window returns onto the book, and (5) hypothetical stress
    that maps user/factor/asset shocks through the book's real exposures. Names
    without coverage are flagged, never imputed.
    """
    import numpy as np

    name, symbols, ws, nav = _resolve_book(params)
    weights_map = {s: w for s, w in zip(symbols, ws)}

    # --- exposures ---
    gross = sum(abs(w) for w in ws)
    net = sum(ws)
    positions = []
    for s, w in zip(symbols, ws):
        c = repo.get_company(s)
        positions.append({
            "symbol": s,
            "name": c["name"] if c else s,
            "sector": (c.get("sector") if c else None),
            "weightPct": round(w * 100.0, 2),
            "exposureUsd": round(w * nav, 0),
            "side": "long" if w >= 0 else "short",
        })
    positions.sort(key=lambda p: abs(p["weightPct"]), reverse=True)

    sec_net: Dict[str, float] = {}
    sec_gross: Dict[str, float] = {}
    for s, w in zip(symbols, ws):
        c = repo.get_company(s)
        key = (c.get("sector") if c else None) or "unknown"
        sec_net[key] = sec_net.get(key, 0.0) + w
        sec_gross[key] = sec_gross.get(key, 0.0) + abs(w)
    sectors = [{
        "sector": k,
        "label": repo.sector_name(k) if k != "unknown" else "Unclassified",
        "netPct": round(v * 100.0, 2),
        "grossPct": round(sec_gross[k] * 100.0, 2),
        "netUsd": round(v * nav, 0),
    } for k, v in sec_net.items()]
    sectors.sort(key=lambda x: abs(x["netPct"]), reverse=True)

    # --- real historical VaR / CVaR / vol from the signed book return series ---
    series: Dict[str, "np.ndarray"] = {}
    src = "mock"
    as_of: Optional[str] = None
    for s in symbols:
        meta = repo.price_series_meta(s, days=260)
        pts = meta.get("points") or []
        closes = [p["c"] for p in pts if p.get("c")]
        if len(closes) >= 30:
            arr = np.asarray(closes, dtype=float)
            series[s] = arr[1:] / arr[:-1] - 1.0
            if meta.get("source") == "live":
                src = "live"
            if meta.get("asOf"):
                as_of = meta["asOf"] if as_of is None else max(as_of, meta["asOf"])
    risk_syms = [s for s in symbols if s in series]
    var95 = cvar95 = ann_vol = None
    days_used = 0
    if risk_syms:
        n = min(len(series[s]) for s in risk_syms)
        days_used = int(n)
        mat = np.vstack([series[s][-n:] for s in risk_syms])  # (k, n)
        wvec = np.asarray([weights_map[s] for s in risk_syms], dtype=float)
        book_rets = (wvec[:, None] * mat).sum(axis=0)
        var95 = engine.var_historical(book_rets, 0.95)
        cvar95 = engine.cvar_historical(book_rets, 0.95)
        ann_vol = float(np.std(book_rets, ddof=0) * np.sqrt(252))

    # --- factor exposures + MCTR via the real model (leverage-aware weights) ---
    factor_block: dict = {"available": False, "exposures": [], "holdings": [],
                          "predictedVolPct": None, "factorVolPct": None,
                          "specificVolPct": None}
    factor_exposures: Dict[str, float] = {}
    try:
        res = factor_model.build(symbols)
        model = res.model
        pos_map = {sym: i for i, sym in enumerate(model.symbols)}
        idx, wsel = [], []
        for s, w in zip(symbols, ws):
            if s in pos_map:
                idx.append(pos_map[s])
                wsel.append(w)
        if idx:
            wv = np.asarray(wsel, dtype=float)
            pr = engine.decompose_portfolio(model, idx, wv)
            exps = []
            for kk, fn in enumerate(model.factor_names):
                e = float(pr.factor_exposures[kk])
                factor_exposures[fn] = e
                exps.append({
                    "factor": fn,
                    "exposure": round(e, 3),
                    "pctOfRisk": round(float(pr.factor_var_contrib[kk]), 2),
                })
            fh = []
            for k, i in enumerate(idx):
                fh.append({
                    "symbol": model.symbols[i],
                    "weightPct": round(float(wv[k]) * 100.0, 2),
                    "mctr": round(float(pr.mctr[k]) * 100.0, 2),
                    "pctOfRisk": round(float(pr.pct_contrib[k]), 2),
                })
            fh.sort(key=lambda h: h["pctOfRisk"], reverse=True)
            factor_block = {
                "available": True,
                "exposures": exps,
                "holdings": fh,
                "predictedVolPct": round(pr.total_vol * 100.0, 2),
                "factorVolPct": round(pr.factor_vol * 100.0, 2),
                "specificVolPct": round(pr.specific_vol * 100.0, 2),
            }
    except Exception:  # noqa: BLE001 — factor model degrades to exposure-only
        factor_block["available"] = False

    # --- limits framework ---
    lim = {**DEFAULT_RISK_LIMITS, **(params.get("limits") or {})}
    rows: List[dict] = []

    def _add(name_, scope, current, limit, fmt, detail=None):
        limit = float(limit)
        util = (abs(current) / limit * 100.0) if limit else 0.0
        status = "breach" if abs(current) > limit else ("warn" if util >= 80.0 else "ok")
        rows.append({
            "name": name_, "scope": scope, "current": round(float(current), 4),
            "limit": round(limit, 4), "utilizationPct": round(util, 1),
            "status": status, "format": fmt, "detail": detail,
        })

    _add("Gross Exposure", "book", gross, lim["maxGross"], "ratio")
    _add("Net Exposure", "book", net, lim["maxNet"], "ratio")
    worst_pos = max(positions, key=lambda p: abs(p["weightPct"])) if positions else None
    if worst_pos:
        over = [p["symbol"] for p in positions if abs(p["weightPct"]) / 100.0 > lim["maxPosition"]]
        _add("Max Position", worst_pos["symbol"], worst_pos["weightPct"] / 100.0,
             lim["maxPosition"], "ratio", ", ".join(over) if over else None)
    if sectors:
        worst_sec = max(sectors, key=lambda x: abs(x["netPct"]))
        _add("Max Sector (net)", worst_sec["label"], worst_sec["netPct"] / 100.0,
             lim["maxSector"], "ratio", worst_sec["label"])
    if factor_block["available"] and factor_exposures:
        wf = max(factor_exposures.items(), key=lambda kv: abs(kv[1]))
        _add("Max Factor", wf[0], wf[1], lim["maxFactor"], "exp", wf[0])
    if var95 is not None:
        _add("Daily VaR 95%", "book", var95, lim["varLimit"], "pct")

    breaches = [r for r in rows if r["status"] == "breach"]

    # --- historical stress (real crisis-window replay) ---
    union_start = min(w["start"] for w in RISK_CRISIS_WINDOWS)
    union_end = max(w["end"] for w in RISK_CRISIS_WINDOWS)
    closes_by_sym: Dict[str, Dict[str, float]] = {}
    for s in symbols:
        try:
            closes_by_sym[s] = cache.cached(
                f"histcloses:{s}:{union_start}:{union_end}", 6 * 3600,
                lambda s=s: p_src.fetch_daily_closes(s, union_start, union_end),
            ) or {}
        except Exception:  # noqa: BLE001 — missing coverage, never imputed
            closes_by_sym[s] = {}

    historical = []
    for win in RISK_CRISIS_WINDOWS:
        rep = engine.replay_window(weights_map, closes_by_sym, win["start"], win["end"])
        period = f'{win["start"]} → {win["end"]}'
        if rep is None:
            historical.append({
                "id": win["id"], "label": win["label"], "period": period,
                "available": False, "bookPnlPct": None, "bookPnlUsd": None,
                "maxDrawdownPct": None, "covered": [],
                "missing": [{"symbol": s, "reason": "no price history in window"} for s in symbols],
                "worst": [],
            })
            continue
        historical.append({
            "id": win["id"], "label": win["label"], "period": period,
            "available": True,
            "bookPnlPct": rep["bookPnlPct"],
            "bookPnlUsd": round(rep["bookPnlPct"] / 100.0 * nav, 0),
            "maxDrawdownPct": rep["maxDrawdownPct"],
            "covered": rep["covered"],
            "missing": [{"symbol": s, "reason": "no price history in window"} for s in rep["missing"]],
            "worst": rep["perHolding"][:3],
        })

    # --- hypothetical stress (factor/asset shocks through real exposures) ---
    hypothetical = []
    if factor_exposures:
        for sc in DEFAULT_HYPO_SHOCKS:
            r = engine.factor_shock_pnl(factor_exposures, sc["factorShocks"])
            hypothetical.append({
                "id": sc["id"], "label": sc["label"],
                "pnlPct": r["totalPnlPct"],
                "pnlUsd": round(r["totalPnlPct"] / 100.0 * nav, 0),
                "breakdown": r["contributions"],
            })

    custom = None
    fshocks = dict(params.get("factor_shocks") or {})
    ashocks = dict(params.get("asset_shocks") or {})
    if params.get("market_shock") is not None:
        fshocks["Market"] = float(params["market_shock"])
    if fshocks or ashocks:
        fb = engine.factor_shock_pnl(factor_exposures, fshocks) if factor_exposures else {"contributions": [], "totalPnlPct": 0.0}
        ab = engine.asset_shock_pnl(weights_map, ashocks)
        total = fb["totalPnlPct"] + ab["totalPnlPct"]
        custom = {
            "label": "Custom Shock",
            "pnlPct": round(total, 2),
            "pnlUsd": round(total / 100.0 * nav, 0),
            "factorBreakdown": fb["contributions"],
            "assetBreakdown": ab["contributions"],
        }

    # --- coverage (honest: names with no usable return history are excluded) ---
    excluded = [{"symbol": s, "reason": "no usable price history"} for s in symbols if s not in series]
    coverage = {
        "included": len(risk_syms),
        "excluded": len(excluded),
        "excludedNames": excluded[:12],
        "days": days_used,
        "source": src,
    }

    return {
        "bookName": name,
        "nav": round(nav, 0),
        "grossPct": round(gross * 100.0, 2),
        "netPct": round(net * 100.0, 2),
        "grossUsd": round(gross * nav, 0),
        "netUsd": round(net * nav, 0),
        "longCount": sum(1 for w in ws if w >= 0),
        "shortCount": sum(1 for w in ws if w < 0),
        "risk": {
            "var95Pct": round(var95 * 100.0, 2) if var95 is not None else None,
            "cvar95Pct": round(cvar95 * 100.0, 2) if cvar95 is not None else None,
            "annVolPct": round(ann_vol * 100.0, 2) if ann_vol is not None else None,
            "predictedVolPct": factor_block.get("predictedVolPct"),
            "var95Usd": round(var95 * nav, 0) if var95 is not None else None,
            "cvar95Usd": round(cvar95 * nav, 0) if cvar95 is not None else None,
        },
        "positions": positions[:14],
        "sectors": sectors,
        "factor": factor_block,
        "limits": rows,
        "breaches": breaches,
        "inLimit": len(breaches) == 0,
        "historicalStress": historical,
        "hypotheticalStress": hypothetical,
        "customStress": custom,
        "coverage": coverage,
        "asOf": as_of,
        "source": src,
    }


def build_factor_exposures(params: dict) -> dict:
    """Portfolio factor tilts: the weighted-average exposure to each factor plus
    a per-holding exposure breakdown, alongside the realized factor premia."""
    name, syms, ws = _resolve_portfolio(params)
    res = factor_model.build(syms)
    model = res.model
    idx, w, dropped = factor_model.portfolio_indices(res, syms, ws)
    pr = engine.decompose_portfolio(model, idx, w)

    exposures = []
    for kk, fn in enumerate(model.factor_names):
        exposures.append({
            "factor": fn,
            "exposure": round(float(pr.factor_exposures[kk]), 3),
            "factorReturn": round(float(res.factor_ann_returns[fn]) * 100.0, 2),
            "tStat": round(float(res.factor_tstats[fn]), 2),
        })

    name_idx = {n: k for k, n in enumerate(model.factor_names)}
    holdings = []
    for k, i in enumerate(idx):
        s = model.symbols[i]
        c = data.get_company(s)
        row = model.exposures[i]
        holdings.append({
            "symbol": s,
            "name": c["name"] if c else s,
            "weight": round(float(w[k]) * 100.0, 2),
            "market": round(float(row[name_idx["Market"]]), 2),
            "size": round(float(row[name_idx["Size"]]), 2),
            "value": round(float(row[name_idx["Value"]]), 2),
            "momentum": round(float(row[name_idx["Momentum"]]), 2),
            "volatility": round(float(row[name_idx["Volatility"]]), 2),
            "quality": round(float(row[name_idx["Quality"]]), 2),
        })
    holdings.sort(key=lambda h: h["weight"], reverse=True)

    return {
        "portfolioName": name,
        "exposures": exposures,
        "holdings": holdings,
        "coverage": _coverage_payload(res, dropped),
        "asOf": res.coverage.as_of,
        "source": res.coverage.source,
    }


_ATTR_RANGE_LABELS = {
    "1M": "1 month", "3M": "3 months", "6M": "6 months",
    "1Y": "1 year", "YTD": "year to date",
}

# ---------------------------- real benchmarks ----------------------------
# Validated, real, liquid US-listed ETFs usable as a headline benchmark for the
# P&L / active-stats comparison. Known tickers get a friendly display name; any
# other ticker the user picks is accepted ONLY if a real price series can be
# sourced for it (see ``_resolve_benchmark``) — we never benchmark against
# non-real data, but the user is free to choose any real instrument or a custom
# basket of real constituents.
_BENCHMARK_ETFS = {
    # Broad market indices.
    "SPY": "S&P 500 (SPY)",
    "QQQ": "Nasdaq-100 (QQQ)",
    "DIA": "Dow Jones (DIA)",
    "IWM": "Russell 2000 (IWM)",
    "VTI": "US Total Market (VTI)",
    "VOO": "S&P 500 (VOO)",
    "RSP": "S&P 500 Equal Weight (RSP)",
    "MDY": "S&P MidCap 400 (MDY)",
    # Sector / industry / thematic ETFs (also valid headline benchmarks).
    "XLK": "Technology Sector (XLK)",
    "XLF": "Financials Sector (XLF)",
    "XLE": "Energy Sector (XLE)",
    "XLV": "Health Care Sector (XLV)",
    "XLY": "Consumer Discretionary (XLY)",
    "XLP": "Consumer Staples (XLP)",
    "XLI": "Industrials Sector (XLI)",
    "XLC": "Communication Services (XLC)",
    "XLB": "Materials Sector (XLB)",
    "XLRE": "Real Estate Sector (XLRE)",
    "XLU": "Utilities Sector (XLU)",
    "SMH": "Semiconductors (SMH)",
    "SOXX": "Semiconductors (SOXX)",
    "CIBR": "Cybersecurity (CIBR)",
    "XBI": "Biotech (XBI)",
    "ITA": "Aerospace & Defense (ITA)",
    "ICLN": "Clean Energy (ICLN)",
    "ARKK": "ARK Innovation (ARKK)",
    "IYT": "Transportation (IYT)",
    "KIE": "Insurance (KIE)",
    "XME": "Metals & Mining (XME)",
    # International / fixed income.
    "EFA": "Developed ex-US (EFA)",
    "EEM": "Emerging Markets (EEM)",
    "AGG": "US Aggregate Bond (AGG)",
}
_DEFAULT_BENCHMARK = "SPY"

# Yahoo history period that comfortably covers each requested window plus the
# lookback needed for the first window return. Sized generously so 1Y / YTD
# stats are computed over the full window rather than a truncated 6mo series.
_BENCH_PERIOD = {"1M": "3mo", "3M": "6mo", "6M": "1y", "1Y": "2y", "YTD": "1y"}

# Sector-aware proxy for the Brinson decomposition: the terminal's thematic
# sectors mapped onto real, liquid sector/industry ETFs so each benchmark sector
# return comes from a real traded instrument. Sectors with no clean real ETF
# (e.g. crypto / space) are excluded from the Brinson universe and reported.
_SECTOR_ETFS = {
    "semiconductors": "XLK", "ai_tech": "XLK", "cloud": "XLK", "quantum": "XLK",
    "cybersecurity": "CIBR", "fintech": "XLF", "financials": "XLF",
    "insurance": "KIE", "energy": "XLE", "clean_energy": "ICLN",
    "ev_auto": "XLY", "consumer": "XLY", "staples": "XLP", "biotech": "XBI",
    "healthcare": "XLV", "robotics": "XLI", "industrials": "XLI",
    "defense": "ITA", "transportation": "IYT", "comms": "XLC", "telecom": "XLC",
    "real_estate": "XLRE", "materials": "XLB", "metals_mining": "XME",
    "utilities": "XLU",
}

# Real SPDR/industry ETF per GICS top-level sector — used to source REAL
# within-sector benchmark returns when a single ETF benchmark is chosen.
_GICS_ETF = {
    "technology": "XLK", "financial_services": "XLF", "healthcare": "XLV",
    "consumer_cyclical": "XLY", "consumer_defensive": "XLP", "energy": "XLE",
    "industrials": "XLI", "basic_materials": "XLB", "real_estate": "XLRE",
    "utilities": "XLU", "communication_services": "XLC",
}

# Granular universe sector keys → GICS top level, so a book's holdings can be
# bucketed into the same sector space an ETF reports its real weights in.
_GRANULAR_TO_GICS = {
    "semiconductors": "technology", "ai_tech": "technology", "cloud": "technology",
    "quantum": "technology", "cybersecurity": "technology",
    "fintech": "financial_services", "financials": "financial_services",
    "insurance": "financial_services",
    "energy": "energy", "clean_energy": "energy",
    "ev_auto": "consumer_cyclical", "consumer": "consumer_cyclical",
    "staples": "consumer_defensive",
    "biotech": "healthcare", "healthcare": "healthcare",
    "robotics": "industrials", "industrials": "industrials",
    "defense": "industrials", "transportation": "industrials",
    "comms": "communication_services", "telecom": "communication_services",
    "real_estate": "real_estate",
    "materials": "basic_materials", "metals_mining": "basic_materials",
    "utilities": "utilities",
}

# yfinance funds_data keys → our canonical GICS keys.
_YF_SECTOR_CANON = {"realestate": "real_estate"}

_GICS_LABELS = {
    "technology": "Technology", "financial_services": "Financial Services",
    "healthcare": "Health Care", "consumer_cyclical": "Consumer Discretionary",
    "consumer_defensive": "Consumer Staples", "energy": "Energy",
    "industrials": "Industrials", "basic_materials": "Materials",
    "real_estate": "Real Estate", "utilities": "Utilities",
    "communication_services": "Communication Services",
}

# Process-local TTL cache so repeated attribution panels in one session don't
# re-hit the network for the same instrument.
_BENCH_CACHE: Dict[str, dict] = {}
_BENCH_TTL = 900.0

# ETF sector compositions change slowly, so cache the (network) lookup for a day.
_ETF_SECTORW_CACHE: Dict[str, Optional[dict]] = {}
_ETF_SECTORW_TS: Dict[str, float] = {}
_ETF_SECTORW_TTL = 86400.0


def _etf_sector_weights(ticker: str) -> Optional[dict]:
    """REAL GICS sector weights for an ETF, or None when not sourceable.

    Pulls the fund's actual sector allocation from Yahoo (yfinance funds_data)
    and canonicalizes it to our GICS keys. Returns ``None`` for instruments
    with no real fund composition (e.g. single stocks) or when the lookup
    fails/rate-limits — the caller then falls back to the diversified sector-ETF
    proxy and reports it. Never fabricates weights.
    """
    import time as _time

    t = (ticker or "").upper().strip().lstrip("$")
    if not t:
        return None
    now = _time.time()
    if t in _ETF_SECTORW_CACHE and now - _ETF_SECTORW_TS.get(t, 0.0) < _ETF_SECTORW_TTL:
        return _ETF_SECTORW_CACHE[t]

    val: Optional[dict] = None
    try:
        import yfinance as yf  # heavy import; only when an ETF benchmark is picked

        raw = yf.Ticker(t).funds_data.sector_weightings or {}
        canon: Dict[str, float] = {}
        for k, v in raw.items():
            key = _YF_SECTOR_CANON.get(str(k), str(k))
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv > 0:
                canon[key] = canon.get(key, 0.0) + fv
        # A real, fully-classified ETF sums to ~1.0; reject thin/garbage payloads.
        if canon and sum(canon.values()) > 0.5:
            val = canon
    except Exception as exc:  # noqa: BLE001
        log.warning("ETF sector weightings unavailable for %s: %s", t, exc)

    _ETF_SECTORW_CACHE[t] = val
    _ETF_SECTORW_TS[t] = now
    return val


def _resolve_benchmark(params: dict) -> tuple:
    """Resolve a REAL benchmark ticker + display name from params.

    Accepts an explicit ``benchmark`` ticker. Known broad/sector ETFs get a
    friendly display name. Any other ticker the user picks is honored ONLY if a
    real price series can be sourced for it (it is then shown by its own
    ticker); otherwise we fall back to the default rather than benchmarking
    against anything for which no real series exists.
    """
    raw = str(params.get("benchmark") or "").upper().strip().lstrip("$")
    if not raw:
        return _DEFAULT_BENCHMARK, _BENCHMARK_ETFS[_DEFAULT_BENCHMARK]
    if raw in _BENCHMARK_ETFS:
        return raw, _BENCHMARK_ETFS[raw]
    rng = (params.get("range") or "3M").upper()
    if _benchmark_closes(raw, rng):
        return raw, raw
    return _DEFAULT_BENCHMARK, _BENCHMARK_ETFS[_DEFAULT_BENCHMARK]


def _resolve_bench_constituents(params: dict) -> tuple:
    """Real, de-duplicated constituent tickers for a custom-basket benchmark.

    Returns ``(kept, dropped)`` where ``kept`` are symbols that exist in the
    tracked universe and ``dropped`` are requested tickers that are not real /
    not tracked (reported to the user rather than silently discarded). Both are
    empty when no explicit basket was requested.
    """
    raw = params.get("benchmark_constituents") or []
    if not isinstance(raw, list):
        return [], []
    out: List[str] = []
    dropped: List[str] = []
    seen = set()
    for s in raw:
        u = str(s).upper().strip().lstrip("$")
        if not u or u in seen:
            continue
        seen.add(u)
        if repo.get_company(u):
            out.append(u)
        else:
            dropped.append(u)
    return out, dropped


def _benchmark_closes(ticker: str, rng: str = "3M") -> Optional[dict]:
    """Real daily closes for a benchmark instrument, keyed by ISO date.

    The fetch window is sized to the requested range (``rng``) so 1Y / YTD stats
    are computed over the full window rather than a truncated 6mo series. Prefers
    real OHLCV already in the DB; otherwise fetches the real Yahoo chart
    synchronously and queues the symbol for the data worker to cache. Returns
    ``{"closes": {date: close}, "source": "live", "asOf": iso|None}`` or None if
    no real series could be sourced (the caller then reports it honestly).
    """
    import time as _time

    t = (ticker or "").upper()
    rng = (rng or "3M").upper()
    win = RANGE_DAYS.get(rng, 90)
    db_days = max(400, win * 2 + 40)
    period = _BENCH_PERIOD.get(rng, "6mo")
    now = _time.time()
    key = f"{t}|{rng}"
    hit = _BENCH_CACHE.get(key)
    if hit and now - hit["ts"] < _BENCH_TTL:
        return hit["val"]

    val: Optional[dict] = None
    try:
        meta = repo.price_series_meta(t, days=db_days)
        if meta.get("source") == "live":
            closes = {
                str(p["t"])[:10]: float(p["c"])
                for p in (meta.get("points") or [])
                if p.get("c") is not None
            }
            if len(closes) >= 2:
                val = {"closes": closes, "source": "live", "asOf": meta.get("asOf")}
    except Exception as exc:  # noqa: BLE001
        log.warning("benchmark DB read failed for %s: %s", t, exc)

    if val is None:
        try:
            res = p_src.fetch_price_history(t, period, "1d")
            closes = {
                str(p["d"])[:10]: float(p["c"])
                for p in (res.get("points") or [])
                if p.get("c") is not None
            }
            if len(closes) >= 2:
                val = {"closes": closes, "source": "live", "asOf": None}
                try:
                    repo.note_symbol(t)
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            log.warning("benchmark live fetch failed for %s: %s", t, exc)

    _BENCH_CACHE[key] = {"ts": now, "val": val}
    return val


def _basket_benchmark(
    cons: List[str],
    params: dict,
    model: "factor_model.RiskModel",
    rets,
    wp_raw: Dict[str, float],
    rp_num: Dict[str, float],
    secs_all: List[str],
    caps_all,
    cum_all,
    source: str,
    dropped_pre: Optional[List[str]] = None,
) -> Optional[dict]:
    """Construct a REAL custom-basket benchmark from explicit constituents.

    The basket's daily series, sector weights and sector returns all come
    straight from the same real, date-aligned return panel used for the book, so
    nothing is imputed. Constituents the risk model could not cover (and any that
    were not real/tracked, ``dropped_pre``) are dropped and reported. Sector
    weights are the constituents' own weights; within-sector returns are
    cap-weighted real returns. Returns ``None`` when no constituent could be
    modeled (the caller then falls back to the default ETF benchmark).
    """
    import numpy as np

    pos = {s: i for i, s in enumerate(model.symbols)}
    idxs: List[int] = []
    kept: List[str] = []
    dropped: List[str] = list(dropped_pre or [])
    for s in cons:
        if s in pos:
            idxs.append(pos[s])
            kept.append(s)
        else:
            dropped.append(s)
    if not idxs:
        return None

    # Weights: honor an aligned ``benchmark_weights`` list, else cap-weight the
    # kept constituents (equal-weight only if no caps are available).
    raw_w = params.get("benchmark_weights")
    bw = None
    if isinstance(raw_w, list) and len(raw_w) == len(cons):
        wmap = {str(c).upper().strip().lstrip("$"): float(x) for c, x in zip(cons, raw_w)}
        vals = np.array([abs(wmap.get(s, 0.0)) for s in kept], dtype=float)
        if vals.sum() > 0:
            bw = vals / vals.sum()
    if bw is None:
        caps = np.array([max(float(caps_all[i]), 0.0) for i in idxs], dtype=float)
        bw = caps / caps.sum() if caps.sum() > 0 else np.full(len(idxs), 1.0 / len(idxs))

    bench = engine.book_returns(rets[:, idxs], bw)  # real daily series, date-aligned

    # Brinson benchmark side from the basket's own sectors.
    sec_w: Dict[str, float] = {}
    sec_num: Dict[str, float] = {}
    sec_cap: Dict[str, float] = {}
    for kk, i in enumerate(idxs):
        sec = secs_all[i]
        sec_w[sec] = sec_w.get(sec, 0.0) + float(bw[kk])
        c = max(float(caps_all[i]), 0.0) or 1.0
        sec_num[sec] = sec_num.get(sec, 0.0) + c * float(cum_all[i])
        sec_cap[sec] = sec_cap.get(sec, 0.0) + c

    rb: Dict[str, float] = {}
    wb_raw: Dict[str, float] = {}
    excluded_sectors: List[str] = []
    for sec in wp_raw:
        if sec in sec_w and sec_cap.get(sec, 0.0) > 0:
            rb[sec] = sec_num[sec] / sec_cap[sec]
            wb_raw[sec] = sec_w[sec]
        else:
            # A book sector the chosen basket does not span — can't attribute it
            # against this benchmark, so exclude & report rather than impute.
            excluded_sectors.append(sec)

    n = len(kept)
    name = params.get("benchmark_name") or f"Custom basket · {n} name{'s' if n != 1 else ''}"
    return {
        "bench": bench,
        "name": name,
        "ticker": None,
        "source": source,
        "asOf": None,
        "missing": 0,
        "rb": rb,
        "wb_raw": wb_raw,
        "wp_raw": wp_raw,
        "rp_num": rp_num,
        "sector_etf": {},
        "excluded_sectors": excluded_sectors,
        "brinsonName": f"{name} (cap-weighted constituents)",
        "constituents": kept,
        "droppedConstituents": dropped,
        "kind": "basket",
    }


def _build_benchmark(
    params: dict,
    model: "factor_model.RiskModel",
    rets,
    dates: List[str],
    rng: str,
    idx: List[int],
    w,
    wp_raw: Dict[str, float],
    rp_num: Dict[str, float],
    secs_all: List[str],
    caps_all,
    cum_all,
    source: str,
) -> dict:
    """Resolve and construct the chosen benchmark for the attribution spine.

    Supports two user-selectable specs, both REAL:
      * an explicit list of real constituent tickers (``benchmark_constituents``)
        — a real, cap- or user-weighted basket; or
      * a single real traded ETF ticker (``benchmark``; default SPY). When the
        ETF's REAL sector composition can be sourced, Brinson is decomposed at
        GICS level using that ETF's own sector weights × real sector-ETF returns
        (so the chosen ETF actually drives the math). When it cannot be sourced,
        we fall back to a diversified sector-ETF proxy and say so.
    Returns the headline daily series plus everything the Brinson decomposition
    needs (sector weights/returns, the portfolio side in the matching sector
    space, excluded sectors). Nothing synthetic.
    """
    import numpy as np

    cons, dropped_pre = _resolve_bench_constituents(params)
    if cons:
        basket = _basket_benchmark(
            cons, params, model, rets, wp_raw, rp_num, secs_all, caps_all,
            cum_all, source, dropped_pre=dropped_pre,
        )
        if basket is not None:
            return basket
        # No constituent could be modeled — fall through to the ETF default but
        # still report every requested basket ticker as dropped.
        dropped_pre = list(dropped_pre) + list(cons)

    bench_ticker, bench_name = _resolve_benchmark(params)
    bser = _benchmark_closes(bench_ticker, rng)
    if not bser:
        raise ValueError(
            f"benchmark {bench_ticker} unavailable — no real price series could be sourced"
        )
    bench, bench_missing = engine.align_benchmark_returns(bser["closes"], dates)

    base = {
        "bench": bench,
        "name": bench_name,
        "ticker": bench_ticker,
        "source": bser["source"],
        "asOf": bser.get("asOf"),
        "missing": int(bench_missing),
        "constituents": None,
        "droppedConstituents": list(dropped_pre),
        "kind": "etf",
    }

    # Preferred path: the chosen ETF's OWN real sector weights drive Brinson.
    etf_w = _etf_sector_weights(bench_ticker)
    if etf_w:
        # Re-bucket the book into the GICS space the ETF reports its weights in.
        g_wp_raw: Dict[str, float] = {}
        g_rp_num: Dict[str, float] = {}
        for kk, i in enumerate(idx):
            g = _GRANULAR_TO_GICS.get(secs_all[i], "other")
            g_wp_raw[g] = g_wp_raw.get(g, 0.0) + float(w[kk])
            g_rp_num[g] = g_rp_num.get(g, 0.0) + float(w[kk]) * float(cum_all[i])

        rb: Dict[str, float] = {}
        wb_raw: Dict[str, float] = {}
        sector_etf: Dict[str, str] = {}
        excluded_sectors: List[str] = []
        for sec in g_wp_raw:
            etf = _GICS_ETF.get(sec)
            ser = _benchmark_closes(etf, rng) if etf else None
            if not ser:
                excluded_sectors.append(sec)
                continue
            arr, _ = engine.align_benchmark_returns(ser["closes"], dates)
            rb[sec] = float(np.prod(1.0 + arr) - 1.0)
            wb_raw[sec] = float(etf_w.get(sec, 0.0))  # the ETF's REAL weight
            sector_etf[sec] = etf

        base.update({
            "rb": rb,
            "wb_raw": wb_raw,
            "wp_raw": g_wp_raw,
            "rp_num": g_rp_num,
            "sector_etf": sector_etf,
            "excluded_sectors": excluded_sectors,
            "brinsonName": f"{bench_name} — its real sector weights × sector-ETF returns",
        })
        return base

    # Fallback: the ETF's real sector mix could not be sourced. Use a diversified
    # sector-ETF proxy (one real ETF per sector, universe cap-weighted) and say
    # so, rather than pretending the chosen ETF drove the sector weights.
    bench_cap: Dict[str, float] = {}
    for j in range(len(model.symbols)):
        bench_cap[secs_all[j]] = bench_cap.get(secs_all[j], 0.0) + float(caps_all[j])

    rb = {}
    wb_raw = {}
    sector_etf = {}
    excluded_sectors = []
    for sec in wp_raw:
        etf = _SECTOR_ETFS.get(sec)
        ser = _benchmark_closes(etf, rng) if etf else None
        if not ser:
            excluded_sectors.append(sec)
            continue
        arr, _ = engine.align_benchmark_returns(ser["closes"], dates)
        rb[sec] = float(np.prod(1.0 + arr) - 1.0)
        wb_raw[sec] = bench_cap.get(sec, 0.0)
        sector_etf[sec] = etf

    base.update({
        "rb": rb,
        "wb_raw": wb_raw,
        "wp_raw": wp_raw,
        "rp_num": rp_num,
        "sector_etf": sector_etf,
        "excluded_sectors": excluded_sectors,
        "brinsonName": f"Diversified sector-ETF proxy ({bench_name} sector weights unavailable)",
    })
    return base


def _compute_attribution(params: dict) -> dict:
    """Shared spine for the performance & factor attribution panels.

    Builds the real factor model over the book's estimation universe, slices a
    window off the aligned real-return panel, and computes (1) P&L vs a REAL
    traded benchmark ETF (default SPY, date-aligned), (2) single-period Brinson
    sector attribution against a sector-aware real benchmark (each sector mapped
    to a real traded sector/industry ETF), and (3) a linear factor decomposition
    of the realized return. Every number is real or excluded — no imputation.
    """
    import numpy as np

    name, syms, ws = _resolve_portfolio(params)
    res = factor_model.build(syms)
    model = res.model
    idx, w, dropped = factor_model.portfolio_indices(res, syms, ws)

    rng = (params.get("range") or "3M").upper()
    win = RANGE_DAYS.get(rng, 90)
    total_days = res.returns.shape[0]
    k = int(min(total_days, max(20, win)))
    rets = res.returns[-k:]                  # (k, N) real daily returns
    dates = list(res.dates[-k:])
    fret = model.factor_returns[-k:]         # (k, K) real factor returns

    # Book daily return series over the window.
    book = engine.book_returns(rets[:, idx], w)

    # Single-period portfolio sector returns over the window (real per-stock).
    cum_all = np.prod(1.0 + rets, axis=0) - 1.0  # (N,)
    secs_all = [(data.get_company(s) or {}).get("sector") or "Other" for s in model.symbols]
    caps_all = np.array(
        [float((data.get_company(s) or {}).get("marketCap") or 0.0) for s in model.symbols],
        dtype=float,
    )

    # Portfolio side: weight & real return by the book's sectors.
    wp_raw: Dict[str, float] = {}
    rp_num: Dict[str, float] = {}
    for kk, i in enumerate(idx):
        sec = secs_all[i]
        wp_raw[sec] = wp_raw.get(sec, 0.0) + float(w[kk])
        rp_num[sec] = rp_num.get(sec, 0.0) + float(w[kk]) * float(cum_all[i])

    # Chosen benchmark (user-selectable): a custom real basket OR a real traded
    # ETF (default SPY). This yields the headline daily series and the Brinson
    # benchmark sector side (weights/returns). Every number is real or excluded.
    bm = _build_benchmark(
        params, model, rets, dates, rng, idx, w, wp_raw, rp_num, secs_all,
        caps_all, cum_all, res.coverage.source,
    )
    bench = bm["bench"]
    bench_name = bm["name"]
    bench_ticker = bm["ticker"]
    bench_missing = bm["missing"]
    rb = bm["rb"]
    wb_raw = bm["wb_raw"]
    sector_etf = bm["sector_etf"]
    excluded_sectors = bm["excluded_sectors"]
    # The benchmark builder may re-bucket the book into the benchmark's sector
    # space (e.g. GICS for an ETF whose real weights drove the math), so use the
    # portfolio side it returns to keep both sides in the same buckets.
    wp_raw = bm["wp_raw"]
    rp_num = bm["rp_num"]

    # Cumulative equity curves + drawdown for the chart (length k, date-aligned).
    book_eq = engine.attribution.equity_curve(book)[1:]
    bench_eq = engine.attribution.equity_curve(bench)[1:]
    peak = np.maximum.accumulate(book_eq)
    dd = book_eq / np.where(peak == 0, np.nan, peak) - 1.0
    series = [
        {
            "date": dates[i],
            "book": round(float(book_eq[i] / 100.0 - 1.0) * 100.0, 2),
            "bench": round(float(bench_eq[i] / 100.0 - 1.0) * 100.0, 2),
            "drawdown": round(float(dd[i]) * 100.0 if np.isfinite(dd[i]) else 0.0, 2),
        }
        for i in range(len(dates))
    ]

    included = [s for s in wp_raw if s in rb]
    # Renormalize portfolio & benchmark weights over the comparable (real-ETF-
    # backed) sectors so the Brinson identity holds within that universe.
    wp_sum = sum(wp_raw[s] for s in included) or 1.0
    wb_sum = sum(wb_raw.get(s, 0.0) for s in included) or 1.0
    wp = {s: wp_raw[s] / wp_sum for s in included}
    wb = {s: (wb_raw.get(s, 0.0) / wb_sum) for s in included}
    rp = {s: (rp_num[s] / wp_raw[s] if wp_raw[s] else 0.0) for s in included}

    sectors = sorted(included, key=lambda s: -wb.get(s, 0.0))
    sector_labels = {s: (_GICS_LABELS.get(s) or repo.sector_name(s)) for s in sectors}
    brinson = engine.brinson(sectors, wp, wb, rp, {s: rb[s] for s in sectors})
    brinson["benchmarkName"] = bm["brinsonName"]
    if excluded_sectors:
        brinson["excludedSectors"] = [
            (_GICS_LABELS.get(s) or repo.sector_name(s)) for s in excluded_sectors
        ]
    for row in brinson["rows"]:
        row["sectorLabel"] = sector_labels.get(row["sector"], row["sector"])
        row["benchmarkEtf"] = sector_etf.get(row["sector"])

    # Linear factor decomposition of the realized book return.
    b_exp = model.exposures[idx].T @ w  # (K,)
    factor = engine.factor_attribution(b_exp, fret, model.factor_names, book)

    return {
        "portfolioName": name,
        "benchmarkName": bench_name,
        "benchmarkTicker": bench_ticker,
        "benchmarkKind": bm["kind"],
        "benchmarkConstituents": bm.get("constituents"),
        "benchmarkDroppedConstituents": bm.get("droppedConstituents") or [],
        "benchmarkSource": bm["source"],
        "benchmarkAsOf": bm["asOf"],
        "benchmarkMissingDays": int(bench_missing),
        "range": rng,
        "rangeLabel": _ATTR_RANGE_LABELS.get(rng, rng),
        "windowDays": int(k),
        "series": series,
        "pnl": engine.pnl_summary(book, bench),
        "brinson": brinson,
        "factor": factor,
        "coverage": _coverage_payload(res, dropped),
        "asOf": res.coverage.as_of,
        "source": res.coverage.source,
    }


def build_performance_pnl(params: dict) -> dict:
    """Book P&L over a window vs a real benchmark: cumulative & periodic returns,
    a drawdown track, and the full risk/return + active stat block (return, vol,
    Sharpe, max drawdown, hit rate, tracking error, information ratio, beta,
    alpha, capture). Real returns only; excluded names reported."""
    a = _compute_attribution(params)
    return {
        "portfolioName": a["portfolioName"],
        "benchmarkName": a["benchmarkName"],
        "benchmarkTicker": a["benchmarkTicker"],
        "benchmarkKind": a["benchmarkKind"],
        "benchmarkConstituents": a["benchmarkConstituents"],
        "benchmarkDroppedConstituents": a["benchmarkDroppedConstituents"],
        "benchmarkSource": a["benchmarkSource"],
        "benchmarkAsOf": a["benchmarkAsOf"],
        "benchmarkMissingDays": a["benchmarkMissingDays"],
        "range": a["range"],
        "rangeLabel": a["rangeLabel"],
        "windowDays": a["windowDays"],
        "series": a["series"],
        "stats": a["pnl"],
        "coverage": a["coverage"],
        "asOf": a["asOf"],
        "source": a["source"],
    }


def build_brinson_attribution(params: dict) -> dict:
    """Brinson allocation / selection / interaction attribution by sector vs a
    sector-aware real benchmark (each sector mapped to a real traded sector/
    industry ETF). The three effects sum exactly to the book's active return.
    Real sector returns; excluded names and unmapped sectors reported."""
    a = _compute_attribution(params)
    return {
        "portfolioName": a["portfolioName"],
        "benchmarkName": a["brinson"].get("benchmarkName", a["benchmarkName"]),
        "range": a["range"],
        "rangeLabel": a["rangeLabel"],
        "windowDays": a["windowDays"],
        "rows": a["brinson"]["rows"],
        "totals": a["brinson"]["totals"],
        "excludedSectors": a["brinson"].get("excludedSectors", []),
        "coverage": a["coverage"],
        "asOf": a["asOf"],
        "source": a["source"],
    }


def build_factor_attribution(params: dict) -> dict:
    """Decompose the book's realized window return into per-factor contributions
    (exposure × realized factor return) plus a specific (idiosyncratic) return
    using the real multi-factor risk model. Contributions + specific reconstruct
    the realized return exactly."""
    a = _compute_attribution(params)
    return {
        "portfolioName": a["portfolioName"],
        "range": a["range"],
        "rangeLabel": a["rangeLabel"],
        "windowDays": a["windowDays"],
        "rows": a["factor"]["rows"],
        "realizedReturn": a["factor"]["realizedReturn"],
        "factorReturn": a["factor"]["factorReturn"],
        "specificReturn": a["factor"]["specificReturn"],
        "coverage": a["coverage"],
        "asOf": a["asOf"],
        "source": a["source"],
    }


def build_tear_sheet(params: dict) -> dict:
    """One report-style view combining P&L vs a real benchmark, drawdowns,
    Brinson sector attribution and factor attribution for a book over a window.
    Wires the three attribution lenses into a single panel for narration."""
    a = _compute_attribution(params)
    return {
        "portfolioName": a["portfolioName"],
        "benchmarkName": a["benchmarkName"],
        "benchmarkTicker": a["benchmarkTicker"],
        "benchmarkKind": a["benchmarkKind"],
        "benchmarkConstituents": a["benchmarkConstituents"],
        "benchmarkDroppedConstituents": a["benchmarkDroppedConstituents"],
        "benchmarkSource": a["benchmarkSource"],
        "benchmarkAsOf": a["benchmarkAsOf"],
        "benchmarkMissingDays": a["benchmarkMissingDays"],
        "range": a["range"],
        "rangeLabel": a["rangeLabel"],
        "windowDays": a["windowDays"],
        "series": a["series"],
        "stats": a["pnl"],
        "brinson": a["brinson"],
        "factor": a["factor"],
        "coverage": a["coverage"],
        "asOf": a["asOf"],
        "source": a["source"],
    }


def build_portfolio_optimizer(params: dict) -> dict:
    """Construct an optimal portfolio from real expected returns + covariance.

    Expected returns are factor-model-implied (exposures × realized factor
    premia) and the covariance comes from the multi-factor risk model — both
    estimated from real data. Supports mean-variance (min-var / max-Sharpe /
    target-vol), Black-Litterman, risk parity and HRP, under long-only/short,
    max-position, sector-cap, gross/net and turnover constraints. Names without
    enough history or fundamentals are excluded and reported in the coverage
    block rather than fabricated.
    """
    from . import portfolio

    payload, res, dropped = portfolio.optimize(params)
    payload["coverage"] = _coverage_payload(res, dropped)
    payload["asOf"] = res.coverage.as_of
    payload["source"] = res.coverage.source
    return payload


# ----------------------------- alpha signal research -----------------------------
# How much history to pull per name for cross-sectional signal evaluation. Live
# names return what the DB has (~6 months of trading days); breadth (mock) names
# return the deterministic calendar series. The signal engine excludes any name
# that lacks enough history at each date — no imputation.
_SIGNAL_DAYS = 400
_SIGNAL_HORIZONS = (1, 5, 10, 21, 42)
_SIGNAL_HOLDING = 21
_SIGNAL_QUANTILES = 5
_SIGNAL_UNIVERSE_CAP = 40
_DEFAULT_SCORECARD_SIGNALS = ["momentum", "short_reversal", "low_volatility", "value", "quality"]


def _resolve_signal_universe(params: dict) -> tuple:
    """Resolve (symbols, label) for the cross-section from explicit names, a
    sector, or a default liquid core. Capped so the bulk fetch stays cheap."""
    raw_syms = params.get("symbols") or []
    syms = [s.upper() for s in raw_syms if repo.get_company(s.upper())]
    if syms:
        label = f"{len(syms)} selected names"
        return syms[:_SIGNAL_UNIVERSE_CAP], label

    sector = params.get("sector")
    sid = repo.resolve_sector(sector) if sector else None
    if sid:
        syms = repo.symbols_in_sector(sid)
        if len(syms) >= _SIGNAL_QUANTILES:
            return syms[:_SIGNAL_UNIVERSE_CAP], repo.sector_name(sid)

    # Default: a broad, liquid cross-section of the universe.
    syms = repo.all_symbols()[:_SIGNAL_UNIVERSE_CAP]
    return syms, "US large-cap universe"


def _signal_ctx(signal: str, companies: Dict[str, dict]) -> tuple:
    """Build per-symbol context for a signal plus a list of names to exclude up
    front because the required fundamental field is genuinely missing.

    Price signals need no context. Fundamental signals derive a single
    cross-sectional value per name (never imputed): value uses earnings yield
    (1 / P·E), quality uses net margin. Names lacking the field are reported.
    """
    meta = engine.SIGNAL_META.get(signal, {})
    if meta.get("kind") != "fundamental":
        return {}, []

    ctx: Dict[str, dict] = {}
    excluded: List[dict] = []
    for sym, c in companies.items():
        fval = None
        reason = ""
        if signal == "value":
            pe = c.get("peRatio")
            if pe is not None and pe > 0:
                fval = 1.0 / float(pe)
            else:
                reason = "missing P/E (earnings yield)"
        elif signal == "quality":
            nm = c.get("netMargin")
            if nm is not None and nm != 0.0:
                fval = float(nm)
            else:
                reason = "missing net margin"
        if fval is None:
            excluded.append({"symbol": sym, "reason": reason or "missing fundamental"})
        else:
            ctx[sym] = {"fval": fval}
    return ctx, excluded


def build_signal_research(params: dict) -> dict:
    """Evaluate one cross-sectional alpha signal over a real universe.

    Computes rank IC (with IC decay across horizons), turnover and a long-short
    quantile spread equity curve from the actual price/fundamental series. Names
    missing data are excluded from the cross-section and reported, never imputed.
    """
    signal = engine.normalize_signal(params.get("signal") or "momentum")
    meta = engine.SIGNAL_META.get(signal, {})
    symbols, universe_label = _resolve_signal_universe(params)
    if len(symbols) < _SIGNAL_QUANTILES:
        raise ValueError("need a broader universe to evaluate a cross-sectional signal")

    bulk = repo.price_closes_bulk(symbols, days=_SIGNAL_DAYS)
    series = bulk["series"]
    companies = repo.companies_bulk(symbols) if meta.get("kind") == "fundamental" else {}
    ctx_by_symbol, pre_excluded = _signal_ctx(signal, companies)

    # Drop names the fundamental field is missing for before evaluation.
    excluded_syms = {e["symbol"] for e in pre_excluded}
    eval_series = {s: pts for s, pts in series.items() if s not in excluded_syms}

    result = engine.evaluate_signal(
        eval_series,
        signal=signal,
        ctx_by_symbol=ctx_by_symbol,
        horizons=_SIGNAL_HORIZONS,
        holding=_SIGNAL_HOLDING,
        quantiles=_SIGNAL_QUANTILES,
    )

    excluded_all = pre_excluded + list(result.get("excluded") or [])
    if len(result.get("included") or []) < _SIGNAL_QUANTILES:
        raise ValueError("not enough names with usable history for this signal")

    return {
        "signal": signal,
        "label": result["label"],
        "description": meta.get("desc", ""),
        "universe": universe_label,
        "universeSize": len(symbols),
        "included": len(result["included"]),
        "excluded": len(excluded_all),
        "excludedNames": excluded_all[:30],
        "horizons": result["horizons"],
        "primaryHorizon": result["primaryHorizon"],
        "holding": result["holding"],
        "quantiles": result["quantiles"],
        "ic": result["ic"],
        "decay": result["decay"],
        "turnover": result["turnover"],
        "turnoverAnnual": result["turnoverAnnual"],
        "rebalances": result["rebalances"],
        "quantileReturns": result["quantileReturns"],
        "spread": result["spread"],
        "spreadStats": result["spreadStats"],
        "asOf": bulk.get("asOf"),
        "source": bulk.get("source", "mock"),
    }


def _downsample(values: List[float], n: int = 24) -> List[float]:
    if len(values) <= n:
        return [round(float(v), 2) for v in values]
    step = len(values) / n
    return [round(float(values[min(len(values) - 1, int(i * step))]), 2) for i in range(n)]


def build_signal_scorecard(params: dict) -> dict:
    """Compare several alpha signals head-to-head over one shared universe.

    Each signal is evaluated on the same names and ranked by IC information ratio
    (mean IC / IC volatility), with mean IC, t-stat, hit rate, turnover and the
    long-short spread performance shown alongside a spread sparkline.
    """
    requested = params.get("signals") or []
    signals = []
    for s in requested:
        key = engine.normalize_signal(s)
        if key not in signals:
            signals.append(key)
    if not signals:
        signals = list(_DEFAULT_SCORECARD_SIGNALS)

    symbols, universe_label = _resolve_signal_universe(params)
    if len(symbols) < _SIGNAL_QUANTILES:
        raise ValueError("need a broader universe to compare signals")

    bulk = repo.price_closes_bulk(symbols, days=_SIGNAL_DAYS)
    series = bulk["series"]
    need_fundamentals = any(engine.SIGNAL_META.get(s, {}).get("kind") == "fundamental" for s in signals)
    companies = repo.companies_bulk(symbols) if need_fundamentals else {}

    rows = []
    for signal in signals:
        meta = engine.SIGNAL_META.get(signal, {})
        ctx_by_symbol, pre_excluded = _signal_ctx(signal, companies)
        excluded_syms = {e["symbol"] for e in pre_excluded}
        eval_series = {s: pts for s, pts in series.items() if s not in excluded_syms}
        result = engine.evaluate_signal(
            eval_series,
            signal=signal,
            ctx_by_symbol=ctx_by_symbol,
            horizons=_SIGNAL_HORIZONS,
            holding=_SIGNAL_HOLDING,
            quantiles=_SIGNAL_QUANTILES,
        )
        ic = result["ic"]
        rows.append({
            "signal": signal,
            "label": result["label"],
            "meanIC": ic["mean"],
            "icIR": ic["ir"],
            "tStat": ic["tStat"],
            "hitRate": ic["hitRate"],
            "turnover": result["turnover"],
            "spreadReturn": result["spreadStats"]["totalReturn"],
            "spreadSharpe": result["spreadStats"]["sharpe"],
            "included": len(result["included"]),
            "spark": _downsample([p["value"] for p in result["spread"]]),
        })

    rows.sort(key=lambda r: r["icIR"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1

    return {
        "universe": universe_label,
        "universeSize": len(symbols),
        "primaryHorizon": _SIGNAL_HOLDING,
        "holding": _SIGNAL_HOLDING,
        "quantiles": _SIGNAL_QUANTILES,
        "rows": rows,
        "asOf": bulk.get("asOf"),
        "source": bulk.get("source", "mock"),
    }


# ----------------------------- supply chain builder -----------------------------
_SUPPLY_CHAIN_DB: dict = {
    "NVDA": {
        "suppliers": [
            {"name": "TSMC", "symbol": "TSM", "exposure": 100.0, "country": "TW", "category": "Foundry (sole source)"},
            {"name": "SK Hynix", "symbol": None, "exposure": 48.0, "country": "KR", "category": "HBM / DRAM"},
            {"name": "Samsung Elec.", "symbol": None, "exposure": 30.0, "country": "KR", "category": "DRAM / HBM"},
            {"name": "ASML", "symbol": "ASML", "exposure": 18.0, "country": "NL", "category": "Litho (via TSMC)"},
            {"name": "Foxconn", "symbol": None, "exposure": 12.0, "country": "TW", "category": "PCB Assembly"},
        ],
        "customers": [
            {"name": "Microsoft", "symbol": "MSFT", "exposure": 16.0, "country": "US", "category": "Azure AI Cloud"},
            {"name": "Amazon AWS", "symbol": "AMZN", "exposure": 14.0, "country": "US", "category": "AWS GPU Compute"},
            {"name": "Alphabet GCP", "symbol": "GOOGL", "exposure": 12.0, "country": "US", "category": "GCP / Gemini Infra"},
            {"name": "Meta AI", "symbol": "META", "exposure": 11.0, "country": "US", "category": "LLaMA / Ad Ranking"},
            {"name": "Other OEMs", "symbol": None, "exposure": 35.0, "country": "Global", "category": "Enterprise / OEM"},
        ],
    },
    "TSM": {
        "suppliers": [
            {"name": "ASML", "symbol": "ASML", "exposure": 85.0, "country": "NL", "category": "EUV Lithography"},
            {"name": "Applied Materials", "symbol": None, "exposure": 55.0, "country": "US", "category": "Etch / Deposition"},
            {"name": "Lam Research", "symbol": None, "exposure": 40.0, "country": "US", "category": "Etch / CVD"},
            {"name": "Tokyo Electron", "symbol": None, "exposure": 30.0, "country": "JP", "category": "Process Equipment"},
            {"name": "Air Liquide", "symbol": None, "exposure": 15.0, "country": "FR", "category": "Specialty Gases"},
        ],
        "customers": [
            {"name": "NVIDIA", "symbol": "NVDA", "exposure": 25.0, "country": "US", "category": "GPU / Accelerators"},
            {"name": "Apple", "symbol": None, "exposure": 22.0, "country": "US", "category": "A-series / M-series SoC"},
            {"name": "AMD", "symbol": "AMD", "exposure": 10.0, "country": "US", "category": "CPU / GPU"},
            {"name": "Qualcomm", "symbol": "QCOM", "exposure": 8.0, "country": "US", "category": "Snapdragon Mobile"},
            {"name": "Broadcom", "symbol": "AVGO", "exposure": 7.0, "country": "US", "category": "Networking ASICs"},
        ],
    },
    "MSFT": {
        "suppliers": [
            {"name": "NVIDIA", "symbol": "NVDA", "exposure": 60.0, "country": "US", "category": "AI Accelerators"},
            {"name": "AMD", "symbol": "AMD", "exposure": 20.0, "country": "US", "category": "EPYC Servers"},
            {"name": "Broadcom", "symbol": "AVGO", "exposure": 15.0, "country": "US", "category": "Network ASICs"},
            {"name": "Dell / HP", "symbol": None, "exposure": 10.0, "country": "US", "category": "Server Hardware"},
            {"name": "OpenAI", "symbol": None, "exposure": 8.0, "country": "US", "category": "Model IP Partner"},
        ],
        "customers": [
            {"name": "Enterprise Software", "symbol": None, "exposure": 45.0, "country": "Global", "category": "M365 / Teams / Copilot"},
            {"name": "Cloud (Azure)", "symbol": None, "exposure": 30.0, "country": "Global", "category": "IaaS / PaaS / AI API"},
            {"name": "Gaming (Xbox)", "symbol": None, "exposure": 12.0, "country": "Global", "category": "Console / Game Pass"},
            {"name": "LinkedIn", "symbol": None, "exposure": 8.0, "country": "Global", "category": "Professional Network"},
            {"name": "Surface / Devices", "symbol": None, "exposure": 5.0, "country": "Global", "category": "Consumer Hardware"},
        ],
    },
    "ASML": {
        "suppliers": [
            {"name": "Carl Zeiss", "symbol": None, "exposure": 70.0, "country": "DE", "category": "EUV Optics (exclusive)"},
            {"name": "Cymer (ASML sub)", "symbol": None, "exposure": 60.0, "country": "US", "category": "Light Source"},
            {"name": "Trumpf", "symbol": None, "exposure": 30.0, "country": "DE", "category": "CO2 Laser"},
            {"name": "VDL", "symbol": None, "exposure": 20.0, "country": "NL", "category": "Mechanical Assembly"},
            {"name": "Corning", "symbol": None, "exposure": 10.0, "country": "US", "category": "Specialty Glass"},
        ],
        "customers": [
            {"name": "TSMC", "symbol": "TSM", "exposure": 38.0, "country": "TW", "category": "Leading-Edge Foundry"},
            {"name": "Samsung Foundry", "symbol": None, "exposure": 28.0, "country": "KR", "category": "Advanced Logic"},
            {"name": "Intel Foundry", "symbol": "INTC", "exposure": 15.0, "country": "US", "category": "IFS 18A / 14A"},
            {"name": "Micron", "symbol": "MU", "exposure": 8.0, "country": "US", "category": "Advanced DRAM"},
            {"name": "Other IDMs", "symbol": None, "exposure": 11.0, "country": "Global", "category": "Mature Nodes"},
        ],
    },
    "AMD": {
        "suppliers": [
            {"name": "TSMC", "symbol": "TSM", "exposure": 95.0, "country": "TW", "category": "Foundry (primary)"},
            {"name": "SK Hynix", "symbol": None, "exposure": 35.0, "country": "KR", "category": "HBM / GDDR"},
            {"name": "ASML", "symbol": "ASML", "exposure": 15.0, "country": "NL", "category": "Litho (via TSMC)"},
            {"name": "Amkor", "symbol": None, "exposure": 20.0, "country": "KR", "category": "Packaging (CoWoS)"},
            {"name": "UMC", "symbol": None, "exposure": 10.0, "country": "TW", "category": "Mature Node Foundry"},
        ],
        "customers": [
            {"name": "Microsoft", "symbol": "MSFT", "exposure": 20.0, "country": "US", "category": "Xbox + Azure EPYC"},
            {"name": "Sony", "symbol": None, "exposure": 15.0, "country": "JP", "category": "PlayStation SoC"},
            {"name": "HP / Dell", "symbol": None, "exposure": 18.0, "country": "US", "category": "Client CPUs"},
            {"name": "Meta Platforms", "symbol": "META", "exposure": 10.0, "country": "US", "category": "AI Inference Chips"},
            {"name": "Cloud OEMs", "symbol": None, "exposure": 25.0, "country": "Global", "category": "EPYC Server CPUs"},
        ],
    },
}


# Geopolitical concentration risk per sourcing region (0.0 = stable, 1.0 = acute).
# Reflects supply-chain fragility from cross-strait tension, sanctions exposure,
# export controls and single-jurisdiction dependence.
_GEO_RISK: dict = {
    "TW": 0.95,   # Taiwan Strait / cross-strait tension
    "CN": 0.90,   # export controls, sanctions exposure
    "HK": 0.80,
    "RU": 0.95,   # sanctions
    "IL": 0.60,   # regional conflict
    "KR": 0.55,   # DPRK proximity
    "IN": 0.35,
    "JP": 0.25,
    "NL": 0.20,
    "DE": 0.20,
    "FR": 0.20,
    "IE": 0.15,
    "US": 0.10,
    "Global": 0.05,  # diversified / multi-region
}

_COUNTRY_NAME: dict = {
    "TW": "Taiwan",
    "CN": "China",
    "HK": "Hong Kong",
    "RU": "Russia",
    "IL": "Israel",
    "KR": "South Korea",
    "IN": "India",
    "JP": "Japan",
    "NL": "Netherlands",
    "DE": "Germany",
    "FR": "France",
    "IE": "Ireland",
    "US": "United States",
    "Global": "Global",
}

# Numeric risk-value thresholds -> ordinal label.
_RISK_BANDS: list = [
    (90.0, "Critical"),
    (55.0, "High"),
    (28.0, "Medium"),
    (0.0, "Low"),
]
_RISK_ORDER: dict = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


def _country_name(code: str) -> str:
    return _COUNTRY_NAME.get(code, code)


def _score_supply_node(exposure: float, country: str) -> dict:
    """Score one supplier/customer dependency for concentration + geopolitical risk.

    Combines how much the subject depends on the node (exposure) with how
    geopolitically fragile its sourcing region is. A 100% single-source
    dependency in Taiwan reads Critical; a diversified 10% buyer reads Low.
    """
    geo = _GEO_RISK.get(country, 0.40)
    single_source = exposure >= 90.0
    risk_value = exposure * (0.55 + 0.65 * geo)

    label = "Low"
    for threshold, name in _RISK_BANDS:
        if risk_value >= threshold:
            label = name
            break

    # Single-source dependencies are structurally fragile regardless of region:
    # floor them at High, and at Critical when the region is also sensitive.
    if single_source:
        floor = "Critical" if geo >= 0.70 else "High"
        if _RISK_ORDER[floor] > _RISK_ORDER[label]:
            label = floor

    return {
        "riskScore": label,
        "riskValue": round(risk_value, 1),
        "geoRisk": round(geo, 2),
        "singleSource": single_source,
    }


def _annotate_supply_chain_risk(result: dict) -> dict:
    """Attach per-node risk scores and a top-3 concentration risk summary."""
    nodes = result.get("nodes", [])
    table = result.get("table", [])

    for node in nodes:
        if node.get("role") == "subject":
            continue
        node.update(_score_supply_node(float(node.get("exposure", 0.0)), node.get("country", "")))
    for row in table:
        row.update(_score_supply_node(float(row.get("exposure", 0.0)), row.get("country", "")))

    # Country concentration on the supply side: share of total supplier exposure
    # sourced from each region. Highlights single-jurisdiction dependence.
    supplier_rows = [r for r in table if r.get("role") == "supplier"]
    total_supplier_exp = sum(float(r.get("exposure", 0.0)) for r in supplier_rows) or 1.0
    by_country: dict = {}
    for r in supplier_rows:
        c = r.get("country", "")
        by_country[c] = by_country.get(c, 0.0) + float(r.get("exposure", 0.0))
    country_concentration = [
        {
            "country": c,
            "countryName": _country_name(c),
            "sharePct": round(100.0 * exp / total_supplier_exp, 1),
            "geoRisk": round(_GEO_RISK.get(c, 0.40), 2),
        }
        for c, exp in by_country.items()
    ]
    country_concentration.sort(key=lambda x: x["sharePct"], reverse=True)

    # Build candidate risk items, then rank by severity for the summary bar.
    candidates: list = []
    for r in table:
        candidates.append({
            "kind": "node",
            "title": r.get("name", ""),
            "detail": f"{round(float(r.get('exposure', 0.0)))}% {r.get('category', r.get('role', ''))} · {_country_name(r.get('country', ''))}",
            "level": r.get("riskScore", "Low"),
            "riskValue": r.get("riskValue", 0.0),
        })
    # Add a region-concentration item for the dominant geopolitically-sensitive hub.
    for cc in country_concentration:
        if cc["sharePct"] >= 40.0 and cc["geoRisk"] >= 0.50:
            level = "Critical" if (cc["sharePct"] >= 60.0 and cc["geoRisk"] >= 0.70) else "High"
            candidates.append({
                "kind": "country",
                "title": f"{cc['countryName']} concentration",
                "detail": f"{cc['sharePct']:.0f}% of supplier exposure sourced from {cc['countryName']}",
                "level": level,
                "riskValue": cc["sharePct"] + cc["geoRisk"] * 50.0,
            })
            break

    candidates.sort(key=lambda x: (_RISK_ORDER.get(x["level"], 0), x["riskValue"]), reverse=True)
    top_risks = [c for c in candidates if _RISK_ORDER.get(c["level"], 0) >= _RISK_ORDER["Medium"]][:3]
    if not top_risks:
        top_risks = candidates[:3]

    counts = {"Low": 0, "Medium": 0, "High": 0, "Critical": 0}
    for node in nodes:
        if node.get("role") == "subject":
            continue
        counts[node.get("riskScore", "Low")] = counts.get(node.get("riskScore", "Low"), 0) + 1

    result["riskSummary"] = {
        "topRisks": top_risks,
        "countryConcentration": country_concentration[:5],
        "counts": counts,
    }
    return result


def _rng_next(seed: int) -> tuple[int, float]:
    seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
    return seed, seed / 0x7FFFFFFF


def _generate_supply_chain(symbol: str, company: dict) -> dict:
    """Generate a plausible supply chain for symbols not in the curated DB."""
    seed = data._seed(symbol)
    sector = company["sector"]

    suppliers_raw = []
    customers_raw = []

    if sector == "semiconductors":
        suppliers_raw = [
            ("TSMC", "TSM", "TW", "Foundry"),
            ("SK Hynix", None, "KR", "Memory"),
            ("Applied Materials", None, "US", "Fab Equipment"),
            ("Lam Research", None, "US", "Etch Tools"),
            ("Corning", None, "US", "Substrates"),
        ]
        customers_raw = [
            ("Enterprise OEM", None, "Global", "Server / Client"),
            ("Cloud Hyperscalers", None, "Global", "Data Center"),
            ("Mobile OEMs", None, "Global", "Mobile Devices"),
            ("Automotive Tier-1", None, "Global", "ADAS / EV"),
            ("Consumer Electronics", None, "Global", "Consumer"),
        ]
    elif sector == "energy":
        suppliers_raw = [
            ("Schlumberger", "SLB", "US", "Oilfield Services"),
            ("Baker Hughes", None, "US", "Well Services"),
            ("Halliburton", None, "US", "Drilling"),
            ("Caterpillar", None, "US", "Heavy Equipment"),
            ("Pipeline Partners", None, "Global", "Midstream"),
        ]
        customers_raw = [
            ("Refineries", None, "Global", "Crude Off-take"),
            ("LNG Terminals", None, "Global", "Natural Gas"),
            ("Utilities", None, "Global", "Power Generation"),
            ("Industrial Buyers", None, "Global", "Petrochemicals"),
            ("Export Markets", None, "Global", "International"),
        ]
    else:
        suppliers_raw = [
            ("AWS / Azure", None, "US", "Cloud Infra"),
            ("NVIDIA", "NVDA", "US", "AI Compute"),
            ("Accenture", None, "IE", "System Integration"),
            ("SAP", None, "DE", "Enterprise Software"),
            ("Telecom Providers", None, "Global", "Connectivity"),
        ]
        customers_raw = [
            ("Enterprise", None, "Global", "Software Licenses"),
            ("Government", None, "US", "Gov Contracts"),
            ("SMB", None, "Global", "SaaS"),
            ("Financial Services", None, "Global", "FinTech"),
            ("Healthcare", None, "Global", "Health IT"),
        ]

    nodes = [{"id": symbol, "name": company["name"], "symbol": symbol, "role": "subject", "exposure": 100.0, "country": "US"}]
    edges = []
    table = []

    for i, (name, sym, country, cat) in enumerate(suppliers_raw):
        seed, r = _rng_next(seed)
        exp = round(20.0 + r * 70.0, 1)
        nid = f"sup_{i}"
        nodes.append({"id": nid, "name": name, "symbol": sym, "role": "supplier", "exposure": exp, "country": country})
        edges.append({"source": nid, "target": symbol, "weight": exp})
        table.append({"name": name, "symbol": sym, "role": "supplier", "exposure": exp, "country": country, "category": cat})

    for i, (name, sym, country, cat) in enumerate(customers_raw):
        seed, r = _rng_next(seed)
        exp = round(5.0 + r * 40.0, 1)
        nid = f"cust_{i}"
        nodes.append({"id": nid, "name": name, "symbol": sym, "role": "customer", "exposure": exp, "country": country})
        edges.append({"source": symbol, "target": nid, "weight": exp})
        table.append({"name": name, "symbol": sym, "role": "customer", "exposure": exp, "country": country, "category": cat})

    return {"symbol": symbol, "name": company["name"], "nodes": nodes, "edges": edges, "table": table}


def build_supply_chain(params: dict) -> dict:
    symbol = (params.get("symbol") or "NVDA").upper()
    company = data.get_company(symbol)
    if not company:
        raise ValueError(f"Unknown symbol: {symbol}")

    if symbol in _SUPPLY_CHAIN_DB:
        db = _SUPPLY_CHAIN_DB[symbol]
        nodes = [{"id": symbol, "name": company["name"], "symbol": symbol, "role": "subject", "exposure": 100.0, "country": "US"}]
        edges = []
        table = []
        for i, s in enumerate(db["suppliers"]):
            nid = f"sup_{i}"
            nodes.append({"id": nid, "name": s["name"], "symbol": s.get("symbol"), "role": "supplier", "exposure": s["exposure"], "country": s["country"]})
            edges.append({"source": nid, "target": symbol, "weight": s["exposure"]})
            table.append({"name": s["name"], "symbol": s.get("symbol"), "role": "supplier", "exposure": s["exposure"], "country": s["country"], "category": s["category"]})
        for i, c in enumerate(db["customers"]):
            nid = f"cust_{i}"
            nodes.append({"id": nid, "name": c["name"], "symbol": c.get("symbol"), "role": "customer", "exposure": c["exposure"], "country": c["country"]})
            edges.append({"source": symbol, "target": nid, "weight": c["exposure"]})
            table.append({"name": c["name"], "symbol": c.get("symbol"), "role": "customer", "exposure": c["exposure"], "country": c["country"], "category": c["category"]})
        result = {"symbol": symbol, "name": company["name"], "nodes": nodes, "edges": edges, "table": table}
        return _annotate_supply_chain_risk(result)

    return _annotate_supply_chain_risk(_generate_supply_chain(symbol, company))


# ----------------------------- DCF builder -----------------------------
def _run_dcf(base_rev: float, shares: float, net_debt: float, assumptions: dict) -> tuple:
    """Return (projections, implied_price, sensitivity_grid)."""
    g = assumptions["revenueGrowth"] / 100.0
    margin = assumptions["ebitdaMargin"] / 100.0
    wacc = assumptions["wacc"] / 100.0
    exit_mult = assumptions["exitMultiple"]
    tax = assumptions["taxRate"] / 100.0
    capex_pct = assumptions["capexPct"] / 100.0

    projections = []
    rev = base_rev
    pv_sum = 0.0
    base_year = date.today().year
    for t in range(1, 6):
        rev = rev * (1 + g)
        ebitda = rev * margin
        nopat = ebitda * (1 - tax)
        capex = rev * capex_pct
        fcf = nopat - capex
        pv = fcf / ((1 + wacc) ** t)
        pv_sum += pv
        projections.append({
            "year": base_year + t,
            "revenue": round(rev, 0),
            "fcf": round(fcf, 0),
            "pvFcf": round(pv, 0),
        })

    # Terminal value
    fcf_5 = projections[-1]["fcf"]
    tv = fcf_5 * exit_mult
    pv_tv = tv / ((1 + wacc) ** 5)
    enterprise_value = pv_sum + pv_tv
    equity_value = enterprise_value - net_debt
    implied_price = equity_value / shares if shares > 0 else 0.0

    # Sensitivity grid: WACC 7-13%, exit multiple 12-28x
    sensitivity = []
    for w_pct in [7.0, 8.5, 10.0, 11.5, 13.0]:
        for em in [12.0, 16.0, 20.0, 24.0, 28.0]:
            w = w_pct / 100.0
            pv2 = sum(
                projections[i]["fcf"] / ((1 + w) ** (i + 1))
                for i in range(5)
            )
            tv2 = projections[-1]["fcf"] * em / ((1 + w) ** 5)
            ev2 = pv2 + tv2 - net_debt
            ip2 = ev2 / shares if shares > 0 else 0.0
            sensitivity.append({"wacc": w_pct, "exitMultiple": em, "impliedPrice": round(ip2, 2)})

    return projections, round(implied_price, 2), sensitivity


def build_dcf_model(params: dict) -> dict:
    symbol = (params.get("symbol") or "MSFT").upper()
    company = data.get_company(symbol)
    if not company:
        raise ValueError(f"Unknown symbol: {symbol}")

    base_rev = company["revenue"]
    price = company["price"]
    market_cap = company["marketCap"]
    shares_out = market_cap  # will divide by price to get shares
    shares_actual = market_cap / price  # actual share count

    # Estimate net debt: rough heuristic by sector
    sector = company["sector"]
    if sector == "energy":
        net_debt = base_rev * 0.3
    elif sector == "semiconductors":
        net_debt = base_rev * 0.05
    else:
        net_debt = 0.0

    # Default assumptions derived from company fundamentals
    seed = data._seed(symbol)
    seed, r = _rng_next(seed)

    # Revenue growth: derive from recent market momentum + sector
    rev_growth_base = {"semiconductors": 18.0, "energy": 6.0, "ai_tech": 14.0}.get(sector, 12.0)
    rev_growth = round(rev_growth_base + (r - 0.5) * 6.0, 1)

    ebitda_margin_base = max(10.0, company["netMargin"] * 1.4)
    ebitda_margin = round(min(60.0, ebitda_margin_base), 1)

    wacc = round(9.0 + company["beta"] * 1.5, 1)
    exit_multiple = round(18.0 + (r - 0.5) * 6.0, 1)
    tax_rate = 21.0
    capex_pct = {"semiconductors": 8.0, "energy": 12.0, "ai_tech": 4.0}.get(sector, 5.0)

    assumptions = {
        "revenueGrowth": rev_growth,
        "ebitdaMargin": ebitda_margin,
        "wacc": wacc,
        "exitMultiple": exit_multiple,
        "taxRate": tax_rate,
        "capexPct": capex_pct,
    }

    projections, implied_mid, sensitivity = _run_dcf(base_rev, shares_actual, net_debt, assumptions)

    # Low / high based on bear / bull assumptions
    bear_assumptions = {**assumptions, "revenueGrowth": rev_growth - 5.0, "wacc": wacc + 2.0, "exitMultiple": exit_multiple - 4.0}
    bull_assumptions = {**assumptions, "revenueGrowth": rev_growth + 5.0, "wacc": wacc - 1.5, "exitMultiple": exit_multiple + 5.0}
    _, implied_low, _ = _run_dcf(base_rev, shares_actual, net_debt, bear_assumptions)
    _, implied_high, _ = _run_dcf(base_rev, shares_actual, net_debt, bull_assumptions)

    return {
        "symbol": symbol,
        "name": company["name"],
        "currentPrice": price,
        "baseRevenue": base_rev,
        "sharesOut": round(shares_actual / 1e6, 1),
        "netDebt": round(net_debt, 0),
        "assumptions": assumptions,
        "projections": projections,
        "impliedPriceLow": implied_low,
        "impliedPriceMid": implied_mid,
        "impliedPriceHigh": implied_high,
        "sensitivity": sensitivity,
    }


# ----------------------------- earnings transcript builder -----------------------------
_TRANSCRIPT_TEMPLATES = {
    "NVDA": {
        "quarter": "Q4 FY2025",
        "call_date": "2025-02-26",
        "segments": [
            ("Jensen Huang", "CEO", "We delivered record revenue of $39.3 billion for Q4, up 78% year-over-year. The AI revolution is in full swing, and NVIDIA is at the center of it.", 0.95, True, "Record Revenue"),
            ("Colette Kress", "CFO", "Data Center revenue reached $35.6 billion, representing 91% of total revenue. Hopper demand remains robust, and Blackwell ramp is proceeding ahead of schedule.", 0.88, True, "Data Center Growth"),
            ("Jensen Huang", "CEO", "We are seeing unprecedented demand from hyperscalers, sovereign AI programs, and enterprises. Our pipeline has never been stronger across all geographies.", 0.90, False, ""),
            ("Colette Kress", "CFO", "Gross margins came in at 73.5%, slightly below guidance due to Blackwell ramp costs. We expect margins to return to the mid-70s range as volumes scale in H1 FY2026.", 0.55, False, ""),
            ("Vivek Arya", "Analyst", "Can you speak to the competitive dynamics from custom silicon efforts at hyperscalers? Are you seeing any displacement risk?", 0.10, False, ""),
            ("Jensen Huang", "CEO", "Custom silicon addresses specific use cases, but the breadth of CUDA's ecosystem and software stack represents a multi-decade moat. We welcome the compute expansion — a rising tide lifts all boats.", 0.82, True, "Competitive Moat"),
            ("Timothy Arcuri", "Analyst", "What's the trajectory for Blackwell GB200 NVL rack shipments in the first half?", 0.20, False, ""),
            ("Colette Kress", "CFO", "We expect Blackwell to contribute meaningfully more than Hopper did in the comparable period. We're supply-constrained, not demand-constrained.", 0.85, True, "Supply Constraints"),
            ("Jensen Huang", "CEO", "Looking ahead, we see AI agents, physical AI, and robotics as the next major growth vectors. We're positioning NVIDIA as the computing infrastructure for the age of AI.", 0.92, True, "Future Outlook"),
            ("Colette Kress", "CFO", "For Q1 FY2026, we guide revenue of approximately $43 billion, plus or minus 2%. Gross margins expected in the 73-74% range.", 0.75, False, ""),
        ],
    },
    "MSFT": {
        "quarter": "Q2 FY2026",
        "call_date": "2026-01-29",
        "segments": [
            ("Satya Nadella", "CEO", "We had an exceptional quarter with revenue of $69.6 billion, up 17% year-over-year. AI is becoming the defining feature across every product line.", 0.92, True, "Revenue Growth"),
            ("Amy Hood", "CFO", "Azure and other cloud services grew 31%, with AI services contributing roughly 13 points of that growth — our fastest-growing AI revenue trajectory to date.", 0.89, True, "Azure AI Growth"),
            ("Satya Nadella", "CEO", "Copilot seat additions accelerated meaningfully. We now have over 400 million commercial users across Microsoft 365, and Copilot conversion continues to expand.", 0.88, True, "Copilot Adoption"),
            ("Amy Hood", "CFO", "Operating income grew 17% to $31.7 billion. Capital expenditures were $22.6 billion, in line with our investment thesis in AI infrastructure.", 0.62, False, ""),
            ("Mark Moerdler", "Analyst", "Can you give us more color on the AI capacity situation? Are you able to meet all demand on Azure AI?", 0.25, False, ""),
            ("Amy Hood", "CFO", "We saw some demand that we weren't able to fully serve in the quarter — we're adding capacity as fast as we can. This should ease materially through the second half of fiscal year.", 0.55, False, ""),
            ("Satya Nadella", "CEO", "Our infrastructure investments give us a multi-year supply advantage over most competitors. We've been investing ahead of demand, and the returns are showing up.", 0.80, True, "Infrastructure Edge"),
            ("Brad Sills", "Analyst", "What are you seeing in terms of enterprise willingness to pay for Copilot beyond the initial pilots?", 0.15, False, ""),
            ("Satya Nadella", "CEO", "Conversion from trial to paid is the best we've seen for any new SKU in Microsoft's history. Customers see 10-30% productivity gains in measured deployments.", 0.90, True, "Copilot ROI"),
        ],
    },
}

_GENERIC_TRANSCRIPT_ROLES = [
    ("CEO", "positive"), ("CFO", "neutral"), ("Analyst", "neutral"), ("Analyst", "neutral"),
]

_GENERIC_SEGMENTS = [
    (0, "We are pleased to report strong results for the quarter. Revenue grew {growth}% year-over-year, driven by continued strength in our core markets.", 0.80, True, "Strong Revenue"),
    (1, "Operating margins expanded {margin_delta} basis points versus the prior year period. Free cash flow generation remained robust.", 0.70, False, ""),
    (2, "Can you comment on the demand environment and competitive positioning heading into next quarter?", 0.10, False, ""),
    (0, "We see continued strong demand from our key customer segments. Our pipeline is healthy and we remain confident in our full-year outlook.", 0.75, True, "Demand Outlook"),
    (1, "For the next quarter we guide revenue in the range of {guide_low} to {guide_high} billion, representing growth of {guide_growth}% year-over-year at the midpoint.", 0.55, False, ""),
    (3, "How should we think about capital allocation priorities for the year? Buybacks versus M&A?", 0.10, False, ""),
    (0, "We remain committed to returning capital to shareholders through our buyback program, while maintaining strategic flexibility for value-accretive acquisitions.", 0.65, True, "Capital Allocation"),
    (1, "We have $X billion of capacity remaining under our current buyback authorization. Gross margins are expected to remain in the {margin_range} range.", 0.60, False, ""),
    (0, "In closing, we are executing on our strategic priorities and remain well-positioned to capitalize on the secular growth trends in our industry.", 0.78, False, ""),
]

_SPEAKERS_BY_ROLE = {
    "CEO": ["Michael Chen", "Sarah Williams", "David Rodriguez", "Jennifer Park"],
    "CFO": ["Robert Kim", "Emily Thompson", "James Martinez"],
    "Analyst": ["Alex Goldman", "Morgan Stanley", "JP Morgan", "BofA Securities", "Citi Research"],
    "Operator": ["Operator"],
}


def _build_mock_transcript(symbol: str, company: dict) -> dict:
    seed = data._seed(symbol)
    seed, r = _rng_next(seed)

    growth = round(8 + r * 25, 1)
    seed, r = _rng_next(seed)
    margin_delta = round(30 + r * 120, 0)
    base_rev_b = company["revenue"] / 1e9
    guide_low = round(base_rev_b / 4 * 1.05, 1)
    guide_high = round(base_rev_b / 4 * 1.12, 1)

    seed, r = _rng_next(seed)
    ceo_idx = int(r * len(_SPEAKERS_BY_ROLE["CEO"]))
    seed, r = _rng_next(seed)
    cfo_idx = int(r * len(_SPEAKERS_BY_ROLE["CFO"]))

    speakers = [
        _SPEAKERS_BY_ROLE["CEO"][ceo_idx % len(_SPEAKERS_BY_ROLE["CEO"])],
        _SPEAKERS_BY_ROLE["CFO"][cfo_idx % len(_SPEAKERS_BY_ROLE["CFO"])],
        "Morgan Stanley",
        "BofA Securities",
    ]

    today = date.today()
    call_date = (today - timedelta(days=45)).isoformat()
    quarter_num = ((today.month - 1) // 3) + 1
    quarter = f"Q{quarter_num} {today.year}"

    segments = []
    for idx, (role_idx, tmpl, sent, is_key, topic) in enumerate(_GENERIC_SEGMENTS):
        text = tmpl.format(
            growth=growth, margin_delta=int(margin_delta),
            guide_low=guide_low, guide_high=guide_high,
            guide_growth=round(growth * 0.9, 1),
            margin_range="65-70%",
        )
        sent_label = "positive" if sent > 0.6 else "negative" if sent < 0.0 else "neutral"
        segments.append({
            "index": idx,
            "speaker": speakers[role_idx],
            "role": ["CEO", "CFO", "Analyst", "Analyst"][role_idx],
            "text": text,
            "sentiment": sent,
            "sentimentLabel": sent_label,
            "isKeyQuote": is_key,
        })

    key_quotes = [
        {"speaker": s["speaker"], "role": s["role"], "text": s["text"], "topic": topic}
        for s in segments
        for seg, _, _, _, topic in _GENERIC_SEGMENTS
        if s["isKeyQuote"] and s["index"] == _GENERIC_SEGMENTS.index((_GENERIC_SEGMENTS[s["index"]][0], _GENERIC_SEGMENTS[s["index"]][1], _GENERIC_SEGMENTS[s["index"]][2], _GENERIC_SEGMENTS[s["index"]][3], _GENERIC_SEGMENTS[s["index"]][4])) and topic
    ][:4]

    if not key_quotes:
        key_quotes = [{"speaker": segments[0]["speaker"], "role": "CEO", "text": segments[0]["text"], "topic": "Revenue Growth"}]

    sentiment_timeline = [
        {"index": s["index"], "score": s["sentiment"], "label": s["sentimentLabel"]}
        for s in segments
    ]

    overall = round(sum(s["sentiment"] for s in segments) / len(segments), 2)

    return {
        "symbol": symbol,
        "name": company["name"],
        "callDate": call_date,
        "quarter": quarter,
        "overallSentiment": overall,
        "segments": segments,
        "keyQuotes": key_quotes,
        "sentimentTimeline": sentiment_timeline,
    }


def build_earnings_transcript(params: dict) -> dict:
    symbol = (params.get("symbol") or "NVDA").upper()
    company = data.get_company(symbol)
    if not company:
        raise ValueError(f"Unknown symbol: {symbol}")

    if symbol in _TRANSCRIPT_TEMPLATES:
        tmpl = _TRANSCRIPT_TEMPLATES[symbol]
        segments = []
        for idx, (speaker, role, text, sent, is_key, topic) in enumerate(tmpl["segments"]):
            sent_label = "positive" if sent > 0.6 else "negative" if sent < 0.2 else "neutral"
            segments.append({
                "index": idx,
                "speaker": speaker,
                "role": role,
                "text": text,
                "sentiment": sent,
                "sentimentLabel": sent_label,
                "isKeyQuote": is_key,
            })

        key_quotes = []
        for seg, (speaker, role, text, sent, is_key, topic) in zip(segments, tmpl["segments"]):
            if is_key and topic:
                key_quotes.append({"speaker": speaker, "role": role, "text": text, "topic": topic})

        sentiment_timeline = [
            {"index": s["index"], "score": s["sentiment"], "label": s["sentimentLabel"]}
            for s in segments
        ]
        overall = round(sum(s["sentiment"] for s in segments) / len(segments), 2)

        return {
            "symbol": symbol,
            "name": company["name"],
            "callDate": tmpl["call_date"],
            "quarter": tmpl["quarter"],
            "overallSentiment": overall,
            "segments": segments,
            "keyQuotes": key_quotes,
            "sentimentTimeline": sentiment_timeline,
        }

    if ai.ai_available():
        try:
            return _build_ai_transcript(symbol, company)
        except Exception:
            pass

    return _build_mock_transcript(symbol, company)


def _build_ai_transcript(symbol: str, company: dict) -> dict:
    prompt = (
        "You are generating a realistic earnings call transcript summary for a market terminal. "
        "The company is " + company["name"] + " (" + symbol + "), a " + company["description"] + ". "
        "Recent price change: " + str(company["changePct"]) + "%. "
        "Revenue TTM: $" + str(round(company["revenue"] / 1e9, 1)) + "B, Net margin: " + str(company["netMargin"]) + "%. "
        "Generate a realistic mock earnings call with 8-10 segments. "
        "Respond with JSON only, shape: "
        '{"quarter": "Q4 FY2025", "callDate": "2025-02-26", "segments": ['
        '{"index": 0, "speaker": "CEO name", "role": "CEO", "text": "...", '
        '"sentiment": 0.85, "sentimentLabel": "positive", "isKeyQuote": true}], '
        '"keyQuotes": [{"speaker": "...", "role": "CEO", "text": "...", "topic": "Revenue"}]}'
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
    segments = parsed.get("segments", [])
    for i, s in enumerate(segments):
        s["index"] = i
        s["sentimentLabel"] = "positive" if s.get("sentiment", 0.5) > 0.6 else "negative" if s.get("sentiment", 0.5) < 0.3 else "neutral"
    overall = round(sum(s.get("sentiment", 0.5) for s in segments) / max(len(segments), 1), 2)
    sentiment_timeline = [
        {"index": s["index"], "score": s.get("sentiment", 0.5), "label": s["sentimentLabel"]}
        for s in segments
    ]
    return {
        "symbol": symbol,
        "name": company["name"],
        "callDate": parsed.get("callDate", date.today().isoformat()),
        "quarter": parsed.get("quarter", "Q4 FY2025"),
        "overallSentiment": overall,
        "segments": segments,
        "keyQuotes": parsed.get("keyQuotes", []),
        "sentimentTimeline": sentiment_timeline,
    }


# ----------------------------- earnings calendar builder -----------------------------
def build_earnings_calendar(params: dict) -> dict:
    """Upcoming scheduled earnings reports for a watchlist, tickers or a sector."""
    symbols_param = params.get("symbols")
    symbol = params.get("symbol")
    sector_param = params.get("sector")
    explicit_days = params.get("days") or params.get("horizon")

    if symbol and not symbols_param:
        symbols_param = [symbol]

    if symbols_param:
        syms = [str(s).upper() for s in symbols_param if data.get_company(str(s).upper())]
        scope = ", ".join(syms[:4]) + ("…" if len(syms) > 4 else "")
        title = f"Earnings Calendar — {scope}" if syms else "Earnings Calendar"
        scope_label = "watchlist"
        default_horizon = 120  # explicit names: always surface each one's next report
    elif sector_param:
        sid = data.resolve_sector(sector_param)
        syms = data.symbols_in_sector(sid) if sid else []
        title = f"Earnings Calendar — {data.sector_name(sid) if sid else sector_param}"
        scope_label = "sector"
        default_horizon = 120
    else:
        syms = list(data.CORE_SYMBOLS)
        title = "Earnings Calendar — Watchlist"
        scope_label = "watchlist"
        default_horizon = 30

    horizon = explicit_days if explicit_days is not None else default_horizon
    try:
        horizon = int(horizon)
    except (TypeError, ValueError):
        horizon = default_horizon
    horizon = max(7, min(horizon, 120))

    if not syms:
        raise ValueError("No tracked symbols to build an earnings calendar for.")

    rows = data.earnings_calendar(syms, horizon_days=horizon)

    # Keep the panel readable while always preserving the soonest (imminent) names,
    # which sit at the front after the date sort.
    max_rows = 40
    if len(rows) > max_rows:
        rows = rows[:max_rows]

    imminent = [r for r in rows if r["imminent"]]

    return {
        "title": title,
        "rows": rows,
        "imminent": imminent,
        "imminentCount": len(imminent),
        "nextReport": rows[0] if rows else None,
        "horizonDays": horizon,
        "count": len(rows),
        "watchlistSize": len(syms),
        "scope": scope_label,
        "asOf": date.today().isoformat(),
        "source": "Synthetic earnings schedule",
    }


# ----------------------------- M&A tracker builder -----------------------------
_MA_DEALS = [
    {
        "target": "Altair Engineering", "targetSymbol": None,
        "acquirer": "Broadcom Inc.", "acquirerSymbol": "AVGO",
        "dealValue": 8_700_000_000, "premium": 34.2,
        "status": "completed", "announced": "2025-01-15", "expectedClose": None,
        "arbSpread": None, "dealType": "acquisition", "sector": "ai_tech",
    },
    {
        "target": "Synopsys EDA Unit", "targetSymbol": None,
        "acquirer": "Palantir Technologies", "acquirerSymbol": "PLTR",
        "dealValue": 2_200_000_000, "premium": 28.5,
        "status": "pending", "announced": "2025-09-03", "expectedClose": "2026-Q2",
        "arbSpread": 5.8, "dealType": "acquisition", "sector": "ai_tech",
    },
    {
        "target": "IronSource (reboot)", "targetSymbol": None,
        "acquirer": "CRM", "acquirerSymbol": "CRM",
        "dealValue": 4_100_000_000, "premium": 22.0,
        "status": "pending", "announced": "2025-11-12", "expectedClose": "2026-Q2",
        "arbSpread": 4.2, "dealType": "merger", "sector": "ai_tech",
    },
    {
        "target": "Vertex Energy", "targetSymbol": None,
        "acquirer": "Occidental Petroleum", "acquirerSymbol": "OXY",
        "dealValue": 1_400_000_000, "premium": 41.0,
        "status": "completed", "announced": "2025-03-20", "expectedClose": None,
        "arbSpread": None, "dealType": "acquisition", "sector": "energy",
    },
    {
        "target": "Semtech Corp.", "targetSymbol": None,
        "acquirer": "Qualcomm Inc.", "acquirerSymbol": "QCOM",
        "dealValue": 5_800_000_000, "premium": 37.5,
        "status": "pending", "announced": "2025-10-08", "expectedClose": "2026-Q3",
        "arbSpread": 7.1, "dealType": "acquisition", "sector": "semiconductors",
    },
    {
        "target": "Numerix LLC", "targetSymbol": None,
        "acquirer": "Snowflake Inc.", "acquirerSymbol": "SNOW",
        "dealValue": 900_000_000, "premium": 18.0,
        "status": "completed", "announced": "2025-05-14", "expectedClose": None,
        "arbSpread": None, "dealType": "acquisition", "sector": "ai_tech",
    },
    {
        "target": "Renesas NA Auto Unit", "targetSymbol": None,
        "acquirer": "NVIDIA Corp.", "acquirerSymbol": "NVDA",
        "dealValue": 3_500_000_000, "premium": 25.0,
        "status": "withdrawn", "announced": "2025-02-01", "expectedClose": None,
        "arbSpread": None, "dealType": "acquisition", "sector": "semiconductors",
    },
    {
        "target": "Scout Energy Partners", "targetSymbol": None,
        "acquirer": "ConocoPhillips", "acquirerSymbol": "COP",
        "dealValue": 2_700_000_000, "premium": 19.8,
        "status": "completed", "announced": "2025-07-22", "expectedClose": None,
        "arbSpread": None, "dealType": "acquisition", "sector": "energy",
    },
    {
        "target": "CloudKitchens (IPO target)", "targetSymbol": None,
        "acquirer": "Amazon.com Inc.", "acquirerSymbol": "AMZN",
        "dealValue": 6_200_000_000, "premium": 31.0,
        "status": "pending", "announced": "2026-02-14", "expectedClose": "2026-Q4",
        "arbSpread": 6.3, "dealType": "acquisition", "sector": "ai_tech",
    },
    {
        "target": "First Solar EPC Div.", "targetSymbol": "FSLR",
        "acquirer": "NextEra Energy", "acquirerSymbol": "NEE",
        "dealValue": 4_800_000_000, "premium": 16.4,
        "status": "pending", "announced": "2026-03-05", "expectedClose": "2026-Q4",
        "arbSpread": 3.9, "dealType": "merger", "sector": "energy",
    },
]


def build_ma_tracker(params: dict) -> dict:
    sector_filter = params.get("sector")
    if sector_filter:
        sid = data.resolve_sector(sector_filter)
        deals = [d for d in _MA_DEALS if d["sector"] == sid] if sid else _MA_DEALS
        title = f"M&A Tracker — {data.sector_name(sid) if sid else sector_filter}"
    else:
        symbol = (params.get("symbol") or "").upper()
        if symbol:
            deals = [
                d for d in _MA_DEALS
                if d.get("targetSymbol") == symbol or d.get("acquirerSymbol") == symbol
            ]
            if not deals:
                deals = _MA_DEALS
            company = data.get_company(symbol)
            title = f"M&A Tracker — {company['name'] if company else symbol}"
        else:
            deals = _MA_DEALS
            title = "M&A Tracker — All Sectors 2025-26"

    deal_list = []
    for i, d in enumerate(deals):
        deal_list.append({
            "id": f"deal-{i}",
            **{k: v for k, v in d.items()},
        })

    total_value = sum(d["dealValue"] for d in deal_list)
    completed = [d for d in deal_list if d["status"] == "completed"]
    pending = [d for d in deal_list if d["status"] == "pending"]
    premiums = [d["premium"] for d in deal_list if d["status"] != "withdrawn"]
    avg_premium = round(sum(premiums) / len(premiums), 1) if premiums else 0.0

    stats = {
        "totalDeals": len(deal_list),
        "totalValue": total_value,
        "avgPremium": avg_premium,
        "pendingDeals": len(pending),
    }

    return {"title": title, "deals": deal_list, "stats": stats}


# ----------------------------- quant data layer -----------------------------
_INTERVAL_LABELS = {
    "1m": "1-minute", "2m": "2-minute", "5m": "5-minute", "15m": "15-minute",
    "30m": "30-minute", "60m": "1-hour", "90m": "90-minute", "1h": "1-hour",
}
_RANGE_LABELS = {
    "1d": "1 day", "5d": "5 days", "7d": "7 days", "1mo": "1 month",
    "60d": "60 days", "3mo": "3 months", "6mo": "6 months",
    "1y": "1 year", "2y": "2 years",
}


def build_data_universe(params: dict) -> dict:
    """Investable-universe overview: symbols, sector/industry, coverage and
    provenance. Honest about which names are live vs catalog breadth (mock)."""
    sector = params.get("sector") or params.get("scope")
    try:
        limit = int(params.get("limit") or 150)
    except (TypeError, ValueError):
        limit = 150
    limit = max(10, min(limit, 400))
    ov = repo.universe_overview(sector=sector, limit=limit)

    if sector and ov["summary"]["totalSymbols"]:
        sid = repo.resolve_sector(sector) or sector
        title = f"Data Universe — {repo.sector_name(sid)}"
    else:
        title = "Data Universe — Coverage & Provenance"

    return {
        "title": title,
        "summary": ov["summary"],
        "sectors": ov["sectors"],
        "rows": ov["rows"],
        "rowsShown": len(ov["rows"]),
        "asOf": ov.get("asOf"),
        "source": ov.get("source") or _live_source(),
    }


def build_intraday_chart(params: dict) -> dict:
    """Intraday OHLCV at a selectable Yahoo resolution, fetched live (with a
    short-lived cache) and clearly labeled with the resolution/window actually
    served. Returns a clean unavailable state when the request exceeds source
    limits — never daily or synthetic data in its place."""
    symbol = (params.get("symbol") or "NVDA").upper()
    repo.note_symbol(symbol)
    company = repo.get_company(symbol)
    name = company["name"] if company else symbol

    interval = (params.get("interval") or params.get("resolution") or "5m").lower()
    rng = params.get("range") or params.get("window")
    rng = rng.lower() if isinstance(rng, str) else None

    base = {
        "symbol": symbol, "name": name,
        "interval": interval,
        "intervalLabel": _INTERVAL_LABELS.get(interval, interval),
    }

    ysym = data.yahoo_symbol(symbol)
    cache_key = f"intraday:{ysym}:{interval}:{rng or 'default'}"
    try:
        res = cache.cached(
            cache_key, 60.0,
            lambda: p_src.fetch_intraday(ysym, interval, rng),
        )
    except p_src.IntradayUnavailable as exc:
        return {
            **base,
            "range": rng or "",
            "rangeLabel": _RANGE_LABELS.get(rng or "", rng or ""),
            "available": False,
            "reason": str(exc),
            "points": [], "last": None, "change": None, "changePct": None,
            "asOf": None, "source": "unavailable",
        }
    except Exception as exc:  # noqa: BLE001 - any upstream failure -> clean state
        return {
            **base,
            "range": rng or "",
            "rangeLabel": _RANGE_LABELS.get(rng or "", rng or ""),
            "available": False,
            "reason": f"Upstream fetch failed: {exc}",
            "points": [], "last": None, "change": None, "changePct": None,
            "asOf": None, "source": "unavailable",
        }

    points = res["points"]
    served_iv = res["interval"]
    last = points[-1]["c"] if points else None
    first = points[0]["o"] if points else None
    change = round(last - first, 2) if (last is not None and first) else None
    change_pct = round(change / first * 100, 2) if (change is not None and first) else None

    return {
        **base,
        "interval": served_iv,
        "intervalLabel": _INTERVAL_LABELS.get(served_iv, served_iv),
        "name": res.get("name") or name,
        "range": res["range"],
        "rangeLabel": _RANGE_LABELS.get(res["range"], res["range"]),
        "currency": res.get("currency") or "USD",
        "available": True,
        "reason": None,
        "bars": len(points),
        "points": points,
        "last": last,
        "change": change,
        "changePct": change_pct,
        "asOf": res.get("asOf"),
        "source": "live",
    }


def _quality_status(source: str, q: dict) -> str:
    if source != "live":
        return "mock"
    if q.get("stale"):
        return "stale"
    if q.get("issues"):
        return "warn"
    return "ok"


def _empty_quality() -> dict:
    """Zeroed quality fields so an unavailable row carries the full shape."""
    return {
        "rows": 0, "gaps": 0, "duplicates": 0, "nanRows": 0,
        "zeroVolume": 0, "droppedRows": 0, "firstDate": None,
        "lastDate": None, "stale": False, "staleSeconds": None, "issues": [],
    }


def _intraday_quality_row(sym: str, name: str, interval: str, rng: Optional[str]) -> dict:
    """Audit one symbol's intraday series at `interval`, validating the live bars
    fetched from Yahoo. Returns a clean `unavailable` row (never daily/synthetic
    data) when the resolution/window isn't served or the fetch fails."""
    ysym = data.yahoo_symbol(sym)
    cache_key = f"intraday:{ysym}:{interval}:{rng or 'default'}"
    base = {
        "symbol": sym, "name": name, "interval": interval,
        "intervalLabel": _INTERVAL_LABELS.get(interval, interval),
    }
    try:
        res = cache.cached(
            cache_key, 60.0,
            lambda: p_src.fetch_intraday(ysym, interval, rng),
        )
    except p_src.IntradayUnavailable as exc:
        return {**base, "source": "unavailable", "asOf": None,
                "status": "unavailable", "reason": str(exc), **_empty_quality()}
    except Exception as exc:  # noqa: BLE001 - any upstream failure -> clean state
        return {**base, "source": "unavailable", "asOf": None,
                "status": "unavailable",
                "reason": f"Upstream fetch failed: {exc}", **_empty_quality()}

    served_iv = res.get("interval") or interval
    as_of = res.get("asOf")
    q = quality.validate_series(res["points"], interval=served_iv, as_of=as_of)
    return {
        **base,
        "interval": served_iv,
        "intervalLabel": _INTERVAL_LABELS.get(served_iv, served_iv),
        "source": "live", "asOf": as_of, "reason": None,
        "status": _quality_status("live", q),
        **q,
    }


def build_data_quality(params: dict) -> dict:
    """Data-quality report over real OHLCV series: gaps, stale, NaN/zero-volume
    bars and duplicate timestamps, each row tagged with its provenance.

    Audits the daily (1d) series by default. Pass an intraday `interval`
    (e.g. 5m) to validate the minute/hour bars instead — missing bars, duplicate
    timestamps and zero-volume gaps that only surface intraday. Symbols whose
    intraday window isn't served are reported as a clean `unavailable` row."""
    symbol = params.get("symbol")
    sector = params.get("sector")
    try:
        days = int(params.get("days") or 120)
    except (TypeError, ValueError):
        days = 120
    days = max(20, min(days, 400))

    interval = (params.get("interval") or params.get("resolution") or "1d").lower()
    intraday = interval != "1d"
    if intraday and interval not in p_src.INTRADAY_RANGES:
        # Unknown resolution -> fall back to the daily audit rather than error.
        interval, intraday = "1d", False
    rng = params.get("range") or params.get("window")
    rng = rng.lower() if isinstance(rng, str) else None

    if symbol:
        syms = [symbol.upper()]
        title = f"Data Quality — {symbol.upper()}"
    elif sector:
        sid = repo.resolve_sector(sector) or sector
        syms = repo.symbols_in_sector(sid)[:12]
        title = f"Data Quality — {repo.sector_name(sid)}"
    else:
        syms = repo.prompt_symbols(8)
        title = "Data Quality — Core Coverage"

    interval_label = _INTERVAL_LABELS.get(interval, interval) if intraday else "daily"
    if intraday:
        title += f" · {interval_label}"

    series: List[dict] = []
    latest: Optional[str] = None
    for sym in syms:
        repo.note_symbol(sym)
        company = repo.get_company(sym)
        nm = company["name"] if company else sym
        if intraday:
            row = _intraday_quality_row(sym, nm, interval, rng)
        else:
            meta = repo.price_series_meta(sym, days=days)
            source = meta.get("source") or "mock"
            as_of = meta.get("asOf")
            q = quality.validate_series(meta["points"], interval="1d", as_of=as_of)
            row = {
                "symbol": sym, "name": nm, "interval": "1d",
                "intervalLabel": "daily", "source": source, "asOf": as_of,
                "reason": None, "status": _quality_status(source, q), **q,
            }
        as_of = row.get("asOf")
        if as_of and (latest is None or as_of > latest):
            latest = as_of
        series.append(row)

    ok = sum(1 for s in series if s["status"] == "ok")
    issues = sum(1 for s in series if s["status"] in ("warn", "stale"))
    mock = sum(1 for s in series if s["status"] == "mock")
    unavailable = sum(1 for s in series if s["status"] == "unavailable")
    return {
        "title": title,
        "interval": interval,
        "intervalLabel": interval_label,
        "series": series,
        "summary": {
            "seriesCount": len(series),
            "okCount": ok,
            "issueCount": issues,
            "mockCount": mock,
            "unavailableCount": unavailable,
            "asOf": latest,
        },
        "asOf": latest,
        "source": "live" if any(s["source"] == "live" for s in series) else "mock",
    }


def build_strategy_desk(params: dict) -> dict:
    """Strategy lifecycle desk: roster of every strategy across the research →
    backtest → paper → live lifecycle plus a marked paper-book detail for one.

    Pure orchestration over the lifecycle service — every P&L number is the book
    marked to REAL prices, and the NAV history is reconstructed from real closes
    since inception (no synthetic curve)."""
    from . import strategy

    selected = params.get("strategy") or params.get("strategyName") or params.get("name")
    payload = strategy.desk_payload(selected)
    payload["title"] = "Strategy Desk"
    return payload


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
    "strategy-desk", "Strategy Lifecycle Desk", "strategy_desk",
    "Lists every systematic strategy across the research → backtest → paper → live "
    "lifecycle with its stage, exposures and live (real-price) P&L, plus a marked "
    "paper-book detail (positions, NAV/P&L curve, realized stats, promotion check) "
    "for one strategy. Use for 'show the desk', 'my strategies', 'the paper book', "
    "'strategy lifecycle'. Pass `strategy` to focus one by name.",
    [
        {"name": "load_registry", "description": "Read the persisted strategy registry.", "expectedOutput": "All strategies with their lifecycle stage."},
        {"name": "mark_books", "description": "Mark each paper/live book to real prices.", "expectedOutput": "Per-strategy exposures and P&L."},
        {"name": "assemble_desk", "description": "Build the roster plus a selected strategy detail.", "expectedOutput": "A desk payload."},
    ],
    build_strategy_desk, "Strategy Desk",
))
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
_reg(SkillDef(
    "order-book", "Order Book Depth", "order_book",
    "Renders a two-sided bid/ask depth ladder with proportional size bars and a scrolling tape "
    "of recent prints. Use when the user asks to see the order book, L2 data, or bid/ask depth.",
    [
        {"name": "resolve_symbol", "description": "Map the request to a known ticker.", "expectedOutput": "A valid ticker."},
        {"name": "generate_ladder", "description": "Generate bid/ask levels with price, size and depth bars.", "expectedOutput": "Sorted bid and ask level lists."},
        {"name": "generate_tape", "description": "Produce a chronological tape of recent prints with side and venue.", "expectedOutput": "A list of print records."},
    ],
    build_order_book, "Order Book",
))
_reg(SkillDef(
    "trade-flow", "Trade Flow & Unusual Activity", "trade_flow",
    "Shows a timeline of prints sized by trade size, highlights block prints and dark pool flow, "
    "and displays net buy/sell imbalance. Use when the user asks about unusual activity, block trades, "
    "dark pool flow, or sweep orders.",
    [
        {"name": "resolve_symbol", "description": "Map the request to a known ticker.", "expectedOutput": "A valid ticker."},
        {"name": "generate_prints", "description": "Generate a timeline of prints with size, side, venue, block and dark flags.", "expectedOutput": "A list of flow print records."},
        {"name": "compute_imbalance", "description": "Derive buy/sell imbalance and dark pool percentage.", "expectedOutput": "Aggregate flow statistics."},
    ],
    build_trade_flow, "Trade Flow",
))
_reg(SkillDef(
    "tca-report", "Execution Simulation & TCA", "tca_report",
    "Runs the execution desk: turns a current-vs-target book (or an explicit order / single name) "
    "into orders, simulates VWAP/TWAP/POV executions against REAL intraday volume, applies a "
    "transparent square-root market-impact model, and reports implementation shortfall vs arrival, "
    "slippage vs interval VWAP, and cost in bps per name and aggregate — clearly separating "
    "real-data benchmarks from the modeled impact, and marking orders without real intraday data "
    "as unsupported. Use when the user asks about TCA, execution quality, slippage, market impact, "
    "VWAP/TWAP/POV, or the cost of trading into a portfolio.",
    [
        {"name": "generate_orders", "description": "Diff the current book against target weights (or take explicit orders) into buys/sells with side and size.", "expectedOutput": "A list of orders with side, shares and notional."},
        {"name": "simulate_algos", "description": "Simulate VWAP/TWAP/POV executions against real intraday volume, returning fill price, schedule and fill rate; mark unsupported when no real intraday data.", "expectedOutput": "Per-order algo fills and schedules."},
        {"name": "model_impact", "description": "Apply the square-root market-impact model to real volume + real daily vol as a labeled estimate.", "expectedOutput": "Modeled impact in bps per order."},
        {"name": "report_tca", "description": "Compute implementation shortfall vs arrival, slippage vs interval VWAP, and per-name + aggregate cost in bps.", "expectedOutput": "A TCA payload with realized and modeled components."},
    ],
    build_tca_report, "Execution TCA",
))
_reg(SkillDef(
    "macro-dashboard", "Macro & Cross-Asset Dashboard", "macro_dashboard",
    "Renders a multi-tile macro dashboard grouping rates (yields, spreads), FX pairs, commodities "
    "(oil, gold, copper), and equity indices in a single panel. Each tile shows price, daily Δ%, "
    "and a sparkline. Use when the user asks for a macro view, global dashboard, or theme-specific "
    "cross-asset view (e.g. inflation, china, risk-on/off).",
    [
        {"name": "resolve_theme", "description": "Map the user's request to a macro theme (global, inflation, china, risk).", "expectedOutput": "A canonical theme key."},
        {"name": "build_tiles", "description": "Assemble asset tiles for the theme with price, change, and sparkline.", "expectedOutput": "Grouped asset tiles."},
    ],
    build_macro_dashboard, "Macro Dashboard",
))
_reg(SkillDef(
    "portfolio-risk", "Portfolio Risk & Factor Exposure", "portfolio_risk",
    "Decomposes a portfolio of tickers into VaR distribution, systematic factor exposures "
    "(market, momentum, size, value, quality), and a risk summary card (1-day 95% VaR, "
    "tracking error, beta). Use when the user asks about risk, VaR, factor exposure, or "
    "portfolio breakdown.",
    [
        {"name": "resolve_symbols", "description": "Map the requested portfolio tickers to valid symbols.", "expectedOutput": "A list of tickers."},
        {"name": "build_var_histogram", "description": "Simulate a P&L distribution and derive VaR bins.", "expectedOutput": "20 histogram bins."},
        {"name": "compute_factor_exposures", "description": "Estimate portfolio loading on each systematic factor.", "expectedOutput": "Factor exposure list."},
        {"name": "summarize_risk", "description": "Compute 1-day 95% VaR, tracking error, and portfolio beta.", "expectedOutput": "Risk summary card."},
    ],
    build_portfolio_risk, "Portfolio Risk",
))
_reg(SkillDef(
    "backtest", "Strategy Backtester", "backtest",
    "Backtests a named strategy (e.g. momentum, mean-reversion) on a single ticker, "
    "returning an equity curve vs benchmark, drawdown chart, and performance statistics "
    "(Sharpe, Sortino, CAGR, max drawdown, win rate). Use when the user asks to backtest, "
    "test a strategy, or see historical performance.",
    [
        {"name": "resolve_symbol", "description": "Map the ticker for the backtest universe.", "expectedOutput": "A valid ticker."},
        {"name": "generate_equity_curve", "description": "Simulate daily strategy and benchmark returns.", "expectedOutput": "Equity curve and drawdown series."},
        {"name": "compute_stats", "description": "Derive Sharpe, Sortino, CAGR, max DD, and win rate.", "expectedOutput": "Performance statistics."},
    ],
    build_backtest, "Backtest",
))
_reg(SkillDef(
    "monte-carlo", "Monte Carlo Simulator", "monte_carlo",
    "Projects forward price paths for a single ticker using a Monte Carlo simulation "
    "fitted to its real historical daily returns (bootstrap resampling or geometric "
    "Brownian motion). Returns a percentile fan (p5-p95), sample paths, expected/median "
    "terminal value, probability of loss, and terminal VaR/CVaR. Use when the user asks "
    "to simulate, project, forecast, or run Monte Carlo / scenario analysis on a stock.",
    [
        {"name": "resolve_symbol", "description": "Map the ticker to simulate.", "expectedOutput": "A valid ticker."},
        {"name": "fit_returns", "description": "Estimate the return distribution from real history.", "expectedOutput": "Daily return statistics."},
        {"name": "simulate_paths", "description": "Run the Monte Carlo paths and aggregate percentiles.", "expectedOutput": "Percentile fan and terminal summary."},
    ],
    build_monte_carlo, "Monte Carlo",
))
_reg(SkillDef(
    "correlation-matrix", "Correlation Matrix & Beta Table", "correlation_matrix",
    "Builds a pairwise correlation heatmap for a set of tickers, with a rolling 30/90-day "
    "toggle and a beta/hedge-ratio table. Use when the user asks about correlations, "
    "co-movement, diversification, or hedge ratios between stocks.",
    [
        {"name": "resolve_symbols", "description": "Map the requested tickers to valid symbols.", "expectedOutput": "A list of at least 2 tickers."},
        {"name": "compute_correlations", "description": "Build the n×n correlation matrix.", "expectedOutput": "Symmetric correlation matrix."},
        {"name": "compute_betas", "description": "Derive beta and hedge ratio per ticker.", "expectedOutput": "Beta/hedge ratio table."},
    ],
    build_correlation_matrix, "Correlation Matrix",
))
_reg(SkillDef(
    "factor-analysis", "Factor Return Attribution", "factor_analysis",
    "Decomposes a stock's returns into systematic factors (momentum, value, size, quality) "
    "month by month, with a factor loading table (loading, t-stat, contribution %). Use "
    "when the user asks about factor analysis, return attribution, or alpha decomposition.",
    [
        {"name": "resolve_symbol", "description": "Map the ticker to analyze.", "expectedOutput": "A valid ticker."},
        {"name": "build_monthly_attribution", "description": "Attribute monthly returns to factors.", "expectedOutput": "12 months of factor attribution."},
        {"name": "compute_loadings", "description": "Estimate factor loadings and t-statistics.", "expectedOutput": "Factor loading table."},
    ],
    build_factor_analysis, "Factor Analysis",
))
_reg(SkillDef(
    "risk-model", "Multi-Factor Risk Model", "risk_model",
    "Decomposes a portfolio's predicted volatility into common-factor risk vs "
    "stock-specific risk using a Barra-style multi-factor model (Market + Size, "
    "Value, Momentum, Volatility, Quality). Reports each factor's share of risk, "
    "the marginal contribution to risk (MCTR) of every holding, total/factor/"
    "specific volatility, the diversification ratio, and an honest coverage block "
    "naming any holdings excluded for lack of history or fundamentals. Use when "
    "the user asks to decompose portfolio risk, factor vs specific risk, MCTR, "
    "risk contribution, or for a risk model.",
    [
        {"name": "resolve_portfolio", "description": "Map the requested tickers and weights to a normalized portfolio.", "expectedOutput": "A list of weighted holdings."},
        {"name": "estimate_factor_model", "description": "Estimate factor returns, factor covariance, and specific risk from real cross-sectional data.", "expectedOutput": "A fitted factor model with coverage."},
        {"name": "decompose_risk", "description": "Split predicted volatility into factor vs specific risk and per-factor contributions.", "expectedOutput": "Risk decomposition with factor contributions."},
        {"name": "compute_mctr", "description": "Derive each holding's marginal contribution to total risk.", "expectedOutput": "Per-holding MCTR and percent of risk."},
    ],
    build_risk_model, "Risk Model",
))
_reg(SkillDef(
    "risk-monitor", "Risk Management & Monitoring", "risk_monitor",
    "A risk desk for a real book: live GROSS/NET/sector/factor exposures and "
    "position concentrations, real historical VaR/CVaR plus the factor model's "
    "predicted volatility, a configurable LIMITS framework (max gross/net/"
    "position/sector/factor and a daily VaR cap) with in-limit/breach status and "
    "a breach list, HISTORICAL STRESS that replays real crisis-window returns "
    "(2020 COVID, 2022 rate shock, 2008 GFC, Q4-2018, Aug-2015) onto the book, "
    "and HYPOTHETICAL STRESS that maps factor/asset/market shocks through the "
    "book's real exposures. Use when the user asks to monitor/manage portfolio "
    "risk, check exposures or limits/breaches, run a stress test, or ask 'how "
    "much could I lose if markets crash'. Pass symbols and optional signed "
    "weights (negative = short), nav/capital, a limits override, and shocks "
    "(factor_shocks, asset_shocks, market_shock). Names lacking coverage are "
    "flagged, never imputed.",
    [
        {"name": "resolve_book", "description": "Map tickers + signed weights + NAV to a real long/short book.", "expectedOutput": "A weighted book with gross/net exposure."},
        {"name": "measure_exposures", "description": "Compute gross/net, sector and factor exposures, concentrations and VaR/CVaR from real data.", "expectedOutput": "Exposure, concentration and tail-risk metrics."},
        {"name": "check_limits", "description": "Evaluate the book against configurable limits and flag breaches.", "expectedOutput": "Per-limit utilization/status and a breach list."},
        {"name": "stress_historical", "description": "Replay real crisis-window returns onto the current book.", "expectedOutput": "Simulated P&L and drawdown per crisis."},
        {"name": "stress_hypothetical", "description": "Map factor/asset/market shocks through the book's real exposures.", "expectedOutput": "Estimated P&L per hypothetical scenario."},
    ],
    build_risk_monitor, "Risk Monitor",
))
_reg(SkillDef(
    "factor-exposures", "Portfolio Factor Exposures", "factor_exposures",
    "Shows a portfolio's tilt toward each style factor (Market, Size, Value, "
    "Momentum, Volatility, Quality) as weighted-average standardized exposures, "
    "alongside the realized factor premia (annualized factor return + t-stat) and "
    "a per-holding exposure breakdown. Use when the user asks about factor tilts, "
    "style exposures, factor loadings of a portfolio, or how a portfolio is "
    "positioned across factors.",
    [
        {"name": "resolve_portfolio", "description": "Map the requested tickers and weights to a normalized portfolio.", "expectedOutput": "A list of weighted holdings."},
        {"name": "estimate_factor_model", "description": "Estimate standardized factor exposures from real fundamentals and returns.", "expectedOutput": "A fitted factor model with coverage."},
        {"name": "aggregate_exposures", "description": "Compute weighted-average portfolio exposures and per-holding tilts.", "expectedOutput": "Factor tilt table and per-holding exposures."},
    ],
    build_factor_exposures, "Factor Exposures",
))
_reg(SkillDef(
    "portfolio-optimizer", "Portfolio Construction & Optimization", "portfolio_optimizer",
    "Builds an optimal target portfolio from a candidate universe. Expected "
    "returns are factor-model-implied (style exposures × realized factor premia) "
    "and the covariance comes from the multi-factor risk model — both estimated "
    "from real data. Methods: max_sharpe / min_variance / target_vol "
    "(mean-variance), black_litterman, risk_parity, hrp. Constraints: long-only "
    "or long/short, per-name max position, sector caps, gross/net exposure, and a "
    "turnover penalty vs a current book. Use when the user wants to construct, "
    "optimize, rebalance, or size a portfolio, find optimal/target weights, build "
    "a max-Sharpe / minimum-variance / risk-parity / Black-Litterman portfolio, "
    "or allocate capital across names.",
    [
        {"name": "resolve_universe", "description": "Resolve the candidate names (explicit tickers, a sector, or a default core).", "expectedOutput": "A modelable universe of tickers."},
        {"name": "estimate_inputs", "description": "Build the covariance from the risk model and factor-implied expected returns from real data.", "expectedOutput": "An expected-return vector and covariance matrix with coverage."},
        {"name": "optimize_weights", "description": "Solve for target weights under the requested method and constraints.", "expectedOutput": "Constrained optimal weights and binding constraints."},
        {"name": "report_portfolio", "description": "Compute expected return, vol, Sharpe, factor tilts, sector allocation and active vs benchmark weights.", "expectedOutput": "A portfolio construction payload."},
    ],
    build_portfolio_optimizer, "Portfolio Optimizer",
))


_reg(SkillDef(
    "yield-curve", "Yield Curve & Rates", "yield_curve",
    "Renders the US (or UK/DE/JP) Treasury spot curve across all tenors with historical overlays "
    "(1Y ago, 2Y ago) and inversion highlights. Use when the user asks about the yield curve, "
    "interest rates, Treasury rates, or curve shape.",
    [
        {"name": "select_region", "description": "Identify the sovereign issuer (US, UK, DE, JP).", "expectedOutput": "A region code."},
        {"name": "bootstrap_curve", "description": "Produce spot rates for each tenor from short to long.", "expectedOutput": "Ordered tenor/rate points for current and historical curves."},
        {"name": "compute_spreads", "description": "Calculate 2Y-10Y, 2Y-30Y, and 3M-10Y spreads and flag inversion.", "expectedOutput": "Spread values and inversion flags."},
    ],
    build_yield_curve, "Yield Curve",
))
_reg(SkillDef(
    "bond-rv", "Bond Relative Value", "bond_rv",
    "Shows Z-spread, OAS, and asset-swap spread for a corporate bond issuer vs. a peer set, "
    "with yield and duration context. Use when the user asks about bond spreads, bond RV, "
    "bond relative value, Z-spread, OAS, asset-swap, or corporate credit.",
    [
        {"name": "resolve_issuer", "description": "Map the request to a known bond issuer.", "expectedOutput": "An issuer ticker."},
        {"name": "build_peer_set", "description": "Assemble bonds from similar-rated issuers for comparison.", "expectedOutput": "A list of bond rows with spread metrics."},
    ],
    build_bond_rv, "Bond Relative Value",
))
_reg(SkillDef(
    "cds-pricer", "CDS Pricer", "cds_pricer",
    "Prices a credit default swap on a reference entity: shows survival probability curve, "
    "running spread, upfront fee, and implied default probabilities by tenor. Use when the "
    "user asks to price a CDS, see credit default swap spreads, or analyze credit risk.",
    [
        {"name": "resolve_entity", "description": "Map the reference entity to a known ticker.", "expectedOutput": "An entity ticker."},
        {"name": "fit_hazard_curve", "description": "Derive flat-hazard survival probabilities from the CDS spread.", "expectedOutput": "Survival probability and hazard rate by tenor."},
        {"name": "compute_upfront", "description": "Calculate the upfront fee relative to the standard 100bps coupon.", "expectedOutput": "Upfront fee as a percentage of notional."},
    ],
    build_cds_pricer, "CDS Pricer",
))
_reg(SkillDef(
    "cashflow-duration", "Cash Flow & Duration", "cashflow_duration",
    "Renders a full coupon + principal cash-flow schedule for a bond, with modified/effective "
    "duration, convexity, DV01, and a parallel-shift scenario table. Use when the user asks "
    "about bond cash flows, duration, convexity, or rate sensitivity.",
    [
        {"name": "resolve_bond", "description": "Map the request to a specific bond (e.g. 10Y Treasury, AAPL bond).", "expectedOutput": "A bond key."},
        {"name": "schedule_cash_flows", "description": "Build the full coupon and principal payment schedule.", "expectedOutput": "Dated payments with present values."},
        {"name": "compute_duration", "description": "Calculate Macaulay, modified and effective duration, convexity and DV01.", "expectedOutput": "Duration metrics."},
        {"name": "build_scenarios", "description": "Compute price/yield changes for ±50/100/200bps parallel shifts.", "expectedOutput": "A scenario table."},
    ],
    build_cashflow_duration, "Cash Flow & Duration",
))
_reg(SkillDef(
    "iv-surface", "Implied Volatility Surface", "iv_surface",
    "Renders the implied volatility surface as a heatmap grid across strike prices and "
    "expiries, plus a 1M skew strip. Use when the user asks about the vol surface, IV surface, "
    "skew, or implied vol.",
    [
        {"name": "resolve_symbol", "description": "Map request to a known ticker.", "expectedOutput": "A valid ticker."},
        {"name": "build_surface", "description": "Generate IV for each (strike, expiry) cell using BS-implied smile.", "expectedOutput": "A grid of IV values."},
        {"name": "compute_skew", "description": "Extract the 1M skew strip across the strike range.", "expectedOutput": "A list of (strike, IV) skew points."},
    ],
    build_iv_surface, "IV Surface",
))
_reg(SkillDef(
    "options-strategy", "Options Strategy Builder", "options_strategy",
    "Builds an options strategy (straddle, strangle, iron condor, call/put spread, etc.) "
    "with a payoff diagram at expiry and a per-leg and net Greeks table. Use when the user "
    "asks to build, price, or analyze an options trade.",
    [
        {"name": "resolve_strategy", "description": "Parse the requested structure into named legs.", "expectedOutput": "A list of option legs with strikes and directions."},
        {"name": "price_legs", "description": "Price each leg using Black-Scholes.", "expectedOutput": "Premiums and Greeks per leg."},
        {"name": "compute_payoff", "description": "Calculate P&L at expiry across a spot price range.", "expectedOutput": "A payoff curve with breakeven points."},
    ],
    build_options_strategy, "Options Strategy",
))
_reg(SkillDef(
    "vol-term-structure", "Volatility Term Structure", "vol_term_structure",
    "Shows implied vol across monthly expiries as a term structure curve, highlighting "
    "contango or backwardation regime. Use when the user asks about VIX curve, vol term "
    "structure, or front-to-back volatility.",
    [
        {"name": "resolve_symbol", "description": "Map to a ticker or use VIX as index.", "expectedOutput": "A valid symbol."},
        {"name": "build_curve", "description": "Generate IV at each expiry with term structure dynamics.", "expectedOutput": "Ordered list of expiry/IV points."},
        {"name": "classify_regime", "description": "Determine contango, backwardation, or flat regime.", "expectedOutput": "A regime label and per-expiry flags."},
    ],
    build_vol_term_structure, "Vol Term Structure",
))
_reg(SkillDef(
    "structured-product", "Structured Product Pricer", "structured_product",
    "Prices a barrier/exotic option (down-and-out call, up-and-out call, etc.) using "
    "Black-Scholes with a scenario table showing P&L under various spot paths. Use when "
    "the user asks about barrier options, exotic products, or structured notes.",
    [
        {"name": "resolve_inputs", "description": "Parse barrier, tenor, notional and product type.", "expectedOutput": "Clean pricer inputs."},
        {"name": "price_barrier", "description": "Apply BS with barrier reflection to price the exotic.", "expectedOutput": "Fair value and Greeks."},
        {"name": "build_scenarios", "description": "Compute P&L under 9 spot-move scenarios.", "expectedOutput": "A scenario table with knock-out flags."},
    ],
    build_structured_product, "Structured Product",
))
_reg(SkillDef(
    "supply-chain", "Supply Chain Mapping", "supply_chain",
    "Generates an interactive supply-chain graph for a single company, showing key upstream "
    "suppliers and downstream customers with revenue exposure percentages. Use when the user "
    "asks about supply chain, vendors, or who buys from a company.",
    [
        {"name": "resolve_symbol", "description": "Map the request to a known ticker.", "expectedOutput": "A valid ticker."},
        {"name": "build_graph", "description": "Construct nodes and edges for suppliers, the subject, and customers.", "expectedOutput": "Nodes and edges with exposure weights."},
        {"name": "rank_table", "description": "Produce a ranked table of supply-chain relationships.", "expectedOutput": "A sorted table of relationships."},
    ],
    build_supply_chain, "Supply Chain",
))
_reg(SkillDef(
    "dcf-model", "DCF Valuation Model", "dcf_model",
    "Builds a discounted-cash-flow model for a single company with editable assumptions "
    "(revenue growth, EBITDA margin, WACC, exit multiple), projected FCF waterfall, and "
    "implied price range with sensitivity grid. Use when the user asks for a DCF, valuation, "
    "or intrinsic value.",
    [
        {"name": "resolve_symbol", "description": "Map the request to a known ticker.", "expectedOutput": "A valid ticker."},
        {"name": "set_assumptions", "description": "Derive plausible default assumptions from company financials.", "expectedOutput": "Revenue growth, margin, WACC, exit multiple."},
        {"name": "project_fcf", "description": "Project free cash flow for 5 years and discount to present value.", "expectedOutput": "5-year FCF projection table."},
        {"name": "build_sensitivity", "description": "Compute implied price across a WACC × exit-multiple grid.", "expectedOutput": "A 5×5 sensitivity heatmap."},
    ],
    build_dcf_model, "DCF Model",
))
_reg(SkillDef(
    "earnings-transcript", "Earnings Call Transcript", "earnings_transcript",
    "Synthesizes a realistic earnings call transcript for a company with sentiment scoring "
    "per paragraph, a sentiment timeline, and key management quote highlights. Use when the "
    "user asks what management said, what was discussed on the earnings call, or for transcript.",
    [
        {"name": "resolve_symbol", "description": "Map the request to a known ticker.", "expectedOutput": "A valid ticker."},
        {"name": "synthesize_transcript", "description": "Generate or retrieve curated transcript segments.", "expectedOutput": "Ordered list of speaker segments with sentiment scores."},
        {"name": "extract_key_quotes", "description": "Surface the highest-impact management statements.", "expectedOutput": "Up to 5 key quote cards."},
    ],
    build_earnings_transcript, "Earnings Transcript",
))
_reg(SkillDef(
    "earnings-calendar", "Earnings Calendar", "earnings_calendar",
    "Lists upcoming scheduled earnings report dates for a watchlist, a set of tickers, or a "
    "sector — each row carries the company, report date, before/after-market timing, a live "
    "countdown, the consensus EPS estimate and the fiscal quarter, and any company reporting "
    "within 24 hours is flagged. Use when the user asks for the earnings calendar, upcoming "
    "earnings, earnings dates/schedule, who reports next, or when a company reports.",
    [
        {"name": "resolve_watchlist", "description": "Resolve the set of tickers (explicit names, a sector, or the tracked watchlist).", "expectedOutput": "A list of tickers."},
        {"name": "schedule_reports", "description": "Compute each name's next scheduled report date, timing and EPS estimate.", "expectedOutput": "Dated rows sorted by soonest report."},
        {"name": "flag_imminent", "description": "Flag companies reporting within the next 24 hours.", "expectedOutput": "An imminent list plus the next report."},
    ],
    build_earnings_calendar, "Earnings Calendar",
))
_reg(SkillDef(
    "signal-research", "Alpha Signal Research", "signal_research",
    "Evaluates a single cross-sectional alpha signal (momentum, short-term reversal, "
    "low volatility, value, or quality) over a real universe: computes rank IC, IC decay "
    "across forward horizons, signal turnover, and a long-short decile/quintile spread "
    "equity curve from real price/fundamental data. Names missing data are excluded and "
    "reported, never imputed. Use when the user wants to research whether an alpha signal "
    "predicts returns, see its information coefficient, IC decay, turnover, or quantile spread.",
    [
        {"name": "resolve_signal", "description": "Map the request to a known signal (momentum, reversal, low-vol, value, quality).", "expectedOutput": "A registered signal key."},
        {"name": "select_universe", "description": "Resolve the cross-section from explicit names, a sector, or the liquid core.", "expectedOutput": "A capped list of tickers."},
        {"name": "evaluate_signal", "description": "Compute rank IC, IC decay, turnover and the long-short quantile spread from real series.", "expectedOutput": "IC stats, decay curve, turnover, spread equity curve and coverage."},
    ],
    build_signal_research, "Signal Research",
))
_reg(SkillDef(
    "signal-scorecard", "Alpha Signal Scorecard", "signal_scorecard",
    "Compares several alpha signals head-to-head over one shared universe and ranks them by "
    "IC information ratio, alongside mean IC, t-stat, hit rate, turnover and long-short spread "
    "performance. Use when the user wants to compare signals, rank alphas, or asks which signal "
    "works best (e.g. 'compare value vs momentum', 'signal scorecard').",
    [
        {"name": "resolve_signals", "description": "Resolve the set of signals to compare (defaults to the full library).", "expectedOutput": "A list of signal keys."},
        {"name": "select_universe", "description": "Resolve one shared cross-section for all signals.", "expectedOutput": "A capped list of tickers."},
        {"name": "rank_signals", "description": "Evaluate each signal on the same names and rank by IC information ratio.", "expectedOutput": "A ranked table of signal scorecard rows with spread sparklines."},
    ],
    build_signal_scorecard, "Signal Scorecard",
))


def _resolve_revenue_growth(symbol: str, company: dict) -> Optional[float]:
    """Live YoY revenue growth from the ingested fundamentals snapshot, falling
    back to the curated default when the live value is unavailable."""
    rg = company.get("revenueGrowth")
    if rg is not None:
        return rg
    return data.get_revenue_growth(symbol)


def _parse_iso_date(v) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _company_catalysts(symbol: str, company: dict) -> List[dict]:
    """Assemble the catalyst list, preferring real earnings/dividend dates from
    the live calendar feed and merging the curated editorial events behind them.

    Falls back entirely to the curated catalysts when no live date is available.
    """
    today = date.today()
    live: List[dict] = []

    ed = _parse_iso_date(company.get("earningsDate"))
    if ed and ed >= today:
        live.append({
            "event": "Next Earnings Report", "date": ed.isoformat(), "impact": "High",
            "description": "Scheduled quarterly earnings date from the live earnings calendar; "
                           "the magnitude of any beat or miss typically sets the near-term tone.",
        })
    xd = _parse_iso_date(company.get("exDividendDate"))
    if xd and xd >= today:
        live.append({
            "event": "Ex-Dividend Date", "date": xd.isoformat(), "impact": "Low",
            "description": "Shares begin trading ex-dividend; holders of record on this date "
                           "receive the upcoming payout.",
        })
    dd = _parse_iso_date(company.get("dividendDate"))
    if dd and dd >= today:
        live.append({
            "event": "Dividend Payment", "date": dd.isoformat(), "impact": "Low",
            "description": "Declared dividend payment date from the live calendar feed.",
        })

    static = data.get_catalysts(symbol)
    if not live:
        return static  # fallback-only: no live calendar data

    # Live earnings supersedes any curated earnings entry; keep the rest of the
    # editorial events (conferences, regulatory) since no free API supplies them.
    merged = list(live)
    for c in static:
        if "earning" in (c.get("event") or "").lower():
            continue
        merged.append(c)

    merged.sort(key=lambda c: _parse_iso_date(c.get("date")) or date.max)
    return merged[:6]


def _daily_returns_by_date(points: List[dict]) -> Dict[str, float]:
    """Map of ISO date -> daily simple return from a chronological close series."""
    out: Dict[str, float] = {}
    prev: Optional[float] = None
    for pt in points:
        c = pt.get("c")
        t = pt.get("t")
        if c is None or t is None:
            continue
        if prev is not None and prev > 0:
            out[t] = (c - prev) / prev
        prev = c
    return out


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def _company_correlations(symbol: str, peer_syms: List[str]) -> Optional[List[dict]]:
    """Rolling ~3M correlation of the subject's daily returns vs each peer's,
    computed from real OHLCV history. Returns None when the subject (or every
    peer) lacks live price history, so the caller can fall back to curated KPIs.
    """
    syms = [symbol] + [p for p in peer_syms if p and p != symbol]
    if len(syms) < 2:
        return None
    bulk = repo.closes_bulk(syms, days=90)
    series = bulk.get("series") or {}
    sources = bulk.get("sources") or {}

    if sources.get(symbol) != "live":
        return None
    subj = _daily_returns_by_date(series.get(symbol) or [])
    if len(subj) < 20:
        return None

    out: List[dict] = []
    for p in peer_syms:
        if p == symbol or sources.get(p) != "live":
            continue
        peer = _daily_returns_by_date(series.get(p) or [])
        keys = sorted(set(subj) & set(peer))
        if len(keys) < 20:
            continue
        r = _pearson([subj[k] for k in keys], [peer[k] for k in keys])
        if r is None:
            continue
        out.append({
            "metric": f"{p} price returns",
            "correlation": round(r, 2),
            "direction": "positive" if r >= 0 else "negative",
        })

    if not out:
        return None
    out.sort(key=lambda c: abs(c["correlation"]), reverse=True)
    return out[:5]


def _company_analytics_fallback(symbol: str, company: dict) -> dict:
    """Rules-based price drivers when AI is unavailable."""
    chg = company["changePct"]
    news = data.news_for("symbol", symbol)
    pos = sum(1 for n in news if n["sentiment"] == "positive")
    neg = sum(1 for n in news if n["sentiment"] == "negative")

    drivers = []
    if chg > 1.0:
        drivers.append({"title": "Positive price momentum", "tag": "bullish",
                        "explanation": f"{company['name']} is up {chg:.1f}% today, outperforming the market on strong near-term flow."})
    elif chg < -1.0:
        drivers.append({"title": "Negative price momentum", "tag": "bearish",
                        "explanation": f"{company['name']} is down {abs(chg):.1f}% today, underperforming on soft sentiment."})
    else:
        drivers.append({"title": "Flat price action", "tag": "neutral",
                        "explanation": f"{company['name']} is trading near flat, with no dominant directional catalyst."})

    if pos > neg:
        drivers.append({"title": "Positive news sentiment", "tag": "bullish",
                        "explanation": f"Recent headlines skew positive ({pos} positive vs {neg} negative), supporting near-term upside."})
    elif neg > pos:
        drivers.append({"title": "Negative news overhang", "tag": "bearish",
                        "explanation": f"Recent headlines skew negative ({neg} negative vs {pos} positive), creating a headwind."})

    if company["netMargin"] > 20:
        drivers.append({"title": "Strong margin profile", "tag": "bullish",
                        "explanation": f"Net margin of {company['netMargin']:.1f}% is well above sector norms, supporting valuation premium."})
    elif company["netMargin"] < 0:
        drivers.append({"title": "Unprofitable on a net basis", "tag": "bearish",
                        "explanation": f"Negative net margin of {company['netMargin']:.1f}% raises cash-burn concerns."})

    rev_growth = _resolve_revenue_growth(symbol, company) or 0.0
    if rev_growth > 20:
        drivers.append({"title": "High revenue growth", "tag": "bullish",
                        "explanation": f"Revenue growing {rev_growth:.1f}% YoY — well above average, justifying a growth premium."})
    elif rev_growth < -5:
        drivers.append({"title": "Revenue contraction", "tag": "bearish",
                        "explanation": f"Revenue declining {abs(rev_growth):.1f}% YoY — top-line headwinds weigh on sentiment."})

    if company.get("beta", 1.0) > 1.5:
        drivers.append({"title": "High-beta macro sensitivity", "tag": "neutral",
                        "explanation": f"Beta of {company['beta']:.2f} means outsized moves with the broader market."})

    return drivers[:5]


def build_company_analytics(params: dict) -> dict:
    symbol = (params.get("symbol") or "NVDA").upper()
    company = repo.get_company(symbol)
    if not company:
        raise ValueError(f"Unknown symbol: {symbol}")

    name = company["name"]
    chg_pct = company["changePct"]
    period_rets = repo.period_returns(symbol, windows=("1M", "YTD", "1Y"))["returns"]

    # --- Peers & competitive comparison ---
    peer_syms = data.get_peers(symbol)
    all_syms = [symbol] + peer_syms
    rev_growth = _resolve_revenue_growth(symbol, company)
    peers_table = []
    for sym in all_syms:
        c = repo.get_company(sym)
        if not c:
            continue
        rg = _resolve_revenue_growth(sym, c)
        mc_b = round(c["marketCap"] / 1_000_000_000, 1)
        peers_table.append({
            "symbol": sym,
            "name": c["name"],
            "isSubject": sym == symbol,
            "revenueGrowth": rg,
            "opMargin": c["netMargin"],
            "pe": c["peRatio"],
            "marketCapB": mc_b,
        })

    # --- KPI correlations (live rolling price correlations, curated fallback) ---
    correlations = _company_correlations(symbol, peer_syms) or data.get_kpi_correlations(symbol)

    # --- Catalysts (live earnings/dividend calendar merged with curated events) ---
    catalysts = _company_catalysts(symbol, company)

    # --- Price drivers (AI preferred, rules fallback) ---
    if ai.ai_available():
        try:
            news = repo.news_for("symbol", symbol)
            ctx = {
                "symbol": symbol,
                "name": name,
                "price": company["price"],
                "changePct": chg_pct,
                "peRatio": company["peRatio"],
                "netMargin": company["netMargin"],
                "revenueGrowthPct": rev_growth,
                "beta": company["beta"],
                "description": company["description"],
                "recentHeadlines": [{"headline": n["headline"], "sentiment": n["sentiment"]} for n in news[:5]],
            }
            prompt = (
                "You are an equity analyst. Using ONLY the data below, identify 3-5 specific "
                "reasons this stock is moving today (could be up or down). "
                "Respond with a single JSON object and nothing else: "
                '{"drivers": [{"title": string (max 6 words), "tag": "bullish"|"bearish"|"neutral", '
                '"explanation": string (1-2 sentences)}]}. '
                "Do not invent precise figures beyond what is provided.\n\nDATA:\n"
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
            drivers = parsed.get("drivers") or []
            if not drivers:
                raise ValueError("empty drivers")
            # Validate tags
            for d in drivers:
                if d.get("tag") not in ("bullish", "bearish", "neutral"):
                    d["tag"] = "neutral"
            drivers = drivers[:5]
        except Exception:
            drivers = _company_analytics_fallback(symbol, company)
    else:
        drivers = _company_analytics_fallback(symbol, company)

    return {
        "symbol": symbol,
        "name": name,
        "priceTrendPct": chg_pct,  # 1-day move
        "returns": {
            "1D": chg_pct,
            "1M": period_rets.get("1M"),
            "YTD": period_rets.get("YTD"),
            "1Y": period_rets.get("1Y"),
        },
        "drivers": drivers,
        "peers": peers_table,
        "correlations": correlations,
        "catalysts": catalysts,
        "asOf": company.get("_asOf"),
        "source": company.get("_source") or _live_source(),
    }


_reg(SkillDef(
    "ma-tracker", "M&A Deal Tracker", "ma_tracker",
    "Returns a deal tracker showing M&A activity with target, acquirer, deal value, premium, "
    "status, expected close date, and arb spread for pending deals. Use when the user asks "
    "about mergers, acquisitions, M&A deals, deal flow, or arb spreads.",
    [
        {"name": "filter_deals", "description": "Select relevant deals by sector or ticker.", "expectedOutput": "A filtered deal list."},
        {"name": "compute_arb_spread", "description": "Calculate annualized arb spread for pending deals.", "expectedOutput": "Arb spread percentage for each open deal."},
        {"name": "aggregate_stats", "description": "Compute summary statistics across the deal set.", "expectedOutput": "Total value, average premium, pending count."},
    ],
    build_ma_tracker, "M&A Tracker",
))
_reg(SkillDef(
    "company-analytics", "Company Analytics", "company_analytics",
    "Produces a deep-dive company analytics panel with four sections: Price Drivers (why the "
    "stock is moving, with bullish/bearish/neutral tags), Competitive Landscape (table comparing "
    "the company vs 2-3 peers across Revenue Growth, Operating Margin, P/E, and Market Cap), "
    "Metric Correlations (which KPIs most closely track this stock's price), and Catalyst Watch "
    "(upcoming events with High/Medium/Low impact labels). Use when the user asks 'why is X up', "
    "'why is X down', 'what drives X stock', 'analyze X vs competitors', 'company analytics for X', "
    "or 'competition for X'.",
    [
        {"name": "resolve_symbol", "description": "Map the request to a known ticker.", "expectedOutput": "A valid ticker."},
        {"name": "generate_price_drivers", "description": "Use the LLM to produce 3-5 price-driver bullets with tags from company fundamentals and news.", "expectedOutput": "A list of driver objects with title, tag, and explanation."},
        {"name": "build_competitive_table", "description": "Assemble peer comparison across revenue growth, operating margin, P/E, and market cap.", "expectedOutput": "A list of peer rows."},
        {"name": "rank_correlations", "description": "Return KPI-to-price correlations ranked by magnitude.", "expectedOutput": "Ordered list of metric/correlation pairs."},
        {"name": "list_catalysts", "description": "Return upcoming events with dates and High/Medium/Low impact labels.", "expectedOutput": "A catalyst list."},
    ],
    build_company_analytics, "Company Analytics",
))
_reg(SkillDef(
    "data-universe", "Data Universe", "data_universe",
    "Shows the formal investable universe: every tracked symbol with its sector, "
    "industry, listing venue, market cap, and data provenance (live vs catalog "
    "breadth), plus coverage statistics by sector and exchange. Use when the user "
    "asks what's covered, the universe, data coverage, which symbols are tracked, "
    "or which names have live vs mock data. Optionally filter by sector.",
    [
        {"name": "select_scope", "description": "Choose the whole universe or a single sector.", "expectedOutput": "A symbol set to summarize."},
        {"name": "assemble_rows", "description": "List symbols with sector, industry, venue, market cap and provenance.", "expectedOutput": "A ranked table of universe rows."},
        {"name": "compute_coverage", "description": "Aggregate live/mock/tracked counts by sector and exchange.", "expectedOutput": "Coverage summary statistics."},
    ],
    build_data_universe, "Data Universe",
))
_reg(SkillDef(
    "intraday-chart", "Intraday OHLCV", "intraday_chart",
    "Renders an intraday OHLCV chart for one ticker at a selectable resolution "
    "(1m, 5m, 15m, 30m, 1h) within the real limits of the data source, fetched "
    "live and labeled with the exact resolution and window served. When the "
    "requested window exceeds source limits it cleanly reports that the data is "
    "unavailable rather than substituting daily or synthetic bars. Use when the "
    "user wants intraday, minute, or hourly price action.",
    [
        {"name": "resolve_symbol", "description": "Map the request to a known ticker.", "expectedOutput": "A valid ticker."},
        {"name": "select_resolution", "description": "Pick an intraday resolution and window within source limits.", "expectedOutput": "An interval and range."},
        {"name": "fetch_intraday", "description": "Fetch live intraday bars (cached briefly) or report unavailable.", "expectedOutput": "An ordered list of intraday OHLCV points, or a clean unavailable state."},
    ],
    build_intraday_chart, "Intraday Chart",
))
_reg(SkillDef(
    "data-quality", "Data Quality", "data_quality",
    "Audits the OHLCV series behind one symbol, a sector, or the core set and "
    "reports data-quality findings: missing periods (gaps), stale freshness, "
    "rows with missing OHLC, zero-volume bars and duplicate timestamps, each "
    "tagged with its provenance. Audits the daily series by default; pass an "
    "intraday `interval` (e.g. 1m, 5m, 15m, 30m, 1h) to audit minute/hour bars "
    "instead, with an optional `range` window. Use when the user asks about data "
    "quality, data gaps, stale data, freshness, intraday/minute-bar quality, or "
    "whether the data can be trusted.",
    [
        {"name": "select_series", "description": "Choose the symbol(s) and resolution to audit.", "expectedOutput": "A set of series to validate at a daily or intraday interval."},
        {"name": "run_checks", "description": "Detect gaps, staleness, NaN/zero-volume and duplicate timestamps.", "expectedOutput": "Per-series quality counts and issues."},
        {"name": "summarize", "description": "Aggregate clean vs flagged vs mock vs unavailable series.", "expectedOutput": "A quality summary."},
    ],
    build_data_quality, "Data Quality",
))


# ----------------------------- analyst report -----------------------------
def _stance_from_figures(returns: dict, change_pct: Optional[float]) -> str:
    """Crude directional read from recent returns when the AI is unavailable."""
    signals = []
    for k in ("1M", "YTD", "1Y"):
        v = returns.get(k)
        if v is not None:
            signals.append(v)
    if change_pct is not None:
        signals.append(change_pct)
    if not signals:
        return "neutral"
    avg = sum(signals) / len(signals)
    if avg >= 5:
        return "bullish"
    if avg <= -5:
        return "bearish"
    return "neutral"


def _analyst_report_fallback(scope: str, scope_type: str, figures: List[dict],
                             returns: dict, change_pct: Optional[float],
                             peers: List[dict], news: List[dict],
                             catalysts: List[dict]) -> dict:
    """Rules-based analyst write-up used when the AI is unavailable or errors."""
    stance = _stance_from_figures(returns, change_pct)
    ytd = returns.get("YTD")
    one_y = returns.get("1Y")
    move = "advanced" if (ytd or 0) >= 0 else "declined"
    thesis = (
        f"{scope} has {move} {abs(ytd):.1f}% year-to-date" if ytd is not None
        else f"{scope} sits in a mixed tape"
    )
    if one_y is not None:
        thesis += f" and is {one_y:+.1f}% over the trailing year"
    thesis += ". The read below is a rules-based summary built from the panel's grounding figures."

    drivers = []
    for f in figures[:3]:
        drivers.append({"title": f["label"], "detail": f"Currently {f['value']}."})
    if not drivers:
        drivers.append({"title": "Price trend", "detail": "Recent performance is the primary observable driver."})

    risks = [
        {"title": "Macro sensitivity", "detail": "Rates, liquidity and broad risk appetite can override company specifics."},
        {"title": "Estimate revisions", "detail": "Forward numbers may re-rate the multiple in either direction."},
    ]
    cats = [{"title": c.get("event", "Upcoming event"), "detail": c.get("date", "")} for c in catalysts[:3]]
    if not cats:
        cats = [{"title": "Next earnings", "detail": "Scheduled results are the most likely near-term catalyst."}]

    return {
        "stance": stance,
        "conviction": 0.45,
        "headline": f"{scope}: {stance.title()} on recent trend",
        "thesis": thesis,
        "drivers": drivers,
        "risks": risks,
        "catalysts": cats,
        "valuation": "Valuation read unavailable without AI; refer to the cited multiples in the figures strip.",
        "call": f"Rules-based stance is {stance}; treat as a low-conviction, data-only summary.",
    }


def build_analyst_report(params: dict) -> dict:
    """Deeper, structured analyst write-up grounded in the terminal's own data.

    Scope is a single ticker (preferred), a sector, or the whole DASHBOARD — a
    portfolio-level review aggregated across the symbols/sectors currently on
    screen (pass scope='dashboard' with symbols/sectors). The AI produces a
    thesis, drivers, risks, catalysts, a valuation read and an explicit
    bull/bear/neutral call; on any failure it degrades to a rules-based summary
    over the same data.
    """
    symbol = (params.get("symbol") or "").upper().strip()
    sector = params.get("sector")
    dash_symbols = [str(s).upper().strip() for s in (params.get("symbols") or []) if str(s).strip()]
    dash_sectors = [str(s) for s in (params.get("sectors") or []) if str(s).strip()]
    scope_pref = (params.get("scope") or "").lower().strip()
    if symbol:
        scope_type = "symbol"
    elif sector:
        scope_type = "sector"
    elif scope_pref == "dashboard" or dash_symbols or dash_sectors:
        scope_type = "dashboard"
    else:
        raise ValueError(
            "An analyst report needs a ticker, a sector, or an active dashboard to analyze."
        )

    figures: List[dict] = []
    returns: dict = {}
    change_pct: Optional[float] = None
    peers: List[dict] = []
    catalysts: List[dict] = []
    news: List[dict] = []
    as_of = None
    source = _live_source()

    if scope_type == "symbol":
        company = repo.get_company(symbol)
        if not company:
            raise ValueError(f"Unknown symbol: {symbol}")
        scope = company["name"]
        change_pct = company.get("changePct")
        ret_meta = repo.period_returns(symbol, windows=("1M", "YTD", "1Y"))
        returns = ret_meta["returns"]
        as_of = company.get("_asOf") or ret_meta.get("asOf")
        source = company.get("_source") or ret_meta.get("source") or source
        rev_growth = data.get_revenue_growth(symbol)
        figures = [
            {"label": "Price", "value": f"${company['price']:,.2f}"},
            {"label": "1D", "value": f"{change_pct:+.2f}%" if change_pct is not None else "n/a"},
            {"label": "YTD", "value": f"{returns.get('YTD'):+.1f}%" if returns.get("YTD") is not None else "n/a"},
            {"label": "1Y", "value": f"{returns.get('1Y'):+.1f}%" if returns.get("1Y") is not None else "n/a"},
            {"label": "P/E", "value": f"{company['peRatio']:.1f}" if company.get("peRatio") else "n/a"},
            {"label": "Net margin", "value": f"{company['netMargin']:.1f}%" if company.get("netMargin") is not None else "n/a"},
            {"label": "Rev growth", "value": f"{rev_growth:+.1f}%" if rev_growth is not None else "n/a"},
            {"label": "Beta", "value": f"{company['beta']:.2f}" if company.get("beta") is not None else "n/a"},
        ]
        peer_syms = data.get_peers(symbol)
        for ps in peer_syms[:3]:
            c = repo.get_company(ps)
            if c:
                peers.append({"symbol": ps, "name": c["name"], "pe": c.get("peRatio"), "netMargin": c.get("netMargin")})
        catalysts = data.get_catalysts(symbol)
        news = repo.news_for("symbol", symbol)
        ctx_extra = {
            "description": company.get("description"),
            "marketCapB": round(company["marketCap"] / 1_000_000_000, 1) if company.get("marketCap") else None,
            "revenueGrowthPct": rev_growth,
        }
    elif scope_type == "sector":
        scope = repo.sector_name(sector)
        syms = repo.symbols_in_sector(sector)[:6]
        ret_bulk = repo.period_returns_bulk(syms, windows=("YTD", "1Y"))
        ytds = [r.get("YTD") for r in ret_bulk.values() if r.get("YTD") is not None]
        oneys = [r.get("1Y") for r in ret_bulk.values() if r.get("1Y") is not None]
        returns = {
            "YTD": round(sum(ytds) / len(ytds), 1) if ytds else None,
            "1Y": round(sum(oneys) / len(oneys), 1) if oneys else None,
        }
        figures = [
            {"label": "Names", "value": str(len(syms))},
            {"label": "Avg YTD", "value": f"{returns['YTD']:+.1f}%" if returns.get("YTD") is not None else "n/a"},
            {"label": "Avg 1Y", "value": f"{returns['1Y']:+.1f}%" if returns.get("1Y") is not None else "n/a"},
        ]
        for ps in syms[:4]:
            c = repo.get_company(ps)
            if c:
                peers.append({"symbol": ps, "name": c["name"], "pe": c.get("peRatio"), "netMargin": c.get("netMargin")})
        news = repo.news_for("sector", sector)
        ctx_extra = {"members": [p["symbol"] for p in peers]}
    else:
        # Dashboard scope: aggregate across the names/sectors currently on screen.
        syms = []
        seen = set()
        for s in dash_symbols:
            if s not in seen and repo.get_company(s):
                seen.add(s)
                syms.append(s)
        for sec in dash_sectors:
            for s in repo.symbols_in_sector(sec):
                if s not in seen and repo.get_company(s):
                    seen.add(s)
                    syms.append(s)
        syms = syms[:8]
        if not syms:
            raise ValueError("No recognizable holdings on the dashboard to analyze.")
        scope = "Your Dashboard"
        ret_bulk = repo.period_returns_bulk(syms, windows=("YTD", "1Y"))
        ytds = [r.get("YTD") for r in ret_bulk.values() if r.get("YTD") is not None]
        oneys = [r.get("1Y") for r in ret_bulk.values() if r.get("1Y") is not None]
        returns = {
            "YTD": round(sum(ytds) / len(ytds), 1) if ytds else None,
            "1Y": round(sum(oneys) / len(oneys), 1) if oneys else None,
        }
        winners = sum(1 for v in ytds if v > 0)
        figures = [
            {"label": "Names", "value": str(len(syms))},
            {"label": "Avg YTD", "value": f"{returns['YTD']:+.1f}%" if returns.get("YTD") is not None else "n/a"},
            {"label": "Avg 1Y", "value": f"{returns['1Y']:+.1f}%" if returns.get("1Y") is not None else "n/a"},
            {"label": "Breadth", "value": f"{winners}/{len(ytds)} up YTD" if ytds else "n/a"},
        ]
        for ps in syms[:6]:
            c = repo.get_company(ps)
            if c:
                peers.append({"symbol": ps, "name": c["name"], "pe": c.get("peRatio"), "netMargin": c.get("netMargin")})
                if c.get("_asOf"):
                    as_of = c["_asOf"] if as_of is None else max(as_of, c["_asOf"])
                source = c.get("_source") or source
        for ps in syms[:4]:
            news.extend(repo.news_for("symbol", ps)[:2])
        ctx_extra = {"members": [p["symbol"] for p in peers], "sectors": dash_sectors or None}

    report: Optional[dict] = None
    if ai.ai_available():
        try:
            ctx = {
                "scope": scope,
                "scopeType": scope_type,
                "figures": figures,
                "returns": returns,
                "changePct": change_pct,
                "peers": peers,
                "recentHeadlines": [{"headline": n["headline"], "sentiment": n.get("sentiment")} for n in news[:6]],
                "catalysts": [{"event": c.get("event"), "date": c.get("date"), "impact": c.get("impact")} for c in catalysts[:5]],
                **ctx_extra,
            }
            scope_note = (
                "This is a PORTFOLIO-LEVEL review across the names currently on the user's "
                "dashboard; write the thesis, drivers, risks, catalysts and call about the "
                "dashboard as a whole, not a single stock.\n" if scope_type == "dashboard" else ""
            )
            prompt = (
                "You are a buy-side equity analyst. Write a structured analyst take using ONLY "
                "the data below. Do NOT invent precise figures beyond what is provided; you may "
                "reason qualitatively. Respond with a single JSON object and nothing else:\n"
                '{"headline": string (max 10 words), '
                '"stance": "bullish"|"bearish"|"neutral", '
                '"conviction": number between 0 and 1, '
                '"thesis": string (2-4 sentences), '
                '"drivers": [{"title": string (max 6 words), "detail": string (1-2 sentences)}] (2-4 items), '
                '"risks": [{"title": string (max 6 words), "detail": string (1-2 sentences)}] (2-4 items), '
                '"catalysts": [{"title": string (max 6 words), "detail": string}] (1-4 items), '
                '"valuation": string (1-3 sentences referencing the multiples provided), '
                '"call": string (1-2 sentences, an explicit actionable view)}\n\n'
                + scope_note
                + "DATA:\n"
                + json.dumps(ctx, default=str)
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
            if parsed.get("stance") not in ("bullish", "bearish", "neutral"):
                parsed["stance"] = _stance_from_figures(returns, change_pct)
            try:
                parsed["conviction"] = max(0.0, min(1.0, float(parsed.get("conviction", 0.5))))
            except (TypeError, ValueError):
                parsed["conviction"] = 0.5
            if not parsed.get("thesis") or not parsed.get("drivers"):
                raise ValueError("incomplete report")
            report = parsed
        except Exception:
            report = None

    if report is None:
        report = _analyst_report_fallback(scope, scope_type, figures, returns, change_pct, peers, news, catalysts)

    report.update({
        "scope": scope,
        "scopeType": scope_type,
        "symbol": symbol or None,
        "sector": sector,
        "figures": figures,
        "asOf": as_of,
        "source": source,
    })
    return report


# ----------------------------- what-if scenario -----------------------------
def _scenario_parse_heuristic(prompt: str, symbols: List[str]) -> dict:
    """Extract a coarse drift estimate and assumptions from a what-if prompt.

    Used when the AI is unavailable. Reads magnitudes (bps, %), a direction, and
    horizon hints, then maps them to a rough annualized return impact.
    """
    import re as _re
    q = (prompt or "").lower()

    horizon = 252
    m = _re.search(r"(\d+)\s*(year|yr)", q)
    if m:
        horizon = max(21, min(252 * 5, int(m.group(1)) * 252))
    else:
        m = _re.search(r"(\d+)\s*(month|mo)", q)
        if m:
            horizon = max(21, min(252 * 5, int(m.group(1)) * 21))

    impact = 0.0
    assumptions: List[dict] = []

    for m in _re.finditer(r"(\d+(?:\.\d+)?)\s*bps", q):
        bps = float(m.group(1))
        # Rate moves: falling rates broadly positive for equities, rising negative.
        sign = 1.0 if any(w in q for w in ["fall", "cut", "lower", "drop", "down", "ease"]) else -1.0
        contrib = sign * (bps / 100.0) * 4.0  # ~4% equity impact per 100bps move
        impact += contrib
        assumptions.append({
            "label": f"Rates move {int(bps)}bps",
            "detail": f"Estimated {contrib:+.1f}% annualized equity impact.",
            "impactPct": round(contrib, 1),
        })

    for m in _re.finditer(r"(\d+(?:\.\d+)?)\s*%", q):
        pct = float(m.group(1))
        if "bps" in q[max(0, m.start() - 6):m.start() + 1]:
            continue
        neg = any(w in q for w in ["compress", "fall", "drop", "cut", "decline", "down", "lower", "shrink"])
        sign = -1.0 if neg else 1.0
        contrib = sign * min(pct, 50.0) * 0.4  # dampened pass-through to return
        impact += contrib
        assumptions.append({
            "label": f"{pct:g}% shift",
            "detail": f"Estimated {contrib:+.1f}% annualized impact (dampened pass-through).",
            "impactPct": round(contrib, 1),
        })

    if not assumptions:
        neg = any(w in q for w in ["recession", "selloff", "crash", "bear", "downturn", "compress"])
        contrib = -8.0 if neg else 6.0
        impact = contrib
        assumptions.append({
            "label": "Directional what-if",
            "detail": f"No explicit magnitude found; assumed {contrib:+.1f}% annualized tilt.",
            "impactPct": contrib,
        })

    impact = max(-60.0, min(60.0, impact))
    return {"horizonDays": horizon, "driftPct": round(impact, 1), "assumptions": assumptions, "caveats": [
        "Heuristic estimate (AI unavailable): magnitudes mapped by simple rules of thumb.",
    ]}


def _scenario_parse_llm(prompt: str, symbols: List[str], scope_label: str) -> dict:
    ctx = {"whatIf": prompt, "symbols": symbols, "scope": scope_label}
    sys = (
        "You translate a natural-language investing what-if into structured assumptions for a "
        "forward simulation. The baseline path is generated separately from REAL price history; "
        "your job is only to estimate the INCREMENTAL impact of the user's assumptions. "
        "Respond with a single JSON object and nothing else:\n"
        '{"horizonDays": integer (21-1260, default 252), '
        '"driftPct": number (total INCREMENTAL annualized total-return impact of all assumptions, '
        'positive or negative, realistic magnitude, clamp to [-60, 60]), '
        '"assumptions": [{"label": string (max 8 words), "detail": string (1 sentence with the reasoning), '
        '"impactPct": number (this assumption\'s share of driftPct)}] (1-5 items), '
        '"reasoning": string (2-4 sentences explaining how the assumptions drive the projected outcome), '
        '"caveats": [string] (2-4 short caveats about model limits and uncertainty)}'
    )
    msg = ai.chat(
        [
            {"role": "system", "content": sys},
            {"role": "user", "content": json.dumps(ctx)},
        ],
        response_format={"type": "json_object"},
    )
    content = (msg.content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
    parsed = json.loads(content)
    drift = float(parsed.get("driftPct", 0.0))
    parsed["driftPct"] = max(-60.0, min(60.0, drift))
    h = int(parsed.get("horizonDays", 252) or 252)
    parsed["horizonDays"] = max(21, min(1260, h))
    if not parsed.get("assumptions"):
        raise ValueError("no assumptions parsed")
    return parsed


def build_scenario(params: dict) -> dict:
    """What-if / scenario reasoning grounded in the simulation engine.

    Parses a natural-language what-if into structured assumptions (AI preferred,
    heuristic fallback), runs a baseline forward projection from REAL returns via
    the Monte Carlo engine, and layers the assumptions' estimated drift on top to
    produce a scenario projection with inputs, outcome, reasoning and caveats.
    """
    prompt = (params.get("prompt") or params.get("query") or "").strip()
    symbol = (params.get("symbol") or "").upper().strip()
    sector = params.get("sector")

    symbols: List[str] = []
    weights: Optional[List[float]] = None
    if symbol:
        symbols = [symbol]
    elif params.get("symbols"):
        symbols = [str(s).upper() for s in params["symbols"]][:6]
    elif sector:
        symbols = repo.symbols_in_sector(sector)[:5]

    proxy_note = None
    if not symbols:
        symbols = ["NVDA", "MSFT", "AAPL", "GOOGL", "AMZN"]
        proxy_note = "No specific asset detected; using a mega-cap basket as a market proxy."

    scope_label = (
        repo.get_company(symbols[0])["name"] if len(symbols) == 1 and repo.get_company(symbols[0])
        else (repo.sector_name(sector) if sector else f"{len(symbols)}-name basket")
    )

    # 1) Parse assumptions (AI preferred, heuristic fallback).
    parsed = None
    basis = "grounded"
    if ai.ai_available():
        try:
            parsed = _scenario_parse_llm(prompt, symbols, scope_label)
        except Exception:
            parsed = None
    if parsed is None:
        parsed = _scenario_parse_heuristic(prompt, symbols)
        basis = "estimated"

    horizon = int(parsed.get("horizonDays", 252) or 252)
    drift_pct = float(parsed.get("driftPct", 0.0))

    # 2) Build a baseline return series from REAL price history.
    series: List[List[float]] = []
    used_symbols: List[str] = []
    as_of = None
    source = "mock"
    for s in symbols:
        meta = repo.price_series_meta(s, days=400)
        pts = meta.get("points") or []
        closes = [p["c"] for p in pts if p.get("c")]
        if len(closes) >= 6:
            rets = [(closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes))]
            series.append(rets)
            used_symbols.append(s)
            if meta.get("source") == "live":
                source = "live"
            if meta.get("asOf"):
                as_of = meta["asOf"] if as_of is None else max(as_of, meta["asOf"])

    projection = None
    if series:
        try:
            basket = engine.combine_returns(series, weights)
            projection = engine.project_scenario(
                basket.tolist(), drift_pct, horizon=horizon, method="bootstrap",
            )
        except Exception:
            projection = None

    if projection is None:
        # Pure AI-reasoned outcome with no grounded path (degraded, but explicit).
        basis = "estimated"

    caveats = list(parsed.get("caveats") or [])
    if proxy_note:
        caveats.insert(0, proxy_note)
    if basis == "estimated" and "AI unavailable" not in " ".join(caveats):
        caveats.append("Scenario delta is an estimate layered on the baseline, not a guaranteed outcome.")
    if not caveats:
        caveats = ["Projections are illustrative, assume the stated shock in isolation, and exclude transaction costs."]

    return {
        "prompt": prompt or "Scenario analysis",
        "scope": scope_label,
        "symbols": used_symbols or symbols,
        "horizonDays": horizon,
        "basis": basis if projection else "estimated",
        "driftPct": round(drift_pct, 1),
        "assumptions": parsed.get("assumptions") or [],
        "reasoning": parsed.get("reasoning") or (
            f"Assumptions sum to an estimated {drift_pct:+.1f}% annualized impact, applied on top of a "
            "baseline projected from real return history."
        ),
        "caveats": caveats[:5],
        "projection": projection,
        "asOf": as_of,
        "source": source if projection else _live_source(),
    }


_reg(SkillDef(
    "analyst-report", "AI Analyst Report", "analyst_report",
    "Produces a deep, structured analyst write-up for a ticker (or sector): a headline, an explicit "
    "bull/bear/neutral STANCE with a conviction score, a multi-sentence THESIS, and sections for "
    "DRIVERS, RISKS, CATALYSTS, a VALUATION read, and a clear actionable CALL — all grounded in the "
    "terminal's own figures (price, returns, multiples, peers, news, catalysts). Use when the user "
    "asks for an 'analyst take', 'deep analysis', 'write-up', 'bull/bear case', 'investment thesis', "
    "'should I buy/sell X', or 'give me your view on X'. This is ADDITIVE to the lighter `analysis` panel.",
    [
        {"name": "gather_grounding", "description": "Collect price, returns, multiples, peers, news and catalysts for the scope.", "expectedOutput": "A grounding context object."},
        {"name": "write_thesis", "description": "Use the LLM to write a structured thesis with stance and conviction.", "expectedOutput": "A headline, stance, conviction and thesis."},
        {"name": "structure_sections", "description": "Produce drivers, risks, catalysts, a valuation read and a call.", "expectedOutput": "Sectioned analyst content."},
    ],
    build_analyst_report, "Analyst Report",
))
_reg(SkillDef(
    "scenario", "What-If Scenario", "scenario",
    "Parses a natural-language what-if ('if rates fall 100bps then...', 'if NVDA margins compress to "
    "40%', 'what if I rotate into semis') into structured assumptions, runs a BASELINE forward "
    "projection from real return history through the Monte Carlo engine, and layers the assumptions' "
    "estimated drift on top to produce a SCENARIO projection. Renders inputs, baseline vs scenario "
    "outcome, divergent projected paths, reasoning and caveats. Use when the user poses a hypothetical, "
    "says 'what if', 'if I do X then Y', 'scenario where', 'suppose', or asks to stress a shock. "
    "Degrades cleanly to a reasoned estimate on AI timeout.",
    [
        {"name": "parse_assumptions", "description": "Translate the what-if into structured assumptions and an incremental drift estimate.", "expectedOutput": "Assumptions with per-item impact and a horizon."},
        {"name": "project_baseline", "description": "Build a baseline forward projection from real returns via Monte Carlo.", "expectedOutput": "A grounded baseline path and distribution."},
        {"name": "apply_scenario", "description": "Layer the estimated drift on the baseline to produce the scenario path.", "expectedOutput": "A scenario projection with delta vs baseline."},
    ],
    build_scenario, "What-If Scenario",
))
_reg(SkillDef(
    "performance-pnl", "Performance & P&L", "performance_pnl",
    "Computes a book's realized P&L over a window against a REAL, traded benchmark ETF (default SPY; "
    "configurable e.g. QQQ/IWM) sourced through the real price path and date-aligned to the book: "
    "cumulative book vs benchmark curves, the drawdown path, and a full "
    "risk/return stat block (total return, vol, Sharpe, Sortino, max drawdown, hit rate) plus active "
    "stats (active return, tracking error, information ratio, beta, alpha, up/down capture). Use when the "
    "user asks for performance, P&L, returns vs a benchmark, or risk-adjusted return of a portfolio/book.",
    [
        {"name": "assemble_book", "description": "Resolve the holdings and align real return history for the window.", "expectedOutput": "An aligned (T,N) return panel and book weights."},
        {"name": "build_benchmark", "description": "Fetch the real benchmark ETF's price series and align its returns to the window.", "expectedOutput": "A real, date-aligned benchmark daily return series."},
        {"name": "compute_stats", "description": "Compute risk/return and active statistics over the window.", "expectedOutput": "Book, benchmark and active stat blocks plus series."},
    ],
    build_performance_pnl, "Performance & P&L",
))
_reg(SkillDef(
    "brinson-attribution", "Brinson Attribution", "brinson_attribution",
    "Decomposes a book's active return versus a sector-aware REAL benchmark — each sector mapped to a real, "
    "traded sector/industry ETF (e.g. XLK/XLF/XLE) whose window return is sourced through the real price path — "
    "into Brinson-Hood-Beebower allocation, selection and interaction effects by sector. Allocation + selection "
    "+ interaction sum exactly to the active return. Sectors without a real ETF are excluded and reported. Use "
    "when the user asks where active return came from, allocation vs selection, sector attribution, or Brinson.",
    [
        {"name": "sector_weights", "description": "Compute portfolio and real sector-ETF benchmark weights and returns.", "expectedOutput": "Per-sector weights and single-period returns."},
        {"name": "decompose", "description": "Apply BHB to split active return into allocation/selection/interaction.", "expectedOutput": "Per-sector effects that sum to active return."},
    ],
    build_brinson_attribution, "Brinson Attribution",
))
_reg(SkillDef(
    "factor-attribution", "Factor Attribution", "factor_attribution",
    "Decomposes a book's realized window return into per-factor contributions (exposure times cumulative "
    "factor return) plus a specific/idiosyncratic return, using the estimated multi-factor model. Factor "
    "contributions plus specific reconstruct the realized return. Use when the user asks what factors drove "
    "returns, factor attribution, or factor-based return decomposition of a portfolio.",
    [
        {"name": "estimate_model", "description": "Estimate factor returns and the book's factor exposures from real data.", "expectedOutput": "An exposure vector and a factor-return panel."},
        {"name": "decompose", "description": "Attribute realized return to each factor and a specific term.", "expectedOutput": "Per-factor contributions plus a specific return."},
    ],
    build_factor_attribution, "Factor Attribution",
))
_reg(SkillDef(
    "tear-sheet", "Performance Tear Sheet", "tear_sheet",
    "Combines P&L vs a REAL benchmark, the drawdown path, the full risk/return + active stat block, Brinson "
    "sector attribution and factor attribution into a single tear sheet. Use when the user asks for a tear "
    "sheet, a full performance review, or a combined performance and attribution report for a book.",
    [
        {"name": "compute_performance", "description": "Build P&L, drawdown and the risk/return + active stats vs a real benchmark.", "expectedOutput": "Series and stat blocks."},
        {"name": "attribute_active", "description": "Run Brinson sector attribution on the active return.", "expectedOutput": "Per-sector allocation/selection/interaction."},
        {"name": "attribute_factors", "description": "Decompose realized return into factor contributions and specific.", "expectedOutput": "Per-factor contributions plus specific."},
    ],
    build_tear_sheet, "Performance Tear Sheet",
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
