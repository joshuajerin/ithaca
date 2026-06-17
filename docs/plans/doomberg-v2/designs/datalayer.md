# Design: Data Layer (MCP Tool Surface)

I now have a complete picture of v1's capabilities, provenance contracts, isolation model, and the review's lessons. I'll write the design doc as my return value.

# Doomberg v2 — DATA LAYER MCP Tool Surface (Design Doc)

Status: design. Scope: the DATA LAYER only (skillsets the user's external agent calls). The DEPLOY LAYER and the web observability UI are separate docs. Primary interface is an MCP server; a thin REST/SSE layer mirrors the same core for the web UI.

Source paths referenced (v1, ported on demand):
- Engine (pure numpy quant): `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/engine/`
- Data adapters: `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/sources/`
- Skill builders (orchestration glue): `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/skills.py`

---

## 0. Design lessons carried from the v1 review (these are invariants, not suggestions)

From `docs/reviews/architecture-review-2026-06-16.md` and `.agents/memory/`:

1. **Provenance is mandatory on every payload.** v1 already learned to emit `source/asOf/live|mock` and `coverage` (see `prices.fetch_price_history` `quote.asOf`, factor-risk "honest coverage", PIT/survivorship "report missing, never impute"). v2 makes this a *typed envelope every tool returns* — not a per-builder convention that can be forgotten.
2. **Tenant isolation is an invariant, not per-call-site plumbing.** v1's win was a request-bound contextvar (`app/tenant.py`) set once in `require_identity`, with `list_all_strategies()` as the single audited cross-tenant escape hatch. v2 keeps this: isolation enforced at the framework boundary, not threaded through tools.
3. **Static-guard-then-trust is unsafe.** v1's runtime AI codegen (`feature_builder`/`code_guard` AST allow-list) is **DROPPED** in v2. No agent-authored code executes in our process. Tools are a fixed, versioned catalog.
4. **Per-call timeouts but no aggregate deadline = runaway sessions.** v2 adds a **session-level deadline + token/credit budget** in addition to per-tool timeouts (v1 had `_resilient.py` per-call timeouts/breakers but nothing capping a whole research session).
5. **Unlocked read-modify-write caused races.** Any cache/quota counter mutation in v2 goes through atomic ops (Redis INCR / `SETNX` / Lua), never get-then-set.
6. **Tests that don't gate are theater.** Every tool ships a contract test (schema + provenance + isolation) that runs in CI and gates merge.

---

## 1. MCP Tool Taxonomy

Naming convention: `doomberg.<group>.<verb_noun>` (dotted, lowercase, snake within segment). Groups below. Each tool lists purpose and the v1 module it ports from.

### 1.1 `market` — prices, quotes, microstructure
Ports from `sources/prices.py`, `sources/iex_deep.py`, `skills.py:build_price_chart/build_intraday_chart/build_order_book/build_trade_flow`.

| Tool | Purpose | Ports from |
|---|---|---|
| `market.get_quote` | Latest quote (price, %chg, 52w hi/lo, volume) for symbols | `prices.fetch_price_history.quote` |
| `market.get_ohlcv` | Daily OHLCV history over a range | `prices.fetch_price_history` |
| `market.get_intraday` | Intraday bars (1m–1h) with honest "unavailable" on out-of-window | `prices.fetch_intraday`, `IntradayUnavailable` |
| `market.get_daily_closes` | PIT-safe close series for a [start,end] (real-only, never imputed) | `prices.fetch_daily_closes` |
| `market.reconstruct_order_book` | IEX DEEP L2 book/ladder reconstruction for a session | `iex_deep.reconstruct`, `list_deep_sessions` |
| `market.list_book_sessions` | Available DEEP session dates | `iex_deep.list_deep_sessions` |
| `market.get_trade_flow` | Trade/tape flow summary | `skills.build_trade_flow` |

### 1.2 `fundamentals` — company financials & analytics
Ports from `sources/fundamentals.py`, `sources/sectors.py`, `skills.py:build_fundamentals/build_company_analytics*/build_comparison`.

| Tool | Purpose | Ports from |
|---|---|---|
| `fundamentals.get_snapshot` | Valuation/margins/cap snapshot (unit-corrected: divYield already %, profitMargins fraction) | `fundamentals.fetch_fundamentals` |
| `fundamentals.get_history` | Multi-period fundamentals history | `fundamentals.fetch_fundamentals_history` |
| `fundamentals.get_market_cap` | Market cap | `fundamentals.fetch_market_cap` |
| `fundamentals.get_company_analytics` | Derived company analytics panel | `skills.build_company_analytics` |
| `fundamentals.compare_companies` | Side-by-side metric comparison | `skills.build_company_analytics_compare`, `build_comparison` |
| `fundamentals.classify_sector` | Map raw sector/industry to canonical sector | `sectors.map_sector` |

### 1.3 `calendar` — earnings, releases, M&A
Ports from `sources/fundamentals.py:fetch_calendar`, `skills.py:build_earnings_calendar/build_ma_tracker/build_economic_releases/build_series_revisions`.

| Tool | Purpose | Ports from |
|---|---|---|
| `calendar.get_earnings` | Earnings calendar for symbols/window | `fundamentals.fetch_calendar`, `build_earnings_calendar` |
| `calendar.get_ma_activity` | M&A tracker | `build_ma_tracker` |
| `calendar.get_economic_releases` | Upcoming/recent macro releases (FRED) | `rates.fetch_economic_releases`, `build_economic_releases` |
| `calendar.get_series_revisions` | FRED vintage/revision history for a series | `rates.fetch_series_revisions`, `build_series_revisions` |

### 1.4 `news` — headlines & sentiment
Ports from `sources/news.py`, `sources/sentiment.py`, `skills.py:build_news/build_sentiment`.

| Tool | Purpose | Ports from |
|---|---|---|
| `news.get_ticker_news` | Per-symbol headlines (Yahoo RSS; note: includes generic articles) | `news.fetch_news` |
| `news.get_topic_news` | Topic/market headlines (Google News RSS) | `news.fetch_topic_news`, `fetch_market_news` |
| `news.get_sentiment` | Derived sentiment score/label over a headline set | `sentiment.derive_sentiment`, `classify_headline`, `build_sentiment` |

### 1.5 `ownership` — insider / congress / 13F / institutional
Ports from `sources/edgar.py`, `sources/congress.py`, `sources/thirteenf.py`, `sources/holdings.py`, `skills.py:build_insider_activity/build_congress_trades/build_institutional_holders/build_institutional_flows/build_filings_browser`.

| Tool | Purpose | Ports from |
|---|---|---|
| `ownership.get_insider_transactions` | Form 3/4/5 insider trades for a company | `edgar.fetch_insider_transactions` |
| `ownership.get_congress_trades` | STOCK Act disclosures (BOTH txn+disclosure dates, ranges not points) | `congress.fetch_congress_trades`, `build_congress_trades` |
| `ownership.get_13f_holdings` | 13F institutional holdings (CUSIP→ticker resolved) | `thirteenf.*`, `build_institutional_holders` |
| `ownership.get_institutional_flows` | Aggregate institutional flow view | `build_institutional_flows` |
| `ownership.get_etf_holdings` | ETF top holdings + reverse exposure (top-holdings only; coverage reported) | `holdings.fetch_etf_holdings` |
| `ownership.search_filings` | EDGAR full-text + company filing search | `edgar.full_text_search`, `fetch_company_filings`, `build_filings_browser` |

### 1.6 `signals` — factor signals & research
Ports from `engine/signals.py`, `engine/stats.py`, `skills.py:build_factor_analysis/build_correlation_matrix`.

| Tool | Purpose | Ports from |
|---|---|---|
| `signals.list_signals` | Catalog of available signals + metadata (`needs`, `kind`, `desc`) | `signals.SIGNAL_META`, `available_signals` |
| `signals.evaluate_signal` | Score a universe by one signal (momentum, short_reversal, low_volatility, value, quality) | `signals.evaluate_signal` |
| `signals.combine_signals` | Blend signals via a combine method (z-score/rank/etc.) | `signals.combine_signals`, `COMBINE_METHODS` |
| `signals.compute_ic` | Spearman information coefficient / IC stats for a signal | `signals.spearman_ic` |
| `signals.correlation_matrix` | Cross-asset/return correlation matrix | `skills.build_correlation_matrix` |
| `signals.factor_analysis` | Single/cross-sectional factor analysis | `skills.build_factor_analysis` |

### 1.7 `risk` — factor risk models, attribution, stress
Ports from `engine/riskmodel.py`, `engine/attribution.py`, `engine/stress.py`, `engine/scenario.py`, `skills.py:build_risk_model/build_risk_comparison/build_portfolio_risk/build_scenario`.

| Tool | Purpose | Ports from |
|---|---|---|
| `risk.build_factor_model` | Barra-style factor model (PCA variance, exposures) | `riskmodel.build_model`, `pca_variance` |
| `risk.decompose_portfolio` | Factor/specific risk decomposition of a book | `riskmodel.decompose_portfolio`, `build_risk_model` |
| `risk.compare_risk` | Compare two portfolios' risk profiles | `build_risk_comparison` |
| `risk.attribution` | Brinson + factor attribution / active stats | `attribution.brinson`, `brinson_linked`, `factor_attribution`, `active_stats` |
| `risk.stress_scenario` | Apply factor/asset shocks; replay a historical window | `stress.factor_shock_pnl`, `asset_shock_pnl`, `replay_window`, `univariate_beta` |
| `risk.project_scenario` | Forward scenario projection | `scenario.project_scenario`, `combine_returns` |
| `risk.performance_stats` | Sharpe/Sortino/CAGR/maxDD/VaR/CVaR on a return series | `stats.*` |

### 1.8 `portfolio` — construction & optimization
Ports from `engine/portfolio.py`, `engine/optimize.py`, `skills.py:build_rebalance_plan`.

| Tool | Purpose | Ports from |
|---|---|---|
| `portfolio.construct` | Build weights from scores under a scheme | `portfolio.construct_portfolio`, `SCHEMES` |
| `portfolio.optimize_mean_variance` | Mean-variance optimization with constraints | `optimize.mean_variance`, `Constraints` |
| `portfolio.optimize_risk_parity` | Risk parity / risk-contribution weighting | `optimize.risk_parity`, `risk_contributions` |
| `portfolio.optimize_hrp` | Hierarchical risk parity | `optimize.hrp` |
| `portfolio.black_litterman` | Black-Litterman with views | `optimize.black_litterman`, `implied_risk_aversion` |
| `portfolio.stats` | Portfolio expected return/vol/diversification | `optimize.portfolio_stats` |
| `portfolio.rebalance_plan` | Generate a rebalance/trade list to target | `skills.build_rebalance_plan` |

### 1.9 `backtest` — backtest primitives (NOT deploy)
Ports from `engine/backtest.py`, `engine/strategies.py`, `engine/montecarlo.py`, `skills.py:build_backtest/build_walk_forward/build_walk_forward_compare/build_monte_carlo`. These are **research primitives** the agent calls; *deploying* a strategy is the DEPLOY LAYER.

| Tool | Purpose | Ports from |
|---|---|---|
| `backtest.list_strategies` | Built-in strategy catalog + default params + grids | `strategies.available_strategies`, `default_params`, `param_grid` |
| `backtest.run` | Run a strategy over real OHLCV; no-lookahead position lag | `backtest.run_backtest`, `resolve_entry` |
| `backtest.walk_forward` | Walk-forward with overfitting guardrails (DSR/PBO/MT-haircut) | `backtest.run_walk_forward`, `build_walk_forward` |
| `backtest.walk_forward_compare` | Compare WF results across params/symbols | `build_walk_forward_compare` |
| `backtest.monte_carlo` | Bootstrap/GBM forward path projection | `montecarlo.monte_carlo` |

### 1.10 `execution` — TCA & cost modeling (paper-only seam)
Ports from `engine/execution.py`, `engine/borrow.py`, `engine/paperbook.py`, `skills.py:build_tca_report/build_shorting_desk`.

| Tool | Purpose | Ports from |
|---|---|---|
| `execution.estimate_costs` | Pre-trade cost estimate (square-root impact) | `execution.estimate_trade_costs`, `square_root_impact` |
| `execution.simulate_orders` | Simulate algo fills on REAL intraday only | `execution.generate_orders`, `simulate_all` |
| `execution.tca_report` | Realized vs modeled TCA | `execution.aggregate_tca`, `build_tca_report` |
| `execution.borrow_profile` | Borrow tier / margin / carry breakdown for shorts | `borrow.classify_borrow`, `margin_profile`, `carry_breakdown`, `build_shorting_desk` |

### 1.11 `options` — chains, greeks, vol, strategies
Ports from `skills.py:build_options_chain/build_options_screener/build_options_strategy/build_iv_surface/build_vol_term_structure/build_structured_product` (engine BS/greeks helpers in `engine/__init__`-adjacent skills helpers).

| Tool | Purpose | Ports from |
|---|---|---|
| `options.get_chain` | Options chain with BS-priced quotes + greeks | `build_options_chain`, `_bs_price`, `_bs_greeks` |
| `options.screen` | Screen options by rank/type/moneyness | `build_options_screener` |
| `options.price_strategy` | Price a multi-leg strategy (spreads, etc.) | `build_options_strategy`, `_parse_strategy` |
| `options.iv_surface` | Implied vol surface | `build_iv_surface`, `_iv_smile` |
| `options.vol_term_structure` | Vol term structure | `build_vol_term_structure` |
| `options.structured_product` | Structured-product payoff modeling | `build_structured_product` |

### 1.12 `fixedincome` — rates, curves, credit
Ports from `sources/rates.py`, `skills.py:build_yield_curve/build_sovereign_compare/build_bond_rv/build_cds_pricer/build_credit_stress/build_cashflow_duration`.

| Tool | Purpose | Ports from |
|---|---|---|
| `fixedincome.get_treasury_curve` | UST curve (+ inversion read) | `rates.fetch_treasury_curve`, `build_yield_curve` |
| `fixedincome.interp_rate` | Interpolate a tenor off the curve | `rates.interp_treasury` |
| `fixedincome.compare_sovereigns` | Cross-country curve compare | `build_sovereign_compare` |
| `fixedincome.bond_relative_value` | Bond RV analysis | `build_bond_rv` |
| `fixedincome.cashflow_duration` | Price/duration/convexity from cashflows | `build_cashflow_duration`, `_bond_price` |
| `fixedincome.cds_price` | CDS pricer (survival/hazard) | `build_cds_pricer`, `_cds_survival` |
| `fixedincome.credit_spreads` | IG/HY credit spread levels + history | `rates.fetch_credit_spreads`, `fetch_credit_spread_history` |
| `fixedincome.credit_stress` | Credit stress regime read | `build_credit_stress` |

### 1.13 `macro` — regime, FRED series, prediction markets
Ports from `sources/rates.py` (FRED), `sources/polymarket.py`, `skills.py:build_macro_dashboard/build_polymarket_*`.

| Tool | Purpose | Ports from |
|---|---|---|
| `macro.get_regime` | Macro regime dashboard (per-tile isLive) | `build_macro_dashboard`, `_compute_macro_regime` |
| `macro.get_fred_series` | A FRED series + metadata + next release | `rates.fetch_fred_series_meta`, `fetch_fred_next_release` |
| `macro.list_prediction_markets` | Polymarket markets by category | `polymarket.fetch_events`, `build_polymarket_markets` |
| `macro.get_prediction_market` | One market (price history, trades) | `polymarket.fetch_market_by_*`, `fetch_price_history`, `fetch_trades`, `build_polymarket_market` |
| `macro.get_prediction_wallet` | Polymarket wallet positions | `polymarket.fetch_wallet`, `build_polymarket_wallet` |

### 1.14 `screen` — cross-sectional discovery
Ports from `skills.py:build_screener/build_heatmap/build_data_universe/build_sectors`.

| Tool | Purpose | Ports from |
|---|---|---|
| `screen.universe` | List the tracked-live vs mock-on-demand universe (PIT-aware via listedAt) | `build_data_universe`, universe registry |
| `screen.run_screener` | Filter universe by metric criteria | `build_screener` |
| `screen.heatmap` | Sector/market heatmap | `build_heatmap` |

### 1.15 `meta` — discovery, provenance, session
New in v2 (thin), plus `skills.py:build_data_quality`.

| Tool | Purpose | Ports from |
|---|---|---|
| `meta.list_tools` | Machine-readable catalog of all tools (groups, schemas, cost class) | new |
| `meta.data_quality` | Coverage/freshness diagnostics for a symbol or universe | `build_data_quality` |
| `meta.open_research_session` | Open a research session bound to a focus (symbol/universe/strategy) | new (see §3) |
| `meta.session_summary` | Current session budget, deadline, and provenance ledger | new |

**Explicitly dropped from v1:** the runtime self-building feature pipeline (`feature_builder.py`, `code_guard.py`, `dynamic_skills.py`, `skills_generated/`) and the in-process LLM `agent.py` loop. v2 does not run the agent and does not execute agent-authored code. The strategy marketplace (`build_strategy_marketplace`) and live "desk" panels (`build_strategy_desk/multi_strategy`) move to the DEPLOY LAYER, not the data layer.

---

## 2. Tool schema conventions

### 2.1 Envelope (every tool returns this shape)
Provenance is structural, not optional. Every tool result is wrapped:

```jsonc
{
  "data": { /* tool-specific payload */ },
  "provenance": {
    "source": "yahoo-chart",          // upstream identifier (matches _resilient breaker key)
    "asOf": "2026-06-16T14:32:05Z",   // ISO8601 UTC of the underlying data, NOT fetch time
    "freshness": "live",              // "live" | "stale" | "mock"
    "staleAgeSec": 0,                 // null when live; age past TTL when stale
    "coverage": {                     // honest coverage — never impute
      "requested": 12, "resolved": 11, "missing": ["BRKB"],
      "pit": true,                    // point-in-time / survivorship-safe where applicable
      "note": "ETF feed returns top holdings only"
    },
    "cost": { "class": "cheap", "credits": 1 },
    "cacheHit": true
  },
  "partial": false,                   // true when some sub-requests failed but result is usable
  "warnings": [
    { "code": "MOCK_FALLBACK", "message": "US2Y has no free source; synthetic", "scope": "US2Y" }
  ]
}
```

Rules:
- `freshness` is computed from the adapter, mirroring v1's per-tile `isLive` and `asOf` contract. A `mock` payload is never silently dressed as live — it carries `freshness: "mock"` and a `MOCK_FALLBACK` warning.
- `coverage.missing` is enumerated; **data is never imputed** to hide gaps (v1 PIT/survivorship lesson).
- `asOf` is the *data's* timestamp (e.g. `regularMarketTime`), distinct from fetch time, so the agent can reason about staleness.

### 2.2 Input conventions
- Symbols: array `symbols: ["AAPL", "MSFT"]`, canonical Yahoo tickers; SGX `.SI` suffix resolved internally.
- Time: `range` tokens (`"6mo"`) OR explicit `start`/`end` ISO dates. Intraday `interval` validated against the per-resolution window map; out-of-window returns a clean `UNSUPPORTED_WINDOW` error, never daily-substituted (mirrors `IntradayUnavailable`).
- All numeric params have documented units in the schema `description` (carrying forward the divYield/profitMargins unit-quirk lesson so the *agent* sees units).

### 2.3 Pagination
Cursor-based, opaque: requests take `cursor` + `limit` (server-capped, e.g. max 200); responses return `nextCursor` (null = done) inside `data.page`. No offset pagination (stable under live updates).

### 2.4 Errors (typed, not strings)
MCP tool error result with a stable `code`:

```jsonc
{ "error": { "code": "UPSTREAM_THROTTLED", "message": "...", "retryable": true, "retryAfterSec": 30 } }
```

Code taxonomy: `BAD_INPUT`, `NOT_FOUND`, `UNSUPPORTED_WINDOW`, `UPSTREAM_THROTTLED` (maps to `_resilient.ThrottleError`), `UPSTREAM_UNAVAILABLE` (`CircuitOpenError` — breaker open), `RATE_LIMITED` (tenant quota), `SESSION_BUDGET_EXCEEDED`, `DEADLINE_EXCEEDED`, `INTERNAL`. Throttle/breaker errors are `retryable: true` with `retryAfterSec`; a 404-class miss is `NOT_FOUND` and not retried (matches v1's "non-throttle errors propagate immediately").

### 2.5 Partial data
A multi-symbol tool returns `partial: true` with `coverage.missing` populated rather than failing the whole call when some symbols throttle. This is the v1 best-effort-fallback behavior made explicit in the envelope.

---

## 3. Composition: how an agent "looks into a stock and works on it"

### 3.1 Discoverability
- MCP `tools/list` is the entry point; `meta.list_tools` returns a richer catalog grouped by §1, each tool tagged with `costClass` (`cheap`/`network`/`heavy-compute`) and `dependsOn` hints (e.g. `risk.decompose_portfolio` depends on `market.get_daily_closes`).
- Consistent `get_*` / `run_*` / `compute_*` verbs and the `<group>.<verb_noun>` naming let an agent pattern-match without reading every schema.

### 3.2 Research-session concept
`meta.open_research_session` returns a `sessionId` bound to a `focus` (a symbol, a universe, or a strategy draft). Passing `sessionId` to subsequent tools gives:
- **Shared resolution context:** symbol→CIK/CUSIP/sector resolved once (ports `edgar.resolve_cik`, `thirteenf.resolve_ticker_cusip`) and reused.
- **A provenance ledger:** every tool call's `provenance` is appended; `meta.session_summary` returns the merged freshness picture (so the agent — and the web UI observing it — can see "this thesis rests on 1 stale credit print + live prices").
- **Budget + deadline enforcement (review lesson #4):** the session carries a wall-clock `deadline` and a `creditBudget`; tools check both before running heavy compute. This is the aggregate cap v1 lacked.
- **The web UI observability hook:** the session is exactly what the BYO-agent observability surface renders (tool calls, args, results, the thought trace). Session events are published on the SSE layer.

### 3.3 A canonical "work on AAPL" flow
`meta.open_research_session(focus={symbol:"AAPL"})` → `fundamentals.get_snapshot` + `market.get_ohlcv` + `news.get_sentiment` + `ownership.get_insider_transactions` (fan-out) → `signals.evaluate_signal` (momentum/quality) → `risk.stress_scenario` → `backtest.run` → `portfolio.rebalance_plan`. Each result shares `sessionId`; the agent reasons; if the user accepts, the resulting strategy spec is handed to the DEPLOY LAYER.

---

## 4. Auth, isolation, rate limiting, caching

### 4.1 Auth for the MCP connection
- **Primary: per-tenant API keys.** A firm admin mints scoped keys in the console (ports the firm/role model from `auth_store.py`). Key format `dbg_<tenant>_<random>`; only a hash is stored (carries forward `auth.hash_token` — never store the raw token). The MCP transport authenticates via `Authorization: Bearer <key>`.
- **OAuth (MCP authorization) as the interactive path** for agent hosts that support it, issuing the same scoped, tenant-bound token. Scopes map to tool groups (e.g. `read:market`, `read:ownership`, `compute:risk`) so a key can be least-privilege.
- The REST/SSE web layer reuses v1's httpOnly `at_session` cookie path; both resolve to the same identity object.

### 4.2 Multi-tenant isolation (hard invariant)
- A request-bound **tenant contextvar** is set once at the MCP/HTTP boundary after auth (direct port of `app/tenant.py` + the async-`require_identity` reason: Starlette copies the contextvar into the sync threadpool). Tools never take a `tenant_id` argument — the context carries it.
- All tenant-scoped stores (research sessions, saved focuses, quotas, cached *derived* results) read `current_tenant_id()` internally. A single audited cross-tenant escape hatch (`list_all_*`, worker-only, wrapped in `tenant_context(...)`) mirrors v1; nothing else may cross tenants.
- **Shared-by-design exception, made explicit:** upstream *market* data (Yahoo OHLCV, EDGAR, FRED, Polymarket, IEX DEEP replays) is public and identical across tenants, so the *raw upstream cache* is global. Only *derived/owned* artifacts (sessions, portfolios, screener saves, quota counters) are tenant-scoped. This boundary is documented per-cache, not decided ad hoc per call site.
- Contract tests assert isolation per tool: tenant A's session/quota is never visible to tenant B. These gate CI (review lesson #6).

### 4.3 Rate limiting + quotas (per tenant)
- **Token-bucket per tenant per cost class** (`cheap`/`network`/`heavy-compute` have separate buckets so a backtest storm can't starve quote lookups). Counters use **atomic Redis INCR/Lua** — never get-then-set (review lesson #5: no unlocked read-modify-write).
- Monthly **credit quota** per tenant; each tool's `cost.credits` debits atomically. Exceeding returns `RATE_LIMITED` / `SESSION_BUDGET_EXCEEDED`.
- Upstream protection still uses v1's `_resilient.py` per-source circuit breakers + backoff (breaker keys: `yahoo-chart`, `yahoo-rss`, `google-news`, `yfinance`, plus new `edgar`, `fred`, `polymarket`, `iex-deep`). Breaker-open surfaces as `UPSTREAM_UNAVAILABLE`, which combines with stale-serve below.

### 4.4 Caching with stale-serve
- Two-tier: in-process LRU (hot, short TTL) → Redis (shared, per-source TTL mirroring v1's `_rates_ttl`/`_poly_ttl` cadences). Keyed by normalized request, **global for public upstream data**, tenant-prefixed for derived data.
- **Stale-while-revalidate:** on TTL expiry serve the cached payload immediately with `freshness: "stale"` + `staleAgeSec`, and trigger an async refresh. If the breaker is open, keep serving stale (better than failing) — the envelope tells the agent it's stale.
- A cache entry stores its own `provenance`, so a stale-served result still carries the original `asOf`/`source` honestly.

---

## 5. Greenfield repo / module structure (data layer)

```
doomberg-data/                      # greenfield; ports v1 numpy logic, rebuilt structure
  pyproject.toml
  src/doomberg_data/
    server/
      mcp_server.py                 # MCP server: registers tool catalog, auth middleware
      rest_app.py                   # thin REST/SSE mirror for the web UI (same core)
      auth.py                       # API-key + OAuth verification (ports auth.py hashing)
      tenant.py                     # contextvar isolation (direct port; keep async boundary)
      ratelimit.py                  # token buckets + credit quota (atomic Redis ops)
      errors.py                     # typed error codes
    core/
      envelope.py                   # Envelope/Provenance/Coverage dataclasses + builders
      registry.py                   # tool catalog, cost classes, scopes, meta.list_tools
      session.py                    # research sessions: focus, ledger, deadline, budget
      cache.py                      # 2-tier cache + stale-while-revalidate
      resilient.py                  # retry + circuit breaker (port of sources/_resilient.py)
    adapters/                       # PORTED from v1 app/sources/, minimal edits
      prices.py  fundamentals.py  news.py  sentiment.py  sectors.py
      edgar.py   congress.py  thirteenf.py  holdings.py
      rates.py   polymarket.py  iex_deep.py
    quant/                          # PORTED from v1 app/engine/, kept pure (no I/O)
      signals.py strategies.py stats.py
      riskmodel.py attribution.py stress.py scenario.py
      portfolio.py optimize.py montecarlo.py
      backtest.py execution.py borrow.py options.py
    tools/                          # one module per tool GROUP from §1; thin orchestration
      market.py fundamentals.py calendar.py news.py ownership.py
      signals.py risk.py portfolio.py backtest.py execution.py
      options.py fixedincome.py macro.py screen.py meta.py
  tests/
    contract/                       # per-tool: schema + provenance + isolation (GATES CI)
    quant/                          # ported pure-engine unit tests (standalone, no-network)
    adapters/                       # parsing tests with patched httpx/yfinance
```

Layering rule (enforced): `tools/` orchestrates `adapters/` (I/O, provenance) + `quant/` (pure numpy, no network — preserves v1's testable-in-isolation property). `quant/` never imports `adapters/` or `server/`. `server/` owns auth/isolation/limits so tools never re-implement them.

---

## Open questions for review
1. Credit-cost calibration per tool (heavy-compute backtests vs cheap quotes) — needs a pricing pass.
2. Whether `screen.universe` / saved screens are tenant-scoped derived data (yes) vs the universe registry itself (global) — confirm the boundary.
3. IEX DEEP replay is large/slow — should `market.reconstruct_order_book` be gated behind an explicit higher cost class + session opt-in.
4. OAuth scope granularity: per-group vs per-tool (proposing per-group to start).