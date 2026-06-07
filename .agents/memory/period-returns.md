---
name: Period returns (day vs year) across terminal widgets
description: Why screener/heatmap show YTD (not 1Y) and how real period returns are computed from price series.
---

Widgets must distinguish a 1-day move (`changePct`) from a multi-period return.
`changePct` is a single-day quote field — never label or reuse it as a period return.

Real period returns are computed from the stored price series, not from quote fields:
- Pure logic lives in `app/returns.py` (`compute_period_returns`); no I/O, fully unit-testable.
- `repo.period_returns(symbol)` and `repo.period_returns_bulk(symbols)` wrap it; bulk does ONE
  OHLCV query and falls back to a deterministic mock walk for breadth (mock-on-demand) names so
  the figure is stable and clearly differs from the 1D move.
- Returns are `None` (rendered "—") when history is too short — honest, never faked.

**Decision: screener + heatmap expose `ret1Y` (true trailing 1-year return).**
**Why:** the price ingest now fetches a 2y daily window per tracked symbol (`_ingest_prices`
range `"2y"`), so the OHLCV store always holds well over a full year — a true 1Y return is
computable for live names instead of all dashes. 1Y is the standard trader metric, so it
replaced the earlier YTD stopgap.
**History:** before the 2y backfill the live DB held only ~6 months, so a 1Y column was all
dashes and the panels showed `retYTD` instead. The switch back to `ret1Y` touched (in lockstep):
ingest range in `worker.py`, `build_screener`/`build_heatmap` windows + field, `models.py`,
`openapi.yaml` + codegen, both panels, and `tests/test_widgets.py` — the field name flows
through all of them.
**How to apply:** any change to which period column these panels show must update that same
chain together, or the generated client/types drift from the API.

company_analytics exposes a full `returns` block (1D/1M/YTD/1Y); price_chart's `change` is already
a period return over its selected range. Tests: `tests/test_widgets.py`.

**Trap: never derive the 1-day `changePct` from Yahoo chart meta `chartPreviousClose`.**
On a ranged chart (e.g. `range=6mo`) `chartPreviousClose` is the close *just before the window
begins* (~6 months ago), so `(price - chartPreviousClose)/chartPreviousClose` is a multi-month
return mislabeled as the daily move (NVDA showed +12% vs the real +1.7%). Yahoo's chart `meta`
also has NO usable `previousClose` on ranged charts (it comes back null). Compute the daily move
from the last two daily closes in the series instead: baseline = `points[-2].c`, latest =
`regularMarketPrice` (fallback `points[-1].c`). `prices.fetch_price_history` does this for
`interval == "1d"`. The 90s price loop and the 15m fundamentals loop (which uses the genuine
`regularMarketPreviousClose`) now both write a correct 1-day value, so the COALESCE upsert
reconciliation is safe.
