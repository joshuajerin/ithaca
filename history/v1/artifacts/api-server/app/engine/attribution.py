"""Performance & factor attribution (pure numpy).

Decomposes a book's realized return over a window against a real benchmark into:

* P&L / active statistics (return, vol, Sharpe, max drawdown, hit rate, plus
  active stats: tracking error, information ratio, beta, alpha, capture);
* single-period Brinson allocation / selection / interaction by sector; and
* a linear factor decomposition (per-factor contribution + specific return)
  using the real risk model's exposures and estimated factor returns.

Everything here is pure (no DB / network): callers source the real returns,
benchmark and factor model and hand aligned arrays in. The two attribution
identities are exact by construction:

* Brinson: ``sum(allocation + selection + interaction) == Rp_total - Rb_total``;
* Factor: ``sum(factor contributions) + specific == realized book return``.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence

import numpy as np

from . import stats

TRADING_DAYS = stats.TRADING_DAYS


def align_benchmark_returns(
    closes: Dict[str, float], dates: Sequence[str]
) -> tuple[np.ndarray, int]:
    """Align a real benchmark's close series onto a window's trading dates.

    ``closes`` maps ISO date -> close for a *real* instrument (e.g. SPY). The
    daily return for ``dates[i]`` is computed from the benchmark's own close on
    that date over its previous available close (the last close strictly before
    ``dates[i]`` for the first day, then the prior aligned day). Dates the
    benchmark did not trade are excluded (return carried as 0.0 for that day and
    counted in the returned ``missing`` so callers can report it honestly).

    Returns ``(returns[len(dates)], missing_count)``.
    """
    keys = sorted(closes.keys())
    out = np.zeros(len(dates), dtype=float)
    missing = 0
    if not keys:
        return out, len(dates)

    import bisect

    def prev_before(d: str):
        j = bisect.bisect_left(keys, d)
        return closes[keys[j - 1]] if j > 0 else None

    prev = prev_before(dates[0]) if dates else None
    for i, d in enumerate(dates):
        c = closes.get(d)
        if c is None:
            missing += 1
            continue
        if prev is not None and prev != 0:
            out[i] = c / prev - 1.0
        prev = c
    return out, missing


def book_returns(asset_returns: np.ndarray, weights: Sequence[float]) -> np.ndarray:
    """Daily book return series from a (T, N) asset-return panel and N weights.

    Fixed (daily-rebalanced) weights — the honest, transparent convention also
    used by the risk model: each day's book return is ``w . r_t``.
    """
    r = np.asarray(asset_returns, dtype=float)
    w = np.asarray(weights, dtype=float)
    if r.ndim != 2 or r.shape[1] != w.shape[0]:
        raise ValueError("asset_returns (T,N) must match weights (N,)")
    return r @ w


def equity_curve(daily_returns: np.ndarray, base: float = 100.0) -> np.ndarray:
    """Compounded equity curve (length T+1) starting at ``base``."""
    r = np.asarray(daily_returns, dtype=float)
    return base * np.concatenate([[1.0], np.cumprod(1.0 + r)])


def _safe_div(a: float, b: float) -> float:
    return float(a / b) if b not in (0, 0.0) and np.isfinite(b) else 0.0


def active_stats(book: np.ndarray, bench: np.ndarray) -> Dict[str, float]:
    """Benchmark-relative statistics for a book vs a benchmark return series."""
    b = np.asarray(book, dtype=float)
    m = np.asarray(bench, dtype=float)
    n = min(b.size, m.size)
    b, m = b[:n], m[:n]
    if n < 2:
        return {
            "activeReturn": 0.0, "trackingError": 0.0, "informationRatio": 0.0,
            "beta": 0.0, "alpha": 0.0, "correlation": 0.0,
            "upCapture": 0.0, "downCapture": 0.0,
        }
    active = b - m
    te = float(active.std(ddof=0) * np.sqrt(TRADING_DAYS))
    ir = _safe_div(active.mean(), active.std(ddof=0)) * np.sqrt(TRADING_DAYS)
    var_m = float(m.var(ddof=0))
    beta = _safe_div(float(np.cov(b, m, ddof=0)[0, 1]), var_m)
    alpha = float((b.mean() - beta * m.mean()) * TRADING_DAYS)
    sd_b, sd_m = b.std(ddof=0), m.std(ddof=0)
    corr = _safe_div(float(np.cov(b, m, ddof=0)[0, 1]), float(sd_b * sd_m))
    up = m > 0
    down = m < 0
    up_cap = _safe_div(b[up].mean(), m[up].mean()) * 100.0 if up.any() else 0.0
    down_cap = _safe_div(b[down].mean(), m[down].mean()) * 100.0 if down.any() else 0.0
    # Active (compounded) return over the window.
    active_total = float(np.prod(1.0 + b) - np.prod(1.0 + m))
    return {
        "activeReturn": round(active_total * 100.0, 2),
        "trackingError": round(te * 100.0, 2),
        "informationRatio": round(ir, 2),
        "beta": round(beta, 2),
        "alpha": round(alpha * 100.0, 2),
        "correlation": round(corr, 2),
        "upCapture": round(up_cap, 1),
        "downCapture": round(down_cap, 1),
    }


def return_stats(daily_returns: np.ndarray) -> Dict[str, float]:
    """Standalone return/risk stat block for one return series (percent units)."""
    r = np.asarray(daily_returns, dtype=float)
    eq = equity_curve(r)
    return {
        "totalReturn": round(stats.total_return(eq) * 100.0, 2),
        "cagr": round(stats.cagr(eq) * 100.0, 2),
        "vol": round(stats.annualized_vol(r) * 100.0, 2),
        "sharpe": round(stats.sharpe(r), 2),
        "sortino": round(stats.sortino(r), 2),
        "maxDD": round(stats.max_drawdown(eq) * 100.0, 2),
        "hitRate": round(stats.win_rate(r) * 100.0, 1),
    }


def pnl_summary(book: np.ndarray, bench: np.ndarray) -> Dict[str, Dict[str, float]]:
    """Full P&L summary: book stats, benchmark stats and active stats."""
    return {
        "book": return_stats(book),
        "benchmark": return_stats(bench),
        "active": active_stats(book, bench),
    }


def brinson(
    sectors: Sequence[str],
    wp: Dict[str, float],
    wb: Dict[str, float],
    rp: Dict[str, float],
    rb: Dict[str, float],
) -> Dict[str, object]:
    """Single-period Brinson-Hood-Beebower attribution by sector.

    For each sector: allocation = (wp-wb)*Rb, selection = wb*(Rp-Rb),
    interaction = (wp-wb)*(Rp-Rb). The three effects sum (across sectors) exactly
    to the total active return ``Rp_total - Rb_total`` where the totals are the
    weighted single-period sector returns. All inputs/outputs are fractions;
    outputs are rendered in percent.
    """
    rows: List[dict] = []
    tot_alloc = tot_sel = tot_inter = 0.0
    rp_total = rb_total = 0.0
    for s in sectors:
        wpi = float(wp.get(s, 0.0))
        wbi = float(wb.get(s, 0.0))
        rpi = float(rp.get(s, 0.0))
        rbi = float(rb.get(s, 0.0))
        alloc = (wpi - wbi) * rbi
        sel = wbi * (rpi - rbi)
        inter = (wpi - wbi) * (rpi - rbi)
        tot_alloc += alloc
        tot_sel += sel
        tot_inter += inter
        rp_total += wpi * rpi
        rb_total += wbi * rbi
        rows.append({
            "sector": s,
            "portWeight": round(wpi * 100.0, 2),
            "benchWeight": round(wbi * 100.0, 2),
            "portReturn": round(rpi * 100.0, 2),
            "benchReturn": round(rbi * 100.0, 2),
            "allocation": round(alloc * 100.0, 2),
            "selection": round(sel * 100.0, 2),
            "interaction": round(inter * 100.0, 2),
            "total": round((alloc + sel + inter) * 100.0, 2),
        })
    return {
        "rows": rows,
        "totals": {
            "allocation": round(tot_alloc * 100.0, 2),
            "selection": round(tot_sel * 100.0, 2),
            "interaction": round(tot_inter * 100.0, 2),
            "total": round((tot_alloc + tot_sel + tot_inter) * 100.0, 2),
            "portReturn": round(rp_total * 100.0, 2),
            "benchReturn": round(rb_total * 100.0, 2),
            "activeReturn": round((rp_total - rb_total) * 100.0, 2),
        },
    }


def _carino_coeff(rp_total: float, rb_total: float) -> float:
    """Carino smoothing coefficient for a (compounded) Rp/Rb pair.

    ``k = (ln(1+Rp) - ln(1+Rb)) / (Rp - Rb)`` with the removable singularity at
    ``Rp == Rb`` filled by its limit ``1 / (1 + Rp)``. Used both for the full
    window (the denominator ``k``) and for each sub-period (the numerators
    ``k_t``); ``k_t / k`` is the factor that rescales single-period arithmetic
    effects so they link geometrically over the window.
    """
    diff = rp_total - rb_total
    if abs(diff) > 1e-12:
        return (math.log1p(rp_total) - math.log1p(rb_total)) / diff
    denom = 1.0 + rp_total
    return 1.0 / denom if abs(denom) > 1e-12 else 1.0


def brinson_linked(
    sectors: Sequence[str],
    wp: Dict[str, Sequence[float]],
    wb: Dict[str, Sequence[float]],
    rp: Dict[str, Sequence[float]],
    rb: Dict[str, Sequence[float]],
) -> Dict[str, object]:
    """Multi-period Brinson-Hood-Beebower attribution with Carino linking.

    Each of ``wp``/``wb``/``rp``/``rb`` maps a sector to a per-sub-period series
    (length ``T``); a scalar (or length-1 series) is broadcast across all
    sub-periods, so constant weights can be passed as a single number. For each
    sub-period ``t`` and sector ``s`` the single-period BHB effects are
    ``alloc = (wp-wb)*Rb``, ``sel = wb*(Rp-Rb)``, ``inter = (wp-wb)*(Rp-Rb)``.

    The per-period effects are scaled by the Carino factor ``k_t / k`` (see
    :func:`_carino_coeff`) and summed over sub-periods. This makes the linked
    effects add up **exactly** to the geometrically compounded active return
    ``Rp_total - Rb_total`` where ``Rp_total = prod_t(1 + Rp_t) - 1`` (and
    likewise for the benchmark), eliminating the residual/linking bias that
    single-period BHB on compounded sector returns accumulates over long windows.

    All inputs/outputs are fractions; outputs are rendered in percent and match
    the shape of :func:`brinson` (``rows`` + ``totals``) for drop-in use.
    """
    secs = list(sectors)

    # Infer the number of sub-periods from the longest provided series.
    T = 0
    for d in (wp, wb, rp, rb):
        for s in secs:
            if s in d:
                T = max(T, int(np.atleast_1d(np.asarray(d[s], dtype=float)).size))
    if T == 0:
        T = 1

    def col(d: Dict[str, Sequence[float]], s: str) -> np.ndarray:
        if s not in d:
            return np.zeros(T, dtype=float)
        a = np.atleast_1d(np.asarray(d[s], dtype=float)).ravel()
        if a.size == 1:
            return np.full(T, float(a[0]))
        if a.size != T:
            raise ValueError(
                f"series for sector {s!r} has length {a.size}, expected {T}"
            )
        return a

    WP = {s: col(wp, s) for s in secs}
    WB = {s: col(wb, s) for s in secs}
    RP = {s: col(rp, s) for s in secs}
    RB = {s: col(rb, s) for s in secs}

    # Per-sub-period total portfolio / benchmark returns.
    rp_t = np.zeros(T, dtype=float)
    rb_t = np.zeros(T, dtype=float)
    for s in secs:
        rp_t += WP[s] * RP[s]
        rb_t += WB[s] * RB[s]

    rp_total = float(np.prod(1.0 + rp_t) - 1.0)
    rb_total = float(np.prod(1.0 + rb_t) - 1.0)
    active_total = rp_total - rb_total

    # Carino linking: scale[t] = k_t / k.
    k = _carino_coeff(rp_total, rb_total)
    scale = np.array(
        [_carino_coeff(float(rp_t[t]), float(rb_t[t])) for t in range(T)],
        dtype=float,
    )
    scale = scale / k if abs(k) > 1e-12 else scale

    rows: List[dict] = []
    tot_alloc = tot_sel = tot_inter = 0.0
    for s in secs:
        d_w = WP[s] - WB[s]
        alloc_t = d_w * RB[s]
        sel_t = WB[s] * (RP[s] - RB[s])
        inter_t = d_w * (RP[s] - RB[s])
        alloc = float(np.sum(scale * alloc_t))
        sel = float(np.sum(scale * sel_t))
        inter = float(np.sum(scale * inter_t))
        tot_alloc += alloc
        tot_sel += sel
        tot_inter += inter
        # Display weights/returns: time-averaged weight, compounded sector return.
        rows.append({
            "sector": s,
            "portWeight": round(float(WP[s].mean()) * 100.0, 2),
            "benchWeight": round(float(WB[s].mean()) * 100.0, 2),
            "portReturn": round(float(np.prod(1.0 + RP[s]) - 1.0) * 100.0, 2),
            "benchReturn": round(float(np.prod(1.0 + RB[s]) - 1.0) * 100.0, 2),
            "allocation": round(alloc * 100.0, 2),
            "selection": round(sel * 100.0, 2),
            "interaction": round(inter * 100.0, 2),
            "total": round((alloc + sel + inter) * 100.0, 2),
        })
    return {
        "rows": rows,
        "totals": {
            "allocation": round(tot_alloc * 100.0, 2),
            "selection": round(tot_sel * 100.0, 2),
            "interaction": round(tot_inter * 100.0, 2),
            "total": round((tot_alloc + tot_sel + tot_inter) * 100.0, 2),
            "portReturn": round(rp_total * 100.0, 2),
            "benchReturn": round(rb_total * 100.0, 2),
            "activeReturn": round(active_total * 100.0, 2),
        },
        "linked": True,
        "subPeriods": int(T),
    }


def factor_attribution(
    exposures: np.ndarray,
    factor_returns: np.ndarray,
    factor_names: Sequence[str],
    book_daily: np.ndarray,
) -> Dict[str, object]:
    """Linear factor decomposition of the book's realized window return.

    ``exposures`` is the book's factor exposure vector ``b = X' w`` (K,),
    ``factor_returns`` is the (T, K) estimated daily factor-return panel, and
    ``book_daily`` is the book's (T,) realized daily return series. Per-factor
    contribution is ``b_k * sum_t f_tk``; the specific (idiosyncratic + residual)
    return is whatever the realized compounded return leaves unexplained, so the
    contributions plus specific reconstruct the realized return exactly.
    """
    b = np.asarray(exposures, dtype=float)
    f = np.asarray(factor_returns, dtype=float)
    if f.ndim != 2 or f.shape[1] != b.shape[0]:
        raise ValueError("factor_returns (T,K) must match exposures (K,)")
    factor_cum = f.sum(axis=0)  # (K,) arithmetic window cumulative factor return
    contrib = b * factor_cum  # (K,)
    realized = float(np.prod(1.0 + np.asarray(book_daily, dtype=float)) - 1.0)
    explained = float(contrib.sum())
    specific = realized - explained
    rows = [
        {
            "factor": factor_names[k],
            "exposure": round(float(b[k]), 2),
            "factorReturn": round(float(factor_cum[k]) * 100.0, 2),
            "contribution": round(float(contrib[k]) * 100.0, 2),
        }
        for k in range(b.shape[0])
    ]
    rows.append({
        "factor": "Specific",
        "exposure": None,
        "factorReturn": None,
        "contribution": round(specific * 100.0, 2),
    })
    return {
        "rows": rows,
        "realizedReturn": round(realized * 100.0, 2),
        "factorReturn": round(explained * 100.0, 2),
        "specificReturn": round(specific * 100.0, 2),
    }
