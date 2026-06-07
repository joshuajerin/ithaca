"""Signal-driven portfolio construction.

Turns a cross-sectional alpha signal into an actual, tradeable book and measures
its *realized* performance. Given each name's close series and the signal value,
it ranks the cross-section at every rebalance, forms a portfolio under a simple
construction scheme (equal-weight top quantile, or a dollar-neutral long-short
quantile spread), holds it for `holding` bars, and compounds the realized daily
book return into an equity curve.

Performance/risk statistics are computed with the shared ``stats`` module — the
exact same Sharpe / CAGR / drawdown / VaR block the single-name backtest panel
uses — so a portfolio's numbers are directly comparable to a backtest's.

Pure numpy + stdlib (no DB / network): callers source the price series and the
fundamental context and own the live/mock provenance decision, mirroring the
signal research engine.

No-lookahead guarantee: weights chosen on date d use only the signal known at d
(itself backward-looking) and take effect for returns on d+1 onward. The book
held *into* bar i is therefore always the book decided at the prior rebalance.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import stats
from .signals import SIGNAL_META, SIGNALS, normalize_signal

TRADING_DAYS = 252

SCHEMES = {
    "top_quantile": "Equal-Weight Top Quantile",
    "long_short": "Long-Short Quantile Spread",
}


def normalize_scheme(scheme: Optional[str]) -> str:
    """Resolve a free-text construction scheme to a registered key."""
    if not scheme:
        return "top_quantile"
    key = str(scheme).strip().lower().replace("-", "_").replace(" ", "_")
    if key in SCHEMES:
        return key
    if any(w in key for w in ("long_short", "longshort", "spread", "ls", "neutral", "hedged")):
        return "long_short"
    if any(w in key for w in ("top", "long_only", "longonly", "quantile", "decile", "bucket")):
        return "top_quantile"
    return "top_quantile"


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


def construct_portfolio(
    series_by_symbol: Dict[str, Sequence[dict]],
    signal: str = "momentum",
    ctx_by_symbol: Optional[Dict[str, dict]] = None,
    scheme: str = "top_quantile",
    quantiles: int = 5,
    holding: int = 21,
    min_names: int = 5,
    cost_bps: float = 5.0,
    rebase: float = 100.0,
) -> dict:
    """Build a portfolio from one signal and backtest its realized performance.

    Returns a dict with the latest book (per-name side/weight/score), the realized
    equity curve vs an equal-weight benchmark, a drawdown series, the full
    performance stat block, turnover, and the included / excluded coverage so the
    panel can report it honestly (names without a usable signal are never imputed).
    """
    signal = normalize_signal(signal)
    fn = SIGNALS[signal]
    ctx_by_symbol = ctx_by_symbol or {}
    scheme = normalize_scheme(scheme)
    quantiles = max(2, int(quantiles))
    holding = max(1, int(holding))
    min_names = max(quantiles, int(min_names))
    cost_rate = max(0.0, float(cost_bps)) / 10000.0

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
        dr = np.zeros(closes.size, dtype=float)
        dr[1:] = closes[1:] / closes[:-1] - 1.0
        per[sym] = {
            "closes": closes,
            "sig": sig,
            "dr": dr,
            "date_idx": {d: i for i, d in enumerate(dates)},
        }

    included = list(per.keys())
    result: dict = {
        "signal": signal,
        "label": SIGNAL_META.get(signal, {}).get("label", signal),
        "scheme": scheme,
        "schemeLabel": SCHEMES[scheme],
        "holding": holding,
        "quantiles": quantiles,
        "rebalances": 0,
        "longCount": 0,
        "shortCount": 0,
        "gross": 0.0,
        "net": 0.0,
        "holdings": [],
        "curve": [],
        "drawdown": [],
        "stats": stats.performance_stats(np.asarray([rebase]), np.asarray([])),
        "benchStats": stats.performance_stats(np.asarray([rebase]), np.asarray([])),
        "turnover": 0.0,
        "turnoverAnnual": 0.0,
        "included": included,
        "includedCount": len(included),
        "excluded": excluded,
    }
    if len(per) < min_names:
        return result

    all_dates = sorted(set().union(*[set(p["date_idx"].keys()) for p in per.values()]))
    n = len(all_dates)
    rebalance_set = set(range(0, n, holding))

    def weights_at(d: str) -> Tuple[Optional[Dict[str, float]], List[dict]]:
        rows: List[Tuple[str, float]] = []
        for sym, P in per.items():
            i = P["date_idx"].get(d)
            if i is None:
                continue
            s = P["sig"][i]
            if np.isfinite(s):
                rows.append((sym, float(s)))
        if len(rows) < min_names:
            return None, []
        rows.sort(key=lambda r: r[1])  # ascending by signal
        idx = np.array_split(np.arange(len(rows)), quantiles)
        top = [rows[int(k)] for k in idx[-1]]
        bot = [rows[int(k)] for k in idx[0]]
        w: Dict[str, float] = {}
        holdings: List[dict] = []
        lw = 1.0 / len(top)
        for sym, sv in top:
            w[sym] = w.get(sym, 0.0) + lw
            holdings.append({"symbol": sym, "side": "long", "weight": round(lw, 4), "score": round(sv, 4)})
        if scheme == "long_short" and bot:
            sw = -1.0 / len(bot)
            for sym, sv in bot:
                w[sym] = w.get(sym, 0.0) + sw
                holdings.append({"symbol": sym, "side": "short", "weight": round(sw, 4), "score": round(sv, 4)})
        return w, holdings

    def book_return(d: str, book: Dict[str, float]) -> float:
        r = 0.0
        for sym, wt in book.items():
            P = per.get(sym)
            if not P:
                continue
            i = P["date_idx"].get(d)
            if i is None or i == 0:
                continue
            r += wt * float(P["dr"][i])
        return r

    def bench_return(d: str) -> float:
        vals: List[float] = []
        for P in per.values():
            i = P["date_idx"].get(d)
            if i is None or i == 0:
                continue
            vals.append(float(P["dr"][i]))
        return float(np.mean(vals)) if vals else 0.0

    held: Dict[str, float] = {}
    last_holdings: List[dict] = []
    prev_top: Optional[set] = None
    turnovers: List[float] = []
    n_rebal = 0

    w0, h0 = weights_at(all_dates[0])
    if w0 is not None:
        held, last_holdings = w0, h0
        prev_top = {s for s, wt in w0.items() if wt > 0}
        n_rebal += 1

    equity = float(rebase)
    bench_eq = float(rebase)
    peak = equity
    curve: List[dict] = [{"t": all_dates[0], "strategy": round(equity, 2), "benchmark": round(bench_eq, 2)}]
    dd_list: List[dict] = [{"t": all_dates[0], "dd": 0.0}]
    port_rets: List[float] = []

    for k in range(1, n):
        d = all_dates[k]
        r = book_return(d, held) if held else 0.0
        cost = 0.0
        if k in rebalance_set:
            new_w, new_h = weights_at(d)
            if new_w is not None:
                syms = set(new_w) | set(held)
                churn = sum(abs(new_w.get(s, 0.0) - held.get(s, 0.0)) for s in syms)
                cost = cost_rate * churn
                top_set = {s for s, wt in new_w.items() if wt > 0}
                if prev_top is not None and top_set:
                    turnovers.append(len(top_set - prev_top) / len(top_set))
                prev_top = top_set
                held, last_holdings = new_w, new_h
                n_rebal += 1
        net_r = r - cost
        equity *= 1.0 + net_r
        bench_eq *= 1.0 + bench_return(d)
        peak = max(peak, equity)
        ddv = (equity - peak) / peak * 100.0 if peak > 0 else 0.0
        port_rets.append(net_r)
        curve.append({"t": d, "strategy": round(equity, 2), "benchmark": round(bench_eq, 2)})
        dd_list.append({"t": d, "dd": round(ddv, 3)})

    eq_arr = np.asarray([c["strategy"] for c in curve], dtype=float)
    ret_arr = np.asarray(port_rets, dtype=float)
    bench_arr = np.asarray([c["benchmark"] for c in curve], dtype=float)
    bench_ret = np.zeros(bench_arr.size, dtype=float)
    if bench_arr.size >= 2:
        bench_ret[1:] = bench_arr[1:] / bench_arr[:-1] - 1.0

    t_mean = float(np.mean(turnovers)) * 100.0 if turnovers else 0.0
    turnover_annual = t_mean * (TRADING_DAYS / holding)

    longs = [h for h in last_holdings if h["side"] == "long"]
    shorts = [h for h in last_holdings if h["side"] == "short"]
    longs.sort(key=lambda h: h["score"], reverse=True)
    shorts.sort(key=lambda h: h["score"])
    ordered = longs + shorts
    gross = float(sum(abs(h["weight"]) for h in ordered))
    net = float(sum(h["weight"] for h in ordered))

    result.update({
        "rebalances": n_rebal,
        "longCount": len(longs),
        "shortCount": len(shorts),
        "gross": round(gross, 3),
        "net": round(net, 3),
        "holdings": ordered,
        "curve": curve,
        "drawdown": dd_list,
        "stats": stats.performance_stats(eq_arr, ret_arr, turnover=round(turnover_annual / 100.0, 2)),
        "benchStats": stats.performance_stats(bench_arr, bench_ret),
        "turnover": round(t_mean, 1),
        "turnoverAnnual": round(turnover_annual, 1),
    })
    return result
