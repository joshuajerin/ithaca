---
name: Pending panel auto-refresh poll
description: How pending ("fetching live data") panels self-populate without the user asking twice.
---

# Pending panel auto-refresh poll

PanelContainer auto-refreshes any panel whose `data.pending === true` (the warm-up
envelope returned by builders like price_chart/fundamentals/order_book/trade_flow
when a ticker isn't ingested yet). A `useEffect` polls every 5s, gives up after 60s,
and stops the moment `result.data.pending` is falsy.

**How it re-fetches:** fires `useRefinePanel` with explicit `params` `{symbol[, range]}`
(deterministic structured refine — bypasses the LLM). The pending builders all accept
`symbol` (price_chart also `range`).

**Why a dedicated 3rd mutation (`pollMutation`):** `renderContent` shows the
"Processing" spinner when `refineMutation.isPending`. Polling on a separate mutation
keeps the satellite "Fetching live data" UI visible and never flips to Processing.

**Why deps are `[isPending, panel.id, sessionId]` only (primitives):** each poll calls
`onRefined`, minting a fresh `data` ref; depending on `data` would restart/starve the
timer (see debounced-recompute-deps). The loop self-schedules via setTimeout and the
cleanup cancels once isPending flips false. `onRefined` is read through a ref.

**How to apply:** new builders that emit a pending envelope just need to carry `symbol`
in the envelope and accept it as a param — no PanelContainer change needed. Fake/invalid
tickers never ingest, so they stay pending and the 60s cap ends the poll cleanly.
