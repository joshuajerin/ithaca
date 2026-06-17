---
name: Cost-aware construction & rebalancing pipeline
description: How trade-cost penalties, the share-level trade list, scheduled rebalance, and the rebalance_plan panel fit together; the real-cost-only contract.
---

# Cost-aware construction & automated rebalancing

The optimizer and the paper-book rebalance both penalize trading by the SAME real
square-root market-impact model used by TCA. No fabricated costs anywhere.

- **Engine** (`app/engine/execution.py::estimate_trade_costs`): the reusable
  diff→cost step. Per order it attaches `impactBps`/`costUsd` only when real ADV +
  daily vol exist; otherwise `costSupported: False` with a reason — never a faked
  cost. The aggregate's `grossNotional` and `totalCostUsd` roll up ONLY the
  supported orders (unsupported notional is excluded), so don't expect gross to
  equal the full order book when some names lack ADV/vol.
- **Optimizer** (`app/engine/optimize.py`): `_solve_utility` / `mean_variance`
  take a per-name `kappa` (square-root impact curvature) folded into a 3/2-power
  penalty `sum_i kappa_i·|w_i - current_i|^1.5` valued by `impact_cost(...)`. The
  cost term reduces churn vs the current book — it never increases it.
- **Strategy** (`app/strategy.py`): `compute_trade_list(view)` is READ-ONLY
  (returns orders + expected modeled cost + navAfter, no mutation). `rebalance`
  applies trades and debits the real modeled cost from cash. Scheduling lives in
  `set_schedule`/`is_due`/`run_scheduled_rebalances` (weekends skipped; due needs
  an ACTIVE stage + cadence elapsed since lastRebalance|inception).
- **Skill** (`app/skills.py::build_rebalance_plan`): preview (no apply) vs apply;
  returns `expected` (modeled) + `realized` (intraday sim, unsupported flagged)
  blocks, order rows, updated weights, status ok|empty. Passthrough panel
  `rebalance_plan` (no DATA_MODEL).
- **Routing** (`app/agent.py`): "rebalance my strategy" → apply; "what trades to
  get to target" / "preview/plan" → preview (no apply). `to (the) target` regex is
  deliberately narrowed so it does NOT hijack optimizer "target vol" requests.

**Why:** the whole point of this pillar is that cost is honest — a future change
that hardcodes a cost, or that lets the optimizer trade as if free, breaks the
contract. Keep cost flowing from the one impact model and keep unsupported orders
flagged, not faked.

## Gotcha: paper books are already at target
`create_strategy(paper=True)` calls `paper_trade`, which establishes the book AT
the target weights from real prices. So a fresh paper strategy shows NO trades on
a rebalance preview — that's correct, not a bug. To exercise establishing trades
in a test, use a research-stage strategy (`paper=False`, positions `None`) so the
trade list is the full establishing set.
