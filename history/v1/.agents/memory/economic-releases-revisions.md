---
name: Economic releases + FRED revision history
description: Two FRED/ALFRED-backed passthrough panels (economic_releases, series_revisions) and the vintage-print honesty contract.
---

# Economic releases & series revisions (FRED/ALFRED)

Two passthrough panels backed by the free FRED series API + ALFRED vintage API (needs `FRED_API_KEY`).

- `economic_releases` — recent/upcoming key US releases (CPI, PCE, GDP, unemployment, payrolls, PPI). Each row: reported value + period, prior value + period, change, frequency, next scheduled release date. Map of tracked series lives in `ECON_RELEASE_SERIES` in `rates.py`.
- `series_revisions` — any FRED series by id. Pulls full vintage history via ALFRED (`realtime_start=1776-07-04`, `realtime_end=9999-12-31`) → per-period vintage prints. Chart overlays **current (revised)** vs **initial print**; table lists per-period initial/current/totalRevision/vintageCount/revised; a vintage timeline highlights the most-revised recent period.

**Honesty contract:** all data real/live with as-of. No synthetic fallback — absent key / unknown id / dead feed return `source="unavailable"` with a `note`; panels render an AlertTriangle empty state. `series_revisions` always keeps its FRED-id input box mounted (even when unavailable) so the user can retry; it routes through `onRefine({series_id})` → `handleRefineParamsLive` (deterministic `RefineRequest.params`, no global Processing overlay).

**Adapter:** `_fred_get` routes through `_resilient.request("fred",...)` (breaker/backoff); propagates non-throttle HTTP errors. Agent bash has no egress, so verify FRED ONLY via the running api-server workflow (curl localhost:$PORT/api/orchestrate), never ad-hoc.

**Wiring:** both are subject-agnostic passthrough types (no DATA_MODELS entry, no codegen). Revisions intent maps phrasings → FRED id (regex for explicit id, default GDPC1). Routed in agent heuristic via `wants_revisions` / `wants_econ_releases`.
