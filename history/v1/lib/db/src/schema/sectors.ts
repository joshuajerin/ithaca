import { pgTable, text, timestamp } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const sectorsTable = pgTable("sectors", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertSectorSchema = createInsertSchema(sectorsTable);
export type InsertSector = z.infer<typeof insertSectorSchema>;
export type Sector = typeof sectorsTable.$inferSelect;
