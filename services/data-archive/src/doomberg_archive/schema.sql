-- Canonical DDL for the v1 market-data archive (schema `archive`).
--
-- This is READ-ONLY reference data, isolated from the v2 platform tables
-- (runs/strategies/trace/books). NOT NULL constraints are replicated (the data
-- satisfies them); strict PKs are intentionally omitted to tolerate the bulk
-- load -- query indexes instead. `tickers` is text[]; sources/trend/changes/
-- sparkline are jsonb.
--
-- Authoritative source: docs/plans/doomberg-v2/DATA-LAYER-INTERFACES.md

CREATE SCHEMA IF NOT EXISTS archive;

CREATE TABLE IF NOT EXISTS archive.universe (
  symbol text NOT NULL, name text, sector text,
  tracked boolean NOT NULL, pending boolean NOT NULL,
  first_seen_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
  country text, exchange text, industry text, website text,
  listed_at date, delisted_at date, status text NOT NULL);
CREATE INDEX IF NOT EXISTS ix_universe_symbol ON archive.universe(symbol);
CREATE INDEX IF NOT EXISTS ix_universe_sector ON archive.universe(sector);

CREATE TABLE IF NOT EXISTS archive.sectors (
  id text NOT NULL, name text NOT NULL, updated_at timestamptz NOT NULL);

CREATE TABLE IF NOT EXISTS archive.ohlcv (
  symbol text NOT NULL, d date NOT NULL,
  o double precision, h double precision, l double precision,
  c double precision, v double precision, updated_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS ix_ohlcv_symbol_d ON archive.ohlcv(symbol, d);

CREATE TABLE IF NOT EXISTS archive.fundamentals (
  symbol text NOT NULL, name text, price double precision, change_pct double precision,
  market_cap double precision, pe_ratio double precision, volume double precision,
  revenue double precision, net_margin double precision, eps double precision,
  dividend_yield double precision, beta double precision,
  week52_high double precision, week52_low double precision, description text,
  updated_at timestamptz NOT NULL, is_live boolean NOT NULL,
  revenue_growth double precision, earnings_date date, ex_dividend_date date,
  dividend_date date, mcap_refreshed_at timestamptz, earnings_eps_estimate double precision);
CREATE INDEX IF NOT EXISTS ix_fundamentals_symbol ON archive.fundamentals(symbol);

CREATE TABLE IF NOT EXISTS archive.fundamentals_pit (
  symbol text NOT NULL, period_end date NOT NULL, report_date date NOT NULL,
  revenue double precision, net_income double precision, net_margin double precision,
  eps double precision, report_estimated boolean NOT NULL, source text,
  updated_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS ix_fund_pit_symbol_report ON archive.fundamentals_pit(symbol, report_date);

CREATE TABLE IF NOT EXISTS archive.analyst_ratings (
  symbol text NOT NULL, name text, covered boolean NOT NULL, consensus_key text,
  recommendation_mean double precision, num_analysts integer,
  strong_buy integer, buy integer, hold integer, sell integer, strong_sell integer,
  target_mean double precision, target_high double precision, target_low double precision,
  target_median double precision, current_price double precision,
  changes jsonb, source text, updated_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS ix_analyst_symbol ON archive.analyst_ratings(symbol);

CREATE TABLE IF NOT EXISTS archive.news (
  id text NOT NULL, headline text NOT NULL, source text, summary text, url text,
  published_at timestamptz, sentiment text, tickers text[], sector text,
  fetched_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS ix_news_published ON archive.news(published_at DESC);
CREATE INDEX IF NOT EXISTS ix_news_tickers ON archive.news USING gin(tickers);

CREATE TABLE IF NOT EXISTS archive.congress_trades (
  id text NOT NULL, member text NOT NULL, chamber text, party text, party_code text,
  ticker text, txn_type text, raw_type text, amount_range text,
  amount_low double precision, amount_high double precision,
  transaction_date date, disclosure_date date, source_url text, description text,
  fetched_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS ix_congress_ticker ON archive.congress_trades(ticker);
CREATE INDEX IF NOT EXISTS ix_congress_date ON archive.congress_trades(transaction_date DESC);

CREATE TABLE IF NOT EXISTS archive.insider_transactions (
  accession_no text NOT NULL, txn_seq integer NOT NULL, symbol text NOT NULL,
  cik text, issuer_name text, insider_name text, role text,
  transaction_code text, transaction_type text, acquired_disposed text, security_title text,
  is_derivative boolean NOT NULL, shares double precision, price double precision,
  value double precision, shares_owned_after double precision,
  transaction_date date, filing_date date, form text, url text, source text,
  updated_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS ix_insider_symbol ON archive.insider_transactions(symbol, transaction_date DESC);

CREATE TABLE IF NOT EXISTS archive.inst_holdings (
  cik text NOT NULL, period date NOT NULL, cusip text NOT NULL, put_call text NOT NULL,
  institution text, ticker text, name text, title_of_class text, shares_type text,
  shares double precision, value double precision, url text, accession_no text,
  source text, updated_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS ix_inst_holdings_ticker ON archive.inst_holdings(ticker, period);
CREATE INDEX IF NOT EXISTS ix_inst_holdings_cik ON archive.inst_holdings(cik, period);

CREATE TABLE IF NOT EXISTS archive.inst_filings (
  cik text NOT NULL, period date NOT NULL, institution text, accession_no text,
  form text, filing_date date, url text, total_value double precision, positions integer,
  source text, updated_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS ix_inst_filings_cik ON archive.inst_filings(cik, period);

CREATE TABLE IF NOT EXISTS archive.etf_holdings (
  etf text NOT NULL, symbol text NOT NULL, name text, weight double precision,
  as_of date, source text, updated_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS ix_etf_holdings_etf ON archive.etf_holdings(etf);
CREATE INDEX IF NOT EXISTS ix_etf_holdings_symbol ON archive.etf_holdings(symbol);

CREATE TABLE IF NOT EXISTS archive.sentiment (
  scope_type text NOT NULL, scope text NOT NULL, overall double precision, label text,
  sources jsonb, trend jsonb, updated_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS ix_sentiment_scope ON archive.sentiment(scope_type, scope);

CREATE TABLE IF NOT EXISTS archive.macro_prices (
  symbol text NOT NULL, name text, price double precision, change_pct double precision,
  updated_at timestamptz NOT NULL);

CREATE TABLE IF NOT EXISTS archive.macro_quotes (
  symbol text NOT NULL, price double precision, change_pct double precision,
  sparkline jsonb, is_live boolean NOT NULL, updated_at timestamptz NOT NULL);
