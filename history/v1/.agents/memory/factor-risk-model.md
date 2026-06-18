---
name: Barra-style multi-factor risk model
description: How the factor risk model is layered (engine vs data-assembly vs skills) and the design conventions baked into factor construction.
---

# Multi-factor risk model

Three layers, kept separate on purpose:
- **`app/engine/riskmodel.py`** — pure numpy, no I/O. Cross-sectional OLS `r_t = X f_t + e_t`
  (hat matrix computed once since X is static), factor covariance, specific variance, R²,
  `decompose_portfolio` (factor vs specific vol, MCTR via Euler, per-factor contrib),
  `pca_variance`. `TRADING_DAYS=252`.
- **`app/factor_model.py`** — bridges REAL data to the engine. Builds the estimation
  universe, aligns returns on a majority-vote date grid, builds standardized exposures,
  and enforces honest coverage (include only names with enough history + fundamentals;
  everything else excluded with a reason, never imputed). Raises `ValueError` when a
  credible model can't be estimated → harness turns it into a clean error panel.
- **`app/skills.py`** builders shape engine output into panel payloads.

**Identities that must always hold** (covered by `tests/test_riskmodel.py`):
factor_var + specific_var == total_var; per-holding risk contributions sum to total vol;
pct contributions sum to 100; `mctr * weight == risk_contrib`; diversification ratio ≥ 1.

**Factor construction conventions** (in `_build_descriptors`):
- Market exposure = raw beta (kept near 1, NOT z-scored).
- Style factors = cross-sectional z-scores, winsorized ±3 by `standardize()` (fixed clip).
- Value = 0.7·z(earnings yield = 1/PE) + 0.3·z(dividend yield).
- Momentum = cumulative window return skipping the last 10 days; then z-scored.
- Volatility = annualized stdev of daily returns; then z-scored.
- Quality = z(net margin). Size = z(ln market cap), large-cap positive.

**Why** real DB history is only ~6 months, so monthly attribution often shows <12 months —
that is honest, not a bug. `factor_analysis` folds Market+Volatility+specific into the
"residual" bucket so the stacked panel total equals the stock's actual monthly return.

**Panels**: `risk_model` (decomposition + MCTR) and `factor_exposures` (tilts + premia),
each with a coverage footer. The heuristic routes risk-decomposition language to
`risk_model` and tilt/style language to `factor_exposures`; plain VaR still → `portfolio_risk`.

`factor_performance` (passthrough panel) charts the CUMULATIVE return of each factor
over the estimation window from `model.factor_returns` (np.cumprod compounding) + a
summary table (cum/ann/vol/Sharpe/t). Routing trap: "cumulative factor returns" must be
checked BEFORE the attribution block because wants_pnl matches plain "cumulative return".

**`risk_comparison`** (A-vs-B) is a thin wrapper: it calls `build_risk_model` once per
portfolio so the factor/specific identities match the single-portfolio panel exactly,
then diffs total/factor/specific vol, the variance split, diversification ratio and
factor exposures. Routed *before* `risk_model` in the heuristic on compare/vs/"riskier
than"/"better diversified" language; heuristic splits tickers around a vs/versus/against
pivot (else halves the list). Note: `coverage.included` reflects the ~60-name estimation
universe, not the portfolio's holding count — so both sides legitimately show the same
"N modeled" number; do not mistake that for a bug.
