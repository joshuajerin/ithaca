"""Execution simulation & transaction-cost analysis (TCA) engine.

Pure, deterministic functions (numpy / stdlib only, no DB or network) that:

  * diff a current book against target weights to produce a list of orders;
  * simulate VWAP / TWAP / POV executions against a **real** intraday volume
    profile, returning the average fill, the child-order schedule and the fill
    rate;
  * estimate market impact with the published square-root law applied to real
    volume + real daily volatility — clearly a *model* estimate, not a realized
    fill;
  * compute TCA metrics (implementation shortfall vs the arrival price, slippage
    vs the interval VWAP) in basis points, signed so a positive number always
    means a cost regardless of side.

Callers (the skill builders) own sourcing the real intraday bars / daily vol /
ADV and the live-vs-unavailable decision. This module never fabricates volume:
handed an empty or zero-volume profile it raises rather than inventing fills, so
an order with no real intraday data is reported unsupported upstream.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence

import numpy as np

# Square-root market-impact coefficient (Almgren-style; Y ~ 1).
DEFAULT_IMPACT_COEF = 1.0
# Default participation rate for the POV algo (10% of interval volume).
DEFAULT_POV_RATE = 0.10
# Minimum tradable order before we bother emitting it.
_MIN_SHARES = 1.0

ALGOS = ("vwap", "twap", "pov")


def side_sign(side: str) -> int:
    """+1 for a buy, -1 for a sell. A buy paying above the benchmark is a cost;
    a sell printing below the benchmark is a cost — multiplying by this sign
    makes a positive bps figure always mean 'cost' regardless of direction."""
    return -1 if str(side).lower() == "sell" else 1


# ----------------------------- order generation -----------------------------
def generate_orders(
    targets: Dict[str, float],
    currents: Dict[str, float],
    prices: Dict[str, float],
    capital: float,
) -> List[dict]:
    """Diff current weights against target weights into a list of orders.

    ``targets`` / ``currents`` map a symbol to a weight *fraction* (0.05 = 5%);
    ``prices`` maps a symbol to its reference price; ``capital`` is the book's
    value in USD. Returns one record per name whose weight actually changes:
    ``{symbol, side, shares, notional, price, targetWeight, currentWeight,
    deltaWeight}`` (weights in %). Names without a usable price are skipped (the
    caller reports them); sub-share deltas are dropped as no-ops.
    """
    syms: List[str] = []
    for s in list(targets.keys()) + list(currents.keys()):
        u = (s or "").upper()
        if u and u not in syms:
            syms.append(u)

    out: List[dict] = []
    for s in syms:
        px = prices.get(s)
        if not px or px <= 0:
            continue
        tw = float(targets.get(s, 0.0))
        cw = float(currents.get(s, 0.0))
        dw = tw - cw
        delta_notional = dw * capital
        shares = delta_notional / px
        if abs(shares) < _MIN_SHARES:
            continue
        out.append({
            "symbol": s,
            "side": "buy" if shares > 0 else "sell",
            "shares": abs(shares),
            "notional": abs(delta_notional),
            "price": float(px),
            "targetWeight": round(tw * 100.0, 2),
            "currentWeight": round(cw * 100.0, 2),
            "deltaWeight": round(dw * 100.0, 2),
        })
    out.sort(key=lambda o: o["notional"], reverse=True)
    return out


def estimate_trade_costs(
    orders: Sequence[dict],
    advs: Dict[str, float],
    daily_vols: Dict[str, float],
    coef: float = DEFAULT_IMPACT_COEF,
) -> tuple:
    """Attach the modeled square-root market-impact cost to each order.

    ``advs`` / ``daily_vols`` map a symbol to its average daily volume (shares)
    and daily return volatility (a fraction, 0.02 = 2%). For each order with a
    usable ADV + daily vol the impact is the published square-root law; the per
    order dollar cost is ``impactBps/1e4 · notional``. Orders whose ADV or vol is
    genuinely missing (<= 0) are flagged ``costSupported: False`` with a reason
    rather than assigned a fabricated cost — the caller reports them.

    Returns ``(enriched_orders, aggregate)`` where the aggregate carries the
    supported/unsupported counts, gross notional, the notional-weighted impact in
    bps and the summed dollar cost. This is the reusable diff -> cost step shared
    by the optimizer's cost-aware construction and the rebalancing pipeline.
    """
    enriched: List[dict] = []
    total_cost = 0.0
    gross = 0.0
    supported = 0
    for o in orders:
        sym = (o.get("symbol") or "").upper()
        shares = float(o.get("shares") or 0.0)
        notional = float(o.get("notional") or 0.0)
        adv = float(advs.get(sym, 0.0) or 0.0)
        dv = float(daily_vols.get(sym, 0.0) or 0.0)
        row = dict(o)
        if adv > 0 and dv > 0 and shares > 0:
            bps = square_root_impact(shares, adv, dv, coef)
            cost = bps / 1e4 * notional
            row.update({
                "costSupported": True,
                "impactBps": bps,
                "costUsd": cost,
                "adv": adv,
                "dailyVol": dv,
            })
            total_cost += cost
            gross += notional
            supported += 1
        else:
            row.update({
                "costSupported": False,
                "impactBps": 0.0,
                "costUsd": 0.0,
                "reason": "no real ADV / daily vol to model impact",
            })
        enriched.append(row)

    agg = {
        "orderCount": len(enriched),
        "supportedCount": supported,
        "unsupportedCount": len(enriched) - supported,
        "grossNotional": gross,
        "totalCostUsd": total_cost,
        "impactBps": (total_cost / gross * 1e4) if gross > 0 else 0.0,
    }
    return enriched, agg


# ----------------------------- intraday helpers -----------------------------
def _typical(bar: dict) -> float:
    """Typical price (H+L+C)/3, falling back to whatever fields exist."""
    vals = [bar.get(k) for k in ("h", "l", "c")]
    vals = [float(v) for v in vals if v is not None]
    if vals:
        return sum(vals) / len(vals)
    o = bar.get("o")
    return float(o) if o is not None else 0.0


def has_real_volume(bars: Sequence[dict]) -> bool:
    """True only when there are >=2 bars carrying genuine (positive) volume."""
    if not bars or len(bars) < 2:
        return False
    return sum(float(b.get("v") or 0.0) for b in bars) > 0.0


def arrival_price(bars: Sequence[dict]) -> float:
    """Decision/arrival price = the first bar's open (the price at the moment
    the order arrives at the desk)."""
    b0 = bars[0]
    o = b0.get("o")
    return float(o) if o is not None else _typical(b0)


def interval_vwap(bars: Sequence[dict]) -> float:
    """Volume-weighted average price over the whole execution window — a real
    benchmark computed straight from the intraday bars."""
    num = 0.0
    den = 0.0
    for b in bars:
        v = float(b.get("v") or 0.0)
        num += _typical(b) * v
        den += v
    if den <= 0:
        prices = [_typical(b) for b in bars]
        return sum(prices) / len(prices) if prices else 0.0
    return num / den


def daily_vol_from_closes(closes: Sequence[float]) -> float:
    """Daily return volatility (a fraction, e.g. 0.02 = 2%) from a real close
    series. Defensive on short input."""
    c = np.asarray([x for x in closes if x is not None], dtype=float)
    c = c[np.isfinite(c)]
    if c.size < 3:
        return 0.0
    rets = np.diff(c) / c[:-1]
    rets = rets[np.isfinite(rets)]
    if rets.size < 2:
        return 0.0
    return float(rets.std(ddof=0))


# ----------------------------- execution algos -----------------------------
def _result(algo: str, schedule: List[dict], shares: float,
            arrival: float, ivwap: float, side: str) -> dict:
    filled = sum(s["childShares"] for s in schedule)
    if filled <= 0:
        avg_fill = arrival
    else:
        avg_fill = sum(s["childShares"] * s["price"] for s in schedule) / filled
    sign = side_sign(side)
    is_bps = sign * (avg_fill - arrival) / arrival * 1e4 if arrival else 0.0
    vwap_slip_bps = sign * (avg_fill - ivwap) / ivwap * 1e4 if ivwap else 0.0
    return {
        "algo": algo,
        "avgFill": avg_fill,
        "fillRate": (filled / shares) if shares > 0 else 0.0,
        "isBps": is_bps,
        "vwapSlipBps": vwap_slip_bps,
        "schedule": schedule,
    }


def simulate_vwap(bars: Sequence[dict], shares: float, side: str,
                  arrival: float, ivwap: float) -> dict:
    """VWAP algo: spread the order across buckets in proportion to each bucket's
    real volume, filling at each bucket's typical price."""
    vols = np.array([float(b.get("v") or 0.0) for b in bars], dtype=float)
    total_v = float(vols.sum())
    if total_v <= 0:
        raise ValueError("no volume to schedule a VWAP execution against")
    schedule: List[dict] = []
    cum = 0.0
    for i, b in enumerate(bars):
        mv = float(vols[i])
        child = shares * (mv / total_v)
        cum += child
        price = _typical(b)
        schedule.append({
            "time": _bar_time(b),
            "price": price,
            "marketVolume": mv,
            "childShares": child,
            "participation": (child / mv) if mv > 0 else 0.0,
            "cumPct": (cum / shares) if shares > 0 else 0.0,
        })
    return _result("vwap", schedule, shares, arrival, ivwap, side)


