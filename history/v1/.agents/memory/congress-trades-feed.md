---
name: Congressional trades feed
description: Durable decisions + honesty contract for the STOCK Act congressional-trading feed/panel.
---

# Congressional trades feed (congress_trades panel)

Real U.S. House + Senate disclosed securities trades (STOCK Act) as a feed + per-ticker panel.

**Data choice:** the underlying filings are public but awkward (House PTR PDFs, Senate eFD
behind a session form), so we read the free, key-less Quiver Quantitative aggregation of them
rather than scraping the primary sources. No API key required.
**Why:** key-less + already-parsed-to-JSON was the only zero-credential path to real data here.

**Honesty contract (the whole point of this feature):**
- Reporting lag is real (up to ~45 days under the STOCK Act). Keep transaction date AND
  disclosure date as distinct fields and render BOTH per row (not just a derived lag) — a
  code review rejected showing lag alone. A frontend test guards this.
- Amounts are disclosed only as ranges — never synthesize a point value.
- Every trade links back to its public disclosure (per-member page, not per-filing — the feed
  has no per-transaction link; document that so "source link" stays honest). The mock set must
  populate this too, or the "marked live with source links" requirement silently degrades.
- Mark live vs sample provenance.

**Routing:** the congress intent must be matched BEFORE the broader trade-flow/"activity" intent,
or generic-activity routing swallows it.

**Persistence:** stored in its own table created via raw DDL and queried with raw SQL (same
pattern as macro_prices), NOT drizzle — keeps a hand-written passthrough panel out of codegen.
Background-ingested on a multi-hour loop with a bounded best-effort refresh at query time so the
first request is current.
