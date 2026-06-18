---
name: Earnings calendar panel + imminent alert
description: How the earnings_calendar panel type and the global "within 24h" earnings alert banner are wired across api-server + terminal.
---

# Earnings calendar panel + imminent earnings alert

Passthrough panel type `earnings_calendar` (no openapi codegen; `Panel.data` is a dict). Shows upcoming report dates for watchlist / explicit symbols / sector.

## Data is REAL, not synthesized
- Report dates and consensus EPS estimates come from the live yfinance calendar feed (`sources/fundamentals.fetch_calendar` → `Earnings Date` + `Earnings Average`, with `info.earningsTimestamp` / `epsCurrentYear`/`forwardEps` fallback). Persisted on `fundamentals` (`earnings_date`, `earnings_eps_estimate`), surfaced via `repo` as `earningsDate` / `earningsEpsEstimate`.
- `data.earnings_calendar(companies, horizon_days, today)` now takes live company **snapshots** (not symbol strings) and returns `(rows, uncovered)`. It NEVER fabricates a date: a name with no upcoming (or only a stale past) date is reported in `uncovered`. `build_earnings_calendar` fetches snapshots via `repo.companies_bulk`, sets `source="live"` + real `asOf` when any dated row is live, else `source="unavailable"`.
- The free feed is **date-only** (no before/after-market session), so `timing` is `"unknown"` (label "Session not disclosed"); the panel renders a neutral "TBA" badge. `reportDateTime` anchors to the date at midnight; `imminent = 0 <= daysUntil <= 1` (reports today/tomorrow).
- `quarter` (`_fiscal_quarter`) is a best-effort calendar-quarter label only; the date and EPS are never approximated.

## Horizon rule (important UX)
`build_earnings_calendar` uses **default_horizon = 30 for the full watchlist** but **120 for explicit symbols / sector**. Why: real reports are ~quarterly, so a small explicit set (e.g. NVDA/AMD/MSFT) frequently has zero reports inside 30 days → empty panel. Explicit asks must always surface each requested name's next report. Caller-supplied `days`/`horizon` still overrides (clamped 7..120).

## Alert banner (frontend)
- The terminal-level amber "Earnings alert" banner lives in `Terminal.tsx`, computed by scanning `activeDashboard.panels` for `earnings_calendar` and unioning their `data.imminent[]`. Dismiss is keyed by the joined imminent symbol list, so a new set of imminent names re-shows it.
- `formatEarningsCountdown(reportDateTime, nowMs)` is exported from `EarningsCalendarPanel.tsx` and reused by both the panel rows and the banner; both tick via a 1s `setInterval`.
- Panel footer shows an honest coverage line listing `uncovered` symbols (names with no scheduled date from the feed).

## Gotchas
- `earnings_calendar` is intentionally NOT in DATA_MODELS, so `harness.run_skill` lifts `asOf`/`source` into the envelope (they come back null inside `panel.data`). The panel/banner don't depend on them.
- `source` can be the literal `"unavailable"` (PanelContainer renders it verbatim) when the DB has no earnings dates yet — e.g. immediately after a restart before the slow calendar ingest loop runs. This is honest, not a bug.
- Vite build for terminal needs `PORT` and `BASE_PATH` env set or config load fails.
