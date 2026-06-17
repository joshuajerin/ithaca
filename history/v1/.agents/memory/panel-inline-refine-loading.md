---
name: In-panel control refine keeps controls mounted
description: How to refine a panel from its own controls without the global "Processing" overlay wiping the control rows.
---

# In-panel control refine loading

PanelContainer's global `renderContent()` shows a full-body "Processing" spinner whenever `refineMutation.isPending`. Any panel whose in-panel controls (strategy/range/30D-90D/ticker) call a handler backed by `refineMutation` therefore has its whole body (controls included) replaced mid-interaction.

**Rule:** route in-panel control refines through the SEPARATE `paramRefineMutation` (handler `handleRefineParamsLive`), and pass `pending={paramRefineMutation.isPending}` into the panel. The panel keeps its control rows mounted, disables them while pending (`disabled={pending}` + `disabled:opacity-50`, no double-submit), and overlays only the data/chart area with an absolute translucent `Loader2` (`pointer-events-none`).

**Why:** `renderContent`'s spinner is keyed only on `refineMutation.isPending` (and `panel.status === "loading"`). A refine does not set `panel.status` to loading — old data stays mounted — so switching to `paramRefineMutation` is enough to suppress the global overlay while the panel shows its own inline state.

**How to apply:** the canonical reference is `IntradayChartPanel` (already used `paramRefineMutation` + `pending`). Panels converted to this pattern: Backtest, CorrelationMatrix, PortfolioRisk, FactorAnalysis. Note `multi_strategy` still uses `handleRefineParams` (the global-spinner path) — convert it the same way if that ever needs the smoother behavior.
