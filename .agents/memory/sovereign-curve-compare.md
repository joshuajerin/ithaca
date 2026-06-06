---
name: Sovereign curve comparison panel
description: Why the multi-curve compare panel adds a per-tenor "twist" and how cross-currency curves share one spot helper.
---

The `sovereign_compare` panel overlays 2–4 sovereign curves (US/UK/DE/JP) and
shows cross-currency 2Y/10Y/30Y spreads in the summary strip.

**Decision: each sovereign curve = US base + parallel `shift` + a per-tenor `twist`
(pivoting around 5Y), shared via `_region_spot(region, i)` in `skills.py`.**
**Why:** the original yield-curve mock used a pure parallel `shift` per region. Under
a pure parallel shift, the 2Y/10Y/30Y cross-market spreads are all identical — which
looks broken for a panel whose whole point is the spread term structure. The `twist`
gives each issuer a distinct slope so spreads vary realistically by tenor.
**How to apply:** `_SOVEREIGN_META` (skills.py) holds `shift`/`twist`/`currency`/`color`
per region; `build_yield_curve` AND `build_sovereign_compare` both go through
`_region_spot` so the single-curve and overlay panels stay consistent. US has
twist=0 so its curve is unchanged from before.

**Routing:** the heuristic `wants_sovereign_compare` must be checked BEFORE
`wants_yield_curve` in `_orchestrate_heuristic` (agent.py) — a "compare US vs German
curve" query would otherwise fall into the single-curve branch. Region detection
(`_detect_sovereign_regions`) keys off space-padded keywords (e.g. " us ", "bund",
"gilt", "jgb") to avoid matching substrings inside other words.

Data shape: `points` flatten each region's spot onto the row keyed by region code
(`{"tenor":"10Y","US":4.52,"DE":3.11}`) so recharts renders one `<Line>` per region;
the pydantic point model uses `ConfigDict(extra="allow")` for those dynamic keys.