def simulate_twap(bars: Sequence[dict], shares: float, side: str,
                  arrival: float, ivwap: float) -> dict:
    """TWAP algo: equal child orders in every bucket, filling at the bucket's
    typical price (time-sliced, ignores the volume shape)."""
    n = len(bars)
    if n == 0:
        raise ValueError("no bars to schedule a TWAP execution against")
    per = shares / n
    schedule: List[dict] = []
    cum = 0.0
    for b in bars:
        mv = float(b.get("v") or 0.0)
        cum += per
        price = _typical(b)
        schedule.append({
            "time": _bar_time(b),
            "price": price,
            "marketVolume": mv,
            "childShares": per,
            "participation": (per / mv) if mv > 0 else 0.0,
            "cumPct": (cum / shares) if shares > 0 else 0.0,
        })
    return _result("twap", schedule, shares, arrival, ivwap, side)


def simulate_pov(bars: Sequence[dict], shares: float, side: str,
                 arrival: float, ivwap: float,
                 pov_rate: float = DEFAULT_POV_RATE) -> dict:
    """POV (participation-of-volume) algo: take a fixed fraction ``pov_rate`` of
    each bucket's real volume until the order is done. May not complete inside
    the window — the returned ``fillRate`` is then < 1 and the residual is left
    unfilled (never forced)."""
    if pov_rate <= 0:
        raise ValueError("pov_rate must be positive")
    remaining = shares
    schedule: List[dict] = []
    cum = 0.0
    for b in bars:
        mv = float(b.get("v") or 0.0)
        child = min(remaining, pov_rate * mv) if mv > 0 else 0.0
        remaining -= child
        cum += child
        price = _typical(b)
        schedule.append({
            "time": _bar_time(b),
            "price": price,
            "marketVolume": mv,
            "childShares": child,
            "participation": (child / mv) if mv > 0 else 0.0,
            "cumPct": (cum / shares) if shares > 0 else 0.0,
        })
    return _result("pov", schedule, shares, arrival, ivwap, side)


