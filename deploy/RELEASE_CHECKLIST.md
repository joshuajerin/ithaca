# Production release checklist

This is the release decision record for Doomberg. Complete it against the exact
image digest being promoted; a green source checkout is not release evidence.

## Before rollout

- Record the image digest, git SHA, deploy environment, operator, and UTC start time.
- Confirm the stacked PR chain is merged in order and every required remote check is green.
- Confirm the production migration job uses the same image digest as the gateways and workers.
- Confirm `DOOMBERG_DB_MIGRATION_MODE=validate` on long-running services; only the one-shot
  `platform-migrate` role may apply schema changes.
- Read the current global and tenant execution kill switches. A release must preserve an
  active halt; it must never clear one as a side effect.
- Confirm the IBKR engine requirement for this release. If customer live data is in scope,
  `LAUNCH_GATE_REQUIRE_IBKR=1` is mandatory. Live order submission remains separately gated.

## Automated release gate

Run from the released image after the rollout:

```bash
python scripts/launch_gate.py \
  --mode http \
  --base-url "${DOOMBERG_REST_URL}" \
  --mcp-url "${DOOMBERG_MCP_URL}" \
  --require-postgres \
  --require-workers-ready \
  --require-mcp \
  --require-ibkr \
  --json | tee "launch-gate-${IMAGE_DIGEST#sha256:}.json"
```

Pass only when the JSON has `ok: true`. In particular, retain evidence for:

- gateway liveness, health, and readiness;
- a current migration ledger with no pending versions;
- current non-degraded heartbeats for every required worker role;
- personalized compliance policy and execution-stop state reads;
- invalid-auth and insufficient-scope rejection;
- durable REST/MCP run creation, observation, cancellation, and cleanup;
- artifact bundle integrity, SSE replay, live trigger lineage, and required IBKR data health.

## Rollout observation

- Watch deployment availability, restart count, Postgres pool waiting requests, worker
  heartbeat expiry, queued-job growth, and reconciliation failures for at least one full
  paper interval plus two worker heartbeat TTLs.
- Re-run the launch gate after any pod replacement or configuration correction.
- Do not use a synthetic provider response to satisfy a release that claims live IBKR data.

## Rollback boundary

Schema releases are roll-forward by default. The migration validator deliberately rejects
database versions unknown to an older image, so do not roll gateways or workers back across
a completed migration without an explicit database compatibility procedure. Keep the
execution kill switch engaged while recovering. Prefer a corrected image that understands
the current schema; never delete migration-ledger rows or drop tables during an incident.

## Handoff record

Attach the launch-gate JSON, image digest, git SHA, deployment run URL, migration version,
worker-role summary, IBKR health result, kill-switch state, operator, UTC completion time,
and any accepted warnings to the release record.
