"""Pure-math helpers for the COMPUTED skills (no archive, no network).

Everything here is deterministic math on *agent-supplied inputs* or on real archive
series the caller hands in. It uses only ``numpy`` (already a dep) + stdlib ``math`` —
no scipy, no new dependency. The Black-Scholes normal CDF is implemented via
``math.erf`` (ported verbatim from the v1 ``skills.py`` pricer). These functions never
fabricate market data: they price/transform whatever S, K, sigma, returns the caller
provides, so a skill that wraps them is honest "source: computed".
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

__all__ = [
    "norm_cdf", "norm_pdf", "bs_price", "bs_greeks", "bs_implied_vol",
    "realized_vol", "log_returns", "simple_returns", "correlation_matrix",
    "covariance_matrix", "dcf_value",
]

_SQRT2 = math.sqrt(2.0)
_SQRT2PI = math.sqrt(2.0 * math.pi)
TRADING_DAYS = 252


# ----------------------------- Black-Scholes (closed form) -----------------------------
def norm_cdf(x: float) -> float:
    """Standard-normal CDF via the stdlib error function (no scipy)."""
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT2PI


def bs_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> float:
    """Black-Scholes European option price (no dividends).

    Degenerate inputs (T<=0 or sigma<=0) fall back to discounted intrinsic value.
    """
    option_type = (option_type or "call").lower()
    if S <= 0 or K <= 0:
        raise ValueError("S and K must be positive")
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == "call":
        return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def bs_greeks(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> dict:
    """delta, gamma, theta (per day), vega (per 1 vol point), rho for one option."""
    option_type = (option_type or "call").lower()
    if T <= 0 or sigma <= 0:
        delta = (1.0 if S > K else 0.0) if option_type == "call" else (-1.0 if S < K else 0.0)
        return {"delta": delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    pdf = norm_pdf(d1)
    if option_type == "call":
        delta = norm_cdf(d1)
        theta = (-S * pdf * sigma / (2 * sqrtT) - r * K * math.exp(-r * T) * norm_cdf(d2)) / 365.0
        rho = K * T * math.exp(-r * T) * norm_cdf(d2) / 100.0
    else:
        delta = norm_cdf(d1) - 1.0
        theta = (-S * pdf * sigma / (2 * sqrtT) + r * K * math.exp(-r * T) * norm_cdf(-d2)) / 365.0
        rho = -K * T * math.exp(-r * T) * norm_cdf(-d2) / 100.0
    gamma = pdf / (S * sigma * sqrtT)
    vega = S * pdf * sqrtT / 100.0
    return {
        "delta": round(delta, 6), "gamma": round(gamma, 6), "theta": round(theta, 6),
        "vega": round(vega, 6), "rho": round(rho, 6),
    }


def bs_implied_vol(price: float, S: float, K: float, T: float, r: float,
                   option_type: str = "call", lo: float = 1e-4, hi: float = 5.0) -> float | None:
    """Implied volatility by bisection on the (monotone) BS price in sigma.

    Returns None when the target price is outside the arbitrage-free band the model
    can reach (e.g. below intrinsic), so the caller can report it honestly.
    """
    option_type = (option_type or "call").lower()
    if T <= 0 or S <= 0 or K <= 0 or price <= 0:
        return None
    intrinsic = max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)
    if price < intrinsic - 1e-9:
        return None
    p_lo = bs_price(S, K, T, r, lo, option_type)
    p_hi = bs_price(S, K, T, r, hi, option_type)
    if not (p_lo - 1e-9 <= price <= p_hi + 1e-9):
        return None
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        pm = bs_price(S, K, T, r, mid, option_type)
        if abs(pm - price) < 1e-8:
            return round(mid, 6)
        if pm < price:
            lo = mid
        else:
            hi = mid
    return round(0.5 * (lo + hi), 6)


# ----------------------------- return / vol transforms -----------------------------
def simple_returns(closes: Sequence[float]) -> np.ndarray:
    c = np.asarray([x for x in closes if x is not None], dtype=float)
    c = c[np.isfinite(c) & (c > 0)]
    if c.size < 2:
        return np.asarray([], dtype=float)
    return c[1:] / c[:-1] - 1.0


def log_returns(closes: Sequence[float]) -> np.ndarray:
    c = np.asarray([x for x in closes if x is not None], dtype=float)
    c = c[np.isfinite(c) & (c > 0)]
    if c.size < 2:
        return np.asarray([], dtype=float)
    return np.log(c[1:] / c[:-1])


def realized_vol(closes: Sequence[float], annualize: bool = True) -> float | None:
    """Annualized realized (close-to-close, log-return) volatility, always >= 0."""
    r = log_returns(closes)
    if r.size < 2:
        return None
    sd = float(r.std(ddof=1))
    return round(sd * math.sqrt(TRADING_DAYS) if annualize else sd, 6)


def correlation_matrix(series: dict[str, Sequence[float]]) -> tuple[list[str], np.ndarray]:
    """Symmetric Pearson correlation matrix of the per-symbol return series.

    Series are aligned to the common (shortest) tail length. Returns
    ``(symbols, matrix)`` with a 1.0 diagonal; symbols with <2 obs are dropped.
    """
    cleaned = {s: np.asarray(r, dtype=float) for s, r in series.items()}
    cleaned = {s: r[np.isfinite(r)] for s, r in cleaned.items()}
    cleaned = {s: r for s, r in cleaned.items() if r.size >= 2}
    syms = list(cleaned)
    if len(syms) < 2:
        return syms, np.eye(len(syms))
    n = min(cleaned[s].size for s in syms)
    m = np.vstack([cleaned[s][-n:] for s in syms])
    cm = np.corrcoef(m)
    cm = np.atleast_2d(cm)
    np.fill_diagonal(cm, 1.0)
    return syms, cm


def covariance_matrix(series: dict[str, Sequence[float]], annualize: bool = True) -> tuple[list[str], np.ndarray]:
    cleaned = {s: np.asarray(r, dtype=float) for s, r in series.items()}
    cleaned = {s: r[np.isfinite(r)] for s, r in cleaned.items()}
    cleaned = {s: r for s, r in cleaned.items() if r.size >= 2}
    syms = list(cleaned)
    if not syms:
        return syms, np.zeros((0, 0))
    n = min(cleaned[s].size for s in syms)
    m = np.vstack([cleaned[s][-n:] for s in syms])
    cov = np.atleast_2d(np.cov(m))
    if annualize:
        cov = cov * TRADING_DAYS
    return syms, cov


# ----------------------------- DCF (deterministic) -----------------------------
def dcf_value(base_revenue: float, shares: float, net_debt: float, assumptions: dict,
              years: int = 5) -> dict:
    """A 5-year discounted-cash-flow valuation (ported from the v1 ``_run_dcf`` math).

    Every input is supplied (revenue/shares/net_debt from the archive fundamentals,
    assumptions from the agent or derived defaults). Pure arithmetic — no randomness.
    Returns projections, implied price, terminal value and a WACC x exit-multiple grid.
    """
    g = float(assumptions.get("revenueGrowth", 10.0)) / 100.0
    margin = float(assumptions.get("ebitdaMargin", 25.0)) / 100.0
    wacc = float(assumptions.get("wacc", 10.0)) / 100.0
    exit_mult = float(assumptions.get("exitMultiple", 18.0))
    tax = float(assumptions.get("taxRate", 21.0)) / 100.0
    capex_pct = float(assumptions.get("capexPct", 5.0)) / 100.0
    if wacc <= -1.0:
        raise ValueError("wacc must be > -100%")

    projections: list[dict] = []
    rev = float(base_revenue)
    pv_sum = 0.0
    for t in range(1, years + 1):
        rev = rev * (1 + g)
        ebitda = rev * margin
        nopat = ebitda * (1 - tax)
        capex = rev * capex_pct
        fcf = nopat - capex
        pv = fcf / ((1 + wacc) ** t)
        pv_sum += pv
        projections.append({"year": t, "revenue": round(rev, 0), "fcf": round(fcf, 0),
                            "pvFcf": round(pv, 0)})

    fcf_n = projections[-1]["fcf"]
    tv = fcf_n * exit_mult
    pv_tv = tv / ((1 + wacc) ** years)
    enterprise_value = pv_sum + pv_tv
    equity_value = enterprise_value - float(net_debt)
    implied_price = equity_value / shares if shares > 0 else 0.0

    sensitivity: list[dict] = []
    for w_pct in (7.0, 8.5, 10.0, 11.5, 13.0):
        for em in (12.0, 16.0, 20.0, 24.0, 28.0):
            w = w_pct / 100.0
            pv2 = sum(projections[i]["fcf"] / ((1 + w) ** (i + 1)) for i in range(years))
            tv2 = projections[-1]["fcf"] * em / ((1 + w) ** years)
            ev2 = pv2 + tv2 - float(net_debt)
            ip2 = ev2 / shares if shares > 0 else 0.0
            sensitivity.append({"wacc": w_pct, "exitMultiple": em, "impliedPrice": round(ip2, 2)})

    return {
        "projections": projections,
        "terminalValue": round(tv, 0),
        "pvTerminalValue": round(pv_tv, 0),
        "enterpriseValue": round(enterprise_value, 0),
        "equityValue": round(equity_value, 0),
        "impliedPrice": round(implied_price, 2),
        "sensitivity": sensitivity,
    }
