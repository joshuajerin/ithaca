# @ithaca/contracts

**Single source of truth** for every cross-service shape in Ithaca v2. Authored once as JSON Schema
(`schema/`), generated into pydantic (`py/`) and zod (`ts/`). Frozen in Phase 0 — services import these,
they never invent their own shapes.

Domains: `tenant` · `auth` · `provenance` · `events` (TraceEvent) · `strategy_spec` (StrategySpec).

- `schema/` — JSON Schema 2020-12, the source of truth. **Edit here.**
- `py/ithaca_contracts/generated/`, `ts/src/generated/` — GENERATED. Do not hand-edit.
- `fixtures/` — golden valid/invalid payloads, run by BOTH the pydantic and zod round-trip tests.
- `scripts/codegen.sh` — regenerate. `scripts/check_drift.sh` — the CI gate.

Workflow: edit a schema → `bash scripts/codegen.sh` → commit schema + regenerated code together.
