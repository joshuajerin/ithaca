"""Skill registry. Each panel type is a skill with a descriptive setup and
subskills, plus a builder that turns resolved params into panel `data`.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

from . import ai, data, db, repo

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


# ----------------------------- builders -----------------------------
def build_price_chart(params: dict) -> dict:
    symbol = (params.get("symbol") or "NVDA").upper()
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
    # clamp/normalize
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
    company = repo.get_company(symbol)
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
    return {
        "symbol": symbol,
        "name": company["name"],
        "metrics": metrics,
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
    rows = []
    companies = []
    for s in syms:
        c = repo.get_company(s)
        if not c:
            continue
        companies.append(c)
        rows.append({
            "symbol": s,
            "name": c["name"],
            "price": c["price"],
            "changePct": c["changePct"],
            "marketCap": c["marketCap"],
            "peRatio": c["peRatio"],
            "volume": c["volume"],
            "sector": repo.sector_name(c["sector"]),
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
    cells = []
    companies = []
    for s in syms:
        c = repo.get_company(s)
        if not c:
            continue
        companies.append(c)
        cells.append({
            "symbol": s,
            "name": c["name"],
            "changePct": c["changePct"],
            "marketCap": c["marketCap"],
            "sector": repo.sector_name(c["sector"]),
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
    # ensure trend ends near overall
    trend[-1]["score"] = overall
    return {"scope": name, "overall": overall, "label": label, "sources": sources,
            "trend": trend, "source": _live_source()}


def build_comparison(params: dict) -> dict:
    symbols = params.get("symbols") or []
    symbols = [s.upper() for s in symbols if repo.get_company(s.upper())]
    if len(symbols) < 2:
        # default to top semiconductors if not enough valid symbols
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
    symbols = [s.upper() for s in (params.get("symbols") or []) if data.get_company(s.upper())]
    if not symbols:
        symbols = ["NVDA", "MSFT", "GOOGL", "META", "AMZN"]
    portfolio_name = params.get("portfolio_name") or (", ".join(symbols[:3]) + " Portfolio")

    seed = data._seed("_".join(sorted(symbols)))

    def rnd():
        nonlocal seed
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    # VaR histogram — simulate 20 bins of a normal-ish P&L distribution
    bins = []
    center = -0.02  # slight negative skew
    for i in range(20):
        b = round(center - 0.04 + i * 0.004, 4)
        # bell-shaped count
        z = (b - center) / 0.012
        base_count = max(1, int(120 * 2.718 ** (-0.5 * z * z) + rnd() * 20))
        bins.append({"bin": round(b * 100, 2), "count": base_count})

    # Factor exposures
    betas = {s: data.get_company(s)["beta"] for s in symbols}
    avg_beta = round(sum(betas.values()) / len(betas), 2)
    factor_exposures = [
        {"factor": "Market", "exposure": round(avg_beta, 2)},
        {"factor": "Momentum", "exposure": round(0.3 + rnd() * 0.5, 2)},
        {"factor": "Size", "exposure": round(-0.2 + rnd() * 0.4, 2)},
        {"factor": "Value", "exposure": round(-0.4 + rnd() * 0.4, 2)},
        {"factor": "Quality", "exposure": round(0.1 + rnd() * 0.5, 2)},
        {"factor": "Volatility", "exposure": round(0.2 + rnd() * 0.4, 2)},
    ]

    var95 = round(1.645 * (0.012 + rnd() * 0.008), 4)
    tracking_error = round(0.04 + rnd() * 0.06, 4)
    summary = {
        "portfolioName": portfolio_name,
        "var95": round(var95 * 100, 2),
        "trackingError": round(tracking_error * 100, 2),
        "beta": avg_beta,
    }
    return {
        "portfolioName": portfolio_name,
        "symbols": symbols,
        "varHistogram": bins,
        "factorExposures": factor_exposures,
        "summary": summary,
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
    symbol = (params.get("symbol") or "SPY").upper()
    company = data.get_company(symbol)
    if not company:
        symbol = "NVDA"
        company = data.get_company(symbol)
    strategy = params.get("strategy") or "momentum"
    rng_key = params.get("range") or "1Y"
    days = RANGE_DAYS.get(rng_key.upper(), 250)

    seed = data._seed(symbol + strategy)

    def rnd():
        nonlocal seed
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    # Generate equity curves: strategy outperforms benchmark on average
    start = date.today() - timedelta(days=days - 1)
    strat_val = 100.0
    bench_val = 100.0
    curve = []
    dd_series = []
    peak = 100.0
    wins = 0
    total_days = 0

    for i in range(days):
        r = rnd()
        # benchmark: daily return ~0.04% drift, 1% vol
        bench_ret = 0.0004 + (r * 2 - 1) * 0.01
        # strategy: slightly better drift, slightly higher vol
        strat_ret = 0.0008 + (rnd() * 2 - 1) * 0.012

        bench_val = round(bench_val * (1 + bench_ret), 4)
        strat_val = round(strat_val * (1 + strat_ret), 4)

        if strat_ret > 0:
            wins += 1
        total_days += 1

        if strat_val > peak:
            peak = strat_val
        dd = round((strat_val - peak) / peak * 100, 3) if peak > 0 else 0.0

        t = (start + timedelta(days=i)).isoformat()
        curve.append({"t": t, "strategy": round(strat_val, 2), "benchmark": round(bench_val, 2)})
        dd_series.append({"t": t, "dd": dd})

    # Compute stats
    strat_final = curve[-1]["strategy"] / 100
    bench_final = curve[-1]["benchmark"] / 100
    years = days / 252
    cagr = round((strat_final ** (1 / years) - 1) * 100, 2)
    max_dd = round(min(p["dd"] for p in dd_series), 2)
    win_rate = round(wins / max(total_days, 1) * 100, 1)
    # Sharpe: approximate
    daily_rets = [
        (curve[i]["strategy"] - curve[i - 1]["strategy"]) / curve[i - 1]["strategy"]
        for i in range(1, len(curve))
    ]
    if daily_rets:
        avg_r = sum(daily_rets) / len(daily_rets)
        var_r = sum((r - avg_r) ** 2 for r in daily_rets) / len(daily_rets)
        std_r = var_r ** 0.5
        sharpe = round((avg_r / std_r) * (252 ** 0.5), 2) if std_r > 0 else 0.0
        # Sortino (downside only)
        neg = [r for r in daily_rets if r < 0]
        dvar = sum(r ** 2 for r in neg) / max(len(neg), 1)
        sortino = round((avg_r / (dvar ** 0.5)) * (252 ** 0.5), 2) if dvar > 0 else 0.0
    else:
        sharpe = sortino = 0.0

    return {
        "symbol": symbol,
        "strategy": strategy,
        "curve": curve,
        "drawdown": dd_series,
        "stats": {
            "sharpe": sharpe,
            "sortino": sortino,
            "cagr": cagr,
            "maxDD": max_dd,
            "winRate": win_rate,
        },
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
        "attribution": attribution,
        "loadings": loadings
    }


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
