---
name: Combined alpha (signal blend)
description: Durable constraints for blending multiple cross-sectional signals into one composite alpha.
---

# Combined alpha — blend N signals into one composite

`combine_signals` (engine/signals.py) blends several cross-sectional signals into
ONE composite alpha, scored with the SAME scorecard path (`_score_panel`) as a
single signal so blend-vs-component metrics are directly comparable.

## Durable constraints
- **Strict intersection is the contract.** The composite at a name/date is formed
  only when EVERY selected component is finite there. A name missing ANY selected
  component's input (e.g. a fundamental for value/quality) is excluded and reported
  with the missing component named — never imputed. Relaxing this to "any component
  present" silently changes composite membership and all downstream scorecard
  metrics; that was rejected in review.
  **Why:** task requires real-data-only; partial-input names corrupt the blend.
- **Per-component ctx, not one ctx.** Build a `ctx_by_signal[signal][symbol]` dict
  (via `_signal_ctx` per component) so value and quality — which share a SIGNALS fn
  but need distinct fundamentals — each get their own cross-sectional value.
- **Component scoring uses each component's own (broader) universe**; only the
  composite is restricted to the strict intersection. IC-weights are derived from
  those standalone component ICs (floored at 0; equal-weight fallback if none +).
- **Method is reported back** (equal_weight / ic_weighted / inverse_correlation).
  `normalize_combine_method` is substring-matched — bare "ic" does NOT map to
  ic_weighted (needs "ic_weight"/"ic weighted"); "inverse"/"risk_weight"/"decorrel"/
  "diversif" → inverse_correlation.

## Wiring (see passthrough-panels.md)
Passthrough panel type `combined_alpha` (plain str, no openapi/models.py enum;
local TS interface; stale-PanelType tsc errors don't gate the vite build). Routed
in agent.py BEFORE scorecard/research but AFTER portfolio-build (so "blend … into a
portfolio" still builds a book). Panel `included` is a count (composite included),
not a list.
