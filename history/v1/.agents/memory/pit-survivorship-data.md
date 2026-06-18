---
name: Point-in-time & survivorship-bias-free data
description: How PIT/survivorship honesty is enforced across repo accessors, builders and panels — the "label, never impute" contract.
---

# Point-in-time (PIT) & survivorship-bias-free data

The honesty contract: historical windows resolve to the universe active *then*
(incl. later-delisted names), fundamentals are served as-reported, and wherever
PIT/delisted coverage is missing it is **clearly LABELED**, never silently
backfilled with restated/survivor data.

## Where the pieces live
- `app/data.py` `DELISTED` dict — curated real listed/delisted dates (Lehman,
  Bear, WaMu, Enron, SVB, FRCB, ATVI, TWTR, YHOO, XLNX, CELG, MTLQQ). `get_delisted`.
- `app/repo.py` PIT accessors: `listing_info` (DB→curated→unknown), `historical_universe`
  (active-in-window + merged delisted, `survivorshipSafe` true only when delisted
  names are actually carried), `historical_closes` (**real-only**: omits names with
  no genuine OHLCV, reports them under `missing` — never mock-fills),
  `fundamentals_as_of` (as-reported latest period ≤ as_of, or **None**),
  `pit_coverage`.
- `app/skills.py` builders emit a `coverage`/`pit` block: build_backtest,
  build_signal_research/scorecard/portfolio, build_data_universe, build_data_quality.
  `_augment_signal_coverage` + `_signal_window` add per-signal coverage.
- `app/models.py` — `coverage: Optional[dict]` on BacktestData/SignalResearchData/
  SignalScorecardData (Optional[dict] passes through the harness untouched).
- terminal `CoverageBadge.tsx` (shared pill strip) wired into the 4 research panels;
  DataUniversePanel + DataQualityPanel render a dedicated PIT/survivorship section.

## Key rules / gotchas
- **Never impute a delisted name.** `historical_closes` is the honesty gate; if a
  window's delisted names have no real OHLCV ingested yet, build_backtest falls back
  to a synthetic curve with `priceBasis:"synthetic"`, `pointInTime:false` and an
  explicit "NOT point-in-time safe / illustrative" note. Real delisted OHLCV + broad
  PIT-fundamentals ingest are deferred follow-ups (not yet populated by the worker).
- `survivorshipSafe` for a single active name is True (no constituents to drop), even
  when priceBasis is synthetic — the price honesty lives in priceBasis/pointInTime/notes.
- Recent windows (no curated delistings) honestly report survivor-only with a note.
- No openapi codegen for the coverage fields — panels read them via a cast
  (`(data as unknown as {coverage?: DataCoverage}).coverage`), matching the existing
  passthrough-panel convention. Terminal `tsc` shows pre-existing stale-codegen errors;
  the **vite build is the real gate** and passes.

## Verifying
- `tests/test_pit_data.py` (standalone, 44 checks) — run via
  `env -i HOME=$HOME PATH=/home/runner/workspace/.pythonlibs/bin:/usr/bin:/bin python3.11 tests/test_pit_data.py`.
- smoke: `env -i ... TERMINAL_SKIP_WORKER=1 bash scripts/smoke-api.sh` (the script's
  bare `python -m uvicorn` hits the MAX_PATH wrapper unless invoked via env -i).
- terminal: `PORT=5000 BASE_PATH=/ pnpm --filter @workspace/terminal run build`.
