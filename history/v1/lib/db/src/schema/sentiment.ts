import { pgTable, text, doublePrecision, jsonb, timestamp, primaryKey } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// Derived social/news sentiment per scope, keyed by (scopeType, scope).
export const sentimentTable = pgTable(
  "sentiment",
  {
    scopeType: text("scope_type").notNull(), // "symbol" | "sector"
    scope: text("scope").notNull(), // upper-cased symbol or sector id
    overall: doublePrecision("overall"),
    label: text("label"),
    sources: jsonb("sources"),
    trend: jsonb("trend"),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (t) => [primaryKey({ columns: [t.scopeType, t.scope] })],
);

export const insertSentimentSchema = createInsertSchema(sentimentTable);
export type InsertSentiment = z.infer<typeof insertSentimentSchema>;
export type SentimentRecord = typeof sentimentTable.$inferSelect;
