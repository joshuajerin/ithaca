# all_md.md

_Concatenation of all 99 markdown files in the Doomberg repo. Generated 2026-06-16._


## Table of contents

- `.agents/memory/MEMORY.md`
- `.agents/memory/ai-client-timeouts.md`
- `.agents/memory/analyst-compare.md`
- `.agents/memory/analyst-ratings-consensus.md`
- `.agents/memory/attribution-benchmark.md`
- `.agents/memory/attribution-multiperiod-linking.md`
- `.agents/memory/auth-firms-roles.md`
- `.agents/memory/backtest-engine.md`
- `.agents/memory/boot-smoke-check.md`
- `.agents/memory/combined-alpha.md`
- `.agents/memory/company-analytics-compare.md`
- `.agents/memory/company-profiles.md`
- `.agents/memory/compliance-gate.md`
- `.agents/memory/congress-trades-feed.md`
- `.agents/memory/console-answer-streaming.md`
- `.agents/memory/console-conversation-persistence.md`
- `.agents/memory/cost-aware-rebalancing.md`
- `.agents/memory/credit-stress-monitor.md`
- `.agents/memory/data-wall-removal.md`
- `.agents/memory/dcf-saved-models.md`
- `.agents/memory/debounced-recompute-deps.md`
- `.agents/memory/durable-session-state.md`
- `.agents/memory/earnings-calendar-panel.md`
- `.agents/memory/economic-releases-revisions.md`
- `.agents/memory/edgar-form4-xml-quirk.md`
- `.agents/memory/etf-holdings.md`
- `.agents/memory/execution-tca.md`
- `.agents/memory/factor-risk-model.md`
- `.agents/memory/filings-browser-edgar.md`
- `.agents/memory/firm-admin-console.md`
- `.agents/memory/firm-audit-trail.md`
- `.agents/memory/fixed-income-live-data.md`
- `.agents/memory/frontend-test-harness.md`
- `.agents/memory/institutional-13f.md`
- `.agents/memory/launch-video-layering.md`
- `.agents/memory/load-test-latency-baseline.md`
- `.agents/memory/macro-dashboard-overrides.md`
- `.agents/memory/macro-live-data.md`
- `.agents/memory/market-data-sources.md`
- `.agents/memory/multi-tenant-isolation.md`
- `.agents/memory/multistrat-allocation.md`
- `.agents/memory/navigator-cursor.md`
- `.agents/memory/options-chain-panel.md`
- `.agents/memory/orderbook-iex-deep-replay.md`
- `.agents/memory/panel-export.md`
- `.agents/memory/panel-inline-refine-loading.md`
- `.agents/memory/panel-layout-collision.md`
- `.agents/memory/panel-resize-handles.md`
- `.agents/memory/panel-runtime-test.md`
- `.agents/memory/passthrough-panels.md`
- `.agents/memory/pending-panel-autorefresh.md`
- `.agents/memory/period-returns.md`
- `.agents/memory/pit-survivorship-data.md`
- `.agents/memory/polymarket-prediction-markets.md`
- `.agents/memory/portfolio-optimizer.md`
- `.agents/memory/portfolio-to-desk-promotion.md`
- `.agents/memory/python-api-server.md`
- `.agents/memory/python-subprocess-maxpath.md`
- `.agents/memory/python-test-conventions.md`
- `.agents/memory/refine-explicit-params.md`
- `.agents/memory/replit-config-tooling-traps.md`
- `.agents/memory/responsive-layout.md`
- `.agents/memory/risk-monitor-pillar.md`
- `.agents/memory/role-permissions.md`
- `.agents/memory/saved-dashboards.md`
- `.agents/memory/security-hardening.md`
- `.agents/memory/self-building-features.md`
- `.agents/memory/signal-library.md`
- `.agents/memory/signal-portfolio.md`
- `.agents/memory/source-resilience.md`
- `.agents/memory/sovereign-curve-compare.md`
- `.agents/memory/stale-vite-phantom-export.md`
- `.agents/memory/strategy-lifecycle-desk.md`
- `.agents/memory/strategy-templates-marketplace.md`
- `.agents/memory/stress-test-panel.md`
- `.agents/memory/supply-chain-risk.md`
- `.agents/memory/terminal-orchestration.md`
- `.agents/memory/trade-flow-alerts.md`
- `.agents/memory/universe-breadth.md`
- `.agents/memory/voice-guided-walkthrough.md`
- `.agents/memory/voice-mode-loop.md`
- `.agents/memory/walk-forward-multi-symbol.md`
- `.agents/memory/walk-forward-research-integrity.md`
- `.agents/memory/yield-curve-recession-signal.md`
- `CLAUDE.md`
- `artifacts/api-server/SECURITY.md`
- `docs/design/v2-system-architecture.md`
- `docs/plans/doomberg-v2/DATA-SOURCING-STRATEGY.md`
- `docs/plans/doomberg-v2/MASTER-PLAN.md`
- `docs/plans/doomberg-v2/critiques/feasibility.md`
- `docs/plans/doomberg-v2/critiques/integration.md`
- `docs/plans/doomberg-v2/designs/datalayer.md`
- `docs/plans/doomberg-v2/designs/deploylayer.md`
- `docs/plans/doomberg-v2/designs/repo-sequencing.md`
- `docs/plans/doomberg-v2/designs/security.md`
- `docs/plans/doomberg-v2/designs/topology.md`
- `docs/plans/doomberg-v2/designs/webui.md`
- `docs/reviews/architecture-review-2026-06-16.md`
- `replit.md`




====================================================================================================
FILE: .agents/memory/MEMORY.md
====================================================================================================

- [Python backend on api-server artifact](python-api-server.md) — how to run a Python/FastAPI service in the shared `api-server` artifact (uvicorn, --app-dir, $PORT, restart-after-toml-swap).
- [Terminal dashboard orchestration](terminal-orchestration.md) — orchestrate is additive-by-default (append panels), "default"/reset mint a fresh session; panels animate via framer-motion keyed by id.
- [Free market data sources + quirks](market-data-sources.md) — Yahoo chart/RSS + yfinance: unit gotchas (dividendYield already %, profitMargins fraction), sector lives on universe, asOf/source freshness contract.
- [Source resilience (retry + breaker)](source-resilience.md) — all sources route through _resilient.py: per-source circuit breaker + backoff; throttle detected by status (httpx) vs exception (yfinance); distinct throttle log.
- [Fixed-income live data](fixed-income-live-data.md) — key-less US Treasury CSV + keyed FRED ICE BofA OAS (fredgraph blocked here, api.stlouisfed.org works); credit needs FRED_API_KEY, Treasury doesn't.
- [Self-building feature pipeline](self-building-features.md) — Build Feature: AI generates skill+panel at runtime, registered in-process (no restart); why api-server runs without --reload; clean-failure + dynamic-panel rendering contract.
- [AI client timeouts vs preview proxy](ai-client-timeouts.md) — bound the OpenAI client (timeout + max_retries=0) under the ~60s proxy window; callers must fall back on timeout like any failure.
- [Panel layout collision resolution](panel-layout-collision.md) — dashboard overlap fix uses two-pass reserve-then-reflow (not single-pass greedy) so non-conflicting panels keep AI positions.
- [Voice Mode push-to-talk](voice-mode-loop.md) — hold orb to listen / release to send (no auto re-arm); continuous=true + graceful stop() vs abort(); mic off during TTS; iframe blocks Web Speech; compact mobile layout.
- [Backtesting & simulation engine](backtest-engine.md) — pure numpy engine in app/engine/; no-lookahead position lag, real OHLCV via price_series_meta (live/mock+asOf), Monte Carlo bootstrap/GBM.
- [Stale Vite phantom export](stale-vite-phantom-export.md) — "no export named X" in browser when source has it = orphaned dev server stuck on ports + stale graph; fix is restart_workflow, not code.
- [Stock universe breadth (US + SGX)](universe-breadth.md) — CORE tracked-live vs bulk mock-on-demand split; SGX base codes + .SI at fetch only; is_live provenance; prompt_symbols cap.
- [Launch video layering & perf](launch-video-layering.md) — persistent layers by baseSceneKey; single rAF loop, no blur filters, scrims behind text fix lag+overlap.
- [Period returns (day vs year)](period-returns.md) — changePct is 1D only; real returns from price series via returns.py; screener/heatmap use YTD not 1Y (live DB ~6mo).
- [AI navigator cursor](navigator-cursor.md) — chat-triggered guided cursor; tours only real session panels via [data-panel-id]; shares highlight with voice so never co-run; intent-strip routing.
- [Voice-driven guided walkthroughs](voice-guided-walkthrough.md) — spoken tour intent runs navigator cursor + TTS captions; conductor owns turn/barge-in, navigator narrated mode advances via async goTo synced to audio end.
- [Adding hand-written panel types](passthrough-panels.md) — new panel types pass through without openapi codegen (Panel.data is dict); stale-PanelType tsc errors are expected and don't gate the vite build.
- [Barra-style factor risk model](factor-risk-model.md) — 3 layers (pure-numpy engine / honest-coverage data assembly / skill builders); decomposition identities + factor-construction conventions.
- [Alpha signal library & eval](signal-library.md) — cross-sectional IC/decay/turnover/spread; real-data-only (exclude+report); builders return data-only; "rank IC" trap in research-vs-scorecard dispatch.
- [Risk Management & Monitoring pillar](risk-monitor-pillar.md) — risk_monitor panel: book exposures+limits, real crisis replay (period1/period2 fetch, missing flagged), hypothetical shocks; routed before scenario.
- [Execution simulation & TCA](execution-tca.md) — algos sim on REAL intraday only (raise on empty→unsupported); realized vs modeled square-root impact; tca_report strictly validated by models.TCARportData; source/asOf lifted to envelope.
- [Attribution benchmark must be REAL](attribution-benchmark.md) — attribution benchmarks must be real traded ETFs (never a synthetic universe); date-align to window, size fetch to range, report coverage.
- [api-server Python test conventions](python-test-conventions.md) — standalone (no pytest) self-running suites; patch shared `db` module for live/mock, `httpx.Client`/`yf.Ticker` for adapter parsing.
- [Supply chain risk scoring](supply-chain-risk.md) — concentration×geo risk score per node; built-in panels have a pydantic model in harness.DATA_MODELS that strips unknown fields (add fields to models.py too).
- [Earnings calendar panel + alert](earnings-calendar-panel.md) — passthrough earnings_calendar type; explicit-symbol horizon=120 vs watchlist=30; Terminal.tsx imminent banner reuses formatEarningsCountdown.
- [Sovereign curve comparison panel](sovereign-curve-compare.md) — multi-curve overlay adds per-tenor twist (shared _region_spot) so cross-market spreads vary; route before yield_curve.
- [Console conversation persistence](console-conversation-persistence.md) — transcript+sessionId in localStorage; ChatPanel now controlled; reset = new sessionId → clear; survives refresh not server restart.
- [Replit config tooling traps](replit-config-tooling-traps.md) — validation tooling hijacks/over-removes `.replit` runButton="Project" (unrecoverable via tools); package firewall 403-blocks vitest, so no committed JS test runner.
- [Options chain panel](options-chain-panel.md) — full calls/puts ladder; all expiries in one payload (client-side tab+pagination); synthetic-but-grounded quotes (BS mid + deterministic spread/vol/OI); wants_chain routed before iv_surface/options.
- [Panel resize handles](panel-resize-handles.md) — drag edge/corner handles resize panels in-grid; grid math must mirror CSS gap/row; commits w/h to session only.
- [API Server boot smoke check](boot-smoke-check.md) — `pnpm smoke:api` boots app + asserts orchestrate 200; NOT a registered validation (setValidationCommand hijacks the multi-artifact Run button, unfixable in-repo); yfinance MAX_PATH only in agent bash; TERMINAL_SKIP_WORKER hook.
- [Multi-period Brinson linking (Carino)](attribution-multiperiod-linking.md) — long windows use per-day BHB scaled by Carino k_t/k so effects sum to the geometric active return; brinson_linked vs single-period brinson.
- [DCF saved custom models](dcf-saved-models.md) — named assumption sets persist per session+symbol in state.py; DCFPanel uses raw /api/dcf-models fetch (no codegen); restore just resets local assumptions.
- [Macro dashboard live data](macro-live-data.md) — isolated macro_quotes ingest (not equity universe); MACRO_YAHOO map; US2Y/2Y10Y/TIPS/iron have no free source → stay mock; staleness guard; per-tile isLive.
- [Refine with explicit params](refine-explicit-params.md) — RefineRequest.params bypasses LLM/heuristic for deterministic in-panel controls; include symbol, use a separate mutation for in-panel spinner.
- [Company profiles (sub-industry + logos)](company-profiles.md) — subIndustry+logoUrl on every record; _apply_company_profiles must run AFTER bulk _load() or bulk names (incl AAPL) miss stamping; live Yahoo industry/website override curated.
- [Signal → portfolio construction](signal-portfolio.md) — "build a portfolio from <signal>" → tradeable book; top_quantile (long-only) vs long_short (dollar-neutral); dispatch before scorecard/backtest and off the word "strategy".
- [Combined alpha (signal blend)](combined-alpha.md) — blend N signals into one composite (equal/ic/inverse-corr), scored vs components + overlap matrix; per-component ctx for value+quality; routed before scorecard, after portfolio-build.
- [Scenario stress test panel](stress-test-panel.md) — stress_test scales each name's REAL fitted beta (SPY/^TNX-level-Δ/CL=F) by the scenario shock; distinct from risk_monitor replay; honest coverage.
- [Company analytics head-to-head compare](company-analytics-compare.md) — `company_analytics_compare` panel: two columns of drivers+catalysts + per-metric leader scoreboard; query-order symbol ordering.
- [Data wall removal](data-wall-removal.md) — arbitrary Yahoo tickers via note_symbol+pending envelope; live macro in SEPARATE macro_quotes table (no equity-screener leak); news uncapped to 100.
- [Terminal frontend test harness (vitest)](frontend-test-harness.md) — jsdom + custom Voice Mode browser-API mocks (drive SpeechRecognition/AudioContext/getUserMedia by hand); test files excluded from tsc.
- [Console answer streaming](console-answer-streaming.md) — questions stream token-by-token via SSE (/orchestrate/stream); builds stay non-streaming; orchestrate & orchestrate_stream share helpers; empty-stream falls back to blocking.
- [Strategy lifecycle & paper book desk](strategy-lifecycle-desk.md) — registry+paperbook+lifecycle; deterministic intent handler before LLM; runtime CREATE TABLE not drizzle push; mark has no weight (use exposures); vite build needs PORT+BASE_PATH.
- [Multi-ticker analyst compare](analyst-compare.md) — fan out build_analyst_report per symbol concurrently, isolate per-name failures; heuristic keyword traps ("view"⊂"overview").
- [Macro dashboard overrides](macro-dashboard-overrides.md) — pin/remove macro tiles via refine; overrides persisted in panel data + on the pydantic model, merged latest-op-per-symbol.
- [Debounced recompute deps](debounced-recompute-deps.md) — panels: a debounced re-run effect must depend on primitives only (refs for symbols/callback), and reset must key off a stable signature, or churning `data` refs starve the timer / wipe edits.
- [Running Python scripts interactively](python-subprocess-maxpath.md) — ad-hoc `python3 foo.py` dies with a MAX_PATH wrapper error; run via `env -i …/.pythonlibs/bin/python3.11`.
- [Saved dashboard layouts](saved-dashboards.md) — name→save/restore; dashboard_store jsonb panels (full payload inline), dedup-by-name; restore mints fresh session; status enum ok|loading|error not "ready".
- [Generated-panel production runtime test](panel-runtime-test.md) — real vite build + post-build panel proves runtime fetch→sucrase→eval path; runs under vitest+jsdom; registry glob try/catch-guarded so it imports outside Vite.
- [Terminal responsive layout](responsive-layout.md) — 3-tier breakpoints: mobile stack / tablet 6-col flow (drops AI x/y) / desktop 12-col placed; console is a drawer on non-desktop.
- [Panel CSV/PDF export](panel-export.md) — client-side quant-panel export; MUST use html2canvas-pro (not html2canvas) under Tailwind v4 oklch; rebuild api-client-react dist on stale shared-type tsc errors.
- [Trade-flow alert rules](trade-flow-alerts.md) — per-session rule/event store; static /alerts/events routes MUST precede /alerts/{rule_id}; event dedup by signature; passthrough panel.
- [Pre-trade compliance gate](compliance-gate.md) — pure engine + GLOBAL config/audit store + ComplianceBlock wired into paper_trade/rebalance; passthrough panel; audit rows use decision/summary.
- [Multi-strategy capital allocation](multistrat-allocation.md) — firm-level multi_strategy panel: sleeve aggregation, cross-strategy risk from REAL NAV snapshots (held-out if thin), allocation methods; route before optimizer+desk.
- [PIT & survivorship-bias-free data](pit-survivorship-data.md) — honesty contract: historical_closes is real-only (report missing, never impute), fundamentals_as_of or None; builders emit coverage/pit blocks; CoverageBadge panels.
- [Walk-forward research integrity](walk-forward-research-integrity.md) — overfitting guardrails (walk-forward/DSR/PBO/MT-haircut) as SEPARATE walk_forward passthrough panel; route before wants_backtest; honest coverage→inconclusive.
- [In-panel control refine loading](panel-inline-refine-loading.md) — route in-panel control refines through paramRefineMutation + `pending` prop so the global "Processing" overlay never wipes the control rows; disable controls + overlay only the data area.
- [Credit stress monitor (IG vs HY OAS)](credit-stress-monitor.md) — needs OAS time series so added fetch_credit_spread_history (separate from latest-only); route before bond_rv/cds; dual y-axis chart.
- [Multi-symbol walk-forward](walk-forward-multi-symbol.md) — walk_forward_compare fans the overfitting check across a list/sector, aggregates per-name verdicts into a robustness score; inconclusive names excluded not hidden.
- [Cost-aware rebalancing pipeline](cost-aware-rebalancing.md) — one real square-root impact model feeds optimizer kappa + trade list + scheduled rebalance; unsupported orders flagged not faked; paper books start at target (use research stage to see establishing trades).
- [Yield-curve recession-signal overlay](yield-curve-recession-signal.md) — 2s10s/3m10s → plain-language recession read + live inversion duration; inversion key uses hyphen, spread label en-dash; recession field added to YieldCurveData model.
- [Pending panel auto-refresh poll](pending-panel-autorefresh.md) — pending panels self-poll refine({symbol[,range]}) every 5s/60s on a 3rd mutation (no Processing flip); deps are primitives so the timer doesn't restart.
- [Portfolio → strategy desk promotion](portfolio-to-desk-promotion.md) — "paper trade this portfolio" registers latest signal_portfolio book as a paper strategy (carry exclusions); tests must isolate compliance_store + use HISTORICAL stub closes so the trackDays promotion gate blocks fresh books.
- [ETF holdings & reverse exposure](etf-holdings.md) — free feed = TOP holdings only; coverage reported never imputed; reverse lookup limited to top-holdings membership; sector mix live-only.
- [Economic releases + FRED revisions](economic-releases-revisions.md) — economic_releases + series_revisions passthrough panels off FRED/ALFRED; vintage prints (initial vs current); honesty contract (unavailable, no synthetic); verify via running workflow only.
- [Polymarket prediction-market data](polymarket-prediction-markets.md) — 3 free key-less APIs (Gamma/CLOB/data-api); JSON-string-encoded fields; resolve by token-relevance not volume; CLOB needs fidelity per interval.
- [Congressional trades feed](congress-trades-feed.md) — STOCK Act disclosures; honesty contract (show BOTH txn+disclosure dates, ranges not point values, source links); route before trade_flow.
- [Order-book real replay (IEX DEEP)](orderbook-iex-deep-replay.md) — order_book serves REAL venue-only/T+1 depth reconstructed from huge IEX HIST DEEP pcapng captures (hand-rolled streaming parser); on-demand job + synthetic fallback; honesty contract (replayReal/venue/session); thin symbol → no real payload.
- [Strategy Templates Marketplace](strategy-templates-marketplace.md) — alpha-signal presets; preview via build_signal_portfolio, clone via create_strategy (topN<7 → ComplianceBlock), save user templates; lifecycle guard + route before desk.
- [SEC filings browser (EDGAR)](filings-browser-edgar.md) — filings_browser panel; FTS `ticker=` IGNORED (use zero-pad `ciks=`), covers since 2001 ranked by relevance; client-side form-chip filter; honest unavailable/error.
- [EDGAR Form 4/5 XML quirk](edgar-form4-xml-quirk.md) — most insider-filing fields are <value>-wrapped but transactionCode/owner/issuer/relationship are DIRECT text; wrong helper silently yields None (all trades "other", insiders "Unknown").
- [Institutional holdings & 13F flows](institutional-13f.md) — 13F panels: partial-amendment filings must not supersede the full book (pick max-holdings); flows split on share change w/ tradeValue=Δshares×price.
- [Auth / firms / roles foundation](auth-firms-roles.md) — multi-tenant identity (firm signup→admin, durable secure-cookie sessions, protected router); traps: secure cookie needs https TestClient, orval LogoutResponse collision, refresh composite dist for ApiError.
- [Durable, firm-scoped session state](durable-session-state.md) — dashboards/history/DCF/alerts externalized to one `session_state` jsonb table (FOR UPDATE mutate) so the API is stateless/scalable; + env pool sizing, /readyz, rebalance advisory lock, loadtest:api.
- [Load-test latency baseline & dashboard caching](load-test-latency-baseline.md) — /api/dashboard/default was the bottleneck (shared, live-fetch, 240KB); cache+single-flight (26s→1s); per-endpoint budgets + opt-in LOAD_GATE_LATENCY; agent-bash can't run worker-skipped (MAX_PATH).
- [Multi-tenant data isolation](multi-tenant-isolation.md) — per-firm scoping of every store via a contextvar set in ASYNC require_identity (anyio copies it into sync threadpool); worker wraps cross-firm loops in firm_context; order-book replays shared-by-design.
- [Role-based permissions enforcement](role-permissions.md) — single authoritative matrix in app/permissions.py; server-enforced via require_permission dep (403, fails closed); AuthIdentity.permissions drives UI can(); smoke script must sign up first.
- [Firm-wide audit trail](firm-audit-trail.md) — compliance_audit generalized to a unified user-attributed append-only log; category column, actor auto from require_identity, no HTTP clear path, admin-only GET /api/audit.
- [Firm Admin Console](firm-admin-console.md) — admin-only /admin/* (users/invites/limits/firm/billing); deactivation enforced at BOTH require_identity AND login (403); last-admin/self guards; cross-firm 404; one-time invite tokens; ?invite= AuthScreen split.



====================================================================================================
FILE: .agents/memory/ai-client-timeouts.md
====================================================================================================

---
name: AI client timeouts vs preview proxy
description: Why the api-server OpenAI client needs a bounded timeout + no retries, and how callers must fall back.
---

The Replit preview proxy returns a 502 if an upstream request hangs past its ~60s
window. The api-server OpenAI client (pointed at the AI Integrations proxy / modelfarm)
must therefore carry a client-side timeout well under that ceiling, otherwise a slow LLM
call silently hangs and the browser sees a 502 with no log line on our side.

**Rule:** any AI call that sits on a request path the user is waiting on must be bounded
AND its caller must treat a timeout exactly like any other failure (fall back to a
heuristic / non-AI path). A timeout that only raises but has no fallback still leaves the
user with an empty result.

**Why:** the orchestrate path makes a tool-enabled call requesting many tokens; with no
timeout it hangs. The existing fallbacks (`_orchestrate_llm`, `_build_narration`) already
catch `Exception`, so a bounded timeout is enough to make them kick in.

**How to apply:**
- Set `timeout` + `max_retries=0` on the shared `OpenAI` client in `app/ai.py`
  (`get_client`). `max_retries` matters — the SDK default of 2 multiplies the wait and can
  blow past the proxy window even with a per-attempt timeout.
- Audio/narration (`speak`) can use a longer per-request budget via
  `client.with_options(timeout=...)` since it is heavier, but still bounded.
- Keep all timeouts comfortably under ~60s (currently chat 30s, audio 45s,
  feature-build 55s).
- **Feature-build is a special case:** its single planning call authors TWO full
  source files and routinely takes ~45-50s, so the default 30s `CHAT_TIMEOUT`
  ALWAYS timed it out. It now passes `timeout=ai.FEATURE_BUILD_TIMEOUT` (55s) to
  `ai.chat` (which gained a per-request `timeout` param). Unlike orchestrate it has
  NO fallback, so the budget must actually fit the work — and the stream emits SSE
  heartbeats while the call runs (see self-building-features.md) so the long call
  doesn't trip the proxy.



====================================================================================================
FILE: .agents/memory/analyst-compare.md
====================================================================================================

---
name: Multi-ticker analyst comparison
description: How the analyst_compare panel composes per-ticker analyst reports, and the heuristic-routing keyword traps to avoid.
---

# Multi-ticker analyst comparison (analyst_compare)

A quick side-by-side of the analyst stance across several tickers. It does NOT
re-implement analysis — it fans out to `build_analyst_report({"symbol": s})` per
name and distills each into a compact card (stance, conviction, headline, call,
top figures).

**Per-ticker isolation is the core contract.** Each symbol is built in a
ThreadPoolExecutor and wrapped so one failing/timing-out name never sinks the
panel; failures go into a `failed` list and are simply omitted from the cards.
The builder raises only when EVERY ticker fails. Concurrency matters: N
sequential analyst reports (each an AI call) would blow past the ~60s preview
proxy window — fan them out, don't loop.

**Why concurrent, not sequential:** see `ai-client-timeouts.md`. Each
build_analyst_report makes its own bounded AI call; running 3+ in series stacks
the latency.

## Heuristic-routing keyword trap
`_orchestrate_heuristic` in agent.py decides analyst_compare via "2+ symbols +
analyst intent". Be careful with substring matches when picking trigger words:
- `"view" in "overview"` is True, `"take"` is overly broad. Using bare
  "view"/"take" wrongly routes "give me an overview of NVDA and AMD" to the
  analyst comparison. Use explicit phrases ("analyst", "stance", "conviction",
  "bull/bear", "better buy") and reuse the existing `wants_analyst_report` flag.
- Route analyst_compare BEFORE the single analyst_report block, since both can
  match a 2-symbol analyst query.



====================================================================================================
FILE: .agents/memory/analyst-ratings-consensus.md
====================================================================================================

---
name: Real analyst ratings & consensus
description: Live-first analyst consensus/price-target source + analyst_ratings table; honesty + grounding contract.
---

Real Street consensus (strongBuy/buy/hold/sell/strongSell counts, consensus label, # analysts,
mean/high/low/median target + implied upside) and recent upgrades/downgrades come from yfinance
`Ticker.info` + recommendation history, normalized in `sources/fundamentals.fetch_analyst_consensus`.

- **Honesty:** uncovered names (ETFs like SPY, thin/foreign tickers) return `covered=False` with
  `None` targets — never invent ratings or targets. `_norm_action` maps raw grades to a small
  action vocabulary (initiated/upgraded/downgraded/maintained/reiterated).
- **Persistence:** worker slow-fundamentals loop ingests into the `analyst_ratings` table (one row
  per symbol, whole snapshot replaced each refresh incl. `covered`; `changes` stored as JSONB via
  `%s::jsonb` + `json.dumps`). repo reads camelCase with `_asOf`/`_source`.
- **Serve contract:** `skills._fetch_consensus` is live-first → persisted-snapshot fallback →
  `(None,...)`. Builder raises (→ harness error panel) only when BOTH live and snapshot are empty.
- **Grounding:** `build_analyst_report`/compare read the persisted snapshot (no network on that
  path) and inject Consensus/Target/Implied figures + `analystConsensus` ctx so the AI write-up
  uses real targets instead of inventing them.

**Why boot looks broken:** the shared yfinance circuit breaker (`sources/_resilient`) opens under
the boot ingest's heavy `.info` traffic, so live consensus is short-circuited AND the
`analyst_ratings` table is still empty (fundamentals loop hasn't won a throttle-free window) →
error panel. This is expected; once the table is populated the snapshot fallback serves it
permanently and the live path works whenever yfinance isn't throttled.

**How to verify in-repo despite throttle:** populate a row via agent bash
(`env -i HOME=$HOME DATABASE_URL="$DATABASE_URL" .../python3.11` → `fetch_analyst_consensus` +
`worker._upsert_analyst_ratings`), then hit `POST localhost:$PORT/api/orchestrate`. `env -i`
strips `DATABASE_URL`, so pass it explicitly or `db.connection()` raises "database unavailable".



====================================================================================================
FILE: .agents/memory/attribution-benchmark.md
====================================================================================================

---
name: Performance/attribution benchmark must be REAL
description: Attribution panels (P&L, Brinson, tear sheet) must benchmark against real traded instruments over the full requested window — never a synthetic universe.
---

# Benchmarks must be real traded instruments

Performance & factor attribution (P&L vs benchmark, Brinson, tear sheet) must
compare the book against a **real, traded** instrument — not a synthetic
"cap-weighted universe" series computed in-house.

**Why:** A prior implementation benchmarked against a home-grown synthetic
"Cap-Weighted Universe" index; code review REJECTED it. A real fund/ETF is the
only honest, defensible benchmark for performance attribution, and users expect
to compare against something they can actually buy.

**How to apply:**
- Headline benchmark is **user-selectable** (parsed from the query) but always
  real: either a single real ETF (broad like SPY/QQQ/IWM or a sector/thematic
  ETF like XLK/SMH/XBI) OR a custom basket of real constituent tickers. Default
  to the broad-market one. A picked ETF ticker is honored **only if a real price
  series resolves for it**, else fall back to the default — never benchmark
  against an unvalidated symbol. A custom basket is acceptable (user-chosen +
  real prices) because it is built from real constituent returns/caps, not a
  home-grown synthetic universe; basket constituents the risk model can't cover
  are dropped and reported.
- Brinson must HONOR the selected ETF, not always a proxy default. A chosen ETF
  drives the decomposition via its **own REAL GICS sector weights**: yfinance
  (`yf.Ticker(etf).funds_data.sector_weightings`, TTL-cached ~1d) returns real
  GICS weights for SPY/QQQ/XLK/XLE/etc. Re-bucket the book into that GICS space
  (`_GRANULAR_TO_GICS`), multiply the ETF's real weights by **real sector-ETF
  returns** (`_GICS_ETF`, one real ETF per GICS sector). This is the
  reviewer-required deterministic real mapping. Proof it's honored: SPY vs QQQ
  yield very different benchmark sector weights (e.g. tech ~59% vs ~84%,
  financials ~17% vs ~0.3%).
  **Why two code-review rejections:** (1) Brinson defaulting to a generic proxy
  even when the user picked an ETF — wrong, the selection must change the math;
  (2) dropped basket constituents (incl. ones filtered before the risk model)
  must ALL be reported, so `_resolve_bench_constituents` returns `(kept, dropped)`
  and the builder echoes every dropped ticker.
- Fallback only when the ETF's real sector composition can't be sourced: a
  diversified sector-ETF proxy (one real ETF per sector, universe cap-weighted),
  and the benchmark name must SAY SO ("… sector weights unavailable") — never
  imply the chosen ETF drove it.
- Sectors with no clean real sector ETF are **excluded and reported**, not
  faked. For a custom basket (takes precedence over `benchmark`), the Brinson
  side uses the **basket's own** real sector weights/returns; book sectors the
  basket doesn't span are excluded+reported.
- `_build_benchmark(params, model, rets, dates, rng, idx, w, wp_raw, rp_num, …)`
  may re-bucket the book into the benchmark's sector space, so it RETURNS the
  matching `wp_raw`/`rp_num`; `_compute_attribution` must use the returned
  portfolio side (not its own pre-bucketed one) or the two sides won't align.
- The orchestrate LLM path is primary (heuristic is only a fallback when the LLM
  returns no panels), so put benchmark/basket parsing in BOTH: tool schemas
  (free-text `benchmark` + `benchmark_constituents`/`benchmark_weights`/
  `benchmark_name`) for the LLM, and `_extract_benchmark`/
  `_extract_benchmark_constituents` for the deterministic fallback. The LLM may
  occasionally pick unrelated panels for a basket query — that's tool-selection
  noise, not a data-layer bug; the builders + heuristic handle baskets reliably.
- Source the benchmark through the same real price path as everything else (DB
  live first, real fetch fallback), and surface coverage in the payload
  (ticker, source, missing trading days) so gaps are visible to the user.
- **Size the history fetch to the requested range.** A fixed short fetch (e.g.
  6mo) silently truncates 1Y/YTD windows; the missing stretch then aligns flat
  and biases active return, tracking error, IR, beta/alpha and drawdown. Always
  fetch enough to cover the window plus the lookback for the first return.
- Date-align benchmark returns to the book's trading days; carry the
  benchmark's own missing days flat and count them rather than dropping dates.
- Any external fetch/DB call on this critical path must degrade cleanly on
  failure (a real module logger must exist — an undefined `log` in the `except`
  turns a transient network error into a panel-killing `NameError`).



====================================================================================================
FILE: .agents/memory/attribution-multiperiod-linking.md
====================================================================================================

---
name: Multi-period Brinson linking (Carino)
description: Why/where attribution links sub-period BHB effects geometrically over long windows instead of single-period BHB on compounded sector returns.
---

# Brinson attribution links geometrically over long windows

Single-period Brinson-Hood-Beebower computed once over a whole window from
*compounded* sector returns accumulates a linking/residual bias on 6M/1Y/YTD
horizons — the allocation/selection/interaction effects drift away from the true
geometric active return.

The engine has two paths:
- `brinson(...)` — single-period BHB on compounded sector returns (kept for the
  degenerate 1-sub-period case and as the unit-test identity).
- `brinson_linked(...)` — takes **per-sub-period** weight/return series per
  sector, computes single-period effects each sub-period, and scales them by the
  Carino factor `k_t / k` before summing. `_carino_coeff(Rp,Rb) = (ln(1+Rp) -
  ln(1+Rb))/(Rp-Rb)` with limit `1/(1+Rp)` at `Rp==Rb`.

**Why Carino:** by construction the linked effects sum *exactly* to the
geometrically compounded active return `prod(1+Rp_t)-1 - (prod(1+Rb_t)-1)`, so
the attribution stays additive and accurate over long horizons.

**How to apply:** `_compute_attribution` builds the per-DAY portfolio sector
return (within-sector book-weighted daily return) and the per-day benchmark
sector ETF return, then calls `brinson_linked` whenever the window has >1 day
(`k > 1`); otherwise the single-period `brinson`. Weights are constant and
broadcast (pass a scalar per sector; `col()` broadcasts to length T).
`brinson_linked` adds `linked: True` and `subPeriods` to its output — callers
that copy explicit fields drop them; `build_tear_sheet`/`attribution_overview`
pass the whole brinson dict through, which is fine (panel models tolerate them).



====================================================================================================
FILE: .agents/memory/auth-firms-roles.md
====================================================================================================

---
name: Auth / firms / roles foundation
description: Identity layer for the terminal (firm signup, login, durable sessions, protected API) and its non-obvious traps.
---

# Auth / firms / roles foundation

Multi-tenant identity: firms (tenants) → users (email/password, one firm each) → roles (admin/trader/analyst/read-only). First user of a firm signup is the firm admin.

## Architecture
- `app/auth.py`: stdlib PBKDF2-HMAC-SHA256. `hash_password(pw) -> (hash_hex, salt_hex)`; `verify_password(pw, hash_hex, salt_hex)`; `new_session_token()` + `hash_token()` (store the HASH, never the raw token); `COOKIE_NAME="at_session"`, 30-day TTL.
- `app/auth_store.py`: firms/users/auth_sessions, DB-first `CREATE TABLE IF NOT EXISTS` + in-memory fallback (same runtime-DDL pattern as strategy desk — NOT drizzle push). Drizzle mirror in `lib/db/src/schema/auth.ts` is for convention only.
- `main.py`: `require_identity` resolves the session from the httpOnly `at_session` cookie OR an `Authorization: Bearer <token>` header (cookie wins; same hash+lookup) → 401 if neither valid. Two routers: `public = APIRouter(prefix="/api")` (healthz + /auth/signup,login,logout,user) vs `api = APIRouter(prefix="/api", dependencies=[Depends(require_identity)])` for everything else. The Bearer path exists so non-browser/test clients with no cookie jar can authenticate — the generated client attaches it via `setAuthTokenGetter`.

## Traps (cost real time)
- **Secure cookie + http TestClient = silent 401s.** The session cookie is `secure=True` (correct for the https Replit proxy/preview). `TestClient(app)` uses `http://testserver`, so the cookie sits in the jar but is never replayed → every authed probe spuriously 401s. Fix: `TestClient(app, base_url="https://testserver")`. Same fix was needed in `test_smoke.py` once orchestrate became protected.
- **Protecting orchestrate breaks the existing smoke test.** Any pre-existing test hitting a now-protected route must sign up first to get a session cookie.
- **orval LogoutResponse collision.** Orval auto-generates a `LogoutResponse` zod validator for the `logout` op, so the response *schema* had to be named `LogoutResult` in openapi.yaml/models.py to avoid a clash.
- **Stale composite `dist/*.d.ts` for api-client-react.** `ApiError` is exported from `src/index.ts`, but terminal tsc resolves the composite project's emitted `dist/index.d.ts`. After adding a new re-export, run `pnpm run typecheck:libs` (`tsc --build`) to refresh dist or tsc reports "no exported member 'ApiError'". Runtime is unaffected (vite uses the exports map → src).

**Why:** these are environment/tooling quirks not visible in the code; each produced a confusing failure (auth works in browser but tests 401; type error on a symbol that is clearly exported).



====================================================================================================
FILE: .agents/memory/backtest-engine.md
====================================================================================================

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

## In-panel tunable strategy params
Backtest exposes per-strategy knobs (lookback/threshold/fast/slow) editable in the
panel and re-run via the structured-refine path.
**Two invariants that keep this safe:**
- Effective params = strategy defaults (canonical, mirror the `signal_*` inline
  fallbacks) overridden only by relevant provided keys. **Why:** so doing nothing
  reproduces original behavior, and a stale key (e.g. a leftover `threshold` after
  switching to momentum) can never alter a run — it's not in that strategy's
  defaults, so it's ignored.
- A strategy switch must NOT inherit the previous strategy's tuning: refine carries
  current params forward only when the strategy is unchanged, otherwise drops them
  so the new strategy starts from fresh defaults.
**How to apply:** a tunable knob must be wired in lockstep across four places
(strategy defaults, build_backtest's override step, the refine passthrough, the
panel control) or the value silently fails to round-trip.

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



====================================================================================================
FILE: .agents/memory/boot-smoke-check.md
====================================================================================================

---
name: API Server boot smoke check
description: The boot smoke check (run command + why it is NOT a registered validation in this multi-artifact repo), the yfinance MAX_PATH agent-bash quirk, and the TERMINAL_SKIP_WORKER hook.
---

`scripts/smoke-api.sh` boots the API Server against the live `.pythonlibs` env, waits
for `/api/healthz`, and asserts `POST /api/orchestrate` returns 200. It exists to catch
the class of "server can't boot" failures (missing/declared-but-uninstalled Python deps
→ ModuleNotFoundError, import errors, broken startup) before they ship. It is exposed as
the root pnpm script `pnpm smoke:api`.

## Why it is a pnpm script, NOT a registered validation (platform limitation)
**Do not register this via the validation skill (`setValidationCommand`) in this repo.**
`setValidationCommand` ALWAYS injects an explicit `[[workflows.workflow]] name="Project"`
block into `.replit` (mode=parallel → `workflow.run <validation>`) plus `runButton="Project"`.
In a multi-artifact repo the `Project` run button is normally *synthesized* from each
`artifact.toml` to run all artifacts; the injected explicit `Project` block OVERRIDES that
synthesis, so the Run button then runs only the validation and the app no longer starts.
**No tool can remove ONLY that block:** `.replit` edits are blocked (edit tool AND bash),
`removeWorkflow("Project")` → "not found" (Project is not a tracked workflow),
`verifyAndReplaceArtifactToml` does not touch `[workflows]`, `configureWorkflow` only makes
single-command workflows (can't express a parallel run-all-artifacts Project), there is no
run-button tool, and `clearValidationCommand` wipes the whole `[workflows]` stanza.
**How to apply:** keep boot/smoke checks as runnable scripts (`pnpm smoke:api`) here. If you
must register a real validation, expect the Run button to break and budget for escalating
the `setValidationCommand` multi-artifact bug — there is currently no clean in-repo fix.

## Environment quirk: yfinance subprocess spawn fails in the agent's bash tool
**Symptom:** running anything that triggers `yf.Ticker(sym).info` (worker fundamentals
loop, or orchestrate's on-demand data refresh) inside the **agent's bash/code_execution
tool** dies with:
```
run process: run_parent
  ... get_target_path ... path exceeds MAX_PATH
```
**Why:** the agent's bash sandbox intercepts process exec via a run-wrapper whose
target-path computation overflows; yfinance spawns a child process that trips it.
The real **workflow** and a normal repl shell run like normal app processes and do NOT
hit this — orchestrate returns 200 there (verified via the workflow on localhost:8080).
**How to apply:** you cannot fully exercise orchestrate's data path from the agent's
own bash tool — verify it via the running workflow (curl localhost:$PORT). `pnpm smoke:api`
works for the user in a normal repl shell but may trip MAX_PATH if you run it directly in
the agent's bash tool.

## TERMINAL_SKIP_WORKER hook
`worker.start()` early-returns when `TERMINAL_SKIP_WORKER=1`. The boot smoke check sets
this so the server boots fast without launching the continuous live-ingestion loops
(hundreds of network calls). Default/unset = normal behavior (worker runs). This is a
test-only hook; do not rely on it in production paths.



====================================================================================================
FILE: .agents/memory/combined-alpha.md
====================================================================================================

---
name: Combined alpha (signal blend)
description: Durable constraints for blending multiple cross-sectional signals into one composite alpha.
---

# Combined alpha — blend N signals into one composite

`combine_signals` (engine/signals.py) blends several cross-sectional signals into
ONE composite alpha, scored with the SAME scorecard path (`_score_panel`) as a
single signal so blend-vs-component metrics are directly comparable.

## Durable constraints
- **Strict intersection is the contract.** The composite at a name/date is formed
  only when EVERY selected component is finite there. A name missing ANY selected
  component's input (e.g. a fundamental for value/quality) is excluded and reported
  with the missing component named — never imputed. Relaxing this to "any component
  present" silently changes composite membership and all downstream scorecard
  metrics; that was rejected in review.
  **Why:** task requires real-data-only; partial-input names corrupt the blend.
- **Per-component ctx, not one ctx.** Build a `ctx_by_signal[signal][symbol]` dict
  (via `_signal_ctx` per component) so value and quality — which share a SIGNALS fn
  but need distinct fundamentals — each get their own cross-sectional value.
- **Component scoring uses each component's own (broader) universe**; only the
  composite is restricted to the strict intersection. IC-weights are derived from
  those standalone component ICs (floored at 0; equal-weight fallback if none +).
- **Method is reported back** (equal_weight / ic_weighted / inverse_correlation).
  `normalize_combine_method` is substring-matched — bare "ic" does NOT map to
  ic_weighted (needs "ic_weight"/"ic weighted"); "inverse"/"risk_weight"/"decorrel"/
  "diversif" → inverse_correlation.

## Wiring (see passthrough-panels.md)
Passthrough panel type `combined_alpha` (plain str, no openapi/models.py enum;
local TS interface; stale-PanelType tsc errors don't gate the vite build). Routed
in agent.py BEFORE scorecard/research but AFTER portfolio-build (so "blend … into a
portfolio" still builds a book). Panel `included` is a count (composite included),
not a list.



====================================================================================================
FILE: .agents/memory/company-analytics-compare.md
====================================================================================================

---
name: Company analytics head-to-head compare
description: How the two-company compare view is wired (panel type, builder, ordering, leader scoreboard).
---

# Company analytics compare (head-to-head)

- Panel type `company_analytics_compare` (passthrough — no openapi codegen). Builder
  `build_company_analytics_compare` in skills.py takes `symbols: [A, B]`; reuses
  `_company_price_drivers` (AI+fallback, refactored out of `build_company_analytics`)
  and `_company_side` per company.
- Comparison "scoreboard" picks a leader per metric: Revenue Growth, Operating Margin
  (=netMargin), P/E (lower-is-better), Market Cap, YTD, 1Y. Each row carries
  `higherIsBetter` + `leader` (sym | "tie" | None when a side is missing).
- Routing: heuristic `wants_compare` needs a compare keyword (vs/versus/compare/
  head-to-head/side-by-side/which is better) AND >=2 symbols; `_order_symbols_by_query`
  orders the two by appearance in the query (left = first named), since
  `_extract_symbols` returns repo order not query order. LLM path has its own tool.
- Frontend `CompanyAnalyticsComparePanel.tsx`: Trophy marks the leader; two columns
  (grid md:grid-cols-2) each with Price Drivers + Catalyst Watch. Routed at width 12.



====================================================================================================
FILE: .agents/memory/company-profiles.md
====================================================================================================

---
name: Company profiles (sub-industry + logos)
description: How richer company profiles (human-readable sub-industry + logo) are assembled across the data catalog and panels.
---

Every company record carries `subIndustry` (human label, distinct from internal `sector` id) and `logoUrl`.

- **Two catalog builders, one stamper.** `data.py` builds COMPANIES via `_c()` (113 curated core, live-tracked) AND `_q()`/`_load()` (bulk breadth, mock-on-demand). BOTH must include `subIndustry`/`logoUrl` default keys. `_apply_company_profiles()` MUST run AFTER all `_load()` calls (it's at module bottom, not after the `_c` block) or bulk names (e.g. AAPL — which is bulk, not core) never get stamped.
  **Why:** original bug — apply ran at line ~848 before bulk loads at ~1318, so only the 113 curated got fields.
- `_COMPANY_PROFILES` is symbol→(sub_industry, domain); covers all 113 core + ~45 prominent bulk mega-caps. Logos = Google s2 favicons (`logo_url(domain)`). Names without a curated entry fall back to the SECTORS group name for subIndustry and a monogram on the frontend for the logo.
- **Live refresh precedence:** `repo._company_from_row` prefers Yahoo's `row.industry` over the curated label, and `logo_url(row.website)` over the curated logo. So a live core symbol can show Yahoo's (sometimes broader) industry instead of the finer curated label — expected.
- Frontend: `CompanyLogo.tsx` (img + monogram fallback on error/missing). Used in ScreenerPanel, CompanyAnalyticsPanel (header + peers). ScreenerRow/HeatmapCell are openapi-typed (need codegen); CompanyAnalyticsData is an inline interface (passthrough dict, edit directly).



====================================================================================================
FILE: .agents/memory/compliance-gate.md
====================================================================================================

---
name: Pre-trade compliance gate
description: How the pre-trade risk/compliance gate is layered and wired into the trade-apply path.
---

# Pre-trade compliance gate

Three layers, mirroring the other quant pillars:
- `app/engine/compliance.py` — pure, IO-free. `book_metrics`, `evaluate_limits`,
  `evaluate_lists`, `evaluate_gate`. Limits: maxPositionPct (per-name abs),
  maxNetPct (signed sum), maxLeverage (gross multiple), maxConcentrationPct (top-5).
  WARN_BAND=0.9 → warn; >1.0 → breach. Restricted = hard block, watch = warn.
  Weights are signed NAV fractions.
- `app/compliance_store.py` — GLOBAL config (single 'global' row) + audit trail.
  DB-first w/ in-mem fallback, idempotent CREATE TABLE. Config is firm-wide, NOT
  session-scoped (unlike alerts). Audit rows expose `decision` ("allowed"/"warn"/
  "blocked") + `summary`, NOT ok/blocked/reason.
- `app/strategy.py` — `ComplianceBlock` exc, `precheck(view, weights, action,
  audit, raise_on_block)`, `check_strategy` (audit=False read-only). Gate enforced
  in paper_trade (raises) and rebalance (returns info blocked).

**Why:** consistency with the existing engine/data/skill three-layer convention so
the gate is testable in isolation and the store survives restarts.

**How to apply:**
- Panel is a PASSTHROUGH type (`compliance`) — `_reg`'d in skills.py, NOT in
  harness.DATA_MODELS. `build_compliance({"strategy": name})` runs a read-only
  check; empty params just returns config+lists+audit.
- REST under `/api/compliance`: GET, POST restricted/watch/limits/kill-switch/check,
  DELETE audit + restricted/{sym} + watch/{sym}. Static routes declared BEFORE the
  parametrized `{symbol}` DELETEs.
- Frontend CompliancePanel.tsx manages its own state, raw-fetches `/api/compliance`
  (like DCFPanel), applies each mutation's returned payload. Audit rendering keys
  off `decision`/`summary`.
- Agent routing: `add_compliance` tool + `wants_compliance` heuristic ("is this
  trade allowed", "restricted/watch list", "kill switch", "halt trading", "compliance
  audit"); dispatch placed before wants_alerts (no real overlap, just ordering safety).



====================================================================================================
FILE: .agents/memory/congress-trades-feed.md
====================================================================================================

---
name: Congressional trades feed
description: Durable decisions + honesty contract for the STOCK Act congressional-trading feed/panel.
---

# Congressional trades feed (congress_trades panel)

Real U.S. House + Senate disclosed securities trades (STOCK Act) as a feed + per-ticker panel.

**Data choice:** the underlying filings are public but awkward (House PTR PDFs, Senate eFD
behind a session form), so we read the free, key-less Quiver Quantitative aggregation of them
rather than scraping the primary sources. No API key required.
**Why:** key-less + already-parsed-to-JSON was the only zero-credential path to real data here.

**Honesty contract (the whole point of this feature):**
- Reporting lag is real (up to ~45 days under the STOCK Act). Keep transaction date AND
  disclosure date as distinct fields and render BOTH per row (not just a derived lag) — a
  code review rejected showing lag alone. A frontend test guards this.
- Amounts are disclosed only as ranges — never synthesize a point value.
- Every trade links back to its public disclosure (per-member page, not per-filing — the feed
  has no per-transaction link; document that so "source link" stays honest). The mock set must
  populate this too, or the "marked live with source links" requirement silently degrades.
- Mark live vs sample provenance.

**Routing:** the congress intent must be matched BEFORE the broader trade-flow/"activity" intent,
or generic-activity routing swallows it.

**Persistence:** stored in its own table created via raw DDL and queried with raw SQL (same
pattern as macro_prices), NOT drizzle — keeps a hand-written passthrough panel out of codegen.
Background-ingested on a multi-hour loop with a bounded best-effort refresh at query time so the
first request is current.



====================================================================================================
FILE: .agents/memory/console-answer-streaming.md
====================================================================================================

---
name: Console answer streaming (word-by-word)
description: How the Console streams conversational question answers via SSE, and the build-path contract that stays non-streaming.
---

The Console streams a *question* answer token-by-token; a *build* request does not
(it returns panels, not prose).

## Backend contract
- `ai.chat_stream(messages)` yields content deltas (stream=True) on the same
  bounded-timeout/no-retry client; raises if unavailable.
- `agent.orchestrate_stream(query, session_id, voice)` is the streaming twin of
  `orchestrate`. It yields event dicts: `{"type":"delta","text":...}` (question
  answer fragments) and exactly one `{"type":"done","result":{...}}` carrying the
  full DashboardSpec-shaped dict. Lifecycle + build emit only the `done` event.
- Both share `_orchestrate_prelude` (sid/base resolution), `_question_result`
  (persist + shape), `_orchestrate_build`. Keep `orchestrate` and
  `orchestrate_stream` in lockstep through these helpers — don't duplicate logic.
- `_answer_messages` builds the prompt for BOTH `_answer_question_llm` (blocking)
  and `_answer_question_stream`. Edit the prompt in one place.
- Endpoint: `POST /api/orchestrate/stream` (main.py) → StreamingResponse,
  text/event-stream, mirrors `/feature-request` SSE framing (`data: {json}\n\n`).
- **Fallback rule:** if streaming yields no tokens, `orchestrate_stream` calls the
  blocking `_answer_question` and emits it as one delta — never leave an empty answer.

## Frontend contract
- Only the plain Console command path uses streaming (`Terminal.tsx` `streamCommand`):
  fetch + ReadableStream reader, split on `\n\n`, parse `data:` lines. Voice and
  nav-tour paths stay on the blocking `useOrchestrate` mutation.
- `streamingAnswer` (live accumulated text) drives a growing assistant bubble in
  `ChatPanel.tsx`; the "Processing command" pulse hides once `streamingAnswer` is set.
  On done: adopt result, `pushReply`, clear `streamingAnswer`.
- Any stream error falls back to `orchestrate.mutateAsync` so the user still gets a full answer.
- The generated `@workspace/api-client-react` has no streaming hook — this path uses
  raw `fetch` to a relative `/api/...` URL (proxy-routed), like FeatureRequestModal.



====================================================================================================
FILE: .agents/memory/console-conversation-persistence.md
====================================================================================================

---
name: Console conversation persistence
description: How the Terminal Console transcript + session id survive a page reload, and how reset clears them.
---

The Console (chat) transcript and its backend session id are persisted in
`localStorage` by `artifacts/terminal/src/hooks/useConsoleConversation.ts`
(keys `agentic-terminal.console.messages.v1` / `...sessionId.v1`). `Terminal.tsx`
owns the conversation via this hook; `ChatPanel` is now a **controlled** component
(receives `messages`, no internal transcript, no `reply`/nonce machinery).

**Why session id is persisted, not the dashboard panels:** restoring the panels
visually is a separate concern (there's a dedicated "save/restore dashboard
layouts" task). We only persist the transcript + session id. On reload the
dashboard area shows the ambient dot-wave until the next command — but because the
same session id is reused, the backend's in-memory `_sessions`/`_session_history`
for that id are still intact, so a follow-up question reconnects with full context
and the panels reappear in the returned spec.

**Reset detection (frontend):** the backend mints a *new* session id on reset (see
terminal-orchestration). So `Terminal` compares the sent session id to
`result.sessionId`; if they differ, it treats it as a reset and calls
`convo.clear()` (wipes transcript + persisted session). This covers typed resets
("start fresh", "reset", etc.) and voice-triggered resets. Voice turns otherwise
stay OUT of the Console transcript but still sync the session id.

**Limitation:** session context survives a *browser refresh* (server stays up) but
NOT an api-server restart — `_sessions`/`_session_history` are in-memory only. The
transcript itself always survives (localStorage); only backend context is lost on a
server restart, after which a follow-up rebuilds fresh.



====================================================================================================
FILE: .agents/memory/cost-aware-rebalancing.md
====================================================================================================

---
name: Cost-aware construction & rebalancing pipeline
description: How trade-cost penalties, the share-level trade list, scheduled rebalance, and the rebalance_plan panel fit together; the real-cost-only contract.
---

# Cost-aware construction & automated rebalancing

The optimizer and the paper-book rebalance both penalize trading by the SAME real
square-root market-impact model used by TCA. No fabricated costs anywhere.

- **Engine** (`app/engine/execution.py::estimate_trade_costs`): the reusable
  diff→cost step. Per order it attaches `impactBps`/`costUsd` only when real ADV +
  daily vol exist; otherwise `costSupported: False` with a reason — never a faked
  cost. The aggregate's `grossNotional` and `totalCostUsd` roll up ONLY the
  supported orders (unsupported notional is excluded), so don't expect gross to
  equal the full order book when some names lack ADV/vol.
- **Optimizer** (`app/engine/optimize.py`): `_solve_utility` / `mean_variance`
  take a per-name `kappa` (square-root impact curvature) folded into a 3/2-power
  penalty `sum_i kappa_i·|w_i - current_i|^1.5` valued by `impact_cost(...)`. The
  cost term reduces churn vs the current book — it never increases it.
- **Strategy** (`app/strategy.py`): `compute_trade_list(view)` is READ-ONLY
  (returns orders + expected modeled cost + navAfter, no mutation). `rebalance`
  applies trades and debits the real modeled cost from cash. Scheduling lives in
  `set_schedule`/`is_due`/`run_scheduled_rebalances` (weekends skipped; due needs
  an ACTIVE stage + cadence elapsed since lastRebalance|inception).
- **Skill** (`app/skills.py::build_rebalance_plan`): preview (no apply) vs apply;
  returns `expected` (modeled) + `realized` (intraday sim, unsupported flagged)
  blocks, order rows, updated weights, status ok|empty. Passthrough panel
  `rebalance_plan` (no DATA_MODEL).
- **Routing** (`app/agent.py`): "rebalance my strategy" → apply; "what trades to
  get to target" / "preview/plan" → preview (no apply). `to (the) target` regex is
  deliberately narrowed so it does NOT hijack optimizer "target vol" requests.

**Why:** the whole point of this pillar is that cost is honest — a future change
that hardcodes a cost, or that lets the optimizer trade as if free, breaks the
contract. Keep cost flowing from the one impact model and keep unsupported orders
flagged, not faked.

## Gotcha: paper books are already at target
`create_strategy(paper=True)` calls `paper_trade`, which establishes the book AT
the target weights from real prices. So a fresh paper strategy shows NO trades on
a rebalance preview — that's correct, not a bug. To exercise establishing trades
in a test, use a research-stage strategy (`paper=False`, positions `None`) so the
trade list is the full establishing set.



====================================================================================================
FILE: .agents/memory/credit-stress-monitor.md
====================================================================================================

---
name: Credit stress monitor panel (IG vs HY OAS)
description: How the credit_stress passthrough panel sources IG/HY OAS history and why its routing sits before bond_rv/cds.
---

The `credit_stress` panel charts investment-grade vs high-yield ICE BofA OAS over
~6 months with a risk-on/off read and a "widening" flag per bucket.

**Data:** reuses the FRED ICE BofA OAS feed, but needs a *time series*, not the
single-latest values `fetch_credit_spreads` returns. So `rates.py` gained a
SEPARATE `fetch_credit_spread_history(window_days)` (+ generic `_fetch_fred_series`
with `observation_start`/asc). Same key requirement as the rest of credit: live
only with `FRED_API_KEY`, else clean mock.
**Mock fallback:** `_mock_credit_history` synthesizes a deterministic wave+drift
path anchored to curated current levels and is honestly labelled `source="mock"`.

**Routing trap (cost real attention):** the heuristic keyword `wants_credit_stress`
MUST be checked BEFORE `wants_cds` and `wants_bond_rv` in `_orchestrate_heuristic` —
"credit risk" belongs to CDS and "credit spread" (singular) to bond RV, so a
credit-conditions query would otherwise be hijacked. credit_stress keys off
"credit stress/conditions/market", "ig vs hy", "high yield", "investment grade",
"spread(s) widening", etc. It's in `_SUBJECT_AGNOSTIC_TYPES` (market-wide, no symbol).

**Frontend:** passthrough panel (no codegen) — dual y-axis line chart, IG on left
axis / HY on right axis (HY is ~3x IG, so a shared axis flattens IG). Mirrors the
SovereignComparePanel structure.



====================================================================================================
FILE: .agents/memory/data-wall-removal.md
====================================================================================================

---
name: Data wall removal (any-ticker + live macro)
description: How the terminal serves arbitrary Yahoo tickers, the pending envelope contract, and the separate live macro feed.
---

# Removing data walls (arbitrary tickers, live macro, uncapped news)

## Any valid Yahoo ticker works
- Price/fundamentals/order-book/trade-flow builders no longer `raise ValueError("Unknown symbol")`. They call `repo.note_symbol(sym)` (on-demand request) + `repo.get_company(sym)`; when the company isn't ingested yet they return a **pending envelope** instead of erroring.
- Pending envelope shape: `{symbol, name, ...zeroed required floats..., pending: True, asOf: None, source: "pending"}`. The required float fields MUST be present (0.0) because the harness validates the builder dict against the pydantic model.
- **Why zeros:** harness pops `asOf`/`source` onto the panel envelope and validates `data` against the model; missing required floats would raise.
- Builders that previously used `data.get_company` (mock-only) were switched to `repo.get_company` so they see live-ingested names too (order_book, trade_flow).

## Pending fills in on the NEXT query, not live
- Panels are set ONCE per orchestrate response; they do not poll. A brand-new ticker shows the pending state, then the worker on-demand loop (~15s) ingests it, so asking again populates it. This is expected, not a bug.
- Frontend renders pending in `PanelContainer.tsx renderContent()` BEFORE the `switch(panel.type)`: `if ((panel.data as any)?.pending)` → Satellite + spinner + "Fetching live data · {symbol}".

## Live macro feed lives in its own table
- `macro_quotes` table (worker DDL in `_seed_universe`) is **separate from fundamentals** on purpose: indices/futures/FX must never leak into equity screeners/heatmaps (those `SELECT FROM fundamentals WHERE price NOT NULL`).
- `data.MACRO_YAHOO` maps internal macro symbol → Yahoo symbol (SPX→^GSPC, US10Y→^TNX already-in-%, DXY→DX-Y.NYB, WTI→CL=F, GOLD→GC=F, etc.). Assets with no clean feed (US2Y, US2Y10Y, TIPS10Y, IRON) stay mock.
- Worker `_macro_loop` (MACRO_INTERVAL=120s) gathers `_ingest_macro` per asset → `_upsert_macro`. `build_macro_dashboard` reads `repo.macro_quotes()` per tile with mock fallback; sets envelope `source=live/mock` + `asOf` = newest tile timestamp.

## News uncapped to 100
- Default limits bumped 20/30/40 → 100 across `sources/news.py` (fetch_news/fetch_topic_news/fetch_market_news), `repo.news_for` + `refresh_news_live`, worker `_ingest_news_for`/`_ingest_market_news`, and `skills.NEWS_PANEL_LIMIT`.



====================================================================================================
FILE: .agents/memory/dcf-saved-models.md
====================================================================================================

---
name: DCF saved custom models
description: How named DCF assumption sets are persisted per session+symbol and restored in the DCF panel.
---

DCF panel lets users save/reload named assumption sets (e.g. "Bull case MSFT").

- Storage is in-memory session state (`state.py` `_dcf_models: sessionId -> [{name, symbol, assumptions, savedAt}]`), scoped by sessionId AND symbol. Same pattern as watchlist — no DB.
- REST endpoints in `main.py`: GET/POST/DELETE `/api/dcf-models` (POST validates the 6 assumption keys; list/delete take query params). Returns `{models: [...]}` filtered to the requested symbol.
- Frontend `DCFPanel.tsx` calls these with **raw relative `fetch("/api/dcf-models")`** (proxy-routed, like FeatureRequestModal), NOT the generated api-client — so no openapi.yaml/codegen churn for this CRUD.
- `DCFPanel` now takes a `sessionId` prop (drilled from `PanelContainer`); the Models UI only renders when sessionId is present.
- **Why client-side restore works:** reloading just sets the local `assumptions` state; the panel already recomputes projections+impliedMid via `runClientDCF`. The static sensitivity grid (`data.sensitivity`) is NOT recomputed on assumption change — pre-existing behavior, left as-is.



====================================================================================================
FILE: .agents/memory/debounced-recompute-deps.md
====================================================================================================

---
name: Debounced effect timer starvation in panels
description: Why a debounced re-run effect in a terminal panel can silently never fire, and how to make it reliable.
---

# Debounced re-run effects must not depend on churning references

Terminal dashboard panels receive their `data` (the parsed panel payload) as a prop
from the Dashboard parent, which re-renders frequently (live data polling,
framer-motion animation). On many of those re-renders the parent passes a **new
`data` object reference** even when content is unchanged.

If a debounced side-effect (e.g. "re-run the projection 450ms after the user edits a
slider") is written as:

```ts
const run = useCallback(async () => { ...uses data.symbols... }, [data.symbols]);
useEffect(() => {
  const t = setTimeout(run, 450);
  return () => clearTimeout(t);
}, [horizon, drift, dirty, run]); // ← `run` identity churns with data
```

then every incidental parent re-render changes `run`'s identity, the effect cleanup
fires, and the 450ms timer is rescheduled. When re-renders arrive faster than the
debounce window, **the timer never completes and the action never fires** — and it
presents as *flaky*: it works whenever there happens to be a render gap, fails when
there isn't.

**Why:** this caused the What-If Scenario "instant re-run" to fire sometimes and
silently do nothing other times in e2e tests.

**How to apply:**
- Keep mutable inputs (e.g. `data.symbols`, `canTune`) in a `useRef` you assign on
  every render, and make the callback `useCallback(..., [])` so it is referentially
  stable.
- Make the debounce `useEffect` depend on **primitives only** (the edited values +
  a `dirty` flag), never on `data` or the callback.
- Same principle for a panel's "reset local edits when a new payload arrives" effect:
  key it off a **stable string signature** of the parsed scenario
  (`prompt|scope|symbols|horizon|drift`), not the `data` object reference — otherwise
  every re-render wipes the user's in-progress tweaks.



====================================================================================================
FILE: .agents/memory/durable-session-state.md
====================================================================================================

---
name: Durable, firm-scoped session state
description: How active dashboards/history/DCF/alerts are externalized to Postgres so the API is stateless and horizontally scalable.
---

The terminal's per-session working state (active dashboards, conversation
history, saved DCF models, trade-flow alert rules/events, session owner) is the
one thing that was process-memory only. It now lives in Postgres so a restart no
longer wipes a user's session and multiple instances share it.

**Design:** one generic table `session_state(firm_id, session_id, kind, data jsonb, updated_at, PK(firm_id,session_id,kind))`.
One row per concern (`kind` = dashboard/history/dcf/alert_rules/alert_events/owner),
so each can be read/mutated independently. Read-modify-write goes through a
`_mutate` helper that takes `SELECT ... FOR UPDATE` so concurrent instances
serialize on the row instead of racing (append_history cap, alert-event dedup,
set-once owner all rely on this). Falls back to an in-memory dict when no
`DATABASE_URL` (feature still works, just not durable/shared) — same DB-first /
in-memory-fallback pattern the other stores use.

**Why one table, not one-per-concern:** keeps schema/migration trivial and the
firm+session scoping uniform; jsonb auto-parses to python objects via psycopg
dict_row, so no per-kind columns needed.

**Firm scoping:** `firm_id` comes from `tenant.current_firm_id()` (the request
contextvar), so two firms with the SAME session_id never see each other's state.
The watchlist is intentionally GLOBAL (shared default symbols) — stored under a
sentinel `firm_id=session_id="__global__"`, not firm-scoped.

**Public API of `state.py` was preserved exactly** — only the storage backend
changed, so all call sites (main.py, agent, skills, worker) are untouched.

## Horizontal-scale companions (same task)
- `db.py`: pool min/max are env-tunable (`DB_POOL_MIN`/`DB_POOL_MAX`, default
  2/16) + a connection `timeout` so a saturated pool raises instead of hanging.
  Added `ping()` (SELECT 1), `pool_stats()`, and `advisory_lock(key)` ctxmgr
  (Postgres `pg_try_advisory_lock`; yields True when no DB → single instance).
- `/readyz` (public): pings DB + reports pool stats; returns 503 when DB is
  *configured but unreachable* (not ready for the durability promise), 200 in
  in-memory fallback mode.
- worker `_rebalance_loop` is wrapped in `db.advisory_lock(REBALANCE_LOCK_KEY)`
  so only ONE instance runs the money-moving rebalance pass per tick. Snapshot
  loop is left unlocked — `record_daily_snapshots` is idempotent per trading day
  so concurrent upserts are safe.

## Validating it
- Durability: signup → write session state (e.g. POST /api/dcf-models) →
  restart workflow → read back. Isolation: a second firm with the same
  sessionId must read empty.
- `pnpm loadtest:api` (scripts/loadtest-api.sh + loadtest_api.py): boots a
  server, signs up N firms, hammers hot paths concurrently, asserts errors=0 and
  zero cross-firm isolation/durability breaches. **Latency is report-only**
  (warning, not a gate) — absolute numbers depend on loopback vs. public-proxy
  and instance count. The agent-bash run trips the yfinance MAX_PATH wrapper at
  uvicorn launch, so drive the DRIVER against the running workflow with the
  `env -i .../.pythonlibs/bin/python3` workaround if you must run it yourself.



====================================================================================================
FILE: .agents/memory/earnings-calendar-panel.md
====================================================================================================

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



====================================================================================================
FILE: .agents/memory/economic-releases-revisions.md
====================================================================================================

---
name: Economic releases + FRED revision history
description: Two FRED/ALFRED-backed passthrough panels (economic_releases, series_revisions) and the vintage-print honesty contract.
---

# Economic releases & series revisions (FRED/ALFRED)

Two passthrough panels backed by the free FRED series API + ALFRED vintage API (needs `FRED_API_KEY`).

- `economic_releases` — recent/upcoming key US releases (CPI, PCE, GDP, unemployment, payrolls, PPI). Each row: reported value + period, prior value + period, change, frequency, next scheduled release date. Map of tracked series lives in `ECON_RELEASE_SERIES` in `rates.py`.
- `series_revisions` — any FRED series by id. Pulls full vintage history via ALFRED (`realtime_start=1776-07-04`, `realtime_end=9999-12-31`) → per-period vintage prints. Chart overlays **current (revised)** vs **initial print**; table lists per-period initial/current/totalRevision/vintageCount/revised; a vintage timeline highlights the most-revised recent period.

**Honesty contract:** all data real/live with as-of. No synthetic fallback — absent key / unknown id / dead feed return `source="unavailable"` with a `note`; panels render an AlertTriangle empty state. `series_revisions` always keeps its FRED-id input box mounted (even when unavailable) so the user can retry; it routes through `onRefine({series_id})` → `handleRefineParamsLive` (deterministic `RefineRequest.params`, no global Processing overlay).

**Adapter:** `_fred_get` routes through `_resilient.request("fred",...)` (breaker/backoff); propagates non-throttle HTTP errors. Agent bash has no egress, so verify FRED ONLY via the running api-server workflow (curl localhost:$PORT/api/orchestrate), never ad-hoc.

**Wiring:** both are subject-agnostic passthrough types (no DATA_MODELS entry, no codegen). Revisions intent maps phrasings → FRED id (regex for explicit id, default GDPC1). Routed in agent heuristic via `wants_revisions` / `wants_econ_releases`.



====================================================================================================
FILE: .agents/memory/edgar-form4-xml-quirk.md
====================================================================================================

---
name: EDGAR Form 4/5 XML field-wrapping quirk
description: Which insider-filing fields are <value>-wrapped vs direct text, and the silent-None failure it causes
---

# SEC Form 4/5 ownership XML: <value>-wrapped vs direct-text fields

In a Form 4/5 `<ownershipDocument>`, MOST fields wrap their content in a child
`<value>` element, but several do NOT — they are direct element text. Mixing
these up parses silently to `None` (no exception), so the bug only shows as bad
data downstream.

**Read with the `<value>` helper (wrapped):** securityTitle, transactionDate,
transactionAmounts/transactionShares, transactionPricePerShare,
transactionAcquiredDisposedCode, postTransactionAmounts/sharesOwnedFollowingTransaction.

**Read as direct text (NOT wrapped):** transactionCoding/transactionCode,
issuer/issuerName, reportingOwnerId/rptOwnerName, and every
reportingOwnerRelationship flag (isDirector, isOfficer, officerTitle,
isTenPercentOwner, isOther, otherText).

**Why it matters:** reading transactionCode with the value-helper made every code
`None` → every trade classified `other` → buy/sell counts 0 → sentiment always
"no open-market activity". Same wrapper mistake made every insider render
"Unknown" and every role blank.

**How to apply:** in `app/sources/edgar.py`, `_value()` = `_text(node, path +
"/value")`; `_text()` = direct element text. Pick per field per the lists above.
There is no schema enforcing this, so verify against a REAL filing (e.g. ADBE)
after any parser change — expect a realistic code distribution (S/M/F/A/G), real
insider names, and populated roles, not all-`other`/all-`Unknown`.



====================================================================================================
FILE: .agents/memory/etf-holdings.md
====================================================================================================

---
name: ETF holdings & reverse exposure
description: Real ETF constituents + "which ETFs hold X" — free-feed limits, coverage honesty, cold-cache bootstrap.
---

# ETF holdings & reverse exposure

Two passthrough panels (no pydantic model in harness.DATA_MODELS — harness lifts
asOf/source/note to the envelope): `etf_holdings` (forward) and `etf_exposure`
(reverse "which ETFs hold <stock>").

## Free-feed limit is the whole story
- Source is yfinance `funds_data.top_holdings`, which exposes a fund's **TOP
  holdings only** (~10 names), NOT the full constituent list. Paid full-holdings
  feeds are out of scope.
- `holdingPercent` arrives as a **fraction** (0.0712 = 7.12%) → multiply by 100.
- **Why it matters:** "coverage" = sum of listed weights is the % of the fund the
  top names span (often ~40–70%), and is reported, never padded to 100%. The
  reverse lookup can only find a stock if it's in some ETF's *top* slice — a name
  held more deeply will not appear. Both panels say this explicitly; never impute.

## Cold-cache bootstrap (reverse lookup)
- The worker `_holdings_loop` round-robins a common-ETF set to keep the cache warm.
- A reverse-lookup request on a cold cache synchronously fetches up to
  `_EXPOSURE_BOOTSTRAP_CAP` (8) uncached ETFs to bound latency under the ~60s
  preview proxy, then re-queries. The scanned universe is reported so a "not found"
  is honest about what was actually checked.

## Sector breakdown is live-only
- Reuses `skills._etf_sector_weights` (yfinance `sector_weightings`, cached). When
  yfinance is throttled it returns empty, so the holdings panel's sector breakdown
  is simply omitted (honest), not faked. It populates once the feed recovers.

## Verifying without live yfinance
- This env's worker hammers yfinance at boot and trips the circuit breaker, so the
  running server often returns `source=unavailable` for fresh ETFs. That's the
  correct honest fallback, not a bug — prove the real parsing path with a mocked
  `top_holdings` DataFrame (cols "Name"/"Holding Percent", percent is a fraction)
  plus an in-memory DB stub instead of relying on the live feed.
- LLM-routed panel types (e.g. intraday_chart) can't be reached here when the AI
  router is unavailable — orchestrate then falls back to the generic heuristic
  bundle. Unrelated to ETF work, but explains why some live orchestrator tests
  flake in isolation.



====================================================================================================
FILE: .agents/memory/execution-tca.md
====================================================================================================

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



====================================================================================================
FILE: .agents/memory/factor-risk-model.md
====================================================================================================

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



====================================================================================================
FILE: .agents/memory/filings-browser-edgar.md
====================================================================================================

---
name: SEC filings browser (EDGAR)
description: How the filings_browser panel sources EDGAR data and the non-obvious EDGAR full-text-search quirks.
---

# SEC filings browser (`filings_browser`)

Two modes in one panel:
- **filings** — recent dated filings for a resolved ticker, from the submissions
  `filings.recent` feed (form, filingDate, reportDate/period, accession, doc/index URLs).
- **search** — EDGAR full-text search (FTS).

## EDGAR full-text search quirks (non-obvious)
- FTS endpoint: `https://efts.sec.gov/LATEST/search-index?q=...&forms=...&ciks=<10-digit>&startdt=&enddt=`.
- **The `ticker=` param is IGNORED by FTS.** You MUST pass a zero-padded 10-digit
  `ciks=` to scope to one filer. Resolve ticker→CIK first.
- A valid SEC `User-Agent` header is required or requests are rejected.
- FTS only covers filing **documents since 2001**; results are ranked by relevance,
  not date. Report this in coverage text so users aren't misled.

## Honesty contract
- No SEC filer / CIK match → `feedSource: "unavailable"`, empty list, coverage note.
- EDGAR unreachable → `feedSource: "error"`. Never fabricate filings.

## Frontend
- Form-type filter chips filter **client-side** over the already-loaded list
  (instant, both modes) keyed on `rootForm`. The search box submits explicit
  `{symbol, query}` via the param-refine path (no global Processing overlay).
- `filings_browser` is a passthrough panel: it's in the BACKEND PanelType enum but
  NOT in the frontend openapi-codegen types, so `case "filings_browser"` throws the
  expected non-gating `TS2678` (same as every other passthrough panel). The vite
  build does not gate on tsc and passes.



====================================================================================================
FILE: .agents/memory/firm-admin-console.md
====================================================================================================

---
name: Firm Admin Console
description: Multi-tenant admin self-service surface (users/invites/limits/firm/billing) and its server-side guards.
---

# Firm Admin Console

Admin-only self-service area, firm-scoped, server-authoritative (`require_role("admin")`).
Routes live in main.py and return plain dicts (no openapi codegen); the frontend uses raw
`fetch("/api/admin/*")` (AdminConsoleModal), same precedent as FeatureRequestModal.

## Invariants that bit us / must hold
- **Deactivation is enforced in TWO places, not one.** `require_identity` rejects an existing
  session of a deactivated user (401), but `/auth/login` must ALSO reject re-login — otherwise a
  deactivated user just logs back in. Login returns **403 "Your account has been deactivated."**
  (distinct from 401 bad-credentials) and the check reads `user.get("active", True)`.
- **Last-active-admin guard** on role-change / deactivate / remove: never let a firm reach zero
  active admins (`count_active_admins(firm_id) <= 1` → 400).
- **Self guards**: an admin cannot demote / deactivate / remove their own account (400).
- **Firm isolation**: `_require_member` asserts the target user belongs to the actor's firm →
  cross-firm action returns **404** (not 403), so you can't probe other firms' user ids.
- Deactivating a user calls `delete_user_sessions` to kick them immediately.

## Invitations
- One-time token: raw via `auth.new_session_token()`, stored as `auth.hash_token(token)`. The
  invite link is `?invite=<rawtoken>` on the terminal path.
- Public `GET /auth/invitation?token=` previews {firmName,email,role}; `POST /auth/accept-invite`
  creates the user in the inviting firm, sets the session cookie, audits via `_admin_audit_system`
  (no admin actor). After accept the token is consumed → preview/accept again is 404.
- AuthScreen splits into LoginScreen vs AcceptInviteScreen (chosen by `?invite=` in the URL);
  useAuth.acceptInvite posts raw (not in generated client) and reuses the AuthIdentity shape.

## Reuse
- Risk limits / kill switch / audit reuse `compliance_store` (get_config/set_limits/
  set_kill_switch/list_audit) + `engine.compliance.LIMIT_DEFS/DEFAULT_LIMITS`. Admin actions are
  audited through `compliance_store.append_audit(decision="ok")` via `_admin_audit`.
- Billing is read-only: plan/seats on the firms row; seatsUsed = active members.

## Test
- tests/test_admin.py is standalone (no pytest); stub ai.ai_available=False + worker.start/stop;
  THREE TestClients (admin/invitee/other) at `base_url="https://testserver"` (secure cookie).
  Run with the MAX_PATH env wrapper. Not wired into any registered validation by design.



====================================================================================================
FILE: .agents/memory/firm-audit-trail.md
====================================================================================================

---
name: Firm-wide audit trail
description: How the unified user-attributed append-only audit log is built on top of the compliance audit plumbing.
---

# Firm-wide audit trail

The pre-trade compliance audit table (`compliance_audit`) was generalized into a
unified firm-scoped, user-attributed, append-only audit log. It is NOT a new
table — the same `compliance_store` plumbing carries every category.

**Categories** (the `category` column groups entries): `compliance` (pre-trade
gate decisions), `trade` (rebalances), `strategy` (create/transition), `config`
(compliance config changes), `dashboard`, `alert`, `feature` (build/delete),
`auth` (signup/login/login_failed/logout/permission_denied), `admin` (firm
settings). `append_audit(category=...)` defaults to `compliance` so the existing
gate calls keep working unchanged.

**Actor attribution is automatic.** `tenant.set_current_actor(...)` is called in
`require_identity` right after `set_current_firm`, so every write (even the deep
pre-trade gate) attributes to the acting user via `tenant.current_actor()` with
no plumbing. The contextvar copies into the sync threadpool the same way firm
does. No resolvable actor → recorded as `system` (e.g. worker-scheduled
rebalances, which run `strategy.rebalance` directly, not the HTTP endpoint).

**Public auth router has no identity context**, so `_audit_auth(...)` in main.py
passes `firm_id` + `actor_*` explicitly. A failed login is only audited when the
email maps to a known user (otherwise there is no firm to scope it to).

**Append-only is enforced by absence**: there is deliberately NO HTTP path to
clear/edit the trail. The old `DELETE /api/compliance/audit` endpoint was
removed; `compliance_store.clear_audit()` remains for test setup only.

**Compliance panel** now shows only gate decisions: `build_compliance` calls
`list_audit(40, category="compliance")`. The full firm-wide log lives behind the
admin-only `GET /api/audit` (require_role("admin"), filters user/category/action/
since/until) which also returns `actors` + `categories` facets for the viewer
dropdowns. Frontend: `AuditLogModal.tsx` raw-fetches `/api/audit` (no codegen),
gated in Terminal header by `identity?.user.role === "admin"`.

**Why:** keeps one storage/contract for all consequential actions and preserves
the pre-trade gate behavior while making the whole system answer "who did what,
when". Test: `tests/test_audit.py` (standalone, https TestClient, create a
non-admin via `auth_store.create_user` to exercise permission_denied + isolation).



====================================================================================================
FILE: .agents/memory/fixed-income-live-data.md
====================================================================================================

---
name: Live Treasury + credit-spread sources for Fixed Income panels
description: Where the FI builders (yield curve, bond RV, CDS, cashflow/duration) get live rates/credit and the env quirks behind the choices.
---

The four Fixed Income builders pull live data via `app/sources/rates.py`:

- **US Treasury par yields:** KEY-LESS CSV at
  `https://home.treasury.gov/.../daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve`.
  Fetch current + prior 2 calendar years to populate the ago1y/ago2y comparison rows.
  Columns are `"1 Mo"`,`"3 Mo"`,`"6 Mo"`,`"1 Yr"`...`"30 Yr"` (no 4M/1.5M tenors).
- **Credit spreads (corporate OAS, used for bond RV + CDS proxy):** ICE BofA OAS
  indices via the **official FRED API** `api.stlouisfed.org` — needs a free `FRED_API_KEY`.
  Series return values in **percent → multiply by 100 for bps**. Buckets: AAA/AA/A/BBB/BB/B/CCC + IG/HY.

**Env quirk (cost real time to discover):** FRED's key-less `fredgraph.csv`/`/data` download
hosts are BLOCKED from this environment (HTTP/2 INTERNAL_ERROR / timeout), but the
keyed API host `api.stlouisfed.org` IS reachable. So credit data REQUIRES the key here even
though FRED nominally offers key-less CSV elsewhere.

**Fallback philosophy:** Treasury works with no key (yield curve + UST cashflows are live
unconditionally). Without `FRED_API_KEY`, credit-dependent panels (bond_rv, cds_pricer,
non-UST cashflow) cleanly fall back to curated mock and label `source:"mock"`. Builders
re-base mock OAS/zSpread/ASW onto the live bucket curve while preserving each name's
idiosyncratic offset, then recompute yields off the live Treasury curve.

**Refresh interval:** `RATES_REFRESH_SECONDS` env (default 3600) via `cache.cached`.



====================================================================================================
FILE: .agents/memory/frontend-test-harness.md
====================================================================================================

---
name: Terminal frontend test harness (vitest)
description: How to run/extend headless tests for the terminal's React hooks, esp. Voice Mode browser-API mocks.
---

The `terminal` artifact has a **vitest + jsdom** setup (added for the Voice Mode
conductor tests). Run with `pnpm --filter @workspace/terminal test` (also a
`voice-frontend` validation command). Config: `artifacts/terminal/vitest.config.ts`
(jsdom env, globals on, `@` alias, setup `src/test/setup.ts`). Test files match
`src/**/*.test.{ts,tsx}` and are **excluded from tsc typecheck** (`**/*.test.ts`),
so vitest globals never break `typecheck`. Note `src/test/*.ts` helpers ARE in the
typecheck include — keep them clean.

**Why a custom browser-API mock instead of real APIs:** jsdom has no
`SpeechRecognition`, no `AudioContext`, no `navigator.mediaDevices.getUserMedia`,
and real Web Speech needs a mic, so the conductor's listen→think→speak→idle loop
can't run headless. `src/test/voiceMocks.ts` stands in for all of them and lets a
test DRIVE the recognizer by hand: `latestRecognition()` grabs the instance the
hook just `.start()`ed, `emitResult(rec, text, isFinal)` feeds speech,
`emitError(rec, "network")` raises, and a recognizer `.stop()/.abort()` fires
`onend`. `denyMic()` makes the next `getUserMedia` reject (mic-denied path). The
mock `AudioContext` resolves narration playback instantly (buffer-source
`start()` → microtask `onended`), and `requestAnimationFrame` is stubbed to a
no-op so the level-meter loop stays inert.

**How to apply:** to test another browser-API-heavy hook, reuse/extend
`voiceMocks.ts` + the renderHook/act/waitFor pattern in
`useVoiceConductor.test.ts`. Remember push-to-talk never auto re-arms, so a full
turn leaves exactly one recognition instance — asserting the instance count is
how the test proves no echo/self-trigger re-listen happened.

**recharts panels need a `ResizeObserver` polyfill under jsdom.** Any test that
renders a panel using recharts `ResponsiveContainer` throws
`ReferenceError: ResizeObserver is not defined` (jsdom has none). Stub it with a
no-op `class { observe(){} unobserve(){} disconnect(){} }` before render.

**Live full-stack integration tests** (e.g. the intraday-chart in-panel controls
test) can boot the real FastAPI app from vitest with `spawn("python", ["-m",
"uvicorn", "app.main:app", "--app-dir", <api-server>, ...])` + `TERMINAL_SKIP_WORKER=1`,
poll `/api/healthz`, then drive the real `<PanelContainer>` via `setBaseUrl`
(from `@workspace/api-client-react`). Because orchestrate routing is LLM-driven,
RETRY orchestrate until the target panel type appears. **Why it can't run in the
agent bash tool:** live yfinance/refine trips the agent shell's MAX_PATH syscall
wrapper — these tests only pass under the `panel-runtime-test`/`smoke`/`voice-backend`
validation env (same env those make live calls in). Verify via the validation run,
not the bash tool.



====================================================================================================
FILE: .agents/memory/institutional-13f.md
====================================================================================================

---
name: Institutional holdings & 13F flows
description: How "who owns X" / 13F-flows panels are built and two non-obvious correctness traps in 13F ingestion.
---

Real institutional ownership + QoQ fund flows come from SEC 13F filings, pre-aggregated by the worker (13F is per-institution, so a per-stock fetch is impossible at request time). Cold store → builders return an honest `feedSource="pending"`, never partial. A curated set of ~16 manager CIKs is tracked; managers configured-but-not-yet-ingested are reported in `coverage.missing`, never imputed.

## Trap 1 — partial 13F amendments must NOT supersede the full filing
A quarter can have an original `13F-HR` plus one or more `13F-HR/A` amendments. An SEC **"NEW HOLDINGS"** amendment lists only the *added* positions (can be a handful), not the full portfolio. Selecting "latest accession per report period" therefore silently discards the full book and makes every other name look **exited** (observed: JPMorgan 2026Q1 amendment had 378 positions vs 7406 in the original → AAPL falsely shown as the biggest seller, −$61B).
**Fix:** for each report period, parse every candidate filing and keep the one with the **most holdings** (the most complete information table), ties broken by recency. Don't merge/impute — surface a single real filing as the snapshot.
**Why:** avoids a fragile amendmentType (RESTATEMENT vs NEW HOLDINGS) parse while reliably defeating the partial-amendment trap.

## Trap 2 — flows are a SHARE decision, not a value change
Buyers/sellers must be split on the discretionary **share** change (new/added vs trimmed/exited), NOT on change in position *value*. A manager who adds shares while the price falls has a negative `deltaValue` and would be miscounted as a seller. Each flow row carries `tradeValue = deltaShares × reported price` (price = 13F value/shares; for an exited row, fall back to the prior period's price). Rank/total by `tradeValue`.
**Gotcha:** the assemble helper returns rows with `priorShares`/`priorValue`; the flow-row converter needs those to recover the price for *exited* rows (latest shares = 0). Don't double-apply the converter — the second pass sees an already-stripped row (no prior keys) and zeroes out exited trade values.

## Verifying changes to ingestion logic
The worker skips re-ingest when `inst_latest_period` already matches, so after changing filing-selection logic you must `DELETE FROM inst_holdings; DELETE FROM inst_filings;` then restart the api-server to force a fresh pull (~1–2 min for the full manager set).



====================================================================================================
FILE: .agents/memory/launch-video-layering.md
====================================================================================================

---
name: Launch video layering & perf
description: How the launch-video artifact avoids transition lag and text/background overlap.
---

# Launch video layering & perf

The launch-video template composites persistent layers controlled by a derived
`baseSceneKey` (strip `_r[12]$` off `currentSceneKey`), NOT by remounting per scene.

**Perf rules (lag fixes):**
- DotWaveBackground keeps ONE persistent rAF loop (useEffect deps `[]`); pass
  `active` via a ref so toggling it never restarts the loop. Restarting rAF on every
  scene change was the main source of transition lag.
- Never animate CSS `filter: blur()` or use `backdrop-blur` in scenes — both tank
  framerate. Animate only opacity / scale / translate / scaleY.
- Cap canvas dpr (~1.5), widen dot spacing (~30), lerp amplitude for smoothness.

**Overlap fixes (readability):**
- Text scenes sit above the canvas with a `CenterScrim` (radial black gradient) or a
  solid `bg-black/NN` panel behind copy. Lower the canvas max dot alpha (~0.6) so dots
  never compete with white text.
- The Voice Orb is a single persistent element repositioned per scene (x/y/scale +
  `visible` opacity prop) so it never sits under body text.

**Why:** user reported "laggy on transitions, text overlaps in bg and front."
**How to apply:** when adding scenes, gate persistent layers (DotWave/Orb/Dashboard)
on `baseSceneKey`; give every text scene its own scrim; keep AnimatePresence keyed by
`currentSceneKey` (not baseSceneKey) so the scene-lock `_r1/_r2` loop still re-fires.
Strict monochrome — no green.



====================================================================================================
FILE: .agents/memory/load-test-latency-baseline.md
====================================================================================================

---
name: Load-test latency baseline & default-dashboard caching
description: True loopback latency baseline for the hot API paths, why /api/dashboard/default was the bottleneck, the cache+single-flight fix, and how the load driver's per-endpoint budgets / opt-in gate work.
---

The hot read paths are all trivial (<12ms warm, served from Postgres) EXCEPT
`/api/dashboard/default`. That endpoint builds 6 panels and fires several live
upstream fetches per request (heatmap, news RSS, sentiment) for a ~240KB payload
— ~1s of work, and its output is IDENTICAL for everyone (no params, no user/firm
scoping). Under concurrency it saturates the single uvicorn worker and starves
every other endpoint (loopback driver: dashboard p95 ~26s, all others multi-second,
~5 req/s).

**Fix:** serve it from a short-TTL process cache (`DASHBOARD_DEFAULT_TTL`, default
60s, 0 disables) via `cache.cached_singleflight`. Result on the same loopback
driver: dashboard p95 ~1s warm, total throughput ~5 → ~91 req/s.

**Why single-flight, not plain `cache.cached`:** `cached` has NO lock around the
producer, so on a cold/expired key every concurrent caller runs the expensive
build at once — a thundering herd (cold-cache dashboard p95 ballooned back to ~10s).
`cached_singleflight` (added to cache.py) takes a per-key lock so only one caller
rebuilds while the rest wait and read the fresh value. Use it for any cached
producer that is both expensive AND shared. Cold-cache p95 then capped at ~2.2s
even with the live-ingestion worker contending.

## Measuring latency here (env constraints)
- **Drive over loopback, not the public proxy.** Point the driver at the running
  workflow: `BASE=http://127.0.0.1:8080`. The public TLS proxy inflates numbers.
- The driver is HTTP-only stdlib, but running ANY python from agent bash needs the
  `env -i .../.pythonlibs/bin/python3.11` MAX_PATH workaround.
- **You cannot get a worker-SKIPPED clean baseline from agent bash.** Booting your
  own uvicorn with `TERMINAL_SKIP_WORKER=1` works, but the moment a request hits a
  stale-data path it spawns a yfinance subprocess → the agent-bash MAX_PATH wrapper
  kills it. So agent-bash runs must go against the live workflow (worker ACTIVE),
  whose contention adds real run-to-run variance (dashboard cold p95 1–2.5s). The
  clean worker-skipped baseline is what `pnpm loadtest:api` (scripts/loadtest-api.sh)
  produces when a human runs it in a NORMAL repl shell.
- **Signup is rate-limited 10/60s** (`security.rate_limit("auth", 10, 60)`). The
  driver signs up 8 firms, so two runs inside a minute trip it ("signup failed for
  firm N"). Run it once per minute.

## Load driver budgets & gate (scripts/loadtest_api.py)
- Per-endpoint p95 budgets replace the old single global one: `ENDPOINT_BUDGET_MS`
  (dashboard_default 2000ms, the rest 1500ms), fallback `DEFAULT_LATENCY_BUDGET_MS`
  (`LOAD_LATENCY_BUDGET_MS`, default 1500). Override any one with
  `LOAD_BUDGET_<LABEL>_MS`.
- Correctness (errors=0, zero cross-firm isolation/durability breaches) ALWAYS gates.
- Latency is a report/warning by default; set `LOAD_GATE_LATENCY=1` to make a p95
  over budget FAIL the run. Keep it opt-in / loopback-only — absolute latency depends
  on loopback-vs-proxy and instance count, so a blanket hard gate would be flaky.



====================================================================================================
FILE: .agents/memory/macro-dashboard-overrides.md
====================================================================================================

---
name: Macro dashboard asset customization
description: Non-obvious contracts when adding pin/add/remove customization to the macro_dashboard panel and its refine flow.
---

# Macro dashboard overrides — gotchas

Refine instructions let users pin/remove macro tiles (e.g. "add EURUSD",
"remove VIX from the risk view"). Three things that bite if you forget them:

- **Persisted refine state must be a field on the pydantic data model.**
  The harness validates builder output with `model.model_validate(...).model_dump()`,
  which silently drops unknown keys. Any state you want to survive across
  refines (here, `overrides`) has to be declared on the model or it vanishes.
  **Why:** refines accumulate by reading the panel's own prior `data`.

- **Refine must special-case subject-agnostic panels before the generic path.**
  The generic heuristic returns `{}` for panels with no symbol/sector, which
  would wipe the panel's theme. `macro_dashboard` is handled first in both
  `_refine_params_llm` and `_refine_params_heuristic`.

- **Never resolve theme unconditionally in the heuristic.**
  `data.resolve_macro_theme()` falls back to "global", so calling it on a plain
  "add gold" would reset the theme. Detect an explicit theme word first and
  keep the current theme otherwise.

Other conventions: only real `MACRO_ASSETS` symbols are honored (unknown ones
ignored, honest-data); overrides merge latest-op-per-symbol so a later add
cancels a prior remove; `data.resolve_macro_symbols()` matches aliases
longest-first and consumes matches so "2y-10y" doesn't also match "2y".



====================================================================================================
FILE: .agents/memory/macro-live-data.md
====================================================================================================

---
name: Macro dashboard live data wiring
description: How the macro/cross-asset dashboard sources live quotes, which symbols have no free source, and the isolated ingest pattern used.
---

The macro dashboard (rates/FX/commodities/indices tiles) is wired to live Yahoo
quotes via a dedicated, isolated path — NOT through the equity universe/fundamentals
tables (so macro pseudo-symbols never leak into screeners/heatmaps).

**Architecture:** `MACRO_YAHOO` map in data.py (internal code → Yahoo symbol) →
worker `_macro_loop` fetches each via the existing `prices.fetch_price_history`
("1mo"/"1d") and upserts into a runtime-created `macro_quotes` table (CREATE TABLE
IF NOT EXISTS in worker start, like strategy_store) → `repo.macro_quotes()` reads
live rows → `build_macro_dashboard` merges live over the curated mock defaults
per tile.

**Per-tile provenance:** each tile carries `isLive`; panel envelope `source` is
"live" when ANY tile resolved live, `asOf` = max of live timestamps. The
MacroTile pydantic model needs `isLive: bool = False` or the harness drops it.
UI shows a green/grey dot per tile + a live/reference legend.

**Symbols with NO clean free source (stay mock/"reference"):** US2Y, the 2Y10Y
spread, TIPS 10Y breakeven, Iron Ore. Yahoo has ^TNX (10Y) but no 2Y ticker;
`2YY=F`/`TIO=F` exist but return month/year-old prints. **Why:** that staleness is
exactly why there's a `MACRO_STALE_DAYS` guard — a quote older than the window is
stored `is_live=FALSE` so we never badge a stale futures print as "live".

**Live-able set:** US10Y(^TNX, a % level), DXY(DX-Y.NYB), EURUSD, USDJPY(JPY=X),
USDCNH(CNH=X — sparse daily history, handle short sparklines), WTI(CL=F),
GOLD(GC=F), COPPER(HG=F), SPX(^GSPC), NDX(^NDX), EEM, HSCEI(^HSCE),
CSI300(000300.SS), VIX(^VIX).



====================================================================================================
FILE: .agents/memory/market-data-sources.md
====================================================================================================

---
name: Free key-less market data sources + quirks
description: Non-obvious behaviors of the free Yahoo/yfinance data sources used for the terminal's realtime ingestion.
---

The terminal backend ingests free, key-less market data. The sources and their
gotchas (not discoverable without hitting them live):

- **OHLCV + quote:** Yahoo chart v8 `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}`
  (`range`/`interval` params). Returns daily series + a `meta` block with the live
  quote (regularMarketPrice, fiftyTwoWeekHigh/Low, etc). Needs a browser `User-Agent`
  header or it 403s/429s.
- **News (per-ticker):** Yahoo RSS `https://feeds.finance.yahoo.com/rss/2.0/headline?s=SYM1,SYM2`
  — multi-symbol, key-less. Parse with feedparser; per-item `tags` carry the tickers.
  Note Yahoo's per-ticker feed also returns broad/generic articles (Motley Fool etc.), so
  symbol-scoped news is never purely about that name.
- **News (topic/market):** Google News RSS, key-less. Search:
  `https://news.google.com/rss/search?q=<query>&hl=en-US&gl=US&ceid=US:en`; Business topic:
  `.../rss/headlines/section/topic/BUSINESS`. BOTH **302-redirect** — httpx needs
  `follow_redirects=True` or you get an empty feed. Titles end in " - Publisher" and carry
  `entry.source.title`; strip the suffix and prefer that as the source name.
- **Fundamentals:** `yfinance` `Ticker(sym).info` (it handles Yahoo's crumb/cookie auth).
  Heavier/slower than the chart endpoint, so ingest it on a slower cadence.

yfinance `.info` unit quirks (**Why:** these silently produce 100x-wrong numbers):
- `dividendYield` is already a **percent** (e.g. `0.47` means 0.47%), do NOT multiply by 100.
- `profitMargins` is a **fraction** (e.g. `0.63`), multiply by 100 to get net-margin %.

**Schema note:** sector is stored only on the `universe` registry table, NOT on
`fundamentals`. Join `fundamentals f LEFT JOIN universe u` and read `u.sector`.

**Yahoo chart `changePct` over a long range is a multi-month move, not 1D**
(**Why:** the chart `meta.chartPreviousClose` is the close at the *start* of the
requested range — a "6mo" pull made SPX show +8% and WTI +54% as the "change").
Equity tiles get a correct daily change from the fundamentals/quote loop, but
macro tiles have no such loop, so for macro ingestion recompute the 1D change
from the **last two daily closes** of the series: `base=closes[-2]`,
`ref=quote price or closes[-1]`, `changePct=(ref-base)/base*100`.

**Yield/derived-spread scales (macro feed):** `^TNX`/`2YY=F` are already in
**percent** (don't ×100). The 2s10s spread (`US2Y10Y`) is reported in **bps**
(10Y%−2Y%)×100; derive its prev value per-leg from each yield's own changePct
(`prev = price/(1+chg/100)`), not from a single blended change.

**Freshness contract:** panels carry optional `asOf`/`source` ("live"|"mock") on the
Panel envelope. Builders return them in their raw dict; the harness pops them off
before validating against the data model (data models intentionally exclude them).
The repository falls back to the curated `data.py` mock set whenever the DB is
unavailable or empty, so panels never render empty.

**Intraday OHLCV quirks (Yahoo chart v8):**
- Hard window-per-resolution limits: 1m≤7d, finer multi-minute (2m/5m/15m/30m/90m)≤60d,
  60m/1h≤2y. There is no range *token* for 7d or 60d — fetch those via `period1`/`period2`
  epoch params instead.
- **`period1` MUST come before `period2` in the query string** or Yahoo returns 422,
  even though the raw values are valid. (**Why:** cost two attempts to find; pure param
  ordering, not a value problem.)
- NEW data surfaces are live-or-unavailable: out-of-limit requests return a clean
  `available:false`/`source:"unavailable"` and NEVER substitute daily/synthetic bars.
  The PanelContainer source badge renders the literal `panel.source` so "unavailable"
  shows verbatim (do not collapse non-live to "mock").



====================================================================================================
FILE: .agents/memory/multi-tenant-isolation.md
====================================================================================================

---
name: Multi-tenant data isolation (per firm)
description: How firm scoping is enforced across every persisted/in-memory store in api-server; the contextvar pattern, the shared-by-design exception, and the verification path.
---

# Per-firm data isolation in api-server

Every user-owned store is scoped to the authenticated firm so Firm A never sees
Firm B's data. The mechanism is a request-bound firm context, not firm_id
threaded through every call site.

## The contextvar pattern (the load-bearing decision)
- `app/tenant.py` holds a `contextvar` with `DEFAULT_FIRM_ID="default"`,
  `set_current_firm()`, `current_firm_id()`, `resolve_firm(firm_id)` (explicit
  arg wins, else context, else default), and `firm_context(firm_id)` context
  manager.
- `require_identity` in `main.py` is **async** on purpose and calls
  `tenant.set_current_firm(...)` before returning. **Why async:** Starlette runs
  sync endpoints in a threadpool via anyio, which *copies* the contextvar into
  the worker thread. A plain sync dependency would set the var on a different
  context and the value would not reach the handler. Do not make it sync.
- Stores read `current_firm_id()` internally (param defaults to `None` →
  `resolve_firm`). Request handlers therefore need **no** firm argument — the
  context already carries it.

## Worker / background path
- The worker has no request context, so cross-firm loops
  (`record_daily_snapshots`, `run_scheduled_rebalances`) iterate
  `strategy_store.list_all_strategies()` (cross-firm, worker-only) and wrap each
  strategy in `with tenant.firm_context(s["firmId"]):`. Everything downstream
  (mark → snapshot read/write, rebalance → compliance precheck/get_config,
  `_persist`/upsert) then auto-scopes to that firm.
- `list_strategies()` is firm-scoped (request path); `list_all_strategies()` is
  the deliberate cross-firm escape hatch — only call it inside a `firm_context`.

## Storage shape
- DB tables get a `firm_id text NOT NULL DEFAULT 'default'` column added via
  idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` + backfill (matches the
  runtime-CREATE-TABLE convention; no drizzle push). Scoped: `strategies`,
  `strategy_snapshots`, `saved_dashboards`, `compliance_audit`.
- `compliance_config` is special: its PK **is** the firm_id (one config row per
  firm). The legacy single `id='global'` row is renamed to `'default'` on
  schema-ensure. Old `_GLOBAL_ID` constant is gone.
- In-memory fallbacks: per-session stores in `state.py` are keyed by a
  `(firm_id, session_id)` tuple via `_key()`; compliance `_mem_cfg`/`_mem_audit`
  are dicts keyed by firm_id.
- Cross-firm deletes/restores use `... WHERE id=%s AND firm_id=%s RETURNING id`
  so a wrong-firm id silently affects nothing (returns False / None).

## Shared-by-design exception
- Order-book replays (`orderbook_store.py`) are **NOT** firm-scoped on purpose:
  a reconstructed IEX DEEP session is firm-agnostic market data, identical for
  all tenants and expensive to rebuild, so it is cached once and shared.

## Verification
- The boot smoke check (`pnpm smoke:api`) now must authenticate first (auth gates
  all `/api`): it signs up a throwaway firm and passes the session via
  `Authorization: Bearer <token>` (the cookie is `Secure`, so curl won't echo it
  over plain http). The token is parsed from the signup `Set-Cookie` header.
- `pnpm smoke:api` boots uvicorn via the `python` wrapper which trips the
  agent-bash MAX_PATH trap — it runs fine in the real workflow/validation runner.
  To verify in agent bash, restart the `artifacts/api-server: API Server`
  workflow and hit `https://$REPLIT_DEV_DOMAIN/api/...` with curl (curl is fine;
  only the python subprocess trips MAX_PATH).
- Proven end-to-end via curl: Firm B can't list/restore Firm A's saved dashboard
  (404), B's delete leaves A's data intact, and A's restricted-symbol compliance
  config is invisible to B.



====================================================================================================
FILE: .agents/memory/multistrat-allocation.md
====================================================================================================

---
name: Multi-strategy capital allocation & firm risk
description: Firm-level multi_strategy panel — honesty contract for sleeve risk + the routing precedence traps it must avoid.
---

The `multi_strategy` panel treats every paper/live strategy as a *sleeve* of one
firm book and recommends a capital split (equal-weight / risk-parity / target-vol).

**Honesty contract (don't break):** every risk number must come from real persisted
daily NAV snapshots. A sleeve with too little history, or too little overlap with
the others, is flagged and held OUT of the covariance/correlation/allocation math —
never imputed. Drop shortest-overlap sleeves first so a brand-new sleeve doesn't
shrink everyone's common window. The combined book (NAV/P&L/netted exposures) still
shows ALL sleeves even when risk can't be computed yet.
**Why:** the whole pillar's value is that it's grounded; a faked correlation would
make the allocation advice actively misleading.

**Routing precedence trap:** "allocate capital" is already an optimizer keyword and
"my strategies" is already a desk keyword, so the multi-strategy intent must be
detected and dispatched BEFORE both the optimizer and the strategy-desk branches in
the agent heuristic. Keep its phrases off verb+"strateg" or the lifecycle
create-regex hijacks them. Note the LLM tool path (not the heuristic) is what
actually runs in /api/orchestrate when the model is up — both paths must route.
**How to apply:** when adding any new firm/strategy-level intent, check it against
the optimizer and desk keyword sets and order its dispatch ahead of them.



====================================================================================================
FILE: .agents/memory/navigator-cursor.md
====================================================================================================

---
name: AI navigator cursor
description: How the chat-triggered guided-walkthrough cursor coexists with voice and grounds tours in real on-screen panels.
---

# AI navigator cursor (Agentic Terminal)

A visible AI-controlled cursor that glides across the dashboard, stops on relevant
panels in reading order, and shows a caption per stop. Triggered from chat by
intent phrases ("walk me through…", "show me what matters", "give me a tour").

## Key design decisions
- **Tours only reference panels currently in session state.** The `/api/navigate`
  endpoint builds stops from `state.get_dashboard`'s panels (LLM grounded + reading-order
  heuristic fallback), validates/dedupes panelIds. The cursor then locates each panel
  in the DOM via `[data-panel-id]`. No invented panels => no dead stops.
- **Navigator is chat-triggered, voice is its own mode.** Voice mode hides chat, so the
  two can't be invoked simultaneously. They *both* drive `highlightedPanelId`, so they
  must never run together — toggling voice on stops any running tour.
  **Why:** shared highlight state would fight if both ran.
- **Intent routing:** strip the nav phrase + filler from the query; empty remainder +
  existing panels => tour what's on screen; non-empty (a subject like "NVDA") =>
  orchestrate first, then tour after the panels render (~850ms delay).
- **Cursor uses viewport coords** (`getBoundingClientRect` centre) to match a
  `position: fixed` overlay. Overlay is `pointer-events-none` (never blocks manual use);
  only the bottom-center control bar is clickable.
- **Playback:** per stop = scrollIntoView(center) → wait ~480ms for scroll to settle →
  re-measure → move cursor (framer spring) → highlight + caption → dwell (scaled to
  caption length) → auto-advance. Manual next/prev cancels the dwell. Re-measures on
  resize. Missing panel => skip to next stop. Tour auto-dismisses after the last stop.

## Gotcha
- api-server runs WITHOUT `--reload`, so backend route/agent changes need a workflow
  restart (`artifacts/api-server: API Server`) to take effect.



====================================================================================================
FILE: .agents/memory/options-chain-panel.md
====================================================================================================

---
name: Options chain panel
description: How the options_chain panel is generated and rendered (calls/puts ladder with expiry selector).
---
- options_chain returns ALL expiries (1W..1Y) in one payload; the frontend `OptionsChainPanel` holds the selected expiry + strike pagination client-side. Backend `selectedExpiry`/`expiry` param only sets the default tab.
- Quotes are synthetic but grounded: IV from `_iv_smile`, mid from `_bs_price`, then `_opt_quote` derives bid/ask (spread widens with |moneyness|), a deterministic `last` (FNV-1a `_det_hash` so it's stable per symbol/strike/expiry), and volume/OI (gaussian peak at ATM, volume heavier near-dated, OI grows with tenor).
- Strike ladder: `_strike_step(S)` picks a nice increment (0.5..100) ~2.5% of spot, centered on rounded ATM, 17 strikes. Real underlying price comes from `repo.get_company` (live), so asOf/source freshness contract applies.
- **Why:** matches the existing IV-surface expiry ladder so the two panels stay consistent; full-payload-per-expiry avoids round-trips when switching tabs.
- Routing: keyword heuristic `wants_chain` is checked BEFORE `wants_iv_surface`/`wants_options` in the derivatives block so "options chain"/"calls and puts"/"all strikes" don't get swallowed by strategy/surface intents. `_extract_expiry` maps free text (1M, weekly, etc.) to a label.



====================================================================================================
FILE: .agents/memory/orderbook-iex-deep-replay.md
====================================================================================================

---
name: Order-book real replay from IEX DEEP
description: How the order_book panel serves REAL depth reconstructed from IEX HIST DEEP captures, with synthetic fallback + honesty contract.
---

# Order-book real replay (IEX DEEP, venue-only, T+1)

The `order_book` panel can serve a **real** depth-of-book replay reconstructed
from IEX Exchange HIST DEEP captures, falling back to clearly-labelled synthetic
depth until a real replay exists.

## Honesty contract (must never be violated)
- `replayReal` is True ONLY for frames rebuilt from a real IEX DEEP capture.
- Real replays are **venue-only** (IEX prints, not the consolidated tape) and
  **T+1** (IEX publishes the capture the morning after the session).
- A symbol IEX barely traded yields NO real payload (`payload()` returns None
  below `MIN_FRAMES`); it must never be promoted to "real". The worker marks such
  jobs `unavailable` so the panel stops promising a real replay.
- Trade side is inferred (DEEP trades carry no side) via the standard quote/tick
  test against the prevailing book — label it as inferred, don't claim it's given.

## Flow (on-demand, never in the request path)
1. `skills.build_order_book` → `orderbook_store.latest_replay(sym)`; if cached,
   return REAL payload (re-select frame by `timestamp` param, set source/asOf).
2. Else `orderbook_store.request_job(sym)` (enqueue) + return synthetic via
   `_synthetic_order_book`, worded by job status (loading vs unavailable). The
   `source` string is lifted to the panel **envelope** by the harness (not data).
3. `worker._orderbook_loop` (20s poll) drains `pending_jobs`, resolves
   `iex_deep.latest_session`, and reconstructs ALL queued symbols in ONE shared
   streaming pass (`iex_deep.reconstruct`) — the ~13 GB download is shared.

## Reconstruction internals (`app/sources/iex_deep.py`)
- Hand-rolled streaming **pcapng** + IEX-TP DEEP `struct` decoder
  (`iter_deep_messages`) — no library (file is huge + dodges package firewall).
  Buffers partial pcapng blocks across chunk boundaries.
- `_SymbolBook` keeps a price-level dict per side + tape; snapshots a frame every
  10 min (09:30–16:00) BEFORE applying the boundary message; skips empty pre-open
  frames. `Reconstructor.past_session()` stops the stream after the close so we
  don't pull the after-hours tail.
- ET offset computed once per session (constant within RTH) → cheap int math on
  ns timestamps instead of per-message tz conversion.

## Testing
- `tests/test_orderbook_replay.py` is standalone (no pytest, no network): builds
  a tiny pcapng+IEX-TP fixture to exercise the wire decoder (incl. chunk
  boundaries + symbol filter), then drives `Reconstructor` directly to assert
  payload schema, frame cadence, ladder ordering, spread, side inference, block
  events, and the thin-symbol→no-real-payload guard.
- A real end-to-end reconstruction is ~20 min (background) and was NOT run in
  CI; it's intended for the worker thread only.



====================================================================================================
FILE: .agents/memory/panel-export.md
====================================================================================================

---
name: Panel CSV/PDF export
description: How client-side quant-panel export works and why html2canvas-pro is required under Tailwind v4.
---

# Panel CSV/PDF export

Client-side export of quant panels lives in `artifacts/terminal/src/lib/panelExport.ts`
and is wired into the panel toolbar in `PanelContainer.tsx` (Download icon → CSV / PDF menu),
gated by `EXPORTABLE_PANEL_TYPES`.

## Must use html2canvas-pro, not html2canvas
**Rule:** for DOM-snapshot/PDF capture in the terminal artifact, import `html2canvas-pro`, never `html2canvas`.
**Why:** the terminal is on Tailwind v4, whose theme tokens (border, muted, etc.) resolve to
`oklch(...)`. Stock html2canvas throws "unsupported color function 'oklch'" and the export fails.
`html2canvas-pro` is a drop-in fork that parses oklch/lab/lch.
**How to apply:** PDF export = html2canvas-pro (capture element) + jsPDF (place PNG on A4, black bg).
Both are dynamically `import()`ed so they code-split out of the main bundle.

## CSV shape
`buildPanelCsv(type, data)` emits a single sectioned CSV string (header rows + blank-line
separated tables) directly from each panel's typed data — no backend involved. Add a new panel
type by writing a `*Rows` builder + a `case` and adding the type to `EXPORTABLE_PANEL_TYPES`.

## Stale shared-types gotcha
The shared data types (`PortfolioRiskData`, etc.) come from `@workspace/api-client-react`.
Its `package.json` exports point at `src/index.ts` (so Vite/runtime is always fresh), but tsc
project references consume the built `lib/api-client-react/dist/*.d.ts`. If a new file imports a
type that tsc claims "has no exported member" while existing files don't, the dist declarations
are stale — rebuild with `tsc -p lib/api-client-react/tsconfig.json`.



====================================================================================================
FILE: .agents/memory/panel-inline-refine-loading.md
====================================================================================================

---
name: In-panel control refine keeps controls mounted
description: How to refine a panel from its own controls without the global "Processing" overlay wiping the control rows.
---

# In-panel control refine loading

PanelContainer's global `renderContent()` shows a full-body "Processing" spinner whenever `refineMutation.isPending`. Any panel whose in-panel controls (strategy/range/30D-90D/ticker) call a handler backed by `refineMutation` therefore has its whole body (controls included) replaced mid-interaction.

**Rule:** route in-panel control refines through the SEPARATE `paramRefineMutation` (handler `handleRefineParamsLive`), and pass `pending={paramRefineMutation.isPending}` into the panel. The panel keeps its control rows mounted, disables them while pending (`disabled={pending}` + `disabled:opacity-50`, no double-submit), and overlays only the data/chart area with an absolute translucent `Loader2` (`pointer-events-none`).

**Why:** `renderContent`'s spinner is keyed only on `refineMutation.isPending` (and `panel.status === "loading"`). A refine does not set `panel.status` to loading — old data stays mounted — so switching to `paramRefineMutation` is enough to suppress the global overlay while the panel shows its own inline state.

**How to apply:** the canonical reference is `IntradayChartPanel` (already used `paramRefineMutation` + `pending`). Panels converted to this pattern: Backtest, CorrelationMatrix, PortfolioRisk, FactorAnalysis. Note `multi_strategy` still uses `handleRefineParams` (the global-spinner path) — convert it the same way if that ever needs the smoother behavior.



====================================================================================================
FILE: .agents/memory/panel-layout-collision.md
====================================================================================================

---
name: Panel layout collision resolution
description: Why dashboard panel overlap resolution uses a two-pass reserve-then-reflow algorithm, not single-pass greedy.
---

# Dashboard panel collision resolution

The terminal dashboard grid (12 columns, `gridAutoRows` ~120px) renders panels
at AI-assigned `{x,y,w,h}`. The AI can emit overlapping or off-grid rects, so
`resolvePanelLayouts` (in `artifacts/terminal/src/lib/layout.ts`) cleans them up
before render.

**Rule:** resolution is two-pass, both in reading order (sort by `y`, then `x`):
1. Reserve every panel that is on-grid AND non-colliding at its desired position.
2. Reflow only the leftover conflicting/off-grid panels into the first available
   top-left slot (row-major scan), without moving reserved panels.

**Why:** a single-pass greedy approach (place-or-reflow in one loop) displaced
originally-clean panels — a conflicting panel reflowed into a still-unprocessed
clean panel's spot and stole it. The task requires non-conflicting panels keep
their AI positions; only two-pass guarantees that.

**How to apply:** if you extend layout logic (e.g. resize handles, persistence),
keep the reserve-then-reflow ordering. Panels keep the same object reference when
their layout is unchanged, so don't assume the returned array is all-new.

**Responsive columns:** `resolvePanelLayouts(panels, columns = GRID_COLUMNS)` is
parameterized by effective column count — the same two-pass algorithm collapses
wide panels (`normalize` clamps `w` to `columns`) and stacks them at narrower
grids. Dashboard.tsx picks columns by viewport via `useResponsiveColumns` (1 on
phones <768px, 6 on tablets <1280px, 12 otherwise) and feeds the same count to
both the CSS `gridTemplateColumns` and the resolver — keep those two in sync.



====================================================================================================
FILE: .agents/memory/panel-resize-handles.md
====================================================================================================

---
name: Panel resize handles
description: How dashboard panels are user-resizable via drag handles in the CSS grid.
---

# Panel resize handles

Users resize dashboard panels by dragging edge/corner handles rendered in
`Dashboard.tsx` (right=width, bottom=height, corner=both). Resize commits new
`{w,h}` to `activeDashboard` via `onPanelResized` -> `handlePanelResized` in
`Terminal.tsx`; no data re-fetch. Neighbors reflow through the existing
`resolvePanelLayouts` pass on the next render.

**Why:** layout coords come from the AI/API and were previously fixed; users
wanted a flexible workspace.

**How to apply:**
- Grid metrics in the resize math MUST mirror the CSS: `gap-6` = 24px and
  `gridAutoRows` = 120px. Column pixel width is measured from the grid ref at
  drag start; if you change the grid's gap or row height, update the constants
  (`GRID_GAP`, `ROW_HEIGHT`) too or snapping drifts.
- Drag uses `setPointerCapture` + handlers on the handle element (not window).
  During drag, only the dragged panel is style-overridden and its framer
  `layout` animation is disabled (`layout={!isDragging}`) to stay crisp.
- Width clamps to `MIN_W..(GRID_COLUMNS - panel.x)` (can't move x on resize);
  height clamps to `MIN_H`. Resize only changes w/h, never x/y.
- Cross-session persistence is a SEPARATE concern (the "Save and restore
  dashboard layouts" task); resize only persists in live session state.



====================================================================================================
FILE: .agents/memory/panel-runtime-test.md
====================================================================================================

---
name: Generated-panel production runtime test
description: How the AI-generated panel production loading path is tested under vitest, and the registry-glob design that makes it possible outside a real build.
---

# Testing the generated-panel production runtime path

The production path for AI-generated panels (fetch TSX from `GET /api/generated-panels`
→ transpile with sucrase → eval → render, generic fallback on failure) lives in
`registry.ts` + `DynamicPanel.tsx`. It cannot be exercised by the dev server (dev uses
Vite HMR / `import.meta.glob`). The test for it lives in
`artifacts/terminal/src/components/terminal/panels/generated/__tests__/production-runtime.test.tsx`.

## Runner: vitest (jsdom per-file)
The terminal uses **vitest** (`vitest.config.ts`, `pnpm --filter @workspace/terminal test`).
The global vitest env is `node`; this React-rendering test opts into jsdom with a
`// @vitest-environment jsdom` docblock on line 1. The config `include` covers both
`*.test.ts` and `*.test.tsx`, and `plugins: [react()]` so app components transform the
same way they do in the real build.
**History:** an earlier attempt used Node's built-in runner because `vitest` was
firewall-blocked (HTTP 403 on the tarball). That block was later lifted upstream — vitest
is the committed standard now; do not reintroduce a parallel `node:test` runner.

## Why the runtime path is still exercised under vitest
Under vitest (which runs through Vite), `import.meta.glob('./*.tsx',{eager:true})` in
`registry.ts` DOES resolve (unlike a bare Node runtime, where the try/catch falls back to
an empty registry). The test panel type is written to disk in `beforeAll` — AFTER the test
module (and the registry it imports) has been evaluated — so it is never in the static glob
registry. `getGeneratedComponent` returns undefined for it, forcing `loadGeneratedComponent`
(fetch + sucrase + eval). This mirrors a production runtime loading a post-build panel.
**Do not** refactor the glob into a variable first — Vite only transforms the literal
`import.meta.glob(...)` call expression; the try/catch is what lets it import outside Vite.

## What the test does
Real `vite build` in `beforeAll` (needs `PORT` + `BASE_PATH` env; ~180s hook timeout) →
write a fresh panel `.tsx` into the generated dir AFTER the build → assert its marker is
absent from `dist` (proves it can only load via the runtime path) → mock `globalThis.fetch`
to return that source and render `<DynamicPanel>`, asserting the compiled component renders;
separate cases assert the generic fallback for disallowed-import / no-default-export /
broken-syntax sources. Test cleans up the temp file in `afterAll`. Test files are excluded
from the production tsconfig (run via vitest only). Registered as the `panel-runtime-test`
validation workflow in `.replit`.



====================================================================================================
FILE: .agents/memory/passthrough-panels.md
====================================================================================================

---
name: Adding new hand-written panel types (passthrough)
description: How to add a new non-generated panel type to the terminal end-to-end without touching openapi codegen, and which tsc errors are expected.
---

# Adding a new hand-written panel type (passthrough pattern)

New panel types (e.g. `company_analytics`, `analyst_report`, `scenario`) can be added
end-to-end WITHOUT touching `openapi.yaml` / generated `models.py` / running codegen.

**How the passthrough works:**
- `harness.py` only validates panel `data` against `DATA_MODELS`. A panel type NOT in
  `DATA_MODELS` has its builder dict passed through untouched; the harness still pops
  `asOf`/`source` into the envelope.
- `models.Panel.data` is `Optional[dict]`, and `DashboardSpec` therefore serializes any
  builder dict over HTTP. So the `/api/orchestrate` response carries the raw dict.
- Frontend `PanelContainer.tsx` switch-cases the new `type` and casts `panel.data as any`
  into the hand-written component.

**Wiring checklist for a new type (mirror `company_analytics`):**
1. `skills.py`: write `build_<x>` with AI + heuristic fallback, register via `_reg(...)`
   with the new `panel_type`.
2. `agent.py`: add `add_<x>` tool in `_tools()`, `_TOOL_TO_TYPE`, `_TYPE_LABELS`,
   `_system_prompt`, and `_orchestrate_heuristic` routing.
3. Frontend: new `panels/<X>Panel.tsx` + import + switch case in `PanelContainer.tsx`.

**Expected (non-blocking) tsc errors — do NOT "fix":**
`pnpm exec tsc` reports "not comparable to type 'PanelType'" errors for every
passthrough panel (and any you add) because the generated `PanelType` enum doesn't
include them. This is by design — the build uses `vite build` (esbuild, no tsc gate)
and dev uses vite, so these never block. Do not regenerate openapi to "fix" them.

**Gotcha — missing `_reg` fails silently as "Unknown panel type":** `skills.build_<x>(params)`
works when called directly, but `/api/orchestrate` dispatches by panel type through the `SKILLS`
registry. If you forget `_reg(SkillDef(... panel_type ...))`, the panel returns a CLEAN failure
(status `error`, note "could not be built: Unknown panel type") with NO traceback in logs — easy
to misread as a builder bug. Always verify the new type via orchestrate, not just the builder.

**Counterpart — EXISTING typed panels are NOT passthrough:** panel types listed in
`harness.DATA_MODELS` (e.g. `order_book`, `trade_flow`) validate via a pydantic model in
`models.py`, which SILENTLY DROPS any field not on the model. If you add new fields to
such a builder's return dict, you MUST add them to the corresponding model (often as
`Optional[...] = None`) or they vanish over `/api/orchestrate` (builder works when called
directly, but the panel arrives missing the new keys). Restart api-server after.

**Always restart `artifacts/api-server: API Server`** after backend changes — it runs
WITHOUT `--reload`.

**Opposite gotcha — adding a FIELD to an EXISTING typed panel:** types in `DATA_MODELS`
(e.g. `price_chart` → `PriceChartData`) are validated by the hand-maintained pydantic
models in `app/models.py`. A new key your builder returns is **silently stripped** from
the HTTP response if it isn't on that pydantic model — the field just shows up `None`/missing
on the client with no error. For typed panels you must add the field in THREE places in
lockstep: `app/models.py` (pydantic, the one that actually gates the response),
`lib/api-spec/openapi.yaml` + rerun `pnpm --filter @workspace/api-spec run codegen` (for the
typed TS client). The openapi/codegen alone is NOT enough; models.py is the real filter.



====================================================================================================
FILE: .agents/memory/pending-panel-autorefresh.md
====================================================================================================

---
name: Pending panel auto-refresh poll
description: How pending ("fetching live data") panels self-populate without the user asking twice.
---

# Pending panel auto-refresh poll

PanelContainer auto-refreshes any panel whose `data.pending === true` (the warm-up
envelope returned by builders like price_chart/fundamentals/order_book/trade_flow
when a ticker isn't ingested yet). A `useEffect` polls every 5s, gives up after 60s,
and stops the moment `result.data.pending` is falsy.

**How it re-fetches:** fires `useRefinePanel` with explicit `params` `{symbol[, range]}`
(deterministic structured refine — bypasses the LLM). The pending builders all accept
`symbol` (price_chart also `range`).

**Why a dedicated 3rd mutation (`pollMutation`):** `renderContent` shows the
"Processing" spinner when `refineMutation.isPending`. Polling on a separate mutation
keeps the satellite "Fetching live data" UI visible and never flips to Processing.

**Why deps are `[isPending, panel.id, sessionId]` only (primitives):** each poll calls
`onRefined`, minting a fresh `data` ref; depending on `data` would restart/starve the
timer (see debounced-recompute-deps). The loop self-schedules via setTimeout and the
cleanup cancels once isPending flips false. `onRefined` is read through a ref.

**How to apply:** new builders that emit a pending envelope just need to carry `symbol`
in the envelope and accept it as a param — no PanelContainer change needed. Fake/invalid
tickers never ingest, so they stay pending and the 60s cap ends the poll cleanly.



====================================================================================================
FILE: .agents/memory/period-returns.md
====================================================================================================

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



====================================================================================================
FILE: .agents/memory/pit-survivorship-data.md
====================================================================================================

---
name: Point-in-time & survivorship-bias-free data
description: How PIT/survivorship honesty is enforced across repo accessors, builders and panels — the "label, never impute" contract.
---

# Point-in-time (PIT) & survivorship-bias-free data

The honesty contract: historical windows resolve to the universe active *then*
(incl. later-delisted names), fundamentals are served as-reported, and wherever
PIT/delisted coverage is missing it is **clearly LABELED**, never silently
backfilled with restated/survivor data.

## Where the pieces live
- `app/data.py` `DELISTED` dict — curated real listed/delisted dates (Lehman,
  Bear, WaMu, Enron, SVB, FRCB, ATVI, TWTR, YHOO, XLNX, CELG, MTLQQ). `get_delisted`.
- `app/repo.py` PIT accessors: `listing_info` (DB→curated→unknown), `historical_universe`
  (active-in-window + merged delisted, `survivorshipSafe` true only when delisted
  names are actually carried), `historical_closes` (**real-only**: omits names with
  no genuine OHLCV, reports them under `missing` — never mock-fills),
  `fundamentals_as_of` (as-reported latest period ≤ as_of, or **None**),
  `pit_coverage`.
- `app/skills.py` builders emit a `coverage`/`pit` block: build_backtest,
  build_signal_research/scorecard/portfolio, build_data_universe, build_data_quality.
  `_augment_signal_coverage` + `_signal_window` add per-signal coverage.
- `app/models.py` — `coverage: Optional[dict]` on BacktestData/SignalResearchData/
  SignalScorecardData (Optional[dict] passes through the harness untouched).
- terminal `CoverageBadge.tsx` (shared pill strip) wired into the 4 research panels;
  DataUniversePanel + DataQualityPanel render a dedicated PIT/survivorship section.

## Key rules / gotchas
- **Never impute a delisted name.** `historical_closes` is the honesty gate; if a
  window's delisted names have no real OHLCV ingested yet, build_backtest falls back
  to a synthetic curve with `priceBasis:"synthetic"`, `pointInTime:false` and an
  explicit "NOT point-in-time safe / illustrative" note. Real delisted OHLCV + broad
  PIT-fundamentals ingest are deferred follow-ups (not yet populated by the worker).
- `survivorshipSafe` for a single active name is True (no constituents to drop), even
  when priceBasis is synthetic — the price honesty lives in priceBasis/pointInTime/notes.
- Recent windows (no curated delistings) honestly report survivor-only with a note.
- No openapi codegen for the coverage fields — panels read them via a cast
  (`(data as unknown as {coverage?: DataCoverage}).coverage`), matching the existing
  passthrough-panel convention. Terminal `tsc` shows pre-existing stale-codegen errors;
  the **vite build is the real gate** and passes.

## Verifying
- `tests/test_pit_data.py` (standalone, 44 checks) — run via
  `env -i HOME=$HOME PATH=/home/runner/workspace/.pythonlibs/bin:/usr/bin:/bin python3.11 tests/test_pit_data.py`.
- smoke: `env -i ... TERMINAL_SKIP_WORKER=1 bash scripts/smoke-api.sh` (the script's
  bare `python -m uvicorn` hits the MAX_PATH wrapper unless invoked via env -i).
- terminal: `PORT=5000 BASE_PATH=/ pnpm --filter @workspace/terminal run build`.



====================================================================================================
FILE: .agents/memory/polymarket-prediction-markets.md
====================================================================================================

---
name: Polymarket prediction-market data
description: How real Polymarket data flows into the terminal — which free APIs, their encoding quirks, and the two resolution/history traps.
---

Three passthrough panels (polymarket_markets / polymarket_market / polymarket_wallet)
serve REAL data from free, key-less Polymarket APIs via `app/sources/polymarket.py`
(routed through `_resilient`, breakers polymarket-gamma/clob/data).

**The four APIs:**
- Gamma `gamma-api.polymarket.com`: events/markets list, `public-search?q=`,
  `markets?slug=`, `markets/{id}`; `tag_slug=` filters events by category.
- CLOB `clob.polymarket.com/prices-history?market=<tokenId>`: yes-share price
  over time = implied probability. `t`=epoch sec, `p`=yes price (0..1).
- data-api `data-api.polymarket.com`: `/trades`, `/positions`, `/value` (wallet).

**Encoding quirk:** Gamma returns `prices`, `outcomes`, `clobTokenIds` as
JSON-**string**-encoded fields — `json.loads()` them before use.

**Trap 1 — market resolution:** ranking search candidates purely by volume picks
the wrong sibling in multi-outcome events ("Spain win World Cup" → highest-volume
Tunisia market). Fix: score by query-token overlap (vs question + label) FIRST,
volume only as tiebreaker. See `search_market` + `_STOPWORDS`.

**Trap 2 — price history fidelity:** CLOB rejects some ranges without an explicit
`fidelity` (e.g. interval `1m` requires `fidelity>=10`). Always send a default
sized to the window — see `_FIDELITY_BY_INTERVAL` in `fetch_price_history`.

**Honesty:** history/trades that come back empty surface as
`historyAvailable=False` / `tradesAvailable=False` — never fabricated. asOf/source
are lifted to the panel envelope by the harness (data dict shows None).

Known live test wallet: `0xbffe0ec796fa44bdb8b32908478c694a5566fe20` (has
positions + value). Wallet routing keys off a `0x...` regex on the raw query.



====================================================================================================
FILE: .agents/memory/portfolio-optimizer.md
====================================================================================================

---
name: Portfolio construction & optimization
description: Durable decisions for the optimizer pillar — real-data inputs, why solvers are home-grown, and the constraint-incompatibility traps that produce degenerate books.
---

# Portfolio Construction & Optimization

Same three-layer shape as the factor-risk-model and signal-library pillars: a
pure-numpy engine, an honest-coverage data bridge, and a passthrough skill/panel.

## Decisions worth keeping

- **No scipy in this repl.** All solvers (mean-variance, Black-Litterman, ERC risk
  parity, HRP) are home-grown numpy. Constraints are enforced by **Dykstra
  alternating projection** onto the intersection of box / sector-cap / gross / net
  sets — not a QP. **Why:** no QP library available; alternating projection is the
  simplest thing that satisfies all constraint sets at once.

- **Expected returns are factor-implied, not a separate forecast:**
  `mu = exposures @ factor_ann_returns`, reusing the risk model's covariance.
  **Why:** keeps the pillar real-data-only and consistent with the factor model;
  don't introduce an independent return model.

## Traps (cost real debugging — don't reintroduce)

- **Risk parity / HRP are inherently long-only & fully invested.** If a request
  carries shorting or market-neutral (net=0), projecting onto {w>=0, sum=0}
  collapses to an **all-zero degenerate book**. Reconcile these methods to
  long-only net=1 and *report* the override — never silently emit zeros.

- **Never silently relax a user constraint.** Two infeasibilities recur: a
  per-name cap below |net|/n, and a **gross budget below |net|** (gross = Σ|w| ≥
  |Σw| = |net| is a hard identity, so gross<|net| is impossible). Both must be
  loosened to stay solvable AND surfaced (panel/voice note + status), not hidden.
  The engine floors `gross_limit()` at |net| so projection never silently
  violates; the bridge reports the relaxation. Silently changing intent (either
  one) was a code-review reject.

- **Heuristic routing:** put the optimizer branch *before* the risk-model/risk
  branches (the phrases "risk parity"/"minimum variance" contain "risk"/"variance"),
  and only prefer explicit symbols when >=2 are given — `_extract_symbols` returns
  single-letter false positives (e.g. "A" from the word "a").

- **Big expected-return magnitudes are expected**, not a bug — factor premia ×
  tilts, annualized the same way the factor model does.



====================================================================================================
FILE: .agents/memory/portfolio-to-desk-promotion.md
====================================================================================================

---
name: Portfolio → strategy desk promotion
description: Promoting a built signal_portfolio panel into a paper-traded strategy, and the compliance/test-stub gotchas it surfaced.
---

# Promote a constructed portfolio into the strategy desk

"paper trade this portfolio" / "track this portfolio" registers the most-recent
`signal_portfolio` panel's holdings as a paper-traded strategy in the lifecycle desk.

- Detection needs BOTH a portfolio/book/holdings reference AND a track/paper/register/promote verb (in `agent.py`). A plain named-strategy command must NOT be hijacked.
- Source of holdings: the latest `signal_portfolio` panel in the session dashboard (`state.get_dashboard`). Long/short signed weights pass through verbatim.
- **Real-data honesty:** carry the portfolio's `excludedNames` + any names dropped during symbol/weight alignment onto the strategy construction (`source="signal_portfolio"`). Pre-filter symbols/weights so they stay aligned, otherwise `derive_target_weights` falls back to signal ranking instead of using the explicit book.
- If no `signal_portfolio` panel exists in the session, pass through (don't fabricate a book).

## Compliance gate is live on every paper_trade
`paper_trade` runs the pre-trade compliance precheck. A concentrated few-name book (e.g. 50/50) trips the default `maxPositionPct=15` and raises `ComplianceBlock`. Any test that builds a paper book must isolate `compliance_store` with permissive limits — see below.

## Test-fixture isolation lesson (tests/test_strategy.py)
- `compliance_store` shares the same `db` module as `strategy_store`; forcing `db_available=lambda:False` routes BOTH to in-memory. Then set `compliance_store._mem_cfg` to `_default_config()` with permissive `limits` (and restore in `finally`), or the gate refuses concentrated test books.
- **Stub close-series must be HISTORICAL (past dates ending today), not future-dated.** The promotion gate counts `trackDays` from the audited snapshot series, falling back to a bootstrap NAV reconstruction (`mark()` in strategy.py) that keeps only closes `>= inception`. A fresh book has `inception==today`; with real (historical) closes it reconstructs ~1 point → `trackDays < minDays(5)` → correctly BLOCKED. A stub that dated closes from today forward kept all points → trackDays cleared the gate and the block test silently passed-then-failed once compliance isolation let it reach the assertion. `test_rebalance.py` already uses the correct `today - n` pattern.



====================================================================================================
FILE: .agents/memory/python-api-server.md
====================================================================================================

---
name: Python backend on api-server artifact
description: How to run a Python/FastAPI service inside the shared `api-server` artifact instead of the default TS Express server.
---

The shared `api-server` artifact defaults to a TypeScript Express server. It can be
repointed to a Python (FastAPI + uvicorn) service while keeping the same `/api` path
mounting that the proxy and generated frontend client expect.

Key facts (durable, not obvious):

- **Code lives under `artifacts/api-server/app/`** as a package (`app/main.py` with
  `app = FastAPI()`), served under the `/api` prefix via an `APIRouter(prefix="/api")`.
- **uvicorn must use `--app-dir artifacts/api-server`** so that `app.main:app` resolves.
  The directory name `api-server` contains a hyphen, so you cannot import it as
  `artifacts.api-server.app.main`; `--app-dir` adds the artifact dir to sys.path instead.
- **Dev run** is a shell string in `artifact.toml`, so `$PORT` is shell-expanded:
  `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir artifacts/api-server --reload`.
  **Production run** is an args array (no shell), so set `PORT` via `[services.production.run.env]`
  and hardcode `--port 8080`. No build step is needed (remove the TS build block).
- **Restart the workflow after swapping artifact.toml.** `verifyAndReplaceArtifactToml`
  updates config but the already-running process keeps the OLD run command until the
  workflow is restarted. Symptom: health/endpoints still answer like the previous server
  (e.g. Express `Cannot GET /api/...` 404s) after the swap.
- **Why:** keeping the service under `/api` on localPort 8080 means the existing proxy
  routing and the orval-generated React Query client (which call `/api/...`) work unchanged
  — no frontend or proxy edits required when switching the server language.
- AI access in Python: point the `openai` SDK at the Replit proxy via
  `OpenAI(base_url=os.environ["AI_INTEGRATIONS_OPENAI_BASE_URL"], api_key=os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"])`.
  Model `gpt-5.4`; use `max_completion_tokens` (NOT `max_tokens`); do not set `temperature`.

## Declared deps must be installed into the running env
The root `pyproject.toml` lists the api-server's Python deps (fastapi, feedparser,
httpx, openai, psycopg[binary], psycopg-pool, pydantic, uvicorn, yfinance). After a
rebase/merge that adds a new source module (e.g. `app/sources/*.py` importing
`yfinance`/`feedparser`), the package may be declared but NOT installed in the
`.pythonlibs` env, so uvicorn crashes at import with `ModuleNotFoundError` and the
frontend "just keeps loading" (no data). Fix: `uv sync --frozen` (installs the full
declared/locked set into `.pythonlibs` since `UV_PROJECT_ENVIRONMENT` points there),
then restart the `artifacts/api-server: API Server` workflow. Install the full set at
once — errors surface one module at a time, don't chase them individually.

**Durable fix for the recurrence:** isolated-task `uv` installs do NOT survive merge
to main. `scripts/post-merge.sh` is what runs after every merge — it now includes
`uv sync --frozen` (alongside `pnpm install` / `db push`). If you ever add a Python
dep, update `pyproject.toml` AND `uv.lock` together or `--frozen` will fail post-merge.



====================================================================================================
FILE: .agents/memory/python-subprocess-maxpath.md
====================================================================================================

---
name: Running Python scripts interactively (MAX_PATH wrapper error)
description: Why ad-hoc `python3 foo.py` fails in this repl and how to actually run a Python snippet against the api-server app.
---

Running Python interactively from bash (e.g. `python3 script.py`, `uv run python …`)
often fails immediately with a Replit run-wrapper error, BEFORE any of your code runs:

```
run process: run_parent
Caused by:
  0: handle_syscall ...
  1: get_target_path
  2: path exceeds MAX_PATH
```

This is NOT your code — the uvicorn workflow runs Python fine. The cause is an
over-long environment variable tripping the syscall interceptor's path check.

**Fix:** invoke the real interpreter with a minimal env, preserving only what's needed:

```
env -i PATH=/usr/bin:/bin HOME=/home/runner \
  UV_PROJECT_ENVIRONMENT=/home/runner/workspace/.pythonlibs \
  .pythonlibs/bin/python3.11 /tmp/script.py
```

To import the api-server package, add its dir to sys.path (the dir name has a hyphen
so it can't be imported as a module): `sys.path.insert(0, "artifacts/api-server")`
then `from app import agent, ai`.

**How to apply:** for HTTP-level checks just curl `https://$REPLIT_DEV_DOMAIN/api/...`
(the proxy needs https). For unit-level checks of agent logic (e.g. forcing
`ai.ai_available = lambda: False` to test fallbacks), use the `env -i` interpreter call.



====================================================================================================
FILE: .agents/memory/python-test-conventions.md
====================================================================================================

---
name: api-server Python test conventions
description: How tests are written/run for the api-server Python backend (no pytest installed; self-running standalone files).
---

The `artifacts/api-server/tests/*.py` suites are **standalone**, not pytest-driven
(pytest is NOT installed in this env). Each file ends with a `_run_all()` that
collects `test_*` globals and runs them, guarded by `if __name__ == "__main__"`.
Run one with `python artifacts/api-server/tests/test_X.py`. They also work under
pytest if it ever gets added, so keep both entry points.

**Import shim:** every test prepends the artifact dir to `sys.path`
(`_API_SERVER_DIR = .../artifacts/api-server`) so `from app import ...` resolves
regardless of cwd. The package can't be imported as `artifacts.api-server...`
(hyphen), so this shim is required.

**Mocking the data layer (no real Postgres needed):**
- `repo` does `from . import db`, so patch the **shared `db` module object**
  (`db.db_available`, `db.query`, `db.query_one`, `db.execute`, `db.execute_many`)
  and every repo accessor follows. `available=False` forces the mock-fallback
  path and the query helpers must never be called; `available=True` + fake row
  dicts drives the "live" path; make the helpers raise to test DB-error fallback.
- Source adapters: patch `module.httpx.Client` with a stub returning a fake resp
  (`.json()` for prices, `.content` bytes for news + real `feedparser.parse`),
  and `fundamentals.yf.Ticker` with a fake exposing `.info`. This tests real
  parsing against captured Yahoo/Google payloads with zero network.
- Always save/restore the patched attr in a `try/finally` (a contextmanager is
  cleanest) so one test's stub never leaks into the next.

**Why:** the "no empty panels" guarantee (live data when DB populated, curated
`data.py` mock otherwise) plus the `asOf`/`source` freshness fields were only
verified manually before; `tests/test_datalayer.py` pins live-vs-mock for every
repo accessor and the adapter parsing/unit-quirks.



====================================================================================================
FILE: .agents/memory/refine-explicit-params.md
====================================================================================================

---
name: Refine with explicit params (deterministic in-panel controls)
description: How interactive in-panel controls re-fetch a panel deterministically, bypassing the LLM/heuristic refine path.
---

# Deterministic panel re-fetch via explicit params

`RefineRequest` carries an optional `params` object alongside the free-text
`instruction`. When `params` is present, `agent.refine` applies it directly to
`harness.run_skill` and skips `_refine_params` (LLM + heuristic). This is the
mechanism for interactive in-panel controls (e.g. intraday chart
resolution/window pickers) that must re-fetch exactly what the user clicked.

**Why:** the only prior way to change a panel was the LLM/heuristic refine path,
which is slow and non-deterministic — unacceptable for a button click. Explicit
params make UI controls fast and exact.

**How to apply:**
- Always include `symbol` (and any other required skill keys) in `params` —
  skills default missing keys (e.g. `build_intraday_chart` defaults to NVDA), so
  omitting `symbol` silently switches the ticker.
- Frontend: pass a dedicated `useRefinePanel()` mutation instance to the
  interactive panel (separate from the text-refine one) so its `isPending`
  drives an in-panel spinner instead of `PanelContainer`'s global "Processing"
  loader that would unmount the controls mid-fetch.
- Invalid skill param combos should still return the skill's clean unavailable
  state; keep the controls rendered in that state so the user can recover.
- Editing `RefineRequest` requires editing `lib/api-spec/openapi.yaml` +
  `app/models.py`, then `pnpm --filter @workspace/api-spec run codegen`.

**Testing note:** orchestration routing is stochastic — the same query may yield
`price_chart` instead of `intraday_chart`. UI tests that need a specific panel
type must retry the command until the distinguishing UI appears.



====================================================================================================
FILE: .agents/memory/replit-config-tooling-traps.md
====================================================================================================

---
name: Replit config tooling traps (.replit runButton, package firewall)
description: Two non-obvious environment traps — validation tooling clobbers the Project run button, and the package firewall blocks installing a JS test runner.
---

# Validation tooling clobbers `.replit` runButton="Project"

`setValidationCommand` materializes a concrete `[[workflows.workflow]] name="Project" mode="parallel"`
whose only task runs the validation command. In a multi-artifact workspace the Run button ("Project")
is normally **synthesized by the platform** from the artifact workflows (there are NO `[[workflows.workflow]]`
blocks in `.replit`; just `[workflows]` + `runButton = "Project"`). Materializing a concrete Project block
**hijacks** the Run button to run only the validation, not the app.

`clearValidationCommand` then **over-removes**: it deletes the Project block AND the `runButton = "Project"`
line (which it did not add), leaving `[workflows]` empty.

**The bare `runButton = "Project"` line cannot be restored via available tooling:**
- Direct edits to `.replit` are blocked ("owned by a different tool").
- `verifyAndReplaceArtifactToml` (artifact re-sync) does NOT rewrite it.
- `restartWorkflow` on an artifact does NOT rewrite it.
- `configureWorkflow` has no runButton param; setting a validation again only re-adds the hijack block.
- Only platform reconciliation on merge (or a manual `.replit` edit) restores it.

**Why:** the run button for multi-artifact repls is platform-synthesized; the validation system assumes a
single-app layout and rewrites the Project workflow.
**How to apply:** avoid `setValidationCommand`/`clearValidationCommand` in multi-artifact repls. To gate code
quality, run tests directly (e.g. `python tests/test_x.py`) rather than registering a validation workflow.

# Package firewall blocks installing `vitest`

`pnpm --filter <pkg> add -D vitest` fails with `ERR_PNPM_FETCH_403` from `package-firewall.replit.local`
("No authorization header"). Per the package-management skill, a 403 from the firewall is a security block —
**do not retry**. Notably `jsdom` and `@testing-library/*` install fine; only `vitest`'s tarball is blocked.

**Consequence:** a committed JS/React test runner cannot be added here. The terminal artifact's components
also rely on Vite-only features (`import.meta.glob`, the `@/` alias, runtime TSX), so a non-vitest runner
(node:test + tsx) is impractical. Frontend end-to-end verification must go through the sanctioned `runTest`
tool (Playwright-based, against the running dev server) rather than a committed spec.
**How to apply:** for frontend flow verification, lean on committed **backend** harness tests for the
deterministic pipeline + `runTest` for the live UI. Don't burn time trying to install vitest/playwright.



====================================================================================================
FILE: .agents/memory/responsive-layout.md
====================================================================================================

---
name: Terminal responsive layout
description: How the terminal dashboard + console adapt across phone/tablet/desktop breakpoints.
---

# Terminal responsive layout

Three-tier breakpoint via `useBreakpoint()` in `hooks/use-mobile.tsx`: mobile <768, tablet <1024, desktop ≥1024.

**Dashboard grid** (`Dashboard.tsx`):
- desktop — full 12-col grid honoring the AI's explicit `panel.layout.x/y` placement.
- tablet — 6-col `grid-auto-flow: row dense`; AI x/y is DROPPED (it assumes 12 cols), panels flow in reading order with halved column spans (`ceil(w/2)`, clamped 2..6). Honoring x/y on fewer columns overflows, so flow instead.
- mobile — single-column flex stack; full width, height = `max(2, h) * 110px`.

**Console** (`Terminal.tsx`):
- desktop — the fixed collapsible 400px `<aside>` sidebar.
- mobile + tablet (non-desktop) — a slide-up full-screen drawer opened from a floating "Console" button; `ChatPanel` gets an `onClose` prop that renders the X in its header. Submitting a command auto-closes the drawer so the user watches the dashboard compose.

**Why:** original redesign was desktop-only (fixed 12-col grid + 400px aside) and overflowed / left phones with no way to issue commands.

**How to apply:** when adding panel layout logic, remember tablet/mobile ignore AI x/y. New header controls should collapse labels under `sm:` (icon-only on phones).



====================================================================================================
FILE: .agents/memory/risk-monitor-pillar.md
====================================================================================================

---
name: Risk Management & Monitoring pillar
description: How the risk_monitor panel is built — book exposures, limits framework, historical crisis replay, hypothetical shock stress.
---

# Risk Monitor pillar (risk_monitor panel)

A risk-desk panel distinct from the factor risk model (decomposition/MCTR) and from scenario (narrative what-if). Three concerns: live exposures + limits, historical crisis replay, hypothetical shocks.

## Layering
- `app/engine/stress.py` — pure numpy, no IO: `factor_shock_pnl` (Σ exposure·shock), `asset_shock_pnl` (Σ weight·shock), `replay_window` (book P&L + drawdown over a real return matrix, returns covered/missing). Reuses `stats.max_drawdown`.
- `app/sources/prices.py::fetch_daily_closes(symbol, start, end)` — Yahoo chart with period1/period2 UNIX seconds → `{iso_date: close}`. This is how crisis windows (2008/2015/2018/2020/2022) get REAL returns; names that didn't trade then come back empty and are flagged missing (e.g. META has no 2008 data), never imputed.
- `app/skills.py::build_risk_monitor` — assembles the book via `_resolve_book` (signed NAV-fraction weights, negative = short, NO renorm so leverage is preserved), exposures, VaR/CVaR from real returns, factor exposures+MCTR via `decompose_portfolio`, limits, and both stress blocks. Registered as SkillDef "risk-monitor" / panel_type "risk_monitor".

## Limits framework
`DEFAULT_RISK_LIMITS` keys: maxGross, maxNet, maxPosition, maxSector, maxFactor (multiples/fractions) + varLimit (daily VaR fraction). Each limit emits status ok/warn/breach by utilization; `inLimit` is false if any breach. Overridable via the `limits` tool param. Each emitted limit row carries a `key` (the config key) so the UI can map a row back to the config.

## Inline limit editing (refine path)
The panel edits limits live via the existing `/refine` flow, NOT a new endpoint. Key constraint: refine REBUILDS the panel from params, and `positions` is truncated to [:14], so the book can't be reconstructed from displayed data. Fix: `build_risk_monitor` stores an internal `_refine` block in the data dict (full symbols/weights/nav/portfolio_name + current limits + factor/asset shocks). `agent._refine_risk_monitor` runs deterministically BEFORE the LLM path: it parses limit edits (JSON `{"limits":{...}}` or `key=value`) and merges them onto `_refine`'s stored book+limits so a limit edit never resets the book and shocks survive. Non-limit instructions return None → fall through to the normal LLM/heuristic refine. Frontend sends `JSON.stringify({limits:{...}})`; ratio limits edit as the multiple, exp/pct edit as a percent (÷100 to config).

## Why pure-numpy engine separate from skills
Same pattern as factor-risk-model and backtest engine: engine stays IO-free and unit-testable (`tests/test_stress.py`, run directly via `python tests/test_stress.py` — pytest is NOT installed), data assembly lives in skills.

## Refine resets the book (gotcha) + custom shock builder
Panels store NO original params — `agent.refine` rebuilds from only the new params, so a naive risk_monitor refine resets to the default NVDA book. The custom shock builder works around this: the frontend (`RiskMonitorPanel.tsx onShock`) emits a CANONICAL instruction ("Custom shock: factor|asset|market <name> <pct>%"), parsed deterministically in `agent.py` (`_parse_shock` + `_risk_monitor_shock_params`, dispatched BEFORE the LLM in `refine`), which reconstructs symbols/weights/nav/name from `panel.data.positions`+`nav`+`bookName` and merges the shock → `build_risk_monitor` returns the `customStress` slot (already existed, was just never rendered). Title preserved only on this shock path (passing `title` globally would regress other panels' refine, e.g. chart ticker swap). Caveat: positions are capped at 14 in panel data, so books >14 names lose the tail on a shock-refine.

## Agent/voice wiring
Passthrough panel (no openapi codegen — Panel.data is a dict; frontend `RiskMonitorPanel.tsx` declares its own interface). Wired in agent.py: tool `add_risk_monitor`, `_TOOL_TO_TYPE`, `_TYPE_LABELS`, system-prompt routing, heuristic `wants_riskmonitor` (routed BEFORE wants_scenario because they share "stress test"/"shock" keywords), and `_apply_dashboard_scope` pulls on-screen symbols when none given. Voice rides the shared orchestrate path automatically.



====================================================================================================
FILE: .agents/memory/role-permissions.md
====================================================================================================

---
name: Role-based permissions enforcement
description: How sensitive-action authorization works — single authoritative matrix, server-enforced via a dependency, UI gated for convenience only.
---

# Role-based permissions

The permission matrix lives in ONE authoritative place: `app/permissions.py`.
- `ROLE_RANK`: read-only(0) < analyst(1) < trader(2) < admin(3).
- `ACTIONS`: maps `action_key -> (min_role, label)`.
- Helpers `can/meets/min_role_for/label_for/allowed_actions/denial_message` all
  **fail closed** — unknown role or unknown action returns False / not-allowed.

**Why a single matrix:** the task required defining permissions in exactly one
place so server enforcement and UI gating can never drift.

## Server is authoritative
`main.py` has a `require_permission(action)` dependency factory. Sensitive routes
declare `dependencies=[Depends(require_permission("<action>"))]`. It re-uses
`require_identity` (FastAPI caches it per-request, so the session resolves once)
and raises 403 with `permissions.denial_message(...)` on violation — even for
direct/hand-crafted API calls that bypass the UI.

## Tier assignments (judgment calls baked into ACTIONS)
- analyst: dashboard.save/delete, watchlist.edit, dcf.save, alert.manage
- trader: + strategy.manage, strategy.trade, template.use
- admin: + compliance.config, feature.build

`feature.build` is admin-only — a deliberate choice (self-building features mutate
server code at runtime), not spelled out in the task's role tiers.

## Client surface
`AuthIdentity` now carries `permissions: string[]` (the caller's allowed action
keys), populated in `Identity.to_payload` AND the manual signup/login dict returns
(all three paths). Frontend `useAuth()` exposes `can(action)` from
`identity.permissions`; UI hides/disables affordances with tooltips. **UI gating is
convenience only** — never the security boundary.

**How to apply:** to gate a new sensitive route, add the action to
`permissions.ACTIONS` (server + client both read it), attach
`require_permission(...)` to the route, and gate the UI control with `can(...)`.
The smoke script (`scripts/smoke-api.sh`) now signs up first because the business
API is session-protected.



====================================================================================================
FILE: .agents/memory/saved-dashboards.md
====================================================================================================

---
name: Saved dashboard layouts (persistence)
description: How named dashboard layouts are saved/restored across sessions in the terminal.
---

# Saved dashboard layouts

Users save the on-screen dashboard under a name and restore it later.

- **Store**: `app/dashboard_store.py` — DB-first (`CREATE TABLE IF NOT EXISTS
  saved_dashboards`, runtime-created like `strategy_store`, NO drizzle push) +
  in-mem dict fallback. `panels` is a jsonb column holding the FULL panel list
  (panels carry all rendered data inline, so restore recomputes nothing).
- **Save dedups by name** (case-insensitive): reusing a name overwrites that
  layout's panels/summary, so the saved list never fills with duplicates.
- **Endpoints** (`main.py`): GET/POST `/dashboards`, GET/DELETE
  `/dashboards/{id}`. Restore mints a FRESH session id and loads panels into
  `state.set_dashboard(sid, panels)` so the user can keep refining from there;
  returns a normal `DashboardSpec` with `intent:"build"`.
- **Save payload comes from the CLIENT** (`SaveDashboardRequest{name, summary,
  panels}`), not from server session memory — `activeDashboard` on screen is the
  source of truth and is decoupled from the in-memory session store.
- **Panel.status enum is `ok|loading|error`** (NOT "ready") — a save will 422 if
  you send "ready".
- **Frontend**: `SavedDashboardsModal.tsx` (header "Dashboards" button in
  `Terminal.tsx`). `useListSavedDashboards()` is generated as a react-query hook
  whose options require `queryKey`; to fetch on open, call `list.refetch()` in a
  `useEffect([open])` rather than passing `{query:{enabled}}` (that fails tsc).



====================================================================================================
FILE: .agents/memory/security-hardening.md
====================================================================================================

---
name: API security hardening
description: Where the api-server's institutional security controls live and the non-obvious constraints around them.
---

# API security hardening (api-server)

Central module: `app/security.py` — `allowed_origins()` (CORS allow-list from
REPLIT_DOMAINS/REPLIT_DEV_DOMAIN, **never `*`** so `allow_credentials=True` is
safe), `SecurityHeadersMiddleware`, `BodySizeLimitMiddleware` (16MB→413),
sliding-window `rate_limit(bucket,limit,window)` dependency. Wired in `main.py`.
Per-firm AI code-execution kill-switch: `app/firm_settings.py` (DB table +
in-mem fallback, default on). Threat model: `artifacts/api-server/SECURITY.md`.

**Rate limiter auto-disables under tests** via `PYTEST_CURRENT_TEST` or
`TERMINAL_RATELIMIT_DISABLED=1` — a combined pytest session hammers auth from one
synthetic IP and would otherwise 429. Standalone single-file runs stay under
limits. Unit-test the core through `security._check` (bypasses the disable),
integration through the dependency.

**Code-execution containment is structural, not heuristic.** `code_guard.py`
AST allow-list excludes `os`, networking, `subprocess`, `app.*`, DB drivers, and
all dynamic-exec — so generated code *cannot* read env secrets or reach the DB /
other firms. Endpoints (`/feature-request`, `DELETE /features/{type}`) gate on
`require_codegen_enabled` → `require_role("admin")` + firm toggle. Validated
features run **in-process** (no restart), so the guard + isolated validation
subprocess are the boundary.

## SAST/semgrep nosemgrep gotchas (the part that bit me)
- `runSastScan` reads the **working tree** (line numbers move with your edits),
  but `# nosemgrep` is only honored **on the same line as the match** — a comment
  on the preceding line does NOT suppress.
- `# nosemgrep: <text>` parses everything after the colon as a **comma-separated
  list of rule-ids**; free-text justification there silently fails to suppress.
  Use **bare `# nosemgrep`** (suppresses all rules on that line) and put the
  reason in a normal comment nearby.
- Confirmed false positives in this repo: gitleaks `generic-api-key` fires on
  plain numeric constants like `DEFAULT_CAPITAL = 1_000_000.0` (underscore
  grouping looks high-entropy). All real secrets come from `os.environ`.

## XML XXE
External XML (SEC EDGAR Form 4/13F in `app/sources/{edgar,thirteenf}.py`) is
parsed with **`defusedxml.ElementTree`**, not stdlib `xml.etree` (semgrep
`use-defused-xml` HIGH). `defusedxml` is a declared dependency.

**Why:** Task #345 institutional security pass. Scans must come back 0
critical/0 high; remaining MEDIUMs are non-crypto MD5/SHA1 cache keys, accepted
in SECURITY.md.



====================================================================================================
FILE: .agents/memory/self-building-features.md
====================================================================================================

---
name: Self-building feature pipeline (Build Feature)
description: How AI-generated skills+panels are added at runtime with no server restart, and the constraints that make it safe.
---

The terminal can author NEW capabilities from a plain-language description: AI generates a
Python skill module + a React panel, validates, writes them, and registers in-process — no restart.

## Why no `--reload` on api-server
uvicorn `--reload` watches the workspace cwd, so writing any generated `.py`/`.tsx` triggers a
restart that wipes in-memory sessions (`state.py`). The dev run was changed (via the artifacts
skill `verifyAndReplaceArtifactToml`, NOT a direct edit) to drop `--reload`. New skills become
live via in-process `dynamic_skills.load_generated_skills()` instead. After any toml swap you
MUST restart the workflow for it to take effect.

## Backend contract (additive-only, never touch core files)
- Generated skills live in `app/skills_generated/<panel_type>.py`. Each exports
  `SKILL_DEFINITION` (id, name, panel_type, description, default_title, subskills,
  invoke_phrases, parameters) + `build(params)->dict` (stdlib only, must work with `{}`).
- `dynamic_skills.py` scans/imports/registers them into `skills.SKILLS` (a `SkillDef`).
- `harness.run_skill`: `DATA_MODELS.get(panel_type)` — when None (dynamic), pass the builder's
  dict through untouched (no pydantic). `models.Panel.type`/`Skill.panelType` are plain `str`
  and `Panel.data` is `dict` so dynamic types serialize. **Safe because frontend TS types come
  from hand-written `lib/api-spec/openapi.yaml`, NOT the Python pydantic models.**
- `agent.py`: `_dynamic_tools()` appended to LLM tools; `_type_of_tool()` resolves `add_<type>`
  for both built-in (`_TOOL_TO_TYPE`) and dynamic; heuristic fallback matches `invoke_phrases`;
  refine uses `_all_tools()`/`_type_of_tool` (old code KeyError'd on dynamic types).

## Clean-failure guarantee
`feature_builder.py` validates Python in an ISOLATED subprocess (ast import + `build({})` returns
JSON-serializable dict) and checks tsx has a default export BEFORE writing anything. Writes py
first, registers in-process, rolls back (deletes py) if registration throws, then writes tsx.
A failure leaves zero partial files.

## Security guard (code_guard.py)
- `app/code_guard.py` `validate_python_source(code)` is an AST allow-list audit run BEFORE any
  execution (subprocess or in-process). Allows stdlib-only roots (math/random/datetime/json/…);
  rejects all other imports, eval/exec/compile/__import__/open/getattr/setattr, dunder attr/name
  access (blocks `().__class__.__subclasses__()` escapes), relative imports. Raises `CodeGuardError`.
- Called in `feature_builder.stream_feature_request` (before `_validate_python`) AND in
  `dynamic_skills._import_module` (so startup-loaded on-disk files are re-audited before exec).
- `_validate_python` subprocess is sandboxed: `-I` isolated mode, private temp cwd, minimal env
  (no inherited secrets, no PYTHONPATH), `preexec_fn` does setsid + RLIMIT_CPU/AS/FSIZE, 10s timeout.
- **RLIMIT_AS gotcha:** `.pythonlibs/bin/python` is a Go-shim launcher that reserves a large
  virtual mapping; AS<~1GB makes it die with "failed to reserve page summary memory". Use 2GB.
- `_validate_tsx` also blocks dangerouslySetInnerHTML/eval/fetch/import()/localStorage and any
  import whose source != "react".
- Test: `tests/test_code_guard.py` (no pytest needed; `python tests/test_code_guard.py`).

## Frontend dynamic rendering (two-path: dev glob + prod runtime compile)
- `panels/generated/registry.ts` has BOTH: (1) static Vite `import.meta.glob('./*.tsx',{eager})`
  keyed by filename=panel_type (dev HMR + panels bundled at build time); (2) a RUNTIME path —
  `loadGeneratedComponent(type)` fetches source from `GET /api/generated-panels`, transpiles TSX
  in-browser with **sucrase** (`transforms: typescript,jsx,imports`), evals via `new Function`
  with a require shim that only allows `"react"`, caches the component. Needed because a built/
  deployed app has no HMR and can't bundle a `.tsx` written after build.
- Endpoint `GET /api/generated-panels` (main.py) reads PANEL_DIR `*.tsx`, EXCLUDES infra files
  `DynamicPanel.tsx`/`GeneratedPanel.tsx` and `_`-prefixed. Returns `{panels:[{panelType,source}]}`.
- `DynamicPanel.tsx` `useGeneratedComponent` hook: static component used immediately, else async
  runtime-load; generic `GeneratedPanel.tsx` shown while loading / on any failure; whole thing in
  an ErrorBoundary so a bad generated component can't crash the dashboard.
- **Why:** generated tsx contract = only `import React from "react"` + default export, so the
  require shim + sucrase imports-transform interop (`_interopRequireDefault`) is sufficient.
- Endpoint `POST /api/feature-request` is SSE (StreamingResponse over a sync generator) with
  stages planning→generating_skill→generating_panel→activating→done|error. `FeatureRequestModal`
  reads it via `fetch` + `ReadableStream` (relative `/api/...`, proxy-routed; no base URL set).
- **Planning call heartbeat:** the planning LLM call authors BOTH files at once and takes ~45-50s
  (so the 30s default `CHAT_TIMEOUT` always killed it — fixed by passing `ai.FEATURE_BUILD_TIMEOUT`
  =55s). To avoid the long blocking call tripping the proxy, `stream_feature_request` runs `_call_ai`
  on a worker thread and `yield`s an SSE comment heartbeat (`: keepalive\n\n`, ignored by the
  frontend parser which only acts on `data:` lines) every 5s while it runs; on completion it re-raises
  any worker error so the existing outer except handlers still produce the clean error + zero partial
  files.

## Provenance manifest (debuggability + feature management)
- `dynamic_skills.py` owns `manifest.json` in `skills_generated/`: `read_manifest()` (resilient —
  missing/corrupt/non-list → `[]`, never raises), `record_feature(panel_type,name,description,
  invoke_example)` (appends, replaces same-panel_type, atomic temp+os.replace), `remove_manifest_entry`
  (drops entry on delete). All best-effort: swallow+log errors. Entry keys: panel_type, name,
  description (ORIGINAL user prompt), invoke_example, created_at (ISO).
- **The manifest is provenance ONLY — the loader scans `*.py` on disk and never reads it, so a bad
  manifest can't block skill loading.** `feature_builder` calls `record_feature` AFTER both files
  write (never aborts activation); `remove_feature` calls `remove_manifest_entry`.
- **Feature-management UI is `/api/features` (list) + `DELETE /api/features/{panel_type}`** (main.py),
  served by `feature_builder.list_features()`/`remove_feature()`. `list_features` returns camelCase
  (panelType,name,description,invokeExample,createdAt) and PREFERS manifest data (original prompt +
  true created_at), falling back to SKILL_DEFINITION + .py mtime for pre-manifest features. The
  `FeatureRequestModal` build/manage view consumes it. (An earlier `/api/generated-features` +
  "Features you've built" list was folded into this richer management UI during a rebase.)

## Abuse throttling (resource/cost guard)
- `feature_builder.stream_feature_request` enforces a per-process limiter via
  `_try_acquire_build_slot()`/`_release_build_slot()` (threading.Lock — SSE generator runs in a
  threadpool, so requests race). Concurrency cap `_MAX_CONCURRENT_BUILDS=1` + rolling-window rate
  `_RATE_MAX_IN_WINDOW=5` per `_RATE_WINDOW_SECONDS=60`. Acquire happens AFTER the
  description/ai_available checks; rejection is emitted as a `{"stage":"error"}` SSE event (NOT
  HTTP 429, since the response is already streaming). Slot is freed in a `finally` (also fires on
  client disconnect via GeneratorExit). Single-at-a-time use is unaffected.



====================================================================================================
FILE: .agents/memory/signal-library.md
====================================================================================================

---
name: Alpha signal library & eval
description: Cross-sectional alpha signal research desk (IC, decay, turnover, quantile spread) — design contract and dispatch rules.
---

# Alpha signal library (signal_research + signal_scorecard)

Pure-numpy cross-sectional signal engine in `app/engine/signals.py`: signals
momentum, short_reversal, low_volatility, value, quality. Eval math = rank IC,
IC decay across horizons, turnover, quantile/decile long-short spread equity curve.

**Real data only:** names/fields that are missing are EXCLUDED and reported in a
coverage footer — never imputed. value uses fval=1/peRatio (pe>0 else excluded
"missing P/E"); quality uses fval=netMargin (None/0.0 excluded).

**Builders return only the panel `data` payload**, not a full Panel. The agent's
`add()` helper / harness wraps it with id/type/title/layout/status. To validate
the route's `response_model=DashboardSpec` offline, get panels from
`agent._orchestrate_heuristic(q)` and wrap in `models.DashboardSpec(...)` — do NOT
feed builder output straight into DashboardSpec.

**Heuristic dispatch (research vs scorecard) is keyword-fragile.** Key trap: the
metric phrase "rank IC" contains "rank", so a bare "rank"/"ranking" compare-intent
falsely routes "momentum signal research" → scorecard. Rule that works:
- scorecard = explicit scorecard phrases, OR compare-words (compare/versus/vs) with
  ≥2 named signals or any signal/alpha mention, OR signal-mention + best/which/leaderboard/ranking AND "signal research" not in query.
- research = "signal research" in query, OR metric kw (rank ic, ic decay, predict returns, cross-sectional, …), OR signal/alpha mention + ≥1 named signal.
Signal dispatch is placed BEFORE wants_factor (factor matches "alpha" too).

**Why:** verifying via curl/$REPLIT_DEV_DOMAIN and FastAPI TestClient both failed —
curl hit proxy path routing, TestClient invoked the real LLM path and hung past the
proxy window. Offline verification path: engine tests (`python tests/test_engine.py`,
no pytest), builder smoke test on live data, and DashboardSpec serialization of
heuristic panels.



====================================================================================================
FILE: .agents/memory/signal-portfolio.md
====================================================================================================

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



====================================================================================================
FILE: .agents/memory/source-resilience.md
====================================================================================================

---
name: Upstream source resilience (retry + circuit breaker)
description: How the key-less market-data sources back off under Yahoo/yfinance throttling.
---

All upstream fetches in `app/sources/` route through `_resilient.py`, which adds
retry-with-backoff + a per-source circuit breaker on top of the raw httpx/yfinance
calls. Two entry points:

- `request(source, url, ...)` — for httpx GET sources (chart endpoint, RSS).
  Throttle is detected by **status code** (429/403/5xx). Non-throttle HTTP errors
  (e.g. 404) propagate immediately, no retry, no breaker trip.
- `guard(source, fn, *args)` — for yfinance (does its own HTTP). Throttle is
  inferred from the **exception text/type** (`_looks_throttled`). Non-throttle
  exceptions (e.g. ValueError "no fundamentals for X") propagate immediately so
  one genuinely-empty symbol never cools down the whole source.

**Breaker keys (independent cooldowns):** `yahoo-chart` (all price/intraday/daily
fetches share it — same host), `yahoo-rss`, `google-news`, `yfinance`.

**Why these design choices:**
- One increment toward the breaker threshold per *user-facing call*, not per retry
  attempt (incremented once at the bottom in `_open_and_raise`). Threshold 3 ⇒
  3 throttled calls before the breaker opens.
- Cooldown doubles on each successive re-open (30s → … → 300s cap); any clean
  success fully resets (`_consecutive`, `_open_until`, `_opens`).
- Breaker is `threading.Lock`-guarded because the worker drives every call via
  `asyncio.to_thread` (multiple threads touch one breaker).

**Logging contract:** throttle/network-retry events log on `terminal.sources.throttle`
(distinct from hard failures, which surface on callers' own loggers). When the
breaker is open, callers raise `CircuitOpenError`; the worker logs those at DEBUG
(`"... ingest skipped ..."`) so a cooldown isn't mistaken for a failure. Exhausted
retries raise `ThrottleError`. Both subclass `Exception`, so existing best-effort
callers (worker loops, repo query-time fetch, skills intraday) keep falling back.



====================================================================================================
FILE: .agents/memory/sovereign-curve-compare.md
====================================================================================================

---
name: Sovereign curve comparison panel
description: Why the multi-curve compare panel adds a per-tenor "twist" and how cross-currency curves share one spot helper.
---

The `sovereign_compare` panel overlays 2–4 sovereign curves (US/UK/DE/JP) and
shows cross-currency 2Y/10Y/30Y spreads in the summary strip.

**Decision: each sovereign curve = US base + parallel `shift` + a per-tenor `twist`
(pivoting around 5Y), shared via `_region_spot(region, i)` in `skills.py`.**
**Why:** the original yield-curve mock used a pure parallel `shift` per region. Under
a pure parallel shift, the 2Y/10Y/30Y cross-market spreads are all identical — which
looks broken for a panel whose whole point is the spread term structure. The `twist`
gives each issuer a distinct slope so spreads vary realistically by tenor.
**How to apply:** `_SOVEREIGN_META` (skills.py) holds `shift`/`twist`/`currency`/`color`
per region; `build_yield_curve` AND `build_sovereign_compare` both go through
`_region_spot` so the single-curve and overlay panels stay consistent. US has
twist=0 so its curve is unchanged from before.

**Routing:** the heuristic `wants_sovereign_compare` must be checked BEFORE
`wants_yield_curve` in `_orchestrate_heuristic` (agent.py) — a "compare US vs German
curve" query would otherwise fall into the single-curve branch. Region detection
(`_detect_sovereign_regions`) keys off space-padded keywords (e.g. " us ", "bund",
"gilt", "jgb") to avoid matching substrings inside other words.

Data shape: `points` flatten each region's spot onto the row keyed by region code
(`{"tenor":"10Y","US":4.52,"DE":3.11}`) so recharts renders one `<Line>` per region;
the pydantic point model uses `ConfigDict(extra="allow")` for those dynamic keys.



====================================================================================================
FILE: .agents/memory/stale-vite-phantom-export.md
====================================================================================================

---
name: Stale Vite dev server → phantom "no export named X"
description: When the browser reports a missing export that clearly exists in source, suspect an orphaned dev server / stale Vite graph, not a code bug.
---

A browser SyntaxError like `The requested module '.../api-client-react/src/index.ts' does not provide an export named 'ApiError'` can be a false alarm: the export exists in the current source.

**Why:** Workflows can fail to release their ports between runs ("address already in use ('0.0.0.0', 8080)", "Port 25245 already in use"). The freshly-started workflow can't bind, so the browser keeps talking to the *old* dev server, whose Vite module graph predates a workspace-linked package change (e.g. an orval regen from an auth merge). The stale graph is missing the new export. The `?t=<ts>` cache-buster in the error is the old server re-transforming its own stale modules, which makes it look "fresh."

**How to apply:** Before editing code, verify the export actually exists (rg the source) and check the workflow logs for port-bind failures. If source is correct and ports are stuck, the fix is a clean `restart_workflow` of every affected artifact (SIGKILL clears orphans, rebinds ports, rebuilds the Vite graph) — not a code change. Confirm with a clean browser console (only `[vite] connected`) and a screenshot.



====================================================================================================
FILE: .agents/memory/strategy-lifecycle-desk.md
====================================================================================================

---
name: Strategy lifecycle & paper book desk
description: How the strategy registry / paper-book / lifecycle pillar is wired across persistence, engine, service, agent, and frontend.
---

# Strategy Lifecycle & Paper Book

A persisted strategy registry (research → backtest → paper → live / demote / retired)
with a paper book marked to REAL prices. Layers:

- **Persistence**: `lib/db/.../strategies.ts` (Drizzle) + `app/strategy_store.py`.
  Store is DB-first with an idempotent `CREATE TABLE IF NOT EXISTS` so it works
  even without `drizzle push`. JSON columns written as `json.dumps(...)::jsonb`;
  reads return a camelCase view; `upsert` expects snake_case (the service maps).
- **Engine**: `app/engine/paperbook.py` — pure MTM (position_marks, book_value,
  exposures, nav_curve from real closes since inception, realized_stats).
- **Service**: `app/strategy.py` — `create_strategy`, `paper_trade`,
  `mark`, `evaluate_promotion`, `transition`, `demote`, `desk_payload`.
- **Agent**: deterministic lifecycle intent handler runs BEFORE the LLM/heuristic
  in `orchestrate` (works for text + voice); `add_strategy_desk` tool + heuristic
  `wants_desk` only VIEW the desk.
- **Frontend**: `StrategyDeskPanel.tsx`, passthrough panel (no openapi model).

## Rebalance
- `strategy.rebalance(view, cost_bps)` re-derives targets from the **signal**
  (not the original explicit symbols/sector — those aren't persisted), diffs the
  marked book via `engine.generate_orders`, applies trades, and re-anchors entry
  prices + inception to today so the marked-book/NAV model stays consistent.
  Reports one-way turnover (`0.5*Σ|Δw|`) + modeled bps cost; stashes a
  `lastRebalance` summary on `construction` (JSON, no schema change) and logs a
  `{event:"rebalance"}` stage-history entry.
- **Routing trap**: "rebalance" is also a portfolio-optimizer keyword. The
  lifecycle handler runs first, so `_lifecycle_action` only returns "rebalance"
  when the query also says strateg/book or names a signal — otherwise "rebalance
  a portfolio" must fall through to `add_portfolio`/optimizer.

## Gotchas (cost >1 attempt)
- **`drizzle push` is destructive here**: pushing drops unrelated columns on
  `fundamentals`/`universe` and needs a TTY. Do NOT push for this table — the
  runtime `CREATE TABLE IF NOT EXISTS` in `strategy_store` is the intended path.
- **`paperbook.position_marks` has NO `weight` field** (only symbol/shares/
  entryPrice/price/marketValue/costBasis/pnl/pnlPct/priced). Per-name weight
  lives on `desk_payload().selected.exposures` (`[{symbol, weight}]`) — join on
  symbol in the UI, don't read `mark.weight`.
- **Promotion to live gates on persisted criteria** (default minSharpe .5,
  minReturnPct 0, maxDrawdownPct 25, minDays 5); "force"/"override"/"anyway" in
  the query bypasses via `transition(..., force=True)`.
- **Track record must come from PERSISTED daily NAV, not calendar age or live
  overlay**: promotion's "track record ≥ N days" counts audited `strategy_snapshots`
  rows (`trackDays`), never `ageDays` and never the display-only live "today"
  overlay point `mark()` appends. **Why:** a strategy must not clear `minDays` on a
  day whose snapshot hasn't been written yet. Snapshots are taken for *every*
  paper/live book (even flat ones — NAV = cash) so the series stays continuous;
  `mark()` only reconstructs from real closes as a fallback when zero snapshots
  exist yet.
- **Terminal vite build needs `PORT` and `BASE_PATH` env** or config load fails:
  `PORT=3000 BASE_PATH=/terminal pnpm --filter @workspace/terminal build`. The
  dev workflow runs HMR so source edits are live without a rebuild.

## Testing the lifecycle offline (tests/test_strategy*.py)
- Force the in-memory store by patching `strategy_store.db.db_available -> False`
  AND resetting `strategy_store._schema_ready=False` + `_mem.clear()`; restore in
  a finally. (`pytest` is not installed — mirror the runnable-as-script pattern.)
- Stub the data layer so nothing hits network/live DB: `repo.get_company`
  (return `{symbol,name,price}`), `repo.price_closes_bulk` (return
  `{series:{SYM:[{t,c}...]}, source, asOf}`), `repo.all_symbols`,
  `repo.get_all_companies`. Patching the `repo` module attrs hits both
  `strategy.py` and `agent.py` (same module object).
- Make close-series dates start at `date.today()` so `nav_curve` keeps them
  (`>= inception`); a fresh paper book has `ageDays=0 < minDays=5`, a
  deterministic promotion BLOCK regardless of stats — good for the gate test.
- Agent intent handler: stub `harness.run_skill` to a trivial panel dict to
  isolate `_handle_lifecycle` from the data-heavy panel builders.
- FastAPI: `TestClient(app)` WITHOUT a `with` block skips the app lifespan
  (background worker); strategy routes + skill registry are import-time so they
  still work. A blocked transition returns 200 with `ok:false` (not an
  HTTPException); only unknown id is a 404.
- **Lifecycle "create" regex hijacks programmatic queries**: `_lifecycle_action`
  matches `(create|register|set up|build|spin up|make) ... strateg`, so ANY
  orchestration query containing verb+"strateg" (e.g. "build a long call options
  strategy") is intercepted and creates a research strategy instead of the
  intended panel. When constructing queries in code (e.g. IV-surface cell click →
  options panel), phrase to dodge it: "Price a long call on NVDA at the $X strike
  for the Y expiry" routes to options_strategy via the `wants_options` heuristic.



====================================================================================================
FILE: .agents/memory/strategy-templates-marketplace.md
====================================================================================================

---
name: Strategy Templates Marketplace
description: How the strategy_marketplace panel works — alpha-signal presets, preview via build_signal_portfolio, clone via create_strategy, save user templates.
---

Templates are **alpha-signal presets** (momentum/value/quality/low_volatility/short_reversal) over an optional sector universe with topN+capital — NOT engine timing strategies.

**Why:** keeps the marketplace on the same model as the Signal Portfolio + Strategy Desk so preview/clone reuse existing, compliance-safe code paths instead of inventing a parallel strategy type.

**How it works:**
- Preview = `skills.build_signal_portfolio({signal, sector, scheme:"top_quantile"})` → real diversified backtest (stats/benchStats/curve/drawdown/holdings, live source). Identical numbers to the Signal Portfolio desk.
- Clone = `strategy.derive_target_weights(signal, None, None, sector, top_n=topN)` → explicit symbols+weights → `strategy.create_strategy(..., paper=True)`. create_strategy runs the compliance gate; route catches `strategy.ComplianceBlock` and returns `{ok:False, blocked:True, reason}`.
- **topN clamp 5–30.** topN=5 → equal-weight 20% > the 15% maxPosition limit → ComplianceBlock. topN≥7 is safe.
- Save = persists a user preset in `strategy_templates` table (template_store, DB-first + in-mem fallback like strategy_store). Built-ins live inline in `templates.py` (_BUILT_IN), never stored.

**Wiring gotchas:**
- `_handle_lifecycle` early-returns None when the query mentions template/marketplace, so the create verb ("build … strategy") doesn't hijack it into the desk.
- Heuristic `wants_marketplace` routes BEFORE `wants_desk` (marketplace text contains "strategies").
- Sector clearing uses "" sentinel (broad universe), mapped to None by `_clean_sector`; the refine branch passes "" through so it survives the None-strip in `_structured_refine_params`.
- `template_store.delete` must check existence first (db.execute returns None, no rowcount) so a missing id yields 404 not 200.
- engine is a PACKAGE (`app/engine/`); SIGNAL_META/normalize_signal/signal_label re-exported from `app/engine/__init__.py`.
- Frontend StrategyMarketplacePanel uses raw `/api/templates/...` fetch for clone/save/delete (like DCFPanel) and `onRefine` (paramRefineMutation) for catalog-select + tweaks.



====================================================================================================
FILE: .agents/memory/stress-test-panel.md
====================================================================================================

---
name: Scenario stress test panel (beta-scaled)
description: How the stress_test panel differs from risk_monitor/scenario and why it uses fitted betas rather than crisis replay.
---

# Scenario Analysis & Stress Test (`stress_test`)

A distinct panel from `risk_monitor` and `scenario`. It estimates a book's P&L
under named scenarios (2020 COVID −34%, 2022 rate shock −28%, 2008 GFC −55%,
+200bps rate shock, oil +50%) by scaling each holding's REAL fitted beta by the
scenario's headline shock, then weighting by positions. Per-scenario portfolio
impact + per-holding impacts.

**Why beta-scaling, not crisis replay:** `risk_monitor`'s historical stress
REPLAYS real crisis-window returns, so any name that didn't trade in the window
(e.g. META in 2008) is dropped — useless for a modern book. The stress_test
panel instead scales each name's CURRENT measured beta, so every holding with
~40+ recent daily obs is covered regardless of when it IPO'd.

**Factor proxies (real, fetched via `_benchmark_closes(ticker,"1Y")`):**
- market → SPY, pct returns; equity scenarios apply `market_beta × shockPct`.
- rate → `^TNX` (10y yield LEVEL). Use day-over-day LEVEL CHANGES (pp), not pct
  returns. +200bps = Δ2.0pp; impact = `rate_beta × 2.0`.
- oil → `CL=F` (WTI), pct returns; impact = `oil_beta × 0.50` for +50%.

**Unit discipline:** betas fit on fractional returns; portfolio impact% =
Σ signed_w_i × impact_i; USD = impact_fraction × nav.

**Honest coverage:** a name with no usable history or <40 overlapping obs with a
proxy is excluded from that scenario and flagged in `missing` — never imputed.
If a whole proxy is unavailable, that scenario is marked unavailable.

Math lives in `engine.univariate_beta` (OLS slope cov/var, returns None on
mismatch/short/zero-variance). Data assembly + scenario loop in
`skills.build_stress_test`. Standard passthrough panel (no openapi codegen).



====================================================================================================
FILE: .agents/memory/supply-chain-risk.md
====================================================================================================

---
name: Supply chain concentration risk scoring
description: How supply-chain panel risk scores are computed and the passthrough-vs-pydantic-model gotcha that strips unknown panel fields.
---

# Supply chain risk scoring

Per-node risk = exposure × (0.55 + 0.65 × geoRisk), bucketed Low/Medium/High/Critical
(`_RISK_BANDS`), with a single-source floor (exposure ≥ 90 → ≥ High; +sensitive region → Critical).
`_GEO_RISK` / `_COUNTRY_NAME` maps live in `skills.py`. `_annotate_supply_chain_risk` mutates
nodes+table and builds `riskSummary` (topRisks, countryConcentration as share of total supplier
exposure, counts). Both the curated `_SUPPLY_CHAIN_DB` path and `_generate_supply_chain` go through it.

**Why a separate score, not raw exposure:** a 100% dependency in Taiwan must read worse than a
100% dependency in the US — geopolitical region amplifies concentration risk.

## Policy / trade-action layer
`_POLICY_RISK` (keyed by country, like `_GEO_RISK`) carries `{flag, severity 0-1, reason}` for
tariffs / export controls / sanctions; `_POLICY_LABEL` maps flag→display. `_score_supply_node`
blends it as a third multiplier term: `exposure * (0.55 + 0.65*geo + 0.5*policy_sev)`, and floors
the label at High when `policy_sev >= 0.80` (severe = sanctions/hard export controls); a severe
single source escalates to Critical. Nodes/rows gain `policyRisk/policyReason/policySeverity`.
`riskSummary.policyRisks` aggregates affected suppliers per region; policy-driven nodes become
`kind="policy"` candidates so they rank into topRisks. **Concentration answers "where am I
exposed", policy answers "what event actually breaks this link"** — keep them as separate signals.
Remember: every new field needs adding to the pydantic models too (see gotcha below).

## The gotcha that cost a round-trip
`supply_chain` is NOT a fully passthrough panel — it has a pydantic model
`models.SupplyChainData` registered in `harness.DATA_MODELS`. `run_skill` does
`model.model_validate(raw).model_dump()`, which **silently drops any field not on the model**.
So adding a key in `skills.py` only is invisible at the API boundary even though calling the
builder directly in a REPL shows it. **Any new supply_chain field must be added to the pydantic
model in `models.py` too.** (Contrast with truly dynamic/AI-generated panels which have no model
and pass through untouched.)

**How to apply:** when extending any built-in panel's data shape, check `harness.DATA_MODELS` for
that panel_type; if a model exists, extend it or the field gets stripped before reaching the frontend.

## Drill-down recenter (click a node)
The supply-chain graph supports drilling into a node's own chain (NVDA → TSM → ASML).
`refine()` in `agent.py` has deterministic canonical-instruction shortcuts that bypass the
LLM entirely — same pattern as `risk_monitor`'s custom shock. The graph emits
`"Recenter supply chain on <SYM>"`, parsed by `_supply_chain_recenter_params` (regex), so a
node click never depends on AI latency/reliability. `keep_title` stays None so
`harness._derive_title` regenerates `{SYM} · Supply Chain`. Frontend trail/breadcrumb state
lives in `SupplyChainPanel` (survives because refine reuses the same panel id); the trail
truncates when navigating back to an existing crumb, appends on new drill-in.

**Why deterministic:** clicks must be instant + reliable; the LLM refine path is for free-text.
**How to apply:** to add another click-driven recompose, add a canonical-instruction shortcut
in `refine()` before the `_refine_params` fallback, not a new endpoint.



====================================================================================================
FILE: .agents/memory/terminal-orchestration.md
====================================================================================================

---
name: Terminal dashboard orchestration model
description: How the agentic terminal composes dashboards — additive-by-default, session handling, reset semantics.
---

The orchestrator (`artifacts/api-server/app/agent.py::orchestrate`) is **context-aware, not
blindly additive**. On each query it first judges which existing panels still belong
(`_decide_kept_panels`): an LLM relevance call (`_relevance_llm`, JSON `{keep:[ids]}`, empty
list = drop all) with a keyword/subject heuristic fallback (`_relevance_heuristic`). Genuine
follow-ups on the same subject KEEP the relevant panels; switching to an unrelated subject
DROPS the abandoned subject's panels. Kept panels are then re-packed from the top
(`_repack` → live cursor) so removed panels leave NO grid holes, and new panels continue
flow-packing from that same cursor. Stored/returned dashboard = `kept + new`.

**Why:** asking about Samsung then about agriculture should replace, not stack. But viewing a
stock then "add retail investor analysis" / "show its news" / "compare to AMD" is a
continuation and must keep what's shown. The heuristic leans conservative (keeps all unless a
clearly different in-dataset ticker/sector appears with no continuation keyword like
add/also/compare/its).

**Gotcha:** api-server runs WITHOUT --reload, so orchestration logic changes only take effect
after restarting the `artifacts/api-server: API Server` workflow — testing via the live API
before restart silently runs the old code.

Session rules:
- The default dashboard uses sessionId `"default"` — a placeholder that must NEVER be
  accumulated onto. `orchestrate` treats `"default"` (and missing sessionId) as "mint a new
  session id," so the first real query starts clean and each page reload starts fresh.
- A **reset** intent (`_wants_reset` — word-boundary match on "reset", "wipe", "start fresh",
  "clear the/everything", "new dashboard", "clean/blank slate", "remove everything") also mints
  a brand-new session id. Minting (vs just clearing panels) ensures the prior **conversation
  history** is dropped too — otherwise stale context biases the "fresh" LLM orchestration.
  Use word boundaries so "preset"/"swipe" don't false-trigger.

Frontend (`Dashboard.tsx`): panels are wrapped in framer-motion `AnimatePresence` + `motion.div`,
keyed by `panel.id`, so appended panels fade/slide/blur in while existing ones (same key) do NOT
remount or re-animate. Grid placement (gridColumn/Row from `panel.layout`) lives on the motion
wrapper; `PanelContainer` is `h-full` and fills the cell.

## Conversational Q&A intent (Console)
`orchestrate` now splits each non-voice, non-reset message into a **question** vs **build**
intent (`_classify_intent`): a cheap `_has_question_signal` gate (no signal → build, no LLM
call) then an LLM classifier (`_classify_intent_llm`, JSON `{intent}`) with a conservative
keyword fallback (`_is_question_heuristic`, defaults to build unless clearly conceptual and no
`_BUILD_CUES`). A question answers in chat (`_answer_question` → LLM grounded in on-screen
panels + last 6 history turns; honest fallback string) and returns the panel set UNCHANGED with
`{intent:"question", answer, summary:""}`; a build is unchanged and returns `{intent:"build"}`.
**Voice always builds** (intent split skipped when `voice=True`) so narration is untouched.

**Frontend contract:** `DashboardSpec` gained optional `intent` + `answer`. `Terminal.tsx`
drives the Console via a nonce-bumped `reply={text,kind,nonce}` prop (replaces the old
content-deduped `lastSummary` effect) so a question's answer ALWAYS renders even if its text
repeats. `ChatPanel` appends on nonce change; answers are labelled "Terminal · Answer".



====================================================================================================
FILE: .agents/memory/trade-flow-alerts.md
====================================================================================================

---
name: Trade-flow alert rules
description: How the trade-flow alert feature is structured and two gotchas that cost rework.
---

Feature: notify when a trade_flow build crosses a threshold (block size,
dark pool %, buy imbalance). Rules + fired events stored per-session in
`state.py` (`_alert_rules`, `_alert_events`). Evaluation engine in
`alerts.py` (METRICS catalog + evaluate_flow/evaluate_dashboard), hooked
into `agent.py` orchestrate/refine. CRUD in `main.py` under /api/alerts.
Frontend: AlertsPanel (builder) + AlertsNotifications (poll + toast).

**Gotcha 1 — FastAPI route ordering:** the static `/alerts/events`
GET/DELETE routes MUST be declared *before* the parametrized
`/alerts/{rule_id}` DELETE. Otherwise "events" is matched as a rule_id
and the event endpoints silently never run (DELETE returns the rule
payload instead of clearing). Symptom: clear-events appears to do nothing.

**Gotcha 2 — event dedup:** events carry a `signature` so repeated
deterministic trade_flow builds (seeded data) don't re-fire duplicate
alerts. Second evaluate_flow over the same flow adds 0 events.

**How to apply:** when adding more static sub-paths under a parametrized
resource, always order static-before-parametrized. When evaluating
deterministic builders repeatedly, dedup on a stable signature.



====================================================================================================
FILE: .agents/memory/universe-breadth.md
====================================================================================================

---
name: Stock universe breadth (US + SGX)
description: How the deep curated catalog stays cheap — mock breadth in DB, live data only on demand, SGX via base codes.
---

# Deep curated universe (US + SGX)

The terminal catalog is large (hundreds of names, many sectors) but only a small
curated **CORE** set is ever continuously fetched. Everything else is breadth:
deterministic mock metrics that look real and only get refreshed with live data
when a user actually opens the symbol.

**The split is the whole design — do not break it:**
- `data.CORE_SYMBOLS` is snapshotted from the hand-written headliners *before*
  the bulk `_q()`/`_load()` loaders run. The worker marks only CORE
  `tracked = TRUE` and ingests it on the price/fundamentals/news loops.
- Bulk names are seeded `tracked = FALSE` with `fundamentals.is_live = FALSE`
  (mock). They become live one-shot via the on-demand loop when `note_symbol()`
  flips `pending = TRUE`.

**Why mock fundamentals are pre-seeded into the DB at startup:** so the
breadth-reading panels (screener/heatmap/sector lists) work off the same
DB queries with no per-symbol fallback gymnastics. `is_live` is the single source
of truth for the `live` vs `mock` provenance badge (`_company_from_row`).

**On-demand contract:** `get_company` does NOT enqueue catalogued symbols (they
already have a DB row), so the primary builders (`build_price_chart`,
`build_fundamentals`) must call `repo.note_symbol()` explicitly to request live
data. `note_symbol` is a no-op once a symbol is already live or already pending.

**SGX gotcha:** SGX names are catalogued under their **base code** (e.g. `D05`,
`O39`, `C38U`) — never with `.SI`. `data.yahoo_symbol()` appends `.SI` only at
fetch time (worker ingest), and rows are always persisted/keyed under the base
code. Symbol regexes (`_extract_symbols`, `note_symbol`) must accept alphanumeric
tokens, not just `[A-Z]`, or SGX codes silently won't resolve.

**Prompt budget:** the full list is far too big to inline in every LLM tool
description. Use `repo.prompt_symbols(n)` (cap, market-cap desc) for prompts;
keep `all_symbols()`/`symbols_in_sector()` for the real breadth at request time.

**Schema:** added idempotently in `worker._seed_universe` (no migration files):
`universe.country`, `universe.exchange`, `fundamentals.is_live`,
`fundamentals.mcap_refreshed_at`.

**Country/exchange filtering (screener/heatmap):** `repo.resolve_market/resolve_country/
resolve_exchange` normalize free text (SG/Singapore/usa/sgx) to canonical
`universe.country`/`exchange` values; `repo.symbols_by_market(sid, country, exchange)`
is the DB-backed (mock-fallback) filter. Builders share `skills._market_filter`/
`_market_title`. **Heuristic trap:** `_extract_symbols`' name-fallback matches a company's
first name-word, so geo words pull in `Singapore` Airlines/Post/Exchange and `United`
Overseas Bank — guard with `_GEO_NAME_STOPWORDS` or "Singapore market heatmap" becomes a
3-ticker comparison. country/exchange already exist on ScreenerRow/HeatmapCell models, so
no openapi codegen is needed.

**Breadth market-cap refresh (don't break the mock/live split):** a slow
round-robin loop corrects ONLY the `market_cap` of mock breadth names so the
hand-entered `_US`/`_SGX` cap hints don't drift over months. Rules:
- Filter is `is_live = FALSE` (exactly the mock breadth set). The cap-only update
  must NOT set `is_live = TRUE` — the row is still mock for every other field.
- The cheap source is `f_src.fetch_market_cap` → yfinance `fast_info["market_cap"]`
  (derived from last price × shares via the chart endpoint; far lighter than full
  `.info`). yfinance `fast_info` keys are accessible via `["market_cap"]`; `.get`
  is unreliable. Returns None if missing → loop skips.
- Round-robins by `ORDER BY mcap_refreshed_at ASC NULLS FIRST` (least-recent
  first); small batch + long sleep so it never competes with live loops/requests.
  First pass is deferred (startup delay) so it never piles onto cold-start boot.
- `_update_market_cap` leaves `updated_at` untouched on purpose so this pass
  doesn't masquerade as a full fundamentals snapshot.



====================================================================================================
FILE: .agents/memory/voice-guided-walkthrough.md
====================================================================================================

---
name: Voice-driven guided walkthroughs
description: How a spoken "walk me through X" runs the navigator cursor + spoken captions, advancing in sync with narration.
---

# Voice-driven guided walkthroughs (Agentic Terminal)

A tour intent spoken in Voice Mode ("walk me through NVDA") drives the navigator
cursor AND narrates each stop's caption via TTS, with the cursor advancing only
after each caption's audio finishes.

## Ownership split (who drives what)
- **The voice conductor owns the turn lifecycle + barge-in + audio playback.**
  The tour runs inside `handleUtterance` as a normal turn (status stays
  `speaking`), so the existing turnId/barge-in machinery and orb animation work
  for tours with no extra plumbing. **Why:** routing the tour as a separate
  out-of-turn flow caused an idle-flash + spurious "complete" toast and lost
  barge-in/orb-animation.
- **The navigator owns the cursor visuals** (caption card, index/total, cursor
  point, highlight). In a voice tour it runs in **narrated mode**
  (`start(tour, { narrated: true })`): the built-in dwell auto-advance is OFF and
  the cursor only moves when the conductor calls the exposed async
  `goTo(i)` (resolves once the cursor has landed). The conductor loops:
  `moveCursorTo(i)` → synth caption → `playSegmentAudio` (await = synced advance)
  → next i.
- **Terminal wires them together** via three conductor args: `prepareTour(text)`
  (returns ordered `{panelId,caption}[]` or null), `moveCursorTo` (=navigator
  `goTo`), `endTour` (=navigator `stop`). `prepareTour` reuses the chat tour's
  NAV_INTENT/tourSubject logic: bare intent + panels on screen → tour what's up;
  otherwise orchestrate (voice:false) → wait ~850ms for render → `/api/navigate`.

## Gotchas / contract
- `prepareTour` returns null for non-tour utterances → conductor falls through to
  the normal narration path (processQuery voice:true). No double orchestration.
- The conductor sets highlight via the navigator (moveCursorTo), NOT itself, in
  the tour loop — avoids double-driving the shared `highlightedPanelId`.
- Stop/dismiss: the NavigatorCursor `onStop`, when voiceMode, also calls the
  conductor's exposed `cancelNarration()` (bumps turnId + stops audio + idle) so
  dismissing the cursor silences the AI; the loop then breaks → `endTour`.
- Manual prev/next are hidden during voice tours (`manualControls={!voiceMode}`)
  because the conductor owns advancing; they'd fight the synced loop.
- `hasPanels` is mirrored to `hasPanelsRef` so `prepareTour` (a stable callback)
  reads the live value instead of a stale closure.



====================================================================================================
FILE: .agents/memory/voice-mode-loop.md
====================================================================================================

---
name: Voice Mode push-to-talk
description: Web Speech recognition quirks and the conductor turn contract for the terminal's push-to-talk Voice Mode.
---

Voice Mode = mic (Web Speech `SpeechRecognition`) → orchestrate → TTS narration, driven by
`useVoiceConductor` over `useSpeechRecognition`.

**Interaction model = push-to-talk (NOT hands-free).** The user presses-and-holds the orb to
listen and releases to send. The mic NEVER re-arms on its own — after a turn finishes it stays
idle until the user holds again. **Why:** the user explicitly rejected the auto re-arm loop. So
there is no `scheduleRestart`/restart timer and no network-retry auto-recovery loop anymore.

**Recognition config for push-to-talk:** `continuous=true` so a session keeps accumulating speech
for as long as held (it does NOT auto-finalize on a pause). Final fragments are accumulated and the
full utterance is emitted from `onend`, not per-`isFinal`. Two stop paths matter:
- **graceful `.stop()`** on release — Chrome finalizes the captured audio so `onend` can emit the
  accumulated utterance. Use this for hold-release.
- **`.abort()`** — discards the session without firing an utterance (sets a `discard` flag so
  `onend` skips emitting). Use this for leaving Voice Mode / cleanup.
Mixing these up is the classic bug: aborting on release throws away the user's words.

**Async mic-setup race:** `startListening` awaits `getUserMedia`. A quick tap can release before the
mic is ready. Guard with a `heldRef` set on press / cleared on release; after the await, bail if no
longer held so a fast tap never strands an armed session.

**Prime mic permission on the Voice-On gesture, NOT during the hold.** On phones the OS permission
prompt interrupts a press-and-hold — a `pointercancel` fires mid-hold, the hold is torn down, and the
user ends up tapping Deny by accident → "mic permission denied." **Fix/contract:** `startVoice` calls
`primeMicPermission()` (a `getUserMedia({audio:true})` that immediately stops the tracks) so the
prompt happens on the deliberate Voice-On tap; once granted, later holds re-acquire the mic with no
prompt. If priming is denied, surface the error + Retry and don't enter idle. Guard
`navigator.mediaDevices?.getUserMedia` (insecure context / unsupported) with a Chrome+https hint.

**Orb is a pointer hold-target:** use pointer events (`onPointerDown`/`onPointerUp`/`onPointerCancel`)
— they unify mouse + touch and avoid the double-fire of mixed mouse+touch handlers. Call
`setPointerCapture` on press so release is received even if the finger slides off. Suppress
`onContextMenu` and set `touch-action:none` + `user-select:none` so a long-press doesn't select text
or open the mobile context menu.

**no-speech end:** with `continuous=true`, releasing after silence (or a Chrome silence timeout) fires
`onend` with nothing captured (`no-speech`/`aborted` are non-fatal, not surfaced as errors). The
conductor treats end-without-utterance as a transition back to **idle** — it does NOT re-arm.

**Barge-in (interrupt the AI while it talks):** holding the orb during `thinking`/`speaking`
interrupts the current turn and immediately starts the next listen. Implemented with a monotonic
`turnIdRef`: each `handleUtterance` claims `++turnIdRef.current`; a barge-in (`interruptTurn`) bumps
it, `.stop()`s the current `AudioBufferSourceNode` (`playSourceRef`), and resets `busyRef`/highlight.
The in-flight turn re-checks `myTurn === turnIdRef.current` after every await (post-processQuery,
each segment, post-synth) and **returns without touching status/busyRef/onComplete** if superseded —
otherwise it stomps the new listening session (stray idle + toast). `source.onended` guards
`playSourceRef.current === source` before nulling so a stop() doesn't clobber a newer source.
VoicePanel gates hold-start on `status !== "listening"` (was idle/error) so only an active listen
blocks a fresh hold. **Why:** user asked to interject mid-narration to ask the next thing.

**Keyboard barge-in (hold Space):** VoicePanel also wires a window `keydown`/`keyup` push-to-talk on
`Space` that mirrors the orb exactly — hold to talk, release to send, and pressing during
thinking/speaking barges in. Guards: skip `e.repeat` (autorepeat), skip when target is an
INPUT/TEXTAREA/contentEditable, and only arm when `status !== "listening"` (matches the orb's
`canHoldStart`). A `keyHeldRef` persists the held flag so the effect re-running on status changes
(it depends on `status`) never drops a key that's still physically down — `keyup` still fires
`onStopListening`. Effect is inert when `!supported || embedded || status === "error"`. **Why:** the
"interrupt mid-response" task asked for a key alternative to the orb; Space is the classic PTT key.

**Echo / self-trigger:** the mic MUST stop the instant an utterance finalizes and stay off through
thinking + speaking, or the recognizer picks up the synthesized TTS and re-triggers. `handleUtterance`
stops recognition before "thinking"; `startListening` refuses to arm unless status is idle/error, so
pressing the orb during thinking/speaking is a no-op.

**Cross-browser (server-side STT fallback):** Safari/Firefox lack Web Speech. When the native API is
absent, `useSpeechRecognition` falls back to recording the hold with `MediaRecorder` and uploading the
clip to the server `/transcribe` endpoint on graceful `.stop()` (abort discards without uploading) —
exposing the SAME start/stop/abort/supported contract so the conductor turn loop is unchanged. The
recorder branch picks a browser-supported mime (Firefox=webm/opus, Safari=mp4) and has NO live interim
(it emits a one-shot "Transcribing…" while the upload is in flight). `/transcribe` mirrors `/speak`:
JSON body `{audio: base64, mimeType}` → OpenAI `gpt-4o-mini-transcribe` (audio.transcriptions) →
`{text}`. The conductor passes a `transcribe(blob)` arg (Terminal wires `useTranscribe`); when present,
`supported` is true on Safari/Firefox so the "needs Chrome" card no longer shows there (only when there
is neither Web Speech NOR MediaRecorder+transcribe). Recognition/synthesis errors set status "error"
with a visible Retry; a single `network` error surfaces as error (hold to retry), not a retry loop.

**Iframe blocks Web Speech (the big one):** Chrome's `SpeechRecognition` is blocked inside
cross-origin iframes — and the Replit **preview pane is an iframe** — so it throws persistent
`network` errors there even though the same app works in a normal top-level tab. This is
environmental; no code change makes recognition work inside the preview. **Fix/contract:** detect the
cross-origin iframe **up front** (shared `lib/embed.ts` `isEmbedded()`) and **short-circuit
`startVoice` before starting recognition** — set a conductor `embedded` flag and render the dedicated
"Open Voice Mode in a new tab" card (`openStandaloneTab()`). The conductor owns detection; VoicePanel
just reads the `embedded` prop.

**Runtime dep:** the generated-panels registry imports `sucrase` (browser-side TSX transpile). It must
actually be installed (`pnpm install`) — a missing install surfaces as a Vite "Failed to resolve
import 'sucrase'" that blanks the whole terminal, easy to mistake for a Voice Mode bug.

**Voice + speed settings:** users pick a gpt-audio voice and a speaking-speed multiplier in a
VoicePanel popover; prefs persist to localStorage and flow through `/speak` (SpeakRequest gains
`voice`/`speed`). **Gotcha:** the gpt-audio *chat-completions* `audio` param only takes
`voice`+`format` — there is NO native speed knob, so speed is steered via a pacing sentence appended
to the narrator system prompt and clamped server-side (0.5–1.5). The frontend `VOICE_OPTIONS` list
must stay in sync with `AVAILABLE_VOICES` in `app/ai.py`.

**Layout:** Voice Mode is a **floating overlay**, NOT a takeover. The dashboard/dotwave stays
full-screen; VoicePanel is a compact `fixed` bottom-center card. **Why:** user rejected the orb
filling the screen — "full screen should just be the terminal, orb should be somewhere." On phones
(`useIsMobile()`, breakpoint 768) the chat aside is not rendered at all (no typed fallback), the
dashboard takes full width, and VoicePanel renders in `compact` mode with a smaller orb (~84px vs
132px) docked at the bottom.



====================================================================================================
FILE: .agents/memory/walk-forward-multi-symbol.md
====================================================================================================

---
name: Multi-symbol walk-forward robustness
description: walk_forward_compare panel — fans the overfitting check across a universe and aggregates per-name verdicts into a robustness score.
---

A single-name walk-forward pass can be a lucky draw, so `walk_forward_compare`
runs the SAME check across a list/sector and aggregates. It does NOT reimplement
the engine — it fans out `build_walk_forward` per symbol concurrently
(ThreadPoolExecutor + `_safe_call`), isolating per-name failures exactly like
`build_analyst_compare`.

**Honest-coverage contract carries through:** thin-history names come back with
`verdict == "inconclusive"` and are EXCLUDED from the aggregate robustness score
(reported in `aggregate.inconclusive`, never hidden). The score is a plain mean
of `_WF_VERDICT_SCORE` over the judged names (robust=100 … severe=0); aggregate
label is robust/mixed/fragile/inconclusive.

**Routing (agent.py, inside the `if wants_walkforward:` block):** route to
`walk_forward_compare` when `len(symbols) >= 2` OR (a sector is detected AND the
query has an "across/universe/basket/every" cue or names no explicit symbol).
Otherwise fall through to single-name `walk_forward`. Added "robust across",
"robust over", "holds up across" to `wants_walkforward` keywords (bare "robust"
is too broad and would steal plain backtest queries). Sector expands via
`repo.symbols_in_sector`; capped at 12 names.

**Passthrough panel** (same as walk_forward): no harness.DATA_MODELS entry,
frontend `WalkForwardComparePanel.tsx` types its own data, stale-PanelType tsc
errors are expected and don't gate the vite build (verify with vite build, not tsc).

**Verdict-label naming trap:** the engine emits `some_overfitting` (not
`some_decay`). The original `WalkForwardPanel.tsx` VERDICT_STYLE keys it as
`some_decay`, so it silently falls back to the inconclusive style — the new
compare panel keys it correctly as `some_overfitting`.



====================================================================================================
FILE: .agents/memory/walk-forward-research-integrity.md
====================================================================================================

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



====================================================================================================
FILE: .agents/memory/yield-curve-recession-signal.md
====================================================================================================

---
name: Yield-curve recession-signal overlay
description: How the yield_curve panel turns 2s10s/3m10s spreads into a plain-language recession read with live inversion duration.
---

The `yield_curve` panel surfaces an explicit recession-risk read derived from the
two market-watched segments: **2Y–10Y** and **3M–10Y** (an inversion = short
yield > long yield).

**Data flow:**
- `rates.fetch_treasury_curve()` adds an `inversion` dict keyed by `"2Y-10Y"`/`"3M-10Y"`
  (HYPHEN, not en-dash). Each value = `{inverted, days, obs, since}` from
  `_inversion_streak`, which walks BACKWARD through ALL daily rows already fetched
  (current + two prior years) counting the *current* consecutive inverted streak;
  it stops at the first non-inverted day (honest current streak, not cumulative).
- `skills._recession_read(spreads, inversion)` builds the `recession` block:
  `level` (warning=both inverted / watch=one / normal=none), `headline`, `detail`
  (plain-language, includes humanized duration via `_humanize_duration`), and
  per-`segments` with `days`/`since` when live streak data is present.
  Mock fallback (non-US regions, source down) passes `inversion=None` → status
  text only, no duration.
- `_SEGMENT_KEYS` maps spread label (en-dash `2Y–10Y`) → inversion key (hyphen
  `2Y-10Y`). Keep both punctuations consistent or the join silently drops duration.

**Contract gotcha:** built-in panels validate against `models.YieldCurveData` (in
`harness.DATA_MODELS`) which STRIPS unknown fields. Added `recession:
Optional[YieldCurveRecession]` (+ nested `YieldCurveRecessionSegment` with optional
`days`/`since`) so the field survives validation. asOf/source still live on the
envelope (popped before validate).

**Frontend** (`YieldCurvePanel.tsx`): `RECESSION_STYLES` by level (red/yellow/
emerald) drives the headline badge + detail card + per-segment "Xd · since DATE"
chips. Falls back to the old "⚠ Curve Inverted" badge only if `recession` absent.



====================================================================================================
FILE: CLAUDE.md
====================================================================================================

## gstack (REQUIRED — global install)

**Before doing ANY work, verify gstack is installed:**

```bash
test -d ~/.claude/skills/gstack/bin && echo "GSTACK_OK" || echo "GSTACK_MISSING"
```

If GSTACK_MISSING: STOP. Do not proceed. Tell the user:

> gstack is required for all AI-assisted work in this repo.
> Install it:
> ```bash
> git clone --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
> cd ~/.claude/skills/gstack && ./setup --team
> ```
> Then restart your AI coding tool.

Do not skip skills, ignore gstack errors, or work around missing gstack.

Using gstack skills: After install, skills like /qa, /ship, /review, /investigate,
and /browse are available. Use /browse for all web browsing.
Use ~/.claude/skills/gstack/... for gstack file paths (the global path).



====================================================================================================
FILE: artifacts/api-server/SECURITY.md
====================================================================================================

# Agentic Terminal API — Security Posture & Threat Model

This document records the security controls on the `api-server` artifact, the
threats they address, and the residual risks an institutional operator should be
aware of. **Server-side enforcement is authoritative**; any frontend gating
(hidden buttons, disabled controls) is convenience only.

Last reviewed: 2026-06-09.

---

## 1. Trust boundaries

| Zone | Description | Trust |
| --- | --- | --- |
| Browser SPA (`artifacts/terminal`) | Untrusted. All input is attacker-controllable. | none |
| Replit edge proxy | Terminates TLS, path-routes to the artifact, injects `X-Forwarded-For`. | infrastructure |
| `api-server` (FastAPI) | The authority. Enforces authn/authz, validation, limits. | trusted |
| PostgreSQL | Holds firms, users, sessions, per-firm settings, app state. | trusted store |
| Upstream data feeds (Yahoo, FRED, US Treasury, SEC EDGAR, IEX, Polymarket) | Untrusted external data. Parsed defensively. | none |
| OpenAI via Replit AI Integrations proxy | Trusted transport; **its output is untrusted** (treated as data, validated before any execution). | none for outputs |

Tenancy model: every authenticated request resolves to an `Identity` of
`{user_id, firm_id, role}`. The firm is the tenant boundary.

---

## 2. Identity, authentication & authorization

- **Authentication.** All non-public routes hang off a router that depends on
  `require_identity` (`app/main.py`). It resolves the caller from the httpOnly
  `at_session` cookie (or an `Authorization: Bearer` token for non-browser
  clients) via a hashed-token session lookup. No/invalid/expired token → `401`
  before any handler runs. Only `/api/healthz`, `/api/auth/signup`,
  `/api/auth/login` are public.
- **Sessions.** Tokens are random and stored only as a hash; the cookie is
  `httpOnly`, `Secure`, `SameSite`. Logout revokes the session server-side.
- **Passwords.** Salted hash with a constant-time compare (`app/auth.py`).
- **Authorization (RBAC).** `require_role(*roles)` builds on `require_identity`
  and returns `403` if the caller's role is not allowed. The first user of a
  firm is `admin`; others default to `analyst`.
- **Tenant isolation.** Handlers operate within `identity.firm_id`. Generated AI
  code cannot reach the DB or other firms' data at all (see §4).

---

## 3. Transport & application hardening

Implemented in `app/security.py`, wired in `app/main.py`:

- **CORS allow-list, never `*`.** `allowed_origins()` derives the explicit origin
  list from `REPLIT_DOMAINS` / `REPLIT_DEV_DOMAIN`. `allow_credentials=True` is
  therefore safe (a wildcard + credentials is forbidden by browsers and was the
  prior misconfiguration). Methods restricted to `GET/POST/DELETE/OPTIONS`.
- **Security headers on every response** (`SecurityHeadersMiddleware`), including
  error/401 responses:
  - `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'`
  - `Referrer-Policy: no-referrer`
  - `Permissions-Policy` disabling geolocation/mic/camera/payment
  - `Cross-Origin-Opener-Policy: same-origin`
  - `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'`
    — appropriate for a JSON API that never renders HTML.
- **Request body cap** (`BodySizeLimitMiddleware`): rejects bodies over
  `MAX_BODY_BYTES` (default 16 MiB) with `413` before reaching a handler. Sized
  to allow a short base64 voice clip on `/transcribe` while blocking body-bombs.
- **Rate limiting** (`rate_limit` dependency, sliding window per client IP):
  | Bucket | Endpoint(s) | Limit |
  | --- | --- | --- |
  | `auth` | `/auth/login`, `/auth/signup` | 10 / 60s |
  | `orchestrate` | `/orchestrate`, `/orchestrate/stream` | 30 / 60s |
  | `feature-request` | `/feature-request` | 10 / 60s |
  | `speak` | `/speak` | 60 / 60s |
  | `transcribe` | `/transcribe` | 60 / 60s |
  Exceeding a bucket returns `429` with `Retry-After`. Auto-disabled under the
  test runner (`PYTEST_CURRENT_TEST`) or `TERMINAL_RATELIMIT_DISABLED=1`.

---

## 4. AI code-execution containment (highest-value control)

The self-building feature pipeline (`/feature-request`) lets an admin describe a
panel and has the LLM author **and run** new Python + TSX. This is the single
highest-risk surface; it is contained in depth:

1. **Authorization gate.** `/feature-request` and `DELETE /features/{type}`
   require the `admin` role (`require_codegen_enabled` → `require_role("admin")`).
2. **Per-firm kill-switch.** `app/firm_settings.py` stores a `codegen_enabled`
   flag per firm (DB-backed, default on). Any admin can disable AI code
   execution for the whole firm via `POST /api/firm/settings`; while off,
   `/feature-request` returns `403`.
3. **Input bound.** Feature descriptions are capped (2000 chars) and rate-limited.
4. **Static allow-list validation** (`app/code_guard.py`). Generated Python is
   parsed to an AST and rejected unless it conforms to a strict allow-list:
   - imports limited to a vetted set of stdlib/data roots; **no** `os`,
     networking, `subprocess`, `app.*`, DB drivers, or filesystem modules;
   - **no** dynamic execution (`eval`, `exec`, `compile`, `__import__`),
     attribute-based escapes, or dunder access.
   Because the allow-list excludes `os`, networking, and `app.*`, generated code
   **cannot read environment secrets, open sockets, or touch the database / other
   firms' data** — containment is structural, not heuristic.
5. **Isolated validation subprocess** (`app/feature_builder.py`). Candidate code
   is imported and exercised in a separate `python -I` subprocess with a clean
   env, POSIX resource limits (CPU/memory/file-size), no network, and a wall-clock
   timeout. Failure leaves **no** partial files (atomic write-or-rollback). This
   subprocess call is annotated `# nosemgrep` — its argv is a static list and it
   *is* the sandbox, not an injection sink.

> Note: validated features run **in-process** afterwards (no server restart), so
> the static guard + sandbox validation are the security boundary. The guard is
> deliberately conservative — it is easier to widen the allow-list later than to
> recover from an escape.

---

## 5. Secrets & logging hygiene

- All credentials (`SESSION_SECRET`, `AI_INTEGRATIONS_*`, `FRED_API_KEY`,
  `DATABASE_URL`/`PG*`) are read from the environment via `os.environ` — none are
  hard-coded. The HoundDog PII/secrets scan reports **0** findings.
- API keys are never logged. Provider clients read keys at call time and log only
  status/latency, never request bodies or auth material.
- Session tokens are logged/stored only as hashes.

---

## 6. Dependency & SAST scan results (2026-06-09)

- **Dependency audit:** 0 critical, 0 high, 1 moderate (transitive). No
  critical/high to remediate.
- **SAST (semgrep):** 0 critical, **0 high** after this pass. Resolved this pass:
  - Switched external XML parsing (`app/sources/edgar.py`,
    `app/sources/thirteenf.py`) from stdlib `xml.etree` to **`defusedxml`** to
    remove the XXE / entity-expansion (billion-laughs) risk on untrusted SEC
    feeds.
  - Triaged + suppressed confirmed false positives: the validation
    `subprocess.run` (the sandbox itself, static argv) and five `generic-api-key`
    hits that are plain numeric constants (e.g. `DEFAULT_CAPITAL = 1_000_000.0`),
    not secrets.
- **HoundDog (PII/secrets):** 0 findings.

### Accepted residual (MEDIUM, out of critical/high scope)

- `insecure-hash-algorithm` (MD5/SHA1) in `app/data.py`, `app/sources/{congress,news,sentiment}.py`:
  used only for **non-cryptographic** content/dedup cache keys, not for security.
  Acceptable; could be migrated to SHA-256 opportunistically.
- `detect-non-literal-regexp` / `unsafe-dynamic-method` in frontend artifacts:
  client-side, low impact; the API does not trust the client regardless.

---

## 7. Known residual risks / non-goals

- **Single-node limits.** Rate limiting and the body cap are in-process. They are
  defense-in-depth against cost/abuse, **not** a substitute for an edge WAF or a
  distributed limiter. A multi-replica deployment should add an edge layer.
- **AI output quality.** Containment prevents a generated feature from causing
  *harm*; it does not guarantee the feature is *correct*. Admins own what they
  build.
- **Upstream data integrity.** External feeds can be wrong or unavailable. The
  app reports source/`asOf`/coverage and never silently imputes, but it trusts
  the *values* those providers return.
- **Self-build is in-process.** A future hardening step would move execution of
  validated features into a persistent isolated worker rather than the API
  process.



====================================================================================================
FILE: docs/design/v2-system-architecture.md
====================================================================================================

# Doomberg v2 — System Architecture & Topology

> **Status:** Design (spine). This is the foundational architecture other v2 designs hang off.
> **Date:** 2026-06-16
> **Scope of this doc:** component map, end-to-end flows, the BYO-agent trace model, layer boundaries/contracts, and a stack recommendation per component.
> **Grounded in:** v1 code at `artifacts/api-server/app/` (engine, sources, strategy lifecycle, tenant context, worker, SSE) and `docs/reviews/architecture-review-2026-06-16.md`.

---

## 0. North star & the v1 lessons that shape this

Doomberg v2 is **not** an AI terminal. It is a **financial tool-platform** that *someone else's* agent plugs into. The user runs their own agent (Claude/GPT/custom); Doomberg gives that agent (1) a **Data Layer** of callable financial tools and (2) a **Deploy Layer** to backtest and run strategies paper-live — plus a web UI that *observes* the agent and renders what it's doing.

Two consequences drive every decision below:

1. **The agent is external and untrusted-as-a-client.** Doomberg never runs the agent loop and never executes agent-authored code in-process. (v1's single worst class of bug — two critical in-process RCEs — came from running LLM-authored code behind a static guard. v2 deletes that path entirely; see §6.)
2. **We must reconstruct a thought process we don't own.** The agent's reasoning happens inside the user's runtime. Doomberg can only see what crosses the wire: MCP tool calls, their arguments, their results, and whatever reasoning the agent volunteers. §3 is the hard problem and the heart of this doc.

The v1 review surfaced six recurring failure themes. Each maps to a **non-negotiable invariant** in v2:

| v1 failure theme | v2 invariant |
|---|---|
| Static-guard-then-trust → RCE | **No agent/LLM-authored code ever executes in a privileged process.** Strategies are *declarative specs*, not code (§4, §6). |
| "Never crash" swallowing erases audit trails | **Every tool call, run transition, and money-path mutation is an append-only event** with structured errors, never a silent `except: pass` (§3, §7). |
| Multi-tenant isolation per-store, not invariant | **`tenant_id` is carried in the auth/session boundary and enforced once at the data-access seam**, not re-implemented per call site (§4.5, §7). |
| Unlocked read-modify-write on the money path | **All book/run mutations go through the control plane in serialized transactions** (`SELECT … FOR UPDATE` / optimistic version), never racing upserts (§4.4). |
| Per-call timeouts but no aggregate budget | **Every run and every tool call has a wall-clock deadline**, enforced at the gateway and the runtime (§4, §7). |
| Tests exist but don't gate; tested path ≠ shipped path | **The MCP tool contract and the deploy state machine are the gated surfaces**, with golden contract tests in CI (§7). |

---

## 1. Component map

```
                          ┌────────────────────────────────────────────────────────┐
                          │                   USER'S MACHINE / CLOUD                 │
                          │   ┌──────────────────────────────────────────────────┐  │
                          │   │  BYO AGENT (Claude / GPT / custom) — agent loop    │  │
                          │   │  runs HERE. Doomberg does NOT host it.             │  │
                          │   └───────────────┬──────────────────────────────────-┘  │
                          └───────────────────│────────────────────────────────────-─┘
                                              │ MCP (stdio or streamable-HTTP)
                                              │ tools.list / tools.call  + optional emit_reasoning
                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│  DOOMBERG CONTROL REGION                                                                         │
│                                                                                                  │
│   ┌──────────────────────────┐        ┌───────────────────────────────────────────────────┐    │
│   │  (A) MCP SERVER           │        │  (B) REST / SSE GATEWAY                            │    │
│   │  PRIMARY agent interface  │        │  Serves the web UI; auth, sessions, SSE fan-out   │    │
│   │  - auth (token → tenant)  │        │  - REST reads (runs, traces, books, panels)       │    │
│   │  - session correlation    │◄──────►│  - SSE streams (trace + run telemetry)            │    │
│   │  - per-call deadline      │ shared │  - promote/accept/reject control actions          │    │
│   │  - emits trace events     │ core   └───────────────────────────────────────────────────┘    │
│   └────────────┬─────────────┘                              ▲                                    │
│                │ both call the same in-process core         │ both publish to the same bus       │
│                ▼                                             │                                    │
│   ┌────────────────────────────────────────────┐   ┌────────┴──────────────────────────────┐   │
│   │  (C) DATA LAYER CORE  (Python)               │   │  (E) EVENT BUS / TRACE SPINE          │   │
│   │  ports v1 app/engine + app/sources           │   │  append-only run/trace events;        │   │
│   │  - sources: prices,news,edgar,congress,13f,  │   │  Postgres LISTEN/NOTIFY (launch) →     │   │
│   │    fundamentals,rates,sentiment,iex_deep…    │   │  Redis Streams (scale)                 │   │
│   │  - engine: backtest,signals,portfolio,       │   └────────┬──────────────────────────────┘   │
│   │    riskmodel,optimize,execution,paperbook,   │            │                                   │
│   │    stats,attribution,montecarlo,stress       │            │ writes events                     │
│   │  - resilience: retry/breaker/SWR cache       │            │                                   │
│   │  - PURE quant; no agent code; no I/O in engine│           │                                   │
│   └───────────────┬──────────────────────────────┘           │                                   │
│                   │ reads market data                         │                                   │
│                   ▼                                           ▼                                   │
│   ┌──────────────────────────┐   ┌────────────────────────────────────────────────────────┐    │
│   │ (F) DATASTORES           │   │  (D) DEPLOY LAYER CONTROL PLANE                          │    │
│   │  - Postgres (system of    │◄─►│  - strategy spec registry (versioned, immutable)        │    │
│   │    record: tenants, runs, │   │  - run state machine: draft→backtest→paper→retired      │    │
│   │    specs, books, events,  │   │  - schedules backtests + paper-live runs onto DO        │    │
│   │    audit, trace)          │   │  - pre-trade compliance gate (engine/compliance)        │    │
│   │  - Object store (S3/Spaces│   │  - serialized money-path mutations (FOR UPDATE)         │    │
│   │    backtest artifacts,    │   └───────────────────────┬────────────────────────────────┘    │
│   │    IEX captures, reports) │                           │ dispatch jobs / collect results       │
│   │  - TS store (Timescale)   │                           ▼                                       │
│   │    for tick/quote/curve   │   ┌────────────────────────────────────────────────────────┐    │
│   │    time-series (optional) │   │  (G) DO CPU CLUSTERS — STRATEGY RUNTIME                  │    │
│   └──────────────────────────┘   │  workers pull jobs; run backtest engine over history;   │    │
│                                   │  run paper-live loop on REAL market data → SIM book;     │    │
│                                   │  brokerage-adapter SEAM (paper adapter only at launch)   │    │
│                                   │  emit telemetry events back onto the bus (E)             │    │
│                                   └────────────────────────────────────────────────────────┘    │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────┐    │
│   │ (H) WEB UI  (React, observability surface — NO chat console)                            │    │
│   │  Tabs: Trace (agent thought process) · Trades · News / Ideas · Algos · Books            │    │
│   │  Subscribes to SSE from (B); reads REST from (B). Pure view of runs + traces.           │    │
│   └──────────────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Component responsibilities, one line each:**

- **(A) MCP server** — the *primary* product surface. Speaks MCP; advertises Data Layer + Deploy Layer tools; authenticates the agent's token → `tenant_id` + `session_id`; enforces per-call deadlines; emits a trace event for every call. Thin: it adapts MCP → the same in-process core the gateway uses.
- **(B) REST/SSE gateway** — feeds the web UI from the *same core*. Handles browser auth/sessions, serves REST reads, fans out SSE (trace + telemetry), and exposes the human control actions (accept idea, promote to paper, pause/retire). Never a second source of truth.
- **(C) Data Layer core** — the ported v1 quant brain. Pure, deterministic `engine/` (numpy) + resilient `sources/`. Exposed as MCP tools and as REST reads. *No agent code runs here.*
- **(D) Deploy Layer control plane** — owns strategy **specs** (versioned/immutable), the **run state machine**, scheduling onto DO, and the **pre-trade compliance gate**. Single writer for the money path.
- **(E) Event bus / trace spine** — append-only stream of `(run_id, seq, event)`. Postgres `LISTEN/NOTIFY` at launch (one bus, transactional with the write); Redis Streams when fan-out demands it.
- **(F) Datastores** — Postgres = system of record; object store = large artifacts; Timescale (optional) = heavy time-series.
- **(G) DO CPU clusters** — stateless workers that *execute* backtests and the paper-live loop. They run our trusted engine code against a spec; they never run agent code.
- **(H) Web UI** — observability dashboard. The chat console from v1 is removed.

---

## 2. End-to-end flows (step by step)

### (a) Agent discovers + calls a Data Layer tool to research a stock

1. User's agent opens an MCP connection to **(A)** with a Doomberg API token. (A) resolves token → `tenant_id`, mints/loads a `session_id`, and binds both into a request context (the v2 successor to v1's `tenant.py` contextvar — see §4.5).
2. Agent calls `tools.list`. (A) returns the Data Layer catalog: e.g. `get_price_history`, `get_news`, `get_fundamentals`, `get_insider_trades`, `get_congress_trades`, `get_institutional_holders`, `compute_signal`, `run_factor_model`, `screen_universe`, `estimate_execution_cost`. Each tool's schema is generated from the v1 skill/engine signatures.
3. Agent calls `tools.call("get_news", {scope_type:"symbol", scope:"NVDA"})`. (A):
   - **opens a trace span** on the bus **(E)**: `{session_id, tool:"get_news", args, ts, span_id}` (args are recorded for the UI and audit);
   - sets a **per-call deadline** (e.g. 15s) and calls the **(C)** core, which routes to `sources/news.py` through the resilience wrapper (retry/breaker/stale-while-revalidate);
   - on return, attaches the **provenance block** (`{source, asOf, freshnessSec, mode: live|stale|mock, coverage}`) — provenance is mandatory on every tool result (a v1 roadmap item promoted to a contract here);
   - **closes the span**: `{span_id, result_summary, provenance, latency_ms, ok}`.
4. (A) returns the tool result to the agent. The agent keeps researching, calling more tools. Each call is one span on the same `session_id`. The web UI **(H)** is already rendering these spans live via SSE — the user watches the agent "think" by watching the tool timeline fill in (§3).

### (b) Agent proposes a strategy

1. After research, the agent calls a Deploy Layer tool: `tools.call("propose_strategy", {spec})`. The `spec` is a **declarative strategy document**, never code: `{universe, signal_id + params, construction_scheme, rebalance, sizing, risk_limits, costs}` — every field maps to an existing `engine/` primitive (`signals.SIGNALS`, `portfolio.SCHEMES`, `strategies.STRATEGIES`, gross/net limits).
2. **(D)** validates the spec against the engine's registered signals/schemes/limits (a closed allow-list — unknown signal = rejected, not "run arbitrary code"), assigns a `strategy_id` + immutable `version`, persists it `draft`, and emits a `strategy.proposed` event.
3. The UI's **Ideas/Algos** tabs render the proposal as a structured card: the resolved signal, universe, limits, and the trace spans that led to it (the research from flow (a) is linked to this proposal by `session_id`). **Nothing is deployed yet** — proposal is inert until a human accepts.

### (c) User accepts → backtest on the Deploy Layer

1. In **(H)**, the user clicks **Accept & Backtest** (or sets a window). This is a human action through **(B)**: `POST /strategies/{id}/backtest {window, costs}`.
2. **(D)** creates a `run` row `{run_id, strategy_id, version, kind:"backtest", state:"queued", tenant_id, deadline}` and **enqueues a job** for **(G)**. State transitions are a guarded state machine (`queued→running→done|failed`), each transition an event.
3. A DO worker **(G)** claims the job, loads the spec + point-in-time history from **(F)**, and runs the **trusted** `engine/backtest.py` / `engine/portfolio.py`. It streams progress telemetry onto **(E)** (`run.progress`, partial equity curve) and writes the final artifact (equity curve, trade log, stat block, drawdown) to the object store + a summary row to Postgres.
4. **(B)** fans the telemetry to **(H)**; the Backtest panel animates the equity curve as it computes, then shows the final stat block with the integrity/provenance badge (rigor mode: common calendar, non-overlapping forward windows — a v1 correctness fix baked into the contract).

### (d) User promotes → paper-live deployment

1. User clicks **Promote to Paper** in **(H)** → `POST /strategies/{id}/promote {to:"paper", criteria}` on **(B)**.
2. **(D)** runs the **pre-trade compliance gate** (ported `engine/compliance.py`: gross/net exposure, per-name caps, restricted lists). If it fails, the promotion is **blocked** and the reason is surfaced as a structured event — never silently. The optimizer/gate re-checks `sum|w|` against the gross limit *after* projection (closes the v1 optimizer over-exposure bug).
3. On pass, **(D)** opens a `run {kind:"paper", state:"running"}` and a **paper book** (fixed positions + cash, built via `engine/execution.generate_orders` and marked by `engine/paperbook.py`). It schedules a **long-lived paper-live job** on **(G)**.
4. The DO worker runs the paper-live loop: on each market tick/bar (REAL market data from **(C)** sources), it re-evaluates the spec's signal, diffs target vs current book, routes orders through the **brokerage-adapter seam** — which at launch is the **paper/sim adapter only** (fills against a simulated book; NO real brokerage, NO real money). Each fill, mark, and rebalance is an event on **(E)**.
5. **Money-path mutations** (book updates) happen *only* in **(D)** under a serialized transaction (`SELECT … FOR UPDATE` or optimistic version) — never a racing upsert from a worker and an API call (closes the v1 lost-update bug). The worker proposes deltas; (D) applies them atomically.

### (e) The web UI renders the whole thing

1. On load, **(H)** authenticates to **(B)**, gets the tenant's active sessions/runs, and opens an **SSE stream per active view** (one for the live trace, one for run telemetry).
2. The stream replays from a `last_seq` cursor (so a reconnect or a freshly-opened tab catches up deterministically — see §3 replay), then tails live.
3. Tabs are pure projections of events: **Trace** (the agent's tool timeline + reasoning), **Trades** (fills from paper runs), **News/Ideas** (research + proposals), **Algos** (specs + their run states), **Books** (live P&L from `paperbook`). Each panel has a top-level + per-panel error boundary so one bad field downgrades a tile, not the session (closes v1's missing boundaries). No chat console.

---

## 3. THE HARD PROBLEM — capturing & rendering a thought process we don't own

The agent runs on the user's side. Doomberg cannot see the agent's hidden chain-of-thought. We can only see what crosses the MCP wire. The design principle: **make the MCP wire itself the trace**, and add one *optional* channel for volunteered reasoning. Three mechanisms, in priority order.

### 3.1 MCP session correlation (the backbone — always available)

Every MCP connection carries a token → `(tenant_id, agent_id)`. (A) assigns a `session_id` to the connection (or honors an `X-Doomberg-Run` header the agent may set to bind a sequence of calls to a named investigation). **Every `tools.call` is automatically a trace event** — we own the server side of the call, so we record, with zero cooperation required from the agent:

```jsonc
// trace event, written transactionally with the tool's side effects
{
  "run_id":     "sess_7Kp…",      // session or explicit run binding
  "seq":        412,               // monotonic per run_id (gap-free ordering)
  "type":       "tool_call",
  "span_id":    "sp_91a",
  "tool":       "get_news",
  "args":       { "scope_type":"symbol", "scope":"NVDA" },
  "ts":         "2026-06-16T18:02:11.220Z"
}
{
  "run_id":"sess_7Kp…", "seq":413, "type":"tool_result", "span_id":"sp_91a",
  "ok": true,
  "result_summary": { "headlines": 12, "top": "NVDA guidance raise" },
  "provenance": { "source":"yahoo_rss", "asOf":"…", "mode":"live", "coverage":1.0 },
  "latency_ms": 380
}
```

This alone reconstructs **what** the agent did and **in what order** — the tool-call timeline is the spine of the UI's Trace tab. It needs no trust in agent-supplied text and survives any agent implementation.

### 3.2 Optional `emit_reasoning` tool (the "why" — volunteered, never trusted)

The tool timeline shows *what* but not *why*. To capture intermediate reasoning, the Data Layer advertises a first-class, side-effect-free MCP tool:

```
emit_reasoning({ kind: "thought"|"hypothesis"|"decision"|"plan_step",
                 text: string, refs?: [span_id], confidence?: number })
```

Well-behaved agents (Claude/GPT with tool use) call this between research steps to narrate their reasoning; it returns `{ok:true}` and emits a `reasoning` event onto the bus, ordered into the same `seq` stream so it interleaves correctly with tool calls. Because it is **just another tool call**, it needs no special protocol, works over stdio or HTTP MCP, and the UI renders it inline with the tool timeline as the agent's "thought bubbles." It is **display + audit only** — reasoning text never influences control-plane decisions, so a lying or absent agent degrades the *richness* of the trace but can never affect money-path behavior. (This is the inverse of v1's mistake: v1 *trusted* LLM output to the point of executing it; here agent text is purely observed.)

We make `emit_reasoning` attractive by documenting in each tool description that "narrating your reasoning with `emit_reasoning` makes the user's dashboard show your thought process." For agents that won't call it, §3.3 provides a fallback.

### 3.3 Inferred reasoning fallback (best-effort, clearly labeled)

If an agent emits no reasoning, (A) can synthesize lightweight *derived* trace annotations from the call pattern itself — e.g. grouping a burst of `get_fundamentals` + `compute_signal` + `propose_strategy` into a "research → decision" arc with a templated, **non-LLM**, deterministic label ("evaluated 3 signals on a 12-name universe"). These are tagged `derived:true` in the UI so the user knows they're inferred, not the agent's own words. No hidden LLM is invoked to fabricate reasoning (that would be a trust-killer and a cost sink).

### 3.4 The session/trace data model

```
trace_event
  run_id        text     -- session_id OR explicit run binding (FK to run when promoted)
  seq           bigint   -- gap-free, monotonic per run_id (assigned by the writer txn)
  type          enum     -- tool_call | tool_result | reasoning | run_state | run_progress
                          --  | fill | mark | proposal | compliance | error
  span_id       text     -- correlates a call to its result
  parent_span   text     -- nesting (a deploy tool that fans out to data tools)
  payload       jsonb    -- type-specific (args/result/text/state…)
  provenance    jsonb    -- on data results
  tenant_id     text     -- enforced at the data-access seam
  ts            timestamptz
  PRIMARY KEY (run_id, seq)
```

- **Association to a `run_id`:** research happens under a `session_id`. When the agent calls `propose_strategy`, the resulting `strategy_id` records its `origin_session_id`, so the run's trace can show *"this algo came from this research."* When the user backtests/promotes, a new `run_id` is created whose trace **links back** to the originating session via `parent_span`/`origin_session_id`. One unbroken chain: research → proposal → backtest → paper.
- **SSE replay:** the gateway **(B)** exposes `GET /streams/{run_id}?from_seq=N`. On connect it replays events `> N` from Postgres, then tails live (via `LISTEN/NOTIFY` → in-process fan-out). The client tracks `last_seq` and reconnects with it, so refreshes/disconnects never lose or duplicate events. Because `seq` is gap-free per `run_id`, the UI can detect a gap and re-fetch deterministically (fixes v1's "superseded stream clobbers newer answer" race — ordering is explicit, not implicit on arrival time).
- **Heartbeat:** during long blocking work (a slow tool, a long backtest), the writer emits `: keepalive` comments on SSE and `run_progress` events, so idle-timeout proxies never kill the stream (fixes v1's missing-heartbeat bug).

---

## 4. Boundaries & contracts between layers

Three hard seams. Each layer owns its data and exposes a narrow, versioned surface.

### 4.1 Agent ↔ Doomberg (the MCP contract) — *the* product API
- **Owns:** (A). **Surface:** MCP `tools.list` / `tools.call` + `emit_reasoning`.
- **Contract:** every tool has a JSON-Schema'd input, a typed output **with a mandatory provenance block**, a declared per-call deadline, and a stable name+version. Tools are pure reads (Data Layer) or guarded control proposals (`propose_strategy` is the only Deploy Layer tool the agent can call directly; **the agent cannot promote to paper or move money** — that requires a human action through (B)).
- **Invariant:** the agent is a *client*. It can read data and *propose*; it can never deploy, promote, or mutate a book.

### 4.2 Gateway ↔ Core (in-process function calls)
- **(A) and (B) are thin adapters over one shared Python core.** Both call the same `core.run_tool(name, args, ctx)` and `core.read(view, ctx)`. This guarantees the MCP path and the UI path can never diverge (v1 had a single FastAPI app; v2 keeps one core but two front doors). `ctx` carries `tenant_id`, `session_id`, `actor`, `deadline`.

### 4.3 Core ↔ Deploy control plane (internal API)
- **Owns:** (D) owns specs, runs, books, the state machine, and the compliance gate. **Surface:** `create_run`, `transition_run`, `apply_book_delta`, `evaluate_gate`.
- **Contract:** the spec is a **closed, declarative schema** validated against the engine's allow-list of signals/schemes/limits. Unknown field or signal → typed rejection. **No free-form code field exists.**

### 4.4 Control plane ↔ DO runtime (job contract)
- **Owns:** (G) executes; (D) schedules and is the **single writer** of books. **Surface:** workers *pull* jobs `{run_id, spec, version, window|live, deadline}`, *stream* telemetry events, and *propose* book deltas — they never write the book directly.
- **Invariant (money path):** all book mutations are applied by (D) in one serialized transaction (`FOR UPDATE` / optimistic `version`). A worker crash leaves the book consistent; a duplicate job is idempotent on `(run_id, seq)`.
- **Invariant (deadline):** every run carries a wall-clock deadline; (G) checks it inside its loops (no unbounded streams — fixes v1's 13 GB IEX reconstruct that had per-read but no aggregate timeout).

### 4.5 Tenancy & identity (cross-cutting, enforced once)
- `tenant_id` is resolved at the **two front doors only** (MCP token in (A); browser session in (B)) and bound into `ctx`. The **data-access layer in (F) is the single enforcement point**: every query is tenant-scoped by the data layer, not by each call site. Stores never accept an unscoped read. This makes isolation an **invariant**, fixing v1's per-store leaks (template store, in-memory dashboard IDOR, global generated-skill registry).

---

## 5. Tech-stack recommendation per component

| Component | Recommendation | Rationale |
|---|---|---|
| **(C) Data Layer core** | **Python 3.12**, numpy. **Port v1 `app/engine/` + `app/sources/` as-is.** | The quant logic is proven, pure, deterministic, and already unit-testable (engine has no I/O). Rewriting numpy quant in another language is pure downside risk. Keep it. |
| **(A) MCP server** | **Python**, official **MCP Python SDK**, `streamable-http` transport for hosted agents + `stdio` for local. Runs in the same process/image as the core. | MCP is the primary interface; the SDK is first-class in Python; co-locating with the core means tool calls are in-process function calls, not a network hop. One language for the whole quant+tool surface. |
| **(B) REST/SSE gateway** | **Python + FastAPI** (Starlette `StreamingResponse` for SSE) — *same app as v1's proven pattern, minus the chat/orchestrator.* | v1 already runs FastAPI with working SSE and the tenant contextvar; reuse it. Sharing the process with the core avoids a second source of truth. Async-friendly for SSE fan-out. |
| **(D) Deploy control plane** | **Python + FastAPI**, but a **separate deployable service** from the gateway. State machine as explicit table + transitions; compliance gate ports `engine/compliance.py`. | It's the money-path single-writer; isolating it as its own service lets it scale, deploy, and be hardened independently (and keeps its blast radius small). Python keeps it next to the engine it gates against. If we later want stronger compile-time guarantees on the state machine, **Go** is the fallback — but launch in Python to avoid a polyglot tax on day one. |
| **(G) DO runtime workers** | **Python** workers (same engine image), containerized, on **DigitalOcean droplets/k8s CPU pool**. Pull jobs from a queue. | They run the *same* trusted engine code as the core — sharing the image guarantees backtest≡paper math. CPU-bound numpy work fits DO CPU clusters (the locked decision). Stateless + pull-based = trivially horizontally scalable. |
| **(E) Event bus / trace** | **Launch: Postgres `LISTEN/NOTIFY`** (events written transactionally with their side effects). **Scale: Redis Streams.** | At launch, transactional writes + NOTIFY give exactly-once, gap-free ordering for free and one fewer moving part. Swap to Redis Streams only when fan-out/throughput demands it; the `(run_id, seq)` model is bus-agnostic. |
| **(F) Datastores** | **Postgres 16** (system of record: tenants, specs, runs, books, `trace_event`, audit). **DO Spaces / S3** (backtest artifacts, IEX captures, reports). **TimescaleDB** (optional, for heavy tick/quote/curve series). | Postgres is the v1 datastore and gives row-locks (`FOR UPDATE`) the money path needs. Object store for large blobs keeps Postgres lean. Timescale only if tick volume justifies it — don't add it speculatively. |
| **(H) Web UI** | **React + TypeScript + Vite**, SSE via `EventSource`, typed API via **Zod schemas / Orval codegen from an OpenAPI spec** (the lib/ packages already in the repo). | The repo already ships `lib/api-zod`, `lib/api-client-react`, and Orval codegen — reuse them so the UI's types are generated from the contract, not hand-kept. Keep the v1 "terminal" visual feel; drop the chat console; add error boundaries app-shell + per-panel. |
| **Cross-cutting: resilience** | Port v1 `sources/_resilient.py` (retry/backoff/jitter + per-source circuit breaker) and add a **stale-while-revalidate / last-known-good tier** so a tool returns `mode:"stale"` with a real `asOf` instead of fabricating mock. | Directly addresses two v1 themes: silent mock-for-real swaps and unprotected fetches (Treasury/FRED bypassed the wrapper). Provenance becomes truthful by construction. |
| **Cross-cutting: tests/CI** | **pytest** gating the **MCP tool contract** (golden schemas + provenance present), the **deploy state machine** (illegal transitions rejected), and the **money-path serialization** (concurrent delta test). Real CI (`.github/workflows`) that runs the full suite. | v1's defining test failure was that the shipped paths weren't the gated paths. v2 gates exactly the two contracts that matter (tool surface + state machine) so isolation, deadlines, and money-path invariants can't silently regress. |

---

## 6. What we explicitly DROP from v1 (and why)

- **Runtime AI codegen / self-building skills** (`dynamic_skills.py`, `feature_builder.py`, `code_guard.py`, `skills_generated/`, the client `new Function` panel eval). These were the source of both critical RCEs (static-guard-then-trust). v2 has **no path that executes agent- or LLM-authored code in a privileged process.** Strategies are *declarative specs* over a closed engine allow-list. *If* dynamic, user-defined panels ever return, they do so only as a declarative non-executable schema or in a sandboxed cross-origin iframe — not by executing generated code server-side.
- **The orchestrator / 197-branch intent heuristic** (`agent.py`). Doomberg no longer runs an agent loop or decides which panels to build — the external agent does. The keyword cascade and its mis-routing class of bugs are deleted, not ported.
- **The chat console.** The UI is an observability surface, not a conversation.

---

## 7. How each v1 invariant is structurally enforced (summary)

1. **No untrusted code execution** → no code field anywhere; specs are declarative; engine runs only trusted code; agent is a read/propose client. (§4.1, §6)
2. **No silent swallowing** → every tool call, transition, fill, and gate result is an append-only `trace_event`; errors are typed events, not `except: pass`. (§3, §4)
3. **Tenancy is an invariant** → resolved at the two front doors, enforced once at the data-access seam in (F). (§4.5)
4. **Money path serialized** → (D) is the single writer; all book deltas in `FOR UPDATE`/versioned transactions; workers only propose. (§4.4)
5. **Aggregate deadlines** → every run and tool call carries a wall-clock deadline checked inside the loops, at the gateway and the runtime. (§4.4, §5)
6. **Gated contracts = shipped contracts** → CI gates the MCP tool contract and the deploy state machine, the two surfaces everything else depends on. (§5)

---

## 8. Open questions for downstream designs (this doc deliberately defers)

- **Exact MCP tool catalog & schemas** (Data Layer design): which v1 skills become which tools, arg shapes, output schemas.
- **Spec schema in full** (Deploy Layer design): the complete declarative strategy document and its validation rules.
- **Paper-live loop cadence & market-data plumbing** (Deploy/runtime design): tick vs bar, EOD marking, the brokerage-adapter seam interface.
- **UI information architecture** (design track): Trace/Trades/Ideas/Algos/Books layout, the thought-process visualization.
- **AuthN/Z model** (security track): agent token issuance, scopes, human roles for accept/promote.
```



====================================================================================================
FILE: docs/plans/doomberg-v2/DATA-SOURCING-STRATEGY.md
====================================================================================================

# Doomberg v2 — Real Data Sourcing Strategy

**Status:** proposed (reworks the data decision in MASTER-PLAN §2.4 / §4 / §10) • **Date:** 2026-06-16
**Decision driver:** The founder has rejected free Yahoo data. v1/v2-draft assumed Yahoo, which forced §2.4's painful compromise — fundamental-factor backtests forbidden, the backtester flagged as one that "lies" because Yahoo is survivorship-biased, dividend-restated, and has no point-in-time vintaging. **New mandate: source official data the way professionals do — direct from exchanges and professional providers.** This doc researches how that actually works (verified against the 2025–2026 landscape, cited inline) and designs the real strategy.

> **TL;DR for the impatient.** "Direct from the exchange the way Bloomberg does it" is a multi-million-dollar/year infrastructure build (colo cages, FPGA ticker plants, per-exchange non-display + redistribution fees), and Bloomberg itself sells you a *normalized* feed rather than the raw exchange firehose. For a startup, "official quality" is achieved by buying from vendors that *themselves* take direct exchange feeds. The single highest-leverage purchase for Doomberg is **not** a real-time feed at all — it is a **point-in-time (PIT), survivorship-bias-free historical dataset** (Sharadar, then optionally CRSP/Norgate). That one purchase unblocks the headline product capability the plan currently has on the cut list: **honest fundamental-factor backtesting.** Recommendation: launch on **Sharadar (PIT research) + Databento (direct-feed prices/intraday/order-book) + Alpaca (broker-grade SIP for paper-live)**, and treat the "direct feeds + colo" endgame as a graduation trigger, not a launch requirement.

---

## 1. How Bloomberg / institutional data actually works

There are three layers in the professional pipeline. Understanding which layer you are actually buying is the whole game.

### 1.1 Layer 1 — Direct exchange feeds (raw, per-venue, un-normalized)

Each exchange generates its own proprietary feed straight off its matching engine. These are the lowest-latency, highest-fidelity source — but every venue speaks its own binary protocol and schema, so a consumer must run a per-exchange decoder and normalize the output itself.

- **Nasdaq TotalView-ITCH** (plus separate feeds for Nasdaq BX and PSX) is a full **depth-of-book** feed: every order add/modify/cancel/execution at every price level, enough to reconstruct queue position and quote lifetimes. Wire format is the **ITCH binary protocol**, disseminated as **multicast UDP** with A/B redundant lines and a separate retransmission/glimpse recovery service, sourced at the Carteret, NJ matching engine ([Nasdaq TotalView-ITCH spec](https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/NQTVITCHSpecification.pdf), [Databento XNAS.ITCH](https://databento.com/datasets/XNAS.ITCH)). Full order-by-order tick data runs to tens of GB/day uncompressed.
- **NYSE Pillar / Integrated Feed** uses the **XDP** binary protocol over **multicast UDP**, carrying complete depth of book, all trades, security status, and opening/closing **imbalance** data, with per-channel A/B line redundancy ([NYSE XDP Integrated Feed Client Spec](https://www.nyse.com/publicdocs/nyse/data/Integrated_Feed_Client_Specification_v2.3d.pdf)).
- **Cboe** (BZX/BYX/EDGA/EDGX) publishes **PITCH** (depth) and **TOP** (top-of-book); Cboe states TOP is "less timely" than the depth feed and offers bandwidth-shaped Multicast PITCH variants ([Cboe Multicast PITCH spec](https://www.cboe.com/document/tech-spec/document/technical-specifications/cboe-titanium-u.s.-equitiesoptions-multicast-pitch-specification)).

**Key property:** these feeds are **raw and un-normalized** — different protocols (ITCH vs XDP vs PITCH), different message semantics, different symbology. "Getting data directly from the exchange" means decoding each venue's wire format and stitching them together yourself. Direct feeds also carry data the public tape omits — trade aggressor side, odd-lot quotes, auction imbalances — and odd-lots alone are nearly **50% of US equity activity not reported to the SIPs** ([Databento — proprietary feeds vs SIP](https://databento.com/blog/proprietary-feeds-vs-sip-data)).

### 1.2 Layer 2 — The consolidated SIP tapes (the regulated public price)

A **Securities Information Processor (SIP)** consolidates quotes and trades from all US exchanges and publishes the **NBBO** — the regulated, single public reference price. SIP data is **Level 1** (top-of-book best quotes + trades), aggregated across all venues. It is split across plans/tapes:
- **CTA/CQS — Tape A** (NYSE-listed) and **Tape B** (NYSE Arca/American + other non-Nasdaq listed), via CTS (trades) and CQS (quotes).
- **UTP — Tape C** (Nasdaq-listed + OTC), via UTDF/UQDF.
- (Options consolidate separately via **OPRA**.) ([Securities Information Processor — Wikipedia](https://en.wikipedia.org/wiki/Securities_information_processor), [Databento — CTA Plan](https://databento.com/microstructure/cta-plan))

**SIP modernization status (2025–2026):** The SEC's 2020 **Market Data Infrastructure Rule** (upheld by the D.C. Circuit in 2022) expanded SIP content and replaced the single-SIP model with **competing consolidators + self-aggregators** ([Sidley](https://www.sidley.com/en/insights/newsupdates/2022/06/dc-circuit-upholds-secs-market-data-infrastructure-rules-paving-the-way-for-competing-consolidators)). The three legacy plans are slated to merge into a **single CT Plan in April 2027**, with **DataCT** selected as administrator; CT Plan fee filings are under SEC review and contested (SIFMA objected Aug 2025), and **no competing consolidator is yet live at scale** ([SIFMA letter Aug 2025](https://www.sifma.org/wp-content/uploads/2025/08/SIFMA-Letter-re-Equity-Market-Data-8.25.2025.pdf), [Traders Magazine](https://www.tradersmagazine.com/am/market-data-competing-consolidators-without-ct-plan/)). Practical implication for Doomberg: the SIP landscape is mid-reform but stable enough to consume through a vendor; don't build against competing-consolidator economics yet.

**SIP latency vs direct feeds:** the SIP must aggregate from venues dispersed across the NJ data centers and adds normalization time. The CTA SIP's internal compile latency has fallen to ~15 µs, but a Carteret quote still arrives ~188 µs slower than a Mahwah quote purely from speed-of-light over ~35 miles ([Bloomberg — SIP vs Direct Feeds](https://www.bloomberg.com/professional/blog/sip-vs-direct-feeds-latency-rules/)). Net: direct feeds are single-digit microseconds; consolidated/normalized paths are milliseconds. This gap is the basis of latency-arbitrage concerns — **and it is completely irrelevant to a research-and-paper-trading platform** (see §4).

### 1.3 Layer 3 — Normalized professional feeds (how firms actually consume data)

Most firms do **not** build colo ticker plants. They buy a **managed, normalized feed**: one pre-normalized stream over a single API across hundreds of venues, with the vendor handling connectivity, decoding, normalization, symbology, entitlements, and gap recovery — trading microsecond latency for radically lower operational burden.

- **Bloomberg B-PIPE** is a consolidated normalized real-time feed aggregating ~35M instruments from 330+ exchanges and 5,000+ contributors via one API, supporting display and **non-display ("black box")** applications — explicitly so firms avoid managing direct connections to each exchange ([Bloomberg Real-Time Data Feed / B-PIPE](https://professional.bloomberg.com/products/data/enterprise-catalog/real-time-data-feed/)).
- **LSEG/Refinitiv Real-Time** (formerly Elektron/RTDS/TREP) is the equivalent enterprise feed + in-house distribution system, with proximity/colo hosting options ([LSEG data feeds](https://www.lseg.com/en/data-analytics/market-data/data-feeds)).
- **ICE Consolidated Feed** normalizes 600+ sources / 300+ exchanges / 25M+ instruments with L1 and full L2 order book across asset classes ([ICE Consolidated Feed](https://www.ice.com/fixed-income-data-services/access-and-delivery/connectivity-and-feeds/consolidated-feed)).

**The load-bearing insight:** *Bloomberg itself sells a normalized feed, not the raw exchange firehose.* "The way Bloomberg does it" already means **Layer 3**. Going to Layer 1 is for latency-sensitive trading, not for research/backtest/paper platforms.

### 1.4 What "direct from the exchange" actually requires

It is an operational build, not a subscription:
- **Co-location cage/rack** in the exchange data center (Equinix NY4/NY5 Secaucus, NYSE Mahwah, Nasdaq Carteret), with power and space — or rent a **hosted ticker-plant** ([Exegy Hosted Ticker Plant](https://www.exegy.com/products/hosted-ticker-plant/)).
- **Cross-connects / 10–100 GbE handoff** to receive the exchange's multicast UDP groups (A/B lines).
- **Feed handler / ticker plant software** per venue: join multicast, decode the binary protocol, do A/B line arbitration, build/maintain the order book, handle sequence-gap detection + retransmission, and **normalize** into one schema + symbology. Vendors: **Exegy** (merged with Vela; SMDS/nxFeed/XTP, FPGA), **Pico/Redline** (InRush ticker plant), **NovaSparks** (pure FPGA, sub-µs), **OnixS** (build-your-own SDKs), **Enyx** (FPGA cards) ([Exegy Ticker Plant](https://www.exegy.com/products/exegy-ticker-plant/), [Pico InRush](https://www.pico.net/redline-software/inrush-ticker-plant/), [NovaSparks](https://novasparks.com/novasparks-is-voted-best-high-performance-data-feed-handler/)).
- **FPGA acceleration** for the lowest tier (sub-µs / nanosecond decode), plus **microwave transport** (McKay Brothers/Quincy) between venues.
- **Per-exchange data-license fees** on top of all of it (§2).

This is the Bloomberg/Citadel-grade build. **Doomberg does not need any of it.** The endgame for Doomberg (if it ever arrives) is at most a *normalized direct-feed vendor* (Databento), not a self-operated colo ticker plant.

---

## 2. The licensing & cost reality (the part founders underestimate)

Exchange fee schedules are assembled from stacked components — you almost never pay just one:

| Component | Charges for | Unit |
|---|---|---|
| **Access fee** | The right to receive the feed at all | flat $/mo per product |
| **Per-user / per-device** | Each human who *views* the data (display) | $/user/mo, split Pro vs Non-Pro |
| **Non-display fee** | Any *machine/automated* consumption | flat $/mo per category, per product |
| **Redistribution fee** | The right to pass data to external parties | flat $/mo |
| **Enterprise license** | Buy-out of per-user counting | large flat $/mo or annual |

Source: [Exegy — Market Data Fees: planning infrastructure](https://www.exegy.com/market-data-fees-planning-infrastructure/).

### 2.1 Concrete published figures

**Nasdaq** (US Equities Price List 2025–2027) ([PDF](https://www.nasdaqtrader.com/content/ProductsServices/PriceList/Nasdaq_US_Equities_Price_List_2025_2026_2027.pdf)):
- TotalView display: **Professional $80.50/user/mo** vs **Non-Professional $15.00/user/mo** (2025).
- TotalView **Non-Display**, per firm/mo, tiered: 40–99 subs **$15,840**; 100–249 **$31,680**; **250+ $75,000**.
- TotalView Enterprise License **$25,000/mo** + depth subscriber fees; Non-Display Enterprise (Direct Access) **$75,000/mo**.

**NYSE** (Proprietary Market Data Fee Schedule, as of 2026-03-16) ([PDF](https://www.nyse.com/publicdocs/nyse/data/NYSE_Market_Data_Fee_Schedule.pdf)):
- Integrated Feed: Access **$8,400/mo**; Pro user **$78/mo**; Non-Pro **$16/mo**; **Non-Display $22,400/mo per category** (cap $67,200); Redistribution **$4,400/mo**.
- So NYSE Integrated alone, one non-display category + redistribution = **~$35,200/mo (~$422k/yr)** before any per-user fees — *for one exchange's feed*.

### 2.2 Professional vs Non-Professional (an order-of-magnitude lever)

The gap is ~5x on depth feeds (Nasdaq $80.50 vs $15.00; NYSE $78 vs $16) and up to 27x on Nasdaq Basic. To qualify as **Non-Professional** you must be a *natural person*, use the data *only for personal use*, *not be registered/qualified* with any securities regulator, *not be an investment adviser*, and *trade only your own capital* ([Interactive Brokers definitions](https://www.interactivebrokers.com/en/accounts/fees/professionalDefinations.php), [NYSE Non-Professional Subscriber Policy](https://www.nyse.com/publicdocs/nyse/data/Policy-Non-ProfessionalSubscribers_PDP.pdf)). **For a B2B/agent platform, assume essentially every user is Professional** — and assume audits will reclassify aggressively ("professional-user creep").

### 2.3 Non-display use — the dominant cost for an AI-agent platform

**Non-display = any use that does not put the data on a screen for a human.** This explicitly includes algorithmic trading, automated decision systems, analytics pipelines — and **feeding quotes to an AI agent or model.** If a machine "reads" the quote, it is non-display, charged as a **flat, large, per-firm fee** with no Non-Pro discount. NYSE's categories: **Cat 1** = on your own behalf; **Cat 2** = on behalf of clients; **Cat 3** = internal order matching ([NYSE fee schedule](https://www.nyse.com/publicdocs/nyse/data/NYSE_Market_Data_Fee_Schedule.pdf)). Nasdaq mirrors this ([Nasdaq Data Policies](https://www.nasdaqtrader.com/content/AdministrationSupport/Policy/USEquitiesandOptionsDataPolicies.pdf)).

> **This is THE gotcha for Doomberg.** A platform where external agents consume real-time quotes is, by definition, **non-display, Category 2 (on behalf of clients)** use. If Doomberg held the exchange feeds directly, it would owe the firmwide non-display fee for *every exchange feed its agents touch* — independent of having 10 customers or 10,000. That is the line that turns "we have a handful of pilot users" into "$400k+/yr in data fees." **The architecture must route this through a vendor that already holds those licenses, and lean on the derived-data path (§2.5) and EOD/PIT data wherever possible.**

The SIP non-display equivalent runs ~$9,500/mo per system per tape on top of proprietary feeds ([Intrinio — NYSE/CTA tapes](https://intrinio.com/blog/understanding-nyse-cta-tapes-a-b-and-c)).

### 2.4 Redistribution — what you must do to serve data downstream

If you serve exchange data to customers (even normalized, even via API) you are a **redistributor** and need a vendor/distributor agreement on top of data fees. Obligations: sign each plan/exchange vendor agreement and pay redistribution fees; **operate an entitlement system** classifying each recipient Pro/Non-Pro and **retain entitlement reports ≥3 years post-termination**; **report subscriber counts monthly**; **file the annual Non-Display Use Declaration by Jan 31** (else $1,000/mo/product late fee); and **submit to audits** ([Nasdaq UTP Vendor Agreement](https://www.utpplan.com/DOC/VendorAgreement.pdf), [NYSE Market Data Vendor Guide](https://www.nyse.com/publicdocs/ctaplan/notifications/trader-update/NYSE%20Market%20Data%20Vendor%20Guide.pdf)). **Delayed (15-min) and EOD data carry far lighter obligations** — a key escape hatch.

### 2.5 Derived data — when computed outputs escape per-quote licensing

"Derived data" = new works computed from raw data that **cannot be reverse-engineered back into, and are not substantially similar to, the original** — a signal value, a volatility surface, a backtest equity curve, a buy/sell conclusion, an aggregated statistic ([Markets Media — Complexities in Market Data Licensing](https://www.marketsmedia.com/complexities-expand-in-market-data-licensing/)). Genuinely derived output may escape per-quote *display/redistribution* licensing. **Catches:** (a) computing it still requires a **non-display license on the input**; (b) exchanges increasingly require a specific derived-data license (Nasdaq lists a Non-Professional Derived Data License at $1,500/firm/mo); (c) "derived enough" is judged after the fact in audits.

> **Strategic fit:** Doomberg's product is *literally* a derived-data engine — agents receive signals, factor scores, backtest curves, risk decompositions, **not raw redistributed quotes.** The provenance/`panelType` contract already serves computed conclusions. This is the legitimate path to minimize output licensing. We still pay the *input* non-display license — which is exactly why we buy it from a vendor.

### 2.6 Realistic annual cost tiers

| Path | Realistic annual cost |
|---|---|
| Vendor API, internal/display-only, small | **$2k–$10k** |
| Vendor API, redistribution + some non-display (agent consumption) | **~$30k–$150k** |
| Direct proprietary depth feeds + non-display + redistribution + colo (full US equities) | **~$1M–$2M+** |

The direct-feed figure is grounded: Exegy's worked example totals ~$111,020/mo (~$1.3M/yr) in **exchange data fees alone** for full US equity depth feeds with one non-display category + redistribution, before colo/FPGA/connectivity (commonly another $100k–$500k+/yr) ([Exegy](https://www.exegy.com/market-data-fees-planning-infrastructure/)).

### 2.7 The friction founders underestimate

1. **Audits are routine, not hypothetical** — exchanges audit the **3 prior years** of entitlement records, MISU firms annually at their own expense ([CTA MISU Policy](https://www.nyse.com/publicdocs/nyse/data/MISU_Policy_with_FAQ.pdf)).
2. **"You owe back-fees"** — underreporting triggers retroactive liability + interest (Nasdaq UTP: pay within 15 days of discovery); a 3-year window + a misclassification = six-figure surprise invoice.
3. **You pay the auditor** if a shortfall ≥~10% / material breach is found (CME, ICE).
4. **Continuous reporting burden** — monthly counts, 3-year retention, annual non-display declaration.
5. **Derived-data ambiguity** is decided by the exchange in an audit, not by you at design time — document derivation logic.

---

## 3. The realistic vendor menu for a startup

> Sourcing caveat: several pricing pages are JS-rendered or login-gated; dollar figures are from vendor blog/announcement posts, docs, and recent third-party reviews, flagged where a single source couldn't be cross-confirmed. **Polygon.io rebranded to "Massive" (massive.com) on 2025-10-30**; `api.polygon.io` still works ([massive.com/blog/polygon-is-now-massive](https://massive.com/blog/polygon-is-now-massive)). **CRSP was acquired by Morningstar (~$365M, announced Sept 2025, completed ~Feb 2026)** — a continuity flag ([Wikipedia — CRSP](https://en.wikipedia.org/wiki/Center_for_Research_in_Security_Prices)).

### Tier A — Direct-feed / consolidated real-time vendors

**Databento** — genuine **direct exchange feeds captured in colocation**: NYSE/Arca/Amex via **Pillar**, Nasdaq venues via **TotalView-ITCH**, cross-connects in NY4 + CME Aurora ([introducing-databento-us-equities](https://databento.com/blog/introducing-databento-us-equities), [CME vendor page](https://www.cmegroup.com/solutions/market-tech-and-data-services/technology-vendor-services/databento.html)). Unified live + historical API, one normalized schema (DBN), Python/C++/Rust clients, L2/L3 order book. **PIT-grade extras:** a **Security Master** with PIT historical identifiers/status, 18 yrs, listed + delisted (survivorship-free) ([databento.com/security-master](https://databento.com/security-master)); a **Corporate Actions** product (~6 yrs PIT, 215 exchanges, 60+ event types) ([corporate-actions](https://databento.com/blog/corporate-actions)). **Pricing:** historical is **pay-as-you-go**; live moved to subscription Jan 2025, **Standard ~$199/mo** + enterprise tiers ([Jan 2025 pricing](https://databento.com/blog/upcoming-changes-to-pricing-plans-in-january-2025)). **Good at:** real protocols, order-book depth, PIT security master + corp actions, best-in-class DX, pay-as-you-go history. **Bad at:** no fundamentals/estimates; corp-action history only ~6 yr; live needs a subscription.

**Polygon.io / Massive** — **SIP-consolidated** (CTA+UTP), *not* direct ITCH/Pillar colo. REST + WebSocket + **bulk flat files** (S3 history). Ticker-centric "PIT-by-ticker," served to delisting date, but reviewers flag data-quality gaps (dividends, missing/dup trades, delisted metadata) ([review](https://medium.com/@yolotrading/a-complete-review-of-the-polygon-io-api-everything-you-wanted-to-know-c79e992a74ff)). **Pricing (per asset class):** Free $0; Stocks ~Starter $29 / Developer $79 / **Advanced ~$199** ([roundup](https://www.mexc.com/news/476023)). **Good at:** low cost, fast/stable API, WebSocket, flat files, easy onboarding. **Bad at:** SIP-only (no direct-feed depth), data-quality concerns, no fundamentals/PIT, per-asset-class billing.

**ICE Data Services — Consolidated Feed** — enterprise normalized feed, 600+ sources / 300+ exchanges / 25M+ instruments, L1/L2/L3 all asset classes, evaluated bond pricing, 10+ yr tick history ([Consolidated Feed](https://www.ice.com/fixed-income-data-services/access-and-delivery/connectivity-and-feeds/consolidated-feed)). **Enterprise/contract-only**, opaque pricing. **Good at:** breadth, full book, deep history, reliability. **Bad at:** no self-serve, overkill for a startup.

**LSEG / Refinitiv** — Real-Time (cloud + RTDS on-prem) and **Real-Time Direct/Ultra Direct** for true direct feeds; **Tick History (TRTH)** to **Jan 1996** incl. **PCAP** with GPS-nanosecond timestamps "sourced directly from exchanges" ([tick-history](https://www.lseg.com/en/data-analytics/market-data/data-feeds/tick-history)); fundamentals via Datastream/Worldscope; proprietary **RIC** symbology. PIT fundamentals exist but are a **paid add-on, not the default**. **Enterprise/quote-only**, six-figure+. **Good at:** deepest tick history + genuine direct PCAP, global breadth. **Bad at:** procurement friction, RIC lock-in, PIT fundamentals must be stitched together.

### Tier B — Affordable API-first feeds (operational live + recent history)

**Intrinio** — real-time/delayed/EOD + 50yr history; options; **both as-reported and standardized SEC fundamentals**. Mixed sources (own EquitiesEdge, IEX, Nasdaq Basic, 15-min SIP; full depth behind Enterprise). Not a rigorously versioned PIT panel. **Pricing:** Individual $150/mo (non-commercial), Startup ~$333→$999/mo, Enterprise from $1,250/mo ([pricing](https://intrinio.com/pricing)). **Good at:** clean API, as-reported SEC fundamentals. **Bad at:** not a survivorship-free research panel; cheap tiers are partial-market.

**Tiingo** — EOD for 65k+ securities, IEX real-time, **news API**, thin third-party fundamentals; includes delisted tickers but **not validated as academically survivorship-bias-free** (no delisting returns, no historical index constituents). **Pricing:** Free; **Power User $10/mo**; commercial/redistribution ~$250–$500 ([pricing](https://www.tiingo.com/about/pricing)). **Good at:** unbeatable price-to-coverage, news. **Bad at:** not bias-free academically, thin fundamentals, single-exchange (IEX) real-time.

**Alpaca** — commission-free **broker + market-data API** (equities/options/crypto). **CTA/UTP** consolidated tape + **OPRA**. **Free = IEX-only; full SIP requires paid.** **Basic $0** (IEX, 15-min delayed REST); **Algo Trader Plus $99/mo** (full SIP real-time, OPRA, corporate actions, 10,000 calls/min) ([data-faq](https://docs.alpaca.markets/us/docs/market-data-faq)). History ~2016+. **Good at:** transparent cheap pricing, unified broker+data+execution (a natural fit for the §5.6 `ExecutionVenue` seam when paper→live ever happens), modern API. **Bad at:** no fundamentals/PIT, no survivorship framework, ~2016+ history, free IEX feed thin.

**dxFeed** — managed ticker plant with **direct market data feeds** from worldwide exchanges; strong **options** (full OPRA + Greeks/IV) ([choose.dxfeed.com](https://choose.dxfeed.com/), [options](https://dxfeed.com/market-data/options/)). Quote-based pricing (retail from ~$19/mo; enterprise indicative ~$350/mo). **Good at:** direct real-time + historical tick/options, full OPRA + Greeks. **Bad at:** no fundamentals/PIT, opaque pricing, OPRA entitlement overhead.

### Tier C — Honest-backtesting research datasets (the ones that matter most)

These are the datasets that genuinely unblock the cut-list item. **The first three bake bias-free/PIT into their core product**; FactSet/LSEG only unblock it if you specifically procure the PIT add-on.

**Sharadar (Core US Fundamentals SF1 / Core US Equities SEP)** — the honest-backtesting workhorse for a startup budget. Derived from SEC filings (EOD/batch, **not** a direct feed). **The PIT mechanics are explicit and exactly what §2.4 needs:** SF1 carries **`DATEKEY`** (actual SEC filing date = when the data became knowable), `REPORTPERIOD`, `CALENDARDATE`, `LASTUPDATED`; dimensions encode **`AR` = As Reported (true vintage)** vs **`MR` = Most Recent (restated)**, crossed with Q/Y/T → ARQ/ARY/ART/MRQ/MRY/MRT ([SF1](https://data.nasdaq.com/databases/SF1)). Coverage: 16,000+ companies (~6,000 active + ~10,000 delisted), fundamentals since 1990, SEP prices since 1998 across 21,000+ active/delisted tickers, "nearly completely free from survivorship bias" ([SEP](https://data.nasdaq.com/databases/SEP)). Distributed direct at sharadar.com **and via Nasdaq Data Link**. Pricing is license-gated (Personal/Academic/Business), historically low-tens-to-low-hundreds-of-$/mo for personal — **verify live**. **Good at:** the cheapest credible honest-backtesting path — true PIT, AR/MR vintage toggle, delisted coverage, adjusted EOD prices, decades of history, simple API. **Bad at:** EOD only (no intraday/options), US-equity-centric, reseller SLA, shorter history than CRSP.

**CRSP** — the academic gold standard: **survivorship-bias-free with explicit delisting returns** (the single most important detail for honest long-horizon backtests). US daily/monthly since **1926** (NYSE), plus the Survivor-Bias-Free Mutual Fund DB; PIT fundamentals via **CRSP/Compustat Merged (CCM)** ([WRDS CRSP](https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/center-for-research-in-security-prices-crsp/)). Access almost always via **WRDS** institutional subscription (academic); commercial is a pricier negotiated license. **Good at:** the gold standard. **Bad at:** no real-time, WRDS-gated, opaque high cost, PIT requires researcher discipline, recent Morningstar-ownership uncertainty.

**Norgate Data** — affordable **survivorship-bias-free EOD** purpose-built for backtesting; includes delisted stocks **and historically accurate index constituents** (eliminates both survivorship *and* index-membership look-ahead — rare). US bias-free back to 1950 (Diamond) / 1990 (Platinum). **Pricing (US, 12-mo):** Silver $270, Gold $360, **Platinum $630** (delisted + historical constituents → 1990, the minimum honest tier), Diamond $787.50 ([packages](https://norgatedata.com/stockmarketpackages.php)). Plugin model (AmiBroker/Python/Zipline), **not generic REST**. **Good at:** affordable genuine bias-free EOD + historical index constituents; deep US futures. **Bad at:** EOD only, weak PIT fundamentals, plugin model.

**FactSet** — **Fundamentals Point-in-Time** (as-reported, vintage/as-of dates since **Feb 1999**) + best-in-class **Symbology/Entity Master** preserving historical identifier mappings so delisted/changed securities resolve correctly ([PIT product](https://www.factset.com/marketplace/catalog/product/factset-fundamentals-point-in-time)); consolidated real-time via Exchange DataFeed. Enterprise/quote-only, five-to-six-figure+. **Good at:** best symbology/entity-linking, genuine PIT vintaged fundamentals. **Bad at:** enterprise cost; PIT only to 1999.

**Nasdaq Data Link (formerly Quandl)** — a **marketplace/distribution platform** (time-series + datatables API, R/Python/Excel), not primarily a producer; **no direct feeds**. Matters here because it **hosts the Sharadar datasets** (SF1/SEP/SFA) — the easiest single API to consume Sharadar ([SHARADAR publisher](https://data.nasdaq.com/publishers/SHARADAR)). **Good at:** cheapest credible PIT path (via Sharadar), clean API. **Bad at:** US-centric, EOD only, reseller SLA.

### 3.1 Which vendors take direct exchange feeds?

| Vendor | Direct exchange feeds? | PIT / survivorship-free history? |
|---|---|---|
| Databento | **Yes** (ITCH + Pillar, colo) | Security Master (PIT IDs, delisted) + Corp Actions; no fundamentals |
| Polygon/Massive | No (SIP-consolidated) | PIT-by-ticker only; quality caveats |
| ICE Consolidated Feed | Normalized (aggregates direct sources) | reference/PIT at contract level |
| LSEG/Refinitiv | **Yes** (Real-Time Direct/PCAP) | yes, but **paid add-on** (Worldscope/Datastream PIT) |
| FactSet | Consolidated | **Yes** — PIT fundamentals 1999+, historical symbology |
| Nasdaq Data Link | No (marketplace) | via **Sharadar** |
| Intrinio | Mixed (IEX, Nasdaq Basic, SIP) | as-reported, not versioned PIT |
| Tiingo | IEX (one exchange) | delisted included, not academically bias-free |
| CRSP | n/a (research DB) | **Yes** — gold standard, delisting returns, 1926+ |
| Norgate | n/a (EOD research) | **Yes** — bias-free + historical index constituents |
| Sharadar | No (SEC-derived EOD) | **Yes** — DATEKEY vintages, AR/MR, delisted |
| dxFeed | **Yes** (direct, options strong) | tick replay; no fundamentals |
| Alpaca | No (SIP + OPRA) | no PIT/survivorship framework |

---

## 4. What this unlocks for the product

The decision to buy official data lifts specific constraints the plan currently bakes in:

1. **Fundamental-factor backtesting comes OFF the cut list.** §2.4's `[CUT-FOR-v2.0]` ("Fundamental-factor backtests are forbidden at launch") and §5.1's primitives-only framing for factor strategies were forced *entirely* by the lack of a vintaged source. **Sharadar SF1 supplies exactly the missing ingredient: as-reported fundamentals with `DATEKEY` vintages and AR/MR dimensions.** With it wired, the worker path's `asOf = bar_i` truncation becomes *real* against fundamentals, not estimated. The §2.4 sentence "Fundamental-factor backtesting unlocks only when a vintaged source (Sharadar/Compustat PIT) is wired" is now satisfiable at launch budget.

2. **Survivorship bias is eliminated, full-universe becomes honest.** Sharadar (delisted included), Norgate (delisted + historical index constituents), and CRSP (delisting returns) all carry delisted securities and point-in-time membership. The `screen.universe` tool's "(PIT-aware via `listedAt`)" promise (§4.1) and the §10 risk #1 ("Free sources can't deliver true PIT") are directly addressed. Cross-sectional rank strategies stop silently selecting only survivors.

3. **`pit: true` becomes legitimately attainable per source.** The provenance `pit` flag (§2.4, §4.2) was destined to read `false`/`estimated` for everything fundamental under Yahoo. Now: Sharadar fundamentals → `pit: true`; Databento Security Master + corp actions → `pit: true` for prices/identifiers; EDGAR/news already `pit: true`. The flag stops being an apology and becomes a real capability signal.

4. **Real intraday and order-book data become real.** Databento's direct ITCH/Pillar feeds make `market.get_intraday` and `market.get_trade_flow` (§4.1) genuinely exchange-grade, and resurrect a *bounded* path for `market.reconstruct_order_book` (the IEX-DEEP tool cut in §4.1 for decoding ~13GB) — Databento serves normalized L2/L3 directly, removing the in-process decode that motivated the cut (though the async/byte-cap discipline from §4.1 still applies).

5. **Honest backtest diagnostics gain teeth.** Flow 3's "always emit walk-forward/overfitting diagnostics (deflated Sharpe, PBO/CSCV)" (§3) is only meaningful on a survivorship-free, point-in-time universe. With Yahoo, those diagnostics decorated a biased sample; with PIT data they measure something true.

6. **Corporate-actions correctness.** Databento corporate actions + Sharadar's adjusted/unadjusted views replace Yahoo's silently-restated dividend/split series — removing a whole class of backtest distortion the plan called out as "dividend-restated."

**What does NOT change / stays cut:** microsecond latency, colo, FPGA — irrelevant to research + paper-live. Doomberg never needs Layer-1 latency. `deploy:live` stays unissuable (§5.6); the freshness floor on paper-live (§7) still governs the money path regardless of source quality.

---

## 5. Recommendation + phased path

### 5.1 The pragmatic answer

**Buy "official quality" by buying from vendors that themselves take direct exchange feeds and that bake PIT into their datasets — do NOT build a colo ticker plant.** The endgame "direct feeds + colo" is a graduation state Doomberg may never need, because its product is *research + paper-trading + derived data*, not latency-sensitive execution.

The recommended launch stack — three vendors, three jobs:

| Vendor | Job | Why | Rough cost |
|---|---|---|---|
| **Sharadar SF1 + SEP** (via Nasdaq Data Link or direct) | **PIT fundamentals + survivorship-free EOD** — the honest-backtest engine | DATEKEY vintages + AR/MR dimensions + delisted; cheapest credible PIT. **This is the purchase that lifts the §2.4 cut.** | low-hundreds $/mo (business license higher; **verify quote**) |
| **Databento** | **Direct-feed prices, intraday, order book, corp actions, security master** | Real ITCH/Pillar in colo; pay-as-you-go history; PIT security master. Makes `market.*` exchange-grade. | history pay-as-you-go (~$100s/mo typical); live Standard ~$199/mo |
| **Alpaca Algo Trader Plus** | **Broker-grade SIP real-time for paper-live ticks** + the natural future `ExecutionVenue` | Full SIP + OPRA + corporate actions at $99/mo; one provider for data + (future) execution; satisfies the §7 freshness floor on the money path | $99/mo |

Add **Tiingo Power User ($10/mo)** as a cheap news + redundancy source for `news.*`, and keep **EDGAR/FRED/Polymarket** as the already-PIT free sources for `ownership.*`/`macro.*`. **CRSP (via WRDS)** and **Norgate Platinum** are *optional later additions* for academic-grade validation / historical-index-constituent rigor, not launch dependencies.

### 5.2 Phased path (slots into the plan's roadmap)

- **Phase 0.5(b) — the honest-backtest spike (already in the plan).** Procure **Sharadar SF1+SEP**, produce the "one defensibly-PIT backtest" the spike demands — now a *fundamental-factor* one, not just price. Enumerate exactly which sources support `pit: true`. **Cost: ~$1–3k for the spike period.**
- **Phase 1 — Data Layer walking skeleton.** Wire **Databento** behind `sources/prices` for `market.get_ohlcv` (direct-feed daily/intraday) and **Sharadar** behind `sources/fundamentals` for `fundamentals.get_history` with real `asOf` truncation. Both expose the per-source `pit` flag honestly. **Cost: ~$300–700/mo.**
- **Phase 3 — Backtest on DO.** The backtest worker pulls a PIT bulk window from Databento (prices) + Sharadar (fundamentals AR dimension at `asOf = bar_i`). Fundamental-factor backtests are now *in scope*. **Cost: usage-metered Databento history + Sharadar flat.**
- **Phase 4 — Paper-live.** Wire **Alpaca Algo Trader Plus** SIP real-time behind the paper-live tick; the §7 freshness floor governs skip-and-alert. **Cost: +$99/mo.**
- **Phase 5 — Breadth + (optional) rigor.** Add Tiingo news, dxFeed if options depth is needed, and **CRSP/Norgate** if academic-grade validation or historical-index-constituent universes become a selling point. **Cost: $10–250/mo + (CRSP via WRDS, negotiated).**

**Rough cost envelope:** launch (Phases 0.5–4) lands around **$500–$1,500/mo (~$6k–$18k/yr)** of vendor spend — well inside the "Vendor API, small" tier (§2.6) and well below the non-display cliff, *because Doomberg serves derived data (§2.5) and uses EOD/PIT data for research rather than redistributing raw real-time quotes.* The "direct feeds + colo" tier ($1M+/yr) is explicitly out of scope.

### 5.3 The graduation trigger

Move from "vendor API" toward "direct feeds + colo" (or a heavier Databento/dxFeed enterprise tier) **only when**:
- Latency becomes product-load-bearing — i.e., `deploy:live` ships and real fills depend on sub-millisecond data (today `deploy:live` is unissuable, so this trigger is years out), **or**
- Vendor metered/redistribution costs cross ~$150k/yr (the point where direct-feed economics begin to compete), **or**
- A customer contract requires data Doomberg can only get under its own exchange agreement.

Until any of those fire, **stay on vendors.** The architecture makes graduation a `sources/` adapter swap, not a rewrite (§5.4).

### 5.4 How it slots into doomberg-core

This decision touches **only** the source adapter layer and the provenance flag — the §2.3/§2.4 architecture was already built for it:

- **`doomberg-core/sources/`** gains adapters: `sources/prices` → Databento; `sources/fundamentals` → Sharadar; a `sources/live` → Alpaca SIP. Each is a `_resilient`-wrapped adapter behind the same breakers/provenance builder. Swapping Yahoo→Databento is an adapter change, not a contract change.
- **The Data Gateway facade (§2.3)** is unchanged: it still applies the single `asOf` truncation knob. The difference is that `asOf` truncation against **Sharadar's `DATEKEY`/AR dimension is now truthful**, where against Yahoo it was estimated. The worker path's `asOf = bar_i` finally means what it claims.
- **The per-source `pit` capability flag (§2.4, §4.2)** is the exact seam this plugs into: each adapter declares `pit: true|false|estimated`. Sharadar fundamentals and Databento prices/corp-actions report `pit: true`; the flag stops being a forced `false`.
- **The global-upstream-cache exception (§7)** for public market data still lives in one reviewed module — now caching *licensed* vendor data, which sharpens the need for the entitlement/derived-data discipline in §2.4/§2.5.

---

## 6. Concrete changes to the master plan

Short, surgical edits given this decision:

**§2.4 (point-in-time):**
- Strike `[CUT-FOR-v2.0] Fundamental-factor backtests are forbidden at launch.` Replace with: *"Fundamental-factor backtests are IN SCOPE at launch, sourced from Sharadar SF1 (as-reported `DATEKEY` vintages, AR/MR dimensions). The `asOf` truncation is truthful against Sharadar's filing-date vintaging, not estimated."*
- Update the bullet on Yahoo's deficiencies: Yahoo is **dropped** as a source; the survivorship-bias/dividend-restatement/no-vintaging critique is resolved by the vendor stack rather than worked around.

**§4.1 (tool taxonomy):**
- `fundamentals.get_history` → annotate **PIT-capable (Sharadar SF1, vintaged)**; `fundamentals.get_snapshot` sourced from Sharadar MR dimension.
- `market.get_ohlcv` / `get_intraday` / `get_trade_flow` → note source is **Databento direct feeds (ITCH/Pillar)**, `pit: true`.
- `screen.universe` → now genuinely PIT-aware (delisted included via Sharadar/Databento Security Master), not aspirational.
- The `[CUT-FOR-v2.0]` on `market.reconstruct_order_book` can be **relaxed**: Databento serves normalized L2/L3 directly, removing the 13GB in-process decode; keep the async/byte-cap discipline but the cut rationale (IEX-DEEP decode cost) no longer applies.

**§4.2 (provenance contract):**
- Update the example `source` from `"yahoo-chart"` to a real source (e.g. `"databento-xnas-itch"` / `"sharadar-sf1"`), and show `"pit": "true"` as the realistic default for the priced/fundamental paths.
- Add a `license` field note to provenance for non-display/derived-data audit traceability (which source, which entitlement, derived vs raw).

**§4.3 (porting map):**
- The "fix-on-port" list should add: **replace the Yahoo adapter in `sources/prices` with a Databento adapter; replace `fetch_fundamentals_history`'s 45-day-lag estimation with Sharadar `DATEKEY`-driven truthful vintaging.** This removes the single worst data-honesty hack in the v1 code.

**§10 (risks):**
- Risk #1 (PIT data honesty) is **downgraded from CRITICAL/open to RESOLVED-at-launch**: the vintaged source (Sharadar) is now a launch dependency, not an open question. Replace the "Open: budget/timeline for a vintaged fundamentals source" line with the cost envelope in §5.2 of this doc.
- Add a **new MEDIUM risk: market-data licensing/audit exposure** — non-display (Category 2) treatment of agent consumption, redistribution obligations, and the 3-year back-fee audit risk (§2.3/§2.7). Mitigation: buy through vendors who hold the licenses, serve derived data not raw quotes, and keep entitlement/usage records from day one.

---

### Consolidated source list
- Nasdaq TotalView-ITCH spec — https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/NQTVITCHSpecification.pdf
- NYSE XDP Integrated Feed Client Spec — https://www.nyse.com/publicdocs/nyse/data/Integrated_Feed_Client_Specification_v2.3d.pdf
- Cboe Multicast PITCH spec — https://www.cboe.com/document/tech-spec/document/technical-specifications/cboe-titanium-u.s.-equitiesoptions-multicast-pitch-specification
- Databento — proprietary feeds vs SIP — https://databento.com/blog/proprietary-feeds-vs-sip-data
- Databento — introducing US equities (direct feeds) — https://databento.com/blog/introducing-databento-us-equities
- Databento — Security Master — https://databento.com/security-master
- Databento — Corporate Actions — https://databento.com/blog/corporate-actions
- Databento — Jan 2025 pricing — https://databento.com/blog/upcoming-changes-to-pricing-plans-in-january-2025
- Securities Information Processor — Wikipedia — https://en.wikipedia.org/wiki/Securities_information_processor
- Sidley — D.C. Circuit upholds MDIR — https://www.sidley.com/en/insights/newsupdates/2022/06/dc-circuit-upholds-secs-market-data-infrastructure-rules-paving-the-way-for-competing-consolidators
- SIFMA — CT Plan fee filing letter (Aug 2025) — https://www.sifma.org/wp-content/uploads/2025/08/SIFMA-Letter-re-Equity-Market-Data-8.25.2025.pdf
- Traders Magazine — Competing Consolidators without CT Plan — https://www.tradersmagazine.com/am/market-data-competing-consolidators-without-ct-plan/
- Bloomberg — SIP vs Direct Feeds latency — https://www.bloomberg.com/professional/blog/sip-vs-direct-feeds-latency-rules/
- Exegy — Hosted Ticker Plant — https://www.exegy.com/products/hosted-ticker-plant/
- Exegy — Ticker Plant (XTP) — https://www.exegy.com/products/exegy-ticker-plant/
- Exegy — Market data fees & infrastructure planning — https://www.exegy.com/market-data-fees-planning-infrastructure/
- Pico InRush Ticker Plant — https://www.pico.net/redline-software/inrush-ticker-plant/
- NovaSparks FPGA feed handler — https://novasparks.com/novasparks-is-voted-best-high-performance-data-feed-handler/
- Bloomberg B-PIPE / Real-Time Data Feed — https://professional.bloomberg.com/products/data/enterprise-catalog/real-time-data-feed/
- LSEG Real-Time data feeds — https://www.lseg.com/en/data-analytics/market-data/data-feeds
- LSEG Tick History (TRTH/PCAP) — https://www.lseg.com/en/data-analytics/market-data/data-feeds/tick-history
- ICE Consolidated Feed — https://www.ice.com/fixed-income-data-services/access-and-delivery/connectivity-and-feeds/consolidated-feed
- Nasdaq US Equities Price List 2025–2027 — https://www.nasdaqtrader.com/content/ProductsServices/PriceList/Nasdaq_US_Equities_Price_List_2025_2026_2027.pdf
- NYSE Proprietary Market Data Fee Schedule — https://www.nyse.com/publicdocs/nyse/data/NYSE_Market_Data_Fee_Schedule.pdf
- Nasdaq US Equities & Options Data Policies — https://www.nasdaqtrader.com/content/AdministrationSupport/Policy/USEquitiesandOptionsDataPolicies.pdf
- NYSE Non-Professional Subscriber Policy — https://www.nyse.com/publicdocs/nyse/data/Policy-Non-ProfessionalSubscribers_PDP.pdf
- Interactive Brokers — Pro/Non-Pro definitions — https://www.interactivebrokers.com/en/accounts/fees/professionalDefinations.php
- Nasdaq UTP Plan Vendor Agreement — https://www.utpplan.com/DOC/VendorAgreement.pdf
- NYSE Market Data Vendor Guide — https://www.nyse.com/publicdocs/ctaplan/notifications/trader-update/NYSE%20Market%20Data%20Vendor%20Guide.pdf
- CTA MISU Policy — https://www.nyse.com/publicdocs/nyse/data/MISU_Policy_with_FAQ.pdf
- Markets Media — Complexities Expand in Market Data Licensing — https://www.marketsmedia.com/complexities-expand-in-market-data-licensing/
- Polygon → Massive rebrand — https://massive.com/blog/polygon-is-now-massive
- Polygon/Massive API review — https://medium.com/@yolotrading/a-complete-review-of-the-polygon-io-api-everything-you-wanted-to-know-c79e992a74ff
- Intrinio pricing — https://intrinio.com/pricing
- Tiingo pricing — https://www.tiingo.com/about/pricing
- Alpaca market-data FAQ — https://docs.alpaca.markets/us/docs/market-data-faq
- dxFeed — https://choose.dxfeed.com/
- Sharadar SF1 (Nasdaq Data Link) — https://data.nasdaq.com/databases/SF1
- Sharadar SEP (Nasdaq Data Link) — https://data.nasdaq.com/databases/SEP
- WRDS — CRSP — https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/center-for-research-in-security-prices-crsp/
- CRSP — Wikipedia (Morningstar acquisition) — https://en.wikipedia.org/wiki/Center_for_Research_in_Security_Prices
- Norgate Data packages — https://norgatedata.com/stockmarketpackages.php
- FactSet Fundamentals Point-in-Time — https://www.factset.com/marketplace/catalog/product/factset-fundamentals-point-in-time



====================================================================================================
FILE: docs/plans/doomberg-v2/MASTER-PLAN.md
====================================================================================================

# Doomberg v2 — Master Implementation Plan

**Status:** approved-to-build • **Date:** 2026-06-16 • **Supersedes:** v1 monolith at `artifacts/api-server/app`
**Inputs synthesized:** 6 subsystem designs (topology, data layer, deploy layer, web UI, security, repo/sequencing) + 2 red-team critiques (integration, feasibility).

This plan resolves every contradiction the red teams surfaced. Where docs conflicted, the resolution is stated inline with a one-line rationale and tagged **[RESOLVED]**. Where a feasibility critique forces a scope cut, it is tagged **[CUT-FOR-v2.0]**. This is meant to be buildable from on Monday.

---

## 1. Vision & positioning

Doomberg v2 is a **financial tool-platform**: a hosted set of quantitative research and paper-trading capabilities that an external, bring-your-own (BYO) agent — Claude, GPT, or a custom agent — calls over MCP. v1 was a monolith that ran *its own* agent loop inside the server and compiled AI-authored code at runtime (the source of two critical RCEs); v2 inverts that completely — **Doomberg never runs the agent and never executes agent-authored code**, it only exposes vetted tools, executes declarative strategy specs on trusted infrastructure, and *observes*. The product is three surfaces over one shared Python core: an **MCP gateway** (the primary API the agent uses to research and propose strategies), a **DigitalOcean deploy layer** that backtests and paper-trades accepted strategies, and a **web observability UI** that lets a human watch their agent think, work, and trade — replayable and fully audited. The shift in one line: *from "an AI terminal that does the thinking" to "a tool-platform someone else's agent thinks with, and a glass box that records everything it did."*

---

## 2. Target architecture

### 2.1 The load-bearing resolution: one core, one language, one contracts package

The single biggest structural risk the integration red-team found is that the six docs each invented their own auth format, spec shape, event schema, tenant key, and allow-list — *while topology asserts a single shared core*. We resolve this at the foundation:

- **[RESOLVED — control-plane language] The entire backend is Python.** The repo-sequencing doc's TypeScript control plane is **overruled** (topology, deploy, and security all specify Python/FastAPI). Rationale: the spec validator, the post-projection gross-L1 risk attestation, and the operator registry are the security boundary and live in numpy/Pydantic. A TS control plane would either duplicate that math (the exact v1 divergence-bug class) or add an unowned Python hop per validation. TypeScript is kept **only for the web UI.**
- **[RESOLVED — one core, no re-porting] `engine/`, `sources/`, `paperbook`, `execution` live in exactly one shared Python package (`doomberg-core`), imported — never re-ported — by the MCP gateway, the REST gateway, and the DO workers.** This kills the three-homes-for-the-money-path problem and guarantees `backtest math ≡ paper math` because both drivers import the same code.
- **`packages/contracts` is frozen in Phase 0 before any service is built.** It owns: the event/trace schema, the `StrategySpec` schema, the provenance envelope, the canonical tenant key, and the auth principal. This is the repo-sequencing doc's stated Phase-0 unlock that the other five docs each violated by inventing their own shapes.

### 2.2 Component map

| | Component | Language | Role |
|---|---|---|---|
| **A** | MCP gateway | Python (official MCP SDK, streamable-http + stdio) | Primary product surface. Token → principal; advertises Data + `propose_strategy`; per-call deadline; emits a trace event per call. Thin adapter over the core. |
| **B** | REST/SSE gateway | Python (FastAPI) | Feeds the web UI from the **same** core. Browser auth, REST reads, SSE fan-out, **human control actions (accept/promote/pause/halt)**. |
| **C** | `doomberg-core` | Python 3.12 + numpy | Ported v1 `engine/` (pure quant) + `sources/` (adapters behind `_resilient`) + the operator registry + the graph evaluator + the accounting/risk kernel. No I/O in `engine`; no agent code anywhere. |
| **D** | Deploy control plane | Python (FastAPI), separate deployable | Owns immutable versioned specs, the run state machine, scheduling onto DO, the pre-trade compliance gate. **Single writer of the money path.** |
| **E** | Event/trace spine | Postgres LISTEN/NOTIFY (launch) → Redis Streams (scale) | Append-only `(run_id, seq)` events. |
| **F** | Datastores | Postgres 16 (+ RLS), DO Spaces | System of record + blobs. TimescaleDB deferred. |
| **G** | DO workers | Python, **same `doomberg-core` image** | Execute backtests + paper-live ticks. Pull jobs, stream telemetry. Reach data **only** through the Data Gateway facade. |
| **H** | Web UI | React + Vite + TS | Observability surface, no chat console. Pure SSE+REST projection. |

### 2.3 [RESOLVED — Data Gateway vs Data Layer are the same service]

The integration red-team found `sources/` had two competing owners (the MCP data layer and a worker-only "Data Gateway"). **Resolution: there is one `sources/` package inside `doomberg-core`. The "Data Gateway" is not a separate service — it is a thin point-in-time facade in front of that one package, exposing a private RPC reachable only from the worker VPC.** The agent path (MCP `core.run_tool`) and the worker path (Gateway RPC with `asOf`) call the *same* adapters, the same breakers, the same provenance builder. The only difference is the `asOf` truncation parameter (see §2.4). This honors topology's "MCP and UI can never diverge."

### 2.4 [RESOLVED — point-in-time is a per-source capability, not a plane guarantee]

The feasibility red-team's **#1 critical** is that v1's free sources cannot deliver true PIT: Yahoo is survivorship-biased and dividend-restated with no vintaging; `fetch_fundamentals_history` *estimates* knowable-dates with a 45-day lag. **Resolution, adopted in full:**
- PIT is a **per-source capability flag in the provenance envelope** (`pit: true | false | estimated`), not a property the gateway can manufacture.
- `asOf` becomes an **optional input parameter** on data-fetch tool schemas (closing the integration red-team's #4). The worker path always passes `asOf = bar_i`; the agent path passes `asOf = now`. One entry point, one truncation knob.
- **[CUT-FOR-v2.0] Fundamental-factor backtests are forbidden at launch.** v2.0 backtests are scoped to **price/technical strategies** (momentum, MA-cross, vol, cross-sectional rank on returns) where Yahoo's restated-but-internally-consistent daily closes are defensible. Fundamental-factor backtesting unlocks only when a vintaged source (Sharadar/Compustat PIT) is wired. **This framing must be fixed before the Gateway is built — otherwise we ship a backtester that lies.**

### 2.5 ASCII architecture diagram

```
                        ┌─────────────────────────────────────────┐
   BYO Agent            │            packages/contracts            │
 (Claude/GPT/custom)    │  events · StrategySpec · provenance ·    │
        │               │  tenant_id · auth principal  (FROZEN P0) │
        │ MCP            └─────────────────────────────────────────┘
        ▼                                  ▲ generates types
 ┌──────────────┐   in-proc   ┌────────────┴───────────────┐
 │ (A) MCP      │────────────▶│   (C) doomberg-core         │
 │   gateway    │  core.run_  │   engine/ (pure numpy)      │
 └──────────────┘   tool()    │   sources/ (+ _resilient)   │
        │                     │   operator registry         │
        │ emits trace         │   graph evaluator           │
        ▼                     │   accounting + risk kernel  │
 ┌──────────────┐   core.read │   Data Gateway facade(asOf) │
 │ (B) REST/SSE │◀────────────│                             │
 │   gateway    │   (view)    └─────┬───────────────┬───────┘
 └──────┬───────┘                   │ propose/      │ private RPC
        │ SSE                       │ create_run    │ (asOf, VPC-only)
        │ + human control           ▼               │
        ▼                  ┌──────────────────┐     │
 ┌──────────────┐          │ (D) Deploy        │     │
 │ (H) Web UI   │◀── SSE ──│   control plane   │     │
 │  React/TS    │          │  specs·runs·books │     │
 │  Runs│Algos│ │          │  state machine    │     │
 │  Deploys│    │          │  compliance gate  │     │
 │  Trades│Ideas│          │  SINGLE WRITER    │     │
 └──────────────┘          └───┬───────────┬───┘     │
                               │ enqueue   │ apply    │
        ┌──────────────────────┘  job      │ delta    │
        ▼                                  ▲          ▼
 ┌─────────────────────────────────────────┴──────────────────┐
 │  (G) DigitalOcean DOKS — workers (same doomberg-core image) │
 │   node pool: backtest (scale-to-zero)  │  node pool: paper  │
 │   deny-all egress except Data Gateway RPC                   │
 │   propose book deltas → (D) applies in serialized txn       │
 └─────────────────────────────────────────────────────────────┘
        │                         │
        ▼                         ▼
 ┌──────────────┐         ┌──────────────┐
 │ (F) Postgres │         │ DO Spaces     │
 │  +RLS  (E)   │         │  artifacts    │
 │  trace_event │         │  logs/blobs   │
 │  LISTEN/NOTIFY│        └──────────────┘
 └──────────────┘
```

### 2.6 Layer contracts (enforced once, never per-call-site)

- **Agent ↔ Doomberg (MCP, THE product API):** every tool has JSON-Schema input, a typed output with a **mandatory provenance block**, a declared deadline, a stable name+version. The agent can **read and `propose_strategy` only**. It cannot promote or move money.
- **Gateway ↔ Core (in-process):** both A and B call one `core.run_tool(name, args, ctx)` / `core.read(view, ctx)`. `ctx` carries `tenant_id, session_id, actor, deadline`. The MCP path and UI path cannot diverge.
- **Core ↔ Deploy:** D exposes `create_run, transition_run, apply_book_delta, evaluate_gate`. Spec is a closed declarative schema validated against the operator registry; **no free-form code field exists** (see §5).
- **Control plane ↔ DO runtime:** workers PULL jobs, STREAM telemetry, **PROPOSE deltas, never write the book** (see §5.4 resolution). Deadline checked inside worker loops. Jobs idempotent on `(run_id, seq)`.
- **Tenancy:** `tenant_id` resolved at the two front doors only, bound into `ctx`; the data-access layer + Postgres RLS is the single enforcement point.

---

## 3. The four key end-to-end flows

**Flow 1 — Research (agent ↔ MCP, observable for free).** The agent opens MCP with a token → resolves to `(tenant_id, agent_id, scopes)` and a `session_id`. `tools.list` returns the Data Layer catalog. `meta.open_research_session({focus})` binds a session carrying a wall-clock **deadline + credit budget** (the aggregate cap v1 lacked). Each `tools.call` (e.g. `market.get_ohlcv`, `signals.evaluate_signal`) opens a trace span, sets a per-call deadline = `min(default, remaining_budget)`, routes through the core's resilience wrapper, and returns an envelope with a **mandatory provenance block** `{source, asOf, freshness, pit, coverage, cost}`. Because we own the server, **every call is a trace event with zero agent cooperation.** The UI renders spans live.

**Flow 2 — Propose (agent → control plane, validated as data).** The agent calls `propose_strategy({spec})`. The spec is the **one canonical `StrategySpec`** (§5). D validates against the schema + semantic linter + **design-time risk pre-attestation**, assigns server-stamped `strategy_id` + immutable `version`, stamps `origin_session_id`, and persists `draft`. Nothing deploys. The agent has emitted *data we validate*, never code we run.

**Flow 3 — Accept → backtest (human-gated, runs on DO).** **[RESOLVED — promotion authority]** A **human** clicks "Backtest" / "Deploy (paper)" in the UI through gateway (B). The agent's `deploy:paper` scope is narrowed to *"may request a deployment that requires human acceptance"* — it cannot self-promote. D creates a guarded `run`, enqueues a job. A backtest worker (G) pulls it, runs trusted `engine/backtest` over a point-in-time window (`asOf = bar_i`, scoped to PIT-capable sources), streams progress telemetry with heartbeats, writes the artifact to Spaces + summary to Postgres, and **always emits the walk-forward/overfitting diagnostics** (deflated Sharpe, PBO/CSCV) — honesty by default. UI animates the equity curve with the integrity/provenance badge.

**Flow 4 — Promote → paper-live → observe (human-gated, single-writer money path).** Human promotes through (B). D runs the pre-trade compliance gate (gross/net/per-name caps, restricted lists) and **re-checks `sum|w|` vs gross AFTER projection** (closes the v1 311%-gross optimizer bug — see §5.3). On pass, D opens a paper book and schedules a market-calendar-aware **paper-live tick** job. Each tick: worker loads current marks, evaluates the graph on **real current data with a hard max-staleness floor** (skip-and-alert if stale — see §7), computes target weights, routes through the **paper venue adapter**, and **proposes a book delta**. D applies it in a serialized `SELECT … FOR UPDATE` transaction. Every fill, mark, and transition is a trace event; the UI streams P&L into Deployments and Trades. The whole chain research→proposal→backtest→paper is one unbroken `origin_session_id` lineage.

---

## 4. Data Layer plan

### 4.1 MCP tool taxonomy

Naming: `<group>.<verb_noun>`. 15 groups, each tool ports from a named v1 module. Headline tools per group:

- **`market`** — `get_quote`, `get_ohlcv`, `get_intraday`, `get_daily_closes` (PIT-safe, real-only), `get_trade_flow`. *(ports `sources/prices`, `iex_deep`)*
- **`fundamentals`** — `get_snapshot` (unit-corrected), `get_history`, `compare_companies`, `classify_sector`. *(ports `sources/fundamentals`, `sectors`)*
- **`calendar`** — `get_earnings`, `get_ma_activity`, `get_economic_releases`, `get_series_revisions`.
- **`news`** — `get_ticker_news`, `get_topic_news`, `get_sentiment`. *(PIT-capable: real `publishedAt`)*
- **`ownership`** — `get_insider_transactions`, `get_congress_trades`, `get_13f_holdings`, `get_etf_holdings`, `search_filings`. *(EDGAR is PIT-capable)*
- **`signals`** — `list_signals`, `evaluate_signal`, `combine_signals`, `compute_ic`, `correlation_matrix`, `factor_analysis`.
- **`risk`** — `build_factor_model`, `decompose_portfolio`, `attribution`, `stress_scenario`, `performance_stats`.
- **`portfolio`** — `construct`, `optimize_mean_variance`, `optimize_risk_parity`, `optimize_hrp`, `black_litterman`, `rebalance_plan`.
- **`backtest`** — `list_strategies`, `run`, `walk_forward`, `monte_carlo`. *(research primitives, NOT deploy)*
- **`execution`** — `estimate_costs`, `simulate_orders` (real intraday only), `tca_report`, `borrow_profile`.
- **`options`** — `get_chain`, `screen`, `price_strategy`, `iv_surface`, `vol_term_structure`.
- **`fixedincome`** — `get_treasury_curve`, `compare_sovereigns`, `cashflow_duration`, `cds_price`, `credit_spreads`.
- **`macro`** — `get_regime`, `get_fred_series`, `list_prediction_markets`, `get_prediction_market`.
- **`screen`** — `universe` (PIT-aware via `listedAt`), `run_screener`, `heatmap`.
- **`meta`** — `list_tools`, `data_quality`, `open_research_session`, `session_summary`.

**[CUT-FOR-v2.0]** `market.reconstruct_order_book` (IEX DEEP) is **removed from the synchronous agent surface** (feasibility #9: a single call decodes ~13GB). If re-added: high-cost class, **hard byte cap** (not just wall-clock), async job, pre-materialized per session-date.

### 4.2 Provenance contract (structural, every payload)

```jsonc
{ "data": {...},
  "provenance": {
    "source": "yahoo-chart", "asOf": "2026-06-16T14:32:05Z",
    "freshness": "live|stale|mock", "staleAgeSec": 0,
    "pit": "true|false|estimated",          // per-source capability — NOT a plane guarantee
    "coverage": { "requested": 12, "resolved": 11, "missing": ["BRKB"] },
    "cost": { "class": "cheap|network|heavy", "credits": 1 }, "cacheHit": true },
  "partial": false,
  "warnings": [{ "code": "MOCK_FALLBACK", "scope": "US2Y" }] }
```

Rules: data is **never imputed** to hide gaps; `mock` is never dressed as live; `asOf` is the *data's* timestamp not fetch time. Typed errors with stable codes (`UNSUPPORTED_WINDOW`, `UPSTREAM_THROTTLED`, `DEADLINE_EXCEEDED`, …). Stale-while-revalidate serves cached data labeled `stale` rather than fabricating mock.

### 4.3 Porting map (fix-on-port)

Port `engine/` (~5000 LOC, genuinely pure per feasibility verification) and `sources/` (~4000 LOC) nearly verbatim into `doomberg-core`. Fix during port: optimizer gross-L1 re-check (`optimize.py:177`), Carino-link attribution (`attribution.py:357`), cross-sectional forward-window alignment (`signals.py:342`), route Treasury/FRED through `_resilient` (`rates.py:91`). **Drop entirely:** `agent.py`, `code_guard.py`, `dynamic_skills.py`, `feature_builder.py`, `skills_generated/`. The 79 v1 skills are **not** ported as the skill abstraction — their underlying engine/source calls become the static MCP tools above.

---

## 5. Deploy Layer plan

### 5.1 [RESOLVED — strategy model: declarative-only, parameterized primitives at launch]

Three docs proposed three spec shapes (flat `signal_id+scheme` / operator-DAG / `engine/strategies.py` primitives) and security added a "scripted escape hatch." **Resolution, taking both red teams' advice:**
- **One canonical `StrategySpec` in `packages/contracts`, authored once, one validator, one evaluator.**
- **[CUT-FOR-v2.0] v2.0 ships the parameterized `engine/strategies.py` primitives, NOT the operator-DAG.** Rationale (feasibility #7): the existing strategies are `(closes, params) -> positions` pure functions covering MA-cross/momentum/mean-reversion — they ship faster, the DAG's semantic linter (cycle detection, feasibility pre-attest, registry) is real work for marginal launch value. The DAG is a **post-launch expressiveness upgrade** that reuses the same evaluator seam.
- **[CUT-FOR-v2.0] The `CustomPythonNode` / "scripted escape hatch" does not exist in the launch schema.** topology's invariant holds: *un-expressible beats off-by-default.* security §3.1's "scripted mode" and deploy's `CustomPythonNode` are re-labeled **"future, not in launch schema."** `firmId`/`id` are always server-stamped.

`StrategySpec` (launch shape):
```jsonc
{ "specVersion": "1.0", "id": "<server-stamped>", "tenant_id": "<stamped>",
  "name": "dual-momentum-tech",
  "universe": { "symbols": ["AAPL","MSFT","NVDA"], "source": "prices" },
  "strategy": { "id": "momentum", "params": { "lookback": 90, "top": 2 } },
  "construction": { "scheme": "rank_weight", "longOnly": true, "gross": 1.0 },
  "risk": { "maxGross": 1.0, "maxNet": 1.0, "maxNamePct": 0.25 },
  "execution": { "costBps": 5, "algo": "vwap", "rebalance": "daily@close" },
  "resources": { "tier": "standard" }, "seed": 42 }
```

### 5.2 SAFE execution model

- **[RESOLVED + CUT-FOR-v2.0 — no microVM at launch]** Feasibility #2: since **no untrusted code runs** (declarative-only), the runtime is *our own trusted code over validated data*. A plain container with **cgroup limits + `activeDeadlineSeconds` + a default-deny egress NetworkPolicy** is sufficient and a fraction of the gVisor/Kata/seccomp work. **The microVM sandbox is deferred to the phase that actually ships `CustomPythonNode`, gated on a spike proving the runtime works on DO.** We do not build a microVM fleet to run numpy we wrote.
- **Out-of-process always.** The runtime never runs in the control-plane process (v1's fatal mistake). One job per container, spawned fresh, killed at completion.
- **Deny-all egress** except the Data Gateway RPC, enforced by Kubernetes NetworkPolicy (an invariant in the cluster, not in code).
- **Aggregate wall-clock deadline per job** (not just per-call), SIGKILL on breach, recorded `timeout` with partial artifacts. Terminal states are explicit: `succeeded|failed|timeout|oom|killed|data_unavailable`. No bare `except: pass`.
- **Determinism:** `seed` in spec + pure numpy + fixed `asOf` window ⇒ identical artifact hash. "Reproduce this run" is free; backtests cache on `(spec_hash, asOf_window)`.

### 5.3 The risk gate — runtime, not lint **[RESOLVED, feasibility #8]**

The 311%-gross v1 bug was a *projection* ending on net+box instead of gross-L1. **The gross-L1 re-check runs post-projection, in the executor, on every emitted target book** — refusing to emit a breaching book (`infeasible-relaxed` with the violation). The design-time pre-attestation is a *nicety*; the runtime attestation is *the boundary*. Gating CI test uses the v1 311%-gross case as a fixture.

### 5.4 [RESOLVED — single-writer money path: worker proposes, D applies]

Docs split on worker-writes-book vs control-plane-sole-writer. **Resolution: topology's invariant wins — the worker computes the target book and PROPOSES a delta; D is the sole writer, applying it in one `SELECT … FOR UPDATE` transaction with an optimistic `version` backstop and a per-deployment advisory lock.** This matches security's "single TenantSession writer." `paperbook`/`execution` live once in `doomberg-core`, imported by both the `execution.*` MCP tools and the runtime.

### 5.5 The two runtimes (shared core)

Backtest and paper-live differ only in **clock** and **data window source**; same evaluator, same accounting, same risk gate.
- **Backtest:** simulated clock; one bulk PIT pull at job start; replays bar-by-bar seeing only `data[:i+1]`; CPU burst; emits curve + stats + overfitting diagnostics.
- **Paper-live:** wall-clock, scheduler-driven on `rebalance` cadence; **stateless tick worker, not a daemon** (each tick loads book → evaluates → proposes delta → exits; a crash loses one tick, not the book). Fills against `PaperVenue` on **real current prices**.

### 5.6 Brokerage seam (interface only — do NOT build)

```python
class ExecutionVenue(Protocol):
    def quote(self, symbols, as_of) -> dict[str, Quote]: ...
    def place_orders(self, orders, *, idempotency_key) -> list[Fill]: ...  # MUST be idempotent
    def positions(self) -> list[Position]: ...
    def venue_caps(self) -> VenueCaps: ...
```
`PaperVenue` is the only launch impl. `idempotency_key` is mandatory **now** (retried ticks must not double-fill). `deploy:live` scope is unissuable; no real adapter exists in the dependency graph.

### 5.7 [RESOLVED + CUT-FOR-v2.0 — DigitalOcean topology]

**Choice: DOKS + two node pools + Managed Postgres + Spaces + VPC.** App Platform rejected (no cgroup/NetworkPolicy/scale-to-zero for jobs); raw Droplets rejected (reinventing K8s). But per feasibility #2, **launch with plain containers + cgroups + NetworkPolicy egress-deny + `activeDeadlineSeconds`** — no gVisor/Kata at launch. Topology:
- **VPC** with cluster + Managed Postgres + the Data Gateway facade. Workers have **no public egress**; one NetworkPolicy allow to the Gateway ClusterIP.
- **Node pool `backtest`** — CPU-optimized, autoscale **min 0 → max N**; backtests as K8s Jobs (`restartPolicy: Never`, `activeDeadlineSeconds` = aggregate deadline). Scale-to-zero = cost control.
- **Node pool `paper`** — small stable pool for the market-calendar-aware scheduler + short tick Jobs.
- **State:** Managed Postgres (RLS), Spaces (artifacts), optional managed Redis for the queue.

---

## 6. Web UI plan

The UI is a **read-mostly observability + control surface**. No chat console; the "conversation" is the **agent trace**. Fed by the thin REST/SSE gateway (B) — the browser **never speaks MCP**.

### 6.1 Information architecture

Six views via a left rail: **Runs** (the centerpiece), **Algos**, **Deploys** (Backtests / Paper-Live tabs), **Trades**, **Ideas**, **Boards**. Global header carries connected-agent status, active Run selector, and a **PAPER** badge.

### 6.2 The centerpiece — visualizing external-agent reasoning

Three-column trace at `/runs/:runId`: **Reasoning rail** (left) · **Tool-call timeline** (middle, the spine) · **Evidence panels** (right). Each `tool_result` carries a `panelType` that keys a **static renderer registry** → renders the matching v1 panel with the result `data`. *A tool call is a question; the panel is the answer; the reasoning is why it was asked.*

**[RESOLVED — reasoning-optional-first, feasibility #5]** A BYO host will almost never volunteer chain-of-thought. So: **the tool-call timeline + evidence panels must be the compelling product with ZERO reasoning.** The reasoning rail is an opt-in enhancement (fed by an `emit_reasoning` tool / MCP notifications when the host supports it; otherwise it collapses and the timeline widens). Deterministic, non-LLM templated annotations (tagged `derived:true`) are the realistic primary fill — designed as such, not a footnote. The aggregate run-deadline bar is first-class in the header (makes a runaway run obvious — the v1 "no aggregate deadline" lesson, visualized).

Trace is **event-sourced** (`TraceEvent[]` + `playhead`); render is pure `select(events, playhead)`, so **live is "playhead pinned to latest seq"** and replay is the same component with a scrubber.

### 6.3 [RESOLVED — `panelType` is part of the tool-output contract, integration #8]

`panelType` is added to the tool-result envelope in `packages/contracts`, and the named panel's prop shape becomes part of the tool output contract. **Contract test:** every tool with a `panelType` produces `data` the named panel renders without `as any`. Unregistered `panelType` → safe static JSON/table viewer (zero eval).

### 6.4 v1 panels: keep / drop

- **KEEP & repurpose (~79 panels)** as display-only tool-output renderers: all the quant/data/strategy panels (`BacktestPanel`, `PerformancePnlPanel`, `FactorAttributionPanel`, `NewsPanel`, `RiskMonitorPanel`, …). Strip `Refine`/`onRefine` (that nudged v1's own agent — gone). Reuse `layout.ts`, `Dashboard.tsx` grid, `Sparkline`, `CoverageBadge`, and the SSE `data:`-chunk parser.
- **DROP:** chat console (`ChatPanel`, console hooks), voice mode, navigator/tour (salvage only the highlight mechanic), and — critically — **`panels/generated/` + the `sucrase` dependency entirely** (the `new Function` client-side RCE). No client-side codegen/eval ever.

---

## 7. Cross-cutting (designed away from v1's failure modes)

| v1 failure | v2 structural fix |
|---|---|
| Static-guard-then-trust → 2 RCEs | No in-process eval of any agent/LLM code. Strategies are declarative data we validate. No client-side codegen. |
| "Never crash" swallowing erases audit | Every tool call, transition, fill, and denial is an append-only trace event; bare `except: pass` banned on audited paths. |
| Tenancy per-store, not invariant | See below — RLS + scoped data layer + CI gate. |
| Unlocked read-modify-write on money | Worker proposes delta; D is sole writer under `FOR UPDATE` + version (§5.4). |
| Per-call timeouts, no aggregate budget | Wall-clock budget per request/session/job; shrinking per-call timeout = `min(default, remaining)`. |
| Tests exist but don't gate | CI gates from Phase 0 (§9). |

- **[RESOLVED — auth, integration #6]** security's account model is authoritative: **Tenant → User → Agent (stable principal) → Credential (rotatable secret).** topology and datalayer adopt `agent_id` as the stable principal and the **`dmbg_<env>_<keyid>_<secret>`** key format (only `sha256(secret)` stored). Effective permission = **role ∩ scope ∩ tenant**. Capability scopes (`data:read`, `strategy:author`, `deploy:backtest`, `deploy:paper`; `deploy:live` **unissuable at launch**). topology's "agent can propose, not promote" is expressed as the *absence* of self-promote on `deploy:paper`, not a hardcoded rule.
  - **[CUT-FOR-v2.0, feasibility #11]** Launch with **hashed API keys + per-principal rate limits + append-only audit + RLS**. Defer OAuth device-code, 15-min token exchange, hash-chained tamper-evidence, MFA, and edge WAF to post-pilot.
- **Tenant isolation as a HARD INVARIANT.** **[RESOLVED — one tenant key, integration #5]** Canonical name `tenant_id` (uuid), one GUC `app.tenant_id`, in `packages/contracts`; the `firmId`/`firm_id` aliases are **banned in CI.** Two defense layers: (A) **Postgres RLS** with `FORCE ROW LEVEL SECURITY` and `SET LOCAL app.tenant_id` per txn — a forgotten filter returns *zero rows, not another tenant's*; (B) a scoped data layer where unscoped queries are un-expressible (no raw `db.execute`; only a `TenantSession` from `ctx`). A CI test enumerates every tenant-eligible table and **fails the build** on any missing RLS policy or nullable `tenant_id`. **[Budgeted per feasibility #12]:** non-owner app role, PgBouncer transaction-mode + `SET LOCAL` interaction tested on the *pooled* path, and the global-upstream-cache exception (public market data, shared by design) lives in **one reviewed module**, not ad-hoc per call site.
- **Sandboxing:** §5.2 — out-of-process, deny-all egress, cgroup + deadline; microVM deferred to `CustomPythonNode`.
- **Secrets:** control plane holds infra secrets; workers get only short-lived per-job tokens scoped to `tenant/<id>/jobs/<jobid>/`. No secret on a worker disk.
- **Audit:** append-only, tenant-attributed, principal-stable across credential rotation. The run event log *is* the audit trail.
- **Deadlines:** aggregate wall-clock at every entry; long jobs are async with heartbeats (never bounded by an HTTP proxy ceiling).
- **[RESOLVED — money-path freshness floor, feasibility #10]** Provenance honesty protects the *agent's reasoning*, not the *fill engine*. The paper-live tick declares a **max-staleness tolerance and skips-and-alerts** when data exceeds it, rather than filling on stale marks. Freshness is a hard precondition on the money path, distinct from the soft display label on the research path.
- **[RESOLVED — one event schema + sequencer, integration #7]** One `TraceEvent` schema in `packages/contracts` (reconcile the `kind`/`type` enums). **`seq` is per-`run_id`, owned by a single writer per run.** Since research (data layer) and deploy (control plane) write to the *same* `trace_event` store, the chain is stitched by `origin_session_id` + `parent_span`; we **do not claim gap-free `seq` across two independently-writing services** (that's impossible without a shared sequencer) — `seq` is gap-free *within a run*, lineage links runs. **SSE standardizes on `Last-Event-ID` carrying `seq`** (native EventSource), with documented server replay-from-`seq`; the `?from_seq=` variant is dropped. Heartbeat format (`: keepalive` + `run_progress`) lives in `contracts` so all producers emit the same keepalive.
- **[RESOLVED — event bus scaling, feasibility #6]** Postgres LISTEN/NOTIFY is fine for Phase 1–2 but **not blessed as the uncritical launch bus** (8000-byte NOTIFY cap; SSE replay scans the system-of-record). Write the `(run_id, seq)` consumer against an **interface from day one**; set a concrete threshold (events/sec, concurrent SSE clients) at which **observability fan-out moves to Redis Streams** — config, not rewrite. Money-path events stay transactional in Postgres.
- **Paper-only by construction:** `deploy:live` unissuable, real adapter not in the dependency graph, `mode:"paper"` asserted at process start, everything labeled PAPER.

---

## 8. Repo structure & tech stack

```
doomberg2/                              # monorepo: uv (Python) + pnpm (TS)
├── packages/contracts/                 # FROZEN P0 — single source of truth
│   ├── schema/  {events, strategy_spec, provenance, tenant, auth}
│   ├── py/      (generated pydantic)   └── ts/ (generated zod)   # CI fails on drift
├── doomberg-core/                      # PYTHON — the ONE shared core (imported, never re-ported)
│   ├── engine/        # PORTED v1 (pure numpy, fix-on-port)
│   ├── sources/       # PORTED v1 adapters + _resilient (+ asOf, + pit flag)
│   ├── registry/      # strategy primitives (DAG ops deferred)
│   ├── graph/         # evaluator (one seam for primitives now, DAG later)
│   ├── accounting/    # paperbook + execution + TCA
│   ├── risk/          # post-projection gross-L1 attestation (THE boundary)
│   └── gateway/       # Data Gateway facade: asOf truncation, provenance, breakers
├── services/
│   ├── mcp-gateway/   # PYTHON — official MCP SDK; thin over core
│   ├── rest-gateway/  # PYTHON FastAPI — UI reads + SSE + human control actions
│   ├── control-plane/ # PYTHON FastAPI — specs, run state machine, compliance gate, SINGLE WRITER
│   └── runtime/       # PYTHON — backtest_runner + live_runner; imports doomberg-core
├── web/               # TS/React/Vite — observability UI; static renderer registry; NO sucrase
├── infra/             # Terraform (DOKS, Managed PG, Spaces, VPC, NetworkPolicy), Docker, compose
└── .github/workflows/ci.yml            # the gate (P0)
```

| Concern | Choice | One-line rationale |
|---|---|---|
| Backend language | **Python 3.12 end-to-end** | Crown-jewel quant + the security-boundary validator are numpy/Pydantic; polyglot re-introduces divergence bugs. |
| Quant engine | **numpy, ported as-is** | Proven, pure, deterministic; rewriting is pure downside. |
| MCP | **Official Python MCP SDK** (streamable-http + stdio) | First-party tool/schema support; co-located with core = in-process calls. |
| Control plane / gateways | **FastAPI** | Reuse v1's proven SSE + tenant contextvar; small money-path service scales independently. |
| Datastore | **Managed Postgres 16 + RLS** | Tenant isolation as a DB invariant; `FOR UPDATE` for the money path. |
| Object store | **DO Spaces** | Artifacts/logs/blobs; keeps Postgres lean. |
| Queue | **Postgres-backed (`pgmq`/graphile-worker)** | Avoids a second stateful system early; runs are versioned rows. |
| Real-time | **SSE, `Last-Event-ID`** | One-way append-only fan-out; trivial reconnect/replay; heartbeats fix v1's idle-kill. |
| Compute | **DOKS, plain containers + cgroups + NetworkPolicy** | Per-pod limits + egress-deny invariant; microVM deferred until untrusted code ships. |
| IaC | **Terraform + Docker** | Reviewable, reproducible; deploy layer gets real IaC, not click-ops. |
| Web UI | **React + Vite + TS** | Keep the terminal aesthetic as an observability surface; reuse panels, drop chat + codegen. |
| Observability | **structlog JSON + OpenTelemetry** | Correlates tool-call → backtest → fill; answers v1's "no logging." |

---

## 9. Phased roadmap

**The thinnest credible first *shippable* slice = Phase 1 + Phase 2** (agent calls in-process tools; UI renders the trace + a price-only backtest) — no DO, no deploy layer, no sandbox. This proves the entire vision and defers every hard infra problem.

**Critical path:** P0 → P0.5 (spikes) → P1 → P2 → P3 → P4. P5 is breadth on a proven spine.

**Phase 0 — Skeleton + the gate + frozen contracts.** Monorepo; `packages/contracts` with one round-trip schema generating pydantic + zod; empty service stubs; compose local stack; **CI as a required check** (lint/typecheck/tests; RLS-coverage test; pydantic⇄zod round-trip). *Exit:* a breaking contract change turns CI red and locks merge. *Demoable:* "the gate works."

**Phase 0.5 — Three de-risking spikes (parallel, before committing the rest) [feasibility #3].** (a) prove plain-container egress-deny + scale-to-zero on a throwaway DOKS cluster (and whether gVisor is even needed/viable — it isn't at launch); (b) produce **one defensibly-PIT backtest** and enumerate exactly which sources support it; (c) prove MCP trace + session correlation survive ≥2 real agent hosts (Claude/GPT). *Exit:* all three green or the plan changes. *Demoable:* a recorded real-host trace + one honest backtest.

**Phase 1 — Data Layer walking skeleton.** Port `engine/{stats,backtest,strategies,signals}` + `sources/prices`; stand up the MCP server exposing `market.get_ohlcv` + `backtest.run` (in-process, on the agent's machine). Wire a real BYO agent. *Exit:* an external agent discovers the tools, runs a real backtest, gets a provenance block. *Demoable:* **the core vision in miniature.**

**Phase 2 — Observability.** REST/SSE gateway + trace ingest; UI three-column trace (reasoning-optional-first) + backtest evidence panel, heartbeats keeping SSE alive. *Exit:* the live trace + equity curve render in real time. *Demoable:* **watch your agent think and produce an algo.**

**Phase 3 — Deploy Layer: one backtest on DigitalOcean.** Terraform up Managed PG (RLS) + Spaces + a backtest worker; control-plane `runs/` (versioned) enqueues, worker pulls, runs with an **aggregate deadline**, writes artifact. `propose_strategy` + human "Backtest" action wired. *Exit:* human-accepted spec → backtest on DO → firm-scoped result in UI. *Demoable:* **full vision end-to-end (research → propose → backtest on DO → observe).**

**Phase 4 — Live paper deployment.** `live_runner` + market-calendar scheduler; deployed strategy ticks on **real data**, proposes deltas, D applies under `FOR UPDATE`; freshness floor + skip-and-alert; Trades/Deploys panels go live. *Exit:* promote → ticks on real intraday → paper fills stream into Trades. *Demoable:* **a strategy paper-trading live, observable in real time.**

**Phase 5 — Breadth + hardening.** Remaining sources/engine modules as tools (news, edgar, fundamentals, rates, 13F, polymarket, risk/attribution); News/Ideas view; Boards; Redis Streams fan-out at threshold; OAuth/WAF/hash-chain audit tier; (gated spike) the operator-DAG + `CustomPythonNode` microVM. *Exit:* full catalog discoverable; load + canary gates green. *Demoable:* **the full tool-platform** — multi-source research → optimized strategy → live paper deploy.

---

## 10. Top risks & open questions

1. **PIT data honesty (CRITICAL, decided but watch).** Free sources can't deliver true PIT. We've scoped to price-only backtests and a `pit` capability flag. **Open:** budget/timeline for a vintaged fundamentals source (Sharadar/Compustat) to unlock the factor-backtest use case that is arguably the product's headline.
2. **Real-host trace fidelity (HIGH, spike-gated).** The reasoning rail may be empty against real hosts, and sessions may fragment across reconnects. P0.5(c) must confirm what we actually get before IA is finalized. **Open:** do we ship the reasoning rail at all in v2.0, or only the templated `derived` annotations?
3. **DO sandbox/egress viability (HIGH, spike-gated).** Plain-container egress-deny + scale-to-zero is assumed sufficient. P0.5(a) must validate NetworkPolicy + cluster-autoscaler behavior on DOKS. **Open:** does anyone on the team have DOKS-in-anger experience? If not, staff or budget for it.
4. **Event-bus scaling cliff (MEDIUM-HIGH).** Postgres LISTEN/NOTIFY has an 8KB cap and SSE replay hits the system-of-record. Mitigated by the day-one consumer interface. **Open:** the exact events/sec + concurrent-SSE threshold to trigger the Redis Streams cutover.
5. **Risk attestation completeness (MEDIUM-HIGH).** The post-projection gross-L1 gate must catch the general infeasibility class, not just the trivial cases. **Open:** enumerate the construction-scheme × constraint combinations that need explicit fixtures beyond the v1 311%-gross case.
6. **Operator-DAG deferral (MEDIUM).** Shipping parameterized primitives is faster but less expressive. **Open:** what fraction of target strategies the primitives actually cover, and the trigger to invest in the DAG.
7. **Spec handoff mechanism (MEDIUM).** datalayer never defined how a research session's analysis becomes a `StrategySpec` row. **Open:** the `propose_strategy` builder contract — which service writes the draft, under which `run_id`/`origin_session_id`, and how the UI shows "this proposal came from that research."
8. **Team size / parallelization (MEDIUM).** The plan assumes parallel workstreams (Quant, Control-plane, Runtime, UI, Infra) after P0 contracts freeze. **Open:** is the team large enough to run WS-A…E in parallel, or does the critical-path spine (P0→1→2→3→4) need to be strictly sequential?


====================================================================================================
FILE: docs/plans/doomberg-v2/critiques/feasibility.md
====================================================================================================

# Red-team critique: feasibility

I now have strong ground-truth. The engine is genuinely pure and portable (good), but the data layer has no real PIT vintaging, and the docs' central "Data Gateway makes PIT a property of the data plane" claim is far harder than implied. I have enough to write the red-team assessment.

I have enough ground truth. Here is the red-team assessment.

---

# Doomberg v2 — Build Feasibility & Sequencing Red-Team

I verified the load-bearing claims against v1 source before writing this. Findings, ranked by risk.

## What the docs get right (so I'm not just dunking)
- The engine **is** genuinely pure and portable: `engine/backtest.py:run_backtest` is `# Pure: no I/O. The caller owns fetching`; `engine/optimize.py` is "no DB / network / scipy ... trivially unit-testable." ~5,000 LOC of numpy that ports nearly verbatim. The "port the crown jewels" plan is sound and low-risk.
- Killing in-process codegen and making strategies declarative is the correct, non-negotiable call.
- `state.py` really does have the `SELECT ... FOR UPDATE` pattern (verified lines 151-162), so generalizing it is grounded.

Now the problems.

---

## Issue 1 — [CRITICAL] Point-in-time correctness is asserted, not achievable, with v1's data sources. The whole backtest value prop rests on this.

The Deploy doc claims PIT is "a **property of the data plane**" — the Data Gateway takes `asOf` and "returns only data that was knowable at asOf." **The underlying v1 sources cannot deliver this, and the docs never confront it:**

- `sources/prices.py` is Yahoo's live chart endpoint. Yahoo serves **survivorship-biased, dividend/split-restated** series with no vintaging. You cannot ask Yahoo "what did this close look like as known on date X." Truncating bars at `asOf` (which the doc proposes) does **not** fix restatement or survivorship — a delisted name simply isn't in the response *today*, so it's silently absent from any "historical" universe. This is the exact v1 survivorship lesson the docs claim to honor, re-introduced.
- `sources/fundamentals.py:fetch_fundamentals` returns **only a current snapshot** (`trailingPE`, `trailingEps` — today's values). `fetch_fundamentals_history` literally **estimates** the knowable-date as "period end + a conservative 45-day reporting lag" (verified, line ~125). That is a guess, not a filing date. A factor backtest on value/quality over this data has look-ahead baked into the *source*, and no gateway `asOf` parameter can remove bias the source never recorded.
- News (`publishedAt` from RSS `pubDate`) and EDGAR (`filingDate`) **do** carry real knowable-dates and are PIT-capable. So PIT correctness is *per-source*, not a uniform plane property.

**Resolution:** Demote the claim. PIT is a per-source *capability flag* surfaced in provenance (`pit: true|false|estimated`), not a guarantee the gateway can enforce. For v2.0, scope backtests to **price-only / technical strategies** (momentum, MA-cross, vol) where Yahoo's restated-but-consistent daily closes are defensible, and **explicitly forbid fundamental-factor backtests** until you have a vintaged fundamentals source (paid: Sharadar, Compustat PIT). Otherwise you ship a backtester whose headline use case is quietly wrong — the single worst possible outcome for a "financial tool-platform."

## Issue 2 — [CRITICAL] DOKS + per-job microVM sandbox + NetworkPolicy egress-deny + cluster-autoscaler is a massive infra project mis-sequenced as early/mid-phase.

The security and deploy docs casually require: gVisor/Kata or microVMs, seccomp profiles, cgroups v2, default-deny `NetworkPolicy` with a single allow to the Data Gateway, scale-to-zero autoscaling, a market-calendar-aware custom scheduler, and RLS migrations. That is **weeks-to-months of platform engineering** by someone who has run DOKS in anger. Meanwhile:

- The repo-sequencing doc puts the first DO run at **Phase 3** and has *no team-size or staffing* stated. WS-E ("Infra") is one parallel workstream expected to have "DO ready when the runner is."
- gVisor on DOKS is not a managed offering — you're installing and maintaining a runtime class on your nodes. Kata needs nested virt / bare-metal-ish nodes DO may not give you on standard droplets. **This is unvalidated.** Nobody confirmed gVisor runs on DO's managed nodes.

The deeper contradiction: the docs **also** say strategies are purely declarative (no agent code runs). **If specs are declarative and executed by your own trusted graph evaluator, you do not need a syscall-filtering microVM at launch.** The microVM is justified only by the *deferred* `CustomPythonNode`. The security doc itself says CustomPythonNode is "off by default, never shipped at launch" — yet it builds the entire heavyweight sandbox for it anyway.

**Resolution:** For v2.0, since no untrusted code runs, the runtime is *your own trusted code over validated data*. A plain container with cgroup limits + `activeDeadlineSeconds` + a default-deny egress NetworkPolicy is sufficient and is a fraction of the work. **Defer gVisor/Kata/seccomp to the phase that actually ships CustomPythonNode** — and gate that phase on a spike that proves the sandbox runtime works on DO. Don't build a microVM fleet to run numpy you wrote.

## Issue 3 — [HIGH] The "thinnest first slice" in the repo doc is wrong — it front-loads the spine but defers the riskiest unknowns.

Phase 1 ("two tools, agent calls them in-process, no DO") is a genuinely good thin slice and I'd keep it. But the phasing buries the three things most likely to kill the project until Phase 3-4:
- DO orchestration (Issue 2),
- PIT data correctness (Issue 1),
- real-time external-agent trace capture fidelity (Issue 5).

Classic critical-path inversion: the easy, already-proven work (porting pure numpy) is sequenced first; the unvalidated infra and the unsolved correctness problem are sequenced last, after sunk cost.

**Resolution:** Insert a **Phase 0.5 = three de-risking spikes, run in parallel with the Phase-0 skeleton, before committing to the phase plan:** (a) prove gVisor/egress-NetworkPolicy/scale-to-zero works on a throwaway DOKS cluster; (b) prove you can produce *one* defensibly-PIT backtest and enumerate which sources support it; (c) prove MCP trace capture survives a real Claude/GPT host (Issue 5). If any spike fails, the phase plan changes. Thin credible first *shippable* slice = Phase 1 + Phase 2 (agent calls tools in-process, UI renders the trace) with **no DO and no deploy layer at all** — that already demonstrates the core vision and defers every hard infra question.

## Issue 4 — [HIGH] Polyglot split (Python data-MCP + **TypeScript** control-plane) contradicts the architecture doc and re-introduces the backtest≠live divergence risk.

The repo-sequencing doc puts the control plane in **TypeScript**, while the system-architecture and deploy docs put it in **Python/FastAPI**. These are different designs presented as one. The TS choice is the worse one here:
- The control plane owns spec validation, the risk pre-attestation, and the lifecycle state machine. The risk attestation (`sum|w|` gross re-check) is the *exact v1 optimizer bug* and lives in numpy. Putting the control plane in TS means either re-implementing risk math in TS (a new divergence-bug class — the thing the docs explicitly try to kill) or an extra Python hop for every validation.
- It also splits the shared `core.run_tool` seam the architecture doc relies on (one shared Python core behind both MCP and REST). You can't share a Python core if the gateway is TS.

**Resolution:** Pick one. Given the crown jewels and the validator are Python, **the control plane is Python/FastAPI** (as topology + deploy docs say). The repo-sequencing doc's TS control plane should be overruled. Keep TS only for the web UI.

## Issue 5 — [HIGH] "Capture the agent's reasoning" is structurally limited and the UI over-promises it.

The honest core (MCP wire = trace) is correct and achievable: you own the server, so every `tools.call` is observable for free. But:
- The "REASONING rail" depends on `emit_reasoning` / MCP notifications that **a BYO agent will almost never call.** Claude Desktop, GPT, and custom hosts do not volunteer chain-of-thought to an MCP server. The realistic default is an **empty left column** — the centerpiece three-column UI degrades to two.
- The `X-Doomberg-Run` header / `session_id` correlation assumes the agent host forwards a stable session across reconnects. Many MCP hosts open a fresh transport per tool call or per task; you may get fragmented sessions you can't stitch into "one unbroken research→proposal→backtest chain." This is unproven against real hosts.
- The "inferred/templated annotations" fallback is reasonable but the docs sell it as a minor footnote when it'll be the *primary* content.

**Resolution:** Design the UI **reasoning-optional-first**: the tool-call timeline + evidence panels must be the compelling product with zero reasoning. Make the reasoning rail an opt-in enhancement, not the headline. Run the Phase-0.5 spike (Issue 3c) against ≥2 real agent hosts to learn what session/reasoning fidelity you actually get *before* designing IA around it.

## Issue 6 — [HIGH] Postgres LISTEN/NOTIFY as the launch event bus + SSE replay will not carry the trace + telemetry load and has a hard payload limit.

The topology doc launches the event bus on Postgres LISTEN/NOTIFY ("transactional, gap-free, one fewer moving part") and replays SSE from Postgres. Real constraints the doc ignores:
- NOTIFY payloads are capped at **8000 bytes**; trace payloads (tool args + result summaries + provenance) will exceed this, forcing a notify-then-SELECT pattern that adds DB read load per event.
- Every SSE reconnect replaying `from_seq` is a Postgres scan; with paper-live ticks + backtest progress + per-tool-call events fanning to multiple UI tabs, the system-of-record DB becomes the hot path for streaming. This is a known scaling cliff, not a "scale later" tweak.

**Resolution:** Fine for Phase 1-2 demos. But don't call it the launch bus uncritically — set a concrete threshold (events/sec, concurrent SSE clients) at which you move trace fan-out to Redis Streams, and write the `(run_id, seq)` consumer against an interface from day one so the swap is config, not rewrite. Keep money-path events transactional in PG; move *observability* fan-out off PG early.

## Issue 7 — [MEDIUM-HIGH] Two parallel, slightly-different security/spec models across docs = the seam where v1's "tested path ≠ shipped path" bug recurs.

The deploy doc's `StrategySpec` is a **signal-graph DAG of operators**. The security doc's strategy is a `{signal → construction → constraints → schedule}` **declarative graph** with a separate "scripted escape hatch." The data-layer doc has `backtest.run` as a research primitive over `engine/strategies.py` (which are `(closes, params) -> positions` functions, **not** a DAG). Three different mental models of "what a strategy is."

If the agent-facing `propose_strategy` schema, the validator, and the executor are built from different docs, the validated artifact and the executed artifact diverge — exactly v1's failure theme.

**Resolution:** One canonical `StrategySpec` schema in `packages/contracts`, authored once, with **one** validator and **one** evaluator consuming it. Decide now whether v2.0 strategies are (a) the existing parameterized `engine/strategies.py` primitives (far simpler, ships faster, covers MA-cross/momentum) or (b) the full operator-DAG (more expressive, much more validation surface). I'd ship (a) for v2.0 and defer the DAG; the DAG's semantic linter (cycle detection, feasibility pre-attestation, registry) is real work for marginal launch value.

## Issue 8 — [MEDIUM-HIGH] Risk pre-attestation "infeasibility" check is presented as easy; it's the v1 bug class and needs to be a hard, tested gate, not a lint.

The deploy doc's example — reject `top:2, longOnly, gross 1.0, maxNamePct 0.25` as statically infeasible — is correct in spirit but the *general* feasibility check across construction scheme × constraints × optimizer projection is nontrivial (it's why v1 shipped a 311%-gross book). Static config-level checks catch only the trivial cases; the real bug was the **projection** ending on net+box instead of gross-L1 (confirmed in `optimize.py` — `gross_limit()` floors gross at `|net|` but the projection order is the issue).

**Resolution:** The gross-L1 re-check must run **post-projection, in the executor, on every emitted target book**, refusing to emit a breaching book — not just a design-time lint on the spec. Make it a gating CI test with the v1 311%-gross case as a fixture. Treat the design-time lint as a nicety, the runtime attestation as the boundary.

## Issue 9 — [MEDIUM] IEX DEEP order-book reconstruction is correctly flagged as huge but still under-scoped as a launch tool.

Verified: `iex_deep.py` confirms "a single DEEP day is ~13 GB gzipped" and streams/decodes incrementally — the parsing is real and good. But exposing `market.reconstruct_order_book` as an MCP tool means a single agent call can pull and decode 13GB on your infra, on demand, per tenant. The data-layer doc's own open question #3 admits this. Per-call deadlines don't bound bytes; the v1 lesson was specifically the *unbounded byte stream*, not just time.

**Resolution:** Cut from v2.0 agent surface. If kept, it must be: explicit high-cost class, a hard **byte cap** (not just wall-clock), async job (not a synchronous tool call), and pre-materialized/cached per session date. Don't let an agent trigger 13GB of decode on a synchronous MCP call.

## Issue 10 — [MEDIUM] "Stale-while-revalidate keeps serving stale when breaker open" can serve unboundedly stale data to a money-adjacent path with only a flag to warn.

The data doc makes stale-serve honest via provenance (good). But paper-live re-evaluates signals on "REAL current market data via the Data Gateway." If the breaker is open and the gateway serves a stale quote labeled `freshness:stale`, the paper-live runtime may **trade on stale marks** unless it explicitly refuses stale on the execution path. Provenance honesty protects the *agent's reasoning*; it does not protect the *fill engine* unless someone wired a freshness floor into the tick.

**Resolution:** The paper-live tick must declare a max-staleness tolerance and **skip-and-alert** (the doc's own pattern for lost ticks) when data exceeds it, rather than fill on stale marks. Make freshness a hard precondition on the money path, distinct from the soft display label on the research path.

## Issue 11 — [MEDIUM] OAuth 2.1 + device-code + 15-min token minting + edge WAF + hash-chained tamper-evident audit is a lot of security surface for v2.0; some is gold-plating.

The security doc is excellent but maximalist. Hash-chained per-tenant audit streams, ASN reputation WAF, MFA/TOTP, device-code linking, and short-lived token exchange are all defensible *eventually*. For a paper-only launch with no real money and a handful of pilot tenants, building all of it pre-launch competes for the same scarce eng time as the actually-hard infra (Issue 2).

**Resolution:** v2.0 minimum: hashed API keys (already a v1 pattern), the RLS invariant + the CI test that fails on any unscoped table (this is the high-value one — keep it), per-principal rate limits, and append-only audit. **Defer** OAuth device-code, token exchange, hash-chaining, and WAF to post-pilot. Keep `deploy:live` unissuable (cheap, high value — keep).

## Issue 12 — [MEDIUM] RLS "cannot be forgotten" is overstated; it has real operational sharp edges the docs don't budget for.

RLS as the tenancy backstop is the right call, but the docs treat `SET LOCAL app.tenant_id` as free. Reality: it requires every connection to run as a non-superuser non-owner role (migrations/owner bypass RLS — a footgun), connection-pooler (PgBouncer transaction mode) interactions with `SET LOCAL`, and a discipline that the *worker* and *Data Gateway* connections also set the GUC. The cross-tenant escape hatch (`list_all_*`) is exactly where it'll be forgotten. The "global upstream cache" exception (data doc §4.2) also lives outside RLS and needs its own audited boundary.

**Resolution:** Keep RLS, but budget for the operational work: pooler config, a non-owner app role, and a test that the *pooled* path (not just a raw connection) enforces isolation. Make the global-cache boundary a single reviewed module, not an ad-hoc exception per call site.

---

## Bottom line — what to actually do for v2.0

1. **Ship Phase 1 + 2 only as the credible first release** (agent calls in-process tools; UI renders the trace + a price-only backtest). No DO, no deploy layer, no sandbox. This proves the entire vision and defers every hard problem.
2. **Run three de-risking spikes (Issue 3) in parallel before committing the rest of the phase plan:** DO sandbox/egress/autoscale viability, one defensible PIT backtest, real-host trace fidelity.
3. **Cut from v2.0:** fundamental-factor backtests (Issue 1), the operator-DAG spec in favor of parameterized v1 strategies (Issue 7), the microVM sandbox until CustomPythonNode actually ships (Issue 2), IEX DEEP as an agent tool (Issue 9), and the OAuth/WAF/hash-chain security tier (Issue 11).
4. **Resolve the two design contradictions now:** control plane language (Python, Issue 4) and the single canonical StrategySpec (Issue 7).
5. **Keep as load-bearing and non-negotiable:** declarative-only / no in-process eval, the RLS invariant + its CI test, the post-projection gross-L1 attestation as a *runtime gate* (Issue 8), aggregate deadlines, and `deploy:live` unissuable.

The single biggest honesty gap: **the docs sell point-in-time-correct backtesting as an infra property when the free data sources can't support it.** Fix that framing before anyone builds the Data Gateway, or you ship a backtester that lies.


====================================================================================================
FILE: docs/plans/doomberg-v2/critiques/integration.md
====================================================================================================

# Red-team critique: integration

I have all six design docs in full. Let me cross-reference the key contradiction surfaces before writing up the findings. The most load-bearing conflicts are around language choice, the spec/sandbox model, and tenant-key naming, so let me verify a couple of specifics in the docs rather than re-read everything.

The docs are self-contained; no file reads needed — the contradictions are textual and I have the complete text. Here are the integration gaps and contradictions.

---

**1. Control-plane language: Python vs TypeScript (repo-sequencing ⊥ topology, deploylayer, security)**
- repo-sequencing puts the **control plane in TypeScript** (`services/control-plane`, Express/Fastify, drizzle, "keeps heavy CPU work in Python where it belongs").
- topology (§5 D) and deploylayer (§3, §6) both specify the control plane in **Python + FastAPI**, and deploylayer's entire spec validator, semantic linter, and risk pre-attestation are **Pydantic v2** — i.e. the security boundary lives in Python.
- This is not cosmetic: the spec validation gate (the thing that stops a malicious spec) lives in whichever service owns it. If the control plane is TS but the validator is Pydantic, you either duplicate the schema (drift = exactly v1's failure) or you have a Python validation sidecar the TS layer calls (an unowned hop). security also assumes one `TenantSession`/RLS GUC-setting data layer; repo-sequencing has drizzle (TS) owning the schema while deploylayer has SQLAlchemy core (Python) owning it.
- **Resolution:** Pick one language for the control plane. Given the spec validator, risk attestation, and operator registry are all Python and are the trust boundary, make the control plane Python+FastAPI (topology/deploylayer/security all agree); repo-sequencing's TS control plane is the outlier and should be overruled. If TS is kept for I/O orchestration, the spec-validation + money-path repo must still be a single Python service, and repo-sequencing must say so explicitly.

**2. The strategy model: declarative-only vs "scripted escape hatch exists" (deploylayer/security ⊥ topology/datalayer)**
- topology states flatly: "Strategies are declarative specs, not code… **no free-form code field exists**" (§4.3), and datalayer echoes "Tools are a fixed, versioned catalog… No agent-authored code executes."
- deploylayer (§0) designs a `CustomPythonNode` seam ("off by default, firm-gated… we design the seam; we don't ship it"). security (§3.1) goes further and makes "**Scripted (escape hatch): the agent submits Python**" a first-class second execution mode with a whole sandbox built for it.
- topology's hard invariant ("no free-form code field exists") directly contradicts a spec schema that has a `CustomPythonNode` op. One doc's "this field cannot exist" is another's "this field exists but is flagged off."
- **Resolution:** Decide whether the *schema* admits a code node at all. Recommend: at launch the `StrategySpec` schema literally has no code-node variant (topology's invariant holds — un-expressible beats off-by-default). The sandbox (security §3.2) is still built as defense-in-depth for declarative operators, but security §3.1's "Scripted mode" and deploylayer's `CustomPythonNode` must be re-labeled "future, not in launch schema," not "escape hatch the agent can submit."

**3. Who owns data egress for workers — and is there a Data Gateway at all? (deploylayer ⊥ datalayer/topology/repo-sequencing)**
- deploylayer introduces a **Data Gateway**: a control-plane-side service that is the *only* network workers can reach, wraps `sources/`, enforces point-in-time `asOf`, and is where PIT correctness lives. Workers have deny-all egress.
- datalayer owns the same `sources/` adapters behind the **MCP/REST core** with its own caching, provenance, resilience, and tenant model — and never mentions a Data Gateway. topology (§1 C/G) says workers "use the SAME trusted engine image as the core" and emit telemetry, but routes data through "(C)'s resilience wrapper," not a separate gateway. repo-sequencing ports `sources/` into `services/data-mcp` (the MCP server), with no Data Gateway service in the repo tree.
- So `sources/` has **two competing owners**: the data layer (datalayer/repo-sequencing) and a worker-only Data Gateway (deploylayer). PIT-`asOf` enforcement, provenance shape, and the breaker keys would be implemented twice and can diverge.
- **Resolution:** Make the Data Gateway and the Data Layer core the *same* service (or the gateway a thin PIT-enforcing facade in front of the one `sources/` package). Decide the owning repo (it should be wherever `sources/` lives once). The worker's deny-all-egress-except-gateway rule (deploylayer §4) then points at that one service.

**4. Point-in-time correctness: data-plane property vs operator/engine property (deploylayer ⊥ datalayer)**
- deploylayer §2.0.1 makes PIT correctness "a **property of the data plane**" — the gateway returns nothing with `publishedAt > asOf`, so operators *cannot* cheat.
- datalayer exposes PIT-ish tools (`market.get_daily_closes` "PIT-safe", `screen.universe` "PIT-aware via listedAt") but its envelope has **no `asOf` request parameter** — `asOf` in datalayer's provenance is the *data's* timestamp (output), not an *input* that truncates the response. The data layer's tools answer "as of now"; the backtest needs "as of bar i."
- A backtest worker calling the shared core's tools would get live data, not as-of-bar data, unless the gateway adds the truncation the MCP tool contract doesn't express.
- **Resolution:** Add `asOf` as an optional input to the data-fetch tool schemas (datalayer §2.2), or formally state that the worker path uses a *different* entry point (the Gateway's `asOf` RPC) than the agent path — and reconcile that with topology's "MCP and UI can never diverge, one `core.run_tool`" claim.

**5. Tenant key name and type: `tenant_id` vs `firmId`/`firm_id`, string vs uuid (all docs collide)**
- topology, datalayer, security: `tenant_id`. deploylayer: `firmId`/`firm_id` (every table, the RLS GUC is `app.firm_id`, the spec stamps `firmId`). webui: `firmId`. security's RLS GUC is `app.tenant_id` (uuid); deploylayer's is `app.firm_id`.
- Same concept, two names and two GUC keys (`app.tenant_id` vs `app.firm_id`) and an unstated type (uuid in security; opaque string in datalayer's `dbg_<tenant>_<random>` key format). The contracts package (repo-sequencing) generates types from one IR — it cannot generate both.
- **Resolution:** Canonicalize one name (`tenant_id`), one GUC (`app.tenant_id`), one type (uuid) in `packages/contracts/provenance` + the schema IR; ban the alias in CI.

**6. Agent principal & auth model: who is `actor`/`agent_id`, and does it carry scopes? (security ⊥ topology/datalayer)**
- security defines a rich model: Tenant→User→**Agent (stable principal)**→Credential, with OAuth device-code linking, 15-min bearer tokens minted from long-lived keys, and per-credential scopes (`data:read`, `deploy:paper`, etc.).
- topology's MCP §3.1 resolves token → `(tenant_id, agent_id)` and `ctx` carries `actor` — but never defines `agent_id` vs `actor`, and §4.1 says the agent "can read and PROPOSE only… cannot promote" as a *blanket* rule, with no scope axis.
- datalayer §4.1 proposes its **own** auth (`dbg_<tenant>_<random>` keys, OAuth scopes mapped to *tool groups* `read:market`/`compute:risk`) — a different key format (`dbg_` vs security's `dmbg_`), different scope taxonomy (tool-group vs capability), and no Agent-vs-Credential distinction.
- **Resolution:** security's account model is the authoritative one; topology and datalayer must adopt `agent_id` as the stable principal, the `dmbg_` key format, and the capability-scope taxonomy. Reconcile datalayer's per-tool-group scopes with security's per-capability scopes (they overlap but aren't identical). topology's "agent can propose, not promote" must be expressed as the absence of the `deploy:paper`+human-gate, not a separate hardcoded rule.

**7. Event/trace data model conflict: `(run_id, seq)` Postgres LISTEN/NOTIFY vs `event` table vs `TraceEvent` SSE — three schemas for one stream (topology ⊥ deploylayer ⊥ webui)**
- topology §3.4 defines the canonical `trace_event(run_id, seq, type, span_id, parent_span, payload, provenance, tenant_id, ts)`, gap-free monotonic `seq`, Postgres LISTEN/NOTIFY bus, replay `GET /streams/{run_id}?from_seq=N`.
- deploylayer §3 has an `event` table (append-only observation stream) and streams over SSE, but never mentions `seq`, gap-free ordering, `span_id/parent_span`, or LISTEN/NOTIFY — and it's a *separate service's* Postgres (the deploy control plane) from the data layer's.
- webui's `TraceEvent` has `seq`, `callId`, `panelType`, `citesCallIds`, `kind` enum (`thought|tool_call|...`) that **doesn't match** topology's `type` enum (`tool_call|tool_result|reasoning|run_state|...`). webui reconnects with `Last-Event-ID`; topology reconnects with `from_seq`. These are different wire contracts.
- Critically: research happens against the **data layer** (datalayer's MCP server emits session events), deploy happens against the **control plane** (deploylayer's `event` table). topology claims "one unbroken chain research→proposal→backtest→paper" via `parent_span`/`origin_session_id` — but those events live in **two different services' datastores** with no defined cross-service `seq` authority. Gap-free monotonic `seq` across two independently-writing services is impossible without a shared sequencer, which no doc owns.
- **Resolution:** One event schema in `packages/contracts/events` (reconcile `kind`/`type` enums, `seq` vs `Last-Event-ID`, `panelType` placement). Decide the single writer/sequencer for `seq` — either one shared `trace_event` store both services write to (then `seq` is per-`run_id` and the data layer and control plane must coordinate run_ids), or accept that `seq` is per-service and the UI stitches via `origin_session_id` (dropping topology's "gap-free across the whole chain" claim).

**8. `panelType` / renderer contract: who owns the tool-output→panel mapping? (webui ⊥ datalayer ⊥ topology)**
- webui's whole Evidence column depends on each `tool_result` carrying a `panelType` that keys into a static renderer `Map`, with `data` matching the v1 panel's existing prop shape.
- datalayer's envelope (`{data, provenance, partial, warnings}`) has **no `panelType` field**, and its `data` is the tool's own payload shape — not guaranteed to match v1 `BacktestPanel`'s prop contract (v1 panels ate `skills.py:build_*` output, which datalayer is *replacing* with new tool payloads).
- topology says the UI is a "pure event projection" and types are "generated from the OpenAPI spec," implying the panel mapping is derived from tool output type — but nothing assigns `panelType` or guarantees payload⇄panel-prop compatibility.
- **Resolution:** Add `panelType` (or a `render` hint) to the tool-result envelope in the contracts package, and make the v1 panel prop shapes part of the tool output contract (contract test: every tool with a `panelType` produces `data` that the named panel renders without `as any`). Otherwise webui's "lift the v1 switch into a static Map" silently breaks on payload drift — the exact failure repo-sequencing warns about.

**9. Promotion/human-approval flow has no clear owner across the MCP/UI/control-plane seam (topology ⊥ datalayer ⊥ deploylayer ⊥ webui)**
- topology: `propose_strategy` is the only Deploy tool the agent can call; **promotion is a human action through (B) the REST gateway**.
- deploylayer: "The agent calls `promote(deployment_id)`… there's no NL parsing on the mutation path" — i.e. promotion is an **MCP tool the agent calls**, not a human UI action. security gives the agent a `deploy:paper` scope (agent can deploy to paper).
- These flatly conflict: topology says a human promotes via the web UI; deploylayer/security say the agent promotes via MCP/scope. datalayer doesn't expose any deploy/promote tool at all (it ends at "the resulting strategy spec is handed to the DEPLOY LAYER" — handoff mechanism undefined). webui §1.2 has a "Deploy (paper)" button (human action) consistent with topology, contradicting deploylayer.
- **Resolution:** Define exactly one promotion authority. Recommend topology's: agent `propose`s, a human `promote`s through (B); the agent's `deploy:paper` scope (security) should be narrowed to "may *request* a deployment that requires human acceptance," and deploylayer's `promote(deployment_id)` becomes a control-plane action invoked by the human UI, not an agent MCP tool. Also define the proposal handoff: how does datalayer's research session spec become deploylayer's `strategy_spec` row (which service writes it, under which `run_id`/`origin_session_id`).

**10. StrategySpec schema vs `propose_strategy` schema vs research-session spec — three spec shapes (topology ⊥ deploylayer ⊥ datalayer)**
- topology §2b: spec = `{universe, signal_id+params, construction_scheme, rebalance, sizing, risk_limits, costs}`.
- deploylayer: spec = a **signal graph** `{specVersion, graph:{nodes,edges}, risk, execution, resources}` — a fundamentally different shape (DAG of operators vs flat signal_id+scheme).
- datalayer: the agent composes research then "the resulting strategy spec is handed to the DEPLOY LAYER," but never defines the spec; its tools (`signals.evaluate_signal`, `portfolio.construct`) return analysis, not a spec the agent can serialize into either topology's flat form or deploylayer's graph form.
- **Resolution:** deploylayer owns the spec; topology's flat `{signal_id, construction_scheme}` description must be updated to the graph form (or explicitly mapped: `signal_id`→a node `op`, `construction_scheme`→a `to_weights` node). datalayer needs a `propose_strategy`/spec-builder contract that emits exactly deploylayer's `StrategySpec` schema, validated against the same operator registry — otherwise the "allow-list" topology and deploylayer both invoke is two different lists.

**11. Operator registry vs engine allow-list vs MCP tool catalog — three "fixed allow-lists," relationship undefined (deploylayer ⊥ topology ⊥ datalayer)**
- deploylayer: the **operator registry** (`load_closes`, `momentum`, `cross_sectional_rank`, `to_weights`) is "the entire trust surface," ported from `engine/strategies.py` + new ops.
- topology §2b: specs validate against "the engine's closed allow-list," every field "mapping to an existing engine primitive."
- datalayer: the agent's research tools are a *different* catalog (`signals.evaluate_signal`, `portfolio.construct`, `backtest.run`) — these are MCP tools, not spec operators.
- So there are two parallel vocabularies: what the agent can *call live* (datalayer tools) and what it can *encode in a deployed spec* (deploylayer operators). They overlap heavily (momentum, ranking, construction) but are maintained separately, so an agent can research with a signal that has no operator equivalent (or vice versa), and the "infeasible at design time" risk attestation can't reason about a tool the registry doesn't know.
- **Resolution:** Derive both from one source. The operator registry and the signal/construction MCP tools should share the underlying `engine/` primitive definitions in `packages/contracts`, with an explicit mapping table (every deployable operator ↔ its research-tool counterpart). Document which research capabilities are intentionally *not* deployable.

**12. Worker writes vs control-plane single-writer for the paper book — and where `paperbook`/`execution` live (topology/deploylayer agree on intent but split the code; datalayer also claims execution)**
- topology §4.4: workers "PROPOSE deltas, never write the book"; (D) is single writer under serialized txn; worker proposes, (D) applies.
- deploylayer §2.2: the **paper-live tick worker itself** "loads the current book from the control plane (under a lock)… applies fills, **atomically persists the new book**" — i.e. the *worker* writes the book (under advisory lock + version), not "proposes a delta to (D)." These are different concurrency models (worker-as-writer vs control-plane-as-sole-writer).
- Compounding it: `engine/paperbook.py` + `engine/execution.py` are claimed by **datalayer** (`execution.simulate_orders`, `execution.tca_report` as MCP tools), **deploylayer** (`runtime_core/accounting`), and **repo-sequencing** (`paperbook.py`→`runtime/`). Three homes for the money-path accounting code.
- **Resolution:** Pick one writer model. topology's "worker proposes delta, (D) applies in serialized txn" is the safer invariant and matches security's "single TenantSession writer"; deploylayer's "worker persists the book directly" should be rewritten to propose-and-apply, OR topology updated to bless worker-writes-under-lock (but then "single writer = (D)" is false). And `paperbook`/`execution` must live once (shared `runtime_core`/quant package) and be *imported* by both the MCP `execution.*` tools and the runtime — not ported into three trees.

**13. (Secondary) SSE reconnect/replay contract mismatch (topology ⊥ webui ⊥ repo-sequencing/deploylayer)**
- topology: client reconnects with `?from_seq=N`, server replays `>N` from Postgres then tails LISTEN/NOTIFY. webui: client reconnects with `Last-Event-ID` (the `seq`), SSE native. deploylayer/repo-sequencing: SSE with heartbeats but no replay/`from_seq` mechanism specified.
- `from_seq` query-param replay and `Last-Event-ID` header replay are different server implementations; only one should be built. Heartbeat token also differs (topology `: keepalive` + `run_progress` events).
- **Resolution:** Standardize on `Last-Event-ID` (native EventSource reconnect, which is what webui's reused v1 parser already does) carrying `seq`, with a documented replay-from-`seq` on the server; delete the `?from_seq=` variant or make it an explicit fallback. Put the heartbeat format in the contracts package so all SSE producers (data layer, control plane) emit the same keepalive.

---

**Cross-cutting meta-issue:** the single largest structural gap is that **research (data layer) and deploy (control plane) are designed as two separately-owned services with two Postgres instances, two auth key formats, two spec shapes, two allow-lists, and two event tables — yet topology asserts one shared core, one event spine, one unbroken `run_id` chain, and "MCP and UI can never diverge."** Issues 3, 5, 6, 7, 9, 10, 11 are all facets of that seam. The highest-leverage resolution is to (a) freeze `packages/contracts` (events, spec, provenance, tenant key, auth principal) before any service is built — exactly repo-sequencing's stated Phase-0 unlock, which the other five docs then violated by each inventing their own shapes — and (b) name a single owner for the `sources/`+`engine`+`paperbook` code so it is imported, never re-ported, by the MCP server and the workers.


====================================================================================================
FILE: docs/plans/doomberg-v2/designs/datalayer.md
====================================================================================================

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


====================================================================================================
FILE: docs/plans/doomberg-v2/designs/deploylayer.md
====================================================================================================

# Design: Deploy Layer & Control Plane (DigitalOcean)

I have everything I need. Returning the design doc.

---

# Doomberg v2 — Deploy Layer Design

**Scope:** the control plane + runtime that runs backtests and paper-live strategies on DigitalOcean CPU clusters. Greenfield. Built so an external (BYO) agent can deploy a strategy and the web UI can observe it.

**North star from v1's review:** every architecture decision below is chosen to *not* repeat the five cross-cutting failures — static-guard-then-trust, silent swallowing, per-store (not invariant) tenancy, unlocked read-modify-write on the money path, and per-call-but-not-aggregate timeouts. These map to concrete invariants, not aspirations.

---

## 0. The load-bearing decision: declarative spec, not arbitrary code

**A deployed strategy is a declarative `StrategySpec` (a signal graph over a fixed library of operators), never arbitrary user/agent code.** This is the single most important call in the whole layer and it directly kills v1's two critical RCEs at the root.

Why declarative wins here:

1. **v1 already proved the dangerous path is unsafe.** `code_guard.py` is an AST allow-list that the review showed is trivially bypassed (`string.Formatter().get_field("0.__globals__[...]")` reaches a live `__import__`), and worse, the *validation* subprocess didn't even cover the in-process `exec_module`/`build()` that actually ran. "Static guard then trust" produced five findings from one decision. We do not get a second chance to relitigate this.
2. **v1's quant value is already declarative-shaped.** `engine/strategies.py` strategies are `(closes, params) -> target_position_array` pure functions. `engine/backtest.py`, `paperbook.py`, `execution.py` are pure numpy, no I/O. The proven edge isn't in users writing Python — it's in *composing these primitives*. A spec captures 95% of real strategies (MA crossover, momentum, mean-reversion, cross-sectional factor ranks, multi-asset rebalancing) with zero code execution.
3. **The agent is external and untrusted by definition.** BYO-agent means the thing emitting strategies is outside our trust boundary. A declarative spec is *data we validate*, not *code we run*. We can diff it, version it, render it in the UI, reproduce it, and reason about it. Arbitrary code is none of those.

### What a `StrategySpec` is

A versioned, JSON/YAML document — a **signal graph**: nodes are typed operators drawn from a **fixed, server-owned operator registry**; edges pass numpy arrays (or small structured frames). The agent emits this; we validate it against a schema + a semantic linter before anything runs.

```jsonc
{
  "specVersion": "1.0",
  "id": "strat_01J...",            // server-assigned, never client-trusted
  "firmId": "...",                  // stamped from auth, never from payload
  "name": "dual-momentum-tech",
  "universe": { "symbols": ["AAPL","MSFT","NVDA"], "source": "prices" },
  "graph": {
    "nodes": [
      { "id": "px",  "op": "load_closes", "args": { "lookbackBars": 252 } },
      { "id": "mom", "op": "momentum",    "in": ["px"], "args": { "lookback": 90 } },
      { "id": "rank","op": "cross_sectional_rank", "in": ["mom"], "args": { "top": 2 } },
      { "id": "tgt", "op": "to_weights",  "in": ["rank"], "args": { "gross": 1.0, "longOnly": true } }
    ],
    "output": "tgt"
  },
  "risk": { "maxGross": 1.0, "maxNet": 1.0, "maxNamePct": 0.25 },
  "execution": { "costBps": 5, "algo": "vwap", "rebalance": "daily@close" },
  "resources": { "tier": "standard" }
}
```

**The operator registry is the entire trust surface.** Each `op` maps to a vetted pure function (most already exist in `engine/`). Adding an operator is a code review + a new server release — not a runtime event. There is no `op: "eval"`, no free-text expression node, no lambda. If a strategy genuinely needs logic the registry can't express, that's a feature request to add a *reviewed* operator, not a hole to punch.

**Escape hatch, deliberately deferred and isolated:** a `CustomPythonNode` (a single pure `(inputs, params) -> array` function) *can* exist later, but only ever runs inside the Worker sandbox (Section 1) with stripped builtins, no network, rlimited — and it is **off by default, firm-gated, and never on the control-plane path**. We design the seam; we don't ship it at launch. The v1 lesson is explicit: "sandboxed self-built skills as a real product — *only after* out-of-process exec." Same rule here.

### Spec validation (the gate, run before any provisioning)
- **Schema validation** (Pydantic v2): types, required fields, value ranges.
- **Semantic lint:** graph is a DAG (no cycles), every `in` references an existing node, every `op` is in the registry, the output node produces weights, declared `risk` limits are internally consistent (`maxNet <= maxGross`).
- **Risk pre-attestation:** reject specs whose static config can't satisfy limits (e.g. `top: 2, longOnly, gross 1.0` with `maxNamePct 0.25` is infeasible — 2 names can't fill 100% gross under a 25% cap). This is the *design-time* analogue of v1's optimizer gross-exposure bug, caught before a worker ever runs.
- `firmId` and `id` are **always server-stamped**, never read from the payload (kills the v1 IDOR class at the door).

---

## 1. Safe execution model (out-of-process, sandboxed, rlimited, egress-controlled)

Even though specs are declarative, we **still execute everything out-of-process** with full isolation — defense in depth, and the mandatory home for the future `CustomPythonNode`. The runtime never runs in the control-plane process. Ever. (v1's fatal mistake was running generated work in the API process.)

**Worker process model (per job):**
- **Separate OS process**, one job at a time, spawned fresh, killed at completion. No long-lived interpreter accumulating state across tenants.
- **Linux namespaces + cgroups v2** (we run our own container image; see DO topology in §4). Each job container gets: `cpu.max` quota, `memory.max` hard cap (OOM-kill, not swap-thrash), `pids.max`, ephemeral writable `/tmp` only, read-only root FS.
- **Network egress: deny-by-default.** Worker containers have **no outbound internet**. The only thing they can reach is the **Data Gateway** (Section 2.0) over a private VPC address on one port. They cannot reach Yahoo/EDGAR/FRED directly, cannot reach the control-plane DB, cannot exfiltrate. This is the structural fix for v1's "egress was wherever a source adapter decided to make an HTTP call." Egress is now an *invariant enforced by the network*, not by code review of each adapter.
- **Stripped interpreter for any code node:** `__builtins__` reduced to a safe map, no `open`/`__import__`/`eval`, `RLIMIT_AS`/`RLIMIT_CPU`/`RLIMIT_NOFILE` set before exec, `seccomp` profile blocking `socket`/`ptrace`/`exec*`.
- **Aggregate wall-clock deadline per job** (not just per-call). v1 had per-call timeouts that summed past the proxy ceiling; here the supervisor sets a hard job deadline at spawn and SIGKILLs on breach, recording `status=timeout` with the partial artifacts. This is the IEX-13GB-stream lesson generalized.
- **Determinism contract:** seed is part of the spec/job; the engine is pure numpy; same spec + same point-in-time data window ⇒ identical artifact hash. This makes "Reproduce this run" (a v1 roadmap ask) free.

**Failure handling is explicit, never swallowed.** Every worker terminal state is one of `succeeded | failed | timeout | oom | killed | data_unavailable`, with a reason string and structured logs shipped to the control plane. No bare `except: pass`. A data gap surfaces as `data_unavailable` with coverage info — never a silently fabricated curve (v1's `paperbook.py` already refuses synthetic curves; we keep that contract end-to-end).

---

## 2. The two runtimes (shared core)

### 2.0 Shared execution core — `runtime-core`
A single Python package, imported by both runtimes, containing:
- The **operator registry** (ports of `engine/strategies.py`, plus `cross_sectional_rank`, `to_weights`, factor ops from v1's `factor_model.py`).
- The **graph evaluator** — topologically evaluates the DAG, calling pure operator fns.
- The **portfolio/accounting kernel** — ports `engine/execution.py` (`generate_orders`, VWAP/TWAP/POV fills, TCA) and `engine/paperbook.py` (`position_marks`, `book_value`, `nav_curve`).
- The **risk attestation** — post-projection re-check of `sum|w|` vs gross *after* the final budget step (the exact v1 optimizer bug: `_project_feasible` ended on net+box, not gross L1, and returned 311%-gross books as "optimal"). Here the core refuses to emit any target book that breaches declared limits; it returns `infeasible-relaxed` with the violation.
- The **Data Gateway client** — the *only* way a worker gets data (see below).

Backtest and paper-live differ only in their **clock** and their **data window source**. Same evaluator, same accounting, same risk gate. One codebase, two drivers.

### 2.0.1 Data Gateway (point-in-time correctness lives here)
A control-plane-side service (reachable only from worker VPC) that wraps v1's `sources/` adapters behind one authenticated RPC. Critically it takes an **`asOf` parameter** on every call and **returns only data that was knowable at `asOf`** — no row with `publishedAt > asOf`, prices truncated at the `asOf` bar. This makes point-in-time correctness a **property of the data plane**, not something each operator must remember (v1's review flagged misaligned forward-return windows and look-ahead in `engine/signals.py` — we remove the operator's ability to cheat by never handing it future data).

The gateway also: enforces tenant scoping on cached data, applies the resilient breaker/retry (v1's `_resilient.request`, routing the Treasury/FRED fetches that v1 left un-wrapped), and returns a `{source, asOf, freshnessSec, mode, coverage}` provenance block on every response — surfaced straight to the UI (the v1 "data lineage" roadmap item, now built in).

### 2.1 Backtest runtime
- **Clock:** simulated, iterates historical bars from a fixed `[start, end]`.
- **Data:** one bulk point-in-time pull from the Data Gateway at job start (the window the spec needs). Backtest then "replays" bar-by-bar, each step seeing only `data[:i+1]` — structurally no lookahead. v1's `run_backtest` already encodes `held[1:] = target[:-1]`; we keep that and additionally enforce it at the data layer.
- **Mode:** CPU-bound burst. Spawn, run to completion (seconds to a few minutes), emit artifacts, die.
- **Output artifact:** equity curve, drawdown, trade log, full stat block (port `engine/stats.py`), plus **always** the walk-forward / overfitting diagnostics from v1's `run_walk_forward` (deflated Sharpe, PBO/CSCV, OOS degradation, honest `coverage.usable=false` when history is too short). Overfitting honesty ships by default, not as a toggle.

### 2.2 Paper-live runtime
- **Clock:** real wall-clock, driven by the control-plane scheduler on the spec's `rebalance` cadence (e.g. `daily@close`).
- **Data:** real, current market data via the Data Gateway (no `asOf` truncation — `asOf = now`).
- **Fills:** against a **simulated/paper book** (port `engine/paperbook.py` + `execution.py`). Live REAL prices, fills against the paper book — exactly the launch scope. The paper book is the durable, marked-to-market state; `nav_curve` reconstructs P&L from real closes since inception (never synthetic).
- **Mode:** **stateless tick worker, not a long-running daemon.** Each scheduled rebalance is a *short job*: the scheduler wakes it, it loads the current book from the control plane (under a lock — see §3), pulls data, evaluates the graph, computes target weights, generates paper orders, applies fills, **atomically persists the new book**, emits a trade/observation event, and exits. Between ticks nothing runs. This is deliberate: long-lived worker processes were where v1 accumulated unscoped global state. A stateless tick model means a crash loses one tick, not the book.
- **Promotion provenance:** when a backtested spec is promoted to paper, the inception, capital, seed, and the backtest artifact hash are stamped on the paper book for audit replay.

---

## 3. Control plane

A stateless API/orchestrator (FastAPI) over Postgres. It **never executes strategy logic**; it only validates specs, schedules jobs, persists state, stores artifacts, and streams observability to the UI and to the agent (via MCP/SSE).

### Core entities (Postgres, every table carries `firm_id`, indexed, filtered in *every* query)
- `strategy_spec` — immutable versioned specs (new version = new row; specs never mutated in place → reproducibility + clean diffs for the UI).
- `deployment` — a spec bound to a runtime + lifecycle stage + paper book.
- `job` — one execution (backtest run or one paper-live tick); status, deadline, resource tier, worker id, reason.
- `paper_book` — positions + cash + capital + inception; the money-path row.
- `artifact` — pointers to Spaces (DO object storage): curves, trade logs, stat blocks, logs.
- `event` — append-only observation stream (tool/graph-node activity, trades, ideas) for the UI trace and the agent.

### Tenant isolation as an invariant (not per-call-site)
v1's #3 failure: tenancy was correct in some stores, absent in others (`template_store`, in-memory `get_dashboard`). Fix: **a single repository layer where `firm_id` is a mandatory, non-optional argument on every read and write**, enforced by:
- Postgres **Row-Level Security** policies keyed on a session GUC (`app.firm_id`) — the DB rejects cross-firm rows even if application code forgets a `WHERE`. Defense in depth: even a bug can't leak.
- A repo base class that *requires* `firm_id`; no in-memory fallback store with different scoping rules (v1's IDOR came from a `_mem` path that ignored scoping when `DATABASE_URL` was unset). There is one path: Postgres.
- The Data Gateway also scopes cached data by firm.

### Money-path concurrency (no unlocked read-modify-write)
v1's #4 failure: strategy books updated via unlocked `INSERT ... ON CONFLICT` over a stale read; the worker advisory lock guarded worker-vs-worker but not worker-vs-API. Fix: **every `paper_book` mutation is `SELECT ... FOR UPDATE` inside one transaction**, plus an **optimistic `version` column** as a backstop. Since paper-live is a single-tick-at-a-time model per deployment, we also take a per-deployment advisory lock so two ticks can't overlap. The mutation path is one function; there is no second writer.

### Lifecycle (explicit state machine, classify-before-act)
`draft → validated → backtesting → backtested → paper_pending → paper_live → paused → retired`, with `promote` (backtested→paper) and `pause`/`resume` as guarded transitions. Each transition: validates the source state, writes an audit `event`, is idempotent. v1 had lifecycle keyword-routing fire *before* intent classification, mutating state on a *question* ("how do I retire a strategy?"). Here lifecycle is an explicit API/MCP action with a typed verb — never inferred from free text. The agent calls `promote(deployment_id)`; there's no NL parsing on the mutation path.

### Scheduling & deadlines
- Backtests → a **work queue** (Redis/RQ or DO-managed Postgres-backed queue) consumed by autoscaled backtest workers.
- Paper-live ticks → a **scheduler** (cron-like, market-calendar-aware) that enqueues a tick job per live deployment at its cadence.
- Every job carries an **aggregate wall-clock deadline** set at enqueue; the worker supervisor enforces it (the v1 "per-call but no aggregate budget" fix). Jobs past deadline are SIGKILLed and recorded `timeout`.
- **Heartbeats:** workers heartbeat to the control plane; a missed heartbeat past threshold marks the job `lost` and (for backtests) re-queues once, (for paper-live) skips the tick and alerts — never silently hangs.

### Observability (the product, not an afterthought)
The UI is an *observation surface*. The control plane streams the `event` table over SSE: graph-node evaluations, the agent's tool calls/args/results (captured because the agent talks to us via MCP), generated target books, paper fills, and the data-provenance badges. Every artifact is reproducible (spec hash + data `asOf` set + seed). Logs/metrics: structured JSON logs to Spaces + a `/health` panel exposing Data Gateway breaker state, queue depth, worker pool saturation, and tick lag — the v1 "SLA/health panel" roadmap item.

### CI that actually gates
v1 ran 3 of 33 suites and had no workflow. Non-negotiable here: a GitHub Actions `required` check runs the full `pytest` suite, the spec-validator property tests, a **golden backtest determinism test** (same spec ⇒ same artifact hash), a **lookahead-detection test** (a spec that tries to peek forward must produce identical results whether or not future bars exist in the store), and a **tenant-isolation test** (firm A cannot read firm B's book/spec/artifact). No merge without green.

---

## 4. DigitalOcean topology (opinionated)

**Choice: DOKS (DigitalOcean Kubernetes) with two node pools + Spaces + Managed Postgres + a VPC. Not App Platform, not raw Droplets.**

Justification against the workload's two distinct shapes:

| Need | Backtests (bursty, CPU-bound, short) | Paper-live (scheduled, short ticks, long-lived *service*) |
|---|---|---|
| Scaling | Scale-to-burst then scale-to-zero | Steady, market-hours-aware |
| Isolation | Strong per-job sandbox + egress control | Same |
| Failure recovery | Re-queue | Skip-and-alert |

- **App Platform rejected:** it's great for stateless web apps but gives us no cgroup/seccomp/network-policy control over *job* containers and no clean scale-to-zero burst model for queued CPU jobs. The sandbox requirements alone disqualify it.
- **Raw Droplets + autoscale rejected as the *primary*:** doable, but we'd hand-roll scheduling, bin-packing, health, and per-job container isolation — reinventing Kubernetes badly. We'd lose the declarative NetworkPolicy that makes egress-deny an *invariant*.
- **DOKS chosen** because it gives us, off the shelf: per-pod resource limits (cgroups), `NetworkPolicy` (the deny-all-egress-except-Data-Gateway invariant — *enforced by the cluster, not by code*), Jobs API for run-to-completion backtests, CronJobs/our scheduler for ticks, and the cluster-autoscaler for burst.

**Concrete topology:**
- **VPC** containing the cluster, Managed Postgres, and the Data Gateway. Workers have **no public egress** (NetworkPolicy default-deny; one allow rule to the Data Gateway service ClusterIP). This is the structural egress control §1 requires.
- **Node pool `backtest`** — CPU-optimized droplets, **autoscaling min 0 → max N**, cluster-autoscaler-backed. Backtests run as Kubernetes **Jobs** (one pod per job, `restartPolicy: Never`, resource `requests`/`limits` from the spec's `resources.tier`, activeDeadlineSeconds = aggregate deadline). Scale-to-zero between bursts = cost control: you pay for backtest compute only while backtests run.
- **Node pool `paper`** — small, stable general-purpose pool for the scheduler + tick jobs. Tick jobs are short Kubernetes Jobs fired by the control-plane scheduler (market-calendar-aware; we run our own scheduler rather than naive CronJobs so we respect holidays/half-days and can pause a single deployment).
- **Control plane** — runs as a regular Deployment (web API + scheduler + Data Gateway), HPA on CPU, fronted by a DO Load Balancer.
- **State:** Managed Postgres (control-plane state, books, events — with RLS), DO Spaces (artifacts, logs), optional managed Redis for the work queue.
- **Cost control:** scale-to-zero backtest pool; per-tier resource caps; aggregate deadlines bound runaway compute; backtest results cached by `(spec_hash, data_asOf_window)` so re-running an identical backtest is a cache hit, not new compute. Budget alarms on node-pool size.
- **Failure recovery:** Jobs API restarts/re-queues failed backtests once; lost paper ticks are skipped-and-alerted (never double-filled — the advisory lock + version guard prevent a re-run from corrupting the book); node failure → pods rescheduled by K8s; control-plane stateless so it restarts cleanly.

---

## 5. Brokerage-adapter seam (interface only — do NOT build)

Launch is paper-only. But the fill path is isolated behind one interface so real execution is a *plugin*, not a rewrite. The paper engine is just the first implementation.

```python
class ExecutionVenue(Protocol):
    """The only seam between the runtime and where orders go.
    Paper book = first impl. A real broker = a future impl. Nothing else changes."""

    def quote(self, symbols: list[str], as_of: str) -> dict[str, Quote]: ...

    def place_orders(self, orders: list[Order], *, idempotency_key: str) -> list[Fill]:
        """MUST be idempotent on idempotency_key (retried ticks must not double-fill)."""

    def positions(self) -> list[Position]: ...
    def cash(self) -> float: ...
    def venue_caps(self) -> VenueCaps:  # supports_short, supports_fractional, min_notional...
        ...
```

- The runtime computes target weights → `generate_orders` (already venue-agnostic in v1) → hands `Order`s to the configured `ExecutionVenue`. Today that's `PaperVenue` (wraps `paperbook`/`execution`). A future `AlpacaVenue`/`IBKRVenue` implements the same Protocol.
- **`idempotency_key`** is mandatory in the interface *now* even though the paper venue is forgiving — because real venues aren't, and our retry/re-queue model means the same logical tick can fire twice. Designing it in at launch is the cheap insurance the v1 review's "lost-update on the money path" lesson demands.
- `venue_caps()` lets the risk attestation reject specs a venue can't honor (e.g. shorting on a long-only venue) at deploy time.

We define the Protocol, the `PaperVenue` impl, and the wiring. We build no real adapter.

---

## 6. Greenfield repo / module structure + stack

**Stack:** Python 3.12, **FastAPI** (control plane + Data Gateway), **Pydantic v2** (spec schema = the security boundary), **Postgres + RLS** (SQLAlchemy core, no fallback in-memory store), **DO Spaces** (artifacts), **Kubernetes Python/Jobs API** for orchestration, **NumPy** runtime core (ported from v1), **Redis/RQ** for the backtest queue. **MCP server (primary agent interface) + thin REST/SSE** sharing the same control-plane services. Why Python end-to-end: v1's proven quant value (`engine/`, `sources/`) is numpy/Python; rewriting it in Go/Rust would re-introduce risk for no isolation benefit (isolation comes from the OS/K8s layer, not the language).

```
doomberg-deploy/
  control_plane/
    api/              # FastAPI REST/SSE — UI-facing, thin
    mcp/              # MCP server — PRIMARY agent interface (deploy/promote/observe tools)
    scheduler/        # market-calendar-aware tick scheduler + backtest enqueuer
    orchestrator/     # K8s Jobs driver: spawn/monitor/deadline/heartbeat
    repo/             # SINGLE data-access layer; firm_id mandatory; RLS-backed
    lifecycle/        # explicit state machine (classify-before-act, audited)
    spec/             # Pydantic StrategySpec schema + semantic linter + risk pre-attest
    events/           # append-only observation stream → SSE/MCP
  data_gateway/       # the ONLY data egress; asOf point-in-time enforcement; provenance; resilient breaker
    adapters/         # ported v1 sources/ (prices, edgar, news, rates, ...), all behind _resilient
  runtime_core/       # SHARED, pure, no-I/O, sandbox-safe
    registry/         # operator registry == the trust surface (ported engine/strategies + factor ops)
    graph/            # DAG evaluator
    accounting/       # paperbook + execution + TCA  (ported engine/)
    stats/            # stat block + walk-forward/overfitting diagnostics (ported engine/)
    risk/             # post-projection gross/net/name attestation (fixes v1 optimizer bug)
  runtimes/
    backtest/         # simulated-clock driver over a point-in-time window
    paper_live/       # wall-clock tick driver, fills via ExecutionVenue
  venues/
    base.py           # ExecutionVenue Protocol  (the future-broker seam)
    paper.py          # PaperVenue (launch impl)
  worker/             # the sandboxed entrypoint run inside each K8s Job pod
    sandbox/          # rlimits, stripped builtins, seccomp, deadline supervisor
  deploy/             # DOKS manifests: node pools, NetworkPolicy (deny-egress), Jobs/CronJobs, RLS migrations
  tests/              # gating CI: determinism, lookahead, tenant-isolation, risk-attestation, spec-fuzz
```

**Trust-boundary summary (one line):** the agent emits *data* (a spec) → control plane *validates* it → workers *execute reviewed operators* out-of-process, network-egress-denied, rlimited, deadline-bounded → all data flows through one point-in-time, provenance-stamped gateway → all state mutations go through one firm-scoped, row-locked repository. Every one of v1's five cross-cutting failures is closed by an *invariant enforced by infrastructure* (RLS, NetworkPolicy, FOR UPDATE, K8s deadlines, fixed operator registry), not by a guard we have to remember to call.

**Relevant source paths reviewed:** `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/engine/{backtest,paperbook,execution,strategies,stats}.py` (reusable pure core), `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/sources/{prices,_resilient}.py` (data adapters to wrap behind the Data Gateway), `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/code_guard.py` (the bypassable guard we are explicitly *not* relying on), and `/Users/joshuajerin/Desktop/jarvis/doomberg/docs/reviews/architecture-review-2026-06-16.md` (the five lessons driving the invariants above).


====================================================================================================
FILE: docs/plans/doomberg-v2/designs/repo-sequencing.md
====================================================================================================

# Design: Repo Structure, Tech Choices & Phased Sequencing

I now have a complete picture of v1: ~5000 LOC of pure numpy quant engine (15 modules), ~4000 LOC of keyless data adapters (12 sources) behind a resilience wrapper, 79 skills, a 297KB agent.py orchestrator and the RCE-laden codegen path to drop, plus an existing TS/pnpm/drizzle/zod workspace. I have the review's six cross-cutting lessons. Here is the design doc.

---

# Doomberg v2 — Repo Structure, Tech Stack & Phased Build Sequence

**Status:** Design proposal | **Date:** 2026-06-16 | **Supersedes:** v1 monolith at `artifacts/api-server/app`

Doomberg v2 is a **financial tool-platform**: the user's own agent calls Doomberg's tools (DATA LAYER), deploys accepted strategies (DEPLOY LAYER), and watches it work in a web UI that **observes** the external agent rather than running it. MCP is the primary interface; a thin REST/SSE layer feeds the UI from the same core. Paper execution only at launch, with a pluggable brokerage seam.

This doc bakes in the six cross-cutting lessons from the v1 architecture review so we do not repeat them:
1. **No static-guard-then-trust.** We drop v1's `code_guard.py`/`dynamic_skills.py`/`feature_builder.py` codegen path entirely. v2 ships *no runtime codegen*. Tools are static, typed, code-reviewed. (If user-authored strategy code ever returns, it runs out-of-process, network-denied, rlimited — never `exec_module` in an API process.)
2. **No silent swallowing.** Structured logging + typed errors from day one; no bare `except: pass`.
3. **Tenant isolation is an invariant, not per-call-site.** Enforced in one place (a tenant-scoped repository layer + Postgres RLS), not re-implemented per store.
4. **No unlocked read-modify-write on the money path.** All mutable book/strategy/run state mutates via `SELECT … FOR UPDATE` or optimistic version guards, in one txn.
5. **Aggregate deadlines, not just per-call timeouts.** Every multi-step operation (backtest, live tick cycle) carries a wall-clock budget.
6. **Tests gate from day one.** GitHub Actions `required` checks; a merge cannot land red. This is built in Phase 0, before features.

---

## 1. Monorepo vs polyrepo + top-level layout

**Decision: single monorepo, pnpm + uv workspaces.** Rationale:
- v2's value is a **shared contract** (tool schemas, panel/event schemas, run records) consumed by Python (MCP/quant/workers), TypeScript (control-plane API, web UI), and IaC. A monorepo lets one source-of-truth schema package generate Python (pydantic) and TS (zod) types, so a contract change fails CI in every consumer atomically — the opposite of v1, where panel data was `as any` and drift was invisible until render.
- v1 already uses a pnpm workspace + uv (`pnpm-workspace.yaml`, `uv.lock`) with `lib/db`, `lib/api-zod`, `lib/api-client-react`. We keep that proven shape and extend it; polyrepo would re-introduce the cross-repo version skew that made v1's contract drift undetectable.
- Atomic refactors across DATA↔DEPLOY↔UI in one PR; one CI gate covers all languages.

```
doomberg2/
├── pnpm-workspace.yaml          # TS workspaces: services/*, web, packages/*
├── pyproject.toml + uv.lock     # uv workspace: py packages below
├── turbo.json                   # task graph / caching for TS build+test+lint
├── Makefile                     # one entrypoint: make test|lint|typecheck|up
├── .github/workflows/ci.yml     # the gate (Phase 0) — see §6
│
├── packages/                    # SHARED CONTRACTS (the spine)
│   ├── contracts/               # canonical schemas, language-neutral source of truth
│   │   ├── schema/              # JSON Schema / .proto-free: authored as zod+pydantic generated from one IR
│   │   │   ├── tools/           # MCP tool input/output schemas (one file per tool family)
│   │   │   ├── events/          # agent-observation event envelope, run lifecycle events
│   │   │   ├── panels/          # UI panel data shapes (trades, news, algos, trace)
│   │   │   └── runs/            # backtest + live run records, fills, positions
│   │   ├── ts/                  # generated zod + TS types (published as @doomberg/contracts)
│   │   └── py/                  # generated pydantic models (doomberg_contracts)
│   ├── provenance/              # shared {source, asOf, freshnessSec, mode, coverage} type (review lesson)
│   └── tsconfig/ + eslint/      # shared TS config
│
├── services/
│   ├── data-mcp/                # PYTHON — DATA LAYER: MCP server (primary agent interface)
│   │   ├── doomberg_data/
│   │   │   ├── server.py        # MCP server: registers tools, SSE/stdio + streamable-http transport
│   │   │   ├── tools/           # one module per tool family; thin wrappers over engine+sources
│   │   │   │   ├── news.py  insider.py  fundamentals.py  prices.py
│   │   │   │   ├── factors.py  signals.py  backtest.py  optimize.py  risk.py
│   │   │   ├── engine/          # PORTED from v1 app/engine (crown jewel, pure numpy)
│   │   │   ├── sources/         # PORTED from v1 app/sources (keyless adapters + _resilient)
│   │   │   ├── observe.py       # emits agent-observation events to control-plane (tool call/args/result)
│   │   │   └── budget.py        # aggregate deadline helper (review lesson #5)
│   │   └── tests/
│   │
│   ├── control-plane/           # TYPESCRIPT — DEPLOY LAYER API + UI backend
│   │   ├── src/
│   │   │   ├── http/            # REST + SSE (feeds web UI from same core)
│   │   │   ├── runs/            # backtest + live "prod" run orchestration (create/start/stop)
│   │   │   ├── do/              # DigitalOcean integration (provision/scale CPU clusters, droplet/k8s API)
│   │   │   ├── observe/         # ingest agent-observation events; fan out to UI via SSE
│   │   │   ├── tenancy/         # the ONE place firm isolation is enforced (repo layer + RLS guard)
│   │   │   └── db/              # drizzle schema + migrations (extends v1 lib/db pattern)
│   │   └── tests/
│   │
│   ├── runtime/                 # PYTHON — DEPLOY LAYER worker that runs on DO CPU clusters
│   │   ├── doomberg_runtime/
│   │   │   ├── backtest_runner.py   # pulls run spec, calls engine, streams progress + result
│   │   │   ├── live_runner.py       # live market data → strategy → PAPER book (simulated fills)
│   │   │   ├── paperbook.py         # PORTED from v1 engine/paperbook.py
│   │   │   ├── brokerage/           # pluggable adapter SEAM (PaperAdapter only at launch)
│   │   │   └── checkpoint.py        # crash-safe run state (FOR UPDATE / versioned, review lesson #4)
│   │   └── tests/
│   │
│   └── scheduler/               # job queue + cron for live run ticks (could be part of control-plane)
│
├── web/                         # TYPESCRIPT/React — OBSERVABILITY UI (no chat console)
│   ├── src/
│   │   ├── panels/              # Trades, News/Ideas, Algos, AgentTrace (the showcase)
│   │   ├── dashboard/           # user-configurable tile layout
│   │   └── lib/                 # SSE client, generated @doomberg/contracts types
│   └── tests/
│
└── infra/                       # IaC for DigitalOcean
    ├── terraform/               # DO droplets/DOKS, managed Postgres, Spaces, VPC, firewall
    ├── docker/                  # service Dockerfiles + runtime image baked with engine
    └── compose/                 # local dev stack (postgres, spaces-compat minio, services)
```

---

## 2. Tech-stack decisions + rationale

| Concern | Choice | Rationale |
|---|---|---|
| **DATA LAYER / MCP server** | **Python** (`services/data-mcp`) | The crown jewels (`engine/`, `sources/`) are ~9000 LOC of proven numpy/httpx Python. The MCP server must be co-located with them to call in-process with no IPC tax. Python wins here unambiguously. |
| **MCP SDK** | **Official Python MCP SDK** (`mcp` / `modelcontextprotocol`, FastMCP-style decorators) | Anthropic's official SDK; MCP is the *primary* interface so we want first-party tool/schema support, streamable-HTTP + stdio transports, and the cleanest path for BYO agents (Claude/GPT/custom) to discover tools. v1 had no MCP — this is greenfield. (Verify exact package/version against current SDK docs before pinning; do not assume from memory.) |
| **Quant engine** | **Python + numpy** (ported as-is) | Deterministic, network-free, already unit-test-shaped. Don't rewrite proven math. |
| **Control plane / DEPLOY API** | **TypeScript (Node, Express 5 or Fastify)** | Reuses v1's working `lib/db` (drizzle), `lib/api-zod`, pino logging stack and pnpm tooling. The control plane is I/O-bound orchestration (DO API, SSE fan-out, run records) where TS's async story + shared zod contracts with the UI are a strong fit. Keeps the heavy CPU work in Python where it belongs. |
| **DEPLOY runtime / workers** | **Python** (`services/runtime`) | Runs the *same engine* the agent backtested against — using one language for backtest and live eliminates a backtest-vs-live divergence class of bug. Runs on DO CPU clusters in the engine Docker image. |
| **Web UI** | **React + Vite + TS** (extends v1's `lib/api-client-react`) | Keep the "visual terminal" feel as an observability surface. Reuse v1 panel components where the *render* logic is sound, but every panel gets a per-panel error boundary + provenance badge from the start (review lessons). Remove the chat console. |
| **Primary datastore** | **Managed Postgres (DO Managed DB)** | Tenants, strategies, run records, fills, positions, observation events. **Row-Level Security on by default** so tenant isolation is a DB invariant, not per-query (review lesson #3). |
| **Object storage** | **DO Spaces (S3-compatible)** | Backtest result artifacts, large tick captures (the v1 IEX DEEP path), agent-trace blobs. Keeps Postgres lean. |
| **Queue / scheduler** | **Postgres-backed queue (e.g. `pgmq`/`graphile-worker`) for v1 of v2; Redis only if needed** | Avoids a second stateful system early. Backtest jobs + live-run tick scheduling go through one durable queue with visibility timeouts + aggregate deadlines. A run is a row with a version column (no lost updates). |
| **Real-time to UI** | **SSE** (not WebSockets) | One-way server→browser fan-out of observation + run events; SSE is simpler, proxy-friendly, and v1 already uses it. We fix v1's gap: **heartbeats during blocking work** so idle-timeout proxies don't kill streams. |
| **IaC** | **Terraform** for DO (droplets/DOKS, Managed PG, Spaces, VPC, firewalls) + **Docker** images | Declarative, reviewable, reproducible CPU-cluster provisioning. The deploy layer is "built fresh" so it gets proper IaC, not click-ops. |
| **Observability** | structured JSON logs (pino/structlog), OpenTelemetry traces correlating agent tool-call → backtest → fill | Directly answers v1's "no logging at all" finding; the agent-trace is also a *product surface*, so we instrument it as a first-class citizen. |

---

## 3. What to PORT from v1 — concrete plan

**Crown jewels (port first, nearly verbatim):**

| v1 path | LOC | v2 destination | Notes |
|---|---|---|---|
| `app/engine/` (15 modules: backtest, signals, optimize, riskmodel, stats, attribution, execution, montecarlo, scenario, stress, strategies, portfolio, borrow, compliance, paperbook) | ~5000 | `services/data-mcp/.../engine/` + `paperbook.py`→`runtime/` | Pure numpy, network-free, already designed for isolated unit tests. Port as a package. **Fix-on-port** the review's quant bugs: optimizer gross-L1 re-check (`optimize.py:177`), Carino-link attribution (`attribution.py:357`), cross-sectional forward-window alignment (`signals.py:342`), rename `var95`→`terminalVar95` (`montecarlo.py:112`). |
| `app/sources/` (12 adapters: prices, news, edgar, fundamentals, congress, thirteenf, rates, sectors, sentiment, polymarket, iex_deep, holdings) + `_resilient.py` | ~4000 | `services/data-mcp/.../sources/` | Keyless/free adapters behind the resilience wrapper — directly become MCP data tools. **Fix-on-port**: route Treasury/FRED through `_resilient` (`rates.py:91`), add wall-clock byte-cap to IEX DEEP reconstruct (`iex_deep.py:450`), reuse one keep-alive httpx client, EDGAR overflow paging. Add a **provenance block** `{source, asOf, freshnessSec, mode, coverage}` to every adapter return. |

**Adapt / re-skin (logic sound, structure changes):**
- v1 `lib/db` (drizzle) → `services/control-plane/.../db` — reuse the drizzle migration pattern; new schema for tenants/runs/fills/observations with **RLS + version columns**.
- v1 panel React components → `web/src/panels` — port render logic for Trades/News/Algos; wrap each in an error boundary; add provenance badge.
- v1 `_resilient.py` breaker/backoff → keep as-is; it's good.

**Drop entirely (do NOT port):**
- `app/agent.py` (297KB orchestrator, 197-branch heuristic) — v2 does not run the agent loop. **Deleted.**
- `app/code_guard.py`, `app/dynamic_skills.py`, `app/feature_builder.py`, `app/skills_generated/` — the runtime-codegen RCE path. **Deleted.** No replacement at launch.
- v1 chat console / `ChatPanel.tsx` / console conversation hooks — UI is observe-only.
- v1 in-process `exec_module`/`new Function` panel eval — replaced by static typed panels.

**Port-as-tools mapping:** v1's 79 skills (`skills.py`) are not ported as the skill abstraction; instead the *underlying engine + source calls* they wrapped become a curated set of **static MCP tools** in `data-mcp/tools/` (news, prices, insider, fundamentals, factors, signals, backtest, optimize, risk). One tool family per file, each with a contract schema in `packages/contracts/tools/`.

**Porting sequence:** (1) `engine/stats`+`backtest`+`strategies`+`signals` (smallest closure that runs a backtest) → (2) `sources/prices` (feeds backtest) → (3) wrap both as 2-3 MCP tools → (4) remaining sources → (5) optimize/risk/attribution.

---

## 4. Phased roadmap (exit criteria + demo)

**Phase 0 — Skeleton + the gate (the thinnest *infrastructure* slice).**
Monorepo scaffold, `packages/contracts` with one round-trip schema generating both pydantic + zod, empty service stubs, Docker compose local stack, and **CI that gates** (lint + typecheck + tests as required checks; a red PR cannot merge).
*Exit:* a trivial contract change that breaks a TS consumer turns CI red and blocks merge. *Demo:* "the gate works" — push a breaking change, watch the merge button lock.

**Phase 1 — DATA LAYER walking skeleton: one tool, one agent call.**
Port `engine/stats+backtest+strategies+signals` + `sources/prices`. Stand up the Python MCP server exposing **two tools**: `get_price_history` and `run_backtest` (in-process, synchronous, on the agent's machine — no DO yet). Wire a BYO agent (Claude) to the MCP server.
*Exit:* an external agent discovers the tools, calls `get_price_history` then `run_backtest`, and gets a real numpy backtest result with a provenance block. *Demo:* **the core vision in miniature** — your own agent reaches a decision about a stock using Doomberg tools.

**Phase 2 — OBSERVABILITY: render the agent's work.**
Control-plane SSE + `observe/` ingest; `data-mcp/observe.py` emits tool-call/args/result/timing events. Web UI panels: AgentTrace (live tool calls), and a results panel for the backtest. No DO yet.
*Exit:* agent makes calls in Phase 1; UI renders the live trace + backtest equity curve in real time, with heartbeats keeping the SSE stream alive through blocking work. *Demo:* **watch your agent think and produce an algo** in the terminal UI.

**Phase 3 — DEPLOY LAYER: one backtest run on DigitalOcean.**
Terraform up Managed PG + Spaces + a DO CPU worker; `services/runtime/backtest_runner.py` in the engine Docker image; control-plane `runs/` creates a run row (versioned), enqueues it, worker pulls it, runs the engine **with an aggregate deadline**, streams progress, writes the artifact to Spaces. Tenancy enforced via RLS from this point.
*Exit:* agent's accepted plan → "Deploy backtest" → run executes on a DO worker → result + artifact rendered in UI, scoped to the firm. *Demo:* **the full vision end-to-end** — MCP tool → agent call → backtest on DO → rendered in UI.

**Phase 4 — LIVE paper deployment.**
`runtime/live_runner.py` + scheduler tick: a deployed strategy runs on **live market data** filling against the simulated `paperbook` via `PaperAdapter` (the pluggable seam). Positions/fills persisted with FOR UPDATE. Trades + Algos panels go live.
*Exit:* deploy a strategy "to prod"; it ticks on real intraday data, books paper fills, and the Trades panel updates live. *Demo:* **a strategy running live, paper-trading, observable in real time.**

**Phase 5 — Capability breadth + hardening.**
Port remaining sources (news, edgar/insider, fundamentals, rates, 13F, polymarket, IEX DEEP) and engine modules (optimize, risk, attribution, stress) as additional MCP tools; News/Ideas panel; multi-tenant admin; canary + load gates in CI; DO cluster autoscaling.
*Exit:* full tool catalog discoverable; News/Ideas + factor/risk tools in use; load + canary gates green. *Demo:* the **full tool-platform** — an agent doing multi-source research → factor model → optimized strategy → live paper deploy.

*Critical-path spine:* Phase 0 → 1 → 2 → 3 → 4. Phase 5 is breadth layered on a proven spine.

---

## 5. Parallelization + critical-path dependencies

**Hard dependency (the spine, must be sequential):** `contracts` (P0) → MCP tools (P1) → observation events (P2) → run orchestration on DO (P3) → live runner (P4). Each depends on the prior's schema being frozen.

**The unlock:** `packages/contracts` is the critical enabler. Land schemas for tools/events/runs/panels **first** (P0). Once frozen, every workstream codes against generated types in parallel and integrates without surprises.

**Parallel workstreams after P0 contracts land:**
- **WS-A Quant/Data (Python):** port engine + sources, build MCP tools. *Owns the spine through P1; can keep porting modules ahead of need.*
- **WS-B Control-plane (TS):** DB schema + RLS, runs API, SSE, observe ingest, DO integration. *Can build the runs API + SSE skeleton against contract types before WS-A's tools exist (mock tool events).*
- **WS-C Runtime (Python):** backtest_runner, live_runner, paperbook, brokerage seam. *Shares the engine package with WS-A; can develop the runner harness against a stub engine, swap in the real one when WS-A ports it.*
- **WS-D Web UI (TS):** panels + dashboard + SSE client. *Builds entirely against contract panel/event types + recorded fixture event streams — fully parallel, no live backend needed until P2 integration.*
- **WS-E Infra (Terraform/Docker):** DO provisioning, images, compose. *Independent; only gates P3. Start immediately so DO is ready when the runner is.*

**Sync points:** P1 (WS-A tools real → WS-D swaps fixtures for live), P3 (WS-B + WS-C + WS-E converge for first DO run). Mock/fixture-against-contract is what keeps WS-B/D/E from blocking on WS-A.

---

## 6. Testing/CI that ACTUALLY gates (from day zero)

v1's failure was concrete: only 3 of 33 suites carried `isValidation`, there were no `.github/workflows`, perf gate defaulted off, and the tested paths weren't the shipped paths (orchestrate tests forced `ai_available=False`). v2 fixes the *mechanism*, in Phase 0, before features.

- **`.github/workflows/ci.yml` as the single required gate**, branch-protection enforced: a PR cannot merge while red. This exists before the first feature lands.
- **All suites run, every PR.** Turbo (TS) + uv/pytest (Python) run the *entire* test graph. There is no per-suite opt-in flag; "exists but doesn't run" is structurally impossible.
- **Test the path that ships.** Contract tests assert pydantic⇄zod round-trip on every schema (no `as any`). MCP tools are tested through the real server interface, not internal stubs. The backtest is tested against a golden fixture series with a numerically pinned result. Tenancy: an RLS test that *attempts* cross-firm access and asserts it's denied — isolation is a tested invariant, not a hope.
- **Determinism in the gate.** Engine/quant tests are pure and seeded (no network, no live yfinance) — the opposite of v1's `panel-runtime-test` that coupled build + live server + LLM + live yfinance into one flaky gate. Live-source adapters are tested against recorded fixtures; a separate *non-gating* nightly job hits real upstreams.
- **Money-path concurrency tests.** Explicit tests that concurrent run/book mutations don't lose updates (asserts FOR UPDATE/version-guard behavior).
- **Budget tests.** Assert aggregate-deadline helpers abort chained operations before the proxy ceiling.
- **Load + canary gates default ON** (fix `LOAD_GATE_LATENCY=0`): per-endpoint latency budgets in CI from the start; post-deploy `/canary` monitoring in the deploy workflow.
- **Pre-merge `/review`, post-merge `/document-release`** per the repo's gstack workflow; CI is the hard gate, review is the soft gate.

**Key files to inspect when implementing:** v1 crown jewels to port at `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/engine/` and `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/sources/` (with `_resilient.py`); the code to DROP at `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/{agent.py,code_guard.py,dynamic_skills.py,feature_builder.py}` and `app/skills_generated/`; the existing reusable TS workspace libs at `/Users/joshuajerin/Desktop/jarvis/doomberg/lib/{db,api-zod,api-client-react}`; and the review whose lessons gate this design at `/Users/joshuajerin/Desktop/jarvis/doomberg/docs/reviews/architecture-review-2026-06-16.md`.


====================================================================================================
FILE: docs/plans/doomberg-v2/designs/security.md
====================================================================================================

# Design: Security, Multi-tenancy, Compliance & Sandboxing

I now have enough grounding in v1's actual mechanisms (contextvar tenant scoping that was applied per-store rather than as an invariant, the FOR UPDATE pattern in state.py, the cookie/PBKDF2 auth, the role matrix, the in-process exec RCE). I have everything I need to write the v2 design doc. The task explicitly says to return findings as the final message, not write a file.

Let me produce the design doc as my final output.

---

# Doomberg v2 — Security, Multi-Tenancy & Safe-Execution Design

**Scope:** the cross-cutting trust layer for the v2 tool-platform. Designed explicitly *away* from the five systemic failure modes verified in the v1 review (`/Users/joshuajerin/Desktop/jarvis/doomberg/docs/reviews/architecture-review-2026-06-16.md`): static-guard-then-trust, per-call-site tenancy, unlocked read-modify-write, per-call-but-no-aggregate timeouts, and tests-that-don't-gate.

**Threat model (who we defend against):**
- T1 — A malicious or compromised **BYO agent** (it authenticates legitimately, then tries to read another tenant's data, exfiltrate secrets, or escape the strategy sandbox).
- T2 — A **malicious strategy/algorithm author** (the strategy code itself is the attacker — RCE, network egress, resource exhaustion, lateral movement to the control plane). This is the v1 RCE class, now first-class.
- T3 — A **confused-deputy** in our own code (an unscoped query, a forgotten tenant filter — v1's #1 systemic flaw).
- T4 — **External abuse / DoS** on the public MCP surface (credential stuffing, request floods, slow-loris, expensive-tool amplification).
- T5 — **Accidental real-money execution** ("paper" silently reaching a real broker).

---

## 1. Identity & Auth

### 1.1 The account model (three distinct objects, never conflated)

```
Tenant (org/firm)                 ← the isolation boundary. Owns everything.
  ├── User (human)                ← logs into the web UI. Has a role.
  ├── Agent (logical principal)   ← a registered BYO agent ("my Claude trader")
  │     └── Credential (secret)   ← an API key OR OAuth client; scoped; revocable
  └── all data rows / deploy jobs / artifacts  ← carry tenant_id (see §2)
```

Key rule: **a Credential is never the principal — the Agent is.** A credential is a rotatable secret *belonging to* an agent. Revoking/rotating a credential never changes the agent's identity, its deployed strategies, or its audit history. This is what makes key rotation safe and lets us attribute every action to a stable principal.

### 1.2 How the BYO agent authenticates to the MCP server

Two supported flows, both resolving to the same `AgentPrincipal`:

1. **API keys (primary, the 80% path).** Format: `dmbg_<env>_<keyid>_<secret>` (e.g. `dmbg_live_k7f3_…`). We store only `sha256(secret)` plus a non-secret `keyid` lookup column — mirroring v1's session-token discipline (`auth.py` stores only `hash_token`). Constant-time compare. The visible prefix lets us scan-and-revoke leaked keys and lets the user identify a key in the UI without exposing it. Keys are shown **once** at creation.
   - **Why primary:** agents run headless; the device-code dance is friction for a long-lived daemon.
2. **OAuth 2.1 client-credentials (for org/programmatic issuance) + device-code (for interactive first-link).** A user "links an agent" in the UI via device-code (agent prints a code, user approves in the web UI under their authenticated session). This binds the agent to the tenant *with the user's explicit consent and role*, then issues a client-credentials pair the agent uses thereafter. This is the clean path for "connect my Claude/GPT/custom agent."

Both flows yield short-lived **bearer access tokens** (15 min) for the MCP session; the long-lived secret (API key / client secret) is only used to mint them. This bounds the blast radius of a leaked in-flight token.

> v1 lesson applied: v1 had no machine-principal model at all (only human cookies, `auth.py`). v2 makes the agent a first-class, separately-credentialed principal so we can scope and rate-limit it independently of any human.

### 1.3 How the web UI user authenticates

Keep v1's proven mechanism, hardened: httpOnly, `Secure`, `SameSite=Lax` session cookie; opaque random token, only `sha256` stored (`auth.py:hash_token`); PBKDF2-HMAC-SHA256 at ≥200k iterations for passwords. **Add:** server-side session records with absolute + idle expiry, explicit logout-all, and a `csrf` double-submit token for state-changing cookie-authed endpoints (v1's CSP was strict but it had no CSRF token; `security.py`). MFA (TOTP) for `admin` role.

### 1.4 Scopes & permissions per credential

Authorization is **role (human) ∩ scope (credential) ∩ tenant**. Both ceilings apply; the effective permission is the intersection.

- **Human role** — keep v1's ranked matrix (`permissions.py`: `read-only < analyst < trader < admin`, fail-closed on unknown action). It still governs UI users.
- **Agent credential scopes** — a separate, finer, *capability* axis stamped on each credential. An agent credential can never exceed the role of the user who linked it, and is *further* narrowed by its scopes:

| Scope | Grants |
|---|---|
| `data:read` | call DATA-LAYER tools (news, ticks, fundamentals, factor models, backtest primitives) |
| `strategy:author` | create/update strategy definitions (not deploy) |
| `deploy:backtest` | submit backtest jobs |
| `deploy:paper` | deploy to the live paper runtime |
| `deploy:live` | **reserved, not issuable at launch** (paper-only, §4.3) |
| `account:read` | read own tenant's positions/trades/audit |

A read-only data agent gets `data:read` only — even if linked by an admin. **Deny-by-default, fail-closed** (v1 `permissions.can()` already does this; we keep that exact discipline and extend it to scopes). Scope checks live in the single auth gate, not at call sites (§2).

---

## 2. Multi-tenancy as a HARD INVARIANT

This is v1's #1 systemic flaw (review §3.3: "isolation is per-store, not an invariant" — correct in `strategy_store`/`dashboard_store`, *missing* in `template_store`, in-memory `get_dashboard`, and the generated-skill registry). v1's `tenant.py` contextvar was the right idea but it was **advisory**: each store had to *remember* to call `tenant.current_firm_id()` and filter, and the ones that forgot leaked. We make forgetting structurally impossible.

### 2.1 Defense layer A — Postgres Row-Level Security (the backstop that cannot be forgotten)

Every tenant-owned table gets a non-null `tenant_id` and an RLS policy. The application connects as a **non-superuser role that has RLS forced** and sets `SET LOCAL app.tenant_id = $1` at the start of every transaction from the resolved principal.

```sql
ALTER TABLE strategies ENABLE ROW LEVEL SECURITY;
ALTER TABLE strategies FORCE ROW LEVEL SECURITY;   -- applies even to table owner
CREATE POLICY tenant_isolation ON strategies
  USING      (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

The critical property: **a query that forgets its tenant filter returns zero rows, not another tenant's rows.** A forgotten filter on a write fails the `WITH CHECK`. This is the structural fix for the v1 IDOR class (`get_dashboard`, `template_store`) — the database enforces it even when the application code is wrong. `current_setting('app.tenant_id')` with no value set → error → fail closed. This is the single most important change from v1: *isolation moves below the application code, where it cannot be omitted per-call-site.*

### 2.2 Defense layer B — a scoped data-access layer that makes unscoped queries un-writable

RLS is the backstop; we *also* remove the footgun at the application layer so unscoped queries are not merely caught but un-expressible:

- There is **no** raw `db.execute(sql)` available to feature/store code. The DB module exposes only a `TenantSession` obtained from the request/job context: `session = ctx.db()`. `TenantSession` opens the transaction, runs `SET LOCAL app.tenant_id`, and is the *only* way to get a cursor.
- Every ORM model for a tenant table inherits from `TenantScoped`, which carries `tenant_id` and whose default manager is bound to the session's tenant. There is no "unscoped" manager exported.
- A unit/CI test (gated — see §5.4 and the v1 "tests don't gate" lesson) enumerates every table; any tenant-eligible table **without** an RLS policy and a `tenant_id` NOT NULL column **fails the build**. New tables are isolated by default or they don't merge. This converts "remember to scope" into "the schema is wrong and CI is red."

### 2.3 Tenant resolution = the auth gate, set once, never threaded

Keep v1's contextvar ergonomics (`tenant.py` — clean, avoids threading `firm_id` through deep call sites) but bind it to the verified principal in a single middleware/dependency, and make every downstream `TenantSession`/job read it. The background worker and deploy runtime enter `firm_context()` per item exactly as v1's worker did — but now if they forget, RLS denies them rather than leaking. The contextvar becomes a *convenience*; RLS is the *guarantee*.

### 2.4 Non-DB artifacts carry the tenant key too

Deploy jobs, backtest result blobs, log streams, and strategy artifacts are **object-store paths prefixed `tenant/<tenant_id>/…`** with bucket IAM policies scoped per prefix, and a `tenant_id` column on the job row (RLS-protected). The runtime sandbox (§3) is handed *only* its own tenant's scoped, short-lived credentials — it physically cannot address another tenant's prefix. v1's in-memory `_mem` dicts that bypassed firm scoping (`dashboard_store`, generated-skill `SKILLS[pt]`) are eliminated: there is no process-global, un-keyed store anywhere in v2.

---

## 3. Safe Strategy Execution (the highest-risk surface)

This is the v1 two-critical-RCE class, made first-class. **Non-negotiable architectural rule: no in-process `eval`/`exec`/`exec_module`/import of agent- or user-authored code, ever, anywhere.** v1's both criticals came from running generated code in the API process behind a static AST guard (`code_guard.py`, `dynamic_skills.py`); v1's *own* review concluded "stop treating the static guard as a security boundary." We adopt that as law: **static analysis is lint, not a boundary.** We also DROP v1's runtime AI-codegen path entirely (per the locked product decision) and replace it with the model below.

### 3.1 What "a strategy" is allowed to be

To shrink the attack surface before sandboxing it, strategies are authored against a **constrained, declarative-first strategy SDK**, not arbitrary Python. The agent assembles strategies from allowlisted DATA-LAYER tool calls + a small set of vetted quant primitives (the proven numpy logic ported from v1 `app/engine/` — signals, optimizer, attribution, risk model). Two execution modes:

1. **Declarative (preferred):** the strategy is a validated JSON/DSL graph of `{signal → construction → constraints → schedule}`. We execute it with *our* trusted interpreter. No user code runs at all. This is the safest and covers most strategies.
2. **Scripted (escape hatch):** if the agent needs custom logic, it submits Python that runs **only** inside the sandbox below, against a capability-restricted SDK surface — never with ambient `__builtins__`, network, or filesystem.

### 3.2 The sandbox (process + container + network + resource)

Every backtest and every live-paper strategy step runs in an **isolated, single-use worker** — *never* the control-plane/API process. Layers, outermost first:

1. **Separate host/pool.** Untrusted execution runs on a dedicated DigitalOcean worker pool, network-isolated from the control plane and the primary database. The control plane is never reachable from a strategy container.
2. **Per-job container** (gVisor/Kata or microVM — a syscall-filtering runtime, not bare Docker), one strategy job per container, destroyed after the job. No shared state between tenants or jobs.
3. **Network: deny-all egress by default.** No DNS, no outbound sockets. The strategy *cannot* call out. Market data and tool results are **pushed in** via a single authenticated stdin/IPC channel from a trusted broker process; results come back over the same channel as validated JSON only (this is exactly v1's review remedy: "marshal only validated JSON back"). If a future strategy needs a feed, it's an allowlisted, brokered, per-tenant-scoped capability — never raw network.
4. **Filesystem:** read-only root, a tmpfs scratch with a hard size cap, no host mounts, no secrets on disk.
5. **Resource limits (the v1 "unbounded IEX stream" / no-aggregate-deadline lesson):** cgroup CPU/memory/PID caps, plus **two clocks** — a per-tool-call timeout *and* an absolute wall-clock job deadline (e.g. backtest ≤ N min, each live step ≤ K s). When the aggregate budget is spent the job is killed and marked `deadline_exceeded`, never left to run past the ceiling. (v1 had per-call timeouts but no wall-clock budget — review §3.5.)
6. **Restricted interpreter:** stripped `__builtins__`, no `import` of anything outside the vetted SDK allowlist, seccomp profile denying `socket`/`ptrace`/`exec` family. Because egress is already denied at the network layer, an interpreter escape still hits a wall — **defense in depth, not a single guard** (the explicit anti-pattern from v1).
7. **No dynamic web/panel execution in the browser realm.** The web UI is observability-only (locked decision: chat console removed). It renders the agent's traces and results as **data**, never `new Function`/`eval` of model output. This deletes the v1 client-side `_TSX_BANNED`/`new Function` RCE (review §2 High) by construction.

### 3.3 Capability allowlisting

The sandbox SDK exposes a fixed, audited set of capabilities: `get_prices`, `get_fundamentals`, `compute_signal`, `optimize(weights, constraints)`, `place_paper_order`, `log`. Each is brokered by the trusted parent process, tenant-scoped, rate-limited, and audited. There is no `os`, no `subprocess`, no `open`, no `requests`. The strategy can only do what the platform offers — capabilities are *granted*, not *removed-from-a-denylist*.

---

## 4. Secrets, Audit Logging & Paper-Trading Guardrails

### 4.1 Secrets management

- **No secret in env vars committed/logged, no secret on a strategy container's disk.** Platform secrets (DO API token, model keys, future broker keys) live in a dedicated secrets manager (DO/Vault/cloud KMS-backed), fetched at runtime by the control plane only.
- **The control plane holds infra secrets; the runtime never sees them.** A strategy container is handed only short-lived, narrowly-scoped, per-job tokens (e.g. an object-store token scoped to `tenant/<id>/jobs/<jobid>/`), minted per job, expiring with the job.
- **Future broker keys (the seam, not built):** stored per-tenant, encrypted at rest with envelope encryption, decryptable only inside the brokerage-adapter process — *never* inside a strategy sandbox. The adapter is a separate, trusted, audited service behind the paper/live gate (§4.3).
- **Rotation:** all credentials (agent keys, infra tokens) rotatable without downtime; key revocation is immediate (the `keyid` lookup row is flipped, in-flight 15-min tokens are the max exposure).

### 4.2 Audit logging (append-only, tenant-attributed, retained)

v1 had an append-only audit table but the review flagged it grew unbounded and that "never-crash" swallowing erased trails (§3.2). v2:

- **Every** security-relevant event is logged: auth (key mint/use/revoke, login, device-link), every agent tool call (tool, args-digest, tenant, agent principal, result status, latency), every deploy job lifecycle, every paper order, every permission denial, every tenant-isolation violation caught by RLS.
- **Append-only by construction:** write-only table (no UPDATE/DELETE grant for the app role) or an external append-only sink (e.g. object-store WORM). Each record carries `tenant_id` (RLS-scoped reads) + the stable `agent_id`/`user_id` principal — attribution survives credential rotation (§1.1).
- **Tamper-evidence:** hash-chain each tenant's audit stream (`record.hash = sha256(prev_hash || payload)`) so deletion/reordering is detectable.
- **Retention:** explicit policy (e.g. 1y hot, then cold WORM), enforced by a scheduled job — *not* v1's lazy unbounded growth. Retention is configurable per-tenant for compliance.
- **No silent swallow:** the v1 "`except Exception: pass`" pattern that erased trails is banned on every audited path; failures to audit fail the operation (audit is on the critical path for money-touching actions).

### 4.3 Paper-trading guardrails — "paper can never accidentally touch real money"

Make it *structurally* impossible, not policy-impossible:

1. **`deploy:live` scope is not issuable at launch.** The code path to mint it is feature-flagged off. There is no credential in the system that can request live execution.
2. **Distinct, separately-deployed execution services.** Order routing goes through an `ExecutionAdapter` interface. The **only** implementation wired at launch is `PaperBook` (simulated fills against live market data). The `BrokerageAdapter` (real) is an interface/seam — *not implemented, not deployed, not in the dependency graph.* There is no binary path from a strategy to a real broker because the code isn't there.
3. **Explicit environment assertion.** Every order carries `mode: "paper"`. The paper book asserts `mode == "paper"` and the system carries a global `EXECUTION_MODE=paper` invariant checked at process start; any order lacking `paper` is rejected and audited as a critical anomaly.
4. **Visual + data labeling everywhere** (carrying forward the review's "data lineage / provenance badge" recommendation): every trade, position, and P&L in the UI and API is tagged `paper`. No path renders a paper fill as anything else.
5. **When live is eventually added:** it will require a separate, audited, MFA-gated, per-tenant opt-in, real broker key in the isolated adapter, and a distinct `deploy:live` scope — gated behind the same intersection model (§1.4). The seam is clean; the gate is closed.

---

## 5. Rate Limiting, Abuse/DoS & Aggregate Deadlines

### 5.1 Rate limiting on the public MCP surface

v1's limiter (`security.py`) was in-process per-IP — fine for a single node, but the review noted it's "not a substitute for an edge WAF." v2:

- **Edge WAF + L7 limiter** in front of the MCP/REST/SSE surface (IP and ASN reputation, slow-loris protection, body-size cap — keep v1's `BodySizeLimitMiddleware`).
- **Distributed, principal-scoped quotas** (Redis token-bucket, shared across nodes — not v1's per-process dict). Limits are keyed by **`tenant_id` + `agent_id`**, not just IP, since agents come from arbitrary IPs. Tiered:
  - per-credential request rate,
  - per-tenant aggregate rate,
  - **per-tool cost budgets** — expensive DATA-LAYER tools (backtests, factor models, large tick pulls) carry a higher "cost" and draw down a per-tenant compute budget, so one agent can't amplify cheap-looking calls into a resource DoS.
- **Concurrent-job caps per tenant** on the deploy layer (bounded backtests/live strategies) so a tenant can't exhaust the worker pool.
- Limits **fail closed and return `429` with `Retry-After`** (v1 pattern, kept). Never disabled in production (v1 disabled under pytest via env — fine for tests, but the prod path must always be on).

### 5.2 Aggregate request deadlines (direct v1 fix)

v1's #5 systemic flaw: "per-call timeouts exist but aggregate budgets don't" (orchestrator 90s past a 60s proxy ceiling, unbounded IEX stream). v2 makes **wall-clock budgets first-class**:

- Every MCP request and every deploy job opens with an **absolute deadline** set at entry. Each downstream call (tool, DB, sandbox step) gets a **shrinking** per-call timeout = `min(call_default, remaining_budget)`. When the budget is exhausted, the request returns a structured `deadline_exceeded` immediately rather than chaining past the ceiling.
- Long jobs (backtests) run **async** with a job handle + SSE/poll status (with heartbeats — v1's review flagged blocking SSE with no keepalive), not a single blocking request, so they're never bounded by the HTTP proxy ceiling at all.

### 5.3 Abuse/DoS specifics

- Auth endpoints: strict per-IP + per-account limits, exponential backoff, lockout + alert on credential-stuffing patterns. Constant-time key compare (no timing oracle on `keyid`→hash lookup).
- Leaked-key scanning (the `dmbg_live_` prefix is grep-able) + auto-revoke on detection.
- Anomaly detection on the audit stream (sudden cross-tool fan-out, deadline-exceeded clusters, RLS-denial spikes → throttle + alert).

### 5.4 Tests that actually gate (cross-cutting, v1 lesson #6)

Security is only real if it's enforced in CI. v1 ran 3 of 33 suites and the paths that shipped weren't tested. v2 **gates merge** on: RLS-coverage test (§2.2, every tenant table has a policy + NOT NULL `tenant_id`); a cross-tenant access test that *asserts* tenant B cannot read/write tenant A's rows, jobs, or artifacts; a sandbox-escape test battery (no network egress, no fs write, no banned import, deadline kills a runaway job); a "no real-broker in the dependency graph" assertion (§4.3); and an auth/scope-intersection matrix test. **No green, no merge.** These tests run the *production* code paths (not stubbed-out SQL or AI-disabled paths — the v1 anti-pattern).

---

## Summary: each v1 systemic flaw → v2 structural fix

| v1 systemic flaw (review §3) | v2 structural answer |
|---|---|
| Static-guard-then-trust → 2 RCEs | No in-process eval of untrusted code; out-of-process, network-denied, rlimited sandbox; declarative-first SDK; capabilities granted not denylisted (§3) |
| Tenancy per-call-site, not invariant | Postgres RLS as the un-forgettable backstop + scoped data layer with no raw query + CI fails on any unscoped table (§2) |
| Unlocked read-modify-write on money path | All mutations through `SELECT … FOR UPDATE` / optimistic-version transactions via the single `TenantSession`; carried over from v1's correct `state.py` pattern (§2.2) |
| Per-call timeouts, no aggregate deadline | Absolute wall-clock budget per request/job; shrinking per-call timeouts; async long jobs with heartbeats (§5.2) |
| Tests exist but don't gate | RLS-coverage, cross-tenant, sandbox-escape, paper-only, and scope-matrix tests gate merge against production paths (§5.4) |
| (new) BYO machine principal | Agent is a first-class, separately-credentialed, scope-limited principal distinct from the human; effective perm = role ∩ scope ∩ tenant (§1) |
| (new) accidental real money | Paper-only by construction: `deploy:live` unissuable, real adapter not in the dependency graph, `mode:"paper"` invariant asserted, everything labeled (§4.3) |

**Highest-risk surface remains strategy execution (§3)** — treat the sandbox as the load-bearing control: assume the interpreter restriction *will* be bypassed and ensure that even then the attacker is in a network-denied, secret-free, per-job, destroyed-after-use microVM that cannot address the control plane, the primary DB, or another tenant's prefix.

Relevant v1 files that inform (and whose patterns are kept or replaced) the design:
- `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/tenant.py` (contextvar scoping — kept as convenience, RLS added as guarantee)
- `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/auth.py` and `permissions.py` (token/role discipline — kept and extended with agent scopes)
- `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/security.py` (rate-limit/headers — replaced with distributed principal-scoped limits + edge WAF)
- `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/state.py` (correct `FOR UPDATE` pattern — generalized into the scoped data layer)
- `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/api-server/app/dynamic_skills.py` and `code_guard.py` (the v1 RCE path — dropped entirely, replaced by §3)


====================================================================================================
FILE: docs/plans/doomberg-v2/designs/topology.md
====================================================================================================

# Design: System Architecture & Topology

I've written the design doc to `/Users/joshuajerin/Desktop/jarvis/doomberg/docs/design/v2-system-architecture.md`. Here it is in full (it is the spine the other v2 designs hang off):

# Doomberg v2 — System Architecture & Topology

Grounded in v1 code at `artifacts/api-server/app/` (engine, sources, strategy lifecycle, tenant context, worker, SSE) and `docs/reviews/architecture-review-2026-06-16.md`.

## 0. North star & the v1 lessons that shape this

Doomberg v2 is a financial **tool-platform** that someone else's agent plugs into. Two consequences drive every decision: (1) the agent is external and untrusted-as-a-client — Doomberg never runs the agent loop and never executes agent-authored code in-process (v1's two critical RCEs came from running LLM-authored code behind a static guard; v2 deletes that path); (2) we must reconstruct a thought process we don't own — we can only see what crosses the MCP wire.

Six v1 failure themes map to six non-negotiable v2 invariants:

| v1 failure theme | v2 invariant |
|---|---|
| Static-guard-then-trust → RCE | No agent/LLM code ever executes in a privileged process. Strategies are declarative specs, not code. |
| "Never crash" swallowing erases audit | Every tool call, transition, and money-path mutation is an append-only event; no silent `except: pass`. |
| Tenant isolation per-store, not invariant | `tenant_id` resolved at the auth boundary, enforced once at the data-access seam. |
| Unlocked read-modify-write on money path | All book/run mutations go through the control plane in serialized transactions. |
| Per-call timeouts but no aggregate budget | Every run and tool call has a wall-clock deadline, enforced at gateway and runtime. |
| Tested path ≠ shipped path | CI gates the MCP tool contract and the deploy state machine — the surfaces everything depends on. |

## 1. Component map

- **(A) MCP server** — the PRIMARY product surface. Speaks MCP; advertises Data + Deploy tools; authenticates agent token → `tenant_id`+`session_id`; per-call deadlines; emits a trace event per call. Thin adapter over the shared core.
- **(B) REST/SSE gateway** — feeds the web UI from the SAME core. Browser auth/sessions, REST reads, SSE fan-out (trace + telemetry), human control actions (accept/promote/pause). Never a second source of truth.
- **(C) Data Layer core (Python)** — ports v1 `app/engine/` (backtest, signals, portfolio, riskmodel, optimize, execution, paperbook, stats, attribution, montecarlo, stress) + `app/sources/` (prices, news, edgar, congress, thirteenf, fundamentals, rates, sentiment, iex_deep, holdings, polymarket). Pure quant; no agent code; no I/O in engine.
- **(D) Deploy Layer control plane** — owns versioned/immutable strategy specs, the run state machine (draft→backtest→paper→retired), scheduling onto DO, the pre-trade compliance gate (`engine/compliance`). Single writer of the money path.
- **(E) Event bus / trace spine** — append-only `(run_id, seq, event)`. Postgres LISTEN/NOTIFY at launch (transactional with the write); Redis Streams at scale.
- **(F) Datastores** — Postgres (system of record: tenants, specs, runs, books, `trace_event`, audit); object store (S3/Spaces for backtest artifacts, IEX captures, reports); TimescaleDB optional for heavy tick/quote/curve series.
- **(G) DO CPU clusters** — stateless workers that EXECUTE backtests and the paper-live loop against a spec using the SAME trusted engine image; never run agent code; emit telemetry to the bus; propose book deltas (never write the book).
- **(H) Web UI (React)** — observability surface, NO chat console. Tabs: Trace, Trades, News/Ideas, Algos, Books. Pure SSE+REST projection.

(A) and (B) are two thin front doors over one shared Python core; both publish to the same event bus.

## 2. End-to-end flows

**(a) Research a stock:** agent opens MCP to (A) with a token → resolves `tenant_id`+`session_id`; `tools.list` returns the Data Layer catalog; `tools.call("get_news",{...})` opens a trace span on (E), sets a per-call deadline, routes through (C)'s resilience wrapper, attaches a **mandatory provenance block** (`{source, asOf, freshnessSec, mode: live|stale|mock, coverage}`), closes the span. UI renders spans live.

**(b) Propose a strategy:** agent calls `propose_strategy({spec})` — a DECLARATIVE document `{universe, signal_id+params, construction_scheme, rebalance, sizing, risk_limits, costs}`, never code, every field mapping to an existing engine primitive. (D) validates against the engine's closed allow-list, assigns `strategy_id`+immutable `version`, persists `draft`. Nothing deploys until a human accepts.

**(c) Accept → backtest:** human action through (B); (D) creates a guarded `run`, enqueues a job; a DO worker (G) runs trusted `engine/backtest` over point-in-time history, streams progress telemetry, writes artifact to object store + summary to Postgres; UI animates the equity curve with the integrity/provenance badge.

**(d) Promote → paper-live:** human action; (D) runs the pre-trade compliance gate (gross/net/per-name caps, restricted lists; re-checks `sum|w|` vs gross AFTER projection — closes v1 optimizer bug). On pass, opens a paper book (`engine/execution.generate_orders` + `engine/paperbook`), schedules a long-lived paper-live job. Worker re-evaluates the signal on REAL market data, routes orders through the **brokerage-adapter seam — paper/sim adapter only at launch** (no real brokerage/money). All book mutations applied ONLY by (D) in serialized transactions (`FOR UPDATE`/optimistic version) — worker proposes deltas, (D) applies atomically.

**(e) UI renders:** (H) authenticates to (B), opens SSE per view, replays from `last_seq` then tails live. Tabs are pure event projections; top-level + per-panel error boundaries.

## 3. THE HARD PROBLEM — capturing a thought process we don't own

Principle: **make the MCP wire itself the trace**, plus one optional channel for volunteered reasoning.

**3.1 MCP session correlation (backbone, always available):** every connection's token → `(tenant_id, agent_id)`; (A) assigns `session_id` (or honors an `X-Doomberg-Run` header). Every `tools.call` is automatically a trace event because we own the server side — `tool_call` + `tool_result` events with args, result summary, provenance, latency. This reconstructs WHAT the agent did and in what order with zero agent cooperation.

**3.2 Optional `emit_reasoning` tool (the WHY, volunteered, never trusted):** a first-class side-effect-free MCP tool `emit_reasoning({kind, text, refs?, confidence?})`. Well-behaved agents narrate between steps; it emits a `reasoning` event ordered into the same `seq` stream so it interleaves with tool calls. It is display+audit ONLY — reasoning text never influences control-plane decisions, so a lying/absent agent degrades trace richness but never money-path behavior. (The inverse of v1's mistake: v1 trusted LLM output enough to execute it; here agent text is purely observed.)

**3.3 Inferred fallback (best-effort, labeled):** if no reasoning is emitted, (A) synthesizes DETERMINISTIC, non-LLM templated annotations from the call pattern, tagged `derived:true`. No hidden LLM fabricates reasoning.

**3.4 Trace data model:** `trace_event(run_id, seq /*gap-free monotonic*/, type /*tool_call|tool_result|reasoning|run_state|run_progress|fill|mark|proposal|compliance|error*/, span_id, parent_span, payload jsonb, provenance jsonb, tenant_id, ts)`, PK `(run_id, seq)`.
- **Association:** research runs under a `session_id`; `propose_strategy` records `origin_session_id`; backtest/promote create new `run_id`s that link back via `parent_span`/`origin_session_id` — one unbroken chain research→proposal→backtest→paper.
- **SSE replay:** `GET /streams/{run_id}?from_seq=N` replays `>N` from Postgres then tails via LISTEN/NOTIFY; client tracks `last_seq` and reconnects with it; gap-free `seq` lets the UI detect gaps and re-fetch deterministically (fixes v1's superseded-stream clobber).
- **Heartbeat:** `: keepalive` + `run_progress` events during long work (fixes v1's missing-heartbeat kill).

## 4. Boundaries & contracts

- **4.1 Agent ↔ Doomberg (MCP contract, THE product API):** every tool has JSON-Schema input, typed output with mandatory provenance, declared deadline, stable name+version. The agent can read and PROPOSE only; `propose_strategy` is the only Deploy tool it can call. **It cannot promote to paper or move money** — those require a human action through (B).
- **4.2 Gateway ↔ Core (in-process):** (A) and (B) both call one shared `core.run_tool(name,args,ctx)` / `core.read(view,ctx)`; the MCP path and UI path can never diverge. `ctx` carries `tenant_id, session_id, actor, deadline`.
- **4.3 Core ↔ Deploy (internal):** (D) owns specs/runs/books/state-machine/gate; surface `create_run, transition_run, apply_book_delta, evaluate_gate`. Spec is a closed declarative schema validated against the engine allow-list — no free-form code field exists.
- **4.4 Control plane ↔ DO runtime (job contract):** workers PULL jobs, STREAM telemetry, PROPOSE deltas; never write the book. Money path: (D) is single writer under serialized txn; jobs idempotent on `(run_id, seq)`. Deadline checked inside worker loops (fixes v1's unbounded 13GB IEX reconstruct).
- **4.5 Tenancy (cross-cutting, enforced once):** `tenant_id` resolved at the two front doors only, bound into `ctx`; the data-access layer in (F) is the single enforcement point — stores never accept an unscoped read (fixes v1 template-store/in-memory-dashboard/global-skill leaks).

## 5. Stack recommendation per component

- **(C) Data Layer core:** Python 3.12 + numpy; PORT v1 `engine/`+`sources/` as-is — proven, pure, deterministic, already unit-testable; rewriting numpy quant elsewhere is pure downside risk.
- **(A) MCP server:** Python, official MCP SDK, `streamable-http` (hosted) + `stdio` (local), co-located with the core so tool calls are in-process, not a network hop.
- **(B) REST/SSE gateway:** Python + FastAPI (Starlette StreamingResponse for SSE) — reuse v1's proven SSE + tenant contextvar, minus chat/orchestrator.
- **(D) Deploy control plane:** Python + FastAPI as a SEPARATE deployable service (money-path single-writer, small blast radius, scales independently). Go is the fallback if we later want compile-time state-machine guarantees, but launch in Python to avoid a polyglot tax.
- **(G) DO workers:** Python, SAME engine image as the core (guarantees backtest≡paper math), containerized on DO CPU clusters, stateless + pull-based.
- **(E) bus/trace:** launch Postgres LISTEN/NOTIFY (transactional, gap-free ordering, one fewer moving part); scale to Redis Streams; `(run_id, seq)` model is bus-agnostic.
- **(F) datastores:** Postgres 16 (row-locks for the money path), DO Spaces/S3 (blobs), TimescaleDB only if tick volume justifies it.
- **(H) Web UI:** React + TypeScript + Vite, `EventSource` SSE, types generated from the OpenAPI spec via the repo's existing `lib/api-zod` + `lib/api-client-react` + Orval; keep the terminal look, drop chat, add error boundaries.
- **Cross-cutting resilience:** port `sources/_resilient.py` (retry/backoff/jitter + per-source breaker) + add stale-while-revalidate so tools return `mode:"stale"` with a real `asOf` instead of fabricating mock — makes provenance truthful by construction.
- **Cross-cutting CI:** pytest gating the MCP tool contract (golden schemas + provenance present), the deploy state machine (illegal transitions rejected), and money-path serialization (concurrent-delta test); real `.github/workflows`.

## 6. Explicitly DROPPED from v1
Runtime AI codegen / self-building skills (`dynamic_skills.py`, `feature_builder.py`, `code_guard.py`, `skills_generated/`, client `new Function` eval) — the source of both critical RCEs; v2 has no privileged path executing generated code. The orchestrator / 197-branch intent heuristic (`agent.py`) — the external agent decides now. The chat console.

## 7. Open questions deferred to downstream designs
Exact MCP tool catalog & schemas (Data Layer design); full declarative spec schema (Deploy Layer design); paper-live loop cadence + market-data plumbing + brokerage-adapter seam interface (runtime design); UI information architecture (design track); authN/Z model and human roles (security track).

Full doc on disk: `/Users/joshuajerin/Desktop/jarvis/doomberg/docs/design/v2-system-architecture.md`


====================================================================================================
FILE: docs/plans/doomberg-v2/designs/webui.md
====================================================================================================

# Design: Web UI / Observability Surface

Stack confirmed: React + Vite + Tailwind + framer-motion + recharts, monorepo with `@workspace/api-client-react`. I have all I need to write the design doc. Returning it now as my final output.

---

# Doomberg v2 Web UI — Observability Surface Design

## 0. Framing: what changed and what the UI is now

v1's UI was the *front-end of an agent that lived inside Doomberg*. The user typed into a chat console (`ChatPanel`), Doomberg's own orchestrator picked skills, generated a `DashboardSpec`, and the UI rendered panels — sometimes by **compiling AI-authored TSX in the browser** (`registry.ts` → `sucrase` → `new Function`, the RCE the architecture review flagged).

v2 inverts this. **Doomberg does not run the agent.** The user's own agent (Claude/GPT/custom) connects over MCP, discovers tools, calls them, and reasons. Doomberg's job is to **observe that external activity and render it** — the agent's thought process, each tool call and its result, the algos/strategies it proposes, what gets deployed, and the live P&L. The UI is a **read-mostly observability + control surface**, fed by a thin REST/SSE layer over the same core the MCP server uses. The chat box is gone; the "conversation" is now the **agent trace**.

The single most reusable asset from v1 is the **~79 panel components** (`artifacts/terminal/src/components/terminal/panels/`). They are pure `({ data }) => JSX` Recharts/typography renderers (verified: `BacktestPanel`, `TradeFlowPanel`, `PerformancePnlPanel` take a `data` prop and draw — no orchestration coupling). In v2 they stop being "what the AI laid out on a grid" and become **result-renderers for tool outputs**: tool `backtest.run` returns data → render `BacktestPanel`. That mapping is the backbone of the whole design.

---

## 1. Information Architecture

A persistent left rail switches between six top-level views. A global header carries: connected-agent status (the MCP session indicator), the active **Run** selector, and environment (paper/live) badge. No chat console anywhere.

```
┌── Doomberg v2 ───────────────────────────────────────────────┐
│ [agent: Claude ● connected]   Run: research-NVDA-0617 ▾   PAPER │
├──────────┬───────────────────────────────────────────────────┤
│ ▸ Runs    │                                                    │
│ ▸ Algos   │             ACTIVE VIEW                            │
│ ▸ Deploys │                                                    │
│ ▸ Trades  │                                                    │
│ ▸ Ideas   │                                                    │
│ ▸ Boards  │                                                    │
└──────────┴───────────────────────────────────────────────────┘
```

**1.1 Agent-Run Observability view (`/runs/:runId`) — the centerpiece.** A live (and replayable) timeline of one agent run: its reasoning stream on the left, a tool-call timeline in the middle, and the **panel(s)** each tool call produces on the right. This is where the user *watches their agent think and work*. Detailed in §2.

**1.2 Algos / Strategies view (`/algos`).** A library of strategy definitions the agent has authored or the user has saved. Each algo is a **declarative spec** (not generated code — see security note): entry/exit rules, parameters, universe, factor weights. Card grid → detail view embedding v1's `BacktestPanel`, `WalkForwardPanel`, `MonteCarloPanel`, `TearSheetPanel`, `FactorAttributionPanel` as result renderers. Actions: *Backtest*, *Deploy (paper)*, *Fork*, *Diff versions*.

**1.3 Deployments view (`/deploys`).** Two tabs over the **fresh-built control plane** (DigitalOcean runtime):
- **Backtests** — historical runs, queued/running/done, each opening a tear-sheet (`TearSheetPanel`, `PerformancePnlPanel`, `WalkForwardComparePanel`).
- **Paper-Live** — strategies running live on real market data, filling against the simulated book. Per-deployment: status (provisioning/running/halted), live equity curve (`PerformancePnlPanel`), open risk (`RiskMonitorPanel`, `PortfolioRiskPanel`), DO node health, kill switch. P&L streams in over SSE.

**1.4 Trades / Positions view (`/trades`).** The simulated book: open positions, fills, exposure. Renderers: `PerformancePnlPanel`, `PortfolioRiskPanel`, `TradeFlowPanel`, `OrderBookPanel`, `RebalancePlanPanel`. Every trade row links back to *the run + the tool call + the algo* that produced it — full provenance.

**1.5 News / Ideas feed (`/ideas`).** A streaming feed of candidate ideas the agent surfaced (news hits, insider clusters, screen results it flagged as interesting) but hasn't acted on. Renderers: `NewsPanel`, `SentimentPanel`, `InsiderActivityPanel`, `CongressTradesPanel`, `ScreenerPanel`, `EarningsCalendarPanel`. Each idea card → "Open in run" to see the reasoning, or "Hand to agent" (writes a note the agent can pick up via a tool).

**1.6 Boards (`/boards`).** User-configured dashboards (§4.2). Repurposes v1's `SavedDashboardsModal` + layout engine, but boards now subscribe to **live data streams / deployment metrics**, not one-shot agent output.

---

## 2. THE CENTERPIECE — visualizing an external agent's reasoning + tool calls

### 2.1 The data we observe

Because Doomberg is the MCP server the agent calls, **every tool call is an observation point** with no extra agent cooperation required. For each call we capture an envelope:

```ts
interface TraceEvent {
  runId: string;
  seq: number;                 // monotonic ordering within a run
  ts: string;
  kind: "thought" | "tool_call" | "tool_result" | "decision" | "error" | "status";
  // tool_call
  tool?: string;               // e.g. "fundamentals.get", "backtest.run"
  args?: Record<string, unknown>;
  callId?: string;             // correlates call ⇄ result
  // tool_result
  status?: "ok" | "error" | "partial";
  panelType?: string;          // which v1 renderer draws this result
  data?: unknown;              // the renderable payload (same shape v1 panels eat)
  durationMs?: number;
  // thought / decision — only present if the agent volunteers reasoning
  text?: string;
  citesCallIds?: string[];     // which tool calls this reasoning leaned on
}
```

`thought`/`decision` events are **best-effort**: a BYO agent may or may not stream its reasoning. The UI must be *legible with tool calls alone* and *richer when reasoning is present* — never assume reasoning exists. (Where the agent supports it, MCP `notifications` / a `reasoning` tool the agent opts into feeds these; otherwise the timeline is purely the observable tool-call sequence.)

### 2.2 The three-column trace UI

```
┌ REASONING ─────────┬ TIMELINE ──────────────┬ EVIDENCE (panels) ──────┐
│ "I want to know if │ ● fundamentals.get     │ ┌─ FundamentalsPanel ──┐ │
│  NVDA's margins     │ │  NVDA            120ms│ │  rev +22% · GM 73%   │ │
│  justify the multi- │ ●─news.search          │ └──────────────────────┘ │
│  ple, so I'll pull  │ │  "NVDA datacenter"    │   ↑ pinned by reasoning  │
│  fundamentals and   │ ●─insider.activity     │                          │
│  recent news…"      │ │  NVDA          ⚠ slow │ ┌─ NewsPanel ──────────┐ │
│                     │ ●─backtest.run         │ │  8 headlines…        │ │
│ ▸ "Momentum looks   │ │  momentum/NVDA  2.3s  │ └──────────────────────┘ │
│   strong → backtest"│ ◐ running…             │                          │
└─────────────────────┴────────────────────────┴──────────────────────────┘
        ◀── replay scrubber ───────●───────────────── 00:42 / LIVE ──▶
```

**Left — Reasoning rail.** The agent's narrated thought process as a vertically scrolling stream of `thought`/`decision` cards, word-by-word as deltas arrive (reuse v1's SSE delta-accumulation loop from `Terminal.tsx` `streamCommand` — the `data:`-line parser is directly portable). Each card can cite the tool calls it depends on; hovering highlights those rows in the timeline (the inverse of v1's navigator highlight, repurposed). If the agent emits no reasoning, this rail collapses and the timeline widens.

**Middle — Tool-call timeline.** The spine. One row per `tool_call`, in `seq` order, each showing tool name, key args, a live status dot (queued ◌ / running ◐ / ok ● / error ⊗ / slow ⚠), and duration. This is where the **deadline/timeout lessons** from the architecture review surface visually: a call exceeding its per-call budget shows ⚠, and the run header shows an **aggregate run deadline** bar (the review called out "per-call timeouts but no aggregate deadline" — make the aggregate first-class in the UI so a runaway run is obvious). Clicking a row scrolls Evidence to that call's panel.

**Right — Evidence column = the tool-call→panel mechanic.** This is the load-bearing reuse of v1. When a `tool_result` arrives:

```
tool_result.panelType ──lookup──▶ PANEL_REGISTRY[panelType] ──render──▶ <BacktestPanel data={result.data}/>
```

The mapping is exactly v1's `PanelContainer` switch (lines 309–404), **lifted out into a static `Map<panelType, Component>`** and reused verbatim. The agent's tool defines a `panelType` + a `data` shape that matches the renderer's existing contract. A panel **pops into the Evidence column the instant its result lands**, with an entrance animation (reuse `PANEL_MOTION` from `Dashboard.tsx`), and a connector line/anchor back to its timeline row. Panels the reasoning explicitly cites get "pinned" to the top; others stack chronologically. This makes the abstraction concrete: *a tool call is a question, the panel is the answer, the reasoning is why it was asked.*

### 2.3 Live vs. replay — one component, two clocks

The trace is **event-sourced** (`TraceEvent[]` keyed by `seq`). That gives replay for free:
- **Live**: subscribe to `GET /api/runs/:id/events` (SSE); append events; auto-scroll all three columns; status dots animate.
- **Replay**: load the full event log via REST; a **scrubber** at the bottom drives a "playhead" `seq`. The same render path filters to `event.seq <= playhead`, so reasoning, timeline, and panels all rewind/fast-forward together. Play/pause/step. Because rendering is a pure function of `(events, playhead)`, live is just "playhead pinned to the latest seq."

A small **run minimap** (sparkline of tool-call density + error markers over time, reuse v1's `Sparkline`) sits above the scrubber for jumping to interesting moments (errors, the decision point, the deploy).

### 2.4 How it reads to a human

The story a watcher should be able to read top-to-bottom: *"My agent wanted X → it called these 4 tools → here's what each returned → it concluded Y → it proposed/deployed this algo."* The reasoning rail gives the *why*, the timeline gives the *what/when/how-long*, the evidence column gives the *result*, and a terminal `decision` event links straight into the Algos or Deployments view (e.g. "Agent deployed `momentum-NVDA` to paper → open deployment").

---

## 3. v1 components: KEEP / REPURPOSE / DROP

### KEEP & REPURPOSE as tool-output renderers (high value)
All ~79 quant/data panels — they are clean `({data}) => JSX`:
- **Charts/quant**: `PriceChartPanel`, `IntradayChartPanel`, `BacktestPanel`, `WalkForwardPanel`, `WalkForwardComparePanel`, `MonteCarloPanel`, `TearSheetPanel`, `PerformancePnlPanel`, `FactorAnalysisPanel`/`FactorAttributionPanel`/`FactorExposurePanel`/`FactorPerformancePanel`, `CorrelationMatrixPanel`, `PortfolioOptimizerPanel`, `RiskModelPanel`/`RiskMonitorPanel`/`PortfolioRiskPanel`, `StressTestPanel`, `ScenarioPanel`, `BrinsonPanel`, `IVSurfacePanel`/`VolTermStructurePanel`/`OptionsChainPanel`/`OptionsStrategyPanel`, `DCFPanel`, `StructuredProductPanel`, `CDSPricerPanel`, `YieldCurvePanel`, `BondRVPanel`.
- **Data/feed**: `NewsPanel`, `SentimentPanel`, `FundamentalsPanel`, `ScreenerPanel`, `HeatmapPanel`, `InsiderActivityPanel`, `CongressTradesPanel`, `InstitutionalHoldersPanel`/`InstitutionalFlowsPanel`, `EarningsCalendarPanel`, `TranscriptPanel`, `AnalystRatingsPanel`/`AnalystReportPanel`/`AnalystComparePanel`, `FilingsBrowserPanel`, `ETFHoldingsPanel`/`ETFExposurePanel`, `EconomicReleasesPanel`, `MacroDashboardPanel`, `TradeFlowPanel`, `OrderBookPanel`.
- **Strategy/exec**: `StrategyDeskPanel`, `MultiStrategyPanel`, `RebalancePlanPanel`, `CombinedAlphaPanel`, `SignalScorecardPanel`/`SignalResearchPanel`/`SignalPortfolioPanel`, `TCAPanelReport`, `CompliancePanel`.

**Repurpose change to make:** strip the per-panel **`Refine`/`Settings2` input and the `onRefine`/`useRefinePanel` round-trips** from `PanelContainer`. Refinement was the user nudging Doomberg's own agent — that's gone. Panels become **display-only** (with read-only controls like chart-range tabs kept, but they re-query the REST layer, not "ask the AImore"). Lift the `panel.type` switch into a static registry `Map`.

**Reuse the layout/board infra:** `lib/layout.ts` (`resolvePanelLayouts`, the reserve-then-reflow grid), `Dashboard.tsx` grid + resize, `SavedDashboardsModal`, `Sparkline`, `CoverageBadge`, `panelExport.ts` (CSV/PDF), the SSE delta-parser in `Terminal.tsx`, `AlertsNotifications`. The responsive 12/6/1-column logic is solid — keep it for Boards.

### DROP
- **Chat console** — `ChatPanel.tsx`, `useConsoleConversation.ts`, the whole `handleCommand`/`streamCommand`/`orchestrate` command path in `Terminal.tsx`. No chat in v2.
- **Voice mode** — `VoicePanel.tsx`, `VoiceOrb.tsx`, `useVoiceConductor.ts`, `useSpeechRecognition.ts`, `voiceSettings.ts`, `/speak` + `/transcribe` clients. Out of scope for an observability surface.
- **Navigator/tour** — `NavigatorCursor.tsx`, `useNavigator.ts`, `/navigate`, the `NAV_INTENT`/`tourSubject` machinery. The "auto-cursor walkthrough" was a demo gimmick for the monolithic agent. **Salvage only the highlight mechanic** (`onHighlight`/`highlightedPanelId`) — repurpose it so hovering a reasoning card or timeline row highlights the linked panel.
- **🔴 SECURITY HOLE — DROP ENTIRELY: `panels/generated/` (`registry.ts`, `DynamicPanel.tsx`, `GeneratedPanel.tsx`) and the `sucrase` dependency.** `registry.ts` fetches arbitrary TSX from `GET /api/generated-panels`, transpiles it, and runs it via `new Function(...)` in the user's browser — a remote code execution path (matches the "runtime AI codegen path (it had critical RCEs)" the brief and review call out). v2 must have **no client-side codegen/eval**. Tool outputs map to a **fixed, vendored registry of renderers** only. If a tool returns a `panelType` with no registered renderer, fall back to a **safe, static JSON/table viewer** (a sanitized rewrite of `GeneratedPanel`'s generic renderer — pure data display, zero eval). Adding a new renderer is a code change that ships through review, never a runtime fetch.
- **`FeatureRequestModal` / `AdminConsoleModal` / `AuditLogModal`** as-is — these belong to v1's "build a feature" codegen flow and its multi-tenant admin. v2 keeps an **audit log view** (it's even more important now — see §4.3) but rebuilt against the v2 control plane, not ported.

---

## 4. Consuming the thin REST/SSE layer (NOT MCP directly)

### 4.1 Why and how
The browser **never speaks MCP**. MCP is the agent's interface. The web UI reads from a thin REST/SSE facade over the *same core* that backs the MCP tools — so the UI and the agent see a consistent world, but the UI gets a stable, queryable, **tenant-scoped** HTTP surface.

```
External Agent ──MCP(tools)──▶ ┌─────────────┐ ──persists──▶ event store / book / deploy state
                               │ Doomberg    │
Web UI ──REST(read)+SSE(live)──▶│  CORE       │
                               └─────────────┘
```

Endpoint sketch (all tenant-scoped by an auth-derived `firmId`, never a client-supplied one — see §4.3):
- `GET /api/runs`, `GET /api/runs/:id` — run metadata + event log (for replay).
- `GET /api/runs/:id/events` *(SSE)* — live `TraceEvent` stream.
- `GET /api/algos`, `GET /api/algos/:id` — strategy specs + version history.
- `GET /api/deploys`, `GET /api/deploys/:id`, `GET /api/deploys/:id/metrics` *(SSE)* — live P&L/risk/node health.
- `POST /api/deploys/:id/halt` — kill switch (one of the few **writes**; everything else is read).
- `GET /api/positions`, `GET /api/trades`, `GET /api/trades/stream` *(SSE)*.
- `GET /api/ideas`, `GET /api/ideas/stream` *(SSE)*.
- `GET /api/boards`, `PUT /api/boards/:id`, `GET /api/series/:key` *(+ SSE)* for board widgets.

Keep v1's pattern: a generated **`@workspace/api-client-react`** package with typed hooks (`useRuns`, `useDeploy`, `useAlgo`) wrapping TanStack Query for REST, plus thin SSE subscription hooks. Reuse v1's robust SSE parser (the `data:`-chunk reader in `Terminal.tsx`) as the shared transport for *all* live streams (`useEventStream<T>(url)`).

### 4.2 Dashboard configurability
Boards (§1.6) let the user assemble a watch-surface: pick which renderers to pin (a deployment's equity curve, the ideas feed, a specific run's evidence column, a positions table), arrange them on the reused 12-col grid, and persist via `PUT /api/boards/:id` (extends `SavedDashboardsModal`). Each widget declares a data source `{ kind, params }` resolved to a REST query + optional SSE subscription, so a board is **live** — it isn't a frozen snapshot of agent output like v1. A user can set a default board (e.g. "my paper deployments + P&L + open positions") that loads on launch, cached like v1's heavy default dashboard.

### 4.3 Carrying the architecture-review lessons into the UI/API seam
- **Tenant isolation as an invariant, not per-call-site.** `firmId` is derived once from the session at the API boundary and applied as a mandatory filter in the data layer — the UI cannot pass it, cannot widen it. Every endpoint above is implicitly `WHERE firm_id = session.firmId`.
- **Aggregate deadlines are visible.** The run header shows the aggregate run-deadline budget, not just per-tool spinners — directly answering the review's "per-call timeouts but no aggregate deadline."
- **No static-guard-then-trust.** The dropped codegen path was exactly that pattern (guard the `require` shim, then trust the eval). v2's renderer registry is a closed set; there is nothing to "guard then trust."
- **Audit view rebuilt.** Because the agent is external and untrusted, the run event log *is* the audit trail. The audit view (replacing v1's `AuditLogModal`) reads `TraceEvent`s and the immutable deploy/halt actions — every tool call, arg, and state change is attributable.

---

## 5. Tech stack, state model, live updates

**Stack — keep v1's, minus the hole.** React + Vite + TypeScript + Tailwind + framer-motion + Recharts, in the existing pnpm workspace with `@workspace/api-client-react`. **Remove `sucrase`** (and `html2canvas-pro`/`jspdf` stay only if export is retained). Add `react-router` for the six top-level views (v1 was effectively single-screen). Keep the editorial black/serif terminal aesthetic — it suits an observability surface.

**State model — three tiers:**
1. **Server cache (TanStack Query)** for all REST reads: runs, algos, deploys, positions, boards. Source of truth lives server-side; the client caches and invalidates.
2. **Event-sourced run state (local reducer):** a run is `TraceEvent[]` + a `playhead`. Render = pure `select(events, playhead)`. Live appends events and pins `playhead`; replay moves it. One reducer powers both modes — this is the key architectural simplification over v1's tangle of refs in `Terminal.tsx`.
3. **Ephemeral UI state (local `useState`/lightweight store):** which view, selected run, pinned panels, board edit mode, highlight target. A small Zustand store is warranted for cross-view selection (active run/deploy) since router + many panels read it; avoid v1's proliferation of `useRef`-mirrored state.

**Live updates — SSE everywhere, one hook.** A single `useEventStream<T>(url, onEvent)` built on v1's proven `data:`-chunk reader handles run traces, deploy metrics, trade fills, and idea feeds uniformly. SSE (not WebSockets) because the data is server→client, append-only, and reconnect/replay is trivial with `Last-Event-ID` (the `seq`). On reconnect, the client resumes from its last `seq`, and because rendering is `select(events, playhead)`, a gap-then-backfill is seamless. Deploy P&L and positions update the same way; the kill switch and board saves are the only client→server writes, done as plain REST mutations with optimistic UI + invalidation.

**Net effect:** the user opens Doomberg, sees their connected agent in the header, watches a run unfold across the three-column trace (reasoning → tool timeline → evidence panels reusing v1's quant renderers), follows a decision into Algos, deploys to paper, and watches live P&L stream into the Deployments and Trades views — all over a tenant-scoped REST/SSE layer, with zero chat, zero client-side codegen, and the agent's entire reasoning recorded as a replayable, auditable event log.

---

**Relevant files inspected (all absolute):**
- `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/terminal/src/pages/Terminal.tsx` (command/voice/nav orchestration — mostly DROP; SSE parser KEEP)
- `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/terminal/src/components/terminal/Dashboard.tsx` (grid + `PANEL_MOTION` — KEEP for Boards/Evidence)
- `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/terminal/src/components/terminal/PanelContainer.tsx` (the `panel.type`→component switch, lines 309–404 — lift into static renderer registry; strip refine)
- `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/terminal/src/components/terminal/panels/` (~79 renderers — KEEP)
- `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/terminal/src/components/terminal/panels/generated/registry.ts` + `DynamicPanel.tsx` + `GeneratedPanel.tsx` (**RCE — DROP entirely; remove `sucrase`**)
- `/Users/joshuajerin/Desktop/jarvis/doomberg/artifacts/terminal/src/lib/layout.ts` (reserve-then-reflow grid — KEEP)
- `/Users/joshuajerin/Desktop/jarvis/doomberg/docs/reviews/architecture-review-2026-06-16.md` (lessons carried into §4.3)


====================================================================================================
FILE: docs/reviews/architecture-review-2026-06-16.md
====================================================================================================

# Doomberg Architecture Review — 2026-06-16

> Multi-agent flaw-finding + feature review. 78 agents, 8 dimensions, **59 verified findings**
> (each adversarially verified against the real code before inclusion). Dimensions: orchestrator,
> security/tenancy, data sources, quant engine, state/scalability, frontend, testing/CI, self-building codegen.

## 1. Executive summary

Doomberg's architecture is functionally rich but carries a small number of severe, exploitable defects
concentrated in its most novel surface — runtime AI code generation. Two **critical** in-process RCE paths
exist: the static AST guard for generated Python is trivially bypassed via string-hidden dunder walks, and
the validation sandbox does not cover the in-process `exec_module`/`build()` that actually runs generated
code. Beyond codegen, the platform has real multi-tenant isolation gaps (template store and in-memory
dashboards leak across firms), money-path concurrency bugs (unlocked read-modify-write on strategy books, an
optimizer that violates hard gross-exposure limits), and effectively no CI gate (3 of 33 test suites run, and
the core LLM→panel path is untested). Biggest risks in order: contain generated-code execution, close
cross-tenant data access, then harden the orchestrator's deadline/heartbeat behavior and the money-path
concurrency. Most findings are well-isolated and fixable without architectural rewrites; the codegen
sandboxing is the one item requiring a structural change (out-of-process execution).

## 2. Top risks ranked

### Critical

- **AST guard bypassable → in-process RCE.** code_guard auditor only inspects dunders as AST nodes;
  string-literal attribute paths (`string.Formatter().get_field("0.__globals__[__builtins__][__import__]", ...)`)
  reach a live `__import__` and `os.popen`. `code_guard.py:117-129`. **Fix:** stop treating the static guard as
  a security boundary; execute all generated code out-of-process (stripped `__builtins__`, network-denied,
  rlimited), drop `string` from the import allowlist, scan string literals for dunder/reflection tokens.

- **Validation sandbox doesn't cover execution.** `_validate_python` runs candidates in an isolated subprocess,
  but `stream_feature_request` then `exec_module`s the file in the main server process and invokes `build()`
  in-process per request. `feature_builder.py:283-322` / `dynamic_skills.py:63` / `harness.py:81`. **Fix:** make
  the subprocess the *execution* environment for the builder's whole lifetime; marshal only validated JSON back.
  Never `exec_module` generated code in the API process.

### High

- **Client-side panel guard is a substring denylist, then `new Function`-eval'd in every browser.**
  `globalThis["fe"+"tch"]` / `["local"+"Storage"]` evade `_TSX_BANNED`; the TSX runs in the page's main realm
  with full access to cookies/fetch/storage. `feature_builder.py:327-351` (+ `registry.ts:83-84`). **Fix:**
  sandboxed cross-origin iframe (no `allow-same-origin`) via postMessage, or a declarative non-executable schema.
- **Generated skills are global across tenants; kill-switch doesn't isolate or unload.** `register_module`
  writes process-global `SKILLS[pt]` with no firm key; dispatch/startup unscoped; `require_codegen_enabled` only
  gates the build endpoint. `dynamic_skills.py:96-97`. **Fix:** key generated skills by firm_id at registration
  and dispatch, filter `get_definitions()`/`run_skill` by caller, unregister on disable.
- **Cross-firm IDOR: in-memory `get_dashboard` ignores firm scoping.** Raw `_mem.get(id)` lets any firm restore
  another's dashboard by guessing a 12-hex id (reachable whenever `DATABASE_URL` is unset).
  `dashboard_store.py:138-140`. **Fix:** add the `(rec.firmId or DEFAULT_FIRM_ID) == fid` guard.
- **Strategy templates have no tenant scoping.** `template_store` omits `firm_id`, never imports `tenant`;
  `delete_template` only checks `id.startswith('user-')` — cross-firm read, clone, destructive delete.
  `template_store.py:25-30`. **Fix:** add `firm_id` column+index, stamp from `tenant.resolve_firm()`, filter all.
- **Strategy book updates are unlocked read-modify-write (lost-update on the money path).** `strategy_store.upsert`
  does `INSERT ... ON CONFLICT DO UPDATE` over a full prior read with no row lock; worker advisory lock guards
  worker-vs-worker but not worker-vs-API / API-vs-API. `strategy_store.py:184-211`, `strategy.py:253-273`.
  **Fix:** `SELECT ... FOR UPDATE` in one txn (mirror `state.py:_mutate`) or optimistic version guard.
- **Optimizer violates the gross (L1) exposure limit on the final projection.** `_project_feasible` ends with
  `_project_box_sum` (net + box, NOT gross L1), so a "gross 200%" book returns as `optimal` at ~311% gross
  (reproduced numerically). `optimize.py:177-188`. **Fix:** re-check `sum|w|` vs gross after final budget step;
  iterate Dykstra to tolerance or return `infeasible-relaxed`.
- **No aggregate deadline across chained LLM calls.** Voice build runs 3 serial `ai.chat` calls (relevance →
  orchestrate → narration), each 30s `max_retries=0`, ~90s worst case — past the ~60s proxy ceiling.
  `agent.py:1738-1790`. **Fix:** wall-clock deadline at start of `_orchestrate_build`, shrinking per-call timeouts,
  fall back to heuristics when budget spent.
- **Streaming build emits no SSE heartbeat during blocking LLM work.** Build branch is a single `yield {done}` —
  all chained calls run before the first byte; idle-timeout proxies kill it. `agent.py:1853-1854`. **Fix:** mirror
  the feature-builder pattern (worker thread + `: keepalive`).
- **Lifecycle keyword routing runs before intent classification.** `_handle_lifecycle` (regex) runs before
  `_classify_intent`, so "how do I retire a strategy?" matches `\bretire\b` and mutates persisted state.
  `agent.py:1801-1813`. **Fix:** classify first, or gate lifecycle on `intent != 'question'`.
- **Treasury and credit-spread fetches bypass the resilience wrapper.** `_fetch_treasury_year`,
  `_fetch_fred_latest`, `_fetch_fred_series` use raw `httpx.Client` — no retry/backoff/breaker; a transient
  503/429 nulls the whole curve. `sources/rates.py:91`. **Fix:** route through `_resilient.request` (mechanical).
- **IEX DEEP reconstruct has no wall-clock timeout on a ~13 GB stream.** Only per-read timeouts; a
  truncated/malformed capture drains the entire tail and ties up a worker thread. `sources/iex_deep.py:450`.
  **Fix:** deadline/byte-cap check inside the message loop.
- **No top-level React error boundary.** Only `PanelErrorBoundary` (generated panels). A render throw in
  `Terminal.tsx`/`Dashboard.tsx`/typed panels blanks the whole app. `App.tsx:43-56`. **Fix:** wrap `AuthGate`.
- **Typed panels render `panel.data as any` with no boundary.** `renderContent()` passes unvalidated data into
  panels calling e.g. `row.price.toFixed(2)`; one bad field throws during render. `PanelContainer.tsx:309-403`.
  **Fix:** per-panel boundary → existing "Data Acquisition Failed" fallback.
- **Only 3 of 33 test suites gate merges.** Just `smoke`, `panel-runtime-test`, `voice-backend` carry
  `isValidation`; auth/security/permissions/strategy/engine/rebalance/compliance/audit run nowhere. No
  `.github/workflows`, no `pytest.ini`. `.replit:31-62`. **Fix:** `isValidation` workflow running `pytest`.
- **Intent routing is a 1300-line, 197-branch keyword cascade where ordering is the spec.**
  `_orchestrate_heuristic` has 82 `return panels` exits; misplaced branch silently mis-routes.
  `agent.py:3383-4700`. **Fix:** registry of `(matcher, builder, priority)` + per-intent query tests; split file.

### Medium

- Lifecycle handler swallows real errors → generic build (`except Exception: return None`, no log). `agent.py:1641-1642`.
- No retry/backoff for transient LLM failures (`max_retries=0` + `except: pass`). `ai.py:53-60`.
- `compliance_store._mutate` unlocked read-modify-write on global config row. `compliance_store.py:211-264`.
- `session_state` first concurrent insert not serialized (`FOR UPDATE` locks nothing when no row). `state.py:140-186`.
- Session ownership recorded but never enforced (within-firm IDOR; `get_session_owner` unused). `state.py:219-238`.
- Registration/invite TOCTOU race + orphan firm; UNIQUE violation → 500 not 409. `main.py:260-273`, `auth_store.py:237-271`.
- DB pool starvation → silent in-memory divergence (PoolTimeout → `_mem` fallback). `db.py` / `state.py`.
- Append-only audit + `session_state` grow unbounded; expired `auth_sessions` cleaned lazily. `compliance_store.py:281-354`, `state.py:65-92`.
- Worker rebalance/snapshot: full-table load + N+1 `get_config` across all firms. `strategy_store.py:134-149`, `strategy.py:682-702`.
- `new Function` eval of AI panel source (bypassable blacklist, unsandboxed). `registry.ts:66-91`.
- Factor attribution mixes arithmetic factor returns w/ geometric realized return → mislabeled idiosyncratic. `engine/attribution.py:357-361`.
- Cross-sectional signal: union-calendar rebalance, forward returns in own bar index → misaligned windows. `engine/signals.py:342-387`.
- Streaming reader has no AbortController; superseded stream clobbers newer answer. `Terminal.tsx:265-330`.
- `_is_dunder`/auditor blind to f-strings + string-literal reflection tokens. `code_guard.py:82-83,117-120`.
- Large tables render every row, no virtualization, inside `layout` AnimatePresence → thrash. `ScreenerPanel.tsx:36-64`.
- No staleness floor / last-known-good when upstream down (flips to mock/empty). `cache.py:44`.
- EDGAR submissions parsing: positional flatten, only `filings.recent`, drops overflow + older Form 4/5. `sources/edgar.py:146`.
- Per-attempt/per-call `httpx.Client` construction defeats keep-alive. `sources/_resilient.py:185`.
- Core LLM tool-call→panel path untested (every test forces `ai_available=False`). `agent.py:1752-1763`.
- `panel-runtime-test` couples build + live server + LLM retries + live yfinance into one slow nondeterministic gate. `IntradayChartPanel.integration.test.tsx`.
- Load/perf regression gate defaults OFF (`LOAD_GATE_LATENCY=0`) and runs in no workflow. `scripts/loadtest_api.py:72-74`.

### Low (noted)

Question-path double LLM call no shared timeout (`agent.py:1809-1811`); internal exception text leaked in SSE/502
(`main.py:557-558`); CORS allow-list silently empty when Replit env unset (`security.py:48-64`); EDGAR global
spacing lock sleeps under the lock (`edgar.py:57`); Polymarket/Yahoo schema changes → indistinguishable empty
results (`polymarket.py:203`); Monte Carlo `var95` horizon-terminal, name-collides with daily (`montecarlo.py:112-113`);
`risk_contributions` docstring claims non-negative 0-100 decomp (`optimize.py:584-594`); unweighted mean
cross-sectional R² (`riskmodel.py:93-97`); mobile console input enabled during streaming (`Terminal.tsx:869`);
chat transcript uses array index as React key (`ChatPanel.tsx:206-239`); per-process `_schema_ready` DDL races
(multiple stores); `execute_many` unbatched single txn (`db.py:163-170`); untyped `GeneratedPanel` fallback
(`GeneratedPanel.tsx:51-64`); localStorage transcript accepts malformed `kind`/no corrupt-session recovery
(`useConsoleConversation.ts:28-51`); ChatPanel data hooks ignore loading/error + dead fetches (`ChatPanel.tsx:34-37`);
standalone suites lack consistent `sys.exit` (`test_engine.py:951-963`); DB tests fully monkeypatch `db`
(`test_datalayer.py:45-56`); smoke probe disables AI (`test_smoke.py:98-103`); post-merge runs installs but no
tests, 20s timeout (`scripts/post-merge.sh:1-4`); TSX artifact left registered if later write fails (`feature_builder.py:505-526`).

## 3. Cross-cutting themes

1. **Static-guard-then-trust is the dominant security failure mode** — both critical RCEs, the client-side panel
   guard, and the f-string gap all assume a denylist/AST audit can make untrusted LLM code safe to run in a
   privileged realm. One architectural decision → five findings.
2. **"Never crash" swallowing degrades silently and erases audit trails** — broad `except Exception: pass/return None`
   in the lifecycle handler, every LLM caller, the data-source fetchers, the state pool-timeout path. The module has
   no logging at all. Consequence: lost mutations, regex-only routing, mock-for-real swaps, per-instance divergence.
3. **Multi-tenant isolation is per-store, not an invariant** — correct in `strategy_store`/`dashboard_store` DB
   paths, missing in `template_store`, the in-memory `get_dashboard`, and the generated-skill registry; `user_id`
   scoping recorded but never enforced. Omissions invisible until exploited.
4. **Unlocked read-modify-write recurs on every mutable store** — strategy books, compliance config, first
   `session_state` insert. `state.py:_mutate` has the correct `FOR UPDATE` pattern the others fail to follow.
5. **Per-call timeouts exist but aggregate budgets don't** — orchestrator (90s), question path (60s), IEX
   reconstruct (unbounded) all exceed the ~60s proxy ceiling.
6. **Tests exist but don't gate, and the paths that ship aren't the paths tested** — 30 suites run nowhere;
   orchestrate tests force `ai_available=False`; smoke disables AI; DB tests stub all SQL; perf gate defaults off.

## 4. Prioritized remediation sequence

1. **Contain generated-code execution (Critical).** Move both `exec_module` and every `build()` into the isolated,
   network-denied, rlimited subprocess, returning only validated JSON. Neutralizes both critical RCEs; downgrades
   the AST/f-string gaps to defense-in-depth. The only remotely-exploitable path to full server compromise.
2. **Sandbox the client panel realm (High).** Cross-origin iframe (or declarative schema) + key generated skills by
   `firm_id`. Closes browser token exfiltration + cross-tenant skill execution.
3. **Close cross-tenant data access (High/Medium).** `firm_id` on `template_store`, firm guard on in-memory
   `get_dashboard`, enforce session ownership. Low effort, high blast radius, no architectural change.
4. **Protect the money path (High/Medium).** Fix the optimizer gross-exposure violation; convert
   strategy/compliance/session mutations to `FOR UPDATE` transactions.
5. **Stand up a real CI gate (High).** Wire `pytest artifacts/api-server/tests` into an `isValidation` workflow +
   add the LLM tool-call→panel test. Do this early so subsequent fixes can't silently regress.
6. **Harden orchestrator/data-source reliability (High/Medium).** Aggregate deadline + SSE heartbeat in
   `_orchestrate_build`, reorder lifecycle-vs-classify, route Treasury/FRED through `_resilient`, bound IEX reconstruct.
7. **Frontend resilience + remaining mediums.** Top-level + per-panel error boundaries, AbortController,
   virtualization, stale-serve cache tier, observability/logging cleanup. Parallel track.

---

# Feature & Reliability Roadmap

Grounded in the findings above. Everything extends systems that already exist.

## Reliability / trust features ("Can I believe the number?")

- **Data lineage & as-of provenance on every panel** — standard `{source, asOf, freshnessSec, mode: live|stale|mock, coverage}` block rendered as a badge. The cache already knows `asOf` (`cache.py:44`); surface it instead of discarding it. A stale-90s real treasury curve is tradeable; a silently-fabricated mock labeled identically is a trust-killer.
- **Stale-while-revalidate / last-known-good tier** — on producer exception/open circuit, serve last good value tagged `stale` with real `asOf` instead of mock/blank.
- **Confidence / coverage surfacing on quant panels** — `methodology` footnote: linking basis, horizon of each risk figure (rename Monte Carlo → `terminalVar95`), symbol coverage, flag when "Specific" exceeds an explained-variance threshold. (attribution.py:357, optimize.py:584, montecarlo.py:112, riskmodel.py:93)
- **Hard risk-limit attestation** — post-projection feasibility re-check; never return `optimal` when `sum|w| > gross + tol` (optimize.py:177).
- **Reproducibility / audit replay** — stamp every build with inputs to reproduce (query, sid, source asOf set, engine params, seed); "Reproduce this panel"; log every lifecycle action.
- **SLA / health & data-freshness panel** — per-source breaker state, last-good timestamps, LLM degraded-mode rate, pool saturation. Reuses `_resilient` breaker state + `pool_stats`.

## High-leverage NEW capabilities (extend what exists)

- **Deterministic + explainable routing** — decompose `_orchestrate_heuristic` into a `(matcher, builder, priority)` registry + representative-query tests; surface "I interpreted this as X because Y".
- **Strategy lifecycle as first-class guarded workflow** — classify before lifecycle, gate on question-signal, explicit confirmed action panel with criteria/stage/diff preview.
- **Backtest / signal integrity mode** — "rigor" toggle: common aligned calendar, non-overlapping forward windows, Carino-linked attribution (already in `brinson_linked`, wire into `factor_attribution`), "methodology integrity" badge.
- **Sandboxed self-built panels as a real product** — only after out-of-process exec + iframe + firm_id keying; then "describe a panel and the terminal builds it" is sellable, not a liability.
- **Per-user working state & sharing** — enforce ownership (403 on userId mismatch), then add intentional, audited sharing of DCF models/watchlists/dashboards.
- **App-shell resilience** — per-panel + app-shell error boundaries so one bad panel downgrades a tile, not the session.

## Quick wins vs big bets

**Quick wins (days):** classify-before-lifecycle; gross re-check → `infeasible-relaxed`; rename `var95`→`terminalVar95`;
React error boundaries; firm-scope in-memory `get_dashboard`; `firm_id` on templates; shared deadline + SSE heartbeat;
one jittered LLM retry; provenance/`asOf` badge; wire full pytest + load gate into CI.

**Big bets (weeks):** out-of-process + iframe-sandboxed self-building skills; intent registry replacing the 197-branch
heuristic; stale-while-revalidate + full resilience coverage; quant integrity mode; per-user state enforcement +
sharing; atomic strategy-mutation path.

**Sequencing:** the two self-building critical RCEs and the gross-exposure / lifecycle-mutation correctness bugs gate
trust for any professional rollout — do them first even though some are "big bets." The provenance badge, error
boundaries, and CI wiring are cheap force-multipliers that make every subsequent change safer to ship.



====================================================================================================
FILE: replit.md
====================================================================================================

# [Project name]

_Replace the heading above with the project's name, and this line with one sentence describing what this app does for users._

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the API server (port 5000)
- `pnpm smoke:api` — boot the API server and assert `/orchestrate` returns 200 (boot smoke check)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- Required env: `DATABASE_URL` — Postgres connection string

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)

## Where things live

_Populate as you build — short repo map plus pointers to the source-of-truth file for DB schema, API contracts, theme files, etc._

## Architecture decisions

_Populate as you build — non-obvious choices a reader couldn't infer from the code (3-5 bullets)._

## Product

_Describe the high-level user-facing capabilities of this app once they exist._

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

_Populate as you build — sharp edges, "always run X before Y" rules._

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
