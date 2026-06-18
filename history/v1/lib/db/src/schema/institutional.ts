import { pgTable, text, date, integer, doublePrecision, timestamp, primaryKey, index } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// Real institutional 13F filings parsed from SEC EDGAR. One row per manager per
// report period (quarter end) carrying the filing's metadata and portfolio
// total, so quarter-over-quarter flows can be computed against the prior period.
//
// Keyed by (cik, period) — the manager CIK and the report period — so
// re-ingesting the latest filing for a quarter upserts idempotently.
export const instFilingsTable = pgTable(
  "inst_filings",
  {
    cik: text("cik").notNull(),
    period: date("period").notNull(),
    institution: text("institution"),
    accessionNo: text("accession_no"),
    form: text("form"),
    filingDate: date("filing_date"),
    url: text("url"),
    totalValue: doublePrecision("total_value"),
    positions: integer("positions"),
    source: text("source"),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (t) => [primaryKey({ columns: [t.cik, t.period] })],
);

// Real 13F information-table positions. One row per (cik, period, cusip,
// putCall) — share positions carry an empty putCall; option positions carry
// "Put"/"Call". The ticker is resolved from the SEC Fails-to-Deliver CUSIP
// feed at ingest and may be null when a CUSIP has no listed-equity ticker.
export const instHoldingsTable = pgTable(
  "inst_holdings",
  {
    cik: text("cik").notNull(),
    period: date("period").notNull(),
    cusip: text("cusip").notNull(),
    putCall: text("put_call").notNull().default(""),
    institution: text("institution"),
    ticker: text("ticker"),
    name: text("name"),
    titleOfClass: text("title_of_class"),
    sharesType: text("shares_type"),
    shares: doublePrecision("shares"),
    value: doublePrecision("value"),
    url: text("url"),
    accessionNo: text("accession_no"),
    source: text("source"),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (t) => [
    primaryKey({ columns: [t.cik, t.period, t.cusip, t.putCall] }),
    index("inst_holdings_ticker_idx").on(t.ticker, t.period),
  ],
);

export const insertInstFilingSchema = createInsertSchema(instFilingsTable);
export type InsertInstFiling = z.infer<typeof insertInstFilingSchema>;
export type InstFiling = typeof instFilingsTable.$inferSelect;

export const insertInstHoldingSchema = createInsertSchema(instHoldingsTable);
export type InsertInstHolding = z.infer<typeof insertInstHoldingSchema>;
export type InstHolding = typeof instHoldingsTable.$inferSelect;
