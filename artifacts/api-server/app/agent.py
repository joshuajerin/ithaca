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

from . import ai, data, dynamic_skills, engine, harness, repo, skills, state, strategy, strategy_store


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
            "description": f"Add a portfolio P&L panel for a book over a window: cumulative & periodic return vs a REAL, traded benchmark ETF (default SPY; configurable e.g. QQQ/IWM), a drawdown track, and a full risk/return + active stat block (return, vol, Sharpe, max drawdown, hit rate, tracking error, information ratio, beta, alpha, up/down capture). Real returns only; excluded names reported. Use for P&L, performance vs benchmark, or how a book/portfolio has performed. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio tickers. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional portfolio weights aligned with symbols (auto-normalized; equal-weight if omitted)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the portfolio."},
                "range": {"type": "string", "enum": ["1M", "3M", "6M", "1Y", "YTD"]},
                "benchmark": {"type": "string", "description": "Real benchmark ETF to compare against (default SPY).", "enum": ["SPY", "QQQ", "DIA", "IWM", "VTI", "VOO"]},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_brinson_attribution",
            "description": f"Add a Brinson performance attribution panel: decomposes a book's active return vs a sector-aware REAL benchmark (each sector mapped to a real, traded sector/industry ETF such as XLK/XLF/XLE) into allocation, selection and interaction effects BY SECTOR (the three effects sum exactly to the active return). Real sector weights/returns; excluded names and unmapped sectors reported. Use for performance attribution, allocation vs selection, Brinson, or 'where did my outperformance come from'. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio tickers. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional portfolio weights aligned with symbols (auto-normalized; equal-weight if omitted)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the portfolio."},
                "range": {"type": "string", "enum": ["1M", "3M", "6M", "1Y", "YTD"]},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_factor_attribution",
            "description": f"Add a factor return attribution panel: decomposes a book's REALIZED return over a window into per-factor contributions (exposure × realized factor return) for Market, Size, Value, Momentum, Volatility, Quality, plus a specific (idiosyncratic) return — contributions + specific reconstruct the realized return. Uses the real multi-factor risk model. Use for factor attribution, factor contribution to return, or 'which factors drove my return'. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio tickers. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional portfolio weights aligned with symbols (auto-normalized; equal-weight if omitted)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the portfolio."},
                "range": {"type": "string", "enum": ["1M", "3M", "6M", "1Y", "YTD"]},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }, "required": ["symbols"]},
        }},
        {"type": "function", "function": {
            "name": "add_tear_sheet",
            "description": f"Add a performance tear-sheet panel that combines P&L vs a REAL benchmark ETF (default SPY; configurable), the drawdown track, Brinson sector attribution and factor attribution into one report-style view for a book over a window. Use for a tear sheet, a full performance review, or 'give me a complete performance breakdown of my portfolio'. Best at full width. {sizing}",
            "parameters": {"type": "object", "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": f"Portfolio tickers. Valid: {syms}"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional portfolio weights aligned with symbols (auto-normalized; equal-weight if omitted)."},
                "portfolio_name": {"type": "string", "description": "Optional display name for the portfolio."},
                "range": {"type": "string", "enum": ["1M", "3M", "6M", "1Y", "YTD"]},
                "benchmark": {"type": "string", "description": "Real benchmark ETF to compare against (default SPY).", "enum": ["SPY", "QQQ", "DIA", "IWM", "VTI", "VOO"]},
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
    "add_monte_carlo": "monte_carlo",
    "add_correlation_matrix": "correlation_matrix",
    "add_factor_analysis": "factor_analysis",
    "add_risk_model": "risk_model",
    "add_factor_exposures": "factor_exposures",
    "add_performance_pnl": "performance_pnl",
    "add_brinson_attribution": "brinson_attribution",
    "add_factor_attribution": "factor_attribution",
    "add_tear_sheet": "tear_sheet",
    "add_portfolio_optimizer": "portfolio_optimizer",
    "add_signal_research": "signal_research",
    "add_signal_scorecard": "signal_scorecard",
    "add_iv_surface": "iv_surface",
    "add_options_strategy": "options_strategy",
    "add_vol_term_structure": "vol_term_structure",
    "add_structured_product": "structured_product",
    "add_supply_chain": "supply_chain",
    "add_dcf_model": "dcf_model",
    "add_earnings_transcript": "earnings_transcript",
    "add_ma_tracker": "ma_tracker",
    "add_company_analytics": "company_analytics",
    "add_data_universe": "data_universe",
    "add_intraday_chart": "intraday_chart",
    "add_data_quality": "data_quality",
    "add_analyst_report": "analyst_report",
    "add_scenario": "scenario",
    "add_risk_monitor": "risk_monitor",
    "add_strategy_desk": "strategy_desk",
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
        "- For derivatives requests: vol surface → add_iv_surface; options strategy → add_options_strategy; "
        "VIX/vol curve → add_vol_term_structure; barrier/exotic → add_structured_product.\n"
        "- For macro and fixed income: global view → add_macro_dashboard; yield curve → add_yield_curve; "
        "bond RV → add_bond_rv; CDS → add_cds_pricer; duration/cash flows → add_cashflow_duration.\n"
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
        "- For M&A / deal flow / mergers / acquisitions / arb spread requests, use add_ma_tracker.\n"
        "- For backtest / strategy / Sharpe / drawdown requests, use add_backtest. For Monte Carlo / "
        "simulation / forward projection / 'probability of loss' / scenario forecast requests, use add_monte_carlo.\n"
        "- For portfolio risk requests, pick the right panel: risk decomposition / factor vs specific risk / "
        "MCTR / 'where is my risk coming from' / risk model → add_risk_model; factor tilts / style exposures / "
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
        "a full 'tear sheet' / complete performance review combining P&L, drawdowns, Brinson and factor "
        "attribution → add_tear_sheet (full width). These take symbols (+ optional weights, range). P&L and "
        "tear sheet also take a real benchmark ETF (default SPY; pass benchmark=QQQ/IWM/DIA/VTI/VOO if the user "
        "names one, e.g. 'vs the Nasdaq' → QQQ).\n"
        "- For alpha signal research (rank IC, information coefficient, IC decay, signal turnover, "
        "quantile/decile long-short spread, 'does <signal> predict returns'), use add_signal_research with one "
        "signal of momentum/short_reversal/low_volatility/value/quality. To compare or rank several signals "
        "('signal scorecard', 'which signal works best', 'compare value vs momentum'), use add_signal_scorecard.\n"
        "- For company analytics requests ('why is X up/down', 'what drives X', 'analyze X vs competitors', "
        "'company analytics for X', 'competition for X', 'price drivers for X'), use add_company_analytics.\n"
        "- For data-layer requests: universe/coverage/'what's tracked'/'live vs mock' → add_data_universe; "
        "intraday/minute/hourly price action → add_intraday_chart; data quality/gaps/stale/freshness/'can I "
        "trust the data' → add_data_quality.\n"
        "- For a DEEP analyst opinion ('analyst take', 'deep analysis', 'write-up', 'bull/bear case', "
        "'investment thesis', 'should I buy/sell X', 'your view on X'), use add_analyst_report (richer than "
        "add_analysis). Pair it with a price chart for context. If the user asks to analyze/review "
        "'my dashboard', 'this dashboard', 'everything on screen' or 'my portfolio', call add_analyst_report "
        "with scope='dashboard' (no symbol/sector) for a portfolio-level take across the kept panels.\n"
        "- For WHAT-IF / hypothetical requests ('what if', 'if I do X then Y', 'if rates fall 100bps', "
        "'if X margins compress to 40%', 'suppose', 'scenario where'), use add_scenario and pass the user's "
        "full hypothetical as the prompt argument.\n"
        "- For RISK MANAGEMENT / MONITORING requests ('monitor/manage my risk', 'risk dashboard', 'check my "
        "exposures', 'gross/net exposure', 'am I within limits', 'any limit breaches', 'stress test my book', "
        "'how much could I lose if markets crash / rates spike / momentum reverses'), use add_risk_monitor. "
        "Pass signed weights (negative = short) when the user describes a long/short book; pass limits to "
        "override defaults, and factor_shocks/asset_shocks/market_shock for a specific hypothetical stress. "
        "This is the risk DESK (exposures + limits + crisis & shock stress); use add_risk_model instead when "
        "the user only wants factor-vs-specific risk decomposition/MCTR, and add_scenario for a narrative "
        "what-if projection.\n"
        "- For STRATEGY LIFECYCLE / paper-book / 'desk' requests that only VIEW state ('show the desk', "
        "'my strategies', 'the paper book', 'strategy lifecycle', 'how is the momentum strategy doing'), "
        "use add_strategy_desk (pass `strategy` to focus one). Lifecycle ACTIONS — create / paper-trade / "
        "promote / demote / retire a strategy — are handled before you are called, so do not try to "
        "perform them; just present the desk.\n"
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
    # portfolio" must fall through to the portfolio-optimization path.
    if re.search(r"\brebalanc\w*\b", q) and (
        re.search(r"\bstrateg|\bbook\b", q) or _signal_in_query(q) is not None
    ):
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


def _handle_lifecycle(query: str, sid: str, voice: bool) -> Optional[dict]:
    q = query.lower()
    action = _lifecycle_action(q)
    if not action:
        return None
    signal = _signal_in_query(q)
    symbols = _extract_symbols(query)
    target: Optional[dict] = None
    msg = ""

    try:
        if action == "create":
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
                target, info = strategy.rebalance(target)
                if info.get("applied"):
                    label = engine.signal_label(target.get("signal") or "momentum")
                    if info.get("established"):
                        msg = (f"Built {target['name']}'s book from the latest {label} targets — "
                               f"{info['trades']} positions, ${info['costUsd']:,.0f} modeled cost.")
                    else:
                        msg = (f"Rebalanced {target['name']} to its latest {label} targets — "
                               f"{info['trades']} trades, {info['turnoverPct']:.1f}% turnover, "
                               f"${info['costUsd']:,.0f} modeled cost.")
                else:
                    msg = f"Couldn't rebalance {target['name']}: {info.get('reason', 'no trades generated')}."
    except Exception:  # noqa: BLE001 — lifecycle must never 500 the orchestrate path
        return None

    cursor = {"x": 0, "y": 0, "rowH": 0}
    panels: List[dict] = []

    def add(panel_type, params, w, h, title=None):
        panels.append(harness.run_skill(panel_type, params, harness.pack_layout(w, h, cursor), title=title))

    add("strategy_desk", {"strategy": target["name"]}, 12, 5)
    wmap = target.get("targetWeights") or {}
    # Link the desk into the Risk Management + Attribution pillars for the book.
    if target.get("stage") in ("paper", "live") and wmap:
        syms = list(wmap.keys())
        ws = [wmap[s] for s in syms]
        add("risk_monitor", {"symbols": syms, "weights": ws, "portfolio_name": target["name"]}, 12, 6)
        add("factor_analysis", {"symbols": syms}, 12, 5)

    state.set_dashboard(sid, panels)
    state.append_history(sid, "user", query)
    state.append_history(sid, "assistant", msg)
    result: dict = {"sessionId": sid, "summary": msg, "panels": panels, "intent": "build"}
    if voice:
        result["narration"] = _build_narration(query, msg, panels)
    return result


def orchestrate(query: str, session_id: Optional[str], voice: bool = False) -> dict:
    # Each new query is evaluated against the panels already on screen: panels
    # that still serve the new request are KEPT, panels belonging to an
    # abandoned subject are dropped, and new panels are added on top.
    reset = _wants_reset(query)
    # A reset (or the "default" placeholder) starts a brand-new session so that
    # BOTH the panels and the prior conversation context start fresh.
    if reset or not session_id or session_id == "default":
        sid = uuid.uuid4().hex[:12]
        base: List[dict] = []
    else:
        sid = session_id
        base = state.get_dashboard(sid)
    if reset:
        base = []

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

    # Decide which existing panels remain relevant to this prompt, then re-pack
    # the kept panels from the top so removed panels leave no holes in the grid.
    kept = _decide_kept_panels(query, sid, base) if base else []
    kept, cursor = _repack(kept)

    panels: List[dict] = []
    summary = ""

    if ai.ai_available():
        try:
            panels, summary = _orchestrate_llm(query, sid, kept, dict(cursor))
        except Exception:
            panels, summary = [], ""

    if not panels:
        dash_syms, dash_secs = _dashboard_subjects(kept)
        panels, summary = _orchestrate_heuristic(query, dict(cursor), dash_syms, dash_secs)

    combined = kept + panels
    state.set_dashboard(sid, combined)
    state.append_history(sid, "user", query)
    state.append_history(sid, "assistant", summary)

    result: dict = {"sessionId": sid, "summary": summary, "panels": combined, "intent": "build"}
    if voice:
        result["narration"] = _build_narration(query, summary, panels)
    return result


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
    return f"{n} trades ({buys} BUY/{sells} SELL); notable: {rows}"


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


_PANEL_SERIALIZERS = {
    "backtest": _ser_backtest,
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


def _answer_question_llm(query: str, sid: str, panels: List[dict]) -> str:
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
    messages = [{"role": "system", "content": sys}]
    for h in state.get_history(sid)[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
    if panels:
        ctx = _panels_context(panels)
        messages.append({"role": "system", "content": f"Panels currently on screen with their data:\n{ctx}"})
    else:
        messages.append({"role": "system", "content": "There are no panels on screen right now."})
    messages.append({"role": "user", "content": query})
    msg = ai.chat(messages)
    return (msg.content or "").strip()


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
_SUBJECT_AGNOSTIC_TYPES = {"macro_dashboard", "yield_curve"}

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
def _build_narration(query: str, summary: str, panels: List[dict]) -> List[dict]:
    """Produce ordered spoken narration segments, each optionally tied to a panel.

    The first segment is a short lead-in (no panel), then one segment per panel
    in layout order so the UI can highlight panels as they are described.
    """
    if ai.ai_available():
        try:
            segs = _narration_llm(query, summary, panels)
            if segs:
                return segs
        except Exception:
            pass
    return _narration_heuristic(summary, panels)


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
    "monte_carlo": "a Monte Carlo simulation",
    "correlation_matrix": "a correlation matrix",
    "factor_analysis": "a factor analysis",
    "risk_model": "a multi-factor risk model",
    "factor_exposures": "a factor exposure panel",
    "performance_pnl": "a P&L panel",
    "brinson_attribution": "a Brinson attribution",
    "factor_attribution": "a factor attribution",
    "tear_sheet": "a performance tear sheet",
    "portfolio_optimizer": "a portfolio optimizer",
    "signal_research": "an alpha signal research panel",
    "signal_scorecard": "an alpha signal scorecard",
    "iv_surface": "an IV surface",
    "options_strategy": "an options strategy",
    "vol_term_structure": "a vol term structure",
    "structured_product": "a structured product pricer",
    "supply_chain": "a supply chain map",
    "dcf_model": "a DCF model",
    "earnings_transcript": "an earnings transcript",
    "ma_tracker": "an M&A tracker",
    "company_analytics": "a company analytics panel",
    "data_universe": "a data universe overview",
    "intraday_chart": "an intraday chart",
    "data_quality": "a data quality report",
    "analyst_report": "an analyst report",
    "scenario": "a what-if scenario",
    "risk_monitor": "a risk monitor",
    "strategy_desk": "the strategy desk",
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
            if len(short) > 3 and re.search(r"\b" + re.escape(short) + r"\b", low):
                found.append(s)
    return found


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


def _extract_benchmark(q: str) -> Optional[str]:
    """Map free-text to a real benchmark ETF ticker, or None for the default."""
    ql = q.lower()
    if "nasdaq" in ql or "qqq" in ql:
        return "QQQ"
    if "russell" in ql or "iwm" in ql or "small cap" in ql or "small-cap" in ql:
        return "IWM"
    if "dow" in ql or "dia" in ql:
        return "DIA"
    if "total market" in ql or " vti" in ql:
        return "VTI"
    if "voo" in ql:
        return "VOO"
    if "s&p" in ql or "sp500" in ql or "s and p" in ql or " spy" in ql or "500" in ql:
        return "SPY"
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

    wants_compare = any(k in q for k in ["compare", "vs", "versus", "against"]) or len(symbols) >= 2
    wants_news = "news" in q or "headline" in q or "happening" in q
    wants_sentiment = any(k in q for k in ["sentiment", "buzz", "mood", "social"])
    wants_overview = any(k in q for k in ["overview", "moving", "market", "movers", "heatmap", "today"])
    wants_screen = any(k in q for k in ["screen", "screener", "scan", "list", "top "])
    wants_order_book = any(k in q for k in ["order book", "orderbook", "bid", "ask", "depth", "level 2", "l2"])
    wants_trade_flow = any(k in q for k in ["unusual", "block", "sweep", "dark pool", "flow", "activity"])
    wants_tca = any(k in q for k in ["tca", "transaction cost", "slippage", "vwap", "twap", "pov",
                                     "execution", "impl", "market impact", "participation rate",
                                     "execution cost", "cost to trade", "trade into"])
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
    wants_riskmodel = any(k in q for k in ["risk model", "risk decomp", "decompose risk", "factor vs specific", "specific risk", "mctr", "marginal contribution", "where is my risk", "risk contribution", "factor risk"])
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
    wants_backtest = any(k in q for k in ["backtest", "back test", "back-test", "momentum strategy", "strategy", "sharpe", "cagr", "drawdown"])
    wants_montecarlo = any(k in q for k in ["monte carlo", "montecarlo", "monte-carlo", "simulate", "simulation", "forward project", "project price", "scenario analysis", "probability of loss", "forecast price", "gbm", "geometric brownian", "bootstrap"])
    wants_correlation = any(k in q for k in ["correlation", "correlat", "hedge ratio", "co-movement", "diversif", "beta table"])
    wants_tearsheet = any(k in q for k in ["tear sheet", "tearsheet", "tear-sheet", "performance review", "performance breakdown", "full performance"])
    wants_brinson = any(k in q for k in ["brinson", "allocation effect", "selection effect", "allocation vs selection", "performance attribution", "attribution analysis"])
    wants_factor_attr = any(k in q for k in ["factor attribution", "factor contribution", "factors drove", "return from factors", "factor return attribution"])
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

    if wants_desk:
        add("strategy_desk", {}, 12, 5)
        return panels, "Here's the strategy desk: every strategy across the lifecycle with live P&L."

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
    wants_dashboard_review = any(k in q for k in [
        "my dashboard", "this dashboard", "the dashboard", "current dashboard",
        "whole dashboard", "entire dashboard", "everything on screen", "on my screen",
        "these panels", "my portfolio", "my holdings", "what i have up",
    ]) and any(k in q for k in [
        "analy", "review", "report", "take", "thesis", "assess", "summary",
        "summarize", "overview", "opinion", "view",
    ])

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
        add("scenario", sc_params, 12, 6)
        label = (
            data.get_company(sym)["name"] if sym
            else repo.sector_name(sector) if sector
            else "your dashboard" if dash_syms
            else "a market-proxy basket"
        )
        return panels, f"What-if scenario for {label}: baseline vs scenario projection with reasoning and caveats."

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

    if wants_company_analytics and symbols:
        sym = symbols[0]
        add("company_analytics", {"symbol": sym}, 8, 6)
        add("price_chart", {"symbol": sym, "range": "3M"}, 4, 6)
        name = data.get_company(sym)["name"]
        return panels, f"Company analytics for {name}: price drivers, competitive landscape, metric correlations, and catalyst watch."

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

    if wants_optimizer:
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

    if wants_tearsheet or wants_brinson or wants_factor_attr or wants_pnl:
        port_syms = symbols if len(symbols) >= 1 else ["NVDA", "MSFT", "GOOGL", "META", "AMZN"]
        params = {"symbols": port_syms}
        rng = _extract_range(q)
        if rng:
            params["range"] = rng
        bench = _extract_benchmark(q)
        if bench:
            params["benchmark"] = bench
        label = ", ".join(port_syms[:3]) + ("..." if len(port_syms) > 3 else "")
        bench_label = bench or "SPY"
        if wants_tearsheet:
            add("tear_sheet", params, 12, 6)
            return panels, f"Performance tear sheet for {label}: P&L vs {bench_label}, drawdowns, Brinson sector attribution and factor attribution in one view."
        if wants_brinson:
            add("brinson_attribution", params, 12, 6)
            return panels, f"Brinson attribution for {label}: allocation, selection and interaction by sector vs real sector ETFs."
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
    if ai.ai_available():
        try:
            return _refine_params_llm(panel_type, panel, instruction)
        except Exception:
            pass
    return _refine_params_heuristic(panel_type, panel, instruction)


def _refine_params_llm(panel_type: str, panel: dict, instruction: str) -> dict:
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
    syms = _extract_symbols(instruction)
    sector = repo.resolve_sector(instruction)
    if panel_type in ("price_chart", "fundamentals", "supply_chain", "dcf_model", "earnings_transcript") and syms:
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
        if panel_type == "news":
            topic = _news_topic(instruction)
            if topic:
                return {"scope_type": "topic", "scope": topic}
    if panel_type in ("screener", "heatmap", "ma_tracker") and sector:
        return {"sector": sector}
    if panel_type in ("iv_surface", "vol_term_structure") and syms:
        return {"symbol": syms[0]}
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
    d = panel.get("data") or {}
    if panel_type in ("price_chart", "fundamentals", "supply_chain", "dcf_model", "earnings_transcript") and d.get("symbol"):
        return {"symbol": d["symbol"]}
    if panel_type in ("iv_surface", "vol_term_structure", "options_strategy", "structured_product") and d.get("symbol"):
        params = {"symbol": d["symbol"]}
        if panel_type == "options_strategy":
            params["strategy"] = _extract_strategy(instruction)
        return params
    return {}
