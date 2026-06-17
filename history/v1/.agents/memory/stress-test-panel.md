---
name: Scenario stress test panel (beta-scaled)
description: How the stress_test panel differs from risk_monitor/scenario and why it uses fitted betas rather than crisis replay.
---

# Scenario Analysis & Stress Test (`stress_test`)

A distinct panel from `risk_monitor` and `scenario`. It estimates a book's P&L
under named scenarios (2020 COVID −34%, 2022 rate shock −28%, 2008 GFC −55%,
+200bps rate shock, oil +50%) by scaling each holding's REAL fitted beta by the
scenario's headline shock, then weighting by positions. Per-scenario portfolio
impact + per-holding impacts.

**Why beta-scaling, not crisis replay:** `risk_monitor`'s historical stress
REPLAYS real crisis-window returns, so any name that didn't trade in the window
(e.g. META in 2008) is dropped — useless for a modern book. The stress_test
panel instead scales each name's CURRENT measured beta, so every holding with
~40+ recent daily obs is covered regardless of when it IPO'd.

**Factor proxies (real, fetched via `_benchmark_closes(ticker,"1Y")`):**
- market → SPY, pct returns; equity scenarios apply `market_beta × shockPct`.
- rate → `^TNX` (10y yield LEVEL). Use day-over-day LEVEL CHANGES (pp), not pct
  returns. +200bps = Δ2.0pp; impact = `rate_beta × 2.0`.
- oil → `CL=F` (WTI), pct returns; impact = `oil_beta × 0.50` for +50%.

**Unit discipline:** betas fit on fractional returns; portfolio impact% =
Σ signed_w_i × impact_i; USD = impact_fraction × nav.

**Honest coverage:** a name with no usable history or <40 overlapping obs with a
proxy is excluded from that scenario and flagged in `missing` — never imputed.
If a whole proxy is unavailable, that scenario is marked unavailable.

Math lives in `engine.univariate_beta` (OLS slope cov/var, returns None on
mismatch/short/zero-variance). Data assembly + scenario loop in
`skills.build_stress_test`. Standard passthrough panel (no openapi codegen).
