---
name: Upstream source resilience (retry + circuit breaker)
description: How the key-less market-data sources back off under Yahoo/yfinance throttling.
---

All upstream fetches in `app/sources/` route through `_resilient.py`, which adds
retry-with-backoff + a per-source circuit breaker on top of the raw httpx/yfinance
calls. Two entry points:

- `request(source, url, ...)` — for httpx GET sources (chart endpoint, RSS).
  Throttle is detected by **status code** (429/403/5xx). Non-throttle HTTP errors
  (e.g. 404) propagate immediately, no retry, no breaker trip.
- `guard(source, fn, *args)` — for yfinance (does its own HTTP). Throttle is
  inferred from the **exception text/type** (`_looks_throttled`). Non-throttle
  exceptions (e.g. ValueError "no fundamentals for X") propagate immediately so
  one genuinely-empty symbol never cools down the whole source.

**Breaker keys (independent cooldowns):** `yahoo-chart` (all price/intraday/daily
fetches share it — same host), `yahoo-rss`, `google-news`, `yfinance`.

**Why these design choices:**
- One increment toward the breaker threshold per *user-facing call*, not per retry
  attempt (incremented once at the bottom in `_open_and_raise`). Threshold 3 ⇒
  3 throttled calls before the breaker opens.
- Cooldown doubles on each successive re-open (30s → … → 300s cap); any clean
  success fully resets (`_consecutive`, `_open_until`, `_opens`).
- Breaker is `threading.Lock`-guarded because the worker drives every call via
  `asyncio.to_thread` (multiple threads touch one breaker).

**Logging contract:** throttle/network-retry events log on `terminal.sources.throttle`
(distinct from hard failures, which surface on callers' own loggers). When the
breaker is open, callers raise `CircuitOpenError`; the worker logs those at DEBUG
(`"... ingest skipped ..."`) so a cooldown isn't mistaken for a failure. Exhausted
retries raise `ThrottleError`. Both subclass `Exception`, so existing best-effort
callers (worker loops, repo query-time fetch, skills intraday) keep falling back.