def simulate_all(bars: Sequence[dict], shares: float, side: str,
                 pov_rate: float = DEFAULT_POV_RATE) -> dict:
    """Run all three algos against the same real intraday profile.

    Returns ``{arrival, intervalVwap, algos: {vwap, twap, pov}}``. Raises
    ``ValueError`` if the profile has no real volume to schedule against.
    """
    if not has_real_volume(bars):
        raise ValueError("intraday profile has no real volume")
    arrival = arrival_price(bars)
    ivwap = interval_vwap(bars)
    return {
        "arrival": arrival,
        "intervalVwap": ivwap,
        "algos": {
            "vwap": simulate_vwap(bars, shares, side, arrival, ivwap),
            "twap": simulate_twap(bars, shares, side, arrival, ivwap),
            "pov": simulate_pov(bars, shares, side, arrival, ivwap, pov_rate),
        },
    }


# ----------------------------- impact model -----------------------------
def square_root_impact(shares: float, adv: float, daily_vol: float,
                       coef: float = DEFAULT_IMPACT_COEF) -> float:
    """Almgren-style square-root market-impact estimate, in basis points.

        cost(bps) = coef · σ_daily · sqrt(Q / ADV) · 1e4

    ``σ_daily`` (``daily_vol``) is a fraction (0.02 = 2% daily vol); ``Q`` is the
    order size in shares and ``ADV`` the average daily volume in shares. This is
    a transparent *model*, not a realized fill — surfaced separately from the
    real-data benchmarks. Returns 0 when inputs are degenerate.
    """
    if adv <= 0 or shares <= 0 or daily_vol <= 0:
        return 0.0
    return coef * daily_vol * math.sqrt(shares / adv) * 1e4


def _bar_time(bar: dict) -> str:
    """Compact HH:MM label from an ISO bar timestamp (best effort)."""
    t = bar.get("t") or bar.get("time")
    if not isinstance(t, str):
        return str(t or "")
    if "T" in t:
        clock = t.split("T", 1)[1]
        return clock[:5]
    return t[:5] if len(t) >= 5 else t


# ----------------------------- aggregation -----------------------------
def aggregate_tca(orders: Sequence[dict]) -> dict:
    """Notional-weighted TCA across supported orders.

    Each input order must carry ``notional``, ``side``, ``isBps``,
    ``vwapSlipBps``, ``impactBps`` and ``allInBps``. Returns gross/buy/sell
    notional, notional-weighted bps figures and the summed dollar cost.
    """
    supp = [o for o in orders if o.get("supported")]
    gross = sum(o["notional"] for o in supp)
    buy_notional = sum(o["notional"] for o in supp if o["side"] == "buy")
    sell_notional = sum(o["notional"] for o in supp if o["side"] == "sell")

    def _wavg(key: str) -> float:
        if gross <= 0:
            return 0.0
        return sum(o[key] * o["notional"] for o in supp) / gross

    total_cost = sum(o["allInBps"] / 1e4 * o["notional"] for o in supp)
    return {
        "orderCount": len(orders),
        "supportedCount": len(supp),
        "unsupportedCount": len(orders) - len(supp),
        "grossNotional": gross,
        "buyNotional": buy_notional,
        "sellNotional": sell_notional,
        "isBps": _wavg("isBps"),
        "vwapSlipBps": _wavg("vwapSlipBps"),
        "impactBps": _wavg("impactBps"),
        "allInBps": _wavg("allInBps"),
        "totalCostUsd": total_cost,
    }
