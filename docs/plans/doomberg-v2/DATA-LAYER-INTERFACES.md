# Data Layer + Archive — shared contract (3-agent build)

This is the single source of truth for three parallel work-streams. Build to THIS file; do not
invent alternative shapes. Cross-stream dependencies are expressed as the `ArchiveGateway`
protocol + the canonical schema below — both sides code to the protocol, integration is then a no-op.

## The v1 archive data we're importing

`data/v1_archive.json` (gitignored, ~92 MB) is a JSON **array of 240,220 records**, each:
```json
{ "tbl": "<table_name>", "row": { ...the row as JSON... } }
```
It is the export of `SELECT tbl, to_jsonb(t) AS row FROM <table> t` UNION-ed across the 15
market-data tables (the v1 secret/app tables — users, auth, firms, compliance_*, strategies,
sessions, order_book_* — were deliberately excluded; never import those).

Per-table record counts (authoritative):

| table | rows |
|---|---|
| inst_holdings | 134349 |
| ohlcv | 81832 |
| insider_transactions | 14376 |
| news | 5672 |
| congress_trades | 1002 |
| fundamentals_pit | 903 |
| universe | 683 |
| fundamentals | 671 |
| etf_holdings | 310 |
| sentiment | 178 |
| analyst_ratings | 155 |
| inst_filings | 32 |
| sectors | 27 |
| macro_prices | 16 |
| macro_quotes | 14 |

## Canonical schema (Postgres, schema `archive`)

The v1 archive is READ-ONLY reference data and lives in its own Postgres schema `archive`,
isolated from the v2 platform tables (runs/strategies/trace/books). NOT NULL constraints are
replicated (the data satisfies them); strict PKs are intentionally omitted to tolerate the bulk
load — query indexes instead. `tickers` is `text[]`; `sources`/`trend`/`changes`/`sparkline` are
`jsonb`.

