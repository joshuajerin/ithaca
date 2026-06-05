---
name: Execution simulation & TCA pillar
description: How the Execution/TCA panel generates orders, simulates algos on REAL intraday volume, models impact, and the realized-vs-modeled separation contract.
---

# Execution Simulation & TCA

Pure engine in `app/engine/execution.py` (numpy/stdlib, no I/O); skill builder `build_tca_report` in `skills.py`; panel `TCAPanelReport.tsx`; pydantic `TCARportData` in `models.py`.

## No-fake-volume contract (the whole point of this pillar)
- Algos simulate against REAL intraday bars only. `simulate_*`/`simulate_all` RAISE `ValueError` on empty or all-zero-volume profiles — never fabricate volume.
- The builder catches that (plus `p_src.IntradayUnavailable`) per order and marks the order `supported: False` with a `reason`. Unsupported orders still appear (with notional) but carry no fills/bps.
- **Why:** real-data-only is the task's reason to exist; a fake fallback would silently defeat it.

## Realized vs modeled separation
- Realized-from-real-data: arrival price, interval VWAP, bucket/schedule prices, fill rates, IS-vs-arrival bps, slippage-vs-interval-VWAP bps.
- Modeled (clearly labeled, shown separately): square-root impact `cost(bps) = Y·σ_daily·√(Q/ADV)·1e4`, Y=`DEFAULT_IMPACT_COEF`=1.0. σ_daily from real daily returns via `repo.price_series_meta`; ADV ≈ latest real daily volume.
- `allInBps = isBps + impactBps`. `isBps` is side-signed via `side_sign` so positive = cost.

## Three order input shapes (`_tca_resolve_orders`)
1. explicit `orders:[{symbol,side,shares|notional}]`
2. `symbols`+`target_weights` (+optional `current_weights`, `capital` default $10M) → `engine.generate_orders` weight diff; weights auto-normalized to fractions if they sum >1.5 (given as %)
3. single `symbol` (+side/notional/shares/participation) → defaults to a 5%-of-ADV buy.
Capped at 12 orders. Defaults: interval 30m, range 1d, algo vwap, pov_rate 0.10.

## Gotchas learned here
- `tca_report` is NOT a passthrough panel — `models.TCARportData` strictly validates panel data. Changing the builder's output shape REQUIRES updating that pydantic model in lockstep or every panel comes back `status: error` ("validation errors for TCARportData"). The old fake shape (avgExecPrice/vwap/twap/buckets) is gone.
- `source`/`asOf` keys in the returned data dict get LIFTED into the panel envelope by the orchestrator (envelope `source`/`asOf` are populated; the in-`data` copies read back as None). Frontend should read them from the envelope, not `data`.
- Builder uses `repo.get_company` for prices/ADV and `data.yahoo_symbol` for intraday fetch (cached 60s).
- Vite build needs `PORT` and `BASE_PATH` env set: `PORT=3000 BASE_PATH=/terminal npx vite build`.
- Engine has no execution-specific unit file yet (the 20 `tests/test_engine.py` cover backtest/signals only); verified via inline smoke + orchestrate curl + Playwright runTest.
