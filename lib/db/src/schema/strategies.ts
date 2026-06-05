import { pgTable, text, doublePrecision, timestamp, date, jsonb, primaryKey } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// One row per systematic strategy in the research-to-production lifecycle.
// `stage` moves research → backtest → paper → live (and demote / retired).
// The paper/live book is a fixed set of `positions` (shares + entry price) plus
// `cash`, marked-to-market against real prices day over day; its P&L history is
// reconstructed from real OHLCV since `inceptionDate`, never persisted synthetic.
export const strategiesTable = pgTable("strategies", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  signal: text("signal"),
  construction: jsonb("construction"),
  stage: text("stage").notNull().default("research"),
  capital: doublePrecision("capital"),
  cash: doublePrecision("cash"),
  inceptionDate: date("inception_date"),
  positions: jsonb("positions"),
  targetWeights: jsonb("target_weights"),
  promotionCriteria: jsonb("promotion_criteria"),
  stageHistory: jsonb("stage_history"),
  notes: text("notes"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertStrategySchema = createInsertSchema(strategiesTable);
export type InsertStrategy = z.infer<typeof insertStrategySchema>;
export type Strategy = typeof strategiesTable.$inferSelect;

// Audited end-of-day mark-to-market snapshots, one row per strategy per trading
// day. Written by the background worker so every paper/live book accrues a real,
// persisted daily NAV/P&L track record instead of being recomputed on the fly.
// The composite primary key (strategy_id, d) makes daily writes idempotent — a
// re-run for the same day refreshes the value rather than inserting a duplicate.
export const strategySnapshotsTable = pgTable(
  "strategy_snapshots",
  {
    strategyId: text("strategy_id").notNull(),
    d: date("d").notNull(),
    nav: doublePrecision("nav"),
    pnl: doublePrecision("pnl"),
    pnlPct: doublePrecision("pnl_pct"),
    cash: doublePrecision("cash"),
    capital: doublePrecision("capital"),
    stage: text("stage"),
    source: text("source"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (t) => [primaryKey({ columns: [t.strategyId, t.d] })],
);

export const insertStrategySnapshotSchema = createInsertSchema(strategySnapshotsTable);
export type InsertStrategySnapshot = z.infer<typeof insertStrategySnapshotSchema>;
export type StrategySnapshot = typeof strategySnapshotsTable.$inferSelect;
