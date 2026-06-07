---
name: Signal → portfolio construction
description: How "build a portfolio from <signal>" turns a research signal into a tradeable book; schemes, dispatch ordering, real-data rules.
---

# Signal portfolio construction (`signal_portfolio` panel)

Turns a signal_research/signal_scorecard signal into a tradeable book. Pure-numpy
engine `app/engine/portfolio.py::construct_portfolio()` reuses the same
cross-sectional ranking as the signal library and the shared
`stats.performance_stats` for the realized stat block.

## Schemes
- `top_quantile` — long-only, equal-weight the top quantile. net == gross == 1.0, no shorts.
- `long_short` — long top quantile / short bottom quantile, **dollar-neutral**: net ≈ 0, gross ≈ 2.0 (1 long + 1 short leg).
- `normalize_scheme()` maps aliases ("long short", "market-neutral", "spread" → long_short; everything else → top_quantile).

## No-lookahead / real-data-only
- Rank at each rebalance (holding=21), positions lag one bar; book return compounds realized daily returns.
- Names with insufficient history are **excluded and reported** (`excluded`/`excludedNames`), never imputed — same contract as the signal library.
- Equal-weight benchmark is computed from the same included universe for an honest comparison.

## Dispatch ordering (heuristic) — important
- `wants_portfolio_build` must be checked **before** the scorecard/research/backtest routes (they all catch signal mentions).
- **Why:** `_lifecycle_action` matches `build…strateg` → "create" (strategy lifecycle desk). "build a portfolio" has no "strateg" so it won't collide; keep portfolio phrases off the word "strategy" or the lifecycle desk wins.

## Panel
- Passthrough pattern: local TS interface in `SignalPortfolioPanel.tsx`, no openapi codegen (`Panel.data` is `Optional[dict]`). Stale-PanelType tsc errors are expected and don't gate the vite build.
- Server runs WITHOUT --reload: restart `artifacts/api-server: API Server` after editing builders/engine or HTTP returns stale/empty `data`.
