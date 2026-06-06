---
name: Earnings calendar panel + imminent alert
description: How the earnings_calendar panel type and the global "within 24h" earnings alert banner are wired across api-server + terminal.
---

# Earnings calendar panel + imminent earnings alert

Passthrough panel type `earnings_calendar` (no openapi codegen; `Panel.data` is a dict). Shows upcoming report dates for watchlist / explicit symbols / sector.

## Data shape & determinism
- `data.earnings_calendar(symbols, horizon_days, today)` synthesizes deterministic-per-symbol report dates (seeded), rolling forward from today on a ~91-day quarter cycle, weekend-nudged. Rows carry: reportDate, reportDateTime (ISO with bmo=08:00 / amc=16:30), timing(bmo/amc)+timingLabel, epsEstimate, quarter, daysUntil, hoursUntil, imminent (0<=h<=24), marketCap. Sorted by reportDateTime.
- These are SYNTHETIC dates, not real scheduled earnings — consistent with the terminal's synthetic-market-intelligence framing.

## Horizon rule (important UX)
`build_earnings_calendar` uses **default_horizon = 30 for the full watchlist** but **120 for explicit symbols / sector**. Why: with a 91-day cycle, a small explicit set (e.g. NVDA/AMD/MSFT) frequently has zero reports inside 30 days → empty panel. Explicit asks must always surface each requested name's next report. Caller-supplied `days`/`horizon` still overrides.

## Alert banner (frontend)
- The terminal-level amber "Earnings alert" banner lives in `Terminal.tsx`, computed by scanning `activeDashboard.panels` for `earnings_calendar` and unioning their `data.imminent[]`. Dismiss is keyed by the joined imminent symbol list, so a new set of imminent names re-shows it.
- `formatEarningsCountdown(reportDateTime, nowMs)` is exported from `EarningsCalendarPanel.tsx` and reused by both the panel rows and the banner; both tick via a 1s `setInterval`.

## Gotchas
- `earnings_calendar` is intentionally NOT in DATA_MODELS, so `harness.run_skill` lifts `asOf`/`source` into the envelope (they come back null inside `panel.data`). The panel/banner don't depend on them.
- Vite build for terminal needs `PORT` and `BASE_PATH` env set or config load fails.
