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
- **News:** Yahoo RSS `https://feeds.finance.yahoo.com/rss/2.0/headline?s=SYM1,SYM2`
  — multi-symbol, key-less. Parse with feedparser; per-item `tags` carry the tickers.
- **Fundamentals:** `yfinance` `Ticker(sym).info` (it handles Yahoo's crumb/cookie auth).
  Heavier/slower than the chart endpoint, so ingest it on a slower cadence.

yfinance `.info` unit quirks (**Why:** these silently produce 100x-wrong numbers):
- `dividendYield` is already a **percent** (e.g. `0.47` means 0.47%), do NOT multiply by 100.
- `profitMargins` is a **fraction** (e.g. `0.63`), multiply by 100 to get net-margin %.

**Schema note:** sector is stored only on the `universe` registry table, NOT on
`fundamentals`. Join `fundamentals f LEFT JOIN universe u` and read `u.sector`.

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
