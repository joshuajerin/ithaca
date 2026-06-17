---
name: Order-book real replay from IEX DEEP
description: How the order_book panel serves REAL depth reconstructed from IEX HIST DEEP captures, with synthetic fallback + honesty contract.
---

# Order-book real replay (IEX DEEP, venue-only, T+1)

The `order_book` panel can serve a **real** depth-of-book replay reconstructed
from IEX Exchange HIST DEEP captures, falling back to clearly-labelled synthetic
depth until a real replay exists.

## Honesty contract (must never be violated)
- `replayReal` is True ONLY for frames rebuilt from a real IEX DEEP capture.
- Real replays are **venue-only** (IEX prints, not the consolidated tape) and
  **T+1** (IEX publishes the capture the morning after the session).
- A symbol IEX barely traded yields NO real payload (`payload()` returns None
  below `MIN_FRAMES`); it must never be promoted to "real". The worker marks such
  jobs `unavailable` so the panel stops promising a real replay.
- Trade side is inferred (DEEP trades carry no side) via the standard quote/tick
  test against the prevailing book — label it as inferred, don't claim it's given.

## Flow (on-demand, never in the request path)
1. `skills.build_order_book` → `orderbook_store.latest_replay(sym)`; if cached,
   return REAL payload (re-select frame by `timestamp` param, set source/asOf).
2. Else `orderbook_store.request_job(sym)` (enqueue) + return synthetic via
   `_synthetic_order_book`, worded by job status (loading vs unavailable). The
   `source` string is lifted to the panel **envelope** by the harness (not data).
3. `worker._orderbook_loop` (20s poll) drains `pending_jobs`, resolves
   `iex_deep.latest_session`, and reconstructs ALL queued symbols in ONE shared
   streaming pass (`iex_deep.reconstruct`) — the ~13 GB download is shared.

## Reconstruction internals (`app/sources/iex_deep.py`)
- Hand-rolled streaming **pcapng** + IEX-TP DEEP `struct` decoder
  (`iter_deep_messages`) — no library (file is huge + dodges package firewall).
  Buffers partial pcapng blocks across chunk boundaries.
- `_SymbolBook` keeps a price-level dict per side + tape; snapshots a frame every
  10 min (09:30–16:00) BEFORE applying the boundary message; skips empty pre-open
  frames. `Reconstructor.past_session()` stops the stream after the close so we
  don't pull the after-hours tail.
- ET offset computed once per session (constant within RTH) → cheap int math on
  ns timestamps instead of per-message tz conversion.

## Testing
- `tests/test_orderbook_replay.py` is standalone (no pytest, no network): builds
  a tiny pcapng+IEX-TP fixture to exercise the wire decoder (incl. chunk
  boundaries + symbol filter), then drives `Reconstructor` directly to assert
  payload schema, frame cadence, ladder ordering, spread, side inference, block
  events, and the thin-symbol→no-real-payload guard.
- A real end-to-end reconstruction is ~20 min (background) and was NOT run in
  CI; it's intended for the worker thread only.
