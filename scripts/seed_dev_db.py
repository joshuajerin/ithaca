"""Seed the local dev SQLite DB with realistic fake data for joshuaj6195@gmail.com."""
from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "doomberg.db"
TENANT_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "usr_joshua_dev_001"
EMAIL = "joshuaj6195@gmail.com"

def ts(offset_hours: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=offset_hours)).isoformat()

def new_id() -> str:
    return str(uuid.uuid4())

# ── Sessions (runs + trace_events) ────────────────────────────────────────────

SESSIONS = [
    {
        "title": "NVDA momentum breakout — is the move real?",
        "prompt": "Analyze NVDA recent price action. Is the breakout above $950 technically valid or just hype? Give me a thesis and backtest it.",
        "agent": "claude-sonnet-4-6",
        "offset_hours": 0.5,
        "state": "done",
        "steps": [
            {"tool": "market_news", "args": {"ticker": "NVDA", "limit": 10}, "result": {"headlines": ["NVDA hits ATH on AI server demand", "Jensen Huang: data center capex cycle 'just beginning'", "Options flow shows bullish gamma positioning above $950"], "count": 10}, "duration_ms": 812},
            {"tool": "price_history", "args": {"symbol": "NVDA", "range": "3mo", "interval": "1d"}, "result": {"points": 63, "latest_close": 974.50, "change_pct": 2.8, "vol_avg": 42_000_000}, "duration_ms": 423},
            {"tool": "price_history", "args": {"symbol": "NVDA", "range": "7d", "interval": "1h"}, "result": {"points": 56, "breakout_confirmed": True, "support_level": 948.0}, "duration_ms": 391},
            {"tool": "get_fundamentals", "args": {"symbol": "NVDA"}, "result": {"pe": 68.2, "revenue_growth_yoy": 1.22, "gross_margin": 0.748, "market_cap": "2.4T"}, "duration_ms": 544},
            {"tool": "calculate_signals", "args": {"symbol": "NVDA", "signals": ["rsi_14", "macd", "bb_squeeze", "vol_breakout"]}, "result": {"rsi_14": 62.4, "macd_cross": "bullish", "bb_squeeze": False, "vol_breakout": True, "signal": "BUY"}, "duration_ms": 287},
            {"tool": "run_backtest", "args": {"symbol": "NVDA", "strategy": "momentum_breakout", "lookback_days": 90, "entry": "vol_breakout", "exit": "trailing_stop_5pct"}, "result": {"total_return": 0.214, "sharpe": 1.87, "max_drawdown": -0.082, "win_rate": 0.64, "trades": 11}, "duration_ms": 1240},
        ],
    },
    {
        "title": "SPY put spread hedge for earnings season",
        "prompt": "I want to hedge my portfolio through earnings season. Analyze the risk/reward on a SPY 520/510 put spread for next month expiry.",
        "agent": "claude-sonnet-4-6",
        "offset_hours": 4,
        "state": "done",
        "steps": [
            {"tool": "price_history", "args": {"symbol": "SPY", "range": "1mo", "interval": "1d"}, "result": {"points": 21, "latest_close": 531.20, "vix_context": "VIX at 14.2 — complacency"}, "duration_ms": 401},
            {"tool": "market_news", "args": {"ticker": "SPY", "limit": 5}, "result": {"headlines": ["Fed minutes signal 2 cuts in 2026", "S&P 500 earnings beat rate at 73%", "Sector rotation into defensives observed"], "count": 5}, "duration_ms": 622},
            {"tool": "calculate_signals", "args": {"symbol": "SPY", "signals": ["iv_rank", "put_call_ratio", "skew_30d"]}, "result": {"iv_rank": 22.1, "put_call_ratio": 0.74, "skew_30d": -0.08, "regime": "low_vol_bullish"}, "duration_ms": 318},
            {"tool": "run_backtest", "args": {"symbol": "SPY", "strategy": "put_spread_hedge", "spread": "520/510", "days_to_expiry": 30, "scenarios": ["flat", "up_3pct", "down_5pct", "down_10pct"]}, "result": {"max_profit": 0.0, "max_loss": -245, "breakeven": 517.55, "down_5pct_pnl": 310, "down_10pct_pnl": 755, "cost": 245}, "duration_ms": 934},
        ],
    },
    {
        "title": "AAPL vs MSFT — which is better AI infrastructure play?",
        "prompt": "Compare AAPL and MSFT as AI infrastructure investments. Which has more upside over 12 months? Build me a relative value thesis.",
        "agent": "claude-sonnet-4-6",
        "offset_hours": 12,
        "state": "done",
        "steps": [
            {"tool": "get_fundamentals", "args": {"symbol": "AAPL"}, "result": {"pe": 32.1, "revenue_growth_yoy": 0.06, "gross_margin": 0.461, "market_cap": "3.2T", "fcf_yield": 0.031}, "duration_ms": 521},
            {"tool": "get_fundamentals", "args": {"symbol": "MSFT"}, "result": {"pe": 36.8, "revenue_growth_yoy": 0.17, "gross_margin": 0.697, "market_cap": "3.4T", "fcf_yield": 0.026, "azure_growth": 0.31}, "duration_ms": 488},
            {"tool": "price_history", "args": {"symbol": "AAPL", "range": "6mo", "interval": "1d"}, "result": {"points": 126, "latest_close": 213.40, "beta": 1.21, "change_6mo": 0.083}, "duration_ms": 412},
            {"tool": "price_history", "args": {"symbol": "MSFT", "range": "6mo", "interval": "1d"}, "result": {"points": 126, "latest_close": 441.80, "beta": 0.89, "change_6mo": 0.194}, "duration_ms": 399},
            {"tool": "market_news", "args": {"ticker": "MSFT", "limit": 8}, "result": {"headlines": ["Azure AI revenue accelerating Q3", "Copilot seats hit 300M", "MSFT increases dividend 10%"], "count": 8}, "duration_ms": 710},
            {"tool": "market_news", "args": {"ticker": "AAPL", "limit": 8}, "result": {"headlines": ["Apple Intelligence drives upgrade cycle", "India iPhone sales up 32% YoY", "Services revenue record $26B"], "count": 8}, "duration_ms": 688},
            {"tool": "calculate_signals", "args": {"symbols": ["AAPL", "MSFT"], "signals": ["relative_strength_52w", "earnings_revision_trend", "analyst_consensus"]}, "result": {"AAPL": {"rs_52w": 0.84, "revision_trend": "flat", "consensus": "buy", "upside_to_target": 0.11}, "MSFT": {"rs_52w": 1.12, "revision_trend": "up", "consensus": "strong_buy", "upside_to_target": 0.18}}, "duration_ms": 392},
        ],
    },
    {
        "title": "MNQ overnight gap fade — does it have real edge?",
        "prompt": "Test the overnight gap fade on MNQ. If MNQ gaps up >0.3% at open, does shorting the open and covering at 10:30am ET have positive expectancy?",
        "agent": "claude-sonnet-4-6",
        "offset_hours": 24,
        "state": "done",
        "steps": [
            {"tool": "price_history", "args": {"symbol": "MNQ=F", "range": "1y", "interval": "1d"}, "result": {"points": 252, "gap_up_days": 47, "gap_down_days": 39, "avg_gap_size": 0.0041}, "duration_ms": 544},
            {"tool": "run_backtest", "args": {"symbol": "MNQ", "strategy": "overnight_gap_fade", "gap_threshold": 0.003, "entry": "open", "exit": "1030am_et", "lookback_days": 252}, "result": {"trades": 47, "win_rate": 0.617, "avg_win": 18.4, "avg_loss": -11.2, "total_pnl": 312.8, "sharpe": 1.44, "max_drawdown": -89.4, "expectancy_per_trade": 6.65}, "duration_ms": 1820},
            {"tool": "run_backtest", "args": {"symbol": "MNQ", "strategy": "overnight_gap_fade", "gap_threshold": 0.005, "entry": "open", "exit": "1030am_et", "lookback_days": 252}, "result": {"trades": 29, "win_rate": 0.655, "avg_win": 22.1, "avg_loss": -14.3, "total_pnl": 214.0, "sharpe": 1.61, "max_drawdown": -57.3, "expectancy_per_trade": 9.40}, "duration_ms": 1640},
            {"tool": "calculate_signals", "args": {"strategy": "overnight_gap_fade", "filter_checks": ["regime_filter", "vix_filter", "day_of_week"]}, "result": {"regime_matters": True, "best_regime": "low_vol", "worst_dow": "Monday", "vix_threshold_optimal": 18.0}, "duration_ms": 441},
        ],
    },
    {
        "title": "TSM earnings play — long IV before print",
        "prompt": "TSM reports in 3 weeks. Analyze whether buying a straddle before the print makes sense given current IV levels and historical move size.",
        "agent": "claude-sonnet-4-6",
        "offset_hours": 36,
        "state": "done",
        "steps": [
            {"tool": "get_fundamentals", "args": {"symbol": "TSM"}, "result": {"pe": 24.8, "revenue_growth_yoy": 0.38, "gross_margin": 0.539, "market_cap": "890B"}, "duration_ms": 512},
            {"tool": "market_news", "args": {"ticker": "TSM", "limit": 10}, "result": {"headlines": ["TSM 3nm yield rates improving", "CoWoS demand outpacing supply by 40%", "Arizona fab on track — TSMC", "AMD, Apple confirm N3P tape-outs"], "count": 10}, "duration_ms": 744},
            {"tool": "calculate_signals", "args": {"symbol": "TSM", "signals": ["iv_rank", "historical_move_4q", "iv_vs_rv"]}, "result": {"iv_rank": 41.2, "avg_4q_move": 0.062, "implied_move": 0.054, "iv_rv_ratio": 1.08, "recommendation": "straddle_attractive"}, "duration_ms": 356},
            {"tool": "run_backtest", "args": {"symbol": "TSM", "strategy": "earnings_straddle", "lookback_quarters": 8, "entry_days_before": 5, "exit": "day_after_earnings"}, "result": {"avg_return": 0.031, "win_rate": 0.625, "best_case": 0.142, "worst_case": -0.054, "sharpe": 1.22}, "duration_ms": 1120},
        ],
    },
    {
        "title": "META — has the Llama moat been underpriced?",
        "prompt": "Make the bull case for META being structurally undervalued on AI. Focus on the open-source moat angle and what it means for compute infrastructure costs.",
        "agent": "claude-sonnet-4-6",
        "offset_hours": 48,
        "state": "done",
        "steps": [
            {"tool": "get_fundamentals", "args": {"symbol": "META"}, "result": {"pe": 28.4, "revenue_growth_yoy": 0.21, "gross_margin": 0.812, "market_cap": "1.6T", "fcf_yield": 0.038, "dau": "3.3B"}, "duration_ms": 498},
            {"tool": "price_history", "args": {"symbol": "META", "range": "1y", "interval": "1w"}, "result": {"points": 52, "latest_close": 596.80, "change_1y": 0.42, "52w_low": 414.50}, "duration_ms": 467},
            {"tool": "market_news", "args": {"ticker": "META", "limit": 10}, "result": {"headlines": ["Llama 4 adoption by enterprise at record pace", "Meta AI reaches 1B monthly users", "AI compute ROI turning positive — Zuckerberg", "Threads DAU surpasses 200M"], "count": 10}, "duration_ms": 688},
            {"tool": "calculate_signals", "args": {"symbol": "META", "signals": ["peg_ratio", "ev_fcf", "rule_of_40"]}, "result": {"peg_ratio": 1.35, "ev_fcf": 26.2, "rule_of_40": 59.1, "relative_value": "cheap_vs_peers"}, "duration_ms": 328},
            {"tool": "run_backtest", "args": {"symbol": "META", "strategy": "buy_and_hold_12m", "entry": "current", "target_return": 0.25, "scenarios": ["base", "bull", "bear"]}, "result": {"base_12m": 0.22, "bull_12m": 0.41, "bear_12m": -0.12, "risk_reward": 1.83}, "duration_ms": 889},
        ],
    },
    {
        "title": "QQQ weekly iron condor — income strategy scan",
        "prompt": "I want to sell a weekly QQQ iron condor every Monday. Model the expected P&L profile and optimal wing placement based on current vol regime.",
        "agent": "claude-sonnet-4-6",
        "offset_hours": 72,
        "state": "done",
        "steps": [
            {"tool": "calculate_signals", "args": {"symbol": "QQQ", "signals": ["iv_rank", "vix", "atm_iv_weekly", "skew"]}, "result": {"iv_rank": 28.4, "vix": 14.2, "atm_iv_weekly": 0.0148, "skew": -0.06, "optimal_wing": "2sd"}, "duration_ms": 344},
            {"tool": "price_history", "args": {"symbol": "QQQ", "range": "3mo", "interval": "1w"}, "result": {"points": 13, "latest_close": 487.20, "weekly_move_avg": 0.0121, "weekly_move_p90": 0.0282}, "duration_ms": 388},
            {"tool": "run_backtest", "args": {"symbol": "QQQ", "strategy": "weekly_iron_condor", "wing_sd": 2.0, "lookback_weeks": 52, "management_rule": "50pct_profit_or_21dte"}, "result": {"trades": 52, "win_rate": 0.788, "avg_credit": 112, "avg_profit": 66, "max_loss": -388, "annual_return": 0.31, "sharpe": 1.54}, "duration_ms": 1880},
            {"tool": "run_backtest", "args": {"symbol": "QQQ", "strategy": "weekly_iron_condor", "wing_sd": 1.5, "lookback_weeks": 52, "management_rule": "50pct_profit_or_21dte"}, "result": {"trades": 52, "win_rate": 0.711, "avg_credit": 187, "avg_profit": 84, "max_loss": -613, "annual_return": 0.39, "sharpe": 1.38}, "duration_ms": 1740},
        ],
    },
    {
        "title": "SMCI short thesis — conviction check",
        "prompt": "SMCI has had accounting issues and the stock is still 3x from lows. Build me a short thesis with clear invalidation levels.",
        "agent": "claude-sonnet-4-6",
        "offset_hours": 96,
        "state": "error",
        "steps": [
            {"tool": "get_fundamentals", "args": {"symbol": "SMCI"}, "result": {"pe": None, "revenue_growth_yoy": 0.61, "gross_margin": 0.148, "market_cap": "22B", "audit_risk": "HIGH — delayed 10-K filing"}, "duration_ms": 533},
            {"tool": "market_news", "args": {"ticker": "SMCI", "limit": 15}, "result": {"headlines": ["SMCI delays annual report again", "Hindenburg Research maintains short", "SMCI CFO departure raises governance flags", "New auditor yet to sign off"], "count": 15}, "duration_ms": 799},
            {"tool": "price_history", "args": {"symbol": "SMCI", "range": "6mo", "interval": "1d"}, "result": {"points": 126, "latest_close": 48.20, "52w_high": 122.90, "short_interest": 0.142}, "duration_ms": 445},
            {"tool": "calculate_signals", "args": {"symbol": "SMCI", "signals": ["short_interest", "borrow_rate", "put_call_ratio", "insider_selling"]}, "result": "ERROR: options data unavailable for this symbol — borrow rate data stale", "duration_ms": 88, "error": True},
        ],
    },
    {
        "title": "Sector rotation — where does money flow post-rate-cut?",
        "prompt": "Model where capital flows when the Fed cuts 25bps. Which sectors outperform in the 90 days post first-cut historically?",
        "agent": "claude-sonnet-4-6",
        "offset_hours": 120,
        "state": "done",
        "steps": [
            {"tool": "price_history", "args": {"symbols": ["XLF", "XLU", "XLI", "XLK", "XLRE", "XLV"], "range": "5y", "interval": "1mo"}, "result": {"data_points": 360, "note": "Post-cut 90d returns loaded for 2019-07, 2020-03, 2024-09"}, "duration_ms": 891},
            {"tool": "run_backtest", "args": {"strategy": "sector_rotation_post_cut", "lookback_cuts": 3, "window_days": 90}, "result": {"XLRE": 0.148, "XLU": 0.112, "XLF": 0.097, "XLV": 0.088, "XLI": 0.071, "XLK": 0.051, "best_sector": "XLRE", "worst_sector": "XLK"}, "duration_ms": 1340},
            {"tool": "market_news", "args": {"ticker": "XLRE", "limit": 8}, "result": {"headlines": ["REIT sector at multi-year relative low vs S&P", "Cap rates compressing on rate cut expectations", "Apartment REITs beat estimates for 3rd consecutive quarter"], "count": 8}, "duration_ms": 656},
            {"tool": "calculate_signals", "args": {"symbols": ["XLRE", "XLU"], "signals": ["relative_value", "dividend_yield", "rate_sensitivity"]}, "result": {"XLRE": {"div_yield": 0.038, "rate_beta": -1.42, "upside_if_25bps": 0.08}, "XLU": {"div_yield": 0.031, "rate_beta": -1.18, "upside_if_25bps": 0.06}}, "duration_ms": 377},
        ],
    },
    {
        "title": "GOOGL vs meta — which has better AI ad monetization runway?",
        "prompt": "Deep dive on AI-enhanced ad monetization at GOOGL vs META. Model the incremental ARPU uplift from AI features over next 2 years.",
        "agent": "claude-sonnet-4-6",
        "offset_hours": 168,
        "state": "done",
        "steps": [
            {"tool": "get_fundamentals", "args": {"symbol": "GOOGL"}, "result": {"pe": 22.4, "ad_revenue": "238B", "youtube_rev": "36B", "cloud_rev": "42B", "market_cap": "2.1T"}, "duration_ms": 504},
            {"tool": "get_fundamentals", "args": {"symbol": "META"}, "result": {"pe": 28.4, "ad_revenue": "161B", "reality_labs_loss": "-5B", "market_cap": "1.6T"}, "duration_ms": 491},
            {"tool": "market_news", "args": {"ticker": "GOOGL", "limit": 8}, "result": {"headlines": ["Search AI Overviews monetizing at parity with text ads", "Google Performance Max ROAS up 18%", "YouTube Shorts monetization gap closing fast"], "count": 8}, "duration_ms": 712},
            {"tool": "market_news", "args": {"ticker": "META", "limit": 8}, "result": {"headlines": ["Meta Advantage+ ROAS beats campaign manager 31%", "AI ad creative tools adopted by 4M advertisers", "Threads ads beta showing 2.4x brand recall"], "count": 8}, "duration_ms": 698},
            {"tool": "calculate_signals", "args": {"symbols": ["GOOGL", "META"], "signals": ["arpu_growth", "ai_rev_contribution_est", "peg_forward"]}, "result": {"GOOGL": {"arpu_growth_est_2y": 0.14, "ai_contribution": "15%", "peg_fwd": 1.21}, "META": {"arpu_growth_est_2y": 0.22, "ai_contribution": "28%", "peg_fwd": 1.35}}, "duration_ms": 401},
            {"tool": "run_backtest", "args": {"symbols": ["GOOGL", "META"], "strategy": "12m_dcf_fair_value", "ai_uplift_scenario": True}, "result": {"GOOGL_fair_value": 204.0, "GOOGL_current": 178.60, "GOOGL_upside": 0.143, "META_fair_value": 714.0, "META_current": 596.80, "META_upside": 0.197, "winner": "META"}, "duration_ms": 1560},
        ],
    },
]

