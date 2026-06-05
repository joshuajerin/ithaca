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
- Headline benchmark = a real ETF from a small validated whitelist (S&P/Nasdaq/
  Dow/Russell/total-market). Default to the broad-market one; unknown or
  non-ETF tickers must fall back to the default, never benchmark against an
  unvalidated symbol.
- Brinson sector benchmark = real sector/industry ETFs, one per sector. Sectors
  with no clean real ETF must be **excluded and reported**, not silently faked
  or imputed. Every benchmark sector return must come from a real instrument.
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