```sql
CREATE SCHEMA IF NOT EXISTS archive;

CREATE TABLE archive.universe (
  symbol text NOT NULL, name text, sector text,
  tracked boolean NOT NULL, pending boolean NOT NULL,
  first_seen_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
  country text, exchange text, industry text, website text,
  listed_at date, delisted_at date, status text NOT NULL);
CREATE INDEX ix_universe_symbol ON archive.universe(symbol);
CREATE INDEX ix_universe_sector ON archive.universe(sector);

CREATE TABLE archive.sectors (
  id text NOT NULL, name text NOT NULL, updated_at timestamptz NOT NULL);

CREATE TABLE archive.ohlcv (
  symbol text NOT NULL, d date NOT NULL,
  o double precision, h double precision, l double precision,
  c double precision, v double precision, updated_at timestamptz NOT NULL);
CREATE INDEX ix_ohlcv_symbol_d ON archive.ohlcv(symbol, d);

CREATE TABLE archive.fundamentals (
  symbol text NOT NULL, name text, price double precision, change_pct double precision,
  market_cap double precision, pe_ratio double precision, volume double precision,
  revenue double precision, net_margin double precision, eps double precision,
  dividend_yield double precision, beta double precision,
  week52_high double precision, week52_low double precision, description text,
  updated_at timestamptz NOT NULL, is_live boolean NOT NULL,
  revenue_growth double precision, earnings_date date, ex_dividend_date date,
  dividend_date date, mcap_refreshed_at timestamptz, earnings_eps_estimate double precision);
CREATE INDEX ix_fundamentals_symbol ON archive.fundamentals(symbol);

CREATE TABLE archive.fundamentals_pit (
  symbol text NOT NULL, period_end date NOT NULL, report_date date NOT NULL,
  revenue double precision, net_income double precision, net_margin double precision,
  eps double precision, report_estimated boolean NOT NULL, source text,
  updated_at timestamptz NOT NULL);
CREATE INDEX ix_fund_pit_symbol_report ON archive.fundamentals_pit(symbol, report_date);

CREATE TABLE archive.analyst_ratings (
  symbol text NOT NULL, name text, covered boolean NOT NULL, consensus_key text,
  recommendation_mean double precision, num_analysts integer,
  strong_buy integer, buy integer, hold integer, sell integer, strong_sell integer,
  target_mean double precision, target_high double precision, target_low double precision,
  target_median double precision, current_price double precision,
  changes jsonb, source text, updated_at timestamptz NOT NULL);
CREATE INDEX ix_analyst_symbol ON archive.analyst_ratings(symbol);

CREATE TABLE archive.news (
  id text NOT NULL, headline text NOT NULL, source text, summary text, url text,
  published_at timestamptz, sentiment text, tickers text[], sector text,
  fetched_at timestamptz NOT NULL);
CREATE INDEX ix_news_published ON archive.news(published_at DESC);
CREATE INDEX ix_news_tickers ON archive.news USING gin(tickers);

CREATE TABLE archive.congress_trades (
  id text NOT NULL, member text NOT NULL, chamber text, party text, party_code text,
  ticker text, txn_type text, raw_type text, amount_range text,
  amount_low double precision, amount_high double precision,
  transaction_date date, disclosure_date date, source_url text, description text,
  fetched_at timestamptz NOT NULL);
CREATE INDEX ix_congress_ticker ON archive.congress_trades(ticker);
CREATE INDEX ix_congress_date ON archive.congress_trades(transaction_date DESC);

CREATE TABLE archive.insider_transactions (
  accession_no text NOT NULL, txn_seq integer NOT NULL, symbol text NOT NULL,
  cik text, issuer_name text, insider_name text, role text,
  transaction_code text, transaction_type text, acquired_disposed text, security_title text,
  is_derivative boolean NOT NULL, shares double precision, price double precision,
  value double precision, shares_owned_after double precision,
  transaction_date date, filing_date date, form text, url text, source text,
  updated_at timestamptz NOT NULL);
CREATE INDEX ix_insider_symbol ON archive.insider_transactions(symbol, transaction_date DESC);

CREATE TABLE archive.inst_holdings (
  cik text NOT NULL, period date NOT NULL, cusip text NOT NULL, put_call text NOT NULL,
  institution text, ticker text, name text, title_of_class text, shares_type text,
  shares double precision, value double precision, url text, accession_no text,
  source text, updated_at timestamptz NOT NULL);
CREATE INDEX ix_inst_holdings_ticker ON archive.inst_holdings(ticker, period);
CREATE INDEX ix_inst_holdings_cik ON archive.inst_holdings(cik, period);

CREATE TABLE archive.inst_filings (
  cik text NOT NULL, period date NOT NULL, institution text, accession_no text,
  form text, filing_date date, url text, total_value double precision, positions integer,
  source text, updated_at timestamptz NOT NULL);
CREATE INDEX ix_inst_filings_cik ON archive.inst_filings(cik, period);

CREATE TABLE archive.etf_holdings (
  etf text NOT NULL, symbol text NOT NULL, name text, weight double precision,
  as_of date, source text, updated_at timestamptz NOT NULL);
CREATE INDEX ix_etf_holdings_etf ON archive.etf_holdings(etf);
CREATE INDEX ix_etf_holdings_symbol ON archive.etf_holdings(symbol);

CREATE TABLE archive.sentiment (
  scope_type text NOT NULL, scope text NOT NULL, overall double precision, label text,
  sources jsonb, trend jsonb, updated_at timestamptz NOT NULL);
CREATE INDEX ix_sentiment_scope ON archive.sentiment(scope_type, scope);

CREATE TABLE archive.macro_prices (
  symbol text NOT NULL, name text, price double precision, change_pct double precision,
  updated_at timestamptz NOT NULL);

CREATE TABLE archive.macro_quotes (
  symbol text NOT NULL, price double precision, change_pct double precision,
  sparkline jsonb, is_live boolean NOT NULL, updated_at timestamptz NOT NULL);
```

## ArchiveGateway — the read seam (Python, psycopg)

The skills read ONLY through this gateway (never raw SQL in a skill). Stream 1 implements it
against `archive.*`; Stream 3 codes against this protocol and tests with an in-memory fake.
All methods are tenant-agnostic (the archive is shared reference data); every result a skill
returns is wrapped in the v2 provenance envelope with `source: "doomberg-v1-archive"`.

