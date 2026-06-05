"""Skill registry. Each panel type is a skill with a descriptive setup and
subskills, plus a builder that turns resolved params into panel `data`.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

from . import ai, data, db, engine, repo

RANGE_DAYS = {"1M": 30, "3M": 90, "6M": 180, "1Y": 250, "YTD": 120}


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
    days = RANGE_DAYS.get(rng, 90)
    points = repo.price_series(symbol, days=days)
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
        "asOf": company.get("_asOf"),
        "source": company.get("_source"),
    }


def build_news(params: dict) -> dict:
    scope_type = params.get("scope_type") or ("symbol" if params.get("symbol") else "sector")
    scope = params.get("scope") or params.get("symbol") or params.get("sector") or "ai_tech"
    items = repo.news_for(scope_type, scope)
    if scope_type == "symbol":
        company = repo.get_company(scope.upper())
        label = company["name"] if company else scope.upper()
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


def build_screener(params: dict) -> dict:
    sector = params.get("sector")
    sid = repo.resolve_sector(sector) if sector else None
    if sid:
        syms = repo.symbols_in_sector(sid)
        title = f"{repo.sector_name(sid)} Screener"
    else:
        syms = repo.all_symbols()
        title = "Market Screener"
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
    sector = params.get("sector") or params.get("scope")
    sid = repo.resolve_sector(sector) if sector else None
    if sid:
        syms = repo.symbols_in_sector(sid)
        title = f"{repo.sector_name(sid)} Heatmap"
    else:
        syms = repo.all_symbols()
        title = "Market Overview"
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

    # Factor exposures: Market beta is the real cap-weighted-ish average beta of
    # the holdings; the remaining style tilts are deterministic approximations.
    betas = {s: repo.get_company(s)["beta"] for s in symbols}
    avg_beta = round(sum(betas.values()) / len(betas), 2)
    seed = data._seed("_".join(sorted(symbols)))

    def rnd():
        nonlocal seed
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    factor_exposures = [
        {"factor": "Market", "exposure": round(avg_beta, 2)},
        {"factor": "Momentum", "exposure": round(0.3 + rnd() * 0.5, 2)},
        {"factor": "Size", "exposure": round(-0.2 + rnd() * 0.4, 2)},
        {"factor": "Value", "exposure": round(-0.4 + rnd() * 0.4, 2)},
        {"factor": "Quality", "exposure": round(0.1 + rnd() * 0.5, 2)},
        {"factor": "Volatility", "exposure": round(0.2 + rnd() * 0.4, 2)},
    ]

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


def build_tca_report(params: dict) -> dict:
    symbol = (params.get("symbol") or "NVDA").upper()
    company = data.get_company(symbol)
    if not company:
        raise ValueError(f"Unknown symbol: {symbol}")
    last = company["price"]
    seed = data._seed(symbol + "tca")

    def _rnd():
        nonlocal seed
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    arrival = round(last * (1 - 0.003 + _rnd() * 0.002), 2)
    vwap = round(arrival * (1 + (_rnd() - 0.5) * 0.004), 2)
    twap = round(arrival * (1 + (_rnd() - 0.5) * 0.003), 2)

    buckets = []
    times = ["09:30", "10:00", "10:30", "11:00", "11:30", "12:00",
             "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30"]
    exec_prices = []
    bucket_vol = company["volume"] / len(times)

    price_walk = arrival
    for i, t in enumerate(times):
        price_walk = round(price_walk * (1 + (_rnd() - 0.49) * 0.003), 2)
        bvwap = round(vwap * (1 + (_rnd() - 0.5) * 0.002), 2)
        btwap = round(twap * (1 + (_rnd() - 0.5) * 0.0015), 2)
        part_rate = round(0.04 + _rnd() * 0.12, 3)
        vol = round(bucket_vol * (0.7 + _rnd() * 0.6), 0)
        buckets.append({
            "time": t,
            "execPrice": price_walk,
            "vwap": bvwap,
            "twap": btwap,
            "participationRate": part_rate,
            "volume": vol,
        })
        exec_prices.append(price_walk)

    avg_exec = round(sum(exec_prices) / len(exec_prices), 2)
    impl_shortfall = round(abs(avg_exec - arrival) / arrival * 10000, 2)
    vwap_slippage = round(abs(avg_exec - vwap) / vwap * 10000, 2)
    twap_slippage = round(abs(avg_exec - twap) / twap * 10000, 2)

    return {
        "symbol": symbol,
        "name": company["name"],
        "arrivalPrice": arrival,
        "avgExecPrice": avg_exec,
        "vwap": vwap,
        "twap": twap,
        "implementationShortfall": impl_shortfall,
        "vwapSlippage": vwap_slippage,
        "twapSlippage": twap_slippage,
        "buckets": buckets,
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
    symbol = (params.get("symbol") or "AAPL").upper()
    company = data.get_company(symbol)
    if not company:
        symbol = "AAPL"
        company = data.get_company(symbol)
    
    seed = data._seed(symbol + "factor")

    def rnd():
        nonlocal seed
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    factors = ["Momentum", "Value", "Size", "Quality", "Residual"]
    attribution = []
    today = date.today()
    for i in range(12):
        month = (today - timedelta(days=30 * (11 - i))).strftime("%b %y")
        # Ensure they sum to something reasonable
        vals = {f: round((rnd() - 0.5) * 4.0, 2) for f in factors}
        attribution.append({"month": month, **vals})

    loadings = []
    for f in factors[:-1]: # exclude residual for loadings
        loading = round(rnd() * 1.5, 2)
        t_stat = round(1.5 + rnd() * 3.0, 2)
        loadings.append({
            "factor": f,
            "loading": loading,
            "tStat": t_stat,
            "contribution": round(loading * 10, 1)
        })

    return {
        "symbol": symbol,
        "name": company["name"],
        "monthlyAttribution": attribution,
        "loadings": loadings
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
        return {"symbol": symbol, "name": company["name"], "nodes": nodes, "edges": edges, "table": table}

    return _generate_supply_chain(symbol, company)


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
    "tca-report", "Transaction Cost Analysis", "tca_report",
    "Compares execution price to VWAP/TWAP benchmarks and breaks down participation rate across "
    "intraday 30-minute buckets. Use when the user asks about TCA, execution quality, slippage, "
    "or implementation shortfall.",
    [
        {"name": "resolve_symbol", "description": "Map the request to a known ticker.", "expectedOutput": "A valid ticker."},
        {"name": "compute_benchmarks", "description": "Derive arrival price, VWAP, TWAP and average execution price.", "expectedOutput": "Benchmark comparison values."},
        {"name": "build_buckets", "description": "Break execution into 30-minute intraday buckets with participation rate.", "expectedOutput": "A list of bucket records."},
    ],
    build_tca_report, "TCA Report",
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

    rev_growth = data.get_revenue_growth(symbol) or 0.0
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
    rev_growth = data.get_revenue_growth(symbol)
    peers_table = []
    for sym in all_syms:
        c = repo.get_company(sym)
        if not c:
            continue
        rg = data.get_revenue_growth(sym)
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

    # --- KPI correlations ---
    correlations = data.get_kpi_correlations(symbol)

    # --- Catalysts ---
    catalysts = data.get_catalysts(symbol)

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
