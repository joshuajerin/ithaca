---
name: Company profiles (sub-industry + logos)
description: How richer company profiles (human-readable sub-industry + logo) are assembled across the data catalog and panels.
---

Every company record carries `subIndustry` (human label, distinct from internal `sector` id) and `logoUrl`.

- **Two catalog builders, one stamper.** `data.py` builds COMPANIES via `_c()` (113 curated core, live-tracked) AND `_q()`/`_load()` (bulk breadth, mock-on-demand). BOTH must include `subIndustry`/`logoUrl` default keys. `_apply_company_profiles()` MUST run AFTER all `_load()` calls (it's at module bottom, not after the `_c` block) or bulk names (e.g. AAPL — which is bulk, not core) never get stamped.
  **Why:** original bug — apply ran at line ~848 before bulk loads at ~1318, so only the 113 curated got fields.
- `_COMPANY_PROFILES` is symbol→(sub_industry, domain); covers all 113 core + ~45 prominent bulk mega-caps. Logos = Google s2 favicons (`logo_url(domain)`). Names without a curated entry fall back to the SECTORS group name for subIndustry and a monogram on the frontend for the logo.
- **Live refresh precedence:** `repo._company_from_row` prefers Yahoo's `row.industry` over the curated label, and `logo_url(row.website)` over the curated logo. So a live core symbol can show Yahoo's (sometimes broader) industry instead of the finer curated label — expected.
- Frontend: `CompanyLogo.tsx` (img + monogram fallback on error/missing). Used in ScreenerPanel, CompanyAnalyticsPanel (header + peers). ScreenerRow/HeatmapCell are openapi-typed (need codegen); CompanyAnalyticsData is an inline interface (passthrough dict, edit directly).
