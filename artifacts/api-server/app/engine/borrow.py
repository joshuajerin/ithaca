"""Shorting reality: borrow cost, financing & margin (pure numpy / stdlib).

The cost of being short is not just the price move — you pay to *borrow* the
shares, you finance any leverage, and you must post margin against the position.
This module turns the observable liquidity of a name plus a few clearly-labeled
reference rates into the three honest frictions a real short book carries:

- **Borrow cost** — an annualized stock-loan fee. There is no free public locate
  feed, so the fee is a transparent *model* keyed off liquidity (dollar ADV with
  a market-cap floor): deep, liquid names trade as *general collateral* (GC) at a
  few tens of bps; thin names are *hard-to-borrow* (HTB) at several hundred bps;
  micro/illiquid names are *locate-infeasible* (cannot be shorted at all). The
  tiers and fees are documented assumptions, not scraped rates.

- **Financing** — interest on the cash a leveraged book borrows (GC + a spread),
  netted against the rebate earned on idle cash / short-sale proceeds. The GC
  anchor is a real short-tenor reference rate supplied by the caller.

- **Margin** — a Reg-T style initial requirement and a maintenance requirement,
  from which leverage, excess liquidity and a breach flag fall out.

Everything is pure (no DB / network): the assembly layer (`app/shorting.py`)
sources the liquidity and the reference rate and owns the live/mock provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

TRADING_DAYS = 252


# ----------------------------- borrow classification -----------------------------
@dataclass(frozen=True)
class BorrowTier:
    key: str
    label: str
    min_dollar_adv: float  # lower bound on 20d dollar ADV ($) for this tier
    fee_lo_bps: float      # annualized stock-loan fee at the top of the tier (most liquid)
    fee_hi_bps: float      # annualized fee at the bottom of the tier (least liquid)
    shortable: bool


# Ordered most-liquid -> least-liquid. Thresholds and fees are documented model
# assumptions (no real locate feed); they are deliberately conservative and
# monotone so a more liquid name is never assigned a higher fee than a thinner one.
BORROW_TIERS: List[BorrowTier] = [
    BorrowTier("gc", "General Collateral", 200_000_000, 15.0, 40.0, True),
    BorrowTier("easy", "Easy-to-Borrow", 50_000_000, 40.0, 90.0, True),
    BorrowTier("moderate", "Moderate", 10_000_000, 90.0, 250.0, True),
    BorrowTier("htb", "Hard-to-Borrow", 2_000_000, 250.0, 900.0, True),
    BorrowTier("locate", "Locate-Infeasible", 0.0, 900.0, 2500.0, False),
]

# A market-cap floor below which a name is treated as locate-infeasible even if a
# burst of volume lifts its dollar ADV — genuine microcaps have no reliable borrow.
_MICRO_CAP_FLOOR = 300_000_000.0


def _interp_fee(tier: BorrowTier, dollar_adv: float, next_floor: float) -> float:
    """Fee within a tier, interpolated by where ADV sits in the tier's band.

    Most-liquid edge of the band -> ``fee_lo_bps``; least-liquid edge ->
    ``fee_hi_bps``. Deterministic and monotone in ``dollar_adv``.
    """
    hi = max(next_floor, tier.min_dollar_adv + 1.0)
    lo = tier.min_dollar_adv
    if dollar_adv >= hi:
        frac = 0.0
    elif dollar_adv <= lo:
        frac = 1.0
    else:
        span = hi - lo
        frac = 1.0 - (dollar_adv - lo) / span if span > 0 else 0.5
    return round(tier.fee_lo_bps + frac * (tier.fee_hi_bps - tier.fee_lo_bps), 1)


def classify_borrow(dollar_adv: float, market_cap: float = 0.0) -> dict:
    """Classify a name's borrow profile from its liquidity.

    ``dollar_adv`` is the 20-day average traded dollar volume (price × shares);
    ``market_cap`` is the floor used to force genuine microcaps into the
    locate-infeasible bucket. Returns ``{tier, label, feeBps, shortable, note}``.
    """
    adv = max(0.0, float(dollar_adv or 0.0))
    cap = max(0.0, float(market_cap or 0.0))

    # Microcap override: no dependable locate regardless of a volume spike.
    if cap > 0 and cap < _MICRO_CAP_FLOOR:
        t = BORROW_TIERS[-1]
        return {
            "tier": t.key,
            "label": t.label,
            "feeBps": t.fee_hi_bps,
            "shortable": False,
            "note": f"market cap ${cap/1e6:.0f}M below ${_MICRO_CAP_FLOOR/1e6:.0f}M locate floor",
        }

    for i, t in enumerate(BORROW_TIERS):
        if adv >= t.min_dollar_adv:
            next_floor = BORROW_TIERS[i - 1].min_dollar_adv if i > 0 else t.min_dollar_adv * 5.0
            fee = _interp_fee(t, adv, next_floor)
            note = ""
            if not t.shortable:
                note = f"dollar ADV ${adv/1e6:.1f}M too thin to locate borrow"
            elif t.key == "htb":
                note = "thin borrow — fee volatile, locate not guaranteed"
            return {
                "tier": t.key,
                "label": t.label,
                "feeBps": fee,
                "shortable": t.shortable,
                "note": note,
            }
    t = BORROW_TIERS[-1]
    return {"tier": t.key, "label": t.label, "feeBps": t.fee_hi_bps,
            "shortable": False, "note": "no usable liquidity"}


# ----------------------------- margin -----------------------------
@dataclass(frozen=True)
class MarginRules:
    """Reg-T style margin requirements (fractions of market value)."""
    init_long: float = 0.50
    init_short: float = 0.50
    maint_long: float = 0.25
    maint_short: float = 0.30
    # Utilization of maintenance vs equity above which we warn (pre-breach).
    warn_utilization: float = 0.80


def margin_profile(
    long_mv: float,
    short_mv: float,
    equity: float,
    rules: Optional[MarginRules] = None,
) -> dict:
    """Margin requirement + leverage + breach diagnostics for a book.

    ``long_mv`` / ``short_mv`` are absolute market values; ``equity`` is the
    account net liquidation value (capital). Returns initial / maintenance
    requirements, gross / net exposure, leverage, excess liquidity, utilization
    and a breach flag with human-readable warnings.
    """
    rules = rules or MarginRules()
    long_mv = max(0.0, float(long_mv or 0.0))
    short_mv = max(0.0, float(short_mv or 0.0))
    equity = float(equity or 0.0)

    gross = long_mv + short_mv
    net = long_mv - short_mv
    init_req = rules.init_long * long_mv + rules.init_short * short_mv
    maint_req = rules.maint_long * long_mv + rules.maint_short * short_mv
    leverage = gross / equity if equity > 0 else 0.0
    excess_liquidity = equity - maint_req
    initial_excess = equity - init_req
    utilization = maint_req / equity if equity > 0 else 0.0

    warnings: List[str] = []
    breach = False
    if excess_liquidity < 0:
        breach = True
        warnings.append(
            f"Maintenance margin breach: requirement ${maint_req:,.0f} exceeds equity "
            f"${equity:,.0f} (excess liquidity -${abs(excess_liquidity):,.0f})."
        )
    if initial_excess < 0:
        warnings.append(
            f"Below Reg-T initial margin: need ${init_req:,.0f} vs ${equity:,.0f} equity — "
            f"no new positions can be opened."
        )
    if not breach and utilization >= rules.warn_utilization:
        warnings.append(
            f"Margin utilization {utilization*100:.0f}% — within {(1-utilization)*100:.0f}% "
            f"of a maintenance call."
        )

    return {
        "equity": round(equity, 2),
        "longMv": round(long_mv, 2),
        "shortMv": round(short_mv, 2),
        "grossMv": round(gross, 2),
        "netMv": round(net, 2),
        "grossLeverage": round(leverage, 3),
        "netLeverage": round(net / equity, 3) if equity > 0 else 0.0,
        "initialMargin": round(init_req, 2),
        "maintenanceMargin": round(maint_req, 2),
        "excessLiquidity": round(excess_liquidity, 2),
        "initialExcess": round(initial_excess, 2),
        "marginUtilizationPct": round(utilization * 100.0, 1),
        "breach": breach,
        "warnings": warnings,
    }


# ----------------------------- carrying cost -----------------------------
def carry_breakdown(
    short_legs: Sequence[dict],
    cash: float,
    nav: float,
    gc_rate_pct: float,
    financing_spread_bps: float = 50.0,
    rebate_haircut_bps: float = 35.0,
) -> dict:
    """Annual + daily carrying cost of a book's shorts and financing.

    - ``short_legs`` is ``[{symbol, mv, feeBps}, ...]`` with ``mv`` the *absolute*
      short market value and ``feeBps`` the per-name annual stock-loan fee.
    - ``cash`` is the book's cash balance (negative = borrowed on margin). When
      negative the book pays financing at ``GC + financing_spread``; when positive
      it earns a rebate at ``GC − rebate_haircut`` (short-sale proceeds are part
      of cash, so the borrow fee is the only explicit short cost — the standard
      rebate = GC − fee decomposition, no double counting).
    - ``nav`` rebases the net carry into an annual drag in bps of book value.

    Returns the per-component annual costs, the net carry, the daily accrual and
    the annualized drag in bps.
    """
    gc = float(gc_rate_pct or 0.0)
    borrow_rows: List[dict] = []
    borrow_cost = 0.0
    for leg in short_legs or []:
        mv = abs(float(leg.get("mv") or 0.0))
        fee_bps = float(leg.get("feeBps") or 0.0)
        cost = mv * fee_bps / 10000.0
        borrow_cost += cost
        borrow_rows.append({
            "symbol": leg.get("symbol"),
            "mv": round(mv, 2),
            "feeBps": round(fee_bps, 1),
            "borrowCostAnnual": round(cost, 2),
        })

    cash = float(cash or 0.0)
    financing_rate_pct = gc + financing_spread_bps / 100.0
    rebate_rate_pct = max(gc - rebate_haircut_bps / 100.0, 0.0)
    borrowed = max(-cash, 0.0)
    idle = max(cash, 0.0)
    financing_cost = borrowed * financing_rate_pct / 100.0
    cash_rebate = idle * rebate_rate_pct / 100.0

    net_carry = borrow_cost + financing_cost - cash_rebate
    nav = float(nav or 0.0)
    drag_bps = (net_carry / nav * 10000.0) if nav > 0 else 0.0

    return {
        "gcRatePct": round(gc, 3),
        "financingRatePct": round(financing_rate_pct, 3),
        "rebateRatePct": round(rebate_rate_pct, 3),
        "cash": round(cash, 2),
        "borrowedCash": round(borrowed, 2),
        "idleCash": round(idle, 2),
        "borrowCostAnnual": round(borrow_cost, 2),
        "financingCostAnnual": round(financing_cost, 2),
        "cashRebateAnnual": round(cash_rebate, 2),
        "netCarryAnnual": round(net_carry, 2),
        "dailyCarry": round(net_carry / TRADING_DAYS, 2),
        "dragBpsAnnual": round(drag_bps, 1),
        "legs": borrow_rows,
    }


def book_cash(capital: float, long_mv: float, short_mv: float) -> float:
    """Cash balance of a self-funded long/short book.

    Buying longs spends cash; shorting receives proceeds held as collateral.
    ``cash = capital − long_mv + short_mv`` (negative ⇒ leverage / margin loan).
    """
    return float(capital or 0.0) - max(0.0, float(long_mv or 0.0)) + max(0.0, float(short_mv or 0.0))


def borrow_fees_by_symbol(profile: Dict[str, dict]) -> Dict[str, float]:
    """Map a borrow ``profile`` ({symbol: {feeBps,...}}) to annual fee *fractions*."""
    return {s: float(p.get("feeBps", 0.0)) / 10000.0 for s, p in (profile or {}).items()}