# ── Strategies ─────────────────────────────────────────────────────────────────

STRATEGIES = [
    {
        "strategy_id": new_id(),
        "name": "MNQ Overnight Gap Fade",
        "spec": {"kind": "intraday", "asset": "MNQ", "entry": "gap_up_gt_30bps_at_open", "exit": "1030am_et", "sizing": "1_contract", "filter": "vix_lt_20"},
    },
    {
        "strategy_id": new_id(),
        "name": "QQQ Weekly Iron Condor",
        "spec": {"kind": "options_income", "asset": "QQQ", "structure": "iron_condor", "wing_width": "2sd", "entry": "monday_open", "exit": "friday_close_or_50pct_profit", "management": "roll_at_21dte"},
    },
    {
        "strategy_id": new_id(),
        "name": "NVDA Momentum Breakout",
        "spec": {"kind": "swing", "asset": "NVDA", "signal": "vol_breakout_with_trend", "entry": "next_open", "stop": "trailing_5pct", "target": "risk_reward_2to1"},
    },
    {
        "strategy_id": new_id(),
        "name": "XLRE Rate-Cut Rotation",
        "spec": {"kind": "macro_rotation", "asset": "XLRE", "trigger": "fed_cut_signal", "hold_days": 90, "sizing": "5pct_of_portfolio"},
    },
]

