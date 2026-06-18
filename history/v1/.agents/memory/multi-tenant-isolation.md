---
name: Multi-tenant data isolation (per firm)
description: How firm scoping is enforced across every persisted/in-memory store in api-server; the contextvar pattern, the shared-by-design exception, and the verification path.
---

# Per-firm data isolation in api-server

Every user-owned store is scoped to the authenticated firm so Firm A never sees
Firm B's data. The mechanism is a request-bound firm context, not firm_id
threaded through every call site.

## The contextvar pattern (the load-bearing decision)
- `app/tenant.py` holds a `contextvar` with `DEFAULT_FIRM_ID="default"`,
  `set_current_firm()`, `current_firm_id()`, `resolve_firm(firm_id)` (explicit
  arg wins, else context, else default), and `firm_context(firm_id)` context
  manager.
- `require_identity` in `main.py` is **async** on purpose and calls
  `tenant.set_current_firm(...)` before returning. **Why async:** Starlette runs
  sync endpoints in a threadpool via anyio, which *copies* the contextvar into
  the worker thread. A plain sync dependency would set the var on a different
  context and the value would not reach the handler. Do not make it sync.
- Stores read `current_firm_id()` internally (param defaults to `None` →
  `resolve_firm`). Request handlers therefore need **no** firm argument — the
  context already carries it.

## Worker / background path
- The worker has no request context, so cross-firm loops
  (`record_daily_snapshots`, `run_scheduled_rebalances`) iterate
  `strategy_store.list_all_strategies()` (cross-firm, worker-only) and wrap each
  strategy in `with tenant.firm_context(s["firmId"]):`. Everything downstream
  (mark → snapshot read/write, rebalance → compliance precheck/get_config,
  `_persist`/upsert) then auto-scopes to that firm.
- `list_strategies()` is firm-scoped (request path); `list_all_strategies()` is
  the deliberate cross-firm escape hatch — only call it inside a `firm_context`.

## Storage shape
- DB tables get a `firm_id text NOT NULL DEFAULT 'default'` column added via
  idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` + backfill (matches the
  runtime-CREATE-TABLE convention; no drizzle push). Scoped: `strategies`,
  `strategy_snapshots`, `saved_dashboards`, `compliance_audit`.
- `compliance_config` is special: its PK **is** the firm_id (one config row per
  firm). The legacy single `id='global'` row is renamed to `'default'` on
  schema-ensure. Old `_GLOBAL_ID` constant is gone.
- In-memory fallbacks: per-session stores in `state.py` are keyed by a
  `(firm_id, session_id)` tuple via `_key()`; compliance `_mem_cfg`/`_mem_audit`
  are dicts keyed by firm_id.
- Cross-firm deletes/restores use `... WHERE id=%s AND firm_id=%s RETURNING id`
  so a wrong-firm id silently affects nothing (returns False / None).

## Shared-by-design exception
- Order-book replays (`orderbook_store.py`) are **NOT** firm-scoped on purpose:
  a reconstructed IEX DEEP session is firm-agnostic market data, identical for
  all tenants and expensive to rebuild, so it is cached once and shared.

## Verification
- The boot smoke check (`pnpm smoke:api`) now must authenticate first (auth gates
  all `/api`): it signs up a throwaway firm and passes the session via
  `Authorization: Bearer <token>` (the cookie is `Secure`, so curl won't echo it
  over plain http). The token is parsed from the signup `Set-Cookie` header.
- `pnpm smoke:api` boots uvicorn via the `python` wrapper which trips the
  agent-bash MAX_PATH trap — it runs fine in the real workflow/validation runner.
  To verify in agent bash, restart the `artifacts/api-server: API Server`
  workflow and hit `https://$REPLIT_DEV_DOMAIN/api/...` with curl (curl is fine;
  only the python subprocess trips MAX_PATH).
- Proven end-to-end via curl: Firm B can't list/restore Firm A's saved dashboard
  (404), B's delete leaves A's data intact, and A's restricted-symbol compliance
  config is invisible to B.
