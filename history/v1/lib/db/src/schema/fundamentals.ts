import { pgTable, text, doublePrecision, timestamp } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// One row per symbol holding the latest fundamentals/quote snapshot.
export const fundamentalsTable = pgTable("fundamentals", {
  symbol: text("symbol").primaryKey(),
  name: text("name"),
  price: doublePrecision("price"),
  changePct: doublePrecision("change_pct"),
  marketCap: doublePrecision("market_cap"),
  peRatio: doublePrecision("pe_ratio"),
  volume: doublePrecision("volume"),
  revenue: doublePrecision("revenue"),
  netMargin: doublePrecision("net_margin"),
  eps: doublePrecision("eps"),
  dividendYield: doublePrecision("dividend_yield"),
  beta: doublePrecision("beta"),
  week52High: doublePrecision("week52_high"),
  week52Low: doublePrecision("week52_low"),
  description: text("description"),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertFundamentalsSchema = createInsertSchema(fundamentalsTable);
export type InsertFundamentals = z.infer<typeof insertFundamentalsSchema>;
export type Fundamentals = typeof fundamentalsTable.$inferSelect;
