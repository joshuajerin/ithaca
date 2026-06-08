"""Performance & risk statistics computed from a real return series.

All functions take simple (arithmetic) daily returns and/or an equity curve and
return plain Python floats so the results serialize cleanly into panel data.
They are defensive against short/degenerate inputs (return 0.0 rather than NaN).
"""
from __future__ import annotations

import itertools
import math
from typing import Dict, Optional

import numpy as np

TRADING_DAYS = 252

# Euler-Mascheroni constant, used by the expected-maximum-Sharpe estimator.
_EULER_GAMMA = 0.5772156649015329


def _clean(returns: np.ndarray) -> np.ndarray:
    r = np.asarray(returns, dtype=float)
    return r[np.isfinite(r)]


def cagr(equity: np.ndarray) -> float:
    """Compound annual growth rate implied by an equity curve."""
    e = np.asarray(equity, dtype=float)
    if e.size < 2 or e[0] <= 0 or e[-1] <= 0:
        return 0.0
    years = (e.size - 1) / TRADING_DAYS
    if years <= 0:
        return 0.0
    return float((e[-1] / e[0]) ** (1.0 / years) - 1.0)


def total_return(equity: np.ndarray) -> float:
    e = np.asarray(equity, dtype=float)
    if e.size < 2 or e[0] == 0:
        return 0.0
    return float(e[-1] / e[0] - 1.0)


def annualized_vol(returns: np.ndarray) -> float:
    r = _clean(returns)
    if r.size < 2:
        return 0.0
    return float(r.std(ddof=0) * np.sqrt(TRADING_DAYS))


def sharpe(returns: np.ndarray, rf: float = 0.0) -> float:
    """Annualized Sharpe ratio (rf is a per-annum risk-free rate)."""
    r = _clean(returns)
    if r.size < 2:
        return 0.0
    excess = r - rf / TRADING_DAYS
    sd = excess.std(ddof=0)
    if sd <= 0:
        return 0.0
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS))


def sortino(returns: np.ndarray, rf: float = 0.0) -> float:
    """Annualized Sortino ratio (downside deviation in the denominator)."""
    r = _clean(returns)
    if r.size < 2:
        return 0.0
    excess = r - rf / TRADING_DAYS
    downside = excess[excess < 0]
    if downside.size == 0:
        return 0.0
    dd = np.sqrt(np.mean(downside ** 2))
    if dd <= 0:
        return 0.0
    return float(excess.mean() / dd * np.sqrt(TRADING_DAYS))


def max_drawdown(equity: np.ndarray) -> float:
    """Worst peak-to-trough decline as a negative fraction (e.g. -0.23)."""
    e = np.asarray(equity, dtype=float)
    if e.size == 0:
        return 0.0
    peak = np.maximum.accumulate(e)
    safe_peak = np.where(peak == 0, np.nan, peak)
    dd = (e - peak) / safe_peak
    dd = dd[np.isfinite(dd)]
    if dd.size == 0:
        return 0.0
    return float(dd.min())


def win_rate(returns: np.ndarray) -> float:
    """Fraction of active (non-zero) bars that were positive."""
    r = _clean(returns)
    active = r[r != 0]
    if active.size == 0:
        return 0.0
    return float((active > 0).sum() / active.size)


def var_historical(returns: np.ndarray, level: float = 0.95) -> float:
    """Historical Value-at-Risk as a positive loss fraction at `level`."""
    r = _clean(returns)
    if r.size < 2:
        return 0.0
    q = np.percentile(r, (1.0 - level) * 100.0)
    return float(max(0.0, -q))


def cvar_historical(returns: np.ndarray, level: float = 0.95) -> float:
    """Conditional VaR (expected shortfall) as a positive loss fraction."""
    r = _clean(returns)
    if r.size < 2:
        return 0.0
    q = np.percentile(r, (1.0 - level) * 100.0)
    tail = r[r <= q]
    if tail.size == 0:
        return float(max(0.0, -q))
    return float(max(0.0, -tail.mean()))


# --------------------------- distribution helpers ---------------------------
def skewness(returns: np.ndarray) -> float:
    """Sample skewness (Fisher, population-style normalisation)."""
    r = _clean(returns)
    if r.size < 3:
        return 0.0
    sd = r.std(ddof=0)
    if sd <= 0:
        return 0.0
    return float(np.mean(((r - r.mean()) / sd) ** 3))


