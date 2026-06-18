---
name: Load-test latency baseline & default-dashboard caching
description: True loopback latency baseline for the hot API paths, why /api/dashboard/default was the bottleneck, the cache+single-flight fix, and how the load driver's per-endpoint budgets / opt-in gate work.
---

The hot read paths are all trivial (<12ms warm, served from Postgres) EXCEPT
`/api/dashboard/default`. That endpoint builds 6 panels and fires several live
upstream fetches per request (heatmap, news RSS, sentiment) for a ~240KB payload
— ~1s of work, and its output is IDENTICAL for everyone (no params, no user/firm
scoping). Under concurrency it saturates the single uvicorn worker and starves
every other endpoint (loopback driver: dashboard p95 ~26s, all others multi-second,
~5 req/s).

**Fix:** serve it from a short-TTL process cache (`DASHBOARD_DEFAULT_TTL`, default
60s, 0 disables) via `cache.cached_singleflight`. Result on the same loopback
driver: dashboard p95 ~1s warm, total throughput ~5 → ~91 req/s.

**Why single-flight, not plain `cache.cached`:** `cached` has NO lock around the
producer, so on a cold/expired key every concurrent caller runs the expensive
build at once — a thundering herd (cold-cache dashboard p95 ballooned back to ~10s).
`cached_singleflight` (added to cache.py) takes a per-key lock so only one caller
rebuilds while the rest wait and read the fresh value. Use it for any cached
producer that is both expensive AND shared. Cold-cache p95 then capped at ~2.2s
even with the live-ingestion worker contending.

## Measuring latency here (env constraints)
- **Drive over loopback, not the public proxy.** Point the driver at the running
  workflow: `BASE=http://127.0.0.1:8080`. The public TLS proxy inflates numbers.
- The driver is HTTP-only stdlib, but running ANY python from agent bash needs the
  `env -i .../.pythonlibs/bin/python3.11` MAX_PATH workaround.
- **You cannot get a worker-SKIPPED clean baseline from agent bash.** Booting your
  own uvicorn with `TERMINAL_SKIP_WORKER=1` works, but the moment a request hits a
  stale-data path it spawns a yfinance subprocess → the agent-bash MAX_PATH wrapper
  kills it. So agent-bash runs must go against the live workflow (worker ACTIVE),
  whose contention adds real run-to-run variance (dashboard cold p95 1–2.5s). The
  clean worker-skipped baseline is what `pnpm loadtest:api` (scripts/loadtest-api.sh)
  produces when a human runs it in a NORMAL repl shell.
- **Signup is rate-limited 10/60s** (`security.rate_limit("auth", 10, 60)`). The
  driver signs up 8 firms, so two runs inside a minute trip it ("signup failed for
  firm N"). Run it once per minute.

## Load driver budgets & gate (scripts/loadtest_api.py)
- Per-endpoint p95 budgets replace the old single global one: `ENDPOINT_BUDGET_MS`
  (dashboard_default 2000ms, the rest 1500ms), fallback `DEFAULT_LATENCY_BUDGET_MS`
  (`LOAD_LATENCY_BUDGET_MS`, default 1500). Override any one with
  `LOAD_BUDGET_<LABEL>_MS`.
- Correctness (errors=0, zero cross-firm isolation/durability breaches) ALWAYS gates.
- Latency is a report/warning by default; set `LOAD_GATE_LATENCY=1` to make a p95
  over budget FAIL the run. Keep it opt-in / loopback-only — absolute latency depends
  on loopback-vs-proxy and instance count, so a blanket hard gate would be flaky.
