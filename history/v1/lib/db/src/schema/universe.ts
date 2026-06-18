import { pgTable, text, boolean, date, timestamp } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// The ticker/universe registry. `tracked` symbols are ingested on a schedule;
// `pending` marks a newly-referenced symbol the worker should fetch on demand.
//
// `listedAt` / `delistedAt` / `status` make the registry point-in-time aware:
// a historical window can resolve to the names that were actually listed then
// (including names later delisted), instead of only today's survivors. These
// are best-effort/free-source-derived (listedAt from the instrument's first
// trade date; delisted names are a curated set) and the data-quality view is
// explicit about how much of the universe carries real listing/delisting dates.
export const universeTable = pgTable("universe", {
  symbol: text("symbol").primaryKey(),
  name: text("name"),
  sector: text("sector"),
  tracked: boolean("tracked").default(true).notNull(),
  pending: boolean("pending").default(false).notNull(),
  // Listing / delisting lifecycle (point-in-time universe support).
  listedAt: date("listed_at"),
  delistedAt: date("delisted_at"),
  status: text("status").default("active").notNull(), // active | delisted
  firstSeenAt: timestamp("first_seen_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertUniverseSchema = createInsertSchema(universeTable);
export type InsertUniverse = z.infer<typeof insertUniverseSchema>;
export type Universe = typeof universeTable.$inferSelect;
