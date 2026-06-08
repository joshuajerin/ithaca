---
name: Backtesting & simulation engine
description: How the api-server quant engine runs strategies on real OHLCV, computes stats, and does Monte Carlo; the no-lookahead contract and fallback behavior.
---

# Backtesting & simulation engine (`app/engine/`)

A pure, deterministic, numpy-based engine (no DB/network) so it is unit-testable
in isolation. Skill builders source the price points and own the live/mock
fallback decision; the engine just computes.

## No-lookahead contract (critical)
A strategy maps a close series to a **target-position array** (one value per bar,
in [-1, 1]) using info up to and including that bar. The engine applies bar i's
position to bar i+1's return (`held[i] = target[i-1]`). Any change here
reintroduces lookahead bias and silently inflates stats.

**Why:** the original quant skills used seeded random walks, not real returns;
tests assert buy-and-hold equity equals the cumulative price ratio, which only
holds if positions are lagged correctly.

## Fallback behavior
`repo.price_series_meta(symbol, days)` returns `{points, source, asOf}` and is the
only way to know if a series is real ("live") vs the curated mock — plain
`price_series` falls back to mock **silently**. Builders carry `source`/`asOf`
into panel data for the freshness contract. The DB worker only ingests ~6mo daily
OHLCV, so `days` is effectively capped there.

## How to apply
- Add a strategy: write `signal_*` in `strategies.py`, register in `STRATEGIES`,
  add an alias in `_ALIASES`. Engine core never changes.
- Stats live in `stats.py` (returns plain floats, defensive on short input).
  `performance_stats` returns percent-scaled values (cagr/vol/var already ×100).
- Monte Carlo (`montecarlo.py`): bootstrap or GBM, seeded `np.random.default_rng`
  for determinism; fan includes step 0 (= horizon+1 points). VaR/CVaR are
  positive loss fractions; CVaR ≥ VaR always.
- Tests: `tests/test_engine.py`, standalone-runnable (`python tests/test_engine.py`)
  since pytest is NOT installed in api-server.

## Engine package re-exports (gotcha)
Skills call engine functions as `engine.<fn>` (the `app.engine` package namespace),
NOT `engine.backtest.<fn>`. A new function added to a submodule (e.g.
`backtest.resolve_entry`) MUST be re-exported from `engine/__init__.py` (both the
`from .backtest import ...` line AND `__all__`) or skills raise at runtime
"module 'app.engine' has no attribute '<fn>'" — and the panel comes back
status=error with that note (engine tests still pass, since they import the
submodule directly).

## Dollar / real-money investing (entry resolution)
`resolve_entry(points, mode, date, start, end)` picks entry/end indices: peak =
argmax close, date = first bar ≥ date, range = start..end, preset = full. Run
`run_backtest(sliced, strategy, rebase=amount)` so the equity curve is in dollars
(rebase=amount, not 100). build_backtest emits investment/entry/endValue/
benchmarkEndValue/gain/gainPct/multiple/entryNote. Peak/old-date entries need
`repo.deep_price_series` (deep Yahoo history) since the worker DB only holds ~6mo.

## "Invest $X, what's it worth now" defaults to buy_and_hold (critical UX)
**Why:** momentum (the default strategy) often sits in cash after a peak, so the
panel returns the principal unchanged (gain $0) — nonsense for "invest $1M in NVDA
at its peak, what's it worth now". A plain invest/buy-and-hold dollar question with
no named strategy must force `buy_and_hold`.
**How to apply:** orchestrate is **LLM-first, heuristic-only-as-fallback** (see
`_orchestrate_build`), so the default must be enforced in BOTH paths: the LLM
tool-call handler post-processes `add_backtest` via `_coerce_invest_backtest`
(backfills parsed amount/entry + forces buy_and_hold on invest phrasing w/o explicit
strategy), and `_orchestrate_heuristic` does the same. Detecting intent in only the
heuristic is a no-op whenever the AI is available.
