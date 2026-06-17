---
name: Refine with explicit params (deterministic in-panel controls)
description: How interactive in-panel controls re-fetch a panel deterministically, bypassing the LLM/heuristic refine path.
---

# Deterministic panel re-fetch via explicit params

`RefineRequest` carries an optional `params` object alongside the free-text
`instruction`. When `params` is present, `agent.refine` applies it directly to
`harness.run_skill` and skips `_refine_params` (LLM + heuristic). This is the
mechanism for interactive in-panel controls (e.g. intraday chart
resolution/window pickers) that must re-fetch exactly what the user clicked.

**Why:** the only prior way to change a panel was the LLM/heuristic refine path,
which is slow and non-deterministic — unacceptable for a button click. Explicit
params make UI controls fast and exact.

**How to apply:**
- Always include `symbol` (and any other required skill keys) in `params` —
  skills default missing keys (e.g. `build_intraday_chart` defaults to NVDA), so
  omitting `symbol` silently switches the ticker.
- Frontend: pass a dedicated `useRefinePanel()` mutation instance to the
  interactive panel (separate from the text-refine one) so its `isPending`
  drives an in-panel spinner instead of `PanelContainer`'s global "Processing"
  loader that would unmount the controls mid-fetch.
- Invalid skill param combos should still return the skill's clean unavailable
  state; keep the controls rendered in that state so the user can recover.
- Editing `RefineRequest` requires editing `lib/api-spec/openapi.yaml` +
  `app/models.py`, then `pnpm --filter @workspace/api-spec run codegen`.

**Testing note:** orchestration routing is stochastic — the same query may yield
`price_chart` instead of `intraday_chart`. UI tests that need a specific panel
type must retry the command until the distinguishing UI appears.
