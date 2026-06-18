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
