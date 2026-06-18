---
name: Institutional holdings & 13F flows
description: How "who owns X" / 13F-flows panels are built and two non-obvious correctness traps in 13F ingestion.
---

Real institutional ownership + QoQ fund flows come from SEC 13F filings, pre-aggregated by the worker (13F is per-institution, so a per-stock fetch is impossible at request time). Cold store → builders return an honest `feedSource="pending"`, never partial. A curated set of ~16 manager CIKs is tracked; managers configured-but-not-yet-ingested are reported in `coverage.missing`, never imputed.

## Trap 1 — partial 13F amendments must NOT supersede the full filing
A quarter can have an original `13F-HR` plus one or more `13F-HR/A` amendments. An SEC **"NEW HOLDINGS"** amendment lists only the *added* positions (can be a handful), not the full portfolio. Selecting "latest accession per report period" therefore silently discards the full book and makes every other name look **exited** (observed: JPMorgan 2026Q1 amendment had 378 positions vs 7406 in the original → AAPL falsely shown as the biggest seller, −$61B).
**Fix:** for each report period, parse every candidate filing and keep the one with the **most holdings** (the most complete information table), ties broken by recency. Don't merge/impute — surface a single real filing as the snapshot.
**Why:** avoids a fragile amendmentType (RESTATEMENT vs NEW HOLDINGS) parse while reliably defeating the partial-amendment trap.

## Trap 2 — flows are a SHARE decision, not a value change
Buyers/sellers must be split on the discretionary **share** change (new/added vs trimmed/exited), NOT on change in position *value*. A manager who adds shares while the price falls has a negative `deltaValue` and would be miscounted as a seller. Each flow row carries `tradeValue = deltaShares × reported price` (price = 13F value/shares; for an exited row, fall back to the prior period's price). Rank/total by `tradeValue`.
**Gotcha:** the assemble helper returns rows with `priorShares`/`priorValue`; the flow-row converter needs those to recover the price for *exited* rows (latest shares = 0). Don't double-apply the converter — the second pass sees an already-stripped row (no prior keys) and zeroes out exited trade values.

## Verifying changes to ingestion logic
The worker skips re-ingest when `inst_latest_period` already matches, so after changing filing-selection logic you must `DELETE FROM inst_holdings; DELETE FROM inst_filings;` then restart the api-server to force a fresh pull (~1–2 min for the full manager set).
