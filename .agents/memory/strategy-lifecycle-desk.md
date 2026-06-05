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
- **Terminal vite build needs `PORT` and `BASE_PATH` env** or config load fails:
  `PORT=3000 BASE_PATH=/terminal pnpm --filter @workspace/terminal build`. The
  dev workflow runs HMR so source edits are live without a rebuild.
