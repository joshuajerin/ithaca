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
