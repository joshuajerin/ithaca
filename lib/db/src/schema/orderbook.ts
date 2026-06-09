import { pgTable, text, jsonb, timestamp, primaryKey } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// One row per (symbol, session) real order-book replay reconstructed from an IEX
// Exchange HIST DEEP capture (T+1, venue-only). `payload` is the full panel data
// dict (frames + tape + events) so the order-book skill can serve it verbatim;
// `source`/`as_of` carry the freshness labelling. Keyed by (symbol, session) for
// idempotent re-writes if a session is reconstructed again.
export const orderBookReplayTable = pgTable(
  "order_book_replay",
  {
    symbol: text("symbol").notNull(),
    session: text("session").notNull(),
    payload: jsonb("payload").notNull(),
    source: text("source"),
    asOf: text("as_of"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (t) => [primaryKey({ columns: [t.symbol, t.session] })],
);

export const insertOrderBookReplaySchema = createInsertSchema(orderBookReplayTable);
export type InsertOrderBookReplay = z.infer<typeof insertOrderBookReplaySchema>;
export type OrderBookReplay = typeof orderBookReplayTable.$inferSelect;

// Background reconstruction queue: one job per symbol. status moves
// pending → running → done | unavailable | error. The worker drains `pending`
// jobs and the order-book skill enqueues them on a cache miss.
export const orderBookJobsTable = pgTable("order_book_jobs", {
  symbol: text("symbol").primaryKey(),
  session: text("session"),
  status: text("status").notNull().default("pending"),
  detail: text("detail"),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertOrderBookJobSchema = createInsertSchema(orderBookJobsTable);
export type InsertOrderBookJob = z.infer<typeof insertOrderBookJobSchema>;
export type OrderBookJob = typeof orderBookJobsTable.$inferSelect;
