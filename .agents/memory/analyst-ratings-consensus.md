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