```python
class ArchiveGateway(Protocol):
    # prices
    def ohlcv(self, symbol: str, start: str | None = None, end: str | None = None) -> list[dict]: ...
    def ohlcv_panel(self, symbols: list[str], start=None, end=None) -> tuple[list[str], "np.ndarray", list[str]]: ...  # dates, closes[T,N], symbols
    # reference
    def universe(self, tracked_only: bool = True) -> list[dict]: ...
    def sectors(self) -> list[dict]: ...
    # fundamentals
    def fundamentals(self, symbols: list[str]) -> list[dict]: ...
    def fundamentals_pit(self, symbol: str, as_of: str) -> dict | None: ...   # latest report_date <= as_of (the PIT unlock)
    # analyst / news / sentiment
    def analyst_ratings(self, symbols: list[str]) -> list[dict]: ...
    def news(self, ticker: str | None = None, sector: str | None = None, limit: int = 50) -> list[dict]: ...
    def sentiment(self, scope_type: str, scope: str) -> dict | None: ...
    # ownership / flows
    def congress_trades(self, ticker: str | None = None, member: str | None = None, limit: int = 100) -> list[dict]: ...
    def insider_transactions(self, symbol: str, limit: int = 100) -> list[dict]: ...
    def inst_holdings(self, ticker: str | None = None, cik: str | None = None, period: str | None = None) -> list[dict]: ...
    def inst_filings(self, cik: str | None = None, period: str | None = None) -> list[dict]: ...
    def etf_holdings(self, etf: str) -> list[dict]: ...
    def etf_exposure(self, symbol: str) -> list[dict]: ...   # which ETFs hold `symbol`
    # macro
    def macro(self) -> dict: ...   # {prices: [...], quotes: [...]}
```

A `connect_args` / DSN comes from `DOOMBERG_ARCHIVE_URL` (Postgres), defaulting to the same
`DOOMBERG_DB` Postgres in prod. Local dev/tests may run against a Postgres container or a
loaded fixture; the gateway must not hard-require network at import.

## Skill catalog (Stream 3) — agent-callable, no limits

Each skill = a `Core`/`SkillSet` method + an entry in a `SKILLS` registry + an MCP `@mcp.tool`
wrapper + a test. Declarative args only; NO agent code runs. Returns a provenance-wrapped result.
Port as many v1 `build_*` skills as the archive supports (real data only — do NOT port the
synthetic v1 skills: order_book, iv_surface/options_*, cds_pricer, trade_flow, structured_product).

| MCP tool | reads | from v1 |
|---|---|---|
| `market.get_ohlcv` (exists) | ohlcv | build_price_chart |
| `market.news` | news | build_news |
| `market.screener` | fundamentals + ohlcv | build_screener |
| `market.movers` | fundamentals/ohlcv | build_heatmap |
| `fundamentals.get` | fundamentals + fundamentals_pit | build_fundamentals |
| `fundamentals.compare` | fundamentals | build_comparison |
| `fundamentals.pit` | fundamentals_pit | (the PIT unlock) |
| `analyst.ratings` | analyst_ratings | build_analyst_ratings |
| `congress.trades` | congress_trades | build_congress_trades |
| `insider.activity` | insider_transactions | build_insider_activity |
| `institutional.holdings` | inst_holdings + inst_filings | build_institutional_holders |
| `institutional.flows` | inst_holdings (period deltas) | build_institutional_flows |
| `etf.holdings` / `etf.exposure` | etf_holdings | build_etf_holdings/exposure |
| `sentiment.get` | sentiment | build_sentiment |
| `macro.dashboard` | macro_prices/quotes | build_macro_dashboard |
| `universe.list` | universe + sectors | build_data_universe |
| `backtest.run` (exists) | ohlcv_panel | build_backtest — now can run on the archive |

Keep shaping logic in the current `doomberg-core` skill implementations. Data comes from
`ArchiveGateway`, never archived v1 HTTP sources, and never synthetic generators.

### COMPUTED skills (`source: "computed"`)

Pure, deterministic math (numpy + stdlib only) over either agent-supplied scalars or REAL archive
series — never fabricated market data. The provenance `source` is `"computed"` and an `inputs`
field records the origin: `"agent"` (scalars the agent passed in) or `"doomberg-v1-archive"` (the
math ran on real archive prices/fundamentals, whose freshness rides along on the envelope). `pit`
is always `false`. The math library is `doomberg_core.skills.compute`; archive-derived risk/
optimizer/backtest skills reuse the real `doomberg_core.engine` (`riskmodel`, `optimize`,
`montecarlo`, `scenario`, `stress`, `backtest`).

