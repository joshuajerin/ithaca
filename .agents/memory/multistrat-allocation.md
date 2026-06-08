---
name: Multi-strategy capital allocation & firm risk
description: Firm-level multi_strategy panel — honesty contract for sleeve risk + the routing precedence traps it must avoid.
---

The `multi_strategy` panel treats every paper/live strategy as a *sleeve* of one
firm book and recommends a capital split (equal-weight / risk-parity / target-vol).

**Honesty contract (don't break):** every risk number must come from real persisted
daily NAV snapshots. A sleeve with too little history, or too little overlap with
the others, is flagged and held OUT of the covariance/correlation/allocation math —
never imputed. Drop shortest-overlap sleeves first so a brand-new sleeve doesn't
shrink everyone's common window. The combined book (NAV/P&L/netted exposures) still
shows ALL sleeves even when risk can't be computed yet.
**Why:** the whole pillar's value is that it's grounded; a faked correlation would
make the allocation advice actively misleading.

**Routing precedence trap:** "allocate capital" is already an optimizer keyword and
"my strategies" is already a desk keyword, so the multi-strategy intent must be
detected and dispatched BEFORE both the optimizer and the strategy-desk branches in
the agent heuristic. Keep its phrases off verb+"strateg" or the lifecycle
create-regex hijacks them. Note the LLM tool path (not the heuristic) is what
actually runs in /api/orchestrate when the model is up — both paths must route.
**How to apply:** when adding any new firm/strategy-level intent, check it against
the optimizer and desk keyword sets and order its dispatch ahead of them.
