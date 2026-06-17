import { pgTable, text, date, doublePrecision, boolean, timestamp, primaryKey } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// Point-in-time (as-reported) fundamentals history, one row per fiscal period.
//
// Unlike `fundamentals` (a single latest, often restated snapshot per symbol),
// this table preserves what was reported for each quarter and the date it became
// public, so a backtest can look up the figures that were actually knowable at a
// given as-of date instead of using today's restated numbers (look-ahead bias).
//
// `reportDate` is when the figure became public; when an exact filing/earnings
// date isn't available from the free source it is estimated from the period end
// plus a conservative reporting lag and flagged via `reportEstimated`. Keyed by
// (symbol, periodEnd) for idempotent upserts.
export const fundamentalsPitTable = pgTable(
  "fundamentals_pit",
  {
    symbol: text("symbol").notNull(),
    periodEnd: date("period_end").notNull(),
    reportDate: date("report_date").notNull(),
    revenue: doublePrecision("revenue"),
    netIncome: doublePrecision("net_income"),
    netMargin: doublePrecision("net_margin"),
    eps: doublePrecision("eps"),
    reportEstimated: boolean("report_estimated").default(false).notNull(),
    source: text("source"),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (t) => [primaryKey({ columns: [t.symbol, t.periodEnd] })],
);

export const insertFundamentalsPitSchema = createInsertSchema(fundamentalsPitTable);
export type InsertFundamentalsPit = z.infer<typeof insertFundamentalsPitSchema>;
export type FundamentalsPit = typeof fundamentalsPitTable.$inferSelect;
