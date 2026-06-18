---
name: Strategy lifecycle & paper book desk
description: How the strategy registry / paper-book / lifecycle pillar is wired across persistence, engine, service, agent, and frontend.
---

# Strategy Lifecycle & Paper Book

A persisted strategy registry (research → backtest → paper → live / demote / retired)
with a paper book marked to REAL prices. Layers:

- **Persistence**: `lib/db/.../strategies.ts` (Drizzle) + `app/strategy_store.py`.
  Store is DB-first with an idempotent `CREATE TABLE IF NOT EXISTS` so it works
  even without `drizzle push`. JSON columns written as `json.dumps(...)::jsonb`;
  reads return a camelCase view; `upsert` expects snake_case (the service maps).
- **Engine**: `app/engine/paperbook.py` — pure MTM (position_marks, book_value,
  exposures, nav_curve from real closes since inception, realized_stats).
- **Service**: `app/strategy.py` — `create_strategy`, `paper_trade`,
  `mark`, `evaluate_promotion`, `transition`, `demote`, `desk_payload`.
- **Agent**: deterministic lifecycle intent handler runs BEFORE the LLM/heuristic
  in `orchestrate` (works for text + voice); `add_strategy_desk` tool + heuristic
  `wants_desk` only VIEW the desk.
- **Frontend**: `StrategyDeskPanel.tsx`, passthrough panel (no openapi model).

## Rebalance
- `strategy.rebalance(view, cost_bps)` re-derives targets from the **signal**
  (not the original explicit symbols/sector — those aren't persisted), diffs the
  marked book via `engine.generate_orders`, applies trades, and re-anchors entry
  prices + inception to today so the marked-book/NAV model stays consistent.
  Reports one-way turnover (`0.5*Σ|Δw|`) + modeled bps cost; stashes a
  `lastRebalance` summary on `construction` (JSON, no schema change) and logs a
  `{event:"rebalance"}` stage-history entry.
- **Routing trap**: "rebalance" is also a portfolio-optimizer keyword. The
  lifecycle handler runs first, so `_lifecycle_action` only returns "rebalance"
  when the query also says strateg/book or names a signal — otherwise "rebalance
  a portfolio" must fall through to `add_portfolio`/optimizer.

## Gotchas (cost >1 attempt)
- **`drizzle push` is destructive here**: pushing drops unrelated columns on
  `fundamentals`/`universe` and needs a TTY. Do NOT push for this table — the
  runtime `CREATE TABLE IF NOT EXISTS` in `strategy_store` is the intended path.
- **`paperbook.position_marks` has NO `weight` field** (only symbol/shares/
  entryPrice/price/marketValue/costBasis/pnl/pnlPct/priced). Per-name weight
  lives on `desk_payload().selected.exposures` (`[{symbol, weight}]`) — join on
  symbol in the UI, don't read `mark.weight`.
- **Promotion to live gates on persisted criteria** (default minSharpe .5,
  minReturnPct 0, maxDrawdownPct 25, minDays 5); "force"/"override"/"anyway" in
  the query bypasses via `transition(..., force=True)`.
- **Track record must come from PERSISTED daily NAV, not calendar age or live
  overlay**: promotion's "track record ≥ N days" counts audited `strategy_snapshots`
  rows (`trackDays`), never `ageDays` and never the display-only live "today"
  overlay point `mark()` appends. **Why:** a strategy must not clear `minDays` on a
  day whose snapshot hasn't been written yet. Snapshots are taken for *every*
  paper/live book (even flat ones — NAV = cash) so the series stays continuous;
  `mark()` only reconstructs from real closes as a fallback when zero snapshots
  exist yet.
- **Terminal vite build needs `PORT` and `BASE_PATH` env** or config load fails:
  `PORT=3000 BASE_PATH=/terminal pnpm --filter @workspace/terminal build`. The
  dev workflow runs HMR so source edits are live without a rebuild.

## Testing the lifecycle offline (tests/test_strategy*.py)
- Force the in-memory store by patching `strategy_store.db.db_available -> False`
  AND resetting `strategy_store._schema_ready=False` + `_mem.clear()`; restore in
  a finally. (`pytest` is not installed — mirror the runnable-as-script pattern.)
- Stub the data layer so nothing hits network/live DB: `repo.get_company`
  (return `{symbol,name,price}`), `repo.price_closes_bulk` (return
  `{series:{SYM:[{t,c}...]}, source, asOf}`), `repo.all_symbols`,
  `repo.get_all_companies`. Patching the `repo` module attrs hits both
  `strategy.py` and `agent.py` (same module object).
- Make close-series dates start at `date.today()` so `nav_curve` keeps them
  (`>= inception`); a fresh paper book has `ageDays=0 < minDays=5`, a
  deterministic promotion BLOCK regardless of stats — good for the gate test.
- Agent intent handler: stub `harness.run_skill` to a trivial panel dict to
  isolate `_handle_lifecycle` from the data-heavy panel builders.
- FastAPI: `TestClient(app)` WITHOUT a `with` block skips the app lifespan
  (background worker); strategy routes + skill registry are import-time so they
  still work. A blocked transition returns 200 with `ok:false` (not an
  HTTPException); only unknown id is a 404.
- **Lifecycle "create" regex hijacks programmatic queries**: `_lifecycle_action`
  matches `(create|register|set up|build|spin up|make) ... strateg`, so ANY
  orchestration query containing verb+"strateg" (e.g. "build a long call options
  strategy") is intercepted and creates a research strategy instead of the
  intended panel. When constructing queries in code (e.g. IV-surface cell click →
  options panel), phrase to dodge it: "Price a long call on NVDA at the $X strike
  for the Y expiry" routes to options_strategy via the `wants_options` heuristic.
