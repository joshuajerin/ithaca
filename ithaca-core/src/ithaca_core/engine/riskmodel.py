"""Barra-style cross-sectional multi-factor risk model (pure numpy).

Given a panel of aligned daily returns (T days x N assets) and a matrix of
static factor exposures (N assets x K factors), estimate factor returns via a
daily cross-sectional regression, then build the annualized factor covariance
matrix and per-asset specific (idiosyncratic) risk. A portfolio's risk is then
decomposed into factor vs specific variance, with the marginal contribution to
risk of each holding and the variance contribution of each factor.

Pure and deterministic: no DB / network access. Callers are responsible for
sourcing the aligned returns, building the descriptors, and deciding the
live/mock provenance. This mirrors the rest of ``app.engine``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

TRADING_DAYS = 252


@dataclass
class FactorModel:
    """Estimated factor model over an aligned panel of assets."""

    factor_names: List[str]
    symbols: List[str]
    exposures: np.ndarray  # (N, K) static factor exposures
    factor_returns: np.ndarray  # (T, K) daily estimated factor returns
    factor_cov: np.ndarray  # (K, K) annualized factor covariance
    specific_var: np.ndarray  # (N,) annualized idiosyncratic variance
    r2: float  # mean daily cross-sectional R^2
    n_days: int


@dataclass
class PortfolioRisk:
    """Decomposition of a portfolio's predicted risk (all annualized)."""

    total_vol: float
    factor_vol: float
    specific_vol: float
    factor_var_pct: float  # % of total variance from common factors
    specific_var_pct: float  # % of total variance idiosyncratic
    factor_exposures: np.ndarray  # (K,) portfolio factor exposures b = X' w
    factor_var_contrib: np.ndarray  # (K,) % of total variance per factor
    factor_vol_contrib: np.ndarray  # (K,) vol-units contribution per factor
    mctr: np.ndarray  # (n,) marginal contribution to risk per holding
    risk_contrib: np.ndarray  # (n,) w_i * mctr_i (sums to total_vol)
    pct_contrib: np.ndarray  # (n,) % of total risk per holding
    diversification_ratio: float


def standardize(x: np.ndarray) -> Tuple[np.ndarray, float, float]:
    """Cross-sectional z-score of a 1-D descriptor, ignoring non-finite values.

    Returns ``(z, mean, std)``. Non-finite entries map to 0 (the cross-sectional
    mean), i.e. a name missing a *single* descriptor is treated as neutral on
    that factor; callers exclude names missing *required* descriptors before
    this point. Z-scores are winsorized at +/- 3 to tame outliers.
    """
    x = np.asarray(x, dtype=float)
    mask = np.isfinite(x)
    if not mask.any():
        return np.zeros_like(x), 0.0, 0.0
    mu = float(x[mask].mean())
    sd = float(x[mask].std(ddof=0))
    z = np.zeros_like(x) if sd == 0 else (x - mu) / sd
    z = np.where(mask, z, 0.0)
    z = np.clip(z, -3.0, 3.0)
    return z, mu, sd


def estimate_factor_returns(
    returns: np.ndarray, exposures: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, float]:
    """Daily cross-sectional OLS ``r_t = X f_t + e_t`` for every day t.

    ``returns`` is (T, N) daily asset returns and ``exposures`` is (N, K) static
    factor exposures. Returns ``(factor_returns (T, K), residuals (T, N),
    mean_r2)``. Because X is constant across days, the OLS hat matrix is computed
    once and applied to all days at once.
    """
    returns = np.asarray(returns, dtype=float)
    X = np.asarray(exposures, dtype=float)
    # (K, N) hat matrix; pinv keeps it stable if columns are near-collinear.
    hat = np.linalg.pinv(X.T @ X) @ X.T
    factor_returns = returns @ hat.T  # (T, K): row t is f_t = hat @ r_t
    fitted = factor_returns @ X.T  # (T, N)
    resid = returns - fitted
    ss_res = (resid ** 2).sum(axis=1)
    ss_tot = ((returns - returns.mean(axis=1, keepdims=True)) ** 2).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r2_t = np.where(ss_tot > 0, 1.0 - ss_res / ss_tot, 0.0)
    mean_r2 = float(np.clip(r2_t, -1.0, 1.0).mean()) if r2_t.size else 0.0
    return factor_returns, resid, mean_r2