def kurtosis(returns: np.ndarray) -> float:
    """Pearson kurtosis (normal == 3.0), i.e. NOT excess kurtosis."""
    r = _clean(returns)
    if r.size < 4:
        return 3.0
    sd = r.std(ddof=0)
    if sd <= 0:
        return 3.0
    return float(np.mean(((r - r.mean()) / sd) ** 4))


def sharpe_per_obs(returns: np.ndarray, rf: float = 0.0) -> float:
    """Per-observation (NOT annualised) Sharpe ratio.

    The deflated-Sharpe and multiple-testing machinery is defined in
    per-observation units, so it needs the raw mean/std ratio rather than the
    annualised number reported in the panels."""
    r = _clean(returns)
    if r.size < 2:
        return 0.0
    excess = r - rf / TRADING_DAYS
    sd = excess.std(ddof=0)
    if sd <= 0:
        return 0.0
    return float(excess.mean() / sd)


# --------------------------- standard normal helpers ---------------------------
def _norm_cdf(x: float) -> float:
    """Standard-normal CDF via the error function (no scipy dependency)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation).

    Accurate to ~1e-9 over the open interval (0, 1); clamps the extremes so the
    callers never hit an infinite quantile."""
    if p <= 0.0:
        return -1e10
    if p >= 1.0:
        return 1e10
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)


# --------------------------- overfitting diagnostics ---------------------------
def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """Expected MAXIMUM per-observation Sharpe under the null of `n_trials`
    independent strategies whose Sharpes have cross-sectional variance
    `sr_variance` (Bailey & López de Prado, 2014).

    This is the benchmark a selected strategy must beat to be considered real;
    with a single trial there is no selection bias so it is 0.0."""
    n = max(1, int(n_trials))
    v = max(0.0, float(sr_variance))
    if n <= 1 or v <= 0.0:
        return 0.0
    e = math.e
    term = ((1.0 - _EULER_GAMMA) * _norm_ppf(1.0 - 1.0 / n)
            + _EULER_GAMMA * _norm_ppf(1.0 - 1.0 / (n * e)))
    return math.sqrt(v) * term


def deflated_sharpe(
    sr_hat: float,
    n_obs: int,
    n_trials: int,
    sr_variance: float,
    skew: float = 0.0,
    kurt: float = 3.0,
) -> Dict[str, float]:
    """Deflated Sharpe Ratio (Bailey & López de Prado).

    `sr_hat` is the selected strategy's PER-OBSERVATION Sharpe. Returns the
    probability that the true Sharpe is positive once the selection across
    `n_trials` configurations (and the return distribution's skew/kurtosis) is
    accounted for, alongside the multiple-testing haircut benchmark `sr0`."""
    sr0 = expected_max_sharpe(n_trials, sr_variance)
    out = {
        "sr0": float(sr0),
        "dsr": 0.0,
        "zScore": 0.0,
    }
    t = int(n_obs)
    if t < 2:
        return out
    denom = 1.0 - skew * sr_hat + ((kurt - 1.0) / 4.0) * sr_hat * sr_hat
    if denom <= 0.0:
        return out
    z = (sr_hat - sr0) * math.sqrt(t - 1.0) / math.sqrt(denom)
    out["zScore"] = float(z)
    out["dsr"] = float(_norm_cdf(z))
    return out


def multiple_testing_haircut(
    sr_hat: float,
    n_obs: int,
    n_trials: int,
    sr_variance: float,
) -> Dict[str, float]:
    """Shrink an annualised Sharpe for the number of configurations tried.

    The haircut benchmark is the expected maximum Sharpe under the null
    (`expected_max_sharpe`); the adjusted Sharpe is the excess of the observed
    Sharpe over that benchmark, floored at zero. All Sharpes are annualised for
    display, consistent with the rest of the panel."""
    sr0 = expected_max_sharpe(n_trials, sr_variance)
    ann = math.sqrt(TRADING_DAYS)
    observed = float(sr_hat) * ann
    benchmark = float(sr0) * ann
    haircut = max(0.0, observed - benchmark)
    haircut_pct = 0.0
    if observed > 1e-9:
        haircut_pct = max(0.0, min(100.0, (1.0 - haircut / observed) * 100.0))
    return {
        "observed": round(observed, 3),
        "benchmark": round(benchmark, 3),
        "haircutSharpe": round(haircut, 3),
        "haircutPct": round(haircut_pct, 1),
        "nTrials": int(n_trials),
    }


