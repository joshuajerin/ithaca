---
name: Strategy Templates Marketplace
description: How the strategy_marketplace panel works — alpha-signal presets, preview via build_signal_portfolio, clone via create_strategy, save user templates.
---

Templates are **alpha-signal presets** (momentum/value/quality/low_volatility/short_reversal) over an optional sector universe with topN+capital — NOT engine timing strategies.

**Why:** keeps the marketplace on the same model as the Signal Portfolio + Strategy Desk so preview/clone reuse existing, compliance-safe code paths instead of inventing a parallel strategy type.

**How it works:**
- Preview = `skills.build_signal_portfolio({signal, sector, scheme:"top_quantile"})` → real diversified backtest (stats/benchStats/curve/drawdown/holdings, live source). Identical numbers to the Signal Portfolio desk.
- Clone = `strategy.derive_target_weights(signal, None, None, sector, top_n=topN)` → explicit symbols+weights → `strategy.create_strategy(..., paper=True)`. create_strategy runs the compliance gate; route catches `strategy.ComplianceBlock` and returns `{ok:False, blocked:True, reason}`.
- **topN clamp 5–30.** topN=5 → equal-weight 20% > the 15% maxPosition limit → ComplianceBlock. topN≥7 is safe.
- Save = persists a user preset in `strategy_templates` table (template_store, DB-first + in-mem fallback like strategy_store). Built-ins live inline in `templates.py` (_BUILT_IN), never stored.

**Wiring gotchas:**
- `_handle_lifecycle` early-returns None when the query mentions template/marketplace, so the create verb ("build … strategy") doesn't hijack it into the desk.
- Heuristic `wants_marketplace` routes BEFORE `wants_desk` (marketplace text contains "strategies").
- Sector clearing uses "" sentinel (broad universe), mapped to None by `_clean_sector`; the refine branch passes "" through so it survives the None-strip in `_structured_refine_params`.
- `template_store.delete` must check existence first (db.execute returns None, no rowcount) so a missing id yields 404 not 200.
- engine is a PACKAGE (`app/engine/`); SIGNAL_META/normalize_signal/signal_label re-exported from `app/engine/__init__.py`.
- Frontend StrategyMarketplacePanel uses raw `/api/templates/...` fetch for clone/save/delete (like DCFPanel) and `onRefine` (paramRefineMutation) for catalog-select + tweaks.
