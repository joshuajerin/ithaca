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
