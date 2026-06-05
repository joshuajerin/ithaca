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

**Decision: screener + heatmap expose `retYTD` (year-to-date), NOT `ret1Y`.**
**Why:** the live OHLCV DB only holds ~6 months (~125 trading days), so a true 1Y return is
`None` for every live name — a 1Y column would be all dashes. YTD is computable for both live
names AND mock names, so it's the longest honest period the live data supports.
**How to apply:** if/when the ingest backfills a full year of history, 1Y becomes viable and the
screener/heatmap period column could switch back to `ret1Y` (update models.py, openapi.yaml +
codegen, both panels, and tests in lockstep — the field name flows through all of them).

company_analytics exposes a full `returns` block (1D/1M/YTD/1Y); price_chart's `change` is already
a period return over its selected range. Tests: `tests/test_widgets.py`.
