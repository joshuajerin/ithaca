---
name: Credit stress monitor panel (IG vs HY OAS)
description: How the credit_stress passthrough panel sources IG/HY OAS history and why its routing sits before bond_rv/cds.
---

The `credit_stress` panel charts investment-grade vs high-yield ICE BofA OAS over
~6 months with a risk-on/off read and a "widening" flag per bucket.

**Data:** reuses the FRED ICE BofA OAS feed, but needs a *time series*, not the
single-latest values `fetch_credit_spreads` returns. So `rates.py` gained a
SEPARATE `fetch_credit_spread_history(window_days)` (+ generic `_fetch_fred_series`
with `observation_start`/asc). Same key requirement as the rest of credit: live
only with `FRED_API_KEY`, else clean mock.
**Mock fallback:** `_mock_credit_history` synthesizes a deterministic wave+drift
path anchored to curated current levels and is honestly labelled `source="mock"`.

**Routing trap (cost real attention):** the heuristic keyword `wants_credit_stress`
MUST be checked BEFORE `wants_cds` and `wants_bond_rv` in `_orchestrate_heuristic` —
"credit risk" belongs to CDS and "credit spread" (singular) to bond RV, so a
credit-conditions query would otherwise be hijacked. credit_stress keys off
"credit stress/conditions/market", "ig vs hy", "high yield", "investment grade",
"spread(s) widening", etc. It's in `_SUBJECT_AGNOSTIC_TYPES` (market-wide, no symbol).

**Frontend:** passthrough panel (no codegen) — dual y-axis line chart, IG on left
axis / HY on right axis (HY is ~3x IG, so a shared axis flattens IG). Mirrors the
SovereignComparePanel structure.
