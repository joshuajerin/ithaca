import { pgTable, text, timestamp } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// A firm is a tenant. Signup creates a firm plus its first (admin) user; every
// user belongs to exactly one firm. Data isolation between firms is a separate
// downstream task — this layer only establishes the firm as an entity.
export const firmsTable = pgTable("firms", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertFirmSchema = createInsertSchema(firmsTable);
export type InsertFirm = z.infer<typeof insertFirmSchema>;
export type Firm = typeof firmsTable.$inferSelect;

// One user, one firm. `role` is admin | trader | analyst | read-only; the first
// user created during firm signup is the admin. Passwords are stored only as a
// PBKDF2-HMAC-SHA256 hash plus per-user salt — never in plaintext. Per-role
// permission enforcement is out of scope for this foundation task.
export const usersTable = pgTable("users", {
  id: text("id").primaryKey(),
  firmId: text("firm_id")
    .notNull()
    .references(() => firmsTable.id, { onDelete: "cascade" }),
  email: text("email").notNull().unique(),
  name: text("name").notNull(),
  role: text("role").notNull().default("trader"),
  passwordHash: text("password_hash").notNull(),
  passwordSalt: text("password_salt").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertUserSchema = createInsertSchema(usersTable);
export type InsertUser = z.infer<typeof insertUserSchema>;
export type User = typeof usersTable.$inferSelect;

// Durable server-side sessions so login survives a server restart. Only the
// SHA-256 hash of each opaque session token is stored, so a database leak does
// not expose usable tokens. Rows self-clean on access once `expiresAt` passes.
export const authSessionsTable = pgTable("auth_sessions", {
  tokenHash: text("token_hash").primaryKey(),
  userId: text("user_id")
    .notNull()
    .references(() => usersTable.id, { onDelete: "cascade" }),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
});

export const insertAuthSessionSchema = createInsertSchema(authSessionsTable);
export type InsertAuthSession = z.infer<typeof insertAuthSessionSchema>;
export type AuthSession = typeof authSessionsTable.$inferSelect;
