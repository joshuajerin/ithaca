import { pgTable, text, boolean, timestamp } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// The ticker/universe registry. `tracked` symbols are ingested on a schedule;
// `pending` marks a newly-referenced symbol the worker should fetch on demand.
export const universeTable = pgTable("universe", {
  symbol: text("symbol").primaryKey(),
  name: text("name"),
  sector: text("sector"),
  tracked: boolean("tracked").default(true).notNull(),
  pending: boolean("pending").default(false).notNull(),
  firstSeenAt: timestamp("first_seen_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertUniverseSchema = createInsertSchema(universeTable);
export type InsertUniverse = z.infer<typeof insertUniverseSchema>;
export type Universe = typeof universeTable.$inferSelect;
