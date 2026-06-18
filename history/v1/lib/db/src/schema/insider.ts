import { pgTable, text, date, integer, doublePrecision, boolean, timestamp, primaryKey, index } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// Real insider transactions parsed from SEC EDGAR Forms 4 and 5 (ownership
// reports). One row per transaction line within a filing, so a single Form 4
// with several buys/sells/option exercises expands to several rows.
//
// Keyed by (accessionNo, txnSeq) — the EDGAR accession number plus the line's
// position within the filing — so re-ingesting a filing upserts idempotently.
// Everything here is parsed from the live filing; nothing is synthesized.
export const insiderTransactionsTable = pgTable(
  "insider_transactions",
  {
    accessionNo: text("accession_no").notNull(),
    txnSeq: integer("txn_seq").notNull(),
    symbol: text("symbol").notNull(),
    cik: text("cik"),
    issuerName: text("issuer_name"),
    insiderName: text("insider_name"),
    role: text("role"),
    transactionCode: text("transaction_code"),
    transactionType: text("transaction_type"),
    acquiredDisposed: text("acquired_disposed"),
    securityTitle: text("security_title"),
    isDerivative: boolean("is_derivative").default(false).notNull(),
    shares: doublePrecision("shares"),
    price: doublePrecision("price"),
    value: doublePrecision("value"),
    sharesOwnedAfter: doublePrecision("shares_owned_after"),
    transactionDate: date("transaction_date"),
    filingDate: date("filing_date"),
    form: text("form"),
    url: text("url"),
    source: text("source"),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (t) => [
    primaryKey({ columns: [t.accessionNo, t.txnSeq] }),
    index("insider_symbol_date_idx").on(t.symbol, t.transactionDate),
  ],
);

export const insertInsiderTransactionSchema = createInsertSchema(insiderTransactionsTable);
export type InsertInsiderTransaction = z.infer<typeof insertInsiderTransactionSchema>;
export type InsiderTransaction = typeof insiderTransactionsTable.$inferSelect;
