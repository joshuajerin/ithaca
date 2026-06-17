---
name: DCF saved custom models
description: How named DCF assumption sets are persisted per session+symbol and restored in the DCF panel.
---

DCF panel lets users save/reload named assumption sets (e.g. "Bull case MSFT").

- Storage is in-memory session state (`state.py` `_dcf_models: sessionId -> [{name, symbol, assumptions, savedAt}]`), scoped by sessionId AND symbol. Same pattern as watchlist — no DB.
- REST endpoints in `main.py`: GET/POST/DELETE `/api/dcf-models` (POST validates the 6 assumption keys; list/delete take query params). Returns `{models: [...]}` filtered to the requested symbol.
- Frontend `DCFPanel.tsx` calls these with **raw relative `fetch("/api/dcf-models")`** (proxy-routed, like FeatureRequestModal), NOT the generated api-client — so no openapi.yaml/codegen churn for this CRUD.
- `DCFPanel` now takes a `sessionId` prop (drilled from `PanelContainer`); the Models UI only renders when sessionId is present.
- **Why client-side restore works:** reloading just sets the local `assumptions` state; the panel already recomputes projections+impliedMid via `runClientDCF`. The static sensitivity grid (`data.sensitivity`) is NOT recomputed on assumption change — pre-existing behavior, left as-is.
