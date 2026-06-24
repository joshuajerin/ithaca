# services

Thin deployables over `doomberg-core`. All Python.

- `mcp-gateway/`   — primary product surface; MCP tools the BYO agent calls. Token→principal, per-call deadline, one trace event per call. Agent may read + `propose_strategy` only (never promote).
- `rest-gateway/`  — feeds the web UI (REST reads + SSE fan-out + human control actions: accept/promote/pause/halt).
- `control-plane/` — immutable versioned specs, run state machine, scheduling onto DO, pre-trade compliance gate. SINGLE writer of the money path (worker proposes a delta; this applies it under SELECT … FOR UPDATE).
- `runtime/`       — DO workers and operators: `backtest_runner`, `live_runner`, and `trigger_engine`. The trigger engine polls active policies, reads connected-account market data through the IBKR VPS engine, and creates durable runs; it never submits broker orders directly.
