---
name: Multi-period Brinson linking (Carino)
description: Why/where attribution links sub-period BHB effects geometrically over long windows instead of single-period BHB on compounded sector returns.
---

# Brinson attribution links geometrically over long windows

Single-period Brinson-Hood-Beebower computed once over a whole window from
*compounded* sector returns accumulates a linking/residual bias on 6M/1Y/YTD
horizons — the allocation/selection/interaction effects drift away from the true
geometric active return.

The engine has two paths:
- `brinson(...)` — single-period BHB on compounded sector returns (kept for the
  degenerate 1-sub-period case and as the unit-test identity).
- `brinson_linked(...)` — takes **per-sub-period** weight/return series per
  sector, computes single-period effects each sub-period, and scales them by the
  Carino factor `k_t / k` before summing. `_carino_coeff(Rp,Rb) = (ln(1+Rp) -
  ln(1+Rb))/(Rp-Rb)` with limit `1/(1+Rp)` at `Rp==Rb`.

**Why Carino:** by construction the linked effects sum *exactly* to the
geometrically compounded active return `prod(1+Rp_t)-1 - (prod(1+Rb_t)-1)`, so
the attribution stays additive and accurate over long horizons.

**How to apply:** `_compute_attribution` builds the per-DAY portfolio sector
return (within-sector book-weighted daily return) and the per-day benchmark
sector ETF return, then calls `brinson_linked` whenever the window has >1 day
(`k > 1`); otherwise the single-period `brinson`. Weights are constant and
broadcast (pass a scalar per sector; `col()` broadcasts to length T).
`brinson_linked` adds `linked: True` and `subPeriods` to its output — callers
that copy explicit fields drop them; `build_tear_sheet`/`attribution_overview`
pass the whole brinson dict through, which is fine (panel models tolerate them).
