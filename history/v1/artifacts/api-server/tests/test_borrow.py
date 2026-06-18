"""Unit tests for the borrow / financing / margin engine (pure numpy / stdlib).

Runnable two ways:
    python artifacts/api-server/tests/test_borrow.py   # standalone
    pytest artifacts/api-server/tests/test_borrow.py    # if pytest installed

Covers: borrow-tier monotonicity (more liquid never costs more), the microcap
locate floor, the Reg-T margin / leverage / breach identities, and the sign and
netting of the carrying-cost breakdown.
"""
from __future__ import annotations

import os
import sys

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app.engine import borrow  # noqa: E402


def test_tier_classification():
    gc = borrow.classify_borrow(500_000_000, 2_000_000_000_000)
    assert gc["tier"] == "gc" and gc["shortable"] and gc["feeBps"] <= 40.0, gc
    htb = borrow.classify_borrow(5_000_000, 5_000_000_000)
    assert htb["tier"] == "htb" and htb["shortable"], htb
    locate = borrow.classify_borrow(500_000, 5_000_000_000)
    assert locate["tier"] == "locate" and not locate["shortable"], locate
    print("ok: liquid->GC, thin->HTB, illiquid->locate-infeasible")


def test_microcap_floor():
    # A volume spike lifts ADV high, but a genuine microcap is still infeasible.
    r = borrow.classify_borrow(300_000_000, 100_000_000)
    assert not r["shortable"] and r["tier"] == "locate", r
    assert "floor" in r["note"].lower(), r
    print("ok: microcap market-cap floor forces locate-infeasible")


def test_fee_monotone():
    advs = [5_000, 1_000_000, 5_000_000, 30_000_000, 80_000_000, 300_000_000, 2_000_000_000]
    fees = [borrow.classify_borrow(a, 5_000_000_000)["feeBps"] for a in advs]
    for lo, hi in zip(fees, fees[1:]):
        assert hi <= lo + 1e-9, ("fee not monotone in liquidity", fees)
    print(f"ok: borrow fee monotone decreasing in liquidity {fees}")


def test_margin_within_limits():
    # $1M equity, $1M long + $0.5M short -> 1.5x gross, comfortably above maint.
    m = borrow.margin_profile(1_000_000, 500_000, 1_000_000)
    assert abs(m["grossLeverage"] - 1.5) < 1e-9, m
    assert abs(m["initialMargin"] - 750_000) < 1e-6, m       # .5*1M + .5*.5M
    assert abs(m["maintenanceMargin"] - 400_000) < 1e-6, m   # .25*1M + .30*.5M
    assert m["excessLiquidity"] > 0 and not m["breach"], m
    print("ok: margin requirement, leverage and excess liquidity within limits")


def test_margin_breach():
    # Heavy leverage: $1M equity carries $3M long + $3M short -> maint > equity.
    m = borrow.margin_profile(3_000_000, 3_000_000, 1_000_000)
    assert m["breach"] and m["excessLiquidity"] < 0, m
    assert any("breach" in w.lower() for w in m["warnings"]), m
    assert m["grossLeverage"] == 6.0, m
    print("ok: over-levered book flags a maintenance margin breach")


def test_carry_signs():
    legs = [
        {"symbol": "AAA", "mv": 100_000, "feeBps": 40.0},   # GC short
        {"symbol": "BBB", "mv": 50_000, "feeBps": 600.0},   # HTB short
    ]
    # Dollar-neutral $1M book: $1M long, $150k short, cash = 1M -1M +150k = 150k idle.
    cash = borrow.book_cash(1_000_000, 1_000_000, 150_000)
    assert abs(cash - 150_000) < 1e-6, cash
    c = borrow.carry_breakdown(legs, cash, nav=1_000_000, gc_rate_pct=5.0)
    assert abs(c["borrowCostAnnual"] - (100_000 * 0.004 + 50_000 * 0.06)) < 1e-6, c
    assert c["financingCostAnnual"] == 0.0 and c["cashRebateAnnual"] > 0.0, c
    # Net carry = borrow + financing - rebate (a cash-rich book can net a credit).
    expect = c["borrowCostAnnual"] + c["financingCostAnnual"] - c["cashRebateAnnual"]
    assert abs(c["netCarryAnnual"] - expect) < 1e-6, c
    print("ok: borrow + financing - rebate netting identity holds")


def test_carry_htb_drag():
    # HTB-heavy shorts: borrow fees dominate the cash rebate -> positive drag.
    legs = [{"symbol": "Z", "mv": 1_000_000, "feeBps": 600.0}]
    cash = borrow.book_cash(1_000_000, 1_000_000, 1_000_000)  # dollar-neutral, 1M idle
    c = borrow.carry_breakdown(legs, cash, nav=1_000_000, gc_rate_pct=5.0)
    assert c["netCarryAnnual"] > 0.0 and c["dragBpsAnnual"] > 0.0, c
    print(f"ok: HTB short book carries a positive drag ({c['dragBpsAnnual']} bps/yr)")


def test_carry_leverage_financing():
    # Levered book: $1.5M long, $0.3M short, $1M equity -> cash negative -> financing.
    cash = borrow.book_cash(1_000_000, 1_500_000, 300_000)
    assert cash < 0, cash
    c = borrow.carry_breakdown([{"symbol": "X", "mv": 500_000, "feeBps": 50.0}],
                               cash, nav=1_000_000, gc_rate_pct=5.0)
    assert c["financingCostAnnual"] > 0.0 and c["cashRebateAnnual"] == 0.0, c
    assert c["financingRatePct"] > c["gcRatePct"], c
    print("ok: levered book pays financing above GC")


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nAll {len(fns)} borrow-engine tests passed.")


if __name__ == "__main__":
    main()
