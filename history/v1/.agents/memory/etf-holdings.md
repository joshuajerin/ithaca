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
