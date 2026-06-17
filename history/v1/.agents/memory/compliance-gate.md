---
name: Pre-trade compliance gate
description: How the pre-trade risk/compliance gate is layered and wired into the trade-apply path.
---

# Pre-trade compliance gate

Three layers, mirroring the other quant pillars:
- `app/engine/compliance.py` — pure, IO-free. `book_metrics`, `evaluate_limits`,
  `evaluate_lists`, `evaluate_gate`. Limits: maxPositionPct (per-name abs),
  maxNetPct (signed sum), maxLeverage (gross multiple), maxConcentrationPct (top-5).
  WARN_BAND=0.9 → warn; >1.0 → breach. Restricted = hard block, watch = warn.
  Weights are signed NAV fractions.
- `app/compliance_store.py` — GLOBAL config (single 'global' row) + audit trail.
  DB-first w/ in-mem fallback, idempotent CREATE TABLE. Config is firm-wide, NOT
  session-scoped (unlike alerts). Audit rows expose `decision` ("allowed"/"warn"/
  "blocked") + `summary`, NOT ok/blocked/reason.
- `app/strategy.py` — `ComplianceBlock` exc, `precheck(view, weights, action,
  audit, raise_on_block)`, `check_strategy` (audit=False read-only). Gate enforced
  in paper_trade (raises) and rebalance (returns info blocked).

**Why:** consistency with the existing engine/data/skill three-layer convention so
the gate is testable in isolation and the store survives restarts.

**How to apply:**
- Panel is a PASSTHROUGH type (`compliance`) — `_reg`'d in skills.py, NOT in
  harness.DATA_MODELS. `build_compliance({"strategy": name})` runs a read-only
  check; empty params just returns config+lists+audit.
- REST under `/api/compliance`: GET, POST restricted/watch/limits/kill-switch/check,
  DELETE audit + restricted/{sym} + watch/{sym}. Static routes declared BEFORE the
  parametrized `{symbol}` DELETEs.
- Frontend CompliancePanel.tsx manages its own state, raw-fetches `/api/compliance`
  (like DCFPanel), applies each mutation's returned payload. Audit rendering keys
  off `decision`/`summary`.
- Agent routing: `add_compliance` tool + `wants_compliance` heuristic ("is this
  trade allowed", "restricted/watch list", "kill switch", "halt trading", "compliance
  audit"); dispatch placed before wants_alerts (no real overlap, just ordering safety).
