"""Backtesting & simulation engine.

A small, deterministic, numpy-based engine that runs configurable trading
strategies against real OHLCV history (or any equivalent close series), computes
real performance/risk statistics, and projects forward Monte Carlo return paths.

It is intentionally pure (no DB / network access) so it can be unit-tested in
isolation: callers (the skill builders) are responsible for sourcing the price
points and for the live/mock fallback decision.
"""
from __future__ import annotations

from . import riskmodel
from .backtest import run_backtest
from .montecarlo import monte_carlo
from .riskmodel import (
    FactorModel,
    PortfolioRisk,
    build_model,
    decompose_portfolio,
    pca_variance,
)
from .scenario import combine_returns, project_scenario
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

__all__ = [
    "run_backtest",
    "monte_carlo",
    "performance_stats",
    "cagr",
    "sharpe",
    "sortino",
    "max_drawdown",
    "var_historical",
    "cvar_historical",
    "STRATEGIES",
    "available_strategies",
    "normalize_strategy",
    "riskmodel",
    "FactorModel",
    "PortfolioRisk",
    "build_model",
    "decompose_portfolio",
    "pca_variance",
]
