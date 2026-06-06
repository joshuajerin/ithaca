---
name: Multi-ticker analyst comparison
description: How the analyst_compare panel composes per-ticker analyst reports, and the heuristic-routing keyword traps to avoid.
---

# Multi-ticker analyst comparison (analyst_compare)

A quick side-by-side of the analyst stance across several tickers. It does NOT
re-implement analysis — it fans out to `build_analyst_report({"symbol": s})` per
name and distills each into a compact card (stance, conviction, headline, call,
top figures).

**Per-ticker isolation is the core contract.** Each symbol is built in a
ThreadPoolExecutor and wrapped so one failing/timing-out name never sinks the
panel; failures go into a `failed` list and are simply omitted from the cards.
The builder raises only when EVERY ticker fails. Concurrency matters: N
sequential analyst reports (each an AI call) would blow past the ~60s preview
proxy window — fan them out, don't loop.

**Why concurrent, not sequential:** see `ai-client-timeouts.md`. Each
build_analyst_report makes its own bounded AI call; running 3+ in series stacks
the latency.

## Heuristic-routing keyword trap
`_orchestrate_heuristic` in agent.py decides analyst_compare via "2+ symbols +
analyst intent". Be careful with substring matches when picking trigger words:
- `"view" in "overview"` is True, `"take"` is overly broad. Using bare
  "view"/"take" wrongly routes "give me an overview of NVDA and AMD" to the
  analyst comparison. Use explicit phrases ("analyst", "stance", "conviction",
  "bull/bear", "better buy") and reuse the existing `wants_analyst_report` flag.
- Route analyst_compare BEFORE the single analyst_report block, since both can
  match a 2-symbol analyst query.
