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


def _prep_series(
    series_by_symbol: Dict[str, Sequence[dict]],
    horizons: Sequence[int],
    holding: int,
) -> Tuple[Dict[str, dict], List[dict], List[int]]:
    """Clean each name's close series and precompute its forward returns.

    Returns ``(per, excluded, horizons)`` where ``per[sym]`` carries the dates,
    closes, per-horizon forward returns and a date->index map (but no signal
    yet). Names with too little history are dropped and reported, never imputed.
    """
    horizons = sorted({int(h) for h in horizons if int(h) >= 1})
    if int(holding) not in horizons:
        horizons = sorted(set(horizons) | {int(holding)})

    per: Dict[str, dict] = {}
    excluded: List[dict] = []
    for sym, points in series_by_symbol.items():
        dates, closes = _clean_series(points)
        if closes.size < 5:
            excluded.append({"symbol": sym, "reason": "insufficient price history"})
            continue
        n = closes.size
        fret: Dict[int, np.ndarray] = {}
        for h in horizons:
            fr = np.full(n, np.nan, dtype=float)
            if h < n:
                fr[: n - h] = closes[h:] / closes[: n - h] - 1.0
            fret[h] = fr
        per[sym] = {
            "dates": dates,
            "closes": closes,
            "sig": None,
            "fret": fret,
            "date_idx": {d: i for i, d in enumerate(dates)},
        }
    return per, excluded, horizons


