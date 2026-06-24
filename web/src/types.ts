import { z } from "zod";
import { TraceEvent as TraceEventSchema } from "@doomberg/contracts/generated";

// The wire event shape is the shared contract. We infer the TS type from the zod schema
// so the UI can never drift from doomberg_contracts.
export type TraceEvent = z.infer<typeof TraceEventSchema>;
export { TraceEventSchema };

export type TraceEventType = TraceEvent["type"];

// Run row as returned by GET /api/runs and GET /api/runs/{id}. The rest-gateway reads these
// from doomberg_platform.RunStore; the UI treats unknown fields permissively (display-only).
export interface RunRow {
  id: string;
  run_id?: string;
  tenant_id: string;
  kind: "backtest" | "paper" | "research" | string;
  state: string;
  strategy_id: string | null;
  job_id?: string | null;
  profile?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  spec?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
  jobs?: Array<Record<string, unknown>>;
  artifacts?: Array<Record<string, unknown>>;
  events?: TraceEvent[];
  trace?: Record<string, unknown> | null;
}

export interface SessionRow extends RunRow {
  prompt?: string | null;
  title?: string | null;
  agent?: string | null;
  last_event_at?: string | null;
  call_count?: number;
  warning_count?: number;
}

// Strategy row as returned by GET /api/strategies.
export interface StrategyRow {
  id: string;
  tenant_id: string;
  version: number;
  name?: string | null;
  spec?: Record<string, unknown> | null;
  created_at?: string | null;
}

export interface JobRow {
  tenant_id: string;
  job_id: string;
  run_id: string;
  kind: string;
  profile: string;
  state: string;
  attempts: number;
  worker_id?: string | null;
  lease_expires_at?: string | null;
  heartbeat_at?: string | null;
  checkpoint_ref?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ArtifactRow {
  tenant_id: string;
  artifact_id: string;
  run_id: string;
  job_id?: string | null;
  kind: string;
  uri: string;
  media_type?: string | null;
  bytes?: number | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
}

export interface ApprovalRow {
  tenant_id: string;
  approval_id: string;
  run_id: string;
  kind: string;
  state: string;
  request: Record<string, unknown>;
  decision?: Record<string, unknown> | null;
  requested_by?: string | null;
  decided_by?: string | null;
  expires_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProviderConnectionRow {
  tenant_id: string;
  connection_id: string;
  provider: string;
  state: string;
  account_ref?: string | null;
  capabilities: string[];
  entitlements: Array<Record<string, unknown>>;
  retention_policy?: string | null;
  credential_configured?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DatasetSnapshotRow {
  tenant_id: string;
  snapshot_id: string;
  provider: string;
  dataset: string;
  entitlement_class: string;
  as_of: string;
  uri?: string | null;
  manifest: Record<string, unknown>;
  created_at?: string | null;
}

export interface OrderIntentRow {
  tenant_id: string;
  intent_id: string;
  run_id: string;
  strategy_id?: string | null;
  account_ref?: string | null;
  state: string;
  payload: Record<string, unknown>;
  risk_decision?: Record<string, unknown> | null;
  idempotency_key?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface OrderRow {
  tenant_id: string;
  order_id: string;
  intent_id: string;
  broker: string;
  client_order_id: string;
  broker_order_id?: string | null;
  state: string;
  payload: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface FillRow {
  tenant_id: string;
  fill_id: string;
  order_id: string;
  broker_fill_id?: string | null;
  payload: Record<string, unknown>;
  event_time: string;
  created_at?: string | null;
}

export interface OrderIntentRecord extends OrderIntentRow {
  orders?: OrderRow[];
  fills?: FillRow[];
}

export interface TriggerRow {
  tenant_id: string;
  trigger_id: string;
  name: string;
  state: string;
  policy: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TriggerDryRunResult {
  dry_run: true;
  would_fire: boolean;
  reason: string;
  trigger_id?: string | null;
  tenant_id?: string | null;
  dedupe_key?: string | null;
  quote_mode?: string | null;
  would_create?: {
    run: boolean;
    job: boolean;
    approval: boolean;
    broker_order: boolean;
  };
  action?: Record<string, unknown>;
  context?: Record<string, unknown>;
}

export interface OpsReadinessRow {
  name: string;
  state: "succeeded" | "warn" | "paused" | "failed" | string;
  detail: string;
}

export interface OpsStatus {
  platform: {
    database: string;
    archive_configured: boolean;
    mcp_allowed_hosts?: string;
  };
  ibkr: {
    engine_configured: boolean;
    engine_host?: string | null;
    quote_path: string;
    order_path: string;
    connected_quote_provider: boolean;
    connected_execution_provider: boolean;
  };
  execution: {
    paper_enabled: boolean;
    live_enabled: boolean;
    max_notional_usd: string;
    max_quantity: string;
    max_freshness_ms: string;
  };
  providers: {
    connections: number;
    connected: number;
    entitlement_records: number;
    dataset_snapshots: number;
  };
  jobs: {
    queued: number;
    leased_or_running: number;
    terminal: number;
  };
  leases: Array<{
    lease_name: string;
    owner_id: string;
    lease_expires_at: string;
    heartbeat_at: string;
    metadata: Record<string, unknown>;
    version: number;
    created_at: string;
    updated_at: string;
  }>;
  triggers: {
    active: number;
    total: number;
  };
  readiness: OpsReadinessRow[];
}

export interface IbkrSmokeInvariant {
  name: string;
  ok: boolean;
  detail: string;
  enforced?: boolean;
  max_freshness_ms?: number;
}

export interface IbkrSmokeStatus {
  configured: boolean;
  ok: boolean;
  status: string;
  code: string;
  host?: string | null;
  quote_path: string;
  symbol: string;
  latency_ms?: number | null;
  error?: string;
  recovery_action?: string;
  quote?: {
    symbol: string;
    price: number;
    last?: number;
    bid?: number | null;
    ask?: number | null;
    source: string;
    source_account?: string | null;
    entitlement_class?: string | null;
    event_time: string;
    received_time: string;
    freshness_ms: number;
  } | null;
  invariants: IbkrSmokeInvariant[];
}

// Backtest result `data` shape (from INTERFACES.md / doomberg_core).
export interface BacktestResult {
  equityCurve: { d: string; v: number }[];
  stats: Record<string, number>;
  finalWeights: Record<string, number>;
  risk: {
    ok: boolean;
    gross: number;
    net: number;
    maxName: number;
    violations: string[];
  };
  relaxed: boolean;
  bars: number;
  symbols: string[];
}
