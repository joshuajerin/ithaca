"""Portfolio construction bridge: real data in, optimal weights out.

This is the honest-coverage assembly layer between the pure-numpy optimizer
(`app/engine/optimize.py`) and the skill/panel surface. It sources every input
from real estimated quantities — no fabricated returns or covariances:

- Covariance ``Sigma`` comes from the multi-factor risk model
  (`factor_model.build` -> `riskmodel.covariance`), the same engine that powers
  the Risk Model pillar.
- Expected returns ``mu`` are factor-model-implied: each name's exposure vector
  dotted with the realized annualized factor premia (X @ f_ann). The exposures
  are the alpha/style factors (Market, Size, Value, Momentum, Volatility,
  Quality) and the premia are estimated from the real cross-sectional panel, so
  this is a genuine signal-based expected-return forecast, not a guess.
- The Black-Litterman market prior uses real market-cap weights and a risk
  aversion implied by the realized market-portfolio return/variance.

Names without enough real history or fundamentals are excluded by the risk model
and reported via the coverage block — never imputed.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from . import data, factor_model, repo, shorting
from .engine import optimize as opt
from .engine import riskmodel

_DEFAULT_UNIVERSE = ["NVDA", "AMD", "AVGO", "MSFT", "GOOGL", "META", "AMZN", "AAPL"]
_UNIVERSE_CAP = 40
_VALID_METHODS = {
    "max_sharpe",
    "min_variance",
    "target_vol",
    "black_litterman",
    "risk_parity",
    "hrp",
}


def _resolve_universe(params: dict) -> Tuple[List[str], str]:
    """Resolve (symbols, label) for the candidate universe to optimize over."""
    raw = params.get("symbols") or []
    syms = [s.upper() for s in raw if repo.get_company(s.upper())]
    if syms:
        return syms[:_UNIVERSE_CAP], f"{len(syms)} selected names"

    sector = params.get("sector")
    sid = repo.resolve_sector(sector) if sector else None
    if sid:
        sec_syms = repo.symbols_in_sector(sid)
        if len(sec_syms) >= 3:
            return sec_syms[:_UNIVERSE_CAP], repo.sector_name(sid)

    return list(_DEFAULT_UNIVERSE), "Core large-cap universe"


def _build_constraints(params: dict, n: int) -> Tuple[opt.Constraints, List[str]]:
    """Build the constraint set and a list of human-readable diagnostics.

    Diagnostics are returned (not silently swallowed) whenever a requested limit
    is infeasible for the universe and has to be relaxed to keep the problem
    solvable, so the panel/voice can honestly report what was changed.
    """
    notes: List[str] = []
    long_only = not bool(params.get("long_short") or params.get("allow_short"))
    net = 1.0
    if not long_only and params.get("market_neutral"):
        net = 0.0
    net = float(params.get("net", net))

    # Per-name cap: a cap below |net|/n can never sum to net, so we must relax it
    # to stay feasible — but we report the relaxation rather than hiding it.
    raw_cap = params.get("max_position")
    floor = abs(net) / n * 1.05 if n else 1.0
    requested_cap: Optional[float] = None
    if raw_cap is not None:
        requested_cap = float(raw_cap)
        max_pos = max(requested_cap, floor)
        if max_pos > requested_cap + 1e-9:
            notes.append(
                f"Max position {requested_cap*100:.1f}% is infeasible across "
                f"{n} names (cannot sum to {net*100:.0f}% net); relaxed to "
                f"{max_pos*100:.1f}%."
            )
    else:
        max_pos = max(0.35, floor)

    sector_caps: Dict[str, float] = {}
    explicit = params.get("sector_caps")
    if isinstance(explicit, dict):
        for k, v in explicit.items():
            sid = repo.resolve_sector(k) or k
            sector_caps[str(sid)] = float(v)
    max_sector = params.get("max_sector")
    if max_sector is not None:
        # Applied per-sector at assembly time once we know which sectors exist.
        sector_caps["__all__"] = float(max_sector)

    # Gross budget: sum|w| >= |net| is a hard identity, so a gross below |net|
    # can never be satisfied. Relax it to |net| and report rather than letting
    # the projection silently violate the requested limit.
    gross = params.get("gross_limit")
    gross_val = float(gross) if gross is not None else None
    if gross_val is not None and gross_val < abs(net) - 1e-9:
        notes.append(
            f"Gross budget {gross_val*100:.0f}% is below net exposure "
            f"{abs(net)*100:.0f}% (gross can never be smaller than |net|); "
            f"raised to {abs(net)*100:.0f}%."
        )
        gross_val = abs(net)

    cons = opt.Constraints(
        long_only=long_only,
        max_position=max_pos,
        net=net,
        gross=gross_val,
        sector_caps=sector_caps,
        turnover_penalty=float(params.get("turnover_penalty", 0.0)),
    )
    cons.requested_max_position = requested_cap  # type: ignore[attr-defined]
    return cons, notes


def _reconcile_method(method: str, cons: opt.Constraints) -> Tuple[opt.Constraints, List[str]]:
    """Force constraint sets that are incompatible with a method into a sane shape.

    Risk parity (ERC) and HRP allocate a *positive* risk budget across names —
    they are inherently long-only and fully invested. Honouring a short /
    market-neutral (net=0) request would collapse the projection onto
    {w>=0, sum=0} to an all-zero, degenerate portfolio. So we override to
    long-only net=1 for these methods and report the override.
    """
    notes: List[str] = []
    if method in ("risk_parity", "hrp"):
        if (not cons.long_only) or abs(cons.net - 1.0) > 1e-9:
            label = "Risk parity" if method == "risk_parity" else "Hierarchical risk parity"
            notes.append(
                f"{label} is a long-only, fully-invested method; the requested "
                "short / market-neutral exposure was ignored."
            )
            cons.long_only = True
            cons.net = 1.0
            cons.gross = None
    return cons, notes


def _expand_sector_caps(cons: opt.Constraints, sectors: List[str]) -> opt.Constraints:
    """Turn a blanket ``__all__`` cap into an explicit per-present-sector cap."""
    if "__all__" not in cons.sector_caps:
        return cons
    blanket = cons.sector_caps.pop("__all__")
    for sid in set(sectors):
        cons.sector_caps.setdefault(str(sid), blanket)
    return cons


def _current_book(params: dict, symbols: List[str]) -> Optional[np.ndarray]:
    """Align the existing book (name->weight) to the optimization order, or None."""
    cur = params.get("current") or params.get("current_weights")
    if not isinstance(cur, dict) or not cur:
        return None
    vec = np.zeros(len(symbols), dtype=float)
    pos = {s: i for i, s in enumerate(symbols)}
    for k, v in cur.items():
        u = str(k).upper()
        if u in pos:
            vec[pos[u]] = float(v)
    return vec


def optimize(params: dict) -> Tuple[dict, "factor_model.RiskModelResult", List[str]]:
    """Construct an optimal portfolio from real expected returns + covariance.

    Returns ``(payload, risk_model_result, dropped)`` so the skill layer can
    attach the shared coverage block. Raises ``ValueError`` (surfaced as a clean
    error panel) when the universe cannot be credibly modeled.
    """
    method = str(params.get("method") or "max_sharpe").lower()
    if method not in _VALID_METHODS:
        method = "max_sharpe"

    universe, label = _resolve_universe(params)
    res = factor_model.build(universe)
    model = res.model

    # Restrict the optimization to the requested names that survived modeling.
    pos = {s: i for i, s in enumerate(model.symbols)}
    idx: List[int] = []
    kept: List[str] = []
    dropped: List[str] = []
    for s in universe:
        if s in pos and pos[s] not in idx:
            idx.append(pos[s])
            kept.append(s)
        elif s not in pos:
            dropped.append(s)
    if len(idx) < 2:
        raise ValueError("need at least two modelable names to optimize a portfolio")

    cov = riskmodel.covariance(model, idx)  # annualized (n, n)
    exposures = model.exposures[idx]  # (n, K)
    f_ann = np.array([res.factor_ann_returns[fn] for fn in model.factor_names])
    mu = exposures @ f_ann  # factor-implied annualized expected returns
    rf = float(params.get("risk_free", 0.0))

    # Market-cap weights for the prior / benchmark comparison.
    caps = np.array([float((data.get_company(s) or {}).get("marketCap", 0.0)) for s in kept])
    w_mkt = caps / caps.sum() if caps.sum() > 0 else np.full(len(kept), 1.0 / len(kept))

    sectors = [str((data.get_company(s) or {}).get("sector", "")) for s in kept]
    cons, notes = _build_constraints(params, len(kept))
    cons, method_notes = _reconcile_method(method, cons)
    notes += method_notes
    cons = _expand_sector_caps(cons, sectors)
    current = _current_book(params, kept)

    # Short-availability / borrow-cost awareness: only for genuine long/short
    # books and only for methods that actually solve the utility (mean-variance
    # family / BL). Risk-parity & HRP are long-only by construction and skip it.
    shorting_block: Optional[dict] = None
    if (not cons.long_only) and method not in ("risk_parity", "hrp"):
        prof = shorting.borrow_profile(kept)
        gc_pct, fin_source, fin_asof = shorting.financing_anchor()
        lb = np.full(len(kept), -float(cons.max_position), dtype=float)
        sc = np.zeros(len(kept), dtype=float)
        blocked: List[str] = []
        borrow_rows: List[dict] = []
        for k, s in enumerate(kept):
            p = prof.get(s)
            if not p:
                continue
            if not bool(p.get("shortable", True)):
                lb[k] = 0.0  # locate-infeasible: forbid the short, allow the long
                blocked.append(s)
            sc[k] = float(p.get("feeBps") or 0.0) / 10000.0  # annual borrow drag
            borrow_rows.append({
                "symbol": s,
                "tier": p.get("tier"),
                "tierLabel": p.get("label"),
                "feeBps": p.get("feeBps"),
                "shortable": bool(p.get("shortable", True)),
            })
        cons.lb_override = lb
        cons.short_cost = sc
        if blocked:
            notes.append(
                "Short blocked (locate-infeasible borrow): " + ", ".join(blocked)
                + " — held flat or long-only for those names."
            )
        shorting_block = {
            "financing": {
                "gcRatePct": gc_pct,
                "anchor": "3M U.S. Treasury par yield",
                "source": fin_source,
                "asOf": fin_asof,
            },
            "borrow": sorted(borrow_rows, key=lambda r: (r["feeBps"] or 0.0), reverse=True),
            "blocked": blocked,
            "note": (
                "Optimizer is short-aware: names that can't be borrowed are barred "
                "from the short side and each short pays its modeled borrow fee, so a "
                "name is only shorted when its alpha clears its cost to borrow."
            ),
        }

    bl_prior = None
    if method == "risk_parity":
        w = opt.apply_long_only_constraints(opt.risk_parity(cov), cons, sectors)
        binding = opt._binding(w, cons, sectors)
    elif method == "hrp":
        w = opt.apply_long_only_constraints(opt.hrp(cov), cons, sectors)
        binding = opt._binding(w, cons, sectors)
    elif method == "black_litterman":
        mkt_daily = res.returns[:, idx] @ w_mkt
        mkt_ann_ret = float(mkt_daily.mean() * riskmodel.TRADING_DAYS)
        mkt_ann_var = float(mkt_daily.var(ddof=1) * riskmodel.TRADING_DAYS)
        delta = opt.implied_risk_aversion(mkt_ann_ret, mkt_ann_var, rf)
        conf = float(params.get("view_confidence", 1.0))
        mu_bl, bl_prior = opt.black_litterman(cov, w_mkt, mu, delta=delta, view_confidence=conf, rf=rf)
        mu = mu_bl
        sub_mode = str(params.get("mv_mode") or "max_sharpe").lower()
        if sub_mode not in ("max_sharpe", "min_variance", "target_vol"):
            sub_mode = "max_sharpe"
        result = opt.mean_variance(mu, cov, mode=sub_mode, cons=cons, sectors=sectors,
                                   current=current, rf=rf,
                                   target_vol=float(params.get("target_vol", 0.15)))
        w, binding = result.weights, result.binding
    else:
        result = opt.mean_variance(mu, cov, mode=method, cons=cons, sectors=sectors,
                                   current=current, rf=rf,
                                   target_vol=float(params.get("target_vol", 0.15)))
        w, binding = result.weights, result.binding

    stats = opt.portfolio_stats(w, mu, cov, rf)
    rc = opt.risk_contributions(w, cov)
    factor_tilts = exposures.T @ w  # (K,)

    holdings = []
    for k in range(len(kept)):
        s = kept[k]
        c = data.get_company(s) or {}
        row = {
            "symbol": s,
            "name": c.get("name", s),
            "sector": data.sector_name(sectors[k]) if sectors[k] else "—",
            "weight": round(float(w[k]) * 100.0, 2),
            "benchWeight": round(float(w_mkt[k]) * 100.0, 2),
            "activeWeight": round(float(w[k] - w_mkt[k]) * 100.0, 2),
            "expReturn": round(float(mu[k]) * 100.0, 2),
            "riskContribPct": round(float(rc[k]), 2),
        }
        if current is not None:
            row["currentWeight"] = round(float(current[k]) * 100.0, 2)
            row["trade"] = round(float(w[k] - current[k]) * 100.0, 2)
        if bl_prior is not None:
            row["priorReturn"] = round(float(bl_prior[k]) * 100.0, 2)
        holdings.append(row)
    holdings.sort(key=lambda h: abs(h["weight"]), reverse=True)

    tilts = [
        {"factor": fn, "tilt": round(float(factor_tilts[kk]), 3),
         "factorReturn": round(float(res.factor_ann_returns[fn]) * 100.0, 2)}
        for kk, fn in enumerate(model.factor_names)
    ]

    # Sector allocation (signed for long/short).
    sec_alloc: Dict[str, float] = {}
    for k in range(len(kept)):
        sec_alloc[sectors[k]] = sec_alloc.get(sectors[k], 0.0) + float(w[k])
    sector_alloc = sorted(
        [{"sector": data.sector_name(sid) if sid else "—", "weight": round(v * 100.0, 2)}
         for sid, v in sec_alloc.items()],
        key=lambda x: abs(x["weight"]), reverse=True,
    )

    turnover = None
    if current is not None:
        turnover = round(float(np.abs(w - current).sum()) * 50.0, 2)  # one-way %

    method_labels = {
        "max_sharpe": "Max Sharpe (mean-variance)",
        "min_variance": "Minimum Variance",
        "target_vol": "Target Volatility",
        "black_litterman": "Black-Litterman",
        "risk_parity": "Risk Parity (ERC)",
        "hrp": "Hierarchical Risk Parity",
    }

    requested_cap = getattr(cons, "requested_max_position", None)
    payload = {
        "method": method,
        "methodLabel": method_labels.get(method, method),
        "universeLabel": label,
        "longOnly": cons.long_only,
        "status": "relaxed" if notes else "ok",
        "notes": notes,
        "objective": {
            "expReturn": round(stats["expReturn"] * 100.0, 2),
            "vol": round(stats["vol"] * 100.0, 2),
            "sharpe": round(stats["sharpe"], 2),
            "gross": round(stats["gross"] * 100.0, 1),
            "net": round(stats["net"] * 100.0, 1),
            "nHoldings": int(np.sum(np.abs(w) > 1e-4)),
        },
        "constraints": {
            "maxPosition": round(cons.max_position * 100.0, 1),
            "requestedMaxPosition": None if requested_cap is None else round(requested_cap * 100.0, 1),
            "longOnly": cons.long_only,
            "net": round(cons.net * 100.0, 1),
            "gross": round(cons.gross_limit() * 100.0, 1),
            "sectorCaps": {
                (data.sector_name(k) if repo.resolve_sector(k) else k): round(v * 100.0, 1)
                for k, v in cons.sector_caps.items()
            },
            "turnoverPenalty": cons.turnover_penalty,
            "binding": binding,
        },
        "holdings": holdings,
        "factorTilts": tilts,
        "sectorAllocation": sector_alloc,
        "turnover": turnover,
        "blDelta": None if bl_prior is None else round(float(opt.implied_risk_aversion(
            float((res.returns[:, idx] @ w_mkt).mean() * riskmodel.TRADING_DAYS),
            float((res.returns[:, idx] @ w_mkt).var(ddof=1) * riskmodel.TRADING_DAYS), rf)), 2),
    }
    if shorting_block is not None:
        # Add the realized Reg-T margin / leverage profile of the *solved* book so
        # the panel can show leverage + any breach alongside the borrow detail.
        long_mv = float(np.sum(w[w > 0]))
        short_mv = float(-np.sum(w[w < 0]))
        shorting_block["margin"] = opt_margin(long_mv, short_mv)
        payload["shorting"] = shorting_block
    return payload, res, dropped


def opt_margin(long_frac: float, short_frac: float) -> dict:
    """Reg-T margin / leverage profile for a book expressed as NAV fractions.

    The optimizer works in weight space (fractions of NAV), so we scale by a
    notional $1 of equity and read the engine's margin profile; leverage and
    utilization are scale-free, so the absolute notional is irrelevant here.
    """
    from .engine import borrow
    m = borrow.margin_profile(long_frac, short_frac, 1.0)
    return {
        "grossLeverage": round(m["grossLeverage"], 3),
        "netLeverage": round(m["netLeverage"], 3),
        "maintenancePct": round(m["maintenanceMargin"] * 100.0, 2),
        "excessLiquidityPct": round(m["excessLiquidity"] * 100.0, 2),
        "breach": bool(m["breach"]),
        "warnings": m["warnings"],
    }
