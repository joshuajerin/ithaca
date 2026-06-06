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
