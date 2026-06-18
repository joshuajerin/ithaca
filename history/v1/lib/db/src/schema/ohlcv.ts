import { pgTable, text, date, doublePrecision, timestamp, primaryKey } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// Daily OHLCV price history, keyed by (symbol, trading date) for idempotent upserts.
export const ohlcvTable = pgTable(
  "ohlcv",
  {
    symbol: text("symbol").notNull(),
    d: date("d").notNull(),
    o: doublePrecision("o"),
    h: doublePrecision("h"),
    l: doublePrecision("l"),
    c: doublePrecision("c"),
    v: doublePrecision("v"),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (t) => [primaryKey({ columns: [t.symbol, t.d] })],
);

export const insertOhlcvSchema = createInsertSchema(ohlcvTable);
export type InsertOhlcv = z.infer<typeof insertOhlcvSchema>;
export type Ohlcv = typeof ohlcvTable.$inferSelect;
