"""Real-data assembly for the Barra-style factor risk model.

Sources real daily returns (live OHLCV when available, the deterministic curated
series otherwise) and real fundamentals, builds standardized factor exposures,
and hands a clean aligned panel to the pure-numpy engine in
``app.engine.riskmodel``.

Honest coverage is the whole point: a name is INCLUDED only when it has enough
overlapping return history AND the fundamentals each style factor needs. Any
name that fails is excluded with an explicit reason — never imputed. Callers
(the skill builders) shape the engine output into panel payloads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import data, repo
from .engine import riskmodel

# Market beta plus the five classic style factors.
STYLE_FACTORS = ["Size", "Value", "Momentum", "Volatility", "Quality"]
FACTOR_NAMES = ["Market"] + STYLE_FACTORS

# Minimum overlapping daily returns required to keep a name in the estimation.
MIN_DAYS = 40
# Cap on the cross-sectional estimation universe (breadth stabilizes factor
# returns without making the daily regression expensive).
MAX_UNIVERSE = 60
# Minimum number of names needed for a credible cross-sectional regression.
MIN_NAMES = 12
# Calendar history requested per name.
WINDOW_DAYS = 180
# Days excluded from the tail of the momentum window (classic 12-1 style skip).
MOMENTUM_SKIP = 10


@dataclass
class Coverage:
    included: List[str]
    excluded: List[dict]  # [{"symbol", "reason"}]
    days: int
    source: str  # "live" if any included name had live data, else "mock"
    as_of: Optional[str]


@dataclass
class RiskModelResult:
    model: riskmodel.FactorModel
    coverage: Coverage
    returns: np.ndarray  # (T, N) aligned daily returns used for estimation
    dates: List[str]  # length-T return dates aligned to returns rows
    factor_ann_returns: Dict[str, float]  # annualized mean factor return
    factor_tstats: Dict[str, float]  # t-stat of each factor's mean daily return
    pca: List[float]  # variance explained by leading principal components
    sources: Dict[str, str] = field(default_factory=dict)


# --------------------------- universe + alignment ---------------------------
def _estimation_universe(portfolio: List[str]) -> List[str]:
    """Portfolio names first, then top names by market cap, deduped + capped."""
    out: List[str] = []
    for s in portfolio:
        u = (s or "").upper()
        if u and u not in out and data.get_company(u):
            out.append(u)
    for s in data.top_symbols(MAX_UNIVERSE * 2):
        if s not in out:
            out.append(s)
        if len(out) >= MAX_UNIVERSE:
            break
    return out


def _aligned_panel(
    series: Dict[str, List[dict]]
) -> Tuple[List[str], List[str]]:
    """Pick a shared trading-date grid and the names that populate it.

    Different provenance can mean different date grids (live = trading days, mock
    = calendar days), so we anchor on the dates shared by the majority of names,
    then keep only names covering enough of that grid, and finally restrict to
    dates every kept name has. Returns ``(dates, symbols)`` both ordered.
    """
    maps: Dict[str, Dict[str, float]] = {}
    for sym, pts in series.items():
        m = {p["t"]: float(p["c"]) for p in pts if p.get("c") is not None}
        if len(m) >= 2:
            maps[sym] = m
    if len(maps) < MIN_NAMES:
        return [], []

    # Majority-vote date grid.
    freq: Dict[str, int] = {}
    for m in maps.values():
        for d in m:
            freq[d] = freq.get(d, 0) + 1
    threshold = max(2, int(0.6 * len(maps)))
    base_dates = sorted(d for d, c in freq.items() if c >= threshold)
    base_dates = base_dates[-WINDOW_DAYS:]
    if len(base_dates) < MIN_DAYS + 1:
        # Fall back to the densest single grid if the majority vote is too thin.
        base_dates = sorted(max(maps.values(), key=len).keys())[-WINDOW_DAYS:]

    base_set = set(base_dates)
    kept = [s for s, m in maps.items() if len(base_set & m.keys()) >= MIN_DAYS]
    if len(kept) < MIN_NAMES:
        return [], []

    # Restrict to dates present in every kept name; if too thin, drop the
    # worst-covering names until the shared grid is deep enough.
    def shared(symbols: List[str]) -> List[str]:
        common = base_set.copy()
        for s in symbols:
            common &= maps[s].keys()
        return sorted(common)

    dates = shared(kept)
    while len(dates) < MIN_DAYS + 1 and len(kept) > MIN_NAMES:
        worst = min(kept, key=lambda s: len(base_set & maps[s].keys()))
        kept.remove(worst)
        dates = shared(kept)

    if len(dates) < MIN_DAYS + 1 or len(kept) < MIN_NAMES:
        return [], []
    return dates, kept


# --------------------------- descriptors ---------------------------
_REQUIRED = {
    "Market": ("beta",),
    "Size": ("marketCap",),
    "Value": ("peRatio",),
    "Quality": ("netMargin",),
}


def _fundamental_reason(company: dict) -> Optional[str]:
    """Return an exclusion reason if any required fundamental is missing."""
    if company.get("beta") in (None, 0):
        return "missing beta"
    if not company.get("marketCap"):
        return "missing market cap"
    if not company.get("peRatio") or company["peRatio"] <= 0:
        return "missing/invalid P/E"
    if company.get("netMargin") is None:
        return "missing net margin"
    return None


def _build_descriptors(
    symbols: List[str], rets: np.ndarray
) -> Dict[str, np.ndarray]:
    """Build the (N, K) exposure columns from real fundamentals + returns.

    Market is the raw beta (kept near 1 as in Barra); the style columns are
    cross-sectional z-scores of their descriptors. Momentum and Volatility are
    derived from the very same aligned return panel used for estimation.
    """
    n = len(symbols)
    beta = np.array([data.get_company(s)["beta"] for s in symbols], dtype=float)
    mcap = np.array([data.get_company(s)["marketCap"] for s in symbols], dtype=float)
    pe = np.array([data.get_company(s)["peRatio"] for s in symbols], dtype=float)
    div = np.array(
        [data.get_company(s).get("dividendYield") or 0.0 for s in symbols], dtype=float
    )
    margin = np.array(
        [data.get_company(s).get("netMargin") or 0.0 for s in symbols], dtype=float
    )

    # Momentum: cumulative return over the window, skipping the recent tail.
    if rets.shape[0] > MOMENTUM_SKIP + 5:
        mom_window = rets[: -MOMENTUM_SKIP]
    else:
        mom_window = rets
    momentum_raw = np.prod(1.0 + mom_window, axis=0) - 1.0
    # Volatility: annualized stdev of daily returns.
    vol_raw = rets.std(axis=0, ddof=1) * np.sqrt(riskmodel.TRADING_DAYS)

    size_z, _, _ = riskmodel.standardize(np.log(np.maximum(mcap, 1.0)))
    earnings_yield = np.where(pe > 0, 1.0 / pe, np.nan)
    ey_z, _, _ = riskmodel.standardize(earnings_yield)
    div_z, _, _ = riskmodel.standardize(div)
    value_z, _, _ = riskmodel.standardize(0.7 * ey_z + 0.3 * div_z)
    mom_z, _, _ = riskmodel.standardize(momentum_raw)
    vol_z, _, _ = riskmodel.standardize(vol_raw)
    qual_z, _, _ = riskmodel.standardize(margin)

    return {
        "Market": beta,
        "Size": size_z,
        "Value": value_z,
        "Momentum": mom_z,
        "Volatility": vol_z,
        "Quality": qual_z,
    }


# --------------------------- public entry point ---------------------------
def build(portfolio: Optional[List[str]] = None) -> RiskModelResult:
    """Estimate the factor model over a real cross-sectional panel.

    ``portfolio`` names are guaranteed a slot in the candidate universe (they may
    still be excluded by the honest coverage checks). Raises ``ValueError`` with
    a human-readable message if a credible model cannot be estimated — the skill
    harness turns that into a clean error panel rather than fabricating numbers.
    """
    portfolio = portfolio or []
    candidates = _estimation_universe(portfolio)
    bulk = repo.closes_bulk(candidates, days=WINDOW_DAYS)
    series, sources = bulk["series"], bulk["sources"]

    dates, aligned = _aligned_panel(series)
    if not aligned:
        raise ValueError(
            "not enough overlapping price history to estimate a factor model"
        )

    # Split aligned names on fundamentals coverage (returns coverage already met).
    included: List[str] = []
    excluded: List[dict] = []
    for s in aligned:
        company = data.get_company(s)
        reason = _fundamental_reason(company) if company else "unknown ticker"
        if reason:
            excluded.append({"symbol": s, "reason": reason})
        else:
            included.append(s)

    # Names that were candidates but never made the aligned grid.
    aligned_set = set(aligned)
    for s in candidates:
        if s not in aligned_set and s in (portfolio or []):
            excluded.append({"symbol": s, "reason": "insufficient overlapping history"})

    if len(included) < MIN_NAMES:
        raise ValueError(
            "too few names with sufficient history and fundamentals to estimate risk"
        )

    # Build the aligned (T, N) return matrix for the included names.
    date_idx = {d: i for i, d in enumerate(dates)}
    closes = np.empty((len(dates), len(included)), dtype=float)
    for j, s in enumerate(included):
        m = {p["t"]: float(p["c"]) for p in series[s] if p.get("c") is not None}
        for d, i in date_idx.items():
            closes[i, j] = m[d]
    rets = closes[1:] / closes[:-1] - 1.0  # (T-1, N)

    descriptors = _build_descriptors(included, rets)
    exposures = np.column_stack([descriptors[f] for f in FACTOR_NAMES])
    model = riskmodel.build_model(rets, exposures, FACTOR_NAMES, included)

    # Annualized factor returns + significance of each factor's mean daily return.
    f = model.factor_returns  # (T, K)
    mean_daily = f.mean(axis=0)
    ann = mean_daily * riskmodel.TRADING_DAYS
    se = f.std(axis=0, ddof=1) / np.sqrt(max(f.shape[0], 1))
    with np.errstate(divide="ignore", invalid="ignore"):
        tstat = np.where(se > 0, mean_daily / se, 0.0)
    factor_ann_returns = {fn: float(ann[k]) for k, fn in enumerate(FACTOR_NAMES)}
    factor_tstats = {fn: float(tstat[k]) for k, fn in enumerate(FACTOR_NAMES)}

    src = "live" if any(sources.get(s) == "live" for s in included) else "mock"
    coverage = Coverage(
        included=included,
        excluded=excluded,
        days=int(rets.shape[0]),
        source=src,
        as_of=bulk.get("asOf"),
    )
    return RiskModelResult(
        model=model,
        coverage=coverage,
        returns=rets,
        dates=dates[1:],
        factor_ann_returns=factor_ann_returns,
        factor_tstats=factor_tstats,
        pca=riskmodel.pca_variance(rets, k=5),
        sources={s: sources.get(s, "mock") for s in included},
    )


# --------------------------- portfolio helpers ---------------------------
def resolve_weights(
    symbols: List[str], weights: Optional[List[float]]
) -> List[Tuple[str, float]]:
    """Pair tickers with weights (equal-weight if absent), normalized to sum 1."""
    syms = [(s or "").upper() for s in symbols if s]
    if weights and len(weights) == len(syms):
        w = [float(x) for x in weights]
    else:
        w = [1.0] * len(syms)
    total = sum(abs(x) for x in w) or 1.0
    return [(s, x / total) for s, x in zip(syms, w)]


def portfolio_indices(
    result: RiskModelResult, symbols: List[str], weights: List[float]
) -> Tuple[List[int], np.ndarray, List[str]]:
    """Map requested holdings to model rows, dropping & renormalizing excluded.

    Returns ``(idx, normalized_weights, dropped_symbols)``. Raises ``ValueError``
    if none of the requested holdings are in the estimation universe.
    """
    included = result.model.symbols
    pos = {s: i for i, s in enumerate(included)}
    idx: List[int] = []
    kept_w: List[float] = []
    dropped: List[str] = []
    for s, w in zip(symbols, weights):
        if s in pos:
            idx.append(pos[s])
            kept_w.append(w)
        else:
            dropped.append(s)
    if not idx:
        raise ValueError("none of the requested holdings could be risk-modeled")
    arr = np.asarray(kept_w, dtype=float)
    total = float(np.abs(arr).sum()) or 1.0
    return idx, arr / total, dropped
