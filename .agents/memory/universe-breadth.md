---
name: Stock universe breadth (US + SGX)
description: How the deep curated catalog stays cheap — mock breadth in DB, live data only on demand, SGX via base codes.
---

# Deep curated universe (US + SGX)

The terminal catalog is large (hundreds of names, many sectors) but only a small
curated **CORE** set is ever continuously fetched. Everything else is breadth:
deterministic mock metrics that look real and only get refreshed with live data
when a user actually opens the symbol.

**The split is the whole design — do not break it:**
- `data.CORE_SYMBOLS` is snapshotted from the hand-written headliners *before*
  the bulk `_q()`/`_load()` loaders run. The worker marks only CORE
  `tracked = TRUE` and ingests it on the price/fundamentals/news loops.
- Bulk names are seeded `tracked = FALSE` with `fundamentals.is_live = FALSE`
  (mock). They become live one-shot via the on-demand loop when `note_symbol()`
  flips `pending = TRUE`.

**Why mock fundamentals are pre-seeded into the DB at startup:** so the
breadth-reading panels (screener/heatmap/sector lists) work off the same
DB queries with no per-symbol fallback gymnastics. `is_live` is the single source
of truth for the `live` vs `mock` provenance badge (`_company_from_row`).

**On-demand contract:** `get_company` does NOT enqueue catalogued symbols (they
already have a DB row), so the primary builders (`build_price_chart`,
`build_fundamentals`) must call `repo.note_symbol()` explicitly to request live
data. `note_symbol` is a no-op once a symbol is already live or already pending.

**SGX gotcha:** SGX names are catalogued under their **base code** (e.g. `D05`,
`O39`, `C38U`) — never with `.SI`. `data.yahoo_symbol()` appends `.SI` only at
fetch time (worker ingest), and rows are always persisted/keyed under the base
code. Symbol regexes (`_extract_symbols`, `note_symbol`) must accept alphanumeric
tokens, not just `[A-Z]`, or SGX codes silently won't resolve.

**Prompt budget:** the full list is far too big to inline in every LLM tool
description. Use `repo.prompt_symbols(n)` (cap, market-cap desc) for prompts;
keep `all_symbols()`/`symbols_in_sector()` for the real breadth at request time.

**Schema:** added idempotently in `worker._seed_universe` (no migration files):
`universe.country`, `universe.exchange`, `fundamentals.is_live`.