def build_model(
    returns: np.ndarray,
    exposures: np.ndarray,
    factor_names: List[str],
    symbols: List[str],
) -> FactorModel:
    """Estimate factor returns, annualized factor covariance and specific risk."""
    returns = np.asarray(returns, dtype=float)
    exposures = np.asarray(exposures, dtype=float)
    if returns.ndim != 2 or returns.shape[0] < 2:
        raise ValueError("need at least 2 days of returns to estimate the model")
    if exposures.shape[0] != returns.shape[1]:
        raise ValueError("exposures rows must match the number of assets")

    factor_returns, resid, r2 = estimate_factor_returns(returns, exposures)
    factor_cov = np.atleast_2d(np.cov(factor_returns, rowvar=False)) * TRADING_DAYS
    specific_var = resid.var(axis=0, ddof=1) * TRADING_DAYS
    # Floor specific variance so a degenerate (perfectly-fit) name still carries
    # a tiny idiosyncratic risk rather than zero.
    specific_var = np.maximum(specific_var, 1e-8)
    return FactorModel(
        factor_names=list(factor_names),
        symbols=list(symbols),
        exposures=exposures,
        factor_returns=factor_returns,
        factor_cov=factor_cov,
        specific_var=specific_var,
        r2=r2,
        n_days=int(returns.shape[0]),
    )


def covariance(model: FactorModel, idx: List[int]) -> np.ndarray:
    """Annualized asset covariance ``X F X' + diag(specific)`` for a subset."""
    Xp = model.exposures[idx]
    Dp = model.specific_var[idx]
    return Xp @ model.factor_cov @ Xp.T + np.diag(Dp)


def decompose_portfolio(
    model: FactorModel, idx: List[int], weights: np.ndarray
) -> PortfolioRisk:
    """Decompose a portfolio's predicted risk into factor and specific parts.

    ``idx`` selects the holdings' rows in the model; ``weights`` are the
    (already normalized) portfolio weights aligned to ``idx``. Identities held by
    construction: ``sum(risk_contrib) == total_vol`` and
    ``factor_var + specific_var == total_var``.
    """
    w = np.asarray(weights, dtype=float)
    Xp = model.exposures[idx]  # (n, K)
    Dp = model.specific_var[idx]  # (n,)
    Fcov = model.factor_cov  # (K, K)
    cov = Xp @ Fcov @ Xp.T + np.diag(Dp)  # (n, n) annualized

    port_var = max(float(w @ cov @ w), 1e-12)
    total_vol = float(np.sqrt(port_var))

    b = Xp.T @ w  # (K,) portfolio factor exposures
    factor_var = float(b @ Fcov @ b)
    specific_var = float((w ** 2) @ Dp)
    factor_vol = float(np.sqrt(max(factor_var, 0.0)))
    specific_vol = float(np.sqrt(max(specific_var, 0.0)))

    # Marginal contribution to risk: d(sigma_p)/d(w_i) = (cov w)_i / sigma_p.
    mctr = (cov @ w) / total_vol  # (n,)
    risk_contrib = w * mctr  # sums to total_vol
    pct_contrib = risk_contrib / total_vol * 100.0

    # Per-factor variance contribution: (F b)_k * b_k sums to factor_var.
    fc_var = (Fcov @ b) * b  # (K,)
    factor_var_contrib = fc_var / port_var * 100.0  # % of total variance
    factor_vol_contrib = fc_var / total_vol  # vol-units (sum to factor_var/vol)

    standalone = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    wavg_vol = float(np.abs(w) @ standalone)
    diversification_ratio = wavg_vol / total_vol if total_vol > 0 else 1.0

    return PortfolioRisk(
        total_vol=total_vol,
        factor_vol=factor_vol,
        specific_vol=specific_vol,
        factor_var_pct=factor_var / port_var * 100.0,
        specific_var_pct=specific_var / port_var * 100.0,
        factor_exposures=b,
        factor_var_contrib=factor_var_contrib,
        factor_vol_contrib=factor_vol_contrib,
        mctr=mctr,
        risk_contrib=risk_contrib,
        pct_contrib=pct_contrib,
        diversification_ratio=diversification_ratio,
    )


def pca_variance(returns: np.ndarray, k: int = 5) -> List[float]:
    """Fraction of total variance explained by the top-k principal components.

    These are the statistical (PCA) factors of the asset return covariance — a
    model-free cross-check on how much common structure the named factors should
    be capturing. Returns a descending list of explained-variance ratios.
    """
    returns = np.asarray(returns, dtype=float)
    if returns.ndim != 2 or returns.shape[0] < 2 or returns.shape[1] < 1:
        return []
    cov = np.atleast_2d(np.cov(returns, rowvar=False))
    eigvals = np.clip(np.linalg.eigvalsh(cov)[::-1], 0.0, None)  # descending
    total = float(eigvals.sum())
    if total <= 0:
        return []
    k = max(1, min(k, eigvals.size))
    return [float(eigvals[i] / total) for i in range(k)]
