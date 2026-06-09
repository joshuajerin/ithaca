---
name: SEC filings browser (EDGAR)
description: How the filings_browser panel sources EDGAR data and the non-obvious EDGAR full-text-search quirks.
---

# SEC filings browser (`filings_browser`)

Two modes in one panel:
- **filings** — recent dated filings for a resolved ticker, from the submissions
  `filings.recent` feed (form, filingDate, reportDate/period, accession, doc/index URLs).
- **search** — EDGAR full-text search (FTS).

## EDGAR full-text search quirks (non-obvious)
- FTS endpoint: `https://efts.sec.gov/LATEST/search-index?q=...&forms=...&ciks=<10-digit>&startdt=&enddt=`.
- **The `ticker=` param is IGNORED by FTS.** You MUST pass a zero-padded 10-digit
  `ciks=` to scope to one filer. Resolve ticker→CIK first.
- A valid SEC `User-Agent` header is required or requests are rejected.
- FTS only covers filing **documents since 2001**; results are ranked by relevance,
  not date. Report this in coverage text so users aren't misled.

## Honesty contract
- No SEC filer / CIK match → `feedSource: "unavailable"`, empty list, coverage note.
- EDGAR unreachable → `feedSource: "error"`. Never fabricate filings.

## Frontend
- Form-type filter chips filter **client-side** over the already-loaded list
  (instant, both modes) keyed on `rootForm`. The search box submits explicit
  `{symbol, query}` via the param-refine path (no global Processing overlay).
- `filings_browser` is a passthrough panel: it's in the BACKEND PanelType enum but
  NOT in the frontend openapi-codegen types, so `case "filings_browser"` throws the
  expected non-gating `TS2678` (same as every other passthrough panel). The vite
  build does not gate on tsc and passes.