| MCP tool | category | computes | inputs |
|---|---|---|---|
| `options.greeks` | options | Black-Scholes price + delta/gamma/theta/vega/rho (`compute.bs_price`+`bs_greeks`) | agent (S,K,T,r,sigma,type) |
| `options.implied_vol` | options | implied vol by bisection (`compute.bs_implied_vol`); None outside arb band | agent (price,S,K,T,r,type) |
| `vol.realized` | volatility | annualized realized (log-return) vol (`compute.realized_vol`) | archive closes |
| `vol.term_structure` | volatility | realized vol at trailing windows [20,60,120,252] + slope | archive closes |
| `correlation.matrix` | risk | symmetric return-correlation matrix (`compute.correlation_matrix`) | archive returns |
| `factor.exposures` | risk | z-scored style exposures Market/Size/Value/Momentum/Quality (`engine.riskmodel.standardize`) | archive fundamentals |
| `portfolio.optimize` | portfolio | mean-variance long-only weights (`engine.optimize.mean_variance`) | archive returns |
| `montecarlo.simulate` | simulation | GBM/bootstrap terminal-price fan + summary (`engine.montecarlo.monte_carlo`), seeded | archive returns or agent (sigma,drift,S) |
| `scenario.project` | simulation | baseline-vs-scenario forward fan (`engine.scenario.project_scenario`), seeded | archive returns + agent drift |
| `dcf.value` | valuation | 5y DCF implied price + sensitivity grid (`compute.dcf_value`) | archive fundamentals + agent assumptions |
| `risk.stress` | risk | factor/asset shock P&L (`engine.stress.factor_shock_pnl`/`asset_shock_pnl`) | agent (exposures/weights + shocks) |
| `tearsheet` | backtest | single-strategy backtest tearsheet (`engine.backtest.run_backtest`) | archive closes + agent strategy |
| `walkforward.run` | backtest | anchored walk-forward + overfitting diagnostics (`engine.backtest.run_walk_forward`) | archive closes + agent strategy |

Final catalog: **29 skills** (16 archive-backed + 13 computed) over `SKILLS`, each with a
`SkillSet` method, an MCP `@mcp.tool` wrapper, and a test. The MCP server advertises **32 tools**
total (the 29 skills + the 3 base tools `market.get_ohlcv` / `backtest.run` / `propose_strategy`).
No target skill was skipped — the engine (`riskmodel`/`optimize`/`montecarlo`/`scenario`/`stress`/
`backtest`) supports the tearsheet, walk-forward, stress and scenario skills cleanly.

## Provenance + PIT
Archive-backed skill results wrap the v2 provenance envelope: `source: "doomberg-v1-archive"`,
`freshness` = max(updated_at/fetched_at) of the rows used, `pit: true` ONLY for
`fundamentals.pit` / `fundamentals_pit`-backed results (real point-in-time), else `pit: false`.
COMPUTED skill results use `source: "computed"`, `pit: false`, and an `inputs` field
(`"agent"` or `"doomberg-v1-archive"`); when they read archive series the data freshness still
rides along. Computed skills NEVER present a calculated number as a live market quote.

## INFRASTRUCTURE GUARDRAIL (Stream 2 — hard constraint)
DigitalOcean services we may use: **Droplets / DOKS (CPU node pools only), Managed Postgres,
Spaces, Container Registry, Load Balancer, VPC, Firewalls.** NEVER provision or reference any of:
GPU Droplets, NVIDIA H100 GPU Kubernetes, Bare Metal GPUs, Dedicated/Serverless Inference,
Paperspace, Cloudways, or any third-party pass-through. Add a Terraform validation that asserts
every node/db size slug is a CPU slug (`s-*`, `c-*`, `db-*`, `g-*` general — NOT `gpu-*`/`gd-*`/
`p-*` GPU) and fail the plan otherwise.

## APPLY BOUNDARY (Streams 1 & 2 — do NOT cross)
No DO API token is present yet (`infra/terraform/.env` absent). Do EVERYTHING up to the credentialed
step — write/lint/validate configs, build loaders, test locally — but NEVER run `terraform apply`,
`doctl` against the real account, or create cloud resources. Produce a one-command apply runbook and
stop, reporting exactly what's needed (the token). Never spend money unattended.