# ── Orders + Fills ─────────────────────────────────────────────────────────────

ORDER_FILLS = [
    {"symbol": "MNQ", "side": "SELL", "qty": 1, "price": 21_482.50, "broker": "paper", "offset_h": 1},
    {"symbol": "MNQ", "side": "BUY",  "qty": 1, "price": 21_441.25, "broker": "paper", "offset_h": 1.5},
    {"symbol": "MNQ", "side": "SELL", "qty": 1, "price": 21_618.75, "broker": "paper", "offset_h": 25},
    {"symbol": "MNQ", "side": "BUY",  "qty": 1, "price": 21_574.00, "broker": "paper", "offset_h": 25.5},
    {"symbol": "MNQ", "side": "SELL", "qty": 1, "price": 21_903.25, "broker": "paper", "offset_h": 49},
    {"symbol": "MNQ", "side": "BUY",  "qty": 1, "price": 21_891.50, "broker": "paper", "offset_h": 49.5},
    {"symbol": "NVDA", "side": "BUY",  "qty": 10, "price": 962.40, "broker": "paper", "offset_h": 3},
    {"symbol": "NVDA", "side": "SELL", "qty": 10, "price": 994.80, "broker": "paper", "offset_h": 27},
    {"symbol": "QQQ",  "side": "SELL", "qty": 2,  "price": 487.80, "broker": "paper", "offset_h": 8, "note": "iron_condor_short_call"},
    {"symbol": "QQQ",  "side": "BUY",  "qty": 2,  "price": 489.40, "broker": "paper", "offset_h": 8, "note": "iron_condor_long_call"},
    {"symbol": "QQQ",  "side": "SELL", "qty": 2,  "price": 484.20, "broker": "paper", "offset_h": 8, "note": "iron_condor_short_put"},
    {"symbol": "QQQ",  "side": "BUY",  "qty": 2,  "price": 482.60, "broker": "paper", "offset_h": 8, "note": "iron_condor_long_put"},
    {"symbol": "XLRE", "side": "BUY",  "qty": 50, "price": 41.82,  "broker": "paper", "offset_h": 73},
    {"symbol": "META", "side": "BUY",  "qty": 5,  "price": 591.20,  "broker": "paper", "offset_h": 50},
    {"symbol": "TSM",  "side": "BUY",  "qty": 8,  "price": 184.40,  "broker": "paper", "offset_h": 37},
]

