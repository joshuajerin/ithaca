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
