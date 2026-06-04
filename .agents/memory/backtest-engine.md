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