# ── Seed ──────────────────────────────────────────────────────────────────────

def seed(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Tenant
    c.execute("INSERT OR IGNORE INTO tenants (id, name, created_at) VALUES (?, ?, ?)",
              (TENANT_ID, "Joshua Jerin", ts(200)))

    # User
    c.execute("""
        INSERT OR IGNORE INTO users (id, email, name, tenant_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (USER_ID, EMAIL, "Joshua Jerin", TENANT_ID, ts(200), ts(0)))

    inserted_runs = 0
    inserted_events = 0
    inserted_strategies = 0
    inserted_fills = 0

    # Sessions
    for sess in SESSIONS:
        run_id = new_id()
        state = sess["state"]
        created = ts(sess["offset_hours"] + 0.1)
        updated = ts(sess["offset_hours"])

        c.execute("""
            INSERT OR IGNORE INTO runs (tenant_id, run_id, kind, state, version, spec, result, created_at, updated_at)
            VALUES (?, ?, 'research', ?, 1, ?, NULL, ?, ?)
        """, (TENANT_ID, run_id, state, json.dumps({"title": sess["title"]}), created, updated))
        inserted_runs += 1

        # session_open event
        seq = 1
        open_ts = ts(sess["offset_hours"] + 0.08)
        c.execute("""
            INSERT OR IGNORE INTO trace_events
            (tenant_id, run_id, seq, ts, type, session_id, origin_session_id, actor, data)
            VALUES (?, ?, ?, ?, 'session_open', ?, ?, ?, ?)
        """, (TENANT_ID, run_id, seq, open_ts, run_id, run_id,
              json.dumps({"kind": "user", "id": "ui"}),
              json.dumps({"title": sess["title"], "prompt": sess["prompt"], "createdBy": "web"})))
        seq += 1
        inserted_events += 1

        # tool_call events
        for step in sess["steps"]:
            step_ts = ts(sess["offset_hours"] + 0.07 - (seq * 0.002))
            event_type = "error" if step.get("error") else "tool_call"
            data: dict = {
                "tool": step["tool"],
                "args": step["args"],
                "result": step["result"],
                "duration_ms": step.get("duration_ms", 500),
            }
            c.execute("""
                INSERT OR IGNORE INTO trace_events
                (tenant_id, run_id, seq, ts, type, session_id, origin_session_id, actor, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (TENANT_ID, run_id, seq, step_ts, event_type, run_id, run_id,
                  json.dumps({"kind": "agent", "id": sess["agent"]}),
                  json.dumps(data)))
            seq += 1
            inserted_events += 1

        # session_close event
        close_ts = ts(sess["offset_hours"])
        c.execute("""
            INSERT OR IGNORE INTO trace_events
            (tenant_id, run_id, seq, ts, type, session_id, origin_session_id, actor, data)
            VALUES (?, ?, ?, ?, 'session_close', ?, ?, ?, ?)
        """, (TENANT_ID, run_id, seq, close_ts, run_id, run_id,
              json.dumps({"kind": "system", "id": "runtime"}),
              json.dumps({"state": state})))
        inserted_events += 1

    # Strategies
    for strat in STRATEGIES:
        c.execute("""
            INSERT OR IGNORE INTO strategies (tenant_id, strategy_id, name, version, spec, created_at)
            VALUES (?, ?, ?, 1, ?, ?)
        """, (TENANT_ID, strat["strategy_id"], strat["name"], json.dumps(strat["spec"]), ts(96)))
        inserted_strategies += 1

    # Orders + Fills
    for fill_data in ORDER_FILLS:
        order_id = new_id()
        fill_id = new_id()
        intent_id = new_id()
        client_order_id = f"dev-{order_id[:8]}"
        event_time = ts(fill_data["offset_h"])
        payload = {
            "symbol": fill_data["symbol"],
            "side": fill_data["side"],
            "qty": fill_data["qty"],
            "price": fill_data["price"],
            "broker": fill_data["broker"],
        }
        if "note" in fill_data:
            payload["note"] = fill_data["note"]

        c.execute("""
            INSERT OR IGNORE INTO orders
            (tenant_id, order_id, intent_id, broker, client_order_id, state, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'filled', ?, ?, ?)
        """, (TENANT_ID, order_id, intent_id, fill_data["broker"], client_order_id,
              json.dumps(payload), event_time, event_time))

        c.execute("""
            INSERT OR IGNORE INTO fills
            (tenant_id, fill_id, order_id, payload, event_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (TENANT_ID, fill_id, order_id, json.dumps(payload), event_time, event_time))
        inserted_fills += 1

    conn.commit()
    conn.close()

    print(f"Seeded {DB_PATH}:")
    print(f"  {inserted_runs} sessions")
    print(f"  {inserted_events} trace events")
    print(f"  {inserted_strategies} strategies")
    print(f"  {inserted_fills} fills/orders")


if __name__ == "__main__":
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    seed(DB_PATH)
