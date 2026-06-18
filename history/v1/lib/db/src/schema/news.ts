import { pgTable, text, timestamp } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// News items, keyed by a stable id derived from the source url/headline.
export const newsTable = pgTable("news", {
  id: text("id").primaryKey(),
  headline: text("headline").notNull(),
  source: text("source"),
  summary: text("summary"),
  url: text("url"),
  publishedAt: timestamp("published_at", { withTimezone: true }),
  sentiment: text("sentiment"),
  tickers: text("tickers").array(),
  sector: text("sector"),
  fetchedAt: timestamp("fetched_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertNewsSchema = createInsertSchema(newsTable);
export type InsertNews = z.infer<typeof insertNewsSchema>;
export type News = typeof newsTable.$inferSelect;
