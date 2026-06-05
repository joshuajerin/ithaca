"""Backtesting & simulation engine.

A small, deterministic, numpy-based engine that runs configurable trading
strategies against real OHLCV history (or any equivalent close series), computes
real performance/risk statistics, and projects forward Monte Carlo return paths.

It is intentionally pure (no DB / network access) so it can be unit-tested in
isolation: callers (the skill builders) are responsible for sourcing the price
points and for the live/mock fallback decision.
"""
from __future__ import annotations

from . import attribution, execution, optimize, paperbook, riskmodel
from .attribution import (
    active_stats,
    align_benchmark_returns,
    book_returns,
    brinson,
    factor_attribution,
    pnl_summary,
    return_stats,
)
from .backtest import run_backtest
from .execution import (
    aggregate_tca,
    daily_vol_from_closes,
    generate_orders,
    simulate_all,
    square_root_impact,
)
from .montecarlo import monte_carlo
from .optimize import (
    Constraints,
    OptResult,
    apply_long_only_constraints,
    black_litterman,
    hrp,
    implied_risk_aversion,
    mean_variance,
    portfolio_stats,
    risk_contributions,
    risk_parity,
)
from .riskmodel import (
    FactorModel,
    PortfolioRisk,
    build_model,
    decompose_portfolio,
    pca_variance,
)
from .scenario import combine_returns, project_scenario
from .stress import asset_shock_pnl, factor_shock_pnl, replay_window
from .stats import (
    cagr,
    cvar_historical,
    max_drawdown,
    performance_stats,
    sharpe,
    sortino,
    var_historical,
)
from .strategies import STRATEGIES, available_strategies, normalize_strategy
from .signals import (
    SIGNAL_META,
    SIGNALS,
    available_signals,
    evaluate_signal,
    normalize_signal,
    signal_label,
    spearman_ic,
)

__all__ = [
    "attribution",
    "active_stats",
    "book_returns",
    "brinson",
    "factor_attribution",
    "pnl_summary",
    "return_stats",
    "run_backtest",
    "monte_carlo",
    "performance_stats",
    "cagr",
    "sharpe",
    "sortino",
    "max_drawdown",
    "var_historical",
    "cvar_historical",
    "combine_returns",
    "project_scenario",
    "factor_shock_pnl",
    "asset_shock_pnl",
    "replay_window",
    "STRATEGIES",
    "available_strategies",
    "normalize_strategy",
    "riskmodel",
    "FactorModel",
    "PortfolioRisk",
    "build_model",
    "decompose_portfolio",
    "pca_variance",
    "SIGNALS",
    "SIGNAL_META",
    "available_signals",
    "evaluate_signal",
    "normalize_signal",
    "signal_label",
    "spearman_ic",
    "execution",
    "paperbook",
    "generate_orders",
    "simulate_all",
    "square_root_impact",
    "daily_vol_from_closes",
    "aggregate_tca",
]
