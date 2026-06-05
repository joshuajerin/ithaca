"""Cross-sectional alpha signal library and evaluation toolkit.

This is the research-desk engine: it computes classic, transparent alpha signals
over a *cross-section* of names and evaluates whether a signal actually predicts
forward returns using the standard quant toolkit:

- Rank IC  — Spearman rank correlation of the signal vs forward returns.
- IC decay — rank IC measured at several forward horizons.
- Turnover — how much the top-quantile membership churns between rebalances.
- Quantile / decile spread — the equity curve of a long-top / short-bottom book.

Everything is pure and deterministic (numpy + stdlib only, no DB/network) so it
is trivially unit-testable. Callers (the skill builders) own sourcing the price
series and fundamentals and the live/mock provenance decision; this module just
computes from the close series and the cross-sectional context it is handed.

No-lookahead guarantee: a signal value on date d uses only information up to and
including d, and is always scored against the *forward* return measured from d to
d+h. There is therefore no lookahead bias in the IC / spread numbers.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

TRADING_DAYS = 252

# A signal takes (closes, ctx) and returns one value per bar (NaN where it cannot
# be computed). ctx carries any cross-sectional context (e.g. a fundamental value).
SignalFn = Callable[[np.ndarray, dict], np.ndarray]


# ----------------------------- signal definitions -----------------------------
def _daily_returns(closes: np.ndarray) -> np.ndarray:
    n = closes.size
    rets = np.full(n, np.nan, dtype=float)
    if n >= 2:
        rets[1:] = closes[1:] / closes[:-1] - 1.0
    return rets


def signal_momentum(closes: np.ndarray, ctx: dict) -> np.ndarray:
    """Trailing price momentum over `lookback` bars (default ~3 months).

    Higher = stronger recent trend. A `skip` of recent bars can be excluded to
    sidestep short-term reversal (classic 12-1 style); default keeps it simple.
    """
    lookback = max(2, int(ctx.get("lookback", 63)))
    skip = max(0, int(ctx.get("skip", 0)))
    n = closes.size
    out = np.full(n, np.nan, dtype=float)
    for i in range(n):
        j = i - lookback
        k = i - skip
        if j >= 0 and k >= 0 and closes[j] > 0:
            out[i] = closes[k] / closes[j] - 1.0
    return out


def signal_short_reversal(closes: np.ndarray, ctx: dict) -> np.ndarray:
    """Short-term reversal: the NEGATIVE of the trailing `lookback`-bar return.

    Recent losers score high (expected to bounce), recent winners score low.
    """
    lookback = max(1, int(ctx.get("lookback", 10)))
    n = closes.size
    out = np.full(n, np.nan, dtype=float)
    for i in range(n):
        j = i - lookback
        if j >= 0 and closes[j] > 0:
            out[i] = -(closes[i] / closes[j] - 1.0)
    return out


def signal_low_volatility(closes: np.ndarray, ctx: dict) -> np.ndarray:
    """Low-volatility signal: NEGATIVE trailing realized volatility.

    Calmer names score high (the low-vol anomaly), choppy names score low.
    """
    window = max(2, int(ctx.get("window", 21)))
    n = closes.size
    out = np.full(n, np.nan, dtype=float)
    rets = _daily_returns(closes)
    for i in range(n):
        if i + 1 >= window + 1:  # need `window` finite returns ending at i
            w = rets[i - window + 1 : i + 1]
            w = w[np.isfinite(w)]
            if w.size >= 2:
                out[i] = -float(w.std(ddof=0))
    return out


def signal_static(closes: np.ndarray, ctx: dict) -> np.ndarray:
    """A fundamentals-derived value that is constant across the price series.

    Used for snapshot fundamental signals (value, quality): the caller supplies a
    single cross-sectional value in ``ctx['fval']`` (or None when the underlying
    field is missing, which yields an all-NaN, i.e. excluded, signal).
    """
    fval = ctx.get("fval")
    n = closes.size
    if fval is None:
        return np.full(n, np.nan, dtype=float)
    try:
        v = float(fval)
    except (TypeError, ValueError):
        return np.full(n, np.nan, dtype=float)
    if not np.isfinite(v):
        return np.full(n, np.nan, dtype=float)
    return np.full(n, v, dtype=float)


SIGNALS: Dict[str, SignalFn] = {
    "momentum": signal_momentum,
    "short_reversal": signal_short_reversal,
    "low_volatility": signal_low_volatility,
    "value": signal_static,
    "quality": signal_static,
}

# Metadata used by the builders for labelling and honest coverage reporting.
# `needs` is the company field a fundamental signal requires; price signals need
# nothing beyond the close series.
SIGNAL_META: Dict[str, dict] = {
    "momentum": {
        "label": "Price Momentum (3M)",
        "kind": "price",
        "needs": None,
        "desc": "Trailing 3-month price return — momentum / trend.",
    },
    "short_reversal": {
        "label": "Short-Term Reversal (2W)",
        "kind": "price",
        "needs": None,
        "desc": "Negative of the trailing 2-week return — mean reversion.",
    },
    "low_volatility": {
        "label": "Low Volatility (1M)",
        "kind": "price",
        "needs": None,
        "desc": "Negative trailing 1-month realized volatility — the low-vol anomaly.",
    },
    "value": {
        "label": "Value (Earnings Yield)",
        "kind": "fundamental",
        "needs": "peRatio",
        "desc": "Earnings yield (1 / P·E) — cheap names score high.",
    },
    "quality": {
        "label": "Quality (Net Margin)",
        "kind": "fundamental",
        "needs": "netMargin",
        "desc": "Net profit margin — more profitable names score high.",
    },
}

_ALIASES = {
    "mom": "momentum",
    "price momentum": "momentum",
    "trend": "momentum",
    "reversal": "short_reversal",
    "short term reversal": "short_reversal",
    "short-term reversal": "short_reversal",
    "mean reversion": "short_reversal",
    "reversion": "short_reversal",
    "low vol": "low_volatility",
    "low volatility": "low_volatility",
    "volatility": "low_volatility",
    "vol": "low_volatility",
    "earnings yield": "value",
    "cheap": "value",
    "profitability": "quality",
    "margin": "quality",
}


def normalize_signal(name: str) -> str:
    """Resolve a free-text signal name to a registered key (default momentum)."""
    if not name:
        return "momentum"
    key = str(name).strip().lower().replace("-", "_")
    if key in SIGNALS:
        return key
    spaced = key.replace("_", " ")
    if spaced in _ALIASES:
        return _ALIASES[spaced]
    if key in _ALIASES:
        return _ALIASES[key]
    return "momentum"


def available_signals() -> List[str]:
    return list(SIGNALS.keys())


def signal_label(name: str) -> str:
    return SIGNAL_META.get(normalize_signal(name), {}).get("label", name)


# ----------------------------- rank statistics -----------------------------
def _rankdata(a: np.ndarray) -> np.ndarray:
    """Average-rank of the values in `a` (1-based), ties averaged (Spearman-ready)."""
    a = np.asarray(a, dtype=float)
    n = a.size
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.arange(1, n + 1, dtype=float)
    sorted_a = a[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sorted_a[j + 1] == sorted_a[i]:
            j += 1
        if j > i:
            avg = (i + 1 + j + 1) / 2.0
            ranks[order[i : j + 1]] = avg
        i = j + 1
    return ranks


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denom = np.sqrt(float((a * a).sum()) * float((b * b).sum()))
    if denom <= 0:
        return float("nan")
    return float((a * b).sum() / denom)


def spearman_ic(signal: Sequence[float], forward: Sequence[float]) -> float:
    """Spearman rank correlation between a signal cross-section and forward returns."""
    x = np.asarray(signal, dtype=float)
    y = np.asarray(forward, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    if int(mask.sum()) < 3:
        return float("nan")
    return _pearson(_rankdata(x[mask]), _rankdata(y[mask]))


# ----------------------------- core evaluation -----------------------------
def _clean_series(points: Sequence[dict]) -> Tuple[List[str], np.ndarray]:
    dates: List[str] = []
    closes: List[float] = []
    for p in points or []:
        c = p.get("c")
        if c is None:
            continue
        try:
            cf = float(c)
        except (TypeError, ValueError):
            continue
        if cf <= 0:
            continue
        dates.append(str(p.get("t")))
        closes.append(cf)
    return dates, np.asarray(closes, dtype=float)


def evaluate_signal(
    series_by_symbol: Dict[str, Sequence[dict]],
    signal: str = "momentum",
    ctx_by_symbol: Optional[Dict[str, dict]] = None,
    horizons: Sequence[int] = (1, 5, 10, 21, 42),
    holding: int = 21,
    quantiles: int = 5,
    ic_stride: int = 5,
    min_names: int = 5,
) -> dict:
    """Evaluate one signal cross-sectionally over many symbols' close series.

    Returns a dict with rank-IC stats (per horizon -> decay curve), turnover, a
    quantile long-short spread equity curve and per-quantile mean forward return,
    plus the included / excluded symbol sets so coverage can be reported honestly.

    ``ctx_by_symbol`` carries any per-symbol context the signal needs (e.g.
    ``{"fval": 0.05}`` for fundamental signals). Price signals ignore it.
    """
    signal = normalize_signal(signal)
    fn = SIGNALS[signal]
    ctx_by_symbol = ctx_by_symbol or {}
    horizons = sorted({int(h) for h in horizons if int(h) >= 1})
    if holding not in horizons:
        horizons = sorted(set(horizons) | {int(holding)})
    quantiles = max(2, int(quantiles))
    min_names = max(quantiles, int(min_names))

    per: Dict[str, dict] = {}
    excluded: List[dict] = []
    for sym, points in series_by_symbol.items():
        dates, closes = _clean_series(points)
        if closes.size < 5:
            excluded.append({"symbol": sym, "reason": "insufficient price history"})
            continue
        ctx = dict(ctx_by_symbol.get(sym) or {})
        sig = np.asarray(fn(closes, ctx), dtype=float)
        if not np.isfinite(sig).any():
            reason = "missing fundamental" if SIGNAL_META.get(signal, {}).get("kind") == "fundamental" else "signal not computable"
            excluded.append({"symbol": sym, "reason": reason})
            continue
        fret: Dict[int, np.ndarray] = {}
        n = closes.size
        for h in horizons:
            fr = np.full(n, np.nan, dtype=float)
            if h < n:
                fr[: n - h] = closes[h:] / closes[: n - h] - 1.0
            fret[h] = fr
        per[sym] = {
            "dates": dates,
            "closes": closes,
            "sig": sig,
            "fret": fret,
            "date_idx": {d: i for i, d in enumerate(dates)},
        }

    included = list(per.keys())
    result: dict = {
        "signal": signal,
        "label": SIGNAL_META.get(signal, {}).get("label", signal),
        "horizons": list(horizons),
        "holding": int(holding),
        "quantiles": quantiles,
        "included": included,
        "excluded": excluded,
        "icByHorizon": {},
        "decay": [],
        "primaryHorizon": int(holding),
        "ic": {"mean": 0.0, "std": 0.0, "ir": 0.0, "tStat": 0.0, "hitRate": 0.0, "n": 0},
        "turnover": 0.0,
        "turnoverAnnual": 0.0,
        "rebalances": 0,
        "quantileReturns": [],
        "spread": [],
        "spreadStats": {"totalReturn": 0.0, "sharpe": 0.0, "cagr": 0.0},
    }
    if len(per) < min_names:
        return result

    all_dates = sorted(set().union(*[set(p["date_idx"].keys()) for p in per.values()]))

    # --- rank IC per horizon (decay curve) ---
    for h in horizons:
        ics: List[float] = []
        for di in range(0, len(all_dates), max(1, ic_stride)):
            d = all_dates[di]
            xs: List[float] = []
            ys: List[float] = []
            for P in per.values():
                i = P["date_idx"].get(d)
                if i is None:
                    continue
                s = P["sig"][i]
                fr = P["fret"][h][i]
                if np.isfinite(s) and np.isfinite(fr):
                    xs.append(float(s))
                    ys.append(float(fr))
            if len(xs) >= min_names:
                ic = spearman_ic(xs, ys)
                if np.isfinite(ic):
                    ics.append(ic)
        arr = np.asarray(ics, dtype=float)
        if arr.size:
            mean = float(arr.mean())
            std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
            ir = mean / std if std > 0 else 0.0
            t_stat = ir * np.sqrt(arr.size) if std > 0 else 0.0
            hit = float((arr > 0).mean() * 100.0)
            stat = {
                "mean": round(mean, 4),
                "std": round(std, 4),
                "ir": round(ir, 3),
                "tStat": round(float(t_stat), 2),
                "hitRate": round(hit, 1),
                "n": int(arr.size),
            }
        else:
            stat = {"mean": 0.0, "std": 0.0, "ir": 0.0, "tStat": 0.0, "hitRate": 0.0, "n": 0}
        result["icByHorizon"][h] = stat
        result["decay"].append({"horizon": int(h), "ic": stat["mean"]})

    result["ic"] = result["icByHorizon"].get(int(holding)) or result["ic"]

    # --- quantile spread + turnover at the holding horizon ---
    rebalance_dates = all_dates[::holding]
    long_eq = short_eq = spread_eq = 100.0
    spread_curve: List[dict] = []
    spread_rets: List[float] = []
    turnovers: List[float] = []
    qret_accum: List[List[float]] = [[] for _ in range(quantiles)]
    prev_top: Optional[set] = None

    for d in rebalance_dates:
        xs: List[float] = []
        frs: List[float] = []
        syms: List[str] = []
        for sym, P in per.items():
            i = P["date_idx"].get(d)
            if i is None:
                continue
            s = P["sig"][i]
            fr = P["fret"][holding][i]
            if np.isfinite(s) and np.isfinite(fr):
                xs.append(float(s))
                frs.append(float(fr))
                syms.append(sym)
        if len(xs) < min_names:
            continue
        order = np.argsort(np.asarray(xs), kind="mergesort")  # ascending by signal
        groups = np.array_split(order, quantiles)
        for qi, g in enumerate(groups):
            for k in g:
                qret_accum[qi].append(frs[int(k)])
        long_g = groups[-1]
        short_g = groups[0]
        long_ret = float(np.mean([frs[int(k)] for k in long_g]))
        short_ret = float(np.mean([frs[int(k)] for k in short_g]))
        spread = long_ret - short_ret
        spread_rets.append(spread)
        long_eq *= 1.0 + long_ret
        short_eq *= 1.0 + short_ret
        spread_eq *= 1.0 + spread
        spread_curve.append({
            "t": d,
            "value": round(spread_eq, 2),
            "long": round(long_eq, 2),
            "short": round(short_eq, 2),
        })
        top_set = {syms[int(k)] for k in long_g}
        if prev_top is not None and top_set:
            replaced = len(top_set - prev_top) / len(top_set)
            turnovers.append(replaced)
        prev_top = top_set

    result["rebalances"] = len(spread_curve)
    result["spread"] = spread_curve
    if turnovers:
        t_mean = float(np.mean(turnovers)) * 100.0
        result["turnover"] = round(t_mean, 1)
        result["turnoverAnnual"] = round(t_mean * (TRADING_DAYS / holding), 1)

    result["quantileReturns"] = [
        {"quantile": qi + 1, "ret": round(float(np.mean(vals)) * 100.0, 2) if vals else 0.0}
        for qi, vals in enumerate(qret_accum)
    ]

    if spread_rets:
        sr = np.asarray(spread_rets, dtype=float)
        total = float(np.prod(1.0 + sr) - 1.0) * 100.0
        ppy = TRADING_DAYS / holding
        sd = float(sr.std(ddof=0))
        sharpe = float(sr.mean() / sd * np.sqrt(ppy)) if sd > 0 else 0.0
        years = sr.size / ppy
        cagr = ((spread_eq / 100.0) ** (1.0 / years) - 1.0) * 100.0 if years > 0 and spread_eq > 0 else 0.0
        result["spreadStats"] = {
            "totalReturn": round(total, 2),
            "sharpe": round(sharpe, 2),
            "cagr": round(cagr, 2),
        }

    return result
