---
name: Trade-flow alert rules
description: How the trade-flow alert feature is structured and two gotchas that cost rework.
---

Feature: notify when a trade_flow build crosses a threshold (block size,
dark pool %, buy imbalance). Rules + fired events stored per-session in
`state.py` (`_alert_rules`, `_alert_events`). Evaluation engine in
`alerts.py` (METRICS catalog + evaluate_flow/evaluate_dashboard), hooked
into `agent.py` orchestrate/refine. CRUD in `main.py` under /api/alerts.
Frontend: AlertsPanel (builder) + AlertsNotifications (poll + toast).

**Gotcha 1 — FastAPI route ordering:** the static `/alerts/events`
GET/DELETE routes MUST be declared *before* the parametrized
`/alerts/{rule_id}` DELETE. Otherwise "events" is matched as a rule_id
and the event endpoints silently never run (DELETE returns the rule
payload instead of clearing). Symptom: clear-events appears to do nothing.

**Gotcha 2 — event dedup:** events carry a `signature` so repeated
deterministic trade_flow builds (seeded data) don't re-fire duplicate
alerts. Second evaluate_flow over the same flow adds 0 events.

**How to apply:** when adding more static sub-paths under a parametrized
resource, always order static-before-parametrized. When evaluating
deterministic builders repeatedly, dedup on a stable signature.