def _score_panel(
    per: Dict[str, dict],
    *,
    signal: str,
    label: str,
    horizons: List[int],
    holding: int,
    quantiles: int,
    ic_stride: int,
    min_names: int,
    excluded: List[dict],
) -> dict:
    """Score a prepared cross-section (each ``per[sym]`` must carry a ``sig``).

    This is the shared rank-IC / IC-decay / quantile-spread / turnover block used
    by both single-signal evaluation and the blended composite alpha, so a
    composite is measured with the *exact same* scorecard as its components.
    """
    quantiles = max(2, int(quantiles))
    min_names = max(quantiles, int(min_names))
    included = list(per.keys())
    result: dict = {
        "signal": signal,
        "label": label,
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
    per, excluded, horizons = _prep_series(series_by_symbol, horizons, holding)
    for sym in list(per.keys()):
        P = per[sym]
        ctx = dict(ctx_by_symbol.get(sym) or {})
        sig = np.asarray(fn(P["closes"], ctx), dtype=float)
        if not np.isfinite(sig).any():
            reason = "missing fundamental" if SIGNAL_META.get(signal, {}).get("kind") == "fundamental" else "signal not computable"
            excluded.append({"symbol": sym, "reason": reason})
            del per[sym]
        else:
            P["sig"] = sig
    label = SIGNAL_META.get(signal, {}).get("label", signal)
    return _score_panel(
        per,
        signal=signal,
        label=label,
        horizons=horizons,
        holding=holding,
        quantiles=quantiles,
        ic_stride=ic_stride,
        min_names=min_names,
        excluded=excluded,
    )


# ----------------------------- alpha combination -----------------------------
COMBINE_METHODS = {
    "equal_weight": "Equal Weight",
    "ic_weighted": "IC-Weighted",
    "inverse_correlation": "Inverse-Correlation (Risk-Weighted)",
}


def normalize_combine_method(method: Optional[str]) -> str:
    """Resolve a free-text combination method to a registered key."""
    if not method:
        return "equal_weight"
    key = str(method).strip().lower().replace("-", "_").replace(" ", "_")
    if key in COMBINE_METHODS:
        return key
    if any(w in key for w in ("ic_weight", "icweight", "ic_ir", "information_coefficient")):
        return "ic_weighted"
    if any(w in key for w in ("inverse", "inv_corr", "risk_weight", "risk_parity", "correlation", "decorrel", "diversif")):
        return "inverse_correlation"
    if any(w in key for w in ("equal", "naive", "1_n", "1n", "uniform")):
        return "equal_weight"
    return "equal_weight"


def _component_per(per: Dict[str, dict], comp: str) -> Tuple[Dict[str, dict], List[dict]]:
    """Slice a prepared cross-section down to one component signal's own sig,
    dropping (and reporting) names where that component is not computable."""
    sub: Dict[str, dict] = {}
    excluded: List[dict] = []
    for sym, P in per.items():
        sig = P["comp_raw"][comp]
        if np.isfinite(sig).any():
            sub[sym] = {
                "dates": P["dates"],
                "closes": P["closes"],
                "fret": P["fret"],
                "date_idx": P["date_idx"],
                "sig": sig,
            }
        else:
            reason = "missing fundamental" if SIGNAL_META.get(comp, {}).get("kind") == "fundamental" else "signal not computable"
            excluded.append({"symbol": sym, "reason": reason})
    return sub, excluded


def combine_signals(
    series_by_symbol: Dict[str, Sequence[dict]],
    signals: Sequence[str],
    ctx_by_signal: Optional[Dict[str, Dict[str, dict]]] = None,
    method: str = "equal_weight",
    horizons: Sequence[int] = (1, 5, 10, 21, 42),
    holding: int = 21,
    quantiles: int = 5,
    ic_stride: int = 5,
    min_names: int = 5,
) -> dict:
    """Blend several cross-sectional signals into one composite alpha.

    Each component is standardized cross-sectionally (per-date z-score) so the
    blend is unit-free, then combined by one of three weighting schemes:

    - ``equal_weight``        — naive 1/N.
    - ``ic_weighted``         — proportional to each component's mean rank IC at
                                the holding horizon (floored at 0; falls back to
                                equal weight if no component has positive IC).
    - ``inverse_correlation`` — risk-weighted: inversely proportional to a
                                component's average absolute cross-sectional rank
                                correlation with the others, so redundant signals
                                are down-weighted.

    The composite is scored with the *same* scorecard as its components (rank IC,
    IC decay, quantile spread, turnover) so it is directly comparable, and a
    component overlap (rank-correlation) matrix is returned. Real data only:
    names lacking inputs are excluded and reported, never imputed.

    ``ctx_by_signal[signal][symbol]`` carries per-component context (e.g.
    ``{"fval": ...}`` for value/quality), so fundamentals that share a signal
    function still get their own distinct cross-sectional value.
    """
    method = normalize_combine_method(method)
    norm_signals: List[str] = []
    for s in signals:
        k = normalize_signal(s)
        if k not in norm_signals:
            norm_signals.append(k)
    if not norm_signals:
        norm_signals = ["momentum"]
    ctx_by_signal = ctx_by_signal or {}
    quantiles = max(2, int(quantiles))
    min_names = max(quantiles, int(min_names))
    stride = max(1, int(ic_stride))

    per, excluded, horizons = _prep_series(series_by_symbol, horizons, holding)

    # Raw component signal per name.
    for sym, P in per.items():
        P["comp_raw"] = {}
        for c in norm_signals:
            ctx = dict((ctx_by_signal.get(c) or {}).get(sym) or {})
            P["comp_raw"][c] = np.asarray(SIGNALS[c](P["closes"], ctx), dtype=float)

    all_dates = sorted(set().union(*[set(p["date_idx"].keys()) for p in per.values()])) if per else []
    k = len(norm_signals)

    # Cross-sectional z-score per component per date (unit-free blend inputs).
    for P in per.values():
        P["comp_z"] = {c: np.full(P["closes"].size, np.nan) for c in norm_signals}
    for d in all_dates:
        for c in norm_signals:
            entries: List[Tuple[str, int, float]] = []
            for sym, P in per.items():
                i = P["date_idx"].get(d)
                if i is None:
                    continue
                v = P["comp_raw"][c][i]
                if np.isfinite(v):
                    entries.append((sym, i, float(v)))
            if len(entries) < 2:
                continue
            vals = np.asarray([e[2] for e in entries], dtype=float)
            mean = float(vals.mean())
            sd = float(vals.std())
            for sym, i, v in entries:
                per[sym]["comp_z"][c][i] = (v - mean) / sd if sd > 0 else 0.0

    # Component overlap: averaged per-date cross-sectional rank correlation.
    corr = [[1.0 if a == b else 0.0 for b in range(k)] for a in range(k)]
    pair_acc: Dict[Tuple[int, int], List[float]] = {}
    for di in range(0, len(all_dates), stride):
        d = all_dates[di]
        for a in range(k):
            for b in range(a + 1, k):
                xs: List[float] = []
                ys: List[float] = []
                for P in per.values():
                    i = P["date_idx"].get(d)
                    if i is None:
                        continue
                    va = P["comp_raw"][norm_signals[a]][i]
                    vb = P["comp_raw"][norm_signals[b]][i]
                    if np.isfinite(va) and np.isfinite(vb):
                        xs.append(float(va))
                        ys.append(float(vb))
                if len(xs) >= min_names:
                    c_ab = spearman_ic(xs, ys)
                    if np.isfinite(c_ab):
                        pair_acc.setdefault((a, b), []).append(c_ab)
    for (a, b), vals in pair_acc.items():
        m = round(float(np.mean(vals)), 3)
        corr[a][b] = m
        corr[b][a] = m

    # Score each component on its own (also yields IC for IC-weighting).
    component_results: Dict[str, dict] = {}
    for c in norm_signals:
        sub, _ex = _component_per(per, c)
        component_results[c] = _score_panel(
            sub,
            signal=c,
            label=SIGNAL_META.get(c, {}).get("label", c),
            horizons=horizons,
            holding=holding,
            quantiles=quantiles,
            ic_stride=stride,
            min_names=min_names,
            excluded=[],
        )

    # Blend weights.
    if method == "ic_weighted":
        raw = {c: max(float(component_results[c]["ic"]["mean"]), 0.0) for c in norm_signals}
        tot = sum(raw.values())
        weights = {c: raw[c] / tot for c in norm_signals} if tot > 0 else {c: 1.0 / k for c in norm_signals}
    elif method == "inverse_correlation":
        raw = {}
        for a, c in enumerate(norm_signals):
            offs = [abs(corr[a][b]) for b in range(k) if b != a]
            avg = float(np.mean(offs)) if offs else 0.0
            raw[c] = 1.0 / (avg + 0.10)
        tot = sum(raw.values())
        weights = {c: raw[c] / tot for c in norm_signals} if tot > 0 else {c: 1.0 / k for c in norm_signals}
    else:
        weights = {c: 1.0 / k for c in norm_signals}

    # Composite alpha: weighted sum of standardized components. Real data only —
    # STRICT eligibility: a name/date contributes to the composite only when
    # EVERY selected component is available there. Names that lack any selected
    # component's input (e.g. a missing fundamental) are excluded and reported,
    # never imputed, so the composite is scored on the strict intersection
    # universe of the chosen signals.
    comp_per: Dict[str, dict] = {}
    comp_excluded: List[dict] = list(excluded)
    for sym, P in per.items():
        n = P["closes"].size
        sig = np.full(n, np.nan, dtype=float)
        any_finite = False
        for i in range(n):
            zs = [P["comp_z"][c][i] for c in norm_signals]
            if all(np.isfinite(z) for z in zs):
                sig[i] = float(sum(weights[c] * z for c, z in zip(norm_signals, zs)))
                any_finite = True
        if any_finite:
            comp_per[sym] = {
                "dates": P["dates"],
                "closes": P["closes"],
                "fret": P["fret"],
                "date_idx": P["date_idx"],
                "sig": sig,
            }
        else:
            # Report which selected components the name lacks entirely so the
            # exclusion is auditable rather than silent.
            missing = [
                SIGNAL_META.get(c, {}).get("label", c)
                for c in norm_signals
                if not np.isfinite(P["comp_z"][c]).any()
            ]
            reason = (
                "missing inputs for " + ", ".join(missing)
                if missing
                else "no date where all selected signals overlap"
            )
            comp_excluded.append({"symbol": sym, "reason": reason})

    comp_res = _score_panel(
        comp_per,
        signal="composite",
        label="Composite Alpha",
        horizons=horizons,
        holding=holding,
        quantiles=quantiles,
        ic_stride=stride,
        min_names=min_names,
        excluded=comp_excluded,
    )

    components = []
    for c in norm_signals:
        res = component_results[c]
        components.append({
            "signal": c,
            "label": res["label"],
            "weight": round(weights[c], 4),
            "meanIC": res["ic"]["mean"],
            "icIR": res["ic"]["ir"],
            "tStat": res["ic"]["tStat"],
            "hitRate": res["ic"]["hitRate"],
            "turnover": res["turnover"],
            "spreadReturn": res["spreadStats"]["totalReturn"],
            "spreadSharpe": res["spreadStats"]["sharpe"],
            "included": len(res["included"]),
            "spreadCurve": [p["value"] for p in res["spread"]],
        })

    composite = {
        "label": comp_res["label"],
        "ic": comp_res["ic"],
        "decay": comp_res["decay"],
        "quantileReturns": comp_res["quantileReturns"],
        "spread": comp_res["spread"],
        "spreadStats": comp_res["spreadStats"],
        "turnover": comp_res["turnover"],
        "turnoverAnnual": comp_res["turnoverAnnual"],
        "rebalances": comp_res["rebalances"],
        "included": len(comp_res["included"]),
    }

    return {
        "method": method,
        "methodLabel": COMBINE_METHODS[method],
        "signals": norm_signals,
        "holding": int(holding),
        "quantiles": quantiles,
        "horizons": list(horizons),
        "weights": [
            {"signal": c, "label": SIGNAL_META.get(c, {}).get("label", c), "weight": round(weights[c], 4)}
            for c in norm_signals
        ],
        "correlation": {
            "signals": norm_signals,
            "labels": [SIGNAL_META.get(c, {}).get("label", c) for c in norm_signals],
            "matrix": corr,
        },
        "components": components,
        "composite": composite,
        "included": comp_res["included"],
        "excluded": comp_excluded,
    }
