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
from typing import List, Optional, Tuple

from . import ai, alerts, data, dynamic_skills, engine, harness, repo, skills, state, strategy, strategy_store


# A short, honest notice surfaced to the UI (and spoken in voice mode) when the
# dashboard/narration had to fall back to the keyword heuristic because the AI
# was slow or unavailable. Reads well both as a chat banner and read aloud.
_DEGRADED_NOTE = "The AI was slow to respond, so here's a quick keyword-built dashboard."


# ----------------------------- tool schemas -----------------------------
def _tools() -> list:
    # The full catalog (hundreds of US + SGX names) is too large to inline into
    # every tool description, so advertise a capped most-valuable slice plus a
    # hint that the wider universe (incl. SGX base codes like D05, no .SI needed)
    # is accepted at request time.
    syms = (", ".join(repo.prompt_symbols(60))
            + ", and many more US + Singapore (SGX) names; SGX uses base codes "
              "like D05/O39 (no .SI suffix needed)")
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
            "description": (
                "Add a live news feed for a ticker, a sector, or a free-text topic/theme. "
                "Use scope_type='topic' for anything that isn't a tracked ticker or sector "
                "(e.g. 'cybersecurity', 'AI chip shortage', 'oil prices', 'EV demand') and "
                f"put the topic words in scope. {sizing}"
            ),
            "parameters": {"type": "object", "properties": {
                "scope_type": {"type": "string", "enum": ["symbol", "sector", "topic"]},
                "scope": {"type": "string", "description": f"A ticker ({syms}), a sector ({secs}), or a free-text topic/theme."},
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
            "description": f"Add a screener table for a sector and/or market. Omit all filters for the whole market. Combine sector + country/exchange for e.g. 'Singapore banks' or 'US semiconductors'. {sizing}",
            "parameters": {"type": "object", "properties": {
                "sector": {"type": "string", "description": f"Sector ({secs}) or omit."},
                "country": {"type": "string", "description": "Optional country filter: 'United States' or 'Singapore'."},
                "exchange": {"type": "string", "description": "Optional exchange filter: NASDAQ, NYSE or SGX."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_heatmap",
            "description": f"Add a market/sector heatmap. Omit all filters for the whole market. Combine sector + country/exchange for e.g. 'Singapore market heatmap' or 'US semiconductors'. {sizing}",
            "parameters": {"type": "object", "properties": {
                "sector": {"type": "string"},
                "country": {"type": "string", "description": "Optional country filter: 'United States' or 'Singapore'."},
                "exchange": {"type": "string", "description": "Optional exchange filter: NASDAQ, NYSE or SGX."},
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
            "name": "add_analyst_compare",
            "description": (
                "Add a QUICK analyst-view comparison across 2+ tickers: a compact card per name with its "
                "bull/bear/neutral stance, conviction score, headline and a one-line call, built by reusing "
                f"the deep analyst-report engine per symbol. {sizing} Use when the user wants to compare "
                "analyst opinions/stance across several names ('compare analyst views on NVDA, AMD, TSM', "
                "'analyst take on X vs Y', 'who's the better buy, X or Y'). Prefer this over add_comparison "
                "(which compares raw metrics) when the user wants the analyst STANCE/CALL side by side; "
                "prefer add_analyst_report for a single-name deep dive."
            ),
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Two or more tickers to compare. Valid: {syms}"},
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
            "name": "add_supply_chain",
            "description": f"Add a supply-chain graph for one ticker showing suppliers and customers with revenue exposure. {sizing}",
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
            "name": "add_alerts",
            "description": f"Add a trade-flow alerts panel where the user can configure alert rules (block print size, dark pool % spike, buy imbalance) per symbol and get notified when the trade flow crosses a threshold. Use when the user asks to set up alerts, get notified, watch for block trades or sweeps, or manage alert rules. Optionally pass a symbol to pre-fill the rule form. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Optional ticker to pre-fill. One of: {syms}"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": []},
        }},
        {"type": "function", "function": {
            "name": "add_compliance",
            "description": f"Add the pre-trade risk & compliance panel: firm limits (max position, net exposure, leverage, concentration), the restricted + watch lists, the global/per-strategy kill switch, and the audit trail of gate decisions. Optionally pass a strategy name to pre-check whether that strategy's book would be allowed (answers 'is this trade allowed'). Use for restricted/watch list, risk limits, kill switch / halt trading, or the compliance audit log. {sizing}",
            "parameters": {"type": "object", "properties": {
                "strategy": {"type": "string", "description": "Optional strategy name to pre-check its prospective book."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": []},
        }},
        {"type": "function", "function": {
            "name": "add_dcf_model",
            "description": f"Add a DCF valuation model for one ticker with projected FCF, implied price range, and sensitivity grid. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_tca_report",
            "description": (
                f"Add an Execution Simulation & Transaction Cost Analysis (TCA) panel. Generates "
                f"orders, simulates VWAP/TWAP/POV executions against REAL intraday volume, applies a "
                f"square-root market-impact model, and reports implementation shortfall vs arrival, "
                f"slippage vs interval VWAP, and cost in bps per name + aggregate. Use when the user "
                f"asks about TCA, execution quality, slippage, market impact, VWAP/TWAP/POV, or "
                f"'how much would it cost to trade into a portfolio'. {sizing}"
            ),
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Single-name execution. Ticker, one of: {syms}"},
                "side": {"type": "string", "enum": ["buy", "sell"], "description": "Order side for the single-symbol case (default buy)."},
                "notional": {"type": "number", "description": "Order size in USD for the single-symbol case."},
                "shares": {"type": "number", "description": "Order size in shares for the single-symbol case."},
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "Portfolio tickers to trade into (pair with target_weights)."},
                "target_weights": {"type": "array", "items": {"type": "number"}, "description": "Target weights aligned with symbols (fractions or %)."},
                "current_weights": {"type": "array", "items": {"type": "number"}, "description": "Optional current book weights aligned with symbols (default flat / all-cash)."},
                "capital": {"type": "number", "description": "Book NAV in USD used to size the weight-diff orders (default 10,000,000)."},
                "algo": {"type": "string", "enum": ["vwap", "twap", "pov"], "description": "Headline execution algo (default vwap; all three are simulated and compared)."},
                "pov_rate": {"type": "number", "description": "Participation rate for the POV algo as a fraction (default 0.10)."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_earnings_transcript",
            "description": f"Add an earnings call transcript panel with sentiment timeline and key quotes for one ticker. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_earnings_calendar",
            "description": (
                f"Add an earnings calendar panel listing upcoming scheduled earnings report dates "
                f"for a watchlist, a set of tickers, or a sector. Each row has the company, report "
                f"date, before/after-market timing, a live countdown, the consensus EPS estimate and "
                f"the fiscal quarter; any company reporting within 24 hours is flagged. Use for "
                f"'earnings calendar', 'upcoming earnings', 'earnings dates/schedule', 'who reports "
                f"next', or 'when does X report'. {sizing}"
            ),
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"},
                            "description": f"Optional explicit tickers to track. Omit to use the tracked watchlist. From: {syms}"},
                "symbol": {"type": "string", "description": "A single ticker to focus on."},
                "sector": {"type": "string", "description": "Optional sector to list earnings for."},
                "days": {"type": "integer", "description": "Horizon in days (default 30, max 120)."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_etf_holdings",
            "description": (
                f"Add an ETF holdings panel listing the real ranked constituents (top holdings) of an "
                f"ETF or index fund — each row has the holding's ticker, name and weight — plus top-N "
                f"concentration (top 5 / top 10) and the fund's real GICS sector breakdown. The free "
                f"fund feed exposes a fund's TOP holdings only, so coverage is partial and reported "
                f"honestly. Use for \"what's in QQQ\", 'holdings of XLK', 'top holdings of SPY', an "
                f"ETF's constituents/components, or what an ETF holds. {sizing}"
            ),
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": "The ETF ticker (e.g. QQQ, XLK, SPY)."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_etf_exposure",
            "description": (
                f"Add an ETF exposure panel: reverse lookup listing the ETFs whose top holdings include "
                f"a given stock, with that stock's weight in each fund, ranked by weight. Scans the "
                f"common benchmark and sector ETFs; because the free feed exposes top holdings only, a "
                f"stock held more deeply may not appear (reported honestly). Use for 'which ETFs hold "
                f"NVDA', 'what funds own AAPL', or a stock's ETF exposure. {sizing}"
            ),
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": "The stock ticker to find ETFs for."},
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
            "description": f"Add a yield curve panel (live US Treasury par yields + 1y/2y-ago overlays, inversion highlights). {sizing}",
            "parameters": {"type": "object", "properties": {
                "region": {"type": "string", "enum": ["US", "UK", "DE", "JP"], "description": "Sovereign issuer. Default US."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_sovereign_compare",
            "description": f"Overlay 2–4 sovereign yield curves (US/UK/DE/JP) on one chart with cross-currency 2Y/10Y/30Y spreads. Use to compare government bond curves across countries/currencies (e.g. UST vs Bund). {sizing}",
            "parameters": {"type": "object", "properties": {
                "regions": {"type": "array", "items": {"type": "string", "enum": ["US", "UK", "DE", "JP"]}, "description": "Sovereign issuers to overlay (2–4). e.g. [\"US\", \"DE\"]. Defaults to US vs DE."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["regions"]},
        }},
        {"type": "function", "function": {
            "name": "add_bond_rv",
            "description": f"Add a bond relative-value panel: Z-spread, OAS and asset-swap vs peers, anchored to live ICE BofA OAS by rating. {sizing}",
            "parameters": {"type": "object", "properties": {
                "ticker": {"type": "string", "description": "Bond issuer ticker (e.g. AAPL, MSFT, F, INTC, META, XOM, AMZN, GOOGL, NVDA, CVX)."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["ticker"]},
        }},
        {"type": "function", "function": {
            "name": "add_cds_pricer",
            "description": f"Price a credit default swap on a reference entity (running spread proxied from live ICE BofA OAS by rating). {sizing}",
            "parameters": {"type": "object", "properties": {
                "ticker": {"type": "string", "description": "Reference entity ticker (e.g. F, INTC, OXY, META, AMZN, AAPL, MSFT, XOM, NVDA, GOOGL)."},
                "tenor": {"type": "string", "enum": ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y"]},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["ticker"]},
        }},
        {"type": "function", "function": {
            "name": "add_credit_stress",
            "description": f"Add a credit stress monitor: charts investment-grade (IG) vs high-yield (HY) ICE BofA OAS over ~6 months with a risk-on/risk-off read and widening flags. Use for credit conditions, IG vs HY spreads, credit stress/widening. {sizing}",
            "parameters": {"type": "object", "properties": {
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_cashflow_duration",
            "description": f"Show bond cash flows, duration, convexity, and rate-shock scenario table (yields off the live Treasury curve + live credit spreads). {sizing}",
            "parameters": {"type": "object", "properties": {
                "bond": {"type": "string", "description": "Bond key: UST10Y, UST30Y, UST5Y, UST2Y, AAPL30, MSFT10, F7Y."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_economic_releases",
            "description": f"Add an economic-releases calendar: recent and upcoming key US data releases (CPI, PCE, GDP, unemployment, nonfarm payrolls, PPI) with reporting period, reported value, prior value, and the next scheduled release date. Live FRED data only. Use for the economic calendar, data releases, CPI/jobs/GDP release dates, what economic data is coming out. {sizing}",
            "parameters": {"type": "object", "properties": {
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_series_revisions",
            "description": f"Chart any FRED economic series by id with its data-revision (vintage) history: overlays the current series vs the initial print and lists each vintage (release date) and the value reported then, distinguishing initial vs revised prints. Live FRED/ALFRED data only. Use for revision history, data revisions, vintages, initial vs revised GDP/payrolls, 'how was X revised', or to pull a FRED series id. {sizing}",
            "parameters": {"type": "object", "properties": {
                "series_id": {"type": "string", "description": "FRED series id, e.g. GDPC1 (Real GDP), PAYEMS (payrolls), CPIAUCSL (CPI), UNRATE (unemployment), PCEPI (PCE)."},
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
            "description": f"Add a strategy backtest for one ticker, denominated in real dollars: invested amount, entry point (date+price), ending value, gain in $ and as a multiple, plus equity curve, drawdown and Sharpe/CAGR stats. Use when the user asks things like 'invest $1M in NVDA at its peak and show what it's worth now'. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "strategy": {"type": "string", "description": "Strategy name, e.g. 'momentum', 'mean_reversion', 'buy_and_hold'. When the user simply asks what a lump sum would be worth (e.g. 'invest $1M in NVDA at its peak, what's it worth now') without naming a systematic strategy, use 'buy_and_hold' so the panel reflects the asset's actual dollar trajectory. Only use 'momentum'/'mean_reversion' when the user explicitly asks for that strategy."},
                "range": {"type": "string", "enum": ["1M", "3M", "6M", "1Y", "YTD"]},
                "amount": {"type": "number", "description": "Dollar lump sum to invest, e.g. 1000000 for $1M. Defaults to 10000."},
                "entry": {"type": "string", "enum": ["peak", "date", "range", "preset"], "description": "Where the money goes in: 'peak' = highest close in available history; 'date' = a specific date (use the 'date' field); 'range' = a custom window (use 'start'/'end'); 'preset' = the recent range window. Defaults to 'preset'."},
                "date": {"type": "string", "description": "ISO date (YYYY-MM-DD) for entry='date'."},
                "start": {"type": "string", "description": "ISO start date for entry='range'."},
                "end": {"type": "string", "description": "ISO end date for entry='range'."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_walk_forward",
            "description": f"Add a research-integrity validation of a strategy: anchored walk-forward backtest (in-sample vs out-of-sample equity), deflated Sharpe ratio, probability of backtest overfitting (PBO/CSCV), a multiple-testing Sharpe haircut, and a plain-language overfitting verdict — all from real price history. Use for 'is this overfit / robust / data-mined', out-of-sample / walk-forward validation, deflated Sharpe, or PBO. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "strategy": {"type": "string", "description": "Strategy name, e.g. 'momentum', 'mean_reversion', 'ma_crossover', 'buy_and_hold'."},
                "splits": {"type": "integer", "description": "Number of anchored walk-forward folds (2-8, default 5)."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_walk_forward_compare",
            "description": f"Add a MULTI-NAME research-integrity validation: run the same anchored walk-forward / overfitting check across a UNIVERSE of tickers (an explicit list OR a sector) and aggregate the per-name verdicts into a robustness score. Use when the user asks whether a strategy is overfit / robust / data-mined ACROSS multiple names, a list, or a sector ('is momentum overfit across megacap tech', 'walk-forward momentum on NVDA, AMD, AVGO', 'is this robust across semis') — a single-name pass can itself be a lucky draw. Prefer this over add_walk_forward whenever two or more tickers (or a sector) are in scope. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Two or more tickers to validate. One of: {syms}"},
                "sector": {"type": "string", "description": "Optional sector to expand into its members instead of an explicit list (e.g. 'tech', 'semis', 'financials')."},
                "strategy": {"type": "string", "description": "Strategy name, e.g. 'momentum', 'mean_reversion', 'ma_crossover', 'buy_and_hold'."},
                "splits": {"type": "integer", "description": "Number of anchored walk-forward folds per name (2-8, default 5)."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": []},
        }},
        {"type": "function", "function": {
            "name": "add_monte_carlo",
            "description": f"Add a Monte Carlo forward simulation for one ticker (percentile fan p5-p95, sample paths, expected/median terminal value, probability of loss, terminal VaR/CVaR) fitted to real historical returns. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "method": {"type": "string", "description": "Simulation method.", "enum": ["bootstrap", "gbm"]},
                "horizon": {"type": "integer", "description": "Forward horizon in trading days, e.g. 252 for one year."},
                "paths": {"type": "integer", "description": "Number of simulated paths, e.g. 1000."},
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
            "name": "add_risk_model",
            "description": f"Add a Barra-style multi-factor risk decomposition for a portfolio: splits predicted volatility into common-factor vs stock-specific risk, shows each factor's share of risk, the marginal contribution to risk (MCTR) of every holding, the diversification ratio, and an honest coverage block. Use for risk decomposition, factor vs specific risk, MCTR, or risk-model requests. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio tickers. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional portfolio weights aligned with symbols (auto-normalized; equal-weight if omitted)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the portfolio."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_risk_comparison",
            "description": f"Add a side-by-side risk comparison of TWO portfolios using the multi-factor risk model: contrasts total volatility, the factor-vs-specific risk split, the diversification ratio, and the dominant factor tilts, and flags the factors where the two books diverge most. Use when the user asks to compare the risk of two portfolios, 'is A riskier / better diversified than B', or wants a side-by-side risk view. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols_a": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio A tickers. Valid: {syms}"},
                "weights_a": {"type": "array", "items": {"type": "number"}, "description": "Optional weights for portfolio A (auto-normalized; equal-weight if omitted)."},
                "name_a": {"type": "string", "description": "Optional display name for portfolio A."},
                "symbols_b": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio B tickers. Valid: {syms}"},
                "weights_b": {"type": "array", "items": {"type": "number"}, "description": "Optional weights for portfolio B (auto-normalized; equal-weight if omitted)."},
                "name_b": {"type": "string", "description": "Optional display name for portfolio B."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols_a", "symbols_b"]},
        }},
        {"type": "function", "function": {
            "name": "add_factor_exposures",
            "description": f"Add a portfolio factor-tilt panel: weighted-average standardized exposures to Market, Size, Value, Momentum, Volatility, and Quality, with realized factor premia (annualized return + t-stat) and a per-holding exposure breakdown. Use for factor tilts, style exposures, or how a portfolio is positioned across factors. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio tickers. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional portfolio weights aligned with symbols (auto-normalized; equal-weight if omitted)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the portfolio."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_performance_pnl",
            "description": f"Add a portfolio P&L panel for a book over a window: cumulative & periodic return vs a benchmark of the USER'S choosing, a drawdown track, and a full risk/return + active stat block (return, vol, Sharpe, max drawdown, hit rate, tracking error, information ratio, beta, alpha, up/down capture). The benchmark can be any real ETF (broad like SPY/QQQ/IWM or a sector ETF like XLK/XLE/XLF) OR a custom basket of constituent tickers. Defaults to SPY. Real returns only; excluded names reported. Use for P&L, performance vs benchmark, or how a book/portfolio has performed. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio tickers. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional portfolio weights aligned with symbols (auto-normalized; equal-weight if omitted)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the portfolio."},
                "range": {"type": "string", "enum": ["1M", "3M", "6M", "1Y", "YTD"]},
                "benchmark": {"type": "string", "description": "Real benchmark ETF ticker to compare against (default SPY). Broad indices (SPY, QQQ, DIA, IWM, VTI, VOO, RSP) or sector/thematic ETFs (e.g. XLK, XLF, XLE, XLV, SMH, XBI) are all valid; any other ticker is honored only if a real price series exists for it."},
                "benchmark_constituents": {"type": "array", "items": {"type": "string"}, "description": f"Optional: build a CUSTOM benchmark basket from these real constituent tickers instead of a single ETF (takes precedence over `benchmark`). Cap-weighted unless `benchmark_weights` is given. Valid: {syms}"},
                "benchmark_weights": {"type": "array", "items": {"type": "number"}, "description": "Optional weights aligned with benchmark_constituents (auto-normalized; cap-weight if omitted)."},
                "benchmark_name": {"type": "string", "description": "Optional display name for a custom benchmark basket."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_brinson_attribution",
            "description": f"Add a Brinson performance attribution panel: decomposes a book's active return into allocation, selection and interaction effects BY SECTOR (the three effects sum exactly to the active return vs the benchmark whose sector weights/returns drive the math). Benchmark selection (both REAL): pass `benchmark` with any ETF ticker (broad like SPY/QQQ or a sector ETF like XLK/XLE) — the ETF's OWN real sector weights (× real sector-ETF returns) then drive the decomposition; OR pass `benchmark_constituents` for a CUSTOM basket of real constituents, whose own real sector weights/returns drive it (takes precedence over `benchmark`). Defaults to SPY. If an ETF's real sector composition can't be sourced, it falls back to a diversified sector-ETF proxy and says so. Excluded names and unmapped sectors are reported. Use for performance attribution, allocation vs selection, Brinson, or 'where did my outperformance come from'. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio tickers. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional portfolio weights aligned with symbols (auto-normalized; equal-weight if omitted)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the portfolio."},
                "range": {"type": "string", "enum": ["1M", "3M", "6M", "1Y", "YTD"]},
                "benchmark": {"type": "string", "description": "Real benchmark ETF ticker whose OWN real sector weights drive the Brinson decomposition (default SPY). Broad indices (SPY, QQQ, DIA, IWM, VTI) or sector ETFs (XLK, XLF, XLE, XLV, SMH...) are valid; falls back to a diversified sector-ETF proxy (and says so) if the ETF's real sector composition can't be sourced."},
                "benchmark_constituents": {"type": "array", "items": {"type": "string"}, "description": f"Optional: a CUSTOM benchmark basket of real constituent tickers; its OWN real sector weights/returns drive the Brinson decomposition (takes precedence over `benchmark`). Valid: {syms}"},
                "benchmark_weights": {"type": "array", "items": {"type": "number"}, "description": "Optional weights aligned with benchmark_constituents (auto-normalized; cap-weight if omitted)."},
                "benchmark_name": {"type": "string", "description": "Optional display name for a custom benchmark basket."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_factor_attribution",
            "description": f"Add a factor return attribution panel: decomposes a book's REALIZED return over a window into per-factor contributions (exposure × realized factor return) for Market, Size, Value, Momentum, Volatility, Quality, plus a specific (idiosyncratic) return — contributions + specific reconstruct the realized return. Uses the real multi-factor risk model. NOTE: this decomposition is benchmark-independent (it explains the book's own return, not active return), so a chosen benchmark/basket does not change the numbers. Use for factor attribution, factor contribution to return, or 'which factors drove my return'. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio tickers. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional portfolio weights aligned with symbols (auto-normalized; equal-weight if omitted)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the portfolio."},
                "range": {"type": "string", "enum": ["1M", "3M", "6M", "1Y", "YTD"]},
                "benchmark": {"type": "string", "description": "Accepted for orchestration consistency but IGNORED — factor attribution explains the book's own realized return and is benchmark-independent."},
                "benchmark_constituents": {"type": "array", "items": {"type": "string"}, "description": "Accepted for orchestration consistency but IGNORED — factor attribution is benchmark-independent."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_factor_performance",
            "description": f"Add a factor performance panel: charts the CUMULATIVE return of each systematic factor (Market, Size, Value, Momentum, Volatility, Quality) over the model's estimation window from the real multi-factor risk model's daily factor returns, plus a summary of each factor's total/annualized return, annualized vol, Sharpe and t-stat. Use for 'how have factors performed over time', 'which factors are paying off / being rewarded', factor performance, or factor returns over time. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Optional portfolio tickers to seed the estimation universe. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional portfolio weights aligned with symbols (auto-normalized; equal-weight if omitted)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the portfolio."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_tear_sheet",
            "description": f"Add a performance tear-sheet panel that combines P&L vs a benchmark of the USER'S choosing (any real ETF — broad like SPY/QQQ or a sector ETF like XLK — OR a custom basket of constituent tickers; default SPY), the drawdown track, Brinson sector attribution and factor attribution into one report-style view for a book over a window. Use for a tear sheet, a full performance review, or 'give me a complete performance breakdown of my portfolio'. Best at full width. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio tickers. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional portfolio weights aligned with symbols (auto-normalized; equal-weight if omitted)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the portfolio."},
                "range": {"type": "string", "enum": ["1M", "3M", "6M", "1Y", "YTD"]},
                "benchmark": {"type": "string", "description": "Real benchmark ETF ticker to compare against (default SPY). Broad indices or sector/thematic ETFs (e.g. XLK, XLE) are valid; any other ticker is honored only if a real price series exists."},
                "benchmark_constituents": {"type": "array", "items": {"type": "string"}, "description": f"Optional: build a CUSTOM benchmark basket from these real constituent tickers instead of a single ETF (takes precedence over `benchmark`). Valid: {syms}"},
                "benchmark_weights": {"type": "array", "items": {"type": "number"}, "description": "Optional weights aligned with benchmark_constituents (auto-normalized; cap-weight if omitted)."},
                "benchmark_name": {"type": "string", "description": "Optional display name for a custom benchmark basket."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_portfolio_optimizer",
            "description": f"Add a portfolio construction & optimization panel that solves for optimal target weights over a candidate universe. Expected returns are factor-model-implied (style exposures × realized factor premia) and the covariance comes from the multi-factor risk model — both from REAL data. Reports expected return, vol, Sharpe, per-name weights vs the cap-weighted benchmark, sector allocation, factor tilts, binding constraints, and an honest coverage block. {sizing} Use to construct/optimize/rebalance/size a portfolio, find optimal/target weights, or allocate capital.",
            "parameters": {"type": "object", "properties": {
                "method": {"type": "string", "description": "Construction method.", "enum": ["max_sharpe", "min_variance", "target_vol", "black_litterman", "risk_parity", "hrp"]},
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Optional explicit candidate universe. Valid: {syms}"},
                "sector": {"type": "string", "description": "Optional sector to scope the candidate universe (e.g. semiconductors, energy, ai_tech)."},
                "max_position": {"type": "number", "description": "Per-name max weight as a fraction (e.g. 0.05 for 5%)."},
                "long_short": {"type": "boolean", "description": "Allow shorts (long/short book). Defaults to long-only."},
                "market_neutral": {"type": "boolean", "description": "Target net exposure 0 (only with long_short)."},
                "max_sector": {"type": "number", "description": "Optional blanket cap on any single sector's weight, as a fraction."},
                "gross_limit": {"type": "number", "description": "Optional gross exposure cap (sum of |weights|) as a fraction, e.g. 2.0 for 200%."},
                "target_vol": {"type": "number", "description": "Annualized target volatility (fraction) for the target_vol method, e.g. 0.15."},
                "turnover_penalty": {"type": "number", "description": "Optional penalty on trading away from the current book."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": []},
        }},
        {"type": "function", "function": {
            "name": "add_signal_research",
            "description": f"Add an alpha signal research panel evaluating ONE cross-sectional signal over a universe: rank IC, IC decay across horizons, signal turnover, and a long-short quantile spread equity curve from REAL price/fundamental data. {sizing} Use for IC, information coefficient, IC decay, signal turnover, quantile/decile spread, or 'does <signal> predict returns'. Signals: momentum, short_reversal, low_volatility, value, quality.",
            "parameters": {"type": "object", "properties": {
                "signal": {"type": "string", "description": "Signal to evaluate.", "enum": ["momentum", "short_reversal", "low_volatility", "value", "quality"]},
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Optional explicit universe. Valid: {syms}"},
                "sector": {"type": "string", "description": "Optional sector to scope the universe."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["signal"]},
        }},
        {"type": "function", "function": {
            "name": "add_signal_scorecard",
            "description": f"Add an alpha signal scorecard comparing SEVERAL signals head-to-head over one shared universe, ranked by IC information ratio with mean IC, t-stat, hit rate, turnover and long-short spread performance. {sizing} Use for 'compare signals', 'rank alphas', 'signal scorecard', or 'which signal works best'. Defaults to the full library if none given.",
            "parameters": {"type": "object", "properties": {
                "signals": {"type": "array", "items": {"type": "string"}, "description": "Signals to compare. Subset of: momentum, short_reversal, low_volatility, value, quality."},
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Optional explicit universe. Valid: {syms}"},
                "sector": {"type": "string", "description": "Optional sector to scope the universe."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": []},
        }},
        {"type": "function", "function": {
            "name": "add_signal_portfolio",
            "description": f"Build a tradeable PORTFOLIO from ONE alpha signal: ranks the real cross-section and constructs either an equal-weight top-quantile (long-only) book or a dollar-neutral long-short quantile spread, then backtests the realized book (equity curve vs equal-weight benchmark, Sharpe, CAGR, drawdown, turnover) with position counts and weights. {sizing} Use for 'build/construct a portfolio from <signal>', 'turn <signal> into a strategy', 'size positions from <signal>', or a signal's realized portfolio performance. Signals: momentum, short_reversal, low_volatility, value, quality.",
            "parameters": {"type": "object", "properties": {
                "signal": {"type": "string", "description": "Signal to build the portfolio from.", "enum": ["momentum", "short_reversal", "low_volatility", "value", "quality"]},
                "scheme": {"type": "string", "description": "Construction scheme: top_quantile (equal-weight long-only top bucket) or long_short (dollar-neutral long-short spread).", "enum": ["top_quantile", "long_short"]},
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Optional explicit universe. Valid: {syms}"},
                "sector": {"type": "string", "description": "Optional sector to scope the universe."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["signal"]},
        }},
        {"type": "function", "function": {
            "name": "add_combined_alpha",
            "description": f"Blend SEVERAL cross-sectional signals into ONE composite alpha score per name, then score the blend with the same scorecard as its components (rank IC, IC decay, quantile spread, turnover) and show how much the components overlap (a correlation matrix). Combination methods: equal_weight, ic_weighted, or inverse_correlation (risk-weighted); the chosen method is reported. {sizing} Use for 'combine/blend signals', 'composite alpha', 'signal ensemble', or 'blend momentum, value and quality into one alpha'. Signals: momentum, short_reversal, low_volatility, value, quality.",
            "parameters": {"type": "object", "properties": {
                "signals": {"type": "array", "items": {"type": "string"}, "description": "Component signals to blend (2+). Subset of: momentum, short_reversal, low_volatility, value, quality."},
                "method": {"type": "string", "description": "Combination method.", "enum": ["equal_weight", "ic_weighted", "inverse_correlation"]},
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Optional explicit universe. Valid: {syms}"},
                "sector": {"type": "string", "description": "Optional sector to scope the universe."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": []},
        }},
        {"type": "function", "function": {
            "name": "add_shorting_desk",
            "description": f"Model the REAL cost of being short for a long/short book: per-name borrow tier and stock-loan fee (general-collateral vs hard-to-borrow), locate-infeasible names that cannot be shorted at all, the carrying-cost drag (borrow fees + financing − cash rebate, anchored to the live 3M Treasury bill) and the Reg-T margin requirement, gross/net leverage and any maintenance-margin breach. {sizing} Use for 'borrow cost', 'cost to short', 'how expensive to short', 'is it hard to borrow', 'margin and leverage', 'financing cost', 'carrying cost of my shorts'. Pass `symbols` to build a dollar-neutral book, or `longs`/`shorts`/`weights` and `capital`.",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Universe to build a dollar-neutral book from. Valid: {syms}"},
                "longs": {"type": "array", "items": {"type": "string"}, "description": "Explicit long names (equal-weighted)."},
                "shorts": {"type": "array", "items": {"type": "string"}, "description": "Explicit short names (equal-weighted)."},
                "weights": {"type": "object", "description": "Explicit {symbol: signed weight} book (negative = short)."},
                "capital": {"type": "number", "description": "Book equity in USD (default 1,000,000)."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": []},
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
            "name": "add_options_chain",
            "description": f"Add a full options chain for a ticker: calls and puts side-by-side across all strikes with bid/ask, last, IV, volume and open interest, plus an expiry selector. {sizing} Use when the user wants to see the options chain, calls and puts, the strike ladder, or all strikes/expiries for a name.",
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Underlying ticker. One of: {syms}"},
                "expiry": {"type": "string", "description": "Default expiry to display. One of: 1W, 2W, 1M, 2M, 3M, 6M, 1Y."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_options_screener",
            "description": f"Scan a whole universe (the tracked watchlist, or a sector/market) for options contracts matching filters, and rank the matches in one table. {sizing} Use for cross-symbol options screens like 'find high-IV calls', 'cheapest puts across tech', 'unusual options volume', 'scan for options expiring within 30 days', 'widest skew names'. NOT for a single ticker's chain (use add_options_chain) or a single strategy payoff (use add_options_strategy).",
            "parameters": {"type": "object", "properties": {
                "sector": {"type": "string", "description": "Optional sector to scope the scan (e.g. semiconductors, energy). Omit to scan the watchlist."},
                "country": {"type": "string", "description": "Optional market filter: 'United States' or 'Singapore'."},
                "exchange": {"type": "string", "description": "Optional exchange filter: 'NASDAQ'/'NYSE'/'SGX'."},
                "option_type": {"type": "string", "description": "call, put, or all (default)."},
                "iv_min": {"type": "number", "description": "Minimum implied vol in percent (e.g. 40)."},
                "iv_max": {"type": "number", "description": "Maximum implied vol in percent."},
                "dte_min": {"type": "number", "description": "Minimum days to expiry."},
                "dte_max": {"type": "number", "description": "Maximum days to expiry."},
                "moneyness": {"type": "string", "description": "all (default), otm, itm, or atm."},
                "volume_min": {"type": "number", "description": "Minimum contract volume."},
                "oi_min": {"type": "number", "description": "Minimum open interest."},
                "rank_by": {"type": "string", "description": "Ranking metric: iv (default), volume, oi, cheap, or skew."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": []},
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
        {"type": "function", "function": {
            "name": "add_ma_tracker",
            "description": f"Add an M&A deal tracker with deal table, arb spreads, and deal statistics. Optionally filter by sector or ticker. {sizing}",
            "parameters": {"type": "object", "properties": {
                "sector": {"type": "string", "description": f"Sector ({secs}) or omit for all sectors."},
                "symbol": {"type": "string", "description": "Filter to deals involving this ticker, or omit."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_company_analytics",
            "description": (
                f"Add a company analytics panel with four sections: Price Drivers (why the stock is moving), "
                f"Competitive Landscape (vs 2-3 peers), Metric Correlations (which KPIs drive price), and "
                f"Catalyst Watch (upcoming events). {sizing} "
                "Use when the user asks 'why is X up/down', 'what drives X stock', 'analyze X vs competitors', "
                "'company analytics for X', 'competition for X', or 'price drivers for X'."
            ),
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_company_analytics_compare",
            "description": (
                f"Add a side-by-side head-to-head comparison of TWO companies. Two columns, each with "
                f"that company's Price Drivers and Catalyst Watch, plus a scoreboard highlighting which "
                f"company leads on Revenue Growth, Operating Margin, P/E, Market Cap, YTD and 1Y return. {sizing} "
                "Use when the user asks to 'compare X vs Y', 'X vs Y company analytics', 'X or Y — which is "
                "better', or wants a side-by-side deep dive of two specific tickers. Prefer this over two "
                "separate add_company_analytics panels when exactly two companies are being compared."
            ),
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"},
                            "description": f"Exactly two tickers in compare order. Each one of: {syms}"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_data_universe",
            "description": (
                f"Add a data-universe panel showing the investable universe: symbols with sector, "
                f"industry, listing venue and market cap, plus coverage statistics and data provenance "
                f"(live vs mock). Optionally filter by sector. {sizing} "
                "Use when the user asks what's covered, the universe, data coverage, tracked symbols, "
                "or which names are live vs mock."
            ),
            "parameters": {"type": "object", "properties": {
                "sector": {"type": "string", "description": f"Sector ({secs}) or omit for the whole universe."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_analyst_report",
            "description": (
                "Add a DEEP, structured AI analyst write-up for a ticker (or sector): headline, an explicit "
                "bull/bear/neutral stance with a conviction score, a multi-sentence thesis, and sections for "
                "drivers, risks, catalysts, a valuation read, and a clear actionable call — grounded in the "
                f"terminal's figures. {sizing} Use for 'analyst take', 'deep analysis', 'write-up', "
                "'bull/bear case', 'investment thesis', 'should I buy/sell X', 'your view on X'. This is "
                "richer than and ADDITIVE to add_analysis; prefer it when the user wants a real analyst opinion."
            ),
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker for a company write-up. One of: {syms}"},
                "sector": {"type": "string", "description": f"Sector for a sector write-up ({secs}). Use symbol OR sector."},
                "scope": {"type": "string", "enum": ["symbol", "sector", "dashboard"], "description": "Set to 'dashboard' for a PORTFOLIO-LEVEL review across everything currently on screen (no symbol/sector needed)."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_intraday_chart",
            "description": (
                f"Add an intraday OHLCV chart for one ticker at a selectable resolution (1m, 5m, 15m, "
                f"30m, 1h), fetched live and labeled with the resolution/window served; reports a clean "
                f"unavailable state when the window exceeds source limits. {sizing} "
                "Use when the user wants intraday, minute, or hourly price action."
            ),
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker. One of: {syms}"},
                "interval": {"type": "string", "enum": ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"]},
                "range": {"type": "string", "enum": ["1d", "5d", "7d", "1mo", "60d", "3mo", "6mo", "1y", "2y"]},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbol"]},
        }},
        {"type": "function", "function": {
            "name": "add_data_quality",
            "description": (
                f"Add a data-quality panel auditing the OHLCV series behind one symbol, a sector, or the "
                f"core set: gaps, stale freshness, missing-OHLC rows, zero-volume bars and duplicate "
                f"timestamps, each tagged with provenance. {sizing} "
                "Use when the user asks about data quality, gaps, stale data, freshness, or data trust."
            ),
            "parameters": {"type": "object", "properties": {
                "symbol": {"type": "string", "description": f"Ticker ({syms}) to audit a single series, or omit."},
                "sector": {"type": "string", "description": f"Sector ({secs}) to audit a group, or omit."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_scenario",
            "description": (
                "Add a WHAT-IF / scenario panel. Parses a natural-language hypothetical into structured "
                "assumptions, runs a baseline forward projection from real return history, and layers the "
                "assumptions' estimated drift on top to show baseline vs scenario outcome, divergent projected "
                f"paths, reasoning and caveats. {sizing} Use when the user poses a hypothetical: 'what if', "
                "'if I do X then Y', 'if rates fall 100bps', 'if NVDA margins compress to 40%', 'suppose', "
                "'scenario where', or asks to stress a shock. Pass the user's full hypothetical as `prompt`."
            ),
            "parameters": {"type": "object", "properties": {
                "prompt": {"type": "string", "description": "The user's full natural-language what-if statement."},
                "symbol": {"type": "string", "description": f"Primary ticker if the what-if targets one name ({syms})."},
                "sector": {"type": "string", "description": f"Sector if the what-if targets a sector ({secs})."},
                "amount": {"type": "number", "description": "Dollar amount invested, e.g. 1000000 for $1M. When given, baseline vs scenario terminal outcomes are shown in dollars."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["prompt"]},
        }},
        {"type": "function", "function": {
            "name": "add_risk_monitor",
            "description": (
                "Add a RISK MANAGEMENT & MONITORING desk for a book: live gross/net/sector/factor "
                "exposures and position concentrations, real historical VaR/CVaR plus the factor model's "
                "predicted volatility, a configurable LIMITS framework (max gross/net/position/sector/"
                "factor and a daily VaR cap) with in-limit/breach status and a breach list, HISTORICAL "
                "STRESS replaying real crisis-window returns (2020 COVID, 2022 rate shock, 2008 GFC, "
                "Q4-2018, Aug-2015) onto the book, and HYPOTHETICAL STRESS mapping factor/asset/market "
                f"shocks through the book's real exposures. {sizing} Use when the user asks to monitor or "
                "manage portfolio risk, check exposures, limits or breaches, run a stress test, or 'how "
                "much could I lose if markets crash / rates spike / momentum reverses'. For a "
                "dashboard-wide review of what's on screen, omit symbols. Names without coverage are "
                "flagged, never imputed."
            ),
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Book tickers. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional signed NAV-fraction weights aligned with symbols (negative = short, e.g. 0.3 or -0.2). Default: equal-weight long."},
                "nav": {"type": "number", "description": "Book NAV in USD (default 10,000,000)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the book."},
                "limits": {"type": "object", "description": "Optional limit overrides: maxGross, maxNet, maxPosition, maxSector, maxFactor (multiples/fractions) and varLimit (daily VaR fraction)."},
                "factor_shocks": {"type": "object", "description": "Optional custom factor shocks in percent, e.g. {\"Momentum\": -8, \"Value\": 5}. Factors: Market, Size, Value, Momentum, Volatility, Quality."},
                "asset_shocks": {"type": "object", "description": "Optional per-ticker price shocks in percent, e.g. {\"NVDA\": -20}."},
                "market_shock": {"type": "number", "description": "Optional broad-market shock in percent (shocks the Market/beta factor), e.g. -10."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_stress_test",
            "description": (
                "Add a SCENARIO ANALYSIS & STRESS TEST panel for a book: estimates the P&L impact "
                "under named historical stress events (2020 COVID −34%, 2022 rate shock −28%, 2008 GFC "
                "−55%) and macro shocks (+200bps rate shock, oil +50%) by scaling each holding's REAL "
                "measured beta (to the market / 10y yield / crude oil) by the scenario's headline shock, "
                f"then weighting by positions. {sizing} Shows per-scenario portfolio impact plus the "
                "individual holding impacts. Use when the user asks to 'stress test my portfolio', wants "
                "scenario P&L, 'how would my book do in a 2008/COVID/rate-shock/oil scenario', or 'crash "
                "test'. For a dashboard-wide test of what's on screen, omit symbols. This is the focused "
                "scenario table; add_risk_monitor is the fuller risk DESK (exposures + limits). Names "
                "whose beta can't be fit from real data are flagged, never imputed."
            ),
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Book tickers. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional signed NAV-fraction weights aligned with symbols (negative = short). Default: equal-weight long."},
                "nav": {"type": "number", "description": "Book NAV in USD (default 10,000,000)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the book."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_strategy_desk",
            "description": (
                "Add the STRATEGY LIFECYCLE DESK: a roster of every systematic strategy across the "
                "research → backtest → paper → live lifecycle with its stage, exposures and live "
                "(real-price) P&L, plus a marked paper-book detail (positions, NAV/P&L curve, realized "
                f"stats, promotion check) for one strategy. {sizing} Use for 'show the desk', 'my "
                "strategies', 'the paper book', 'strategy lifecycle', or after a lifecycle action. Pass "
                "`strategy` to focus a specific one by name. This shows existing strategies; it does NOT "
                "create, paper-trade, promote, demote or retire — those are handled separately."
            ),
            "parameters": {"type": "object", "properties": {
                "strategy": {"type": "string", "description": "Optional strategy name to focus the detail block on."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_multi_strategy",
            "description": (
                "Add the MULTI-STRATEGY CAPITAL ALLOCATION & firm-level risk panel: treats every "
                "paper/live strategy as a SLEEVE of one combined firm book and recommends how to split "
                "capital across the sleeves. Shows the combined book (total NAV, P&L, netted exposures), "
                "cross-strategy correlation from the sleeves' REAL daily NAV snapshots, firm-level risk "
                "(combined vol, per-sleeve contribution to risk, concentration, diversification benefit) "
                "and recommended vs current sleeve weights. "
                f"{sizing} Use for 'allocate capital across my strategies', 'firm-level risk', 'how should "
                "I split capital between my sleeves', 'risk budget across strategies', 'portfolio of "
                "strategies'. This is the FIRM view over MANY strategies — use add_strategy_desk for a "
                "single-strategy roster/paper book and add_portfolio_optimizer to optimize weights of "
                "individual TICKERS. Recommendation only — it does not move capital."
            ),
            "parameters": {"type": "object", "properties": {
                "method": {"type": "string", "enum": ["equal_weight", "risk_parity", "target_risk"],
                           "description": "Allocation method across sleeves (default risk_parity)."},
                "target_vol": {"type": "number", "description": "Target annualized firm volatility for the target_risk method, e.g. 0.10 for 10%."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "add_rebalance_plan",
            "description": (
                "Add a COST-AWARE REBALANCE PLAN: the share-level trade list (buy/sell per name) to "
                "move a strategy's paper book from its CURRENT weights to its latest signal TARGETS, "
                "priced with the REAL square-root market-impact model — expected (modeled) cost plus a "
                "realized intraday-execution-sim cost per name, with names lacking real intraday data "
                f"flagged (never faked), and an updated weights/NAV view. {sizing} Use for 'rebalance my "
                "strategy', 'what trades to get to target', 'rebalance plan', 'preview the trades'. Set "
                "`apply` to TRUE to actually apply the trades to the paper book, or FALSE / omit to only "
                "PREVIEW them. Pass `strategy` to target one by name."
            ),
            "parameters": {"type": "object", "properties": {
                "strategy": {"type": "string", "description": "Optional strategy name to rebalance."},
                "apply": {"type": "boolean", "description": "True = apply trades to the book; False/omit = preview only."},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
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
    "add_alerts": "alerts",
    "add_compliance": "compliance",
    "add_tca_report": "tca_report",
    "add_macro_dashboard": "macro_dashboard",
    "add_yield_curve": "yield_curve",
    "add_sovereign_compare": "sovereign_compare",
    "add_bond_rv": "bond_rv",
    "add_cds_pricer": "cds_pricer",
    "add_credit_stress": "credit_stress",
    "add_economic_releases": "economic_releases",
    "add_series_revisions": "series_revisions",
    "add_cashflow_duration": "cashflow_duration",
    "add_portfolio_risk": "portfolio_risk",
    "add_backtest": "backtest",
    "add_walk_forward": "walk_forward",
    "add_walk_forward_compare": "walk_forward_compare",
    "add_monte_carlo": "monte_carlo",
    "add_correlation_matrix": "correlation_matrix",
    "add_factor_analysis": "factor_analysis",
    "add_risk_model": "risk_model",
    "add_risk_comparison": "risk_comparison",
    "add_factor_exposures": "factor_exposures",
    "add_performance_pnl": "performance_pnl",
    "add_brinson_attribution": "brinson_attribution",
    "add_factor_attribution": "factor_attribution",
    "add_factor_performance": "factor_performance",
    "add_tear_sheet": "tear_sheet",
    "add_portfolio_optimizer": "portfolio_optimizer",
    "add_signal_research": "signal_research",
    "add_signal_scorecard": "signal_scorecard",
    "add_signal_portfolio": "signal_portfolio",
    "add_combined_alpha": "combined_alpha",
    "add_shorting_desk": "shorting_desk",
    "add_iv_surface": "iv_surface",
    "add_options_chain": "options_chain",
    "add_options_screener": "options_screener",
    "add_options_strategy": "options_strategy",
    "add_vol_term_structure": "vol_term_structure",
    "add_structured_product": "structured_product",
    "add_supply_chain": "supply_chain",
    "add_dcf_model": "dcf_model",
    "add_earnings_transcript": "earnings_transcript",
    "add_earnings_calendar": "earnings_calendar",
    "add_etf_holdings": "etf_holdings",
    "add_etf_exposure": "etf_exposure",
    "add_ma_tracker": "ma_tracker",
    "add_company_analytics": "company_analytics",
    "add_company_analytics_compare": "company_analytics_compare",
    "add_data_universe": "data_universe",
    "add_intraday_chart": "intraday_chart",
    "add_data_quality": "data_quality",
    "add_analyst_report": "analyst_report",
    "add_analyst_compare": "analyst_compare",
    "add_scenario": "scenario",
    "add_risk_monitor": "risk_monitor",
    "add_stress_test": "stress_test",
    "add_strategy_desk": "strategy_desk",
    "add_multi_strategy": "multi_strategy",
    "add_rebalance_plan": "rebalance_plan",
}


_SIZING = "Width is grid columns 3-12 (12 = full row). Height is row units 2-6."


def _dynamic_tools() -> list:
    """Tool schemas for AI-generated (dynamic) skills, so the LLM can dispatch them."""
    tools = []
    for d in dynamic_skills.get_definitions():
        props = dict(d.get("parameters") or {})
        props.setdefault("width", {"type": "integer"})
        props.setdefault("height", {"type": "integer"})
        tools.append({"type": "function", "function": {
            "name": f"add_{d['panel_type']}",
            "description": f"{d['description']} {_SIZING}",
            "parameters": {"type": "object", "properties": props},
        }})
    return tools


def _all_tools() -> list:
    return _tools() + _dynamic_tools()


def _type_of_tool(name: str) -> Optional[str]:
    """Map a tool name to a panel type, supporting both built-in and dynamic skills."""
    if name in _TOOL_TO_TYPE:
        return _TOOL_TO_TYPE[name]
    if name.startswith("add_"):
        cand = name[4:]
        if cand in skills.SKILLS:
            return cand
    return None


def _system_prompt() -> str:
    return (
        "You are the orchestrator of an agentic market terminal that tracks live market "
        "data across three sectors: semiconductors, energy, and AI/tech. When the user sends a "
        "request, you compose a focused dashboard by calling the panel tools. Rules:\n"
        "- Call multiple tools in one turn to build a coherent dashboard (typically 2-5 panels).\n"
        "- Choose panel types that actually answer the request. For a single stock deep-dive, a "
        "price chart + fundamentals + news + analysis works well. For 'what's moving', use a "
        "heatmap + screener. For comparisons, use the comparison tool.\n"
        "- The catalog spans US (NASDAQ/NYSE) and Singapore (SGX) names. When the user scopes a "
        "screener or heatmap to a market ('SGX stocks', 'Singapore market heatmap', 'US "
        "semiconductors', 'Singapore banks'), pass country ('United States'/'Singapore') and/or "
        "exchange ('NASDAQ'/'NYSE'/'SGX') to add_screener / add_heatmap, combined with sector when given.\n"
        "- For derivatives requests: vol surface → add_iv_surface; options chain/calls and puts/all strikes → add_options_chain; "
        "cross-symbol options SCREEN/scan ('find/scan/screen options across names', 'high-IV calls', "
        "'cheapest puts in tech', 'unusual options volume', 'options expiring within N days', 'widest skew') "
        "→ add_options_screener (optionally pass sector/country/exchange and filters like iv_min, dte_max, "
        "option_type, moneyness, rank_by); "
        "options strategy → add_options_strategy; "
        "VIX/vol curve → add_vol_term_structure; barrier/exotic → add_structured_product.\n"
        "- For macro and fixed income: global view → add_macro_dashboard; single-country yield curve → add_yield_curve; "
        "comparing sovereign curves across countries/currencies (e.g. 'US vs German curve', 'UST vs Bund', "
        "'Treasury vs Gilt 10Y spread') → add_sovereign_compare (pass the 2–4 region codes); "
        "bond RV → add_bond_rv; CDS → add_cds_pricer; credit stress / IG vs HY spreads / credit "
        "conditions / spread widening → add_credit_stress; duration/cash flows → add_cashflow_duration. "
        "For economic data: the economic calendar / data releases / when CPI, jobs, GDP come out, with "
        "reported vs prior values → add_economic_releases; data revisions / vintages / initial vs revised "
        "prints / how a FRED series (e.g. GDP, payrolls) was revised, or to pull a FRED series id → "
        "add_series_revisions (pass series_id). Both use live FRED/ALFRED data and fail honestly when unavailable. "
        "Fixed-income panels use live data: US Treasury par yields come from the U.S. Treasury daily "
        "curve, and credit spreads (bond OAS, CDS proxies) from live ICE BofA OAS indices; each panel "
        "labels its source live/mock so you can tell when a feed is unavailable.\n"
        "- For alert requests ('alert me', 'notify me', 'set up alerts', 'watch for block trades/sweeps', "
        "'manage alert rules'), use add_alerts (optionally with the symbol to pre-fill).\n"
        "- For pre-trade risk / compliance requests ('is this trade allowed', 'can I trade X', "
        "'show/edit the restricted list', 'add X to the watch list', 'set risk limits', "
        "'engage the kill switch', 'halt trading', 'compliance audit'), use add_compliance "
        "(optionally with a strategy name to pre-check that strategy's book).\n"
        "- For microstructure/execution requests: order book → add_order_book; trade flow/unusual activity → add_trade_flow; "
        "TCA / execution simulation / slippage / market impact / VWAP-TWAP-POV / 'cost to trade into a portfolio' → add_tca_report "
        "(pass symbols+target_weights for a portfolio, or symbol+side+notional for one name).\n"
        "- For news requests, use add_news. If the request is about a tracked ticker or sector, "
        "pass scope_type='symbol'/'sector'. For ANY theme or topic that is not a tracked ticker "
        "or sector ('cybersecurity news', 'AI chip shortage', 'oil prices', 'EV demand', "
        "'rate cuts'), pass scope_type='topic' and put the user's topic words in scope so the "
        "feed is about that topic, not generic market news.\n"
        "- For supply chain requests ('suppliers', 'supply chain', 'vendors'), use add_supply_chain.\n"
        "- For DCF / valuation / intrinsic value requests, use add_dcf_model.\n"
        "- For earnings call / transcript / 'what did management say' requests, use add_earnings_transcript.\n"
        "- For the earnings calendar / upcoming earnings / earnings dates / 'who reports next' / "
        "'when does X report', use add_earnings_calendar.\n"
        "- For ETF holdings / constituents / 'what's in <ETF>' / 'holdings of <ETF>' / 'top holdings', "
        "use add_etf_holdings. For the reverse — 'which ETFs hold <stock>' / 'what funds own <stock>' / "
        "a stock's ETF exposure — use add_etf_exposure.\n"
        "- For M&A / deal flow / mergers / acquisitions / arb spread requests, use add_ma_tracker.\n"
        "- For backtest / strategy / Sharpe / drawdown requests, use add_backtest. For research-integrity "
        "checks — 'is this strategy overfit / robust / data-mined', out-of-sample or walk-forward validation, "
        "deflated Sharpe, PBO / probability of backtest overfitting, multiple-testing haircut — use "
        "add_walk_forward (a separate mode from add_backtest). For Monte Carlo / "
        "simulation / forward projection / 'probability of loss' / scenario forecast requests, use add_monte_carlo.\n"
        "- For portfolio risk requests, pick the right panel: risk decomposition / factor vs specific risk / "
        "MCTR / 'where is my risk coming from' / risk model → add_risk_model; COMPARING the risk of TWO "
        "portfolios ('is A riskier / better diversified than B', 'compare risk of X vs Y side by side') → "
        "add_risk_comparison (pass symbols_a and symbols_b, plus optional weights_a/weights_b and name_a/name_b); "
        "factor tilts / style exposures / "
        "'how is my portfolio positioned across factors' → add_factor_exposures; simple VaR / tracking error → "
        "add_portfolio_risk. A risk model + factor exposures pair makes a strong portfolio-risk dashboard.\n"
        "- For portfolio construction / optimization ('build/optimize/rebalance a portfolio', 'optimal "
        "weights', 'how should I allocate', 'max-Sharpe / minimum-variance / risk-parity / Black-Litterman "
        "/ HRP portfolio', 'size my positions', 'target-vol portfolio'), use add_portfolio_optimizer. Pass "
        "method (max_sharpe/min_variance/target_vol/black_litterman/risk_parity/hrp), an optional sector or "
        "symbols for the candidate universe, and constraints (max_position, long_short, max_sector, "
        "gross_limit, target_vol). Pair with add_risk_model to show where the optimized book's risk sits.\n"
        "- For performance & attribution requests, pick the right panel: P&L / performance vs a benchmark / "
        "returns + Sharpe / drawdowns for a book → add_performance_pnl; performance attribution / allocation vs "
        "selection / Brinson / 'where did my out/under-performance come from' → add_brinson_attribution; factor "
        "attribution / which factors drove my return / per-factor contribution to return → add_factor_attribution; "
        "how factors have PERFORMED over time / which factors are paying off or being rewarded / cumulative factor "
        "returns / style premia over time → add_factor_performance; "
        "a full 'tear sheet' / complete performance review combining P&L, drawdowns, Brinson and factor "
        "attribution → add_tear_sheet (full width). These take symbols (+ optional weights, range). P&L and "
        "tear sheet also take a real benchmark ETF (default SPY; pass benchmark=QQQ/IWM/DIA/VTI/VOO if the user "
        "names one, e.g. 'vs the Nasdaq' → QQQ).\n"
        "- For alpha signal research (rank IC, information coefficient, IC decay, signal turnover, "
        "quantile/decile long-short spread, 'does <signal> predict returns'), use add_signal_research with one "
        "signal of momentum/short_reversal/low_volatility/value/quality. To compare or rank several signals "
        "('signal scorecard', 'which signal works best', 'compare value vs momentum'), use add_signal_scorecard. "
        "To BUILD a tradeable portfolio/strategy FROM a signal ('build a portfolio from momentum', 'turn the value "
        "signal into a strategy', 'size positions from <signal>', 'long-short book from <signal>'), use "
        "add_signal_portfolio (scheme=top_quantile for long-only, long_short for a dollar-neutral spread). "
        "To BLEND several signals into ONE composite alpha ('combine momentum, value and quality', 'composite "
        "alpha', 'signal ensemble', 'blend these signals'), use add_combined_alpha with the component signals and "
        "a method (equal_weight, ic_weighted, or inverse_correlation).\n"
        "- For the REAL COST OF SHORTING ('borrow cost', 'cost/fee to short X', 'how expensive is it to short', "
        "'is X hard to borrow', 'can I even short X', 'carrying cost of my shorts', 'financing cost', 'margin "
        "and leverage on my book', 'maintenance margin / am I over-levered'), use add_shorting_desk. It tiers "
        "each name's borrow fee from real liquidity (general-collateral vs hard-to-borrow vs locate-infeasible), "
        "anchors financing to the live 3M Treasury bill, and reports the carrying drag plus the Reg-T margin / "
        "leverage / breach profile. Pass `symbols` for a dollar-neutral book, or `longs`/`shorts`/`weights` and "
        "`capital`. Prefer add_risk_monitor for exposures/limits and add_portfolio_optimizer to CONSTRUCT a book.\n"
        "- For company analytics requests ('why is X up/down', 'what drives X', 'analyze X vs competitors', "
        "'company analytics for X', 'competition for X', 'price drivers for X'), use add_company_analytics. "
        "For a head-to-head deep dive of EXACTLY TWO named companies ('compare X vs Y', 'X vs Y company "
        "analytics', 'X or Y — which is better'), use add_company_analytics_compare with both tickers in "
        "the symbols array instead of two separate panels.\n"
        "- For data-layer requests: universe/coverage/'what's tracked'/'live vs mock' → add_data_universe; "
        "intraday/minute/hourly price action → add_intraday_chart; data quality/gaps/stale/freshness/'can I "
        "trust the data' → add_data_quality.\n"
        "- For a DEEP analyst opinion ('analyst take', 'deep analysis', 'write-up', 'bull/bear case', "
        "'investment thesis', 'should I buy/sell X', 'your view on X'), use add_analyst_report (richer than "
        "add_analysis). Pair it with a price chart for context. If the user asks to analyze/review "
        "'my dashboard', 'this dashboard', 'everything on screen' or 'my portfolio', call add_analyst_report "
        "with scope='dashboard' (no symbol/sector) for a portfolio-level take across the kept panels. "
        "To COMPARE the analyst stance/call across several names side by side ('compare analyst views on "
        "NVDA, AMD, TSM', 'analyst take on X vs Y', 'who's the better buy, X or Y'), use add_analyst_compare "
        "with the list of symbols instead.\n"
        "- For WHAT-IF / hypothetical requests ('what if', 'if I do X then Y', 'if rates fall 100bps', "
        "'if X margins compress to 40%', 'suppose', 'scenario where'), use add_scenario and pass the user's "
        "full hypothetical as the prompt argument.\n"
        "- For SCENARIO ANALYSIS / STRESS TEST requests ('stress test my portfolio', 'scenario P&L', 'crash "
        "test', 'how would my book do in a 2008 / COVID / rate-shock / oil scenario'), use add_stress_test. "
        "It returns a focused table of per-scenario portfolio impacts (2020 COVID, 2022 rate shock, 2008 GFC, "
        "+200bps rates, oil +50%) with per-holding impacts, scaling each name's REAL beta. Prefer it over "
        "add_risk_monitor when the user wants scenario P&L specifically rather than the full risk desk.\n"
        "- For RISK MANAGEMENT / MONITORING requests ('monitor/manage my risk', 'risk dashboard', 'check my "
        "exposures', 'gross/net exposure', 'am I within limits', 'any limit breaches', "
        "'how much could I lose if markets crash / rates spike / momentum reverses'), use add_risk_monitor. "
        "Pass signed weights (negative = short) when the user describes a long/short book; pass limits to "
        "override defaults, and factor_shocks/asset_shocks/market_shock for a specific hypothetical stress. "
        "This is the risk DESK (exposures + limits + crisis & shock stress); use add_risk_model instead when "
        "the user only wants factor-vs-specific risk decomposition/MCTR, and add_scenario for a narrative "
        "what-if projection.\n"
        "- For STRATEGY LIFECYCLE / paper-book / 'desk' requests that only VIEW state ('show the desk', "
        "'my strategies', 'the paper book', 'strategy lifecycle', 'how is the momentum strategy doing'), "
        "use add_strategy_desk (pass `strategy` to focus one). Lifecycle ACTIONS — create / paper-trade / "
        "promote / demote / retire / REBALANCE a strategy — are handled before you are called, so do not try to "
        "perform them; just present the desk.\n"
        "- For FIRM-LEVEL capital allocation across MANY strategies ('allocate capital across my strategies', "
        "'firm-level risk', 'how should I split capital between my sleeves', 'risk budget across strategies'), "
        "use add_multi_strategy — it treats each paper/live strategy as a sleeve, combines them into one firm "
        "book and recommends sleeve weights (equal_weight / risk_parity / target_risk). This is distinct from "
        "add_strategy_desk (single-strategy roster) and add_portfolio_optimizer (weights of individual tickers).\n"
        "- For COST-AWARE REBALANCING of a strategy's paper book ('rebalance my strategy', 'what trades to "
        "get to target', 'rebalance plan', 'preview the trades'), use add_rebalance_plan: it diffs the book "
        "to its latest signal targets and prices the trade list with the real square-root impact model. Set "
        "`apply` true only when the user clearly wants to execute the trades; otherwise leave it off to "
        "preview. (Strategy rebalances are usually handled before you are called.)\n"
        "- Decide each panel's width (3-12 grid columns) and height (2-6 row units). Make the "
        "primary panel larger; supporting panels narrower. A full-width hero is width 12.\n"
        "- Only use tickers and sectors that exist in the dataset.\n"
        "- After the tool calls, the panels are rendered for the user; your text content should be "
        "a one or two sentence summary of what you assembled and why. Keep it crisp.\n"
        f"- Popular tickers include: {', '.join(repo.prompt_symbols(60))}. The dataset also covers "
        "hundreds more US and Singapore (SGX) names across every sector; SGX names use their base "
        "code (e.g. D05 for DBS, O39 for OCBC, Z74 for Singtel) with no .SI suffix.\n"
        f"- Valid sectors: {', '.join(data.SECTORS.keys())}."
    )


# ----------------------------- strategy lifecycle -----------------------------
# Lifecycle ACTIONS (create / paper-trade / promote / demote / retire) mutate the
# persisted registry, so they are handled deterministically BEFORE the normal
# panel-composition flow — this keeps them reliable in both the Console and Voice
# Mode and independent of the LLM. Pure VIEW requests ("show the desk") fall
# through to the standard skill path (strategy_desk).
_SIGNAL_KEYWORDS = (
    ("momentum", ("momentum", "trend")),
    ("short_reversal", ("reversal", "mean reversion", "reversion")),
    ("low_volatility", ("low vol", "low volatility")),
    ("value", ("value", "earnings yield", "cheap")),
    ("quality", ("quality", "net margin", "profitab")),
)


def _signal_in_query(q: str) -> Optional[str]:
    for key, kws in _SIGNAL_KEYWORDS:
        if any(k in q for k in kws):
            return key
    return None


def _wants_trade_preview(q: str) -> bool:
    """Phrasings that ask for the trade list to reach a strategy's targets but do
    not contain the word "rebalance" (e.g. 'what trades to get to target')."""
    return bool(
        re.search(r"\bwhat trades?\b", q)
        or re.search(r"\btrade list\b", q)
        or re.search(r"\brebalance plan\b", q)
        or re.search(r"\bget (me )?to (the )?targets?\b", q)
        or re.search(r"\btrades?\b[^.]*\bto (the )?targets?\b", q)
        or re.search(r"\bpreview (the )?trades?\b", q)
    )


def _rebalance_should_apply(q: str) -> bool:
    """True = actually apply the trades, False = preview only. Default is apply
    ('rebalance my strategy'); preview/plan phrasings opt out unless the user is
    explicit about applying/executing."""
    explicit_apply = bool(re.search(r"\bapply\b|\bexecute\b|\bactually\b|\bcommit\b|\bgo ahead\b", q))
    if explicit_apply:
        return True
    preview = bool(
        re.search(r"\bpreview\b|\bplan\b|\bdry[- ]?run\b|\bsimulate\b|\bwhat trades?\b|\btrade list\b", q)
        or re.search(r"\bwithout (applying|executing|trading|rebalanc)", q)
        or re.search(r"\bget (me )?to (the )?targets?\b", q)
    )
    return not preview


def _rebalance_summary(data: dict, target: dict, applied: bool) -> str:
    """Build the chat summary from a rebalance_plan panel payload."""
    name = data.get("strategyName") or target.get("name")
    if data.get("status") == "empty":
        return data.get("message") or "You don't have any strategies to rebalance yet."
    if not data.get("hasTrades"):
        return f"{name} is already at its latest targets — no trades needed."
    n = data.get("tradeCount") or 0
    exp = (data.get("expected") or {})
    cost = exp.get("costUsd")
    cost_txt = f"${cost:,.0f}" if isinstance(cost, (int, float)) else "n/a"
    turn = data.get("turnoverPct")
    turn_txt = f"{turn:.1f}% turnover, " if isinstance(turn, (int, float)) else ""
    unsupported = exp.get("unsupportedCount") or 0
    flag = f" ({unsupported} flagged — no real cost data)" if unsupported else ""
    if applied and data.get("applied"):
        if data.get("established"):
            return (f"Built {name}'s book from its latest targets — {n} positions, "
                    f"{cost_txt} modeled cost{flag}.")
        return (f"Rebalanced {name} to its latest targets — {n} trades, {turn_txt}"
                f"{cost_txt} modeled cost{flag}.")
    return (f"Here's the plan to rebalance {name} to its latest targets — {n} trades, "
            f"{turn_txt}{cost_txt} estimated cost{flag}. Say 'apply' to execute them.")


def _lifecycle_action(q: str) -> Optional[str]:
    if re.search(r"\bretire\b|\bdecommission\b|\bshut down\b|\barchive\b|\bkill the\b", q):
        return "retire"
    if re.search(r"\bpromote\b|\bgo[es]? live\b|\b(push|move|take|send|put)\b[^.]*\blive\b", q):
        return "promote"
    if re.search(r"\bdemote\b|\bmove\b[^.]*\bback\b|\brevert\b[^.]*\bpaper\b|\bstep\b[^.]*\bdown\b", q):
        return "demote"
    if re.search(r"\bpaper[- ]?trad\w*\b|\bstart paper\b|\badd\b[^.]*\bpaper book\b", q):
        return "paper"
    # Rebalance is only a lifecycle action when it clearly refers to a strategy
    # (the word "strateg", "book", or a signal keyword) — otherwise "rebalance a
    # portfolio" must fall through to the portfolio-optimization path. The
    # trade-list preview phrasings ("what trades to get to target", "rebalance
    # plan", "trade list") also resolve to a strategy here.
    if re.search(r"\brebalanc\w*\b", q) and (
        re.search(r"\bstrateg|\bbook\b", q) or _signal_in_query(q) is not None
    ):
        return "rebalance"
    if _wants_trade_preview(q):
        return "rebalance"
    if re.search(r"\b(create|register|set up|build|spin up|make)\b[^.]*\bstrateg", q) or re.search(r"\bnew strateg", q):
        return "create"
    return None


def _extract_strategy_name(q: str) -> Optional[str]:
    m = re.search(r'(?:called|named)\s+"?([A-Za-z0-9 _-]{2,40})"?', q)
    if m:
        return m.group(1).strip().strip('"')
    m = re.search(r'"([^"]{2,40})"', q)
    if m:
        return m.group(1).strip()
    return None


def _resolve_target_strategy(query: str, signal: Optional[str]) -> Optional[dict]:
    """Find the strategy a lifecycle command refers to: by explicit name tokens,
    by signal, else the single / most recently touched one (handles 'it')."""
    strategies = strategy_store.list_strategies()
    if not strategies:
        return None
    ql = query.lower()
    best = None
    best_len = -1
    for s in strategies:
        nm = (s.get("name") or "").lower()
        toks = [t for t in re.split(r"[^a-z0-9]+", nm)
                if len(t) > 2 and t not in ("the", "strategy")]
        if toks and all(t in ql for t in toks) and len(nm) > best_len:
            best, best_len = s, len(nm)
    if best:
        return best
    if signal:
        for s in strategies:
            if s.get("signal") == signal:
                return s
    if len(strategies) == 1:
        return strategies[0]
    return max(strategies, key=lambda s: s.get("updatedAt") or "")


def _session_portfolio(sid: str) -> Optional[dict]:
    """Most recent ``signal_portfolio`` panel payload in this session, if any.

    Lets the lifecycle handler promote a freshly constructed portfolio into the
    desk using its own holdings/weights rather than re-deriving from a signal.
    """
    for p in reversed(state.get_dashboard(sid) or []):
        if p.get("type") == "signal_portfolio" and isinstance(p.get("data"), dict):
            return p.get("data")
    return None


def _wants_portfolio_promotion(q: str) -> bool:
    """True when the user asks to track / paper-trade an existing constructed
    portfolio (e.g. 'paper trade this portfolio', 'track this book').

    Requires an explicit portfolio/book/holdings reference (not a bare 'it') so
    it never hijacks a strategy-by-name command like 'paper trade the value
    strategy'. The session must actually hold a portfolio for this to fire.
    """
    refers = re.search(r"\bportfolio\b|\bholdings\b|\bconstruction\b|\bbook\b", q)
    if not refers:
        return False
    return bool(re.search(
        r"\btrack\b|\bpaper[- ]?trad\w*\b|\bregister\b|\bmonitor\b|\bpromote\b"
        r"|\bturn\b[^.]*\bstrateg|\bmake\b[^.]*\bstrateg|\badd\b[^.]*\bdesk\b", q))


def _register_portfolio_strategy(query: str, data: dict) -> Tuple[dict, str, List[str]]:
    """Register a strategy from a constructed signal_portfolio's holdings/weights
    and start paper-trading it. Returns (view, summary, dropped_symbols).

    The portfolio's signed fraction weights are passed through verbatim, so a
    long-only book stays long and a dollar-neutral long/short book keeps its
    short leg. Names the portfolio already excluded — plus any holding that no
    longer resolves to a real company — are carried onto the strategy's
    construction so the real-data-only / exclusion contract is preserved.
    """
    holdings = data.get("holdings") or []
    picks = [
        (str(h.get("symbol")).upper(), float(h.get("weight") or 0.0))
        for h in holdings
        if h.get("symbol") and float(h.get("weight") or 0.0) != 0.0
    ]
    resolved = [(s, w) for s, w in picks if repo.get_company(s)]
    dropped = [s for s, _ in picks if not repo.get_company(s)]
    if not resolved:
        raise ValueError("portfolio has no tradeable holdings to register")

    symbols = [s for s, _ in resolved]
    weights = [w for _, w in resolved]
    signal = engine.normalize_signal(data.get("signal") or "momentum")

    # Carry the portfolio's own exclusions (insufficient history / missing
    # fundamentals) plus any dropped name onto the strategy's construction.
    excl: List[str] = []
    for e in data.get("excludedNames") or []:
        if isinstance(e, dict) and e.get("symbol"):
            excl.append(str(e["symbol"]))
        elif isinstance(e, str):
            excl.append(e)
    excl.extend(dropped)

    scheme_label = data.get("schemeLabel") or ""
    label = data.get("label") or engine.signal_label(signal)
    name = _extract_strategy_name(query) or (
        f"{label} {scheme_label}".strip() + " Portfolio").strip()

    cons = {
        "source": "signal_portfolio",
        "scheme": data.get("scheme"),
        "schemeLabel": scheme_label or None,
        "universe": data.get("universe"),
    }
    if excl:
        cons["excluded"] = excl

    capital = _extract_capital(query)
    target = strategy.create_strategy(
        name=name, signal=signal, symbols=symbols, weights=weights,
        construction=cons, capital=capital, paper=True,
    )
    excl_note = f" ({len(excl)} names excluded)" if excl else ""
    msg = (f"Promoted {target['name']} from your constructed portfolio into the "
           f"strategy desk and started paper-trading a ${int(target['capital']):,} "
           f"book of {len(symbols)} holdings{excl_note}.")
    return target, msg, dropped


def _extract_capital(q: str) -> Optional[float]:
    """Parse an optional book size like '$2m' / '500k of capital' from the query."""
    m = re.search(r"\$?\s*([\d,]+(?:\.\d+)?)\s*(k|m|mm|million|thousand|bn|billion)?\s*"
                  r"(?:of\s+)?(?:capital|equity|book|nav)?", q.lower())
    if not m or not m.group(2):
        return None
    amt = float(m.group(1).replace(",", ""))
    unit = m.group(2)
    if unit in ("k", "thousand"):
        amt *= 1_000
    elif unit in ("m", "mm", "million"):
        amt *= 1_000_000
    elif unit in ("bn", "billion"):
        amt *= 1_000_000_000
    return amt if amt > 0 else None


def _handle_lifecycle(query: str, sid: str, voice: bool) -> Optional[dict]:
    q = query.lower()
    action = _lifecycle_action(q)
    # Promote a freshly constructed signal portfolio into the desk: this takes
    # precedence over the generic paper/promote actions when the session holds a
    # portfolio and the user explicitly references it.
    portfolio_src = _session_portfolio(sid) if _wants_portfolio_promotion(q) else None
    if not action and portfolio_src is None:
        return None
    signal = _signal_in_query(q)
    symbols = _extract_symbols(query)
    target: Optional[dict] = None
    msg = ""
    block_result: Optional[dict] = None

    try:
        if portfolio_src is not None:
            target, msg, _dropped = _register_portfolio_strategy(query, portfolio_src)
            action = "paper"  # downstream panels treat it as a fresh paper book
        elif action == "create":
            target = strategy.create_strategy(
                name=_extract_strategy_name(query), signal=signal,
                symbols=symbols or None, paper=bool(re.search(r"\bpaper", q)),
            )
            if target.get("stage") == "paper":
                msg = (f"Created {target['name']} and started paper-trading it with a "
                       f"${int(target['capital']):,} book.")
            else:
                msg = f"Created {target['name']} in research."
        else:
            target = _resolve_target_strategy(query, signal)
            if target is None:
                if action == "paper" and (signal or symbols):
                    target = strategy.create_strategy(signal=signal, symbols=symbols or None, paper=True)
                    msg = f"Created and started paper-trading {target['name']}."
                else:
                    return {
                        "sessionId": sid, "intent": "build", "panels": state.get_dashboard(sid),
                        "summary": "You don't have any strategies yet — say e.g. "
                                   "'create a momentum strategy' or 'paper-trade the value strategy'.",
                    }
            elif action == "paper":
                target = strategy.paper_trade(target)
                msg = f"{target['name']} is now paper-trading a ${int(target['capital']):,} book."
            elif action == "promote":
                force = bool(re.search(r"\bforce\b|\boverride\b|\banyway\b", q))
                target, _ok, msg = strategy.transition(target, "live", force=force)
            elif action == "demote":
                target, _ok, msg = strategy.demote(target)
            elif action == "retire":
                target, _ok, msg = strategy.transition(target, "retired")
            elif action == "rebalance":
                # The cost-aware trade list (and the optional apply) is produced by
                # the rebalance_plan panel builder below — leave the book untouched
                # here so preview and apply share one code path.
                pass
    except strategy.ComplianceBlock as cb:
        # A hard pre-trade violation refused the trade. Surface the specific
        # reason and the compliance panel rather than silently dropping it.
        block_result = cb.result
        target = cb.view or target
        nm = (target or {}).get("name") or "the strategy"
        verb = {"paper": "Paper-trade", "promote": "Promotion", "create": "Trade"}.get(action, "Trade")
        msg = (f"{verb} refused for {nm} by pre-trade compliance: "
               f"{cb.result.get('reason')}.")
    except Exception:  # noqa: BLE001 — lifecycle must never 500 the orchestrate path
        return None

    cursor = {"x": 0, "y": 0, "rowH": 0}
    panels: List[dict] = []

    def add(panel_type, params, w, h, title=None):
        panels.append(harness.run_skill(panel_type, params, harness.pack_layout(w, h, cursor), title=title))

    # A refused trade leads with the compliance panel (showing the specific
    # breach + the rule that fired) so the trader sees exactly why it was gated.
    if block_result is not None:
        add("compliance", {"strategy": (target or {}).get("name")}, 12, 6,
            title="Pre-Trade Compliance")
    if target is None:
        state.set_dashboard(sid, panels)
        state.append_history(sid, "user", query)
        state.append_history(sid, "assistant", msg)
        return {"sessionId": sid, "summary": msg, "panels": panels, "intent": "build"}

    if action == "rebalance":
        apply = _rebalance_should_apply(q)
        panel = harness.run_skill(
            "rebalance_plan", {"strategy": target["name"], "apply": apply},
            harness.pack_layout(12, 6, cursor),
        )
        panels.append(panel)
        msg = _rebalance_summary(panel.get("data") or {}, target, apply)
        # After applying, surface the marked desk + risk pillar for the new book.
        if apply and (panel.get("data") or {}).get("applied"):
            target = _resolve_target_strategy(query, signal) or target
            add("strategy_desk", {"strategy": target["name"]}, 12, 5)
            wmap = target.get("targetWeights") or {}
            if target.get("stage") in ("paper", "live") and wmap:
                syms = list(wmap.keys())
                ws = [wmap[s] for s in syms]
                add("risk_monitor", {"symbols": syms, "weights": ws, "portfolio_name": target["name"]}, 12, 6)
    else:
        add("strategy_desk", {"strategy": target["name"]}, 12, 5)
        wmap = target.get("targetWeights") or {}
        # Link the desk into the Risk Management + Attribution pillars for the book.
        if block_result is None and target.get("stage") in ("paper", "live") and wmap:
            syms = list(wmap.keys())
            ws = [wmap[s] for s in syms]
            add("risk_monitor", {"symbols": syms, "weights": ws, "portfolio_name": target["name"]}, 12, 6)
            add("factor_analysis", {"symbols": syms}, 12, 5)

    state.set_dashboard(sid, panels)
    state.append_history(sid, "user", query)
    state.append_history(sid, "assistant", msg)
    result: dict = {"sessionId": sid, "summary": msg, "panels": panels, "intent": "build"}
    if voice:
        narration, narr_degraded = _build_narration(query, msg, panels)
        result["narration"] = narration
        # Mirror the orchestrate path: if the narrator fell back because the AI
        # was slow/unavailable, flag it and speak the same lead-in notice.
        if bool(panels) and narr_degraded:
            result["degraded"] = True
            result["note"] = _DEGRADED_NOTE
            result["narration"] = [{"text": _DEGRADED_NOTE, "panelId": None}] + narration
    return result


def _orchestrate_prelude(query: str, session_id: Optional[str]):
    """Resolve the session id and the panel set this query starts from.

    Returns ``(reset, sid, base)``. A reset (or the ``"default"`` placeholder /
    missing session) mints a fresh session so BOTH the panels and the prior
    conversation context start clean.
    """
    reset = _wants_reset(query)
    if reset or not session_id or session_id == "default":
        sid = uuid.uuid4().hex[:12]
        base: List[dict] = []
    else:
        sid = session_id
        base = state.get_dashboard(sid)
    if reset:
        base = []
    return reset, sid, base


def _question_result(query: str, sid: str, answer: str, base: List[dict]) -> dict:
    """Persist a question turn (panels unchanged) and shape the response dict."""
    state.append_history(sid, "user", query)
    state.append_history(sid, "assistant", answer)
    # Persist the (unchanged) panel set so the session keeps its dashboard.
    state.set_dashboard(sid, base)
    return {
        "sessionId": sid,
        "summary": "",
        "answer": answer,
        "intent": "question",
        "panels": base,
    }


def _orchestrate_build(query: str, sid: str, base: List[dict], voice: bool) -> dict:
    """Compose / modify the dashboard for a build request and persist it."""
    # Decide which existing panels remain relevant to this prompt, then re-pack
    # the kept panels from the top so removed panels leave no holes in the grid.
    kept = _decide_kept_panels(query, sid, base) if base else []
    kept, cursor = _repack(kept)

    panels: List[dict] = []
    summary = ""
    # Tracks whether we fell back to the keyword heuristic because the AI was
    # slow/unavailable (vs. genuinely AI-composed). Surfaced to the UI so the
    # user knows why the dashboard may look simpler than usual.
    ai_degraded = False

    if ai.ai_available():
        try:
            panels, summary = _orchestrate_llm(query, sid, kept, dict(cursor))
        except Exception:
            panels, summary = [], ""
            ai_degraded = True
    else:
        ai_degraded = True

    if not panels:
        dash_syms, dash_secs = _dashboard_subjects(kept)
        panels, summary = _orchestrate_heuristic(query, dict(cursor), dash_syms, dash_secs)

    combined = kept + panels
    state.set_dashboard(sid, combined)
    state.append_history(sid, "user", query)
    state.append_history(sid, "assistant", summary)

    # Fire any configured trade-flow alerts against the panels just built.
    alerts.evaluate_dashboard(sid, combined)

    result: dict = {"sessionId": sid, "summary": summary, "panels": combined, "intent": "build"}

    narr_degraded = False
    if voice:
        narration, narr_degraded = _build_narration(query, summary, panels)
        result["narration"] = narration

    # Only flag degradation when the fallback actually produced something — an
    # empty dashboard has nothing to explain.
    if bool(panels) and (ai_degraded or narr_degraded):
        result["degraded"] = True
        result["note"] = _DEGRADED_NOTE
        if voice:
            # Speak the same notice as a brief lead-in segment (no panel) so the
            # hands-free user hears why the walkthrough may be simpler.
            result["narration"] = [{"text": _DEGRADED_NOTE, "panelId": None}] + result["narration"]

    return result


def orchestrate(query: str, session_id: Optional[str], voice: bool = False) -> dict:
    # Each new query is evaluated against the panels already on screen: panels
    # that still serve the new request are KEPT, panels belonging to an
    # abandoned subject are dropped, and new panels are added on top.
    reset, sid, base = _orchestrate_prelude(query, session_id)

    # Lifecycle mutations (paper-trade / promote / demote / retire / create) are
    # handled here, deterministically, before the panel-composition flow.
    lifecycle = _handle_lifecycle(query, sid, voice)
    if lifecycle is not None:
        return lifecycle

    # A message can either ask a question (answer it in chat, leave the dashboard
    # untouched) or be a build/modify request (compose panels as before). Voice
    # mode always builds — its narration flow is unchanged. A reset is an explicit
    # build/clear action, never a question.
    if not voice and not reset and _classify_intent(query, sid) == "question":
        answer = _answer_question(query, sid, base)
        return _question_result(query, sid, answer, base)

    return _orchestrate_build(query, sid, base, voice)


def orchestrate_stream(query: str, session_id: Optional[str], voice: bool = False):
    """Streaming variant of :func:`orchestrate`.

    Yields event dicts:
      - ``{"type": "delta", "text": ...}`` — incremental answer text (questions only)
      - ``{"type": "done", "result": {...}}`` — the final ``DashboardSpec``-shaped dict

    Only the conversational *question* path streams token-by-token; the build
    path returns panels (not prose), so it is computed in one shot and emitted as
    a single ``done`` event. If token streaming is unavailable the answer falls
    back to a single ``delta`` carrying the whole blocking answer.
    """
    reset, sid, base = _orchestrate_prelude(query, session_id)

    lifecycle = _handle_lifecycle(query, sid, voice)
    if lifecycle is not None:
        yield {"type": "done", "result": lifecycle}
        return

    if not voice and not reset and _classify_intent(query, sid) == "question":
        parts: List[str] = []
        if ai.ai_available():
            try:
                for delta in _answer_question_stream(query, sid, base):
                    if delta:
                        parts.append(delta)
                        yield {"type": "delta", "text": delta}
            except Exception:
                parts = []  # fall through to the blocking fallback below
        answer = "".join(parts).strip()
        if not answer:
            # Streaming unavailable or produced nothing — fall back to the
            # blocking answer (model or honest message) and emit it at once.
            answer = _answer_question(query, sid, base)
            yield {"type": "delta", "text": answer}
        yield {"type": "done", "result": _question_result(query, sid, answer, base)}
        return

    yield {"type": "done", "result": _orchestrate_build(query, sid, base, voice)}


# --------------------- conversational question answering ---------------------
# Signals that a message *might* be a question rather than a build request. When
# none are present the message is unambiguously a build, so we skip the extra LLM
# classification round-trip entirely (keeps build latency low).
_QUESTION_SIGNALS = (
    r"\?",
    r"\bwhat\b", r"\bwhat'?s\b", r"\bwhy\b", r"\bhow\b", r"\bwhen\b",
    r"\bwhich\b", r"\bwho\b",
    r"\bexplain\b", r"\bdefine\b", r"\bdefinition\b", r"\bdescribe\b",
    r"\bdifference\b", r"\bmean(s|ing)?\b", r"\btell me about\b",
    r"\bhelp me understand\b", r"\bsummari[sz]e\b",
)

# Strong build cues — even when a question word is present (e.g. "what's the
# latest news on NVDA"), these mark the message as a dashboard build request.
_BUILD_CUES = (
    r"\bshow\b", r"\badd\b", r"\bbuild\b", r"\bcompose\b", r"\bpull up\b",
    r"\bbring up\b", r"\bgive me\b", r"\bdisplay\b", r"\bscreen\b",
    r"\bheatmap\b", r"\bchart\b", r"\bdashboard for\b", r"\bnews\b",
    r"\bsentiment\b", r"\bcompare\b", r"\bdeep dive\b", r"\bdcf\b",
    r"\bbacktest\b", r"\bmodel for\b", r"\bwhat'?s moving\b",
    r"\bwhat'?s the latest\b",
)


def _has_question_signal(query: str) -> bool:
    q = query.lower()
    return any(re.search(p, q) for p in _QUESTION_SIGNALS)


def _classify_intent(query: str, sid: str) -> str:
    """Return "question" or "build" for the message.

    Fast path: a message with no question signal at all is always a build, so we
    avoid an extra model call on the common case. When there *is* a question
    signal we ask the model to disambiguate (a definitional question vs. a build
    phrased as a question like "what's the latest news on NVDA"), falling back to
    a keyword heuristic if the model is unavailable.
    """
    if not _has_question_signal(query):
        return "build"
    if ai.ai_available():
        try:
            intent = _classify_intent_llm(query, sid)
            if intent in ("question", "build"):
                return intent
        except Exception:
            pass
    return "question" if _is_question_heuristic(query) else "build"


def _classify_intent_llm(query: str, sid: str) -> Optional[str]:
    sys = (
        "Classify a message sent to an agentic market terminal as either QUESTION or BUILD.\n"
        "- QUESTION: the user wants a conversational explanation in the chat, not new panels. "
        "This covers concept/definition questions ('what is a Sortino ratio', 'explain Monte Carlo "
        "VaR', \"what's the difference between IV and HV\", 'how is beta calculated') and questions "
        "about what is currently on their screen ('explain what I'm seeing', 'what does this dashboard "
        "tell me', 'summarize these panels').\n"
        "- BUILD: the user wants to see data or compose/change the dashboard ('show me NVDA news', "
        "'add a yield curve', 'compare V and MA', \"what's moving today\", 'screen biotech', 'heatmap "
        "of healthcare', 'DCF for MSFT', \"what's the sentiment on PLTR\"). A request naming a "
        "ticker or sector together with a view (news, chart, screener, heatmap, sentiment, comparison, "
        "model) is BUILD even when phrased as a question.\n"
        "Use the recent conversation for follow-ups (e.g. after a definition, 'and how is it different "
        "from Sharpe?' is a QUESTION).\n"
        'Return JSON: {"intent": "question" | "build"}.'
    )
    messages = [{"role": "system", "content": sys}]
    for h in state.get_history(sid)[-4:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": query})
    msg = ai.chat(messages, response_format={"type": "json_object"})
    content = (msg.content or "").strip()
    if not content:
        return None
    parsed = json.loads(content)
    intent = parsed.get("intent")
    return intent if intent in ("question", "build") else None


def _is_question_heuristic(query: str) -> bool:
    """Keyword fallback used only when the model is unavailable.

    Conservative: defaults to BUILD (the established behavior) unless the message
    clearly reads as a concept/definition or a "what am I seeing" question and
    carries no strong build cue.
    """
    q = query.lower().strip()
    if any(re.search(p, q) for p in _BUILD_CUES):
        return False
    concept = (
        r"\bwhat(?:'?s| is| are| does| do)\b.*\b(ratio|spread|curve|model|metric|"
        r"sharpe|sortino|beta|alpha|var|drawdown|duration|convexity|greeks|vix|iv|"
        r"hv|cds|dcf|monte carlo|backtest|skew|volatility|correlation|factor)\b",
        r"\bwhat'?s the difference\b",
        r"\b(explain|define|definition of|describe)\b",
        r"\bhow (?:do|does|is|are)\b.*\b(work|works|calculated|computed|defined|differ)\b",
        r"\bwhat (?:am i|are we) (?:seeing|looking at)\b",
        r"\bwhat (?:does|do) (?:this|these|the|my)\b.*\b(tell|mean|show|say|indicate)\b",
        r"\bhelp me understand\b",
    )
    return any(re.search(p, q) for p in concept)


def _answer_question(query: str, sid: str, panels: List[dict]) -> str:
    """Generate a conversational chat answer, grounded in on-screen panels.

    Uses the AI client (bounded timeout / no retry, like every other caller) and
    falls back to a short honest message if the model is unavailable.
    """
    if ai.ai_available():
        try:
            ans = _answer_question_llm(query, sid, panels)
            if ans:
                return ans
        except Exception:
            pass
    return _answer_fallback(panels)


# --------------------- panel-data serialization for grounding ---------------------
# These helpers turn a panel's `data` dict into a short, bounded text summary so
# the question-answering model can read the actual figures the user sees (a
# backtest's stats, equity curve, worst drawdown, notable trades, etc.) instead
# of just the title and type. Everything is capped so latency and token use stay
# reasonable even when many panels are on screen or a series is very long.
_SER_MAX_LIST = 6           # generic list items surfaced
_SER_MAX_LABELVAL = 16      # label/value rows surfaced (fundamentals, comparison)
_SER_MAX_STR = 200          # long strings truncated to this
_SER_MAX_PANEL_CHARS = 1100  # hard cap on one panel's data summary
_SER_MAX_TOTAL_CHARS = 6000  # hard cap across all panels in one prompt


def _ser_scalar(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return "n/a"
        av = abs(v)
        if av != 0 and (av < 1e-4 or av >= 1e7):
            return f"{v:.3e}"
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return s or "0"
    if isinstance(v, int):
        return str(v)
    s = str(v)
    return s if len(s) <= _SER_MAX_STR else s[:_SER_MAX_STR] + "…"


def _ser_dict(d: dict, max_keys: int = 24) -> str:
    """Flatten a dict of scalars into `k=v` pairs (used for stat blocks)."""
    parts: List[str] = []
    for k, v in list(d.items())[:max_keys]:
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            parts.append(f"{k}={_ser_scalar(v)}")
    return ", ".join(parts)


def _ser_list(key: str, lst: list) -> str:
    n = len(lst)
    if n == 0:
        return ""
    first = lst[0]
    if isinstance(first, (str, int, float, bool)):
        sample = ", ".join(_ser_scalar(x) for x in lst[:_SER_MAX_LIST])
        more = f", …(+{n - _SER_MAX_LIST} more)" if n > _SER_MAX_LIST else ""
        return f"{key}[{n}]: {sample}{more}"
    if isinstance(first, dict):
        keys = set(first.keys())
        # Label/value rows (fundamentals metrics, comparison values) -> pairs.
        if {"label", "value"} <= keys:
            rows = [f"{it.get('label')}={it.get('value')}" for it in lst[:_SER_MAX_LABELVAL]]
            more = f", …(+{n - _SER_MAX_LABELVAL} more)" if n > _SER_MAX_LABELVAL else ""
            return f"{key}[{n}]: " + ", ".join(rows) + more
        # Long time series -> just the endpoints (avoid dumping the whole curve).
        if "t" in keys and n > _SER_MAX_LIST:
            return f"{key}[{n}]: first {{{_ser_dict(first, 6)}}} … last {{{_ser_dict(lst[-1], 6)}}}"
        sample = " | ".join("{" + _ser_dict(it, 6) + "}" for it in lst[:_SER_MAX_LIST])
        more = f" …(+{n - _SER_MAX_LIST} more)" if n > _SER_MAX_LIST else ""
        return f"{key}[{n}]: {sample}{more}"
    return f"{key}[{n}]"


def _ser_generic(data: dict) -> str:
    """Degrade-gracefully serializer for any panel: scalars, stat blocks, lists."""
    parts: List[str] = []
    for k, v in data.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            parts.append(f"{k}={_ser_scalar(v)}")
        elif isinstance(v, dict):
            inner = _ser_dict(v)
            if inner:
                parts.append(f"{k}: {{{inner}}}")
        elif isinstance(v, list):
            s = _ser_list(k, v)
            if s:
                parts.append(s)
    return "; ".join(parts)


def _ser_curve(curve: list) -> str:
    """Summarize a backtest equity curve: start/end (+return), peak, trough."""
    out: List[str] = []
    for key, label in (("strategy", "strategy"), ("benchmark", "benchmark")):
        vals = [(c.get("t"), c.get(key)) for c in curve if isinstance(c.get(key), (int, float))]
        if not vals:
            continue
        start = vals[0][1]
        end = vals[-1][1]
        peak = max(vals, key=lambda x: x[1])
        trough = min(vals, key=lambda x: x[1])
        ret = (end / start - 1.0) * 100.0 if start else 0.0
        out.append(
            f"{label} equity {_ser_scalar(start)}→{_ser_scalar(end)} ({ret:+.1f}%), "
            f"peak {_ser_scalar(peak[1])} on {peak[0]}, trough {_ser_scalar(trough[1])} on {trough[0]}"
        )
    return "; ".join(out)


def _ser_trades(trades: list) -> str:
    n = len(trades)
    if n == 0:
        return "no trades"
    buys = sum(1 for t in trades if t.get("action") == "BUY")
    sells = sum(1 for t in trades if t.get("action") == "SELL")
    summary = f"{n} trades ({buys} BUY/{sells} SELL)"

    def _pnl(t: dict) -> float:
        try:
            return float(t.get("pnl") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _pnl_pct(t: dict) -> float:
        try:
            return float(t.get("pnlPct") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    # Rank realized P&L by closed round-trips (trades that booked a gain/loss).
    closed = [t for t in trades if _pnl(t) != 0.0]
    if closed:
        total = sum(_pnl(t) for t in closed)
        wins = sum(1 for t in closed if _pnl(t) > 0)
        best = max(closed, key=_pnl)
        worst = min(closed, key=_pnl)

        def _fmt(t: dict) -> str:
            return (
                f"{t.get('action')} @ {_ser_scalar(t.get('price'))} on {t.get('t')} "
                f"(P&L {_pnl(t):+.2f} pts / {_pnl_pct(t):+.2f}% on a 100 capital base)"
            )

        summary += (
            f"; {len(closed)} closed round-trips, {wins} winners; "
            f"total realized P&L {total:+.2f} pts (points on a 100 capital base, i.e. dollars per $100); "
            f"biggest winner: {_fmt(best)}; biggest loser: {_fmt(worst)}"
        )
        return summary

    # No closed round-trips (e.g. a single still-open position) -> rank by size.
    def _mag(t: dict) -> float:
        try:
            return abs(float(t.get("toPos", 0)) - float(t.get("fromPos", 0)))
        except (TypeError, ValueError):
            return 0.0

    notable = sorted(trades, key=_mag, reverse=True)[:5]
    rows = ", ".join(
        f"{t.get('action')} @ {_ser_scalar(t.get('price'))} on {t.get('t')} "
        f"(pos {_ser_scalar(t.get('fromPos'))}→{_ser_scalar(t.get('toPos'))})"
        for t in notable
    )
    return f"{summary}; no closed round-trips yet; notable by size: {rows}"


def _ser_backtest(data: dict) -> str:
    parts: List[str] = []
    head = []
    if data.get("symbol"):
        head.append(f"symbol={data['symbol']}")
    if data.get("strategy"):
        head.append(f"strategy={data['strategy']}")
    if head:
        parts.append(", ".join(head))
    stats = data.get("stats")
    if isinstance(stats, dict) and stats:
        parts.append("stats: " + _ser_dict(stats))
    curve = data.get("curve") or []
    if curve:
        c = _ser_curve(curve)
        if c:
            parts.append(c)
    dd = data.get("drawdown") or []
    if dd:
        try:
            worst = min(
                dd,
                key=lambda x: x.get("dd", 0.0) if isinstance(x.get("dd"), (int, float)) else 0.0,
            )
            parts.append(f"worst drawdown {_ser_scalar(worst.get('dd'))}% on {worst.get('t')}")
        except (TypeError, ValueError):
            pass
    parts.append(_ser_trades(data.get("tradeLog") or []))
    return "; ".join(p for p in parts if p)


def _ser_signal_portfolio(data: dict) -> str:
    parts: List[str] = []
    head = []
    if data.get("label"):
        head.append(f"signal={data['label']}")
    if data.get("schemeLabel"):
        head.append(f"scheme={data['schemeLabel']}")
    if head:
        parts.append(", ".join(head))
    lc, sc = data.get("longCount"), data.get("shortCount")
    if lc is not None:
        parts.append(f"book: {lc} long / {sc or 0} short, gross {_ser_scalar(data.get('gross'))}x, net {_ser_scalar(data.get('net'))}")
    stats = data.get("stats")
    if isinstance(stats, dict) and stats:
        parts.append("stats: " + _ser_dict(stats))
    bench = data.get("benchStats")
    if isinstance(bench, dict) and bench:
        parts.append(f"equal-weight benchmark return {_ser_scalar(bench.get('totalReturn'))}%")
    curve = data.get("curve") or []
    if curve:
        c = _ser_curve(curve)
        if c:
            parts.append(c)
    holdings = data.get("holdings") or []
    longs = [h for h in holdings if h.get("side") == "long"][:6]
    if longs:
        parts.append("top longs: " + ", ".join(f"{h.get('symbol')} {_ser_scalar(round(h.get('weight', 0.0) * 100, 1))}%" for h in longs))
    if data.get("turnoverAnnual") is not None:
        parts.append(f"annual turnover {_ser_scalar(data.get('turnoverAnnual'))}%")
    cov = []
    if data.get("included") is not None:
        cov.append(f"{data['included']}/{data.get('universeSize')} included")
    if data.get("excluded"):
        cov.append(f"{data['excluded']} excluded (never imputed)")
    if cov:
        parts.append(", ".join(cov))
    return "; ".join(p for p in parts if p)


def _ser_combined_alpha(data: dict) -> str:
    parts: List[str] = []
    head = []
    if data.get("methodLabel"):
        head.append(f"method={data['methodLabel']}")
    weights = data.get("weights") or []
    if weights:
        head.append("weights: " + ", ".join(f"{w.get('label')} {_ser_scalar(round((w.get('weight') or 0.0) * 100, 1))}%" for w in weights))
    if head:
        parts.append("; ".join(head))
    comp = data.get("composite") or {}
    ic = comp.get("ic") or {}
    if ic:
        parts.append(f"composite rank IC mean {_ser_scalar(ic.get('mean'))}, IC IR {_ser_scalar(ic.get('ir'))}, hit rate {_ser_scalar(ic.get('hitRate'))}%")
    sstats = comp.get("spreadStats") or {}
    if sstats:
        parts.append(f"composite long-short spread return {_ser_scalar(sstats.get('totalReturn'))}%, Sharpe {_ser_scalar(sstats.get('sharpe'))}")
    if comp.get("turnover") is not None:
        parts.append(f"composite turnover {_ser_scalar(comp.get('turnover'))}%")
    rows = data.get("rows") or []
    comp_rows = [r for r in rows if not r.get("isComposite")]
    if comp_rows:
        parts.append("components: " + "; ".join(f"{r.get('label')} IC {_ser_scalar(r.get('meanIC'))}/spread {_ser_scalar(r.get('spreadReturn'))}%" for r in comp_rows))
    corr = data.get("correlation") or {}
    matrix = corr.get("matrix") or []
    labels = corr.get("labels") or []
    if len(matrix) >= 2 and len(labels) == len(matrix):
        offs = []
        for a in range(len(matrix)):
            for b in range(a + 1, len(matrix)):
                offs.append(f"{labels[a]}/{labels[b]} {_ser_scalar(matrix[a][b])}")
        if offs:
            parts.append("overlap (rank corr): " + ", ".join(offs))
    cov = []
    if data.get("included") is not None:
        cov.append(f"{data['included']}/{data.get('universeSize')} included")
    if data.get("excluded"):
        cov.append(f"{data['excluded']} excluded (never imputed)")
    if cov:
        parts.append(", ".join(cov))
    return "; ".join(p for p in parts if p)


def _ser_shorting_desk(data: dict) -> str:
    parts: List[str] = []
    if data.get("label"):
        parts.append(f"book={data['label']}")
    lc, sc = data.get("longCount"), data.get("shortCount")
    if lc is not None:
        parts.append(f"{lc} long / {sc or 0} short on ${_ser_scalar(data.get('capital'))} capital")
    margin = data.get("margin") or {}
    if margin:
        parts.append(
            f"gross leverage {_ser_scalar(margin.get('grossLeverage'))}x, "
            f"maint margin ${_ser_scalar(margin.get('maintenanceMargin'))}, "
            f"excess liquidity ${_ser_scalar(margin.get('excessLiquidity'))}"
            + (" — BREACH" if margin.get("breach") else "")
        )
    carry = data.get("carry") or {}
    if carry:
        parts.append(
            f"carry: borrow ${_ser_scalar(carry.get('borrowCostAnnual'))}/yr, "
            f"financing ${_ser_scalar(carry.get('financingCostAnnual'))}, "
            f"rebate ${_ser_scalar(carry.get('cashRebateAnnual'))}, "
            f"net drag {_ser_scalar(carry.get('dragBpsAnnual'))}bps/yr"
        )
    fin = data.get("financing") or {}
    if fin.get("gcRatePct") is not None:
        parts.append(f"GC anchor {_ser_scalar(fin.get('gcRatePct'))}% ({fin.get('source')})")
    shorts = [h for h in (data.get("holdings") or []) if h.get("side") == "short"][:6]
    if shorts:
        parts.append("shorts: " + ", ".join(
            f"{h.get('symbol')} {h.get('tierLabel')} {_ser_scalar(h.get('feeBps'))}bps"
            + ("(no-locate)" if not h.get("shortable") else "")
            for h in shorts))
    if data.get("blocked"):
        parts.append("locate-infeasible: " + ", ".join(data["blocked"]))
    return "; ".join(p for p in parts if p)


def _ser_walk_forward(data: dict) -> str:
    parts: List[str] = []
    head = []
    if data.get("symbol"):
        head.append(f"symbol={data['symbol']}")
    if data.get("strategy"):
        head.append(f"strategy={data['strategy']}")
    if data.get("paramGridSize") is not None:
        head.append(f"{data['paramGridSize']} configs tried")
    if head:
        parts.append(", ".join(head))
    verdict = data.get("verdict") or {}
    if verdict.get("summary"):
        parts.append(f"verdict: {verdict['summary']}")
    is_st = data.get("isStats") or {}
    oos_st = data.get("oosStats") or {}
    if is_st or oos_st:
        parts.append(
            f"in-sample Sharpe {_ser_scalar(is_st.get('sharpe'))} vs "
            f"out-of-sample {_ser_scalar(oos_st.get('sharpe'))} "
            f"({_ser_scalar(data.get('degradationPct'))}% degradation)"
        )
    dsr = data.get("deflatedSharpe") or {}
    if dsr:
        parts.append(
            f"observed Sharpe {_ser_scalar(dsr.get('observed'))}, "
            f"haircut to {_ser_scalar(dsr.get('haircutSharpe'))} "
            f"({_ser_scalar(dsr.get('haircutPct'))}% cut), "
            f"deflated-Sharpe confidence {_ser_scalar(dsr.get('dsr'))}%"
        )
    pbo = data.get("pbo")
    if pbo:
        parts.append(f"PBO {_ser_scalar(pbo.get('pbo'))}% over {pbo.get('nCombos')} CSCV splits")
    folds = data.get("folds") or []
    if folds:
        rows = ", ".join(
            f"fold {f.get('fold')}: IS {_ser_scalar(f.get('isSharpe'))} → OOS {_ser_scalar(f.get('oosSharpe'))} ({f.get('paramLabel')})"
            for f in folds[:6]
        )
        parts.append(f"folds: {rows}")
    cov = data.get("coverage") or {}
    if cov and not cov.get("usable") and cov.get("note"):
        parts.append(f"coverage: {cov['note']}")
    return "; ".join(p for p in parts if p)


def _ser_walk_forward_compare(data: dict) -> str:
    parts: List[str] = []
    head = []
    if data.get("strategy"):
        head.append(f"strategy={data['strategy']}")
    cards = data.get("cards") or []
    if cards:
        head.append(f"{len(cards)} names")
    if head:
        parts.append(", ".join(head))
    agg = data.get("aggregate") or {}
    if agg.get("summary"):
        parts.append(f"aggregate: {agg['summary']}")
    if agg.get("robustnessScore") is not None:
        parts.append(
            f"robustness {_ser_scalar(agg.get('robustnessScore'))}/100, "
            f"{agg.get('judged')} judged / {agg.get('inconclusive')} inconclusive, "
            f"mean OOS Sharpe {_ser_scalar(agg.get('meanOosSharpe'))}, "
            f"mean degradation {_ser_scalar(agg.get('meanDegradationPct'))}%"
        )
    rows = ", ".join(
        f"{c.get('symbol')}: {c.get('verdictLabel')} (OOS Sharpe {_ser_scalar(c.get('oosSharpe'))}, "
        f"{_ser_scalar(c.get('degradationPct'))}% decay)"
        for c in cards[:12]
    )
    if rows:
        parts.append(f"per name: {rows}")
    failed = data.get("failed") or []
    if failed:
        parts.append("could not validate: " + ", ".join(f.get("symbol", "?") for f in failed))
    return "; ".join(p for p in parts if p)


_PANEL_SERIALIZERS = {
    "backtest": _ser_backtest,
    "walk_forward": _ser_walk_forward,
    "walk_forward_compare": _ser_walk_forward_compare,
    "signal_portfolio": _ser_signal_portfolio,
    "combined_alpha": _ser_combined_alpha,
    "shorting_desk": _ser_shorting_desk,
}


def _serialize_panel(panel: dict) -> str:
    """Bounded text summary of a panel's meaningful values for grounded answers."""
    ptype = panel.get("type", "")
    title = panel.get("title", "")
    label = _TYPE_LABELS.get(ptype, ptype)
    header = f"{title} [{ptype}]" if title else f"[{ptype}]"
    if panel.get("status") == "error":
        note = panel.get("note") or "could not be built"
        return f"{header}: ({note})"
    data = panel.get("data")
    if not isinstance(data, dict) or not data:
        return f"{header}: {label} (no detailed data)"
    try:
        body = _PANEL_SERIALIZERS.get(ptype, _ser_generic)(data)
    except Exception:
        body = ""
    if not body:
        body = label
    if len(body) > _SER_MAX_PANEL_CHARS:
        body = body[:_SER_MAX_PANEL_CHARS] + "…"
    extras = []
    if panel.get("asOf"):
        extras.append(f"asOf={panel['asOf']}")
    if panel.get("source"):
        extras.append(f"source={panel['source']}")
    tail = f" ({', '.join(extras)})" if extras else ""
    return f"{header}: {body}{tail}"


def _panels_context(panels: List[dict]) -> str:
    """Join per-panel summaries under a shared total-size budget."""
    blocks: List[str] = []
    total = 0
    for i, p in enumerate(panels):
        s = _serialize_panel(p)
        if blocks and total + len(s) > _SER_MAX_TOTAL_CHARS:
            blocks.append(f"(+{len(panels) - i} more panels omitted to save space)")
            break
        blocks.append(s)
        total += len(s)
    return "\n".join(f"- {b}" for b in blocks)


def _answer_messages(query: str, sid: str, panels: List[dict]) -> List[dict]:
    """Build the chat messages for a Console question (shared by the blocking
    and streaming answer paths)."""
    sys = (
        "You are the analyst assistant inside an agentic market terminal. The user is asking a "
        "question in the side Console rather than requesting a new dashboard, so answer in chat — "
        "do NOT describe building anything. Reply conversationally in plain prose (no markdown "
        "headings), tight and concrete: about 2-5 sentences for a concept question. Bring real "
        "finance/quant knowledge to definitions (e.g. Sortino ratio, Monte Carlo VaR, IV vs HV, "
        "drawdown, beta). "
        "If the user asks about what they are seeing / this dashboard / these panels, ground your "
        "answer in the panels currently on screen (listed below WITH their underlying data): "
        "explain what they collectively show and how they relate. "
        "When the user asks about specific figures — e.g. a backtest's Sharpe, Sortino, CAGR, max "
        "drawdown, win rate, total return, benchmark comparison, the worst-drawdown date, or notable "
        "trades — answer with the EXACT values from the relevant panel's data below. Never invent "
        "panels, figures, or data that are not provided. If a value the user asks about is not in "
        "the panel data, say it isn't shown rather than guessing. If there are no panels on screen "
        "and the user asks about the screen, say the dashboard is empty and invite them to ask for "
        "something to build."
    )
    messages: List[dict] = [{"role": "system", "content": sys}]
    for h in state.get_history(sid)[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
    if panels:
        ctx = _panels_context(panels)
        messages.append({"role": "system", "content": f"Panels currently on screen with their data:\n{ctx}"})
    else:
        messages.append({"role": "system", "content": "There are no panels on screen right now."})
    messages.append({"role": "user", "content": query})
    return messages


def _answer_question_llm(query: str, sid: str, panels: List[dict]) -> str:
    msg = ai.chat(_answer_messages(query, sid, panels))
    return (msg.content or "").strip()


def _answer_question_stream(query: str, sid: str, panels: List[dict]):
    """Yield the answer text in incremental fragments as the model produces it.

    Raises if the AI client/stream is unavailable so the caller can fall back to
    the blocking :func:`_answer_question` path."""
    yield from ai.chat_stream(_answer_messages(query, sid, panels))


def _answer_fallback(panels: List[dict]) -> str:
    if panels:
        labels: List[str] = []
        for p in panels:
            label = _TYPE_LABELS.get(p["type"], p["type"])
            if label not in labels:
                labels.append(label)
        if len(labels) == 1:
            body = labels[0]
        else:
            body = ", ".join(labels[:-1]) + " and " + labels[-1]
        return (
            f"Right now your dashboard shows {body}. I can't write a full explanation at the "
            "moment — try your question again shortly, or ask me to add or change panels."
        )
    return (
        "I can't answer that right now — the assistant is temporarily unavailable. "
        "Please try again in a moment."
    )


# --------------------- context-aware panel relevance ---------------------
# Panel types that are market-wide rather than tied to a single subject; they
# can reasonably stay on screen even when the user switches focus.
_SUBJECT_AGNOSTIC_TYPES = {"macro_dashboard", "yield_curve", "sovereign_compare", "credit_stress",
                          "economic_releases", "series_revisions"}

# Keyword → sovereign region code, used by the heuristic fallback to detect
# multi-country curve comparisons (e.g. "US vs German curve", "UST vs Bund").
_SOVEREIGN_REGION_KEYWORDS = {
    "US": [" us ", " u.s.", "ust", "treasury", "treasuries", "american"],
    "DE": ["german", "germany", "bund", "bunds", " de "],
    "UK": [" uk ", "gilt", "gilts", "british", "britain", "england"],
    "JP": ["japan", "japanese", "jgb", "jgbs"],
}


def _detect_sovereign_regions(q: str) -> list:
    """Detect sovereign region codes mentioned in a query, in order of first
    appearance, deduplicated. Used to route multi-curve comparison requests."""
    padded = f" {q} "
    hits = []
    for code, kws in _SOVEREIGN_REGION_KEYWORDS.items():
        idx = min((padded.find(kw) for kw in kws if kw in padded), default=-1)
        if idx >= 0:
            hits.append((idx, code))
    hits.sort()
    return [code for _, code in hits]

# Words that signal the new prompt builds on what's already shown (a genuine
# follow-up) rather than switching to a brand-new subject.
_CONTINUATION_KEYWORDS = (
    "add", "also", "too", "more", "another", "alongside", "as well",
    "compare", "vs", "versus", "against", "include", "plus",
    "its", "their", "it",
)


def _decide_kept_panels(query: str, sid: str, existing: List[dict]) -> List[dict]:
    """Return the subset of existing panels still relevant to the new query.

    Uses the AI to judge continuation vs. context switch when available, with a
    keyword/subject heuristic as a fallback.
    """
    if not existing:
        return []
    if ai.ai_available():
        try:
            kept_ids = _relevance_llm(query, sid, existing)
            if kept_ids is not None:
                return [p for p in existing if p.get("id") in kept_ids]
        except Exception:
            pass
    return _relevance_heuristic(query, existing)


def _relevance_llm(query: str, sid: str, existing: List[dict]) -> Optional[set]:
    """Ask the model which existing panel ids to keep for the new request.

    Returns a set of ids to keep, or None if the model output is unusable (so the
    caller can fall back to the heuristic). An empty set is a valid answer that
    means "drop everything currently shown".
    """
    brief = [
        {"id": p["id"], "type": p["type"], "title": p.get("title", "")}
        for p in existing
    ]
    sys = (
        "You curate an agentic market terminal dashboard. You are given the panels "
        "currently on screen and a NEW user request. Decide which existing panels still "
        "belong, then return ONLY their ids.\n"
        "- CONTINUATION: if the new request is a follow-up or deeper look at the SAME "
        "subject(s) already shown (e.g. a stock is shown and the user asks for its news, "
        "analysis, supply chain, or to compare it with a peer), KEEP the relevant panels.\n"
        "- CONTEXT SWITCH: if the new request moves to an UNRELATED subject (e.g. the panels "
        "are about Samsung and the user now asks about farming/agriculture, or about a "
        "different company or sector), REMOVE the panels tied to the abandoned subject.\n"
        "- Broad market-wide panels (macro dashboards, yield curves) may stay if still useful.\n"
        'Return JSON: {"keep": [<panel ids to keep>]}. Use only ids from the provided list. '
        "An empty list means keep nothing."
    )
    user = json.dumps({"request": query, "panels": brief})
    msg = ai.chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
    )
    content = (msg.content or "").strip()
    if not content:
        return None
    parsed = json.loads(content)
    keep = parsed.get("keep")
    if not isinstance(keep, list):
        return None
    valid = {p["id"] for p in existing}
    return {k for k in keep if k in valid}


def _panel_subjects(panel: dict) -> dict:
    """Best-effort subjects (symbols + sector) a panel is about, from its title."""
    title = panel.get("title") or ""
    symbols = set(_extract_symbols(title))
    sectors = set()
    sec = repo.resolve_sector(title)
    if sec:
        sectors.add(sec)
    return {"symbols": symbols, "sectors": sectors}


def _dashboard_subjects(panels: List[dict]):
    """Collect the distinct symbols and sectors the kept panels are about.

    Used to ground a dashboard-scoped analyst report / scenario in whatever the
    user currently has on screen, in panel order.
    """
    syms: List[str] = []
    secs: List[str] = []
    seen_s, seen_sec = set(), set()
    for p in panels:
        subj = _panel_subjects(p)
        for s in subj["symbols"]:
            if s not in seen_s:
                seen_s.add(s)
                syms.append(s)
        for sec in subj["sectors"]:
            if sec not in seen_sec:
                seen_sec.add(sec)
                secs.append(sec)
    return syms, secs


def _apply_dashboard_scope(name: str, args: dict, dash_syms: List[str], dash_secs: List[str]) -> None:
    """Fill a dashboard-scoped analyst report / scenario with the kept panels' subjects.

    When the model requests scope='dashboard' (or omits any subject) for an analyst
    report, or omits a subject for a scenario, inject the symbols/sectors currently
    on screen so the builder can aggregate over them instead of guessing.
    """
    if name == "add_analyst_report":
        wants_dash = args.get("scope") == "dashboard" or (
            not args.get("symbol") and not args.get("sector")
        )
        if wants_dash and (dash_syms or dash_secs):
            args["scope"] = "dashboard"
            args.setdefault("symbols", dash_syms)
            args.setdefault("sectors", dash_secs)
    elif name == "add_scenario":
        if (
            not args.get("symbol")
            and not args.get("sector")
            and not args.get("symbols")
            and dash_syms
        ):
            args["symbols"] = dash_syms
    elif name == "add_risk_monitor":
        if not args.get("symbols") and dash_syms:
            args["symbols"] = dash_syms
    elif name == "add_stress_test":
        if not args.get("symbols") and dash_syms:
            args["symbols"] = dash_syms
    elif name == "add_shorting_desk":
        if not any(args.get(k) for k in ("symbols", "longs", "shorts", "weights")) and dash_syms:
            args["symbols"] = dash_syms


def _relevance_heuristic(query: str, existing: List[dict]) -> List[dict]:
    """Fallback relevance judgement when the AI is unavailable.

    Conservative by design: keeps everything unless the prompt clearly introduces
    a new subject (ticker/sector) that doesn't overlap an existing panel.
    """
    q = query.lower()
    # Explicit follow-up phrasing -> treat as continuation, keep everything.
    if any(re.search(r"\b" + re.escape(k) + r"\b", q) for k in _CONTINUATION_KEYWORDS):
        return list(existing)

    new_syms = set(_extract_symbols(query))
    new_sector = repo.resolve_sector(query)
    # No detectable new subject -> assume a follow-up, keep everything.
    if not new_syms and not new_sector:
        return list(existing)

    kept: List[dict] = []
    for p in existing:
        subj = _panel_subjects(p)
        if new_syms & subj["symbols"]:
            kept.append(p)
        elif new_sector and new_sector in subj["sectors"]:
            kept.append(p)
        elif p.get("type") in _SUBJECT_AGNOSTIC_TYPES:
            kept.append(p)
    return kept


def _repack(panels: List[dict]):
    """Flow-pack the given panels from the top-left of the grid, preserving order
    and each panel's width/height. Returns (repacked_panels, cursor) where cursor
    is the live packing position so new panels can continue filling the same row.
    """
    cursor = {"x": 0, "y": 0, "rowH": 0}
    out: List[dict] = []
    for p in panels:
        lay = p.get("layout") or {}
        new_layout = harness.pack_layout(lay.get("w"), lay.get("h"), cursor)
        repacked = dict(p)
        repacked["layout"] = new_layout
        out.append(repacked)
    return out, cursor


# ----------------------------- spoken narration -----------------------------
def _build_narration(query: str, summary: str, panels: List[dict]) -> Tuple[List[dict], bool]:
    """Produce ordered spoken narration segments, each optionally tied to a panel.

    The first segment is a short lead-in (no panel), then one segment per panel
    in layout order so the UI can highlight panels as they are described.

    Returns ``(segments, degraded)`` where ``degraded`` is True when the heuristic
    narrator was used because the AI was slow/unavailable (an AI call that simply
    returns nothing is NOT counted as degraded).
    """
    if ai.ai_available():
        try:
            segs = _narration_llm(query, summary, panels)
            if segs:
                return segs, False
        except Exception:
            return _narration_heuristic(summary, panels), True
        return _narration_heuristic(summary, panels), False
    return _narration_heuristic(summary, panels), True


def _narration_llm(query: str, summary: str, panels: List[dict]) -> List[dict]:
    panel_brief = [
        {"id": p["id"], "type": p["type"], "title": p.get("title", "")}
        for p in panels
    ]
    sys = (
        "You narrate a market terminal out loud for a hands-free user. You are given the "
        "user's request and the panels just assembled. Produce a short spoken walkthrough as "
        "JSON: {\"segments\": [{\"panelId\": <id or null>, \"text\": <one spoken sentence>}]}.\n"
        "- Start with ONE brief lead-in segment with panelId null (e.g. acknowledge the request).\n"
        "- Then ONE segment per panel, in the given order. Put the panel's id in the panelId "
        "field ONLY.\n"
        "- CRITICAL: the `text` is read aloud by a voice. NEVER speak the id, panel type code, "
        "or any technical token. Refer to panels naturally by what they show (e.g. 'the price "
        "chart', 'the fundamentals', 'the latest news') and the tickers/sectors involved.\n"
        "- Keep each sentence short and conversational (suitable for text-to-speech). Do not "
        "invent panels or ids. Only use ids from the provided list."
    )
    user = json.dumps({"request": query, "summary": summary, "panels": panel_brief})
    msg = ai.chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
    )
    content = (msg.content or "").strip()
    if not content:
        return []
    parsed = json.loads(content)
    raw = parsed.get("segments") or []
    valid_ids = {p["id"] for p in panels}
    segs: List[dict] = []
    for s in raw:
        if not isinstance(s, dict):
            continue
        text = (s.get("text") or "").strip()
        if not text:
            continue
        pid = s.get("panelId")
        if pid is not None and pid not in valid_ids:
            pid = None
        segs.append({"text": text, "panelId": pid})
    return segs


def _narration_heuristic(summary: str, panels: List[dict]) -> List[dict]:
    segs: List[dict] = []
    lead = (summary or "Here is your dashboard.").strip()
    segs.append({"text": lead, "panelId": None})
    for p in panels:
        label = _TYPE_LABELS.get(p["type"], p["type"]).lstrip("a ").lstrip("an ")
        title = p.get("title") or label
        segs.append({"text": f"This panel shows {title}.", "panelId": p["id"]})
    return segs


# ----------------------------- navigator tour -----------------------------
def _reading_order(panels: List[dict]) -> List[dict]:
    """Sort panels in visual reading order (top-to-bottom, then left-to-right)."""
    def key(p: dict):
        layout = p.get("layout") or {}
        return (layout.get("y", 0), layout.get("x", 0))
    return sorted(panels, key=key)


def navigate(query: Optional[str], session_id: str) -> dict:
    """Produce an ordered navigator tour over the panels currently on screen.

    The tour references ONLY panels that exist in the session's dashboard, so the
    AI cursor never points at something that isn't rendered. Uses the AI to order
    and caption the stops when available, with a reading-order heuristic fallback.
    """
    panels = state.get_dashboard(session_id)
    if not panels:
        return {"sessionId": session_id, "title": "Navigator", "stops": []}

    q = (query or "").strip()
    if ai.ai_available():
        try:
            tour = _navigate_llm(q, panels)
            if tour and tour.get("stops"):
                return {"sessionId": session_id, **tour}
        except Exception:
            pass
    return {"sessionId": session_id, **_navigate_heuristic(q, panels)}


def _navigate_llm(query: str, panels: List[dict]) -> Optional[dict]:
    """Ask the model to order the on-screen panels into a guided tour with captions."""
    panel_brief = [
        {"id": p["id"], "type": p["type"], "title": p.get("title", "")}
        for p in panels
    ]
    sys = (
        "You are the navigator of an agentic market terminal. An AI cursor will glide across the "
        "screen, stopping on one panel at a time to walk the user through an analysis. You are given "
        "the panels CURRENTLY on screen and the user's request. Plan the tour as JSON: "
        '{"title": <short tour title>, "stops": [{"panelId": <id>, "caption": <one short caption>}]}.\n'
        "- Order the stops so the walkthrough tells a coherent story for the request (lead with the "
        "most important panel, then supporting context).\n"
        "- Include only panels that genuinely matter to the request; you may skip irrelevant ones. "
        "If everything is relevant, include them all.\n"
        "- Each caption is shown on screen next to the cursor: ONE short, plain sentence about what "
        "to look at and why it matters. No markdown, no panel ids, no type codes.\n"
        "- Use ONLY ids from the provided list. Never invent panels or ids."
    )
    user = json.dumps({"request": query or "Walk me through this dashboard", "panels": panel_brief})
    msg = ai.chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
    )
    content = (msg.content or "").strip()
    if not content:
        return None
    parsed = json.loads(content)
    raw = parsed.get("stops") or []
    valid_ids = {p["id"] for p in panels}
    stops: List[dict] = []
    seen: set = set()
    for s in raw:
        if not isinstance(s, dict):
            continue
        pid = s.get("panelId")
        caption = (s.get("caption") or "").strip()
        if pid not in valid_ids or not caption or pid in seen:
            continue
        seen.add(pid)
        stops.append({"panelId": pid, "caption": caption})
    if not stops:
        return None
    title = (parsed.get("title") or "Guided walkthrough").strip() or "Guided walkthrough"
    return {"title": title, "stops": stops}


def _navigate_heuristic(query: str, panels: List[dict]) -> dict:
    """Reading-order tour with templated captions, used when the AI is unavailable."""
    stops: List[dict] = []
    for p in _reading_order(panels):
        label = _TYPE_LABELS.get(p["type"], p["type"]).lstrip("a ").lstrip("an ")
        title = p.get("title") or label
        stops.append({"panelId": p["id"], "caption": f"Here's {title}."})
    title = "Guided walkthrough"
    if query:
        title = f"Walkthrough: {query[:48]}"
    return {"title": title, "stops": stops}


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


def _orchestrate_llm(query: str, sid: str, existing: List[dict], cursor: dict):
    messages = [{"role": "system", "content": _system_prompt()}]
    for h in state.get_history(sid)[-4:]:
        messages.append({"role": h["role"], "content": h["content"]})
    if existing:
        shown = ", ".join(f'{p.get("title")} ({p["type"]})' for p in existing)
        messages.append({"role": "system", "content": (
            "These panels are still on screen because they remain relevant to the new "
            "request: " + shown + ". They have ALREADY been kept; stale panels from any "
            "abandoned subject were removed before you were called. ADD new panels that "
            "answer the request and complement what is kept. Do NOT recreate panels that "
            "are already shown. Your text summary should describe only what you just added."
        )})
    messages.append({"role": "user", "content": query})

    msg = ai.chat(messages, tools=_all_tools(), tool_choice="auto")
    tool_calls = getattr(msg, "tool_calls", None) or []
    dash_syms, dash_secs = _dashboard_subjects(existing)
    panels: List[dict] = []
    for tc in tool_calls:
        name = tc.function.name
        panel_type = _type_of_tool(name)
        if not panel_type:
            continue
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        _apply_dashboard_scope(name, args, dash_syms, dash_secs)
        if name == "add_backtest":
            _coerce_invest_backtest(query, args)
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
    "alerts": "a trade-flow alerts panel",
    "compliance": "a pre-trade compliance panel",
    "tca_report": "a TCA report",
    "macro_dashboard": "a macro dashboard",
    "yield_curve": "a yield curve",
    "sovereign_compare": "a sovereign curve comparison",
    "bond_rv": "bond relative value",
    "cds_pricer": "a CDS pricer",
    "credit_stress": "a credit stress monitor",
    "economic_releases": "an economic releases calendar",
    "series_revisions": "a data revision history",
    "cashflow_duration": "cash flow & duration",
    "portfolio_risk": "a portfolio risk breakdown",
    "backtest": "a backtest",
    "walk_forward": "a walk-forward validation",
    "walk_forward_compare": "a multi-name walk-forward robustness check",
    "monte_carlo": "a Monte Carlo simulation",
    "correlation_matrix": "a correlation matrix",
    "factor_analysis": "a factor analysis",
    "risk_model": "a multi-factor risk model",
    "risk_comparison": "a side-by-side risk comparison",
    "factor_exposures": "a factor exposure panel",
    "performance_pnl": "a P&L panel",
    "brinson_attribution": "a Brinson attribution",
    "factor_attribution": "a factor attribution",
    "factor_performance": "a factor performance panel",
    "tear_sheet": "a performance tear sheet",
    "portfolio_optimizer": "a portfolio optimizer",
    "signal_research": "an alpha signal research panel",
    "signal_scorecard": "an alpha signal scorecard",
    "signal_portfolio": "a signal portfolio",
    "combined_alpha": "a combined alpha blend",
    "shorting_desk": "a shorting desk (borrow cost, financing & margin)",
    "iv_surface": "an IV surface",
    "options_chain": "an options chain",
    "options_screener": "an options screener",
    "options_strategy": "an options strategy",
    "vol_term_structure": "a vol term structure",
    "structured_product": "a structured product pricer",
    "supply_chain": "a supply chain map",
    "dcf_model": "a DCF model",
    "earnings_transcript": "an earnings transcript",
    "earnings_calendar": "an earnings calendar",
    "ma_tracker": "an M&A tracker",
    "company_analytics": "a company analytics panel",
    "company_analytics_compare": "a company comparison",
    "data_universe": "a data universe overview",
    "intraday_chart": "an intraday chart",
    "data_quality": "a data quality report",
    "analyst_report": "an analyst report",
    "analyst_compare": "an analyst comparison",
    "scenario": "a what-if scenario",
    "stress_test": "a stress test",
    "risk_monitor": "a risk monitor",
    "strategy_desk": "the strategy desk",
    "multi_strategy": "the multi-strategy allocation",
    "rebalance_plan": "a cost-aware rebalance plan",
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
_AMBIGUOUS_TICKERS = {"NOW", "COP"}

# Country/nationality words that appear as a company's first name-word but, when
# present in a query, signal a market filter (not a specific-ticker request).
_GEO_NAME_STOPWORDS = {"singapore", "united", "american", "america", "states"}


def _extract_symbols(q: str) -> List[str]:
    up = q.upper()
    # Allow alphanumeric tokens so SGX base codes (e.g. D05, O39, C38U) match,
    # not just pure-alpha US tickers.
    tokens = set(re.findall(r"\b[A-Z0-9]{1,6}\b", up))
    explicit_upper = set(re.findall(r"\b[A-Z0-9]{2,6}\b", q))
    dollar = {d.upper() for d in re.findall(r"\$([A-Za-z0-9]{1,6})", q)}
    found: List[str] = []
    for s in repo.all_symbols():
        if s in tokens or s in dollar:
            if s in _AMBIGUOUS_TICKERS and s not in explicit_upper and s not in dollar:
                continue
            found.append(s)
    if not found:
        low = q.lower()
        for s, c in repo.get_all_companies().items():
            short = c["name"].split()[0].lower()
            # Skip geographic/nationality first-words ("Singapore" Airlines/Post/
            # Exchange, "United" Overseas Bank): a country/market word in the query
            # is a filter, not a ticker request, and matches several names at once.
            if short in _GEO_NAME_STOPWORDS:
                continue
            if len(short) > 3 and re.search(r"\b" + re.escape(short) + r"\b", low):
                found.append(s)
    return found


_ETF_TOKEN_RE = re.compile(r"\b[A-Z]{2,5}\b")
# Short all-caps tokens that are English words, not ETF tickers — keeps the
# fallback extractor from mistaking "of"/"top" etc. for a ticker.
_ETF_STOPWORDS = {
    "OF", "IN", "ON", "IS", "IT", "BE", "TO", "DO", "GO", "AT", "BY", "AS", "OR",
    "AN", "IF", "SO", "UP", "MY", "ME", "WE", "US", "THE", "AND", "FOR", "ETF",
    "ETFS", "FUND", "TOP", "ALL", "ITS", "NOW", "OWN", "OWNS", "OWNED", "HOLD",
    "HOLDS", "WHAT", "WHATS", "HELD", "HAVE", "HAS", "ARE", "WHO", "HOW", "WHY",
    "NEW", "OLD", "BIG", "LOW", "HIGH", "BOND", "CASH", "LIST", "SHOW", "GIVE",
    "WHICH", "FUNDS", "INDEX", "STOCK", "SHARE",
}


def _extract_etf(q: str) -> Optional[str]:
    """Best-effort ETF ticker from a holdings query.

    Prefers a recognised benchmark/sector ETF; otherwise falls back to a
    standalone ticker-looking token (skipping common English words). Returns the
    upper-cased ticker, or None when nothing plausible is present.
    """
    known = set(skills._BENCHMARK_ETFS.keys())
    toks = _ETF_TOKEN_RE.findall(q.upper())
    dollar = {d.upper() for d in re.findall(r"\$([A-Za-z]{2,5})", q)}
    for t in toks:
        if t in known:
            return t
    for t in toks:
        if t in dollar:
            return t
    for t in toks:
        if t not in _ETF_STOPWORDS:
            return t
    return None


def _order_symbols_by_query(q: str, symbols: List[str]) -> List[str]:
    """Order matched symbols by where they (or their company name) first appear in the query."""
    up = q.upper()
    low = q.lower()

    def pos(s: str) -> int:
        i = up.find(s)
        if i >= 0:
            return i
        c = repo.get_company(s)
        if c:
            short = c["name"].split()[0].lower()
            j = low.find(short)
            if j >= 0:
                return 1000 + j
        return 10_000

    return sorted(symbols, key=pos)


def _extract_range(q: str) -> Optional[str]:
    """Map a free-text window to a supported range token, or None for default."""
    ql = q.lower()
    if "ytd" in ql or "year to date" in ql or "year-to-date" in ql:
        return "YTD"
    if "1 year" in ql or "one year" in ql or "1y" in ql or "12 month" in ql or "12-month" in ql:
        return "1Y"
    if "6 month" in ql or "6-month" in ql or "6mo" in ql or "6m" in ql or "half year" in ql:
        return "6M"
    if "3 month" in ql or "3-month" in ql or "3mo" in ql or "3m" in ql or "quarter" in ql:
        return "3M"
    if "1 month" in ql or "one month" in ql or "1mo" in ql or "1m" in ql:
        return "1M"
    return None


# Sector/thematic ETF tickers we recognize as benchmarks (also accepted by
# skills._resolve_benchmark, which validates any picked ticker against real data).
_BENCH_SECTOR_TICKERS = (
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLC", "XLB", "XLRE", "XLU",
    "SMH", "SOXX", "CIBR", "XBI", "ITA", "ICLN", "ARKK", "IYT", "KIE", "XME",
    "EFA", "EEM", "AGG", "RSP", "MDY",
)
# Free-text sector phrases → the real sector ETF a user likely means.
_BENCH_SECTOR_PHRASES = (
    ("semiconductor", "SMH"), ("chip sector", "SMH"),
    ("tech sector", "XLK"), ("technology sector", "XLK"),
    ("energy sector", "XLE"), ("financial sector", "XLF"),
    ("financials sector", "XLF"), ("bank sector", "XLF"),
    ("health care sector", "XLV"), ("healthcare sector", "XLV"),
    ("biotech", "XBI"), ("utilities sector", "XLU"), ("utility sector", "XLU"),
    ("real estate sector", "XLRE"), ("materials sector", "XLB"),
    ("industrials sector", "XLI"), ("industrial sector", "XLI"),
    ("staples sector", "XLP"), ("discretionary sector", "XLY"),
    ("communication sector", "XLC"), ("cybersecurity", "CIBR"),
    ("defense sector", "ITA"), ("aerospace", "ITA"), ("clean energy", "ICLN"),
    ("emerging market", "EEM"), ("developed market", "EFA"),
    ("aggregate bond", "AGG"), ("bond index", "AGG"),
)


def _extract_benchmark(q: str) -> Optional[str]:
    """Map free-text to a real benchmark ETF ticker, or None for the default."""
    ql = q.lower()
    if "nasdaq" in ql or "qqq" in ql:
        return "QQQ"
    if "russell" in ql or "iwm" in ql or "small cap" in ql or "small-cap" in ql:
        return "IWM"
    if "dow" in ql or "dia" in ql:
        return "DIA"
    if "equal weight" in ql or "equal-weight" in ql or " rsp" in ql:
        return "RSP"
    if "total market" in ql or " vti" in ql:
        return "VTI"
    if "voo" in ql:
        return "VOO"
    # Explicit sector ETF tickers.
    for t in _BENCH_SECTOR_TICKERS:
        if re.search(rf"\b{t}\b", q.upper()):
            return t
    # Free-text sector phrases.
    for phrase, t in _BENCH_SECTOR_PHRASES:
        if phrase in ql:
            return t
    if "s&p" in ql or "sp500" in ql or "s and p" in ql or " spy" in ql or "500" in ql:
        return "SPY"
    return None


# Phrases that introduce an explicit custom benchmark basket of tickers, e.g.
# "vs a basket of AAPL, MSFT, NVDA" or "benchmark against a portfolio of ...".
_BENCH_BASKET_RE = re.compile(
    r"(?:basket|portfolio|index|group|set)\s+of\s+(.+)$", re.IGNORECASE
)


def _extract_benchmark_constituents(q: str) -> List[str]:
    """Parse an explicit custom benchmark basket like 'vs a basket of A, B, C'.

    Returns the real universe tickers named after the basket cue (empty when no
    basket phrasing is present). Only triggers when the basket clearly belongs to
    a benchmark/comparison context to avoid hijacking the book holdings.
    """
    ql = q.lower()
    cue = any(
        k in ql
        for k in ("benchmark", "compare", "vs ", "vs.", "versus", "against", "relative to")
    )
    if not cue:
        return []
    m = _BENCH_BASKET_RE.search(q)
    if not m:
        return []
    return _extract_symbols(m.group(1))


def _extract_expiry(q: str) -> Optional[str]:
    """Map free-text to an options-chain expiry label (1W..1Y), or None for default."""
    ql = q.lower()
    for tok, label in [
        ("1 week", "1W"), ("one week", "1W"), ("weekly", "1W"), ("1w", "1W"),
        ("2 week", "2W"), ("two week", "2W"), ("2w", "2W"),
        ("1 year", "1Y"), ("one year", "1Y"), ("12 month", "1Y"), ("1y", "1Y"),
        ("6 month", "6M"), ("6mo", "6M"), ("6m", "6M"), ("half year", "6M"),
        ("3 month", "3M"), ("3mo", "3M"), ("3m", "3M"), ("quarter", "3M"),
        ("2 month", "2M"), ("2mo", "2M"), ("2m", "2M"),
        ("1 month", "1M"), ("one month", "1M"), ("1mo", "1M"), ("1m", "1M"), ("30 day", "1M"),
    ]:
        if tok in ql:
            return label
    return None


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


def _news_topic(query: str) -> str:
    """Reduce a free-text news prompt to its topical keywords (empty if none)."""
    return " ".join(repo.news_keywords(query))


_MONEY_RE = re.compile(
    r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k|thousand|m|mm|mn|million|b|bn|billion)?",
    re.IGNORECASE,
)
_MONEY_MULT = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
}
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _parse_invest_entry(query: str) -> dict:
    """Pull a dollar amount + entry spec out of a free-text invest/backtest prompt.

    Returns a dict with any of {amount, entry, date, start, end} that were found.
    Handles "$1M", "1 million", "500k"; "at its peak" / "all-time high"; an ISO
    date ("on 2023-01-03"); and a date range ("from 2022-01-01 to 2023-01-01").
    Money is only taken when paired with a $ sign or a magnitude word so plain
    counts (e.g. "50 day momentum") aren't misread as dollars.
    """
    out: dict = {}
    q = query or ""
    ql = q.lower()

    # Dollar amount — require a $ or a magnitude suffix to avoid false positives.
    best: Optional[float] = None
    for m in _MONEY_RE.finditer(q):
        num_s, suffix = m.group(1), (m.group(2) or "").lower()
        has_dollar = m.group(0).lstrip().startswith("$")
        if not suffix and not has_dollar:
            continue
        try:
            val = float(num_s.replace(",", ""))
        except ValueError:
            continue
        val *= _MONEY_MULT.get(suffix, 1.0)
        if val > 0 and (best is None or val > best):
            best = val
    if best is not None:
        out["amount"] = best

    # Entry: explicit date range > single date > peak.
    dates = _DATE_RE.findall(q)
    if ("from" in ql or "between" in ql) and len(dates) >= 2:
        out["entry"] = "range"
        out["start"], out["end"] = dates[0], dates[1]
    elif dates:
        out["entry"] = "date"
        out["date"] = dates[0]
    elif any(k in ql for k in ("at its peak", "at peak", "all-time high", "all time high",
                                "record high", "the peak", "its high", "the top")):
        out["entry"] = "peak"

    return out


def _coerce_invest_backtest(query: str, args: dict) -> None:
    """Normalise an LLM ``add_backtest`` call for plain invest-style questions.

    The LLM tends to default to ``momentum`` even when the user just asks how much
    a lump sum would be worth ("invest $1M in NVDA at its peak, what's it worth
    now?"). That sits in cash and returns the principal unchanged. When the prompt
    is clearly a buy-and-hold dollar question and names no systematic strategy, we
    backfill the parsed amount/entry and force ``buy_and_hold`` so the panel shows
    the asset's real dollar trajectory. We never override an explicitly requested
    strategy.
    """
    ql = (query or "").lower()
    parsed = _parse_invest_entry(query)
    # Backfill amount/entry the model may have dropped.
    for k in ("amount", "entry", "date", "start", "end"):
        if k in parsed and not args.get(k):
            args[k] = parsed[k]
    has_amount = bool(args.get("amount") or parsed.get("amount"))
    explicit_strategy = any(
        kw in ql for kw in ("momentum", "trend", "mean reversion", "mean-reversion",
                            "reversion", "buy and hold", "buy-and-hold")
    )
    invest_phrasing = any(
        k in ql for k in (
            "invest", "worth now", "worth today", "worth right now",
            "if i bought", "if i had bought", "if i'd bought", "had i bought",
            "put $", "bought $", "what's it worth", "what is it worth",
            "what it's worth", "what it is worth", "would it be worth",
        )
    )
    if has_amount and invest_phrasing and not explicit_strategy:
        args["strategy"] = "buy_and_hold"


def _orchestrate_heuristic(query: str, cursor: Optional[dict] = None,
                           dash_syms: Optional[List[str]] = None,
                           dash_secs: Optional[List[str]] = None):
    q = query.lower()
    if cursor is None:
        cursor = {"x": 0, "y": 0, "rowH": 0}
    dash_syms = dash_syms or []
    dash_secs = dash_secs or []
    panels: List[dict] = []

    def add(panel_type, params, w, h, title=None):
        layout = harness.pack_layout(w, h, cursor)
        panels.append(harness.run_skill(panel_type, params, layout, title=title))

    symbols = _extract_symbols(query)
    sector = repo.resolve_sector(query)
    market = repo.resolve_market(query)

    def _market_params(extra: dict) -> dict:
        """Merge the detected country/exchange filter into screener/heatmap params."""
        p = dict(extra)
        if market:
            if market.get("country"):
                p["country"] = market["country"]
            if market.get("exchange"):
                p["exchange"] = market["exchange"]
        return p

    # AI-generated (dynamic) skills get first crack when their invoke phrases match,
    # so a feature works in the keyword fallback even when the LLM is unavailable.
    for d in dynamic_skills.get_definitions():
        phrases = d.get("invoke_phrases") or [d["panel_type"].replace("_", " ")]
        if any(str(p).lower() in q for p in phrases):
            params: dict = {}
            prop_names = set((d.get("parameters") or {}).keys())
            if symbols and ({"symbol", "ticker"} & prop_names):
                params["symbol" if "symbol" in prop_names else "ticker"] = symbols[0]
            add(d["panel_type"], params, 12, 5)
            return panels, f"Added the {d['name']} panel."

    # Cross-symbol options screen/scan. Detected EARLY (before compliance/trade_flow/
    # equity-screener) so words like "watchlist" or "unusual" don't divert a clear
    # options screen, and before the single-symbol chain/strategy intents below.
    wants_opt_screen = (
        any(k in q for k in ["options screen", "option screen", "options screener",
                             "option screener", "screen options", "screen for options",
                             "scan options", "scan for options", "options scan",
                             "unusual options", "unusual option"])
        or (any(k in q for k in ["option", "options", "calls", "puts"])
            and any(k in q for k in ["screen", "scan", "find", "search for", "look for",
                                     "across", "universe", "watchlist", "which names",
                                     "cheapest", "highest iv", "high iv", "widest skew"]))
    )
    if wants_opt_screen:
        sp: dict = {}
        if sector:
            sp["sector"] = sector
        elif market:
            if market.get("country"):
                sp["country"] = market["country"]
            if market.get("exchange"):
                sp["exchange"] = market["exchange"]
        if "put" in q and "call" not in q:
            sp["option_type"] = "put"
        elif "call" in q and "put" not in q:
            sp["option_type"] = "call"
        if "cheap" in q:
            sp["rank_by"] = "cheap"
        elif "skew" in q:
            sp["rank_by"] = "skew"
        elif "volume" in q or "unusual" in q or "active" in q:
            sp["rank_by"] = "volume"
        elif "open interest" in q:
            sp["rank_by"] = "oi"
        m = re.search(r"(\d+)\s*day", q)
        if m:
            sp["dte_max"] = float(m.group(1))
        add("options_screener", sp, 12, 6)
        scope_label = repo.sector_name(sector) if sector else "your watchlist"
        return panels, f"Options screener across {scope_label} — contracts ranked by your filters with per-row provenance."

    wants_compare = any(k in q for k in ["compare", "vs", "versus", "against"]) or len(symbols) >= 2
    wants_news = "news" in q or "headline" in q or "happening" in q
    wants_sentiment = any(k in q for k in ["sentiment", "buzz", "mood", "social"])
    wants_overview = any(k in q for k in ["overview", "moving", "market", "movers", "heatmap", "today"])
    wants_screen = any(k in q for k in ["screen", "screener", "scan", "list", "top "])
    # Short tokens (bid/ask/l2) need word boundaries — otherwise "ask" matches
    # "basket", hijacking custom-benchmark-basket queries into the order book.
    wants_order_book = (
        any(k in q for k in ["order book", "orderbook", "depth", "level 2"])
        or bool(re.search(r"\b(bid|ask|l2)\b", q))
    )
    wants_trade_flow = any(k in q for k in ["unusual", "block", "sweep", "dark pool", "flow", "activity"])
    wants_alerts = any(k in q for k in ["alert", "notify", "notification", "watch for", "set up alert", "alert rule"])
    wants_compliance = any(k in q for k in [
        "compliance", "restricted list", "restricted name", "restrict ", "watch list",
        "watchlist", "risk limit", "position limit", "exposure limit", "leverage limit",
        "concentration limit", "kill switch", "kill-switch", "halt trading", "halt all",
        "pre-trade", "pretrade", "is this trade allowed", "trade allowed", "can i trade",
        "allowed to trade", "compliance audit", "audit trail", "audit log",
    ])
    wants_tca = any(k in q for k in ["tca", "transaction cost", "slippage", "vwap", "twap", "pov",
                                     "execution", "impl", "market impact", "participation rate",
                                     "execution cost", "cost to trade", "trade into"])
    wants_macro = any(k in q for k in [
        "macro", "cross-asset", "cross asset", "global dashboard", "risk-on", "risk-off",
        "risk on", "risk off", "roro", "rates fx", "inflation dashboard", "china macro",
        "global risk", "mosaic",
    ])
    sovereign_regions = _detect_sovereign_regions(q)
    wants_sovereign_compare = (
        any(k in q for k in ["sovereign", "cross-currency curve", "cross currency curve",
                             "cross-country curve", "curve spread", "curve comparison",
                             "compare curves", "compare sovereign"])
        or (any(k in q for k in ["compare", "vs", "versus", "against", "overlay",
                                 "spread between", " v "]) and len(sovereign_regions) >= 2)
    )
    wants_yield_curve = any(k in q for k in ["yield curve", "treasury curve", "rates curve", "rate curve", "interest rate", "treasury yield", "yield spread", "2s10s", "inversion"])
    wants_bond_rv = any(k in q for k in ["bond rv", "bond relative value", "z-spread", "z spread", "oas", "asset swap", "asset-swap", "corporate bond", "credit spread"])
    wants_cds = any(k in q for k in ["cds", "credit default swap", "credit risk", "default swap", "survival prob"])
    wants_credit_stress = any(k in q for k in [
        "credit stress", "credit-stress", "credit condition", "credit market", "credit monitor",
        "credit spreads", "spread widening", "spreads widening", "credit widening",
        "widening credit", "ig vs hy", "hy vs ig", "ig/hy", "hy/ig", "high yield",
        "high-yield", "investment grade", "investment-grade", "risk-off credit", "risk on credit",
    ])
    wants_cashflow = any(k in q for k in ["cash flow", "cashflow", "duration", "convexity", "dv01", "rate sensitivity", "bond cash", "modified duration"])
    wants_revisions = any(k in q for k in [
        "revision history", "data revision", "data revisions", "revisions", "revised",
        "vintage", "vintages", "alfred", "initial print", "initial estimate",
        "first print", "first estimate", "initial vs revised", "as first reported",
        "fred series", "pull fred", "fred id",
    ])
    wants_econ_releases = any(k in q for k in [
        "economic calendar", "economic releases", "economic release", "data releases",
        "data calendar", "release calendar", "release schedule", "economic data",
        "macro releases", "macro calendar", "release dates", "when is cpi",
        "when does cpi", "when is the jobs report", "next cpi", "next gdp",
        "next jobs report", "next payrolls", "upcoming releases", "upcoming data",
    ])
    wants_risk = any(k in q for k in ["risk", "var", "value at risk", "tracking error", "factor exposure", "portfolio risk"])
    wants_riskmodel = any(k in q for k in ["risk model", "risk decomp", "decompose risk", "factor vs specific", "specific risk", "mctr", "marginal contribution", "where is my risk", "risk contribution", "factor risk"])
    wants_stresstest = any(k in q for k in [
        "stress test", "stress-test", "stresstest", "stress my book", "stress the book",
        "stress my portfolio", "crash test", "crash-test", "scenario analysis", "scenario p&l",
        "scenario pnl", "scenario impact", "covid crash", "covid scenario", "2008 crash",
        "2008 gfc", "gfc", "global financial crisis", "rate shock", "rates shock", "+200bps",
        "200bps rate", "oil shock", "oil spike", "oil +50",
        "how would my portfolio do", "how would my book do", "how would my portfolio perform",
    ])
    wants_riskmonitor = any(k in q for k in [
        "risk monitor", "risk management", "manage my risk", "manage risk", "monitor my risk",
        "monitor risk", "risk dashboard", "risk desk", "risk limit", "limit breach", "breach",
        "within limits", "within my limits", "in limit", "limits framework", "exposure limit",
        "gross exposure", "net exposure", "check my exposure", "check exposures", "my exposures",
        "stress my book", "stress the book", "stress test my", "monitor my book", "risk report",
        "how much could i lose", "how much can i lose", "downside risk", "crisis scenario",
        "replay 2008", "replay 2020", "if markets crash", "market crash",
    ])
    wants_factor_exposures = any(k in q for k in ["factor exposure", "factor tilt", "style exposure", "style tilt", "factor loading", "factor premia", "positioned across factors"])
    wants_riskcompare = any(k in q for k in [
        "compare risk", "risk comparison", "compare the risk", "side by side", "side-by-side",
        "riskier than", "better diversified", "more diversified", "which is riskier",
    ]) or (any(k in q for k in [" vs ", "versus", "against"]) and any(k in q for k in ["risk", "diversif", "volatility", "vol "]))
    wants_optimizer = any(k in q for k in [
        "optimize", "optimise", "optimal portfolio", "optimal weight", "construct a portfolio",
        "build a portfolio", "build me a portfolio", "rebalance", "max sharpe", "max-sharpe",
        "maximum sharpe", "minimum variance", "min variance", "min-variance", "risk parity",
        "risk-parity", "black-litterman", "black litterman", "hierarchical risk", "hrp",
        "target vol", "target-vol", "mean-variance", "mean variance", "allocate capital",
        "how should i allocate", "asset allocation", "position sizing", "size my positions",
        "efficient frontier", "tangency portfolio",
    ])
    wants_desk = any(k in q for k in [
        "strategy desk", "the desk", "show the desk", "my strategies", "strategy lifecycle",
        "paper book", "paper-book", "strategy registry", "strategy roster", "live book",
        "strategy book", "the book",
    ])
    _invest_parsed = _parse_invest_entry(query)
    # A plain "invest $X in <ticker> ... what's it worth now" is a buy-and-hold
    # dollar question, not a systematic-strategy backtest. Detect it explicitly so
    # it is handled deterministically (and denominated in dollars) rather than
    # falling through to the LLM, which tends to pick momentum and sit in cash.
    wants_invest = bool(_invest_parsed.get("amount")) and any(
        k in q for k in [
            "invest", "worth now", "worth today", "worth right now",
            "if i bought", "if i had bought", "if i'd bought", "had i bought",
            "put $", "bought $", "what's it worth", "what is it worth",
            "what it's worth", "what it is worth", "would it be worth",
        ]
    )
    # Firm-level view OVER MANY strategies (sleeves): allocate capital across them
    # and budget firm risk. Must be detected before wants_desk (it mentions
    # "strategies") and before wants_optimizer (it catches "allocate capital").
    _sleeve_words = any(k in q for k in ["sleeve", "sleeves"])
    _firm_words = any(k in q for k in [
        "firm-level", "firm level", "firm-wide", "firm wide", "firmwide", "multi-strategy",
        "multi strategy", "multistrategy", "portfolio of strategies", "across strategies",
        "across my strategies", "across all strategies", "between strategies", "between my strategies",
        "risk budget across", "combined book", "combined nav",
    ])
    _alloc_across_strats = (
        any(k in q for k in ["allocate", "allocation", "split capital", "split the capital",
                             "divide capital", "capital across", "capital between", "risk budget",
                             "risk-budget", "risk parity across", "risk-parity across"])
        and any(k in q for k in ["strateg", "sleeve"])
    )
    wants_multistrat = _sleeve_words or _firm_words or _alloc_across_strats
    wants_shorting = any(k in q for k in [
        "borrow cost", "borrow fee", "cost to short", "cost of shorting", "cost of being short",
        "shorting cost", "short cost", "carry cost", "carrying cost", "hard to borrow",
        "hard-to-borrow", "htb", "locate", "can i short", "can i even short",
        "stock loan", "stock-loan", "financing cost", "financing rate", "short rebate",
        "margin requirement", "maintenance margin", "reg-t", "reg t", "over-levered",
        "over levered", "shorting desk", "short book cost",
    ]) or (
        any(k in q for k in ["margin", "leverage"]) and any(k in q for k in ["short", "book", "borrow"])
    )
    wants_walkforward = any(k in q for k in [
        "overfit", "over-fit", "over fit", "walk forward", "walk-forward", "walkforward",
        "out of sample", "out-of-sample", "oos", "in-sample", "in sample",
        "deflated sharpe", "pbo", "probability of backtest overfitting",
        "backtest overfitting", "multiple testing", "multiple-testing", "data mined",
        "data-mined", "data mining", "research integrity", "is this robust",
        "is it robust", "robustness check", "robust across", "robust over",
        "hold up across", "holds up across", "cross-validation", "cross validation",
    ])
    wants_backtest = wants_invest or any(k in q for k in ["backtest", "back test", "back-test", "momentum strategy", "strategy", "sharpe", "cagr", "drawdown"])
    wants_montecarlo = any(k in q for k in ["monte carlo", "montecarlo", "monte-carlo", "simulate", "simulation", "forward project", "project price", "scenario analysis", "probability of loss", "forecast price", "gbm", "geometric brownian", "bootstrap"])
    wants_correlation = any(k in q for k in ["correlation", "correlat", "hedge ratio", "co-movement", "diversif", "beta table"])
    wants_tearsheet = any(k in q for k in ["tear sheet", "tearsheet", "tear-sheet", "performance review", "performance breakdown", "full performance"])
    wants_brinson = any(k in q for k in ["brinson", "allocation effect", "selection effect", "allocation vs selection", "performance attribution", "attribution analysis"])
    wants_factor_attr = any(k in q for k in ["factor attribution", "factor contribution", "factors drove", "return from factors", "factor return attribution"])
    wants_factor_perf = any(k in q for k in [
        "factor performance", "factors performed", "factor returns over time", "factors over time",
        "factors are paying off", "factors paying off", "which factors pay", "factors paid off",
        "factors being rewarded", "factors rewarded", "cumulative factor", "factor pnl",
        "style premia over time", "factor premia over time", "how have factors", "factor premium over time",
        "have factors paid off", "style premium",
    ])
    wants_pnl = any(k in q for k in ["p&l", "pnl", "p and l", "performance vs", "vs benchmark", "book performance", "portfolio performance", "performance of my portfolio", "how has my portfolio", "realized return", "return attribution", "cumulative return"])
    wants_factor = any(k in q for k in ["factor analysis", "factor", "attribution", "alpha", "loading", "momentum factor", "value factor"])
    def _signals_in_query() -> list:
        found = []
        for key, kws in (
            ("momentum", ["momentum", "trend"]),
            ("short_reversal", ["reversal", "mean reversion", "reversion"]),
            ("low_volatility", ["low vol", "low volatility", "volatility"]),
            ("value", ["value", "earnings yield", "cheap"]),
            ("quality", ["quality", "margin", "profitab"]),
        ):
            if any(kw in q for kw in kws) and key not in found:
                found.append(key)
        return found

    _mentions_signal = any(k in q for k in ["signal", "alpha"])
    _signals_found = _signals_in_query()
    _explicit_scorecard = any(k in q for k in [
        "scorecard", "compare signals", "compare signal", "rank signals", "rank the signals",
        "rank alpha", "rank alphas", "rank the alphas", "which signal", "best signal",
        "signal library", "signal comparison", "compare alphas", "signal leaderboard",
    ])
    _compare_words = any(k in q for k in ["compare", "versus", " vs "])
    wants_scorecard = (
        _explicit_scorecard
        or (_compare_words and (len(_signals_found) >= 2 or _mentions_signal))
        or (_mentions_signal and "signal research" not in q
            and any(k in q for k in ["best", "which", "leaderboard", "ranking"]))
    )
    wants_signal = wants_scorecard or "signal research" in q or any(k in q for k in [
        "alpha signal", "rank ic", "information coefficient", " ic ",
        "ic decay", "signal turnover", "quantile spread", "decile spread", "long-short spread",
        "long short spread", "predict returns", "cross-sectional", "cross sectional",
    ]) or (_mentions_signal and len(_signals_found) >= 1)

    # Build a tradeable portfolio FROM a signal. Must be checked before the
    # scorecard/research/backtest routes because they also catch signal mentions.
    _portfolio_build_words = any(k in q for k in [
        "build a portfolio", "build portfolio", "construct a portfolio", "construct portfolio",
        "portfolio from", "build a book", "construct a book", "long-short book", "long short book",
        "into a portfolio", "into a strategy", "into a book", "size positions from",
        "size a portfolio", "tradeable portfolio", "tradable portfolio", "make a portfolio",
        "form a portfolio", "top quantile portfolio", "top-quantile portfolio",
    ])
    wants_portfolio_build = (_mentions_signal or len(_signals_found) >= 1) and (
        _portfolio_build_words
        or ("portfolio" in q and any(k in q for k in ["build", "construct", "from", "make", "form"]))
    )

    # Blend several signals into ONE composite alpha. Checked before the
    # scorecard/research routes (which also catch signal mentions) but after the
    # portfolio build route (so "blend ... into a portfolio" still builds a book).
    _combine_words = any(k in q for k in [
        "combined alpha", "composite alpha", "composite signal", "combine signals",
        "combine the signals", "combine alphas", "blend signals", "blend the signals",
        "blend alphas", "blended alpha", "blended signal", "signal blend", "signal ensemble",
        "ensemble of signals", "blend these signals", "mix signals", "alpha blend",
    ])
    wants_combine = _combine_words or (
        (_mentions_signal or len(_signals_found) >= 2)
        and any(k in q for k in ["combine", "blend", "ensemble", "composite", "mix "])
    )
    _combine_method = (
        "ic_weighted" if any(k in q for k in ["ic-weight", "ic weight", "ic weighted", "ic-weighted", "information coefficient weight"])
        else "inverse_correlation" if any(k in q for k in ["inverse correlation", "inverse-correlation", "risk weight", "risk-weight", "risk parity", "risk-parity", "decorrel", "diversif"])
        else "equal_weight"
    )

    if wants_multistrat:
        mp = {}
        if "equal" in q and ("weight" in q or "split" in q):
            mp["method"] = "equal_weight"
        elif "risk parity" in q or "risk-parity" in q:
            mp["method"] = "risk_parity"
        elif "target" in q and ("risk" in q or "vol" in q):
            mp["method"] = "target_risk"
        add("multi_strategy", mp, 12, 6)
        return panels, ("Firm-level multi-strategy allocation: every paper/live strategy as a sleeve of "
                        "one combined book, with cross-strategy risk and recommended vs current capital weights.")

    if wants_shorting:
        params: dict = {}
        if symbols:
            # A vs/short pivot lets the user name the short side explicitly.
            pivot = next((d for d in [" short ", " shorting ", " against "] if d in q), None)
            if pivot and len(symbols) >= 2:
                params["symbols"] = symbols
            else:
                params["symbols"] = symbols
        elif sector:
            sec_syms = data.symbols_in_sector(sector)[:10]
            if sec_syms:
                params["symbols"] = sec_syms
        m = re.search(r"\$?\s*([\d,]+(?:\.\d+)?)\s*(k|m|mm|million|thousand)?\s*(?:of\s+)?(?:capital|equity|book|nav)", q)
        if m:
            amt = float(m.group(1).replace(",", ""))
            unit = (m.group(2) or "").lower()
            if unit in ("k", "thousand"):
                amt *= 1_000
            elif unit in ("m", "mm", "million"):
                amt *= 1_000_000
            if amt > 0:
                params["capital"] = amt
        add("shorting_desk", params, 12, 6)
        return panels, ("Shorting desk: per-name borrow tier and fee, locate-infeasible names, the "
                        "carrying-cost drag (borrow + financing − rebate) and the Reg-T margin, "
                        "leverage and any breach for the book.")

    if wants_desk:
        add("strategy_desk", {}, 12, 5)
        return panels, "Here's the strategy desk: every strategy across the lifecycle with live P&L."

    if wants_order_book and symbols:
        sym = symbols[0]
        add("order_book", {"symbol": sym}, 6, 5)
        add("price_chart", {"symbol": sym, "range": "1M"}, 6, 4)
        name = data.get_company(sym)["name"]
        return panels, f"{name} order book depth ladder and tape."

    if wants_compliance:
        strat_name = None
        # A "can I trade / is this allowed / pre-check" phrasing resolves a
        # strategy so the panel runs a read-only gate over its prospective book.
        if any(k in q for k in ["allowed", "can i trade", "pre-trade", "pretrade",
                                "pre-check", "precheck", "check"]):
            tgt = _resolve_target_strategy(query, _signal_in_query(q))
            if tgt:
                strat_name = tgt.get("name")
        add("compliance", {"strategy": strat_name} if strat_name else {}, 12, 6)
        if strat_name:
            return panels, (f"Pre-trade compliance check for {strat_name}: firm limits, "
                            "restricted/watch lists and the kill switch.")
        return panels, ("Pre-trade compliance: firm limits, the restricted and watch lists, "
                        "the kill switch and the audit trail of gate decisions.")

    if wants_alerts:
        sym = symbols[0] if symbols else None
        add("alerts", {"symbol": sym} if sym else {}, 6, 5)
        if sym:
            add("trade_flow", {"symbol": sym}, 6, 5)
            name = data.get_company(sym)["name"]
            return panels, f"Trade-flow alerts for {name}: configure thresholds and watch the live flow."
        return panels, "Trade-flow alerts: configure block-size, dark-pool and imbalance thresholds per symbol."

    if wants_trade_flow and symbols:
        sym = symbols[0]
        add("trade_flow", {"symbol": sym}, 8, 5)
        add("price_chart", {"symbol": sym, "range": "1M"}, 4, 4)
        name = data.get_company(sym)["name"]
        return panels, f"{name} trade flow: block prints, dark pool activity and buy/sell imbalance."

    if wants_tca:
        params: dict = {}
        if "sell" in q:
            params["side"] = "sell"
        if len(symbols) >= 2:
            # Treat a multi-name request as a portfolio to trade into equally.
            params["symbols"] = symbols
            params["target_weights"] = [round(1.0 / len(symbols), 4)] * len(symbols)
            add("tca_report", params, 12, 6)
            return panels, (
                f"Execution TCA across {len(symbols)} names: VWAP/TWAP/POV simulated on real "
                "intraday volume, with square-root impact and per-name + aggregate cost in bps."
            )
        sym = symbols[0] if symbols else "NVDA"
        params["symbol"] = sym
        add("tca_report", params, 12, 6)
        name = data.get_company(sym)["name"] if data.get_company(sym) else sym
        side = params.get("side", "buy")
        return panels, (
            f"Execution TCA for a {side} in {name}: VWAP/TWAP/POV simulated on real intraday "
            "volume, with implementation shortfall vs arrival and square-root market impact."
        )

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
    wants_supply_chain = any(k in q for k in ["supply chain", "supplier", "vendor", "customer", "who makes"])
    wants_dcf = any(k in q for k in ["dcf", "valuation", "intrinsic value", "fair value", "discounted cash flow"])
    wants_transcript = any(k in q for k in ["transcript", "earnings call", "what did management", "what did ceo", "call", "said on"])
    wants_calendar = (
        any(k in q for k in [
            "earnings calendar", "earnings date", "earnings schedule", "earnings season",
            "reporting season", "upcoming earnings", "next earnings", "reporting date",
            "report date", "who reports", "reports next",
        ])
        or (("report" in q or "reporting" in q) and any(k in q for k in ["when", "next", "upcoming", "calendar", "date", "schedule"]))
    )
    wants_etf_exposure = (
        any(k in q for k in ["which etf", "which etfs", "what etf", "what etfs", "what funds own",
                             "which funds own", "etf exposure", "funds holding", "etfs holding",
                             "etfs that hold", "funds that hold", "etfs that own", "funds that own",
                             "what funds hold", "which funds hold"])
        or (("etf" in q or "fund" in q) and any(k in q for k in ["hold", "own", "contain", "include"])
            and any(k in q for k in ["which", "what", "list"]))
    )
    wants_etf_holdings = (
        not wants_etf_exposure
        and (
            any(k in q for k in ["etf holding", "etf holdings", "fund holding", "fund holdings",
                                 "holdings of", "what's in", "whats in", "what is in",
                                 "constituents", "constituent", "components of", "top holdings"])
            or (("etf" in q or "fund" in q) and any(k in q for k in ["hold", "holding", "contain",
                                                                     "made up", "composition", "inside"]))
        )
    )
    wants_ma = any(k in q for k in ["m&a", "merger", "acquisition", "deal", "arb spread", "takeover", "buyout"])
    wants_company_analytics = any(k in q for k in [
        "why is", "why is it", "what drives", "price driver", "company analytics",
        "compete", "competition for", "competitors", "analyze", "vs competitor",
    ])
    wants_scenario = any(k in q for k in [
        "what if", "what-if", "if i ", "if rates", "if the", "suppose", "scenario where",
        "stress test", "shock", "hypothetical", "rotate into", "100bps", "bps",
    ]) or bool(re.search(r"\bif\b.+\bthen\b", q))
    wants_analyst_report = any(k in q for k in [
        "analyst take", "analyst report", "analyst view", "deep analysis", "deep-dive analysis",
        "write-up", "writeup", "write up", "bull case", "bear case", "bull/bear", "bull or bear",
        "investment thesis", "thesis on", "should i buy", "should i sell", "your view on",
        "your take on", "make the case",
    ])
    wants_analyst_compare = (
        len(symbols) >= 2
        and (
            wants_analyst_report
            or any(k in q for k in [
                "analyst", "stance", "conviction", "bull/bear", "bull or bear",
                "better buy", "rather own", "best buy", "which to buy",
            ])
        )
    )
    wants_dashboard_review = any(k in q for k in [
        "my dashboard", "this dashboard", "the dashboard", "current dashboard",
        "whole dashboard", "entire dashboard", "everything on screen", "on my screen",
        "these panels", "my portfolio", "my holdings", "what i have up",
    ]) and any(k in q for k in [
        "analy", "review", "report", "take", "thesis", "assess", "summary",
        "summarize", "overview", "opinion", "view",
    ])

    if wants_stresstest:
        st_params: dict = {}
        if symbols:
            st_params["symbols"] = symbols
        elif dash_syms:
            st_params["symbols"] = dash_syms
        add("stress_test", st_params, 12, 6)
        scope = (
            "the symbols you named" if symbols
            else "your dashboard book" if dash_syms
            else "a representative book"
        )
        return panels, (
            f"Stress test for {scope}: scenario P&L across the 2020 COVID, 2022 rate-shock and "
            "2008 GFC crises plus +200bps rate and oil shocks, with per-holding impacts."
        )

    if wants_riskmonitor:
        rm_params: dict = {}
        if symbols:
            rm_params["symbols"] = symbols
        elif dash_syms:
            rm_params["symbols"] = dash_syms
        add("risk_monitor", rm_params, 12, 6)
        scope = (
            "the symbols you named" if symbols
            else "your dashboard book" if dash_syms
            else "a representative book"
        )
        return panels, (
            f"Risk monitor for {scope}: gross/net & factor exposures, limit breaches, "
            "and historical + hypothetical stress."
        )

    if wants_scenario:
        sym = symbols[0] if symbols else None
        sc_params: dict = {"prompt": query}
        if sym:
            sc_params["symbol"] = sym
        elif sector:
            sc_params["sector"] = sector
        elif dash_syms:
            sc_params["symbols"] = dash_syms
        _sc_money = _parse_invest_entry(query).get("amount")
        if _sc_money:
            sc_params["amount"] = _sc_money
        add("scenario", sc_params, 12, 6)
        label = (
            data.get_company(sym)["name"] if sym
            else repo.sector_name(sector) if sector
            else "your dashboard" if dash_syms
            else "a market-proxy basket"
        )
        return panels, f"What-if scenario for {label}: baseline vs scenario projection with reasoning and caveats."

    if wants_analyst_compare:
        add("analyst_compare", {"symbols": symbols}, 12, 5)
        names = ", ".join(symbols)
        return panels, f"Analyst comparison across {names}: stance, conviction and the one-line call side by side."

    if wants_analyst_report or wants_dashboard_review:
        if symbols:
            sym = symbols[0]
            add("analyst_report", {"symbol": sym}, 8, 6)
            add("price_chart", {"symbol": sym, "range": "6M"}, 4, 6)
            name = data.get_company(sym)["name"]
            return panels, f"Analyst report on {name}: thesis, drivers, risks, catalysts, valuation and a clear call."
        if sector:
            add("analyst_report", {"sector": sector}, 12, 6)
            return panels, f"Analyst report on {repo.sector_name(sector)}: thesis, drivers, risks, catalysts and a call."
        if dash_syms or dash_secs:
            add("analyst_report", {"scope": "dashboard", "symbols": dash_syms, "sectors": dash_secs}, 12, 6)
            return panels, "Analyst report across your current dashboard: thesis, drivers, risks, catalysts and a clear call."

    wants_compare = (
        (wants_company_analytics or any(k in q for k in ["compare", " vs ", " vs. ", "versus", "head-to-head", "head to head", "side by side", "side-by-side", "which is better"]))
        and (" vs" in q or "versus" in q or "compare" in q or "head-to-head" in q or "head to head" in q or "side by side" in q or "side-by-side" in q or "which is better" in q)
    )
    if wants_compare and len(symbols) >= 2:
        ordered = _order_symbols_by_query(query, symbols)[:2]
        add("company_analytics_compare", {"symbols": ordered}, 12, 6)
        names = " vs ".join(data.get_company(s)["name"] for s in ordered)
        return panels, f"Head-to-head: {names}. Price drivers, catalysts, and a metric scoreboard for each."

    if wants_company_analytics and symbols:
        sym = symbols[0]
        add("company_analytics", {"symbol": sym}, 8, 6)
        add("price_chart", {"symbol": sym, "range": "3M"}, 4, 6)
        name = data.get_company(sym)["name"]
        return panels, f"Company analytics for {name}: price drivers, competitive landscape, metric correlations, and catalyst watch."

    if wants_etf_exposure:
        sym = symbols[0] if symbols else _extract_etf(query)
        if sym:
            add("etf_exposure", {"symbol": sym}, 12, 6)
            c = data.get_company(sym)
            label = c["name"] if c else sym
            return panels, f"ETFs holding {label}, ranked by the stock's weight in each fund (top holdings of the common ETF set; deeper positions may not appear)."

    if wants_etf_holdings:
        etf = _extract_etf(query) or (symbols[0] if symbols else None)
        if etf:
            add("etf_holdings", {"symbol": etf}, 12, 6)
            label = skills._BENCHMARK_ETFS.get(etf, etf)
            return panels, f"Top holdings of {label} with weights, top-N concentration and the fund's sector breakdown (free feed exposes top holdings only)."

    if wants_ma:
        sym = symbols[0] if symbols else None
        sec = sector
        ma_params = {}
        if sym:
            ma_params["symbol"] = sym
        elif sec:
            ma_params["sector"] = sec
        add("ma_tracker", ma_params, 12, 5)
        return panels, "M&A deal tracker with arb spreads and deal statistics."

    if wants_calendar:
        cal_params: dict = {}
        if symbols:
            cal_params["symbols"] = symbols
        elif sector:
            cal_params["sector"] = sector
        add("earnings_calendar", cal_params, 12, 5)
        scope = (
            ", ".join(symbols[:3]) + ("..." if len(symbols) > 3 else "")
            if symbols else (repo.sector_name(sector) if sector else "your watchlist")
        )
        return panels, f"Upcoming earnings calendar for {scope} with live countdowns; any name reporting within 24 hours is flagged."

    if wants_transcript and symbols:
        sym = symbols[0]
        add("earnings_transcript", {"symbol": sym}, 8, 6)
        add("analysis", {"scope_type": "symbol", "scope": sym}, 4, 6)
        name = data.get_company(sym)["name"]
        return panels, f"Earnings call transcript and AI analysis for {name}."

    if wants_dcf and symbols:
        sym = symbols[0]
        add("dcf_model", {"symbol": sym}, 8, 6)
        add("fundamentals", {"symbol": sym}, 4, 6)
        name = data.get_company(sym)["name"]
        return panels, f"DCF valuation model and fundamentals for {name}."

    if wants_supply_chain and symbols:
        sym = symbols[0]
        add("supply_chain", {"symbol": sym}, 8, 5)
        add("news", {"scope_type": "symbol", "scope": sym}, 4, 5)
        name = data.get_company(sym)["name"]
        return panels, f"Supply chain map and latest news for {name}."

    # --- Fixed income heuristics ---
    if wants_sovereign_compare:
        regions = sovereign_regions[:4]
        if len(regions) < 2:
            regions = ["US", "DE"]
        add("sovereign_compare", {"regions": regions}, 8, 5)
        names = " vs ".join(regions)
        return panels, f"Sovereign curve comparison — {names} overlaid with cross-currency 2Y/10Y/30Y spreads."

    if wants_yield_curve:
        region = "US"
        for r in ["UK", "DE", "JP"]:
            if r.lower() in q:
                region = r
        add("yield_curve", {"region": region}, 8, 5)
        add("news", {"scope_type": "sector", "scope": "energy"}, 4, 5)
        return panels, f"{region} Treasury yield curve with historical overlays and spread analysis."

    if wants_revisions:
        # Map common phrasings to a FRED series id, else pick up an explicit id token.
        rev_aliases = {
            "real gdp": "GDPC1", "gdp": "GDPC1", "payroll": "PAYEMS",
            "nonfarm": "PAYEMS", "jobs": "PAYEMS", "employment": "PAYEMS",
            "unemployment": "UNRATE", "jobless rate": "UNRATE",
            "core pce": "PCEPILFE", "pce": "PCEPI", "core cpi": "CPILFESL",
            "cpi": "CPIAUCSL", "inflation": "CPIAUCSL", "ppi": "PPIACO",
            "retail sales": "RSAFS", "industrial production": "INDPRO",
        }
        series_id = None
        m = re.search(r"\b([A-Z][A-Z0-9]{2,})\b", query)
        if m and m.group(1) not in {"FRED", "GDP", "CPI", "PCE", "PPI"}:
            series_id = m.group(1)
        if not series_id:
            for kw, sid in rev_aliases.items():
                if kw in q:
                    series_id = sid
                    break
        series_id = series_id or "GDPC1"
        add("series_revisions", {"series_id": series_id}, 12, 6)
        return panels, f"Revision history for FRED series {series_id} — current series vs initial print with each vintage."

    if wants_econ_releases:
        add("economic_releases", {}, 12, 6)
        return panels, "Economic releases calendar — recent and upcoming key US data with reported vs prior values (live FRED)."

    if wants_credit_stress:
        add("credit_stress", {}, 8, 5)
        add("yield_curve", {"region": "US"}, 4, 5)
        return panels, "Credit stress monitor — IG vs HY OAS spreads with a risk-on/risk-off read and widening flags."

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

    if wants_optimizer and not wants_portfolio_build:
        params: dict = {}
        if "min variance" in q or "min-variance" in q or "minimum variance" in q:
            params["method"] = "min_variance"
        elif "risk parity" in q or "risk-parity" in q:
            params["method"] = "risk_parity"
        elif "hrp" in q or "hierarchical risk" in q:
            params["method"] = "hrp"
        elif "black-litterman" in q or "black litterman" in q:
            params["method"] = "black_litterman"
        elif "target vol" in q or "target-vol" in q:
            params["method"] = "target_vol"
        else:
            params["method"] = "max_sharpe"
        if any(k in q for k in ["long/short", "long short", "long-short", "market neutral", "market-neutral", "allow short"]):
            params["long_short"] = True
            if "market neutral" in q or "market-neutral" in q:
                params["market_neutral"] = True
        m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:max|cap|position|per name|per-name|maximum)?", q)
        if "max position" in q or "position cap" in q or "max weight" in q or (m and "%" in q):
            if m:
                params["max_position"] = float(m.group(1)) / 100.0
        # Portfolio construction needs breadth: only prefer explicit names when
        # at least two were given (a lone single-letter false positive would
        # otherwise leave nothing to optimize over).
        use_syms = len(symbols) >= 2
        if use_syms:
            params["symbols"] = symbols
        elif sector:
            params["sector"] = sector
        add("portfolio_optimizer", params, 12, 6)
        label = (", ".join(symbols[:3]) + ("..." if len(symbols) > 3 else "")) if use_syms else (
            repo.sector_name(sector) if sector else "the core universe")
        method_label = {
            "max_sharpe": "max-Sharpe", "min_variance": "minimum-variance",
            "target_vol": "target-volatility", "black_litterman": "Black-Litterman",
            "risk_parity": "risk-parity", "hrp": "hierarchical risk parity",
        }[params["method"]]
        return panels, f"Constructed a {method_label} portfolio over {label}: optimal weights, expected return/vol/Sharpe, factor tilts and binding constraints from real data."

    if wants_riskcompare:
        # Split the mentioned tickers into two books around a vs/versus/against
        # pivot when present; otherwise halve the list. Fall back to sensible
        # contrasting defaults so the panel always renders something real.
        ql = q
        pivot = next((d for d in [" versus ", " vs ", " against "] if d in ql), None)
        syms_a: List[str] = []
        syms_b: List[str] = []
        if pivot:
            left, right = ql.split(pivot, 1)
            syms_a = _extract_symbols(left)
            syms_b = _extract_symbols(right)
        if not syms_a or not syms_b:
            if len(symbols) >= 2:
                mid = (len(symbols) + 1) // 2
                syms_a = symbols[:mid]
                syms_b = symbols[mid:]
            else:
                syms_a = syms_a or ["NVDA", "MSFT", "GOOGL", "META", "AMZN"]
                syms_b = syms_b or ["JPM", "XOM", "JNJ", "PG", "WMT"]
        add("risk_comparison", {"symbols_a": syms_a, "symbols_b": syms_b}, 12, 6)
        la = ", ".join(syms_a[:3]) + ("..." if len(syms_a) > 3 else "")
        lb = ", ".join(syms_b[:3]) + ("..." if len(syms_b) > 3 else "")
        return panels, f"Side-by-side risk comparison of {la} vs {lb}: total vol, factor vs specific risk, diversification ratio, and dominant factor tilts."

    if wants_riskmodel or wants_factor_exposures:
        port_syms = symbols if symbols else ["NVDA", "MSFT", "GOOGL", "META", "AMZN"]
        label = ", ".join(port_syms[:3]) + ("..." if len(port_syms) > 3 else "")
        if wants_riskmodel:
            add("risk_model", {"symbols": port_syms}, 7, 6)
            add("factor_exposures", {"symbols": port_syms}, 5, 6)
            summary = f"Multi-factor risk model for {label}: factor vs specific risk, per-factor contributions, and MCTR per holding."
        else:
            add("factor_exposures", {"symbols": port_syms}, 7, 6)
            add("risk_model", {"symbols": port_syms}, 5, 6)
            summary = f"Factor exposures for {label}: style tilts, factor premia, and per-holding loadings."
        return panels, summary

    if wants_risk:
        port_syms = symbols if symbols else ["NVDA", "MSFT", "GOOGL", "META", "AMZN"]
        add("portfolio_risk", {"symbols": port_syms}, 12, 5)
        summary = f"Portfolio risk breakdown for {', '.join(port_syms[:3])}{'...' if len(port_syms) > 3 else ''}: VaR, factor exposures, and risk metrics."
        return panels, summary

    if wants_montecarlo and symbols:
        sym = symbols[0]
        method = "gbm" if any(k in q for k in ["gbm", "geometric brownian", "lognormal", "parametric"]) else "bootstrap"
        add("monte_carlo", {"symbol": sym, "method": method}, 12, 6)
        name = data.get_company(sym)["name"]
        summary = f"Monte Carlo simulation of {name}: percentile fan, probability of loss, and terminal VaR/CVaR."
        return panels, summary

    if wants_portfolio_build:
        sig = _signals_found[0] if _signals_found else "momentum"
        scheme = "long_short" if any(k in q for k in [
            "long-short", "long short", "long/short", "ls ", "market neutral",
            "market-neutral", "dollar neutral", "dollar-neutral", "spread", "hedged",
        ]) else "top_quantile"
        params = {"signal": sig, "scheme": scheme}
        if symbols:
            params["symbols"] = symbols
        elif sector:
            params["sector"] = sector
        add("signal_portfolio", params, 12, 6)
        scheme_label = "long-short quantile spread" if scheme == "long_short" else "equal-weight top-quantile"
        return panels, (f"Built a {scheme_label} portfolio from the {sig.replace('_', ' ')} signal: "
                        f"position weights, realized equity vs an equal-weight benchmark, Sharpe, drawdown and turnover.")

    def _strategy_from_query() -> str:
        if "mean" in q or "reversion" in q:
            return "mean_reversion"
        if ("buy" in q and "hold" in q) or "buy-and-hold" in q:
            return "buy_and_hold"
        if "crossover" in q or "moving average" in q or "ma cross" in q:
            return "ma_crossover"
        return "momentum"

    if wants_walkforward:
        strategy = _strategy_from_query()
        # A strategy can survive out-of-sample on one name by luck, so when the
        # user names two-plus tickers OR a whole sector, validate across that
        # universe and aggregate the verdicts rather than picking a single name.
        wf_across = any(k in q for k in ["across", "each of", "all of", "universe", "basket", "every", "list of"])
        if len(symbols) >= 2 or (sector and (wf_across or not symbols)):
            wfc_params: dict = {"strategy": strategy}
            if len(symbols) >= 2:
                wfc_params["symbols"] = symbols
                scope = ", ".join(symbols[:4]) + ("..." if len(symbols) > 4 else "")
            else:
                wfc_params["sector"] = sector
                scope = repo.sector_name(sector)
            add("walk_forward_compare", wfc_params, 12, 6)
            summary = (
                f"Walk-forward robustness of the {strategy.replace('_', ' ')} strategy across {scope}: "
                "per-name out-of-sample verdicts (deflated Sharpe, PBO, decay) and an aggregate "
                "robustness score, so you can see if the edge holds across the universe or was a lucky draw. "
                "Thin-history names are flagged, not hidden."
            )
            return panels, summary
        sym = symbols[0] if symbols else "NVDA"
        add("walk_forward", {"symbol": sym, "strategy": strategy}, 12, 6)
        name = data.get_company(sym)["name"]
        summary = (
            f"Walk-forward validation of the {strategy.replace('_', ' ')} strategy on {name}: "
            "in-sample vs out-of-sample equity, deflated Sharpe, PBO, a multiple-testing "
            "haircut, and a plain-language overfitting verdict — all from real history."
        )
        return panels, summary

    if wants_backtest and symbols:
        sym = symbols[0]
        strategy = _strategy_from_query()
        explicit_strategy = strategy != "momentum" or "momentum" in q or "trend" in q
        bt_params = {"symbol": sym, "strategy": strategy}
        bt_params.update(_parse_invest_entry(query))
        # "Invest $X ... what's it worth now" with no named strategy means
        # buy-and-hold: the user wants the asset's actual dollar trajectory, not a
        # systematic strategy that may sit in cash.
        if bt_params.get("amount") and not explicit_strategy:
            strategy = "buy_and_hold"
            bt_params["strategy"] = strategy
        add("backtest", bt_params, 12, 6)
        name = data.get_company(sym)["name"]
        amt = bt_params.get("amount")
        if amt:
            entry_lbl = {
                "peak": "its all-time peak", "date": f"on {bt_params.get('date')}",
                "range": f"from {bt_params.get('start')}",
            }.get(bt_params.get("entry"), "the recent window")
            summary = (f"Invested ${amt:,.0f} in {name} at {entry_lbl}: entry point, "
                       "ending value, total gain in dollars, and the equity curve in dollars.")
        else:
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

    if wants_combine:
        chosen = _signals_in_query()
        params = {"method": _combine_method}
        if len(chosen) >= 2:
            params["signals"] = chosen
        if symbols:
            params["symbols"] = symbols
        elif sector:
            params["sector"] = sector
        add("combined_alpha", params, 12, 6)
        method_label = {
            "ic_weighted": "IC-weighted",
            "inverse_correlation": "inverse-correlation (risk-weighted)",
            "equal_weight": "equal-weight",
        }[_combine_method]
        return panels, (f"Combined alpha ({method_label}): blended the component signals into one composite score, "
                        "scored it against each component (rank IC, IC decay, quantile spread, turnover) and mapped their overlap.")

    if wants_scorecard:
        chosen = _signals_in_query()
        params: dict = {}
        if len(chosen) >= 2:
            params["signals"] = chosen
        if symbols:
            params["symbols"] = symbols
        elif sector:
            params["sector"] = sector
        add("signal_scorecard", params, 12, 6)
        return panels, "Alpha signal scorecard: rank IC, IC IR, t-stat, hit rate, turnover and long-short spread ranked across the signal library."

    if wants_signal:
        chosen = _signals_in_query()
        sig = chosen[0] if chosen else "momentum"
        params = {"signal": sig}
        if symbols:
            params["symbols"] = symbols
        elif sector:
            params["sector"] = sector
        add("signal_research", params, 12, 6)
        return panels, f"Alpha signal research for {sig.replace('_', ' ')}: rank IC, IC decay, turnover and the long-short quantile spread from real data."

    if wants_factor_perf:
        port_syms = symbols if symbols else ["NVDA", "MSFT", "GOOGL", "META", "AMZN"]
        params = {"symbols": port_syms} if symbols else {}
        add("factor_performance", params, 12, 6)
        return panels, "Factor performance over the estimation window: the cumulative return of each style factor (Market, Size, Value, Momentum, Volatility, Quality) so you can see which premia are actually being rewarded."

    if wants_tearsheet or wants_brinson or wants_factor_attr or wants_pnl:
        # A custom benchmark basket ("vs a basket of A, B, C") takes precedence
        # over a single ETF; strip those tickers from the book holdings so the
        # basket names don't leak into the portfolio.
        bench_basket = _extract_benchmark_constituents(q)
        book_syms = [s for s in symbols if s not in set(bench_basket)]
        port_syms = book_syms if len(book_syms) >= 1 else ["NVDA", "MSFT", "GOOGL", "META", "AMZN"]
        params = {"symbols": port_syms}
        rng = _extract_range(q)
        if rng:
            params["range"] = rng
        bench = _extract_benchmark(q)
        if bench_basket:
            params["benchmark_constituents"] = bench_basket
            bench_label = "a custom basket (" + ", ".join(bench_basket[:3]) + ("..." if len(bench_basket) > 3 else "") + ")"
        elif bench:
            params["benchmark"] = bench
            bench_label = bench
        else:
            bench_label = "SPY"
        label = ", ".join(port_syms[:3]) + ("..." if len(port_syms) > 3 else "")
        if wants_tearsheet:
            add("tear_sheet", params, 12, 6)
            return panels, f"Performance tear sheet for {label}: P&L vs {bench_label}, drawdowns, Brinson sector attribution and factor attribution in one view."
        if wants_brinson:
            # Brinson's sector decomposition is driven by a custom basket (its own
            # real sector weights/returns) or the chosen ETF's OWN real sector
            # weights × real sector-ETF returns; SPY by default.
            add("brinson_attribution", params, 12, 6)
            return panels, f"Brinson attribution for {label}: allocation, selection and interaction by sector vs {bench_label}."
        if wants_factor_attr:
            add("factor_attribution", params, 12, 6)
            return panels, f"Factor attribution for {label}: realized return decomposed into per-factor contributions and a specific return."
        add("performance_pnl", params, 12, 6)
        return panels, f"P&L for {label}: cumulative return vs {bench_label} with drawdowns and the full risk/return + active stat block."

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

    wants_chain = any(k in q for k in [
        "options chain", "option chain", "options table", "calls and puts",
        "full chain", "strike ladder", "all strikes",
    ])

    if wants_chain:
        sym = symbols[0] if symbols else "NVDA"
        params = {"symbol": sym}
        exp = _extract_expiry(query)
        if exp:
            params["expiry"] = exp
        add("options_chain", params, 12, 6)
        name = data.get_company(sym)["name"]
        return panels, f"{name} options chain — calls and puts across all strikes with bid/ask, IV, volume and open interest."

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
        add("heatmap", _market_params({"sector": sector}), 7, 4)
        add("screener", _market_params({"sector": sector}), 5, 4)
        if wants_news or True:
            add("news", {"scope_type": "sector", "scope": sector}, 6, 4)
        add("analysis", {"scope_type": "sector", "scope": sector}, 6, 4)
        scope_label = repo.market_label(market.get("country"), market.get("exchange")) if market else None
        prefix = f"{scope_label} " if scope_label else ""
        return panels, f"{prefix}{repo.sector_name(sector)} overview: heatmap, screener, news and analysis."

    if market:
        label = repo.market_label(market.get("country"), market.get("exchange")) or "Market"
        add("heatmap", _market_params({}), 8, 4)
        add("screener", _market_params({}), 4, 5)
        return panels, f"{label} overview: a market-filtered heatmap and screener."

    if wants_news:
        topic = _news_topic(query)
        if topic:
            add("news", {"scope_type": "topic", "scope": topic}, 12, 5)
            if wants_sentiment:
                add("sentiment", {"scope_type": "sector", "scope": "ai_tech"}, 6, 4)
            return panels, f"Live headlines on {topic}."

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
def refine(
    session_id: str,
    panel_id: str,
    instruction: str = "",
    params: Optional[dict] = None,
) -> Optional[dict]:
    panel = state.get_panel(session_id, panel_id)
    if panel is None:
        return None
    panel_type = panel["type"]
    layout = panel["layout"]
    title = panel.get("title")

    resolved = None
    keep_title = None
    if params:
        # Structured refine: interactive panel controls send explicit parameters
        # so we rebuild deterministically without natural-language parsing. The
        # quant panels merge control values over current data via
        # _structured_refine_params; other panel types apply params directly.
        resolved = _structured_refine_params(panel_type, panel, params)
    elif panel_type == "risk_monitor":
        # The risk monitor's custom shock builder submits a canonical instruction
        # that we parse deterministically and apply against the panel's CURRENT
        # book (which the panel data lets us reconstruct), so the shock never
        # resets the portfolio.
        resolved = _risk_monitor_shock_params(panel, instruction)
        if resolved is not None:
            keep_title = title  # a shock keeps the same book, so keep its title
    if resolved is None and panel_type == "supply_chain":
        # Drill-down: the graph emits a canonical "recenter" instruction when a
        # supplier/customer node is clicked. Parse it deterministically so the
        # recompose never depends on the LLM, and let the title regenerate to the
        # new subject (keep_title stays None).
        resolved = _supply_chain_recenter_params(instruction)
    if resolved is None:
        resolved = _refine_params(panel_type, panel, instruction)
    updated = harness.run_skill(panel_type, resolved, layout, title=keep_title, panel_id=panel_id)
    state.update_panel(session_id, updated)
    if panel_type == "trade_flow" and isinstance(updated.get("data"), dict):
        alerts.evaluate_flow(session_id, updated["data"])
    return updated


# Canonical custom-shock instructions emitted by the risk monitor's shock builder,
# e.g. "Custom shock: factor Momentum -8%", "Custom shock: asset NVDA -15%",
# "Custom shock: market -10%". Parsed deterministically (no LLM dependency).
_SHOCK_FACTOR_RE = re.compile(r"factor\s+([A-Za-z]+)\s+(-?\d+(?:\.\d+)?)\s*%?", re.I)
_SHOCK_ASSET_RE = re.compile(r"asset\s+([A-Za-z0-9.]+)\s+(-?\d+(?:\.\d+)?)\s*%?", re.I)
_SHOCK_MARKET_RE = re.compile(r"market\s+(-?\d+(?:\.\d+)?)\s*%?", re.I)


def _parse_shock(instruction: str) -> Optional[dict]:
    text = instruction or ""
    m = _SHOCK_FACTOR_RE.search(text)
    if m:
        return {"factor_shocks": {m.group(1).title(): float(m.group(2))}}
    m = _SHOCK_ASSET_RE.search(text)
    if m:
        return {"asset_shocks": {m.group(1).upper(): float(m.group(2))}}
    m = _SHOCK_MARKET_RE.search(text)
    if m:
        return {"market_shock": float(m.group(1))}
    return None


def _risk_monitor_shock_params(panel: dict, instruction: str) -> Optional[dict]:
    """Build refine params that re-run the SAME book with a custom shock applied.

    Returns None when the instruction isn't a custom-shock command, so the caller
    falls back to the normal LLM/heuristic refine path.
    """
    shock = _parse_shock(instruction)
    if not shock:
        return None
    data_blk = panel.get("data") or {}
    params: dict = {}
    positions = [p for p in (data_blk.get("positions") or []) if p.get("symbol")]
    if positions:
        params["symbols"] = [p["symbol"] for p in positions]
        params["weights"] = [float(p.get("weightPct", 0.0)) / 100.0 for p in positions]
    nav = data_blk.get("nav")
    if nav:
        params["nav"] = float(nav)
    name = data_blk.get("bookName")
    if name:
        params["portfolio_name"] = name
    params.update(shock)
    return params


_RISK_LIMIT_KEYS = ("maxGross", "maxNet", "maxPosition", "maxSector", "maxFactor", "varLimit")


def _parse_limit_edits(instruction: str) -> dict:
    """Extract limit overrides from a refine instruction.

    Accepts a JSON object ({"limits": {...}} or a bare {maxGross: ...} dict) or
    a `key=value` / `key:value` list. Only known limit keys with positive numeric
    values are kept. Returns {} when no limit edit is present.
    """
    edits: dict = {}
    text = (instruction or "").strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            src = obj.get("limits") if isinstance(obj.get("limits"), dict) else obj
            for k in _RISK_LIMIT_KEYS:
                if k in src:
                    try:
                        v = float(src[k])
                        if v > 0:
                            edits[k] = v
                    except (TypeError, ValueError):
                        pass
            if edits:
                return edits
    except (ValueError, TypeError):
        pass
    for k in _RISK_LIMIT_KEYS:
        m = re.search(rf"{k}\s*[=:]\s*(-?\d+(?:\.\d+)?)", text)
        if m:
            try:
                v = float(m.group(1))
                if v > 0:
                    edits[k] = v
            except ValueError:
                pass
    return edits


def _refine_risk_monitor(panel: dict, instruction: str) -> Optional[dict]:
    """Deterministic refine for risk_monitor limit edits: merge new limits onto
    the stored book/limits so editing a limit re-evaluates breaches without
    resetting the book. Returns None when the instruction is not a limit edit."""
    edits = _parse_limit_edits(instruction)
    if not edits:
        return None
    data = panel.get("data") or {}
    base = data.get("_refine") or {}
    limits = {**(base.get("limits") or {}), **edits}
    params: dict = {"limits": limits}
    symbols = base.get("symbols")
    if not symbols:
        # Fallback for panels built before _refine was stored: reconstruct from
        # the (possibly truncated) displayed positions.
        positions = data.get("positions") or []
        symbols = [p["symbol"] for p in positions if p.get("symbol")]
        weights = [float(p.get("weightPct", 0.0)) / 100.0 for p in positions]
        nav = data.get("nav")
        name = data.get("bookName")
    else:
        weights = base.get("weights")
        nav = base.get("nav")
        name = base.get("portfolio_name")
    if symbols:
        params["symbols"] = symbols
        if weights:
            params["weights"] = weights
        if nav:
            params["nav"] = nav
        if name:
            params["portfolio_name"] = name
    if base.get("factor_shocks"):
        params["factor_shocks"] = base["factor_shocks"]
    if base.get("asset_shocks"):
        params["asset_shocks"] = base["asset_shocks"]
    return params


# Canonical drill-down instruction emitted by the supply-chain graph when a
# node with a known symbol is clicked, e.g. "Recenter supply chain on TSM".
_SC_RECENTER_RE = re.compile(r"recenter\s+supply\s+chain\s+on\s+([A-Za-z0-9.]+)", re.I)


def _supply_chain_recenter_params(instruction: str) -> Optional[dict]:
    """Build refine params that recompose the supply chain on a new subject.

    Returns None when the instruction isn't a canonical recenter command, so the
    caller falls back to the normal LLM/heuristic refine path.
    """
    m = _SC_RECENTER_RE.search(instruction or "")
    if not m:
        return None
    return {"symbol": m.group(1).upper()}


def _structured_refine_params(panel_type: str, panel: dict, params: dict) -> dict:
    """Merge explicit control values over the panel's current parameters so a
    partial update (e.g. only the time window) keeps the rest of the state."""
    d = panel.get("data") or {}
    out: dict = {}
    if panel_type == "portfolio_risk":
        out["symbols"] = [s.upper() for s in (params.get("symbols") or d.get("symbols") or [])]
    elif panel_type == "correlation_matrix":
        out["symbols"] = [s.upper() for s in (params.get("symbols") or d.get("symbols") or [])]
        out["window"] = params.get("window") or d.get("window") or 30
    elif panel_type == "backtest":
        out["symbol"] = (params.get("symbol") or d.get("symbol") or "").upper() or None
        out["strategy"] = params.get("strategy") or d.get("strategy")
        out["range"] = params.get("range") or d.get("range")
        cur_entry = d.get("entry") or {}
        # Amount: explicit param wins, else keep the panel's current investment.
        amt = params.get("amount")
        if amt is None:
            amt = d.get("investment")
        out["amount"] = amt
        # Entry mode/date/range: explicit params win, else fall back to the
        # panel's current entry so changing only the amount keeps the entry put.
        out["entry"] = params.get("entry") or cur_entry.get("mode")
        out["date"] = params.get("date") or (cur_entry.get("date") if (params.get("entry") or cur_entry.get("mode")) == "date" else None)
        out["start"] = params.get("start")
        out["end"] = params.get("end")
        # Strategy parameters (lookback/threshold/fast/slow): an explicit param
        # wins; otherwise keep the panel's current tuned value — but only when the
        # strategy is unchanged, so switching strategies starts from fresh defaults
        # instead of leaking the previous strategy's settings.
        cur_params = d.get("params") or {}
        strategy_changed = bool(params.get("strategy")) and params.get("strategy") != d.get("strategy")
        for key in ("lookback", "threshold", "fast", "slow"):
            val = params.get(key)
            if val is None and not strategy_changed:
                val = cur_params.get(key)
            if val is not None:
                out[key] = val
    elif panel_type == "walk_forward":
        out["symbol"] = (params.get("symbol") or d.get("symbol") or "").upper() or None
        out["strategy"] = params.get("strategy") or d.get("strategy")
        out["splits"] = params.get("splits") or d.get("nSplits")
    elif panel_type == "factor_analysis":
        out["symbol"] = (params.get("symbol") or d.get("symbol") or "").upper() or None
    else:
        out = dict(params)
    return {k: v for k, v in out.items() if v is not None}


def _refine_params(panel_type: str, panel: dict, instruction: str) -> dict:
    if panel_type == "risk_monitor":
        rp = _refine_risk_monitor(panel, instruction)
        if rp is not None:
            return rp
    if ai.ai_available():
        try:
            return _refine_params_llm(panel_type, panel, instruction)
        except Exception:
            pass
    return _refine_params_heuristic(panel_type, panel, instruction)


def _current_macro_state(panel: dict) -> tuple:
    """Return (theme, overrides) from a macro_dashboard panel's persisted data."""
    d = panel.get("data") or {}
    theme = d.get("theme") or "global"
    overrides = [
        {"op": o.get("op"), "symbol": o.get("symbol")}
        for o in (d.get("overrides") or [])
        if o.get("op") and o.get("symbol")
    ]
    return theme, overrides


def _merge_macro_overrides(existing: list, new_ops: list) -> list:
    """Apply new add/remove ops on top of existing ones; latest op per symbol wins."""
    merged = [dict(o) for o in existing]
    for op in new_ops:
        sym = op["symbol"]
        merged = [m for m in merged if m["symbol"] != sym]
        merged.append({"op": op["op"], "symbol": sym})
    return merged


def _detect_macro_theme(instruction: str) -> Optional[str]:
    """Return a theme key only if the instruction explicitly names a theme.

    Returns None when no theme is referenced so the caller keeps the panel's
    current theme (calling resolve_macro_theme unconditionally would wrongly
    reset every plain add/remove to the "global" default).
    """
    ql = " " + (instruction or "").lower() + " "
    candidates = list(data.MACRO_THEMES.keys()) + list(data.MACRO_THEME_ALIASES.keys())
    for cand in sorted(candidates, key=len, reverse=True):
        if re.search(r"\b" + re.escape(cand) + r"\b", ql):
            return data.resolve_macro_theme(cand)
    return None


def _refine_macro_heuristic(panel: dict, instruction: str) -> dict:
    theme, existing = _current_macro_state(panel)
    new_theme = _detect_macro_theme(instruction) or theme
    syms = data.resolve_macro_symbols(instruction)
    ql = instruction.lower()
    is_remove = any(k in ql for k in ("remove", "drop", "delete", "take out", "take off", "get rid", "hide", "exclude", "without"))
    new_ops = [{"op": "remove" if is_remove else "add", "symbol": s} for s in syms]
    return {"theme": new_theme, "overrides": _merge_macro_overrides(existing, new_ops)}


def _refine_macro_llm(panel: dict, instruction: str) -> dict:
    theme, existing = _current_macro_state(panel)
    valid = ", ".join(data.MACRO_ASSETS.keys())
    tool = {"type": "function", "function": {
        "name": "update_macro_dashboard",
        "description": "Update which assets appear on a macro dashboard, and optionally its theme.",
        "parameters": {"type": "object", "properties": {
            "theme": {"type": "string", "enum": ["global", "inflation", "china", "risk"],
                      "description": "Only change if the user explicitly asks for a different theme."},
            "add": {"type": "array", "items": {"type": "string"},
                    "description": f"Macro symbols to add. Must be one of: {valid}"},
            "remove": {"type": "array", "items": {"type": "string"},
                       "description": f"Macro symbols to remove. Must be one of: {valid}"},
        }},
    }}
    sys = (
        "You edit a macro / cross-asset dashboard panel. Decide which assets to add or remove "
        f"to satisfy the instruction. Use ONLY these macro symbols: {valid}. Map names to symbols "
        "(e.g. 'EUR/USD'->EURUSD, 'iron ore'->IRON, 'gold'->GOLD, 'S&P 500'->SPX, 'dollar index'->DXY, "
        "'VIX'->VIX, '10y'->US10Y). Do not change the theme unless explicitly asked. Call the tool once."
    )
    msg = ai.chat(
        [
            {"role": "system", "content": sys},
            {"role": "user", "content": f"Current theme: {theme}\nInstruction: {instruction}"},
        ],
        tools=[tool],
        tool_choice={"type": "function", "function": {"name": "update_macro_dashboard"}},
    )
    tcs = getattr(msg, "tool_calls", None) or []
    if not tcs:
        raise RuntimeError("no tool call")
    args = json.loads(tcs[0].function.arguments or "{}")
    new_ops: list = []
    for s in (args.get("remove") or []):
        su = str(s).upper()
        if su in data.MACRO_ASSETS:
            new_ops.append({"op": "remove", "symbol": su})
    for s in (args.get("add") or []):
        su = str(s).upper()
        if su in data.MACRO_ASSETS:
            new_ops.append({"op": "add", "symbol": su})
    new_theme = args.get("theme") or theme
    if new_theme not in data.MACRO_THEMES:
        new_theme = theme
    return {"theme": new_theme, "overrides": _merge_macro_overrides(existing, new_ops)}


def _refine_params_llm(panel_type: str, panel: dict, instruction: str) -> dict:
    if panel_type == "macro_dashboard":
        return _refine_macro_llm(panel, instruction)
    tool = next(
        (t for t in _all_tools() if _type_of_tool(t["function"]["name"]) == panel_type),
        None
    )
    if tool is None:
        raise RuntimeError(f"no tool for panel type {panel_type}")
    current = {"type": panel_type, "title": panel.get("title")}
    sys = (
        "You update a single dashboard panel in a market terminal. Keep the panel the SAME "
        "type. Call the provided tool exactly once with the parameters that satisfy the user's "
        "instruction. Use only valid tickers and sectors.\n"
        f"Popular tickers: {', '.join(repo.prompt_symbols(60))}. Hundreds more US + Singapore (SGX) "
        "names are valid; SGX uses base codes like D05/O39 (no .SI). "
        f"Valid sectors: {', '.join(data.SECTORS.keys())}."
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
    if panel_type == "macro_dashboard":
        return _refine_macro_heuristic(panel, instruction)
    syms = _extract_symbols(instruction)
    sector = repo.resolve_sector(instruction)
    if panel_type in ("price_chart", "fundamentals", "supply_chain", "dcf_model", "earnings_transcript"):
        d = panel.get("data") or {}
        sym = syms[0] if syms else d.get("symbol")
        if sym:
            params = {"symbol": sym}
            # Range round-trips even when the instruction is just a window
            # (e.g. the chart's "1Y" picker) — keep the current symbol, swap range.
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
        if panel_type == "news":
            topic = _news_topic(instruction)
            if topic:
                return {"scope_type": "topic", "scope": topic}
    if panel_type in ("screener", "heatmap", "ma_tracker"):
        market = repo.resolve_market(instruction)
        if sector or market:
            params = {}
            if sector:
                params["sector"] = sector
            if market and panel_type in ("screener", "heatmap"):
                if market.get("country"):
                    params["country"] = market["country"]
                if market.get("exchange"):
                    params["exchange"] = market["exchange"]
            if params:
                return params
    if panel_type in ("iv_surface", "vol_term_structure") and syms:
        return {"symbol": syms[0]}
    if panel_type == "options_chain" and (syms or _extract_expiry(instruction)):
        params = {"symbol": syms[0]} if syms else {"symbol": (panel.get("data") or {}).get("symbol", "NVDA")}
        exp = _extract_expiry(instruction)
        if exp:
            params["expiry"] = exp
        return params
    if panel_type == "options_screener":
        ql = instruction.lower()
        params = dict(panel.get("data", {}).get("filters") or {})
        # carry the current universe forward
        d = panel.get("data") or {}
        if sector:
            params["sector"] = sector
        if "put" in ql and "call" not in ql:
            params["optionType"] = "put"
        elif "call" in ql and "put" not in ql:
            params["optionType"] = "call"
        elif "all" in ql and ("type" in ql or "call" in ql or "put" in ql):
            params["optionType"] = "all"
        if "cheap" in ql:
            params["rankBy"] = "cheap"
        elif "skew" in ql:
            params["rankBy"] = "skew"
        elif "volume" in ql or "unusual" in ql or "active" in ql:
            params["rankBy"] = "volume"
        elif "open interest" in ql:
            params["rankBy"] = "oi"
        elif "high iv" in ql or "highest iv" in ql or "implied vol" in ql:
            params["rankBy"] = "iv"
        for band in ("otm", "itm", "atm"):
            if band in ql:
                params["moneyness"] = band
        m = re.search(r"(\d+)\s*day", ql)
        if m:
            params["dteMax"] = float(m.group(1))
        m = re.search(r"iv\s*(?:over|above|>|min|of)?\s*(\d+)", ql)
        if m:
            params["ivMin"] = float(m.group(1))
        return params
    if panel_type == "options_strategy" and syms:
        return {"symbol": syms[0], "strategy": _extract_strategy(instruction)}
    if panel_type == "structured_product" and syms:
        return {"symbol": syms[0]}
    if panel_type == "signal_research":
        ql = instruction.lower()
        sig = engine.normalize_signal(ql) if any(
            k in ql for k in ["momentum", "trend", "reversal", "reversion", "low vol", "volatility", "value", "earnings yield", "cheap", "quality", "margin", "profitab"]
        ) else (panel.get("data") or {}).get("signal", "momentum")
        params = {"signal": sig}
        if syms:
            params["symbols"] = syms
        elif sector:
            params["sector"] = sector
        return params
    if panel_type == "signal_scorecard":
        params = {}
        if syms:
            params["symbols"] = syms
        elif sector:
            params["sector"] = sector
        return params
    if panel_type == "earnings_calendar":
        if syms:
            return {"symbols": syms}
        if sector:
            return {"sector": sector}
        return {}
    if panel_type == "etf_holdings":
        etf = _extract_etf(instruction) or (syms[0] if syms else (panel.get("data") or {}).get("etf"))
        if etf:
            return {"symbol": etf}
    if panel_type == "etf_exposure":
        sym = syms[0] if syms else (_extract_etf(instruction) or (panel.get("data") or {}).get("symbol"))
        if sym:
            return {"symbol": sym}
    d = panel.get("data") or {}
    if panel_type == "portfolio_risk":
        return {"symbols": syms or d.get("symbols") or []}
    if panel_type == "factor_analysis":
        return {"symbol": syms[0] if syms else d.get("symbol")}
    if panel_type == "correlation_matrix":
        out = {"symbols": syms if len(syms) >= 2 else d.get("symbols")}
        ql = instruction.lower()
        if "90" in ql:
            out["window"] = 90
        elif "30" in ql:
            out["window"] = 30
        elif d.get("window"):
            out["window"] = d["window"]
        return out
    if panel_type == "backtest":
        out = {"symbol": syms[0] if syms else d.get("symbol")}
        ql = instruction.lower()
        if any(k in ql for k in ["momentum", "mean", "revert", "revers", "buy", "hold", "crossover", "moving average", "trend"]):
            out["strategy"] = engine.normalize_strategy(ql)
        elif d.get("strategy"):
            out["strategy"] = d["strategy"]
        for r in ["1M", "3M", "6M", "1Y", "YTD"]:
            if r.lower() in ql:
                out["range"] = r
        return out
    if panel_type in ("price_chart", "fundamentals", "supply_chain", "dcf_model", "earnings_transcript") and d.get("symbol"):
        return {"symbol": d["symbol"]}
    if panel_type in ("iv_surface", "vol_term_structure", "options_strategy", "structured_product") and d.get("symbol"):
        params = {"symbol": d["symbol"]}
        if panel_type == "options_strategy":
            params["strategy"] = _extract_strategy(instruction)
        return params
    return {}