def _column_sharpe(rows: np.ndarray) -> np.ndarray:
    """Per-column per-observation Sharpe of a (rows × trials) matrix."""
    if rows.shape[0] < 2:
        return np.zeros(rows.shape[1])
    mu = rows.mean(axis=0)
    sd = rows.std(axis=0, ddof=0)
    out = np.zeros(rows.shape[1])
    nz = sd > 0
    out[nz] = mu[nz] / sd[nz]
    return out


def pbo_cscv(returns_matrix: np.ndarray, n_splits: int = 10) -> Optional[Dict[str, float]]:
    """Probability of Backtest Overfitting via Combinatorially-Symmetric
    Cross-Validation (Bailey, Borwein, López de Prado & Zhu, 2017).

    `returns_matrix` is (T observations × N configurations) of per-bar strategy
    returns. The rows are split into S contiguous blocks; for every way of
    choosing S/2 blocks as in-sample, the in-sample-best configuration is found
    and its OUT-of-sample relative rank is measured. PBO is the fraction of
    splits in which that configuration lands in the bottom half out-of-sample
    (logit ≤ 0). Returns None when there are too few configurations or rows to
    run the procedure honestly."""
    m = np.asarray(returns_matrix, dtype=float)
    if m.ndim != 2 or m.shape[1] < 2:
        return None
    t, n = m.shape
    # Need an even number of blocks, each with at least 2 rows.
    s = max(4, int(n_splits))
    if s % 2 == 1:
        s += 1
    while s > 4 and t < s * 2:
        s -= 2
    if t < s * 2:
        return None
    trim = t - (t % s)
    m = m[:trim]
    block = trim // s
    blocks = [m[i * block:(i + 1) * block] for i in range(s)]
    all_idx = set(range(s))
    overfit = 0
    total = 0
    logits = []
    for combo in itertools.combinations(range(s), s // 2):
        is_rows = np.vstack([blocks[i] for i in combo])
        oos_rows = np.vstack([blocks[i] for i in all_idx - set(combo)])
        is_perf = _column_sharpe(is_rows)
        oos_perf = _column_sharpe(oos_rows)
        n_star = int(np.argmax(is_perf))
        # Relative rank of the IS-best config among OOS performances, in (0, 1).
        rank = int(np.sum(oos_perf < oos_perf[n_star])) + 1
        omega = rank / (n + 1.0)
        omega = min(max(omega, 1e-6), 1.0 - 1e-6)
        lam = math.log(omega / (1.0 - omega))
        logits.append(lam)
        if lam <= 0.0:
            overfit += 1
        total += 1
    if total == 0:
        return None
    return {
        "pbo": round(overfit / total, 4),
        "nTrials": int(n),
        "nSplits": int(s),
        "nCombos": int(total),
        "medianLogit": round(float(np.median(logits)), 3),
    }


def performance_stats(
    equity: np.ndarray,
    returns: np.ndarray,
    turnover: float = 0.0,
    rf: float = 0.0,
) -> Dict[str, float]:
    """Bundle the full stat block used by the backtest panel."""
    return {
        "sharpe": round(sharpe(returns, rf), 2),
        "sortino": round(sortino(returns, rf), 2),
        "cagr": round(cagr(equity) * 100.0, 2),
        "totalReturn": round(total_return(equity) * 100.0, 2),
        "vol": round(annualized_vol(returns) * 100.0, 2),
        "maxDD": round(max_drawdown(equity) * 100.0, 2),
        "winRate": round(win_rate(returns) * 100.0, 1),
        "turnover": round(float(turnover), 2),
        "var95": round(var_historical(returns, 0.95) * 100.0, 2),
        "cvar95": round(cvar_historical(returns, 0.95) * 100.0, 2),
    }
