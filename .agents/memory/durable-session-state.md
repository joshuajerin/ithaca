---
name: Durable, firm-scoped session state
description: How active dashboards/history/DCF/alerts are externalized to Postgres so the API is stateless and horizontally scalable.
---

The terminal's per-session working state (active dashboards, conversation
history, saved DCF models, trade-flow alert rules/events, session owner) is the
one thing that was process-memory only. It now lives in Postgres so a restart no
longer wipes a user's session and multiple instances share it.

**Design:** one generic table `session_state(firm_id, session_id, kind, data jsonb, updated_at, PK(firm_id,session_id,kind))`.
One row per concern (`kind` = dashboard/history/dcf/alert_rules/alert_events/owner),
so each can be read/mutated independently. Read-modify-write goes through a
`_mutate` helper that takes `SELECT ... FOR UPDATE` so concurrent instances
serialize on the row instead of racing (append_history cap, alert-event dedup,
set-once owner all rely on this). Falls back to an in-memory dict when no
`DATABASE_URL` (feature still works, just not durable/shared) — same DB-first /
in-memory-fallback pattern the other stores use.

**Why one table, not one-per-concern:** keeps schema/migration trivial and the
firm+session scoping uniform; jsonb auto-parses to python objects via psycopg
dict_row, so no per-kind columns needed.

**Firm scoping:** `firm_id` comes from `tenant.current_firm_id()` (the request
contextvar), so two firms with the SAME session_id never see each other's state.
The watchlist is intentionally GLOBAL (shared default symbols) — stored under a
sentinel `firm_id=session_id="__global__"`, not firm-scoped.

**Public API of `state.py` was preserved exactly** — only the storage backend
changed, so all call sites (main.py, agent, skills, worker) are untouched.

## Horizontal-scale companions (same task)
- `db.py`: pool min/max are env-tunable (`DB_POOL_MIN`/`DB_POOL_MAX`, default
  2/16) + a connection `timeout` so a saturated pool raises instead of hanging.
  Added `ping()` (SELECT 1), `pool_stats()`, and `advisory_lock(key)` ctxmgr
  (Postgres `pg_try_advisory_lock`; yields True when no DB → single instance).
- `/readyz` (public): pings DB + reports pool stats; returns 503 when DB is
  *configured but unreachable* (not ready for the durability promise), 200 in
  in-memory fallback mode.
- worker `_rebalance_loop` is wrapped in `db.advisory_lock(REBALANCE_LOCK_KEY)`
  so only ONE instance runs the money-moving rebalance pass per tick. Snapshot
  loop is left unlocked — `record_daily_snapshots` is idempotent per trading day
  so concurrent upserts are safe.

## Validating it
- Durability: signup → write session state (e.g. POST /api/dcf-models) →
  restart workflow → read back. Isolation: a second firm with the same
  sessionId must read empty.
- `pnpm loadtest:api` (scripts/loadtest-api.sh + loadtest_api.py): boots a
  server, signs up N firms, hammers hot paths concurrently, asserts errors=0 and
  zero cross-firm isolation/durability breaches. **Latency is report-only**
  (warning, not a gate) — absolute numbers depend on loopback vs. public-proxy
  and instance count. The agent-bash run trips the yfinance MAX_PATH wrapper at
  uvicorn launch, so drive the DRIVER against the running workflow with the
  `env -i .../.pythonlibs/bin/python3` workaround if you must run it yourself.
