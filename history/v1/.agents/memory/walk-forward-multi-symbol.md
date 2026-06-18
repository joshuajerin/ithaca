---
name: Multi-symbol walk-forward robustness
description: walk_forward_compare panel — fans the overfitting check across a universe and aggregates per-name verdicts into a robustness score.
---

A single-name walk-forward pass can be a lucky draw, so `walk_forward_compare`
runs the SAME check across a list/sector and aggregates. It does NOT reimplement
the engine — it fans out `build_walk_forward` per symbol concurrently
(ThreadPoolExecutor + `_safe_call`), isolating per-name failures exactly like
`build_analyst_compare`.

**Honest-coverage contract carries through:** thin-history names come back with
`verdict == "inconclusive"` and are EXCLUDED from the aggregate robustness score
(reported in `aggregate.inconclusive`, never hidden). The score is a plain mean
of `_WF_VERDICT_SCORE` over the judged names (robust=100 … severe=0); aggregate
label is robust/mixed/fragile/inconclusive.

**Routing (agent.py, inside the `if wants_walkforward:` block):** route to
`walk_forward_compare` when `len(symbols) >= 2` OR (a sector is detected AND the
query has an "across/universe/basket/every" cue or names no explicit symbol).
Otherwise fall through to single-name `walk_forward`. Added "robust across",
"robust over", "holds up across" to `wants_walkforward` keywords (bare "robust"
is too broad and would steal plain backtest queries). Sector expands via
`repo.symbols_in_sector`; capped at 12 names.

**Passthrough panel** (same as walk_forward): no harness.DATA_MODELS entry,
frontend `WalkForwardComparePanel.tsx` types its own data, stale-PanelType tsc
errors are expected and don't gate the vite build (verify with vite build, not tsc).

**Verdict-label naming trap:** the engine emits `some_overfitting` (not
`some_decay`). The original `WalkForwardPanel.tsx` VERDICT_STYLE keys it as
`some_decay`, so it silently falls back to the inconclusive style — the new
compare panel keys it correctly as `some_overfitting`.
