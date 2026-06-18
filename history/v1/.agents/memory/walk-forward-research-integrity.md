---
name: Walk-forward research-integrity validation
description: Overfitting guardrails (walk-forward, deflated Sharpe, PBO, MT haircut) as a SEPARATE panel mode from single-run backtest.
---

Research-integrity mode validates whether a strategy is overfit — it does NOT replace the single-run `backtest` panel. It is its own panel type `walk_forward`.

**Engine layering (mirror the other engine pillars):**
- `engine/stats.py` holds the pure stats, hand-rolled (no scipy in this env): `skewness`, `kurtosis` (Pearson, normal==3.0, NOT excess), `sharpe_per_obs`, `_norm_cdf`/`_norm_ppf` (Acklam), `expected_max_sharpe(n_trials, sr_variance)`, `deflated_sharpe(sr_hat, n_obs, n_trials, sr_variance, skew, kurt)` → {sr0, dsr (prob 0–1), zScore}, `multiple_testing_haircut(...)` → annualised {observed, benchmark, haircutSharpe, haircutPct, nTrials}, `pbo_cscv(returns_matrix, n_splits)` → {pbo (fraction 0–1), ...} or None when <2 configs.
- `engine/strategies.py` adds `param_grid(strategy)` + `param_label(params)`. buy_and_hold → `[{}]` (no knobs → no MT penalty, no PBO).
- `engine/backtest.py` `run_walk_forward` assembles the panel dict; its `deflatedSharpe` field MERGES haircut + deflated_sharpe outputs (so panel keys differ from raw stats dicts).

**Honest coverage:** thin history → `coverage.usable=False`, verdict label `inconclusive`, never a fabricated verdict. Folds are anchored; each fold's OOS window starts after its IS window (no look-ahead).

**Why a per-day price feed matters:** `build_walk_forward` pulls `repo.price_series_meta(days=750)` (wants every bar) and only falls back to `data.price_series` mock if the DB is empty.

**Routing trap:** the heuristic `wants_walkforward` block MUST run BEFORE `wants_backtest` in agent.py — "strategy"/"sharpe" collide and would otherwise be captured by the backtest branch. Keywords: overfit, walk-forward, out-of-sample/oos, in-sample, deflated sharpe, pbo, multiple testing, data-mined, robustness.

**Panel is passthrough:** `walk_forward` is rendered by `WalkForwardPanel.tsx` via `panel.data as any` — no openapi codegen, do NOT add to `harness.DATA_MODELS`. Frontend defines its own local `WalkForwardData` interface.
