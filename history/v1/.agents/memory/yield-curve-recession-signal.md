---
name: Yield-curve recession-signal overlay
description: How the yield_curve panel turns 2s10s/3m10s spreads into a plain-language recession read with live inversion duration.
---

The `yield_curve` panel surfaces an explicit recession-risk read derived from the
two market-watched segments: **2Y–10Y** and **3M–10Y** (an inversion = short
yield > long yield).

**Data flow:**
- `rates.fetch_treasury_curve()` adds an `inversion` dict keyed by `"2Y-10Y"`/`"3M-10Y"`
  (HYPHEN, not en-dash). Each value = `{inverted, days, obs, since}` from
  `_inversion_streak`, which walks BACKWARD through ALL daily rows already fetched
  (current + two prior years) counting the *current* consecutive inverted streak;
  it stops at the first non-inverted day (honest current streak, not cumulative).
- `skills._recession_read(spreads, inversion)` builds the `recession` block:
  `level` (warning=both inverted / watch=one / normal=none), `headline`, `detail`
  (plain-language, includes humanized duration via `_humanize_duration`), and
  per-`segments` with `days`/`since` when live streak data is present.
  Mock fallback (non-US regions, source down) passes `inversion=None` → status
  text only, no duration.
- `_SEGMENT_KEYS` maps spread label (en-dash `2Y–10Y`) → inversion key (hyphen
  `2Y-10Y`). Keep both punctuations consistent or the join silently drops duration.

**Contract gotcha:** built-in panels validate against `models.YieldCurveData` (in
`harness.DATA_MODELS`) which STRIPS unknown fields. Added `recession:
Optional[YieldCurveRecession]` (+ nested `YieldCurveRecessionSegment` with optional
`days`/`since`) so the field survives validation. asOf/source still live on the
envelope (popped before validate).

**Frontend** (`YieldCurvePanel.tsx`): `RECESSION_STYLES` by level (red/yellow/
emerald) drives the headline badge + detail card + per-segment "Xd · since DATE"
chips. Falls back to the old "⚠ Curve Inverted" badge only if `recession` absent.
