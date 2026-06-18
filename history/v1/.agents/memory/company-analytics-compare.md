---
name: Company analytics head-to-head compare
description: How the two-company compare view is wired (panel type, builder, ordering, leader scoreboard).
---

# Company analytics compare (head-to-head)

- Panel type `company_analytics_compare` (passthrough — no openapi codegen). Builder
  `build_company_analytics_compare` in skills.py takes `symbols: [A, B]`; reuses
  `_company_price_drivers` (AI+fallback, refactored out of `build_company_analytics`)
  and `_company_side` per company.
- Comparison "scoreboard" picks a leader per metric: Revenue Growth, Operating Margin
  (=netMargin), P/E (lower-is-better), Market Cap, YTD, 1Y. Each row carries
  `higherIsBetter` + `leader` (sym | "tie" | None when a side is missing).
- Routing: heuristic `wants_compare` needs a compare keyword (vs/versus/compare/
  head-to-head/side-by-side/which is better) AND >=2 symbols; `_order_symbols_by_query`
  orders the two by appearance in the query (left = first named), since
  `_extract_symbols` returns repo order not query order. LLM path has its own tool.
- Frontend `CompanyAnalyticsComparePanel.tsx`: Trophy marks the leader; two columns
  (grid md:grid-cols-2) each with Price Drivers + Catalyst Watch. Routed at width 12.
