---
name: Supply chain concentration risk scoring
description: How supply-chain panel risk scores are computed and the passthrough-vs-pydantic-model gotcha that strips unknown panel fields.
---

# Supply chain risk scoring

Per-node risk = exposure × (0.55 + 0.65 × geoRisk), bucketed Low/Medium/High/Critical
(`_RISK_BANDS`), with a single-source floor (exposure ≥ 90 → ≥ High; +sensitive region → Critical).
`_GEO_RISK` / `_COUNTRY_NAME` maps live in `skills.py`. `_annotate_supply_chain_risk` mutates
nodes+table and builds `riskSummary` (topRisks, countryConcentration as share of total supplier
exposure, counts). Both the curated `_SUPPLY_CHAIN_DB` path and `_generate_supply_chain` go through it.

**Why a separate score, not raw exposure:** a 100% dependency in Taiwan must read worse than a
100% dependency in the US — geopolitical region amplifies concentration risk.

## Policy / trade-action layer
`_POLICY_RISK` (keyed by country, like `_GEO_RISK`) carries `{flag, severity 0-1, reason}` for
tariffs / export controls / sanctions; `_POLICY_LABEL` maps flag→display. `_score_supply_node`
blends it as a third multiplier term: `exposure * (0.55 + 0.65*geo + 0.5*policy_sev)`, and floors
the label at High when `policy_sev >= 0.80` (severe = sanctions/hard export controls); a severe
single source escalates to Critical. Nodes/rows gain `policyRisk/policyReason/policySeverity`.
`riskSummary.policyRisks` aggregates affected suppliers per region; policy-driven nodes become
`kind="policy"` candidates so they rank into topRisks. **Concentration answers "where am I
exposed", policy answers "what event actually breaks this link"** — keep them as separate signals.
Remember: every new field needs adding to the pydantic models too (see gotcha below).

## The gotcha that cost a round-trip
`supply_chain` is NOT a fully passthrough panel — it has a pydantic model
`models.SupplyChainData` registered in `harness.DATA_MODELS`. `run_skill` does
`model.model_validate(raw).model_dump()`, which **silently drops any field not on the model**.
So adding a key in `skills.py` only is invisible at the API boundary even though calling the
builder directly in a REPL shows it. **Any new supply_chain field must be added to the pydantic
model in `models.py` too.** (Contrast with truly dynamic/AI-generated panels which have no model
and pass through untouched.)

**How to apply:** when extending any built-in panel's data shape, check `harness.DATA_MODELS` for
that panel_type; if a model exists, extend it or the field gets stripped before reaching the frontend.

## Drill-down recenter (click a node)
The supply-chain graph supports drilling into a node's own chain (NVDA → TSM → ASML).
`refine()` in `agent.py` has deterministic canonical-instruction shortcuts that bypass the
LLM entirely — same pattern as `risk_monitor`'s custom shock. The graph emits
`"Recenter supply chain on <SYM>"`, parsed by `_supply_chain_recenter_params` (regex), so a
node click never depends on AI latency/reliability. `keep_title` stays None so
`harness._derive_title` regenerates `{SYM} · Supply Chain`. Frontend trail/breadcrumb state
lives in `SupplyChainPanel` (survives because refine reuses the same panel id); the trail
truncates when navigating back to an existing crumb, appends on new drill-in.

**Why deterministic:** clicks must be instant + reliable; the LLM refine path is for free-text.
**How to apply:** to add another click-driven recompose, add a canonical-instruction shortcut
in `refine()` before the `_refine_params` fallback, not a new endpoint.
