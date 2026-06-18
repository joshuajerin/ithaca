# doomberg-core

The ONE shared Python core, imported (never re-ported) by the MCP gateway, REST gateway, and DO workers.
This guarantees `backtest math ≡ paper math`. No I/O in `engine/`; **no agent code anywhere**.

- `engine/`     — pure numpy quant, ported from v1 `app/engine/` (fix-on-port: optimizer gross-L1 recheck, Carino linking, signal window alignment)
- `sources/`    — data adapters behind a resilience wrapper, ported from v1 `app/sources/` (+ `asOf`, + per-source `pit` flag)
- `registry/`   — declarative strategy primitives (the operator-DAG is post-launch)
- `graph/`      — the evaluator (one seam for primitives now, DAG later)
- `accounting/` — paperbook + execution + TCA (the money-path kernel)
- `risk/`       — post-projection gross-L1 attestation (THE runtime boundary)
- `gateway/`    — point-in-time data facade: asOf truncation, provenance, breakers
