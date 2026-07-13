import { z } from "zod";

// Narrow runtime validation for the fields the browser renders. Do not import the full
// generated contract here; it pulls internal execution vocabulary into the customer bundle.
export const TraceEventSchema = z.object({
  seq: z.number(),
  ts: z.string(),
  type: z.string(),
  run_id: z.string().optional(),
  tenant_id: z.string().optional(),
  span_id: z.string().nullable().optional(),
  parent_span_id: z.string().nullable().optional(),
  actor: z.unknown().optional(),
  data: z.record(z.unknown()).default({}),
}).passthrough();

export type TraceEvent = z.infer<typeof TraceEventSchema>;
export type TraceEventType = TraceEvent["type"];

// Run row as returned by GET /api/runs and GET /api/runs/{id}. The rest-gateway reads these
// from doomberg_platform.RunStore; the UI treats unknown fields permissively (display-only).
export interface RunRow {
  id: string;
  run_id?: string;
  tenant_id: string;
  kind: "backtest" | "research" | string;
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

export interface OrderRow {
  tenant_id: string;
  order_id: string;
  intent_id: string;
  broker: string;
  broker_order_id?: string | null;
  client_order_id: string;
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
  event_time?: string | null;
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
  orders?: OrderRow[];
  fills?: FillRow[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProviderConnectionRow {
  tenant_id: string;
  connection_id: string;
  provider: string;
  state: string;
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
    mcp_allowed_hosts?: string;
  };
  live_data: {
    engine_configured: boolean;
    quote_path: string;
    connected_quote_provider: boolean;
  };
  execution: {
    paper_enabled: boolean;
    live_enabled: boolean;
    disabled?: boolean;
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

export interface LiveDataSmokeInvariant {
  name: string;
  ok: boolean;
  detail: string;
  enforced?: boolean;
  max_freshness_ms?: number;
}

export interface LiveDataSmokeStatus {
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
    entitlement_class?: string | null;
    event_time: string;
    received_time: string;
    freshness_ms: number;
  } | null;
  invariants: LiveDataSmokeInvariant[];
}

export type AdaptiveDashboardWidgetId =
  | "performance_pnl"
  | "portfolio_risk"
  | "trade_flow"
  | "order_book"
  | "congress_trades"
  | "yield_curve"
  | "sentiment"
  | "recent_sessions"
  | "tool_usage"
  | "warning_watch"
  | "live_data_status";

export interface AdaptiveDashboardWidget {
  id: AdaptiveDashboardWidgetId | string;
  title: string;
  priority: number;
  layout: { x: number; y: number; w: number; h: number };
  reason: string;
}

export interface AdaptiveDashboardSpec {
  summary: string;
  widgets: AdaptiveDashboardWidget[];
}

export type AdaptiveDashboardResponse =
  | { status: "empty" }
  | {
      status: "pending";
      spec: AdaptiveDashboardSpec;
      source_session_count: number;
      source_event_count: number;
    }
  | {
      status: "ready";
      spec: AdaptiveDashboardSpec;
      model: string;
      source_session_count: number;
      source_event_count: number;
      generated_for_date: string;
      created_at: string;
      updated_at: string;
    };

export type DashboardReadStatus = "ready" | "empty" | "stale" | "unavailable";

export interface DashboardReadEnvelope<T> {
  status: DashboardReadStatus;
  as_of: string | null;
  source: string;
  entitlement_class: string | null;
  freshness_ms: number | null;
  data: T;
  error: { code: string; message: string } | null;
}

export interface DashboardRunView {
  run_id: string | null;
  kind: string | null;
  state: string | null;
  strategy_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface DashboardBookView {
  run_id: string | null;
  capital: number | null;
  gross: number | null;
  cash: number | null;
  weights: Record<string, number>;
  updated_at: string | null;
}

export interface DashboardSummaryData {
  run_counts: { total: number; active: number; by_state: Record<string, number> };
  latest_run: DashboardRunView | null;
  latest_backtest: (DashboardRunView & {
    equity_curve: Array<{ d: string; v: number }>;
    stats: Record<string, number>;
  }) | null;
  latest_paper: (DashboardRunView & { book: DashboardBookView | null }) | null;
}

export interface DashboardRiskData {
  backtest: { run_id: string | null; metrics: Record<string, number> } | null;
  paper_exposure: DashboardBookView | null;
}

export type DashboardSummaryResponse = DashboardReadEnvelope<DashboardSummaryData>;
export type DashboardRiskResponse = DashboardReadEnvelope<DashboardRiskData>;

export interface DashboardTriggerView {
  trigger_id: string | null;
  name: string | null;
  state: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface DashboardAlertView {
  notification_id: string | null;
  event_type: string | null;
  subject_type: string | null;
  subject_id: string | null;
  priority: string | null;
  state: string | null;
  payload: Record<string, string | number | boolean>;
  created_at: string | null;
  updated_at: string | null;
}

export interface DashboardActivityData {
  runs: DashboardRunView[];
  triggers: DashboardTriggerView[];
  alerts: DashboardAlertView[];
}

export interface DashboardEntitlementView {
  dataset?: string | null;
  entitlement_class?: string | null;
  permitted_use?: string[];
  freshness_class?: string | null;
  as_of?: string | null;
}

export interface DashboardProviderConnectionView {
  connection_id: string | null;
  provider: string;
  state: string | null;
  capabilities: string[];
  entitlements: DashboardEntitlementView[];
  credential_configured: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface DashboardProviderStatusData {
  connections: DashboardProviderConnectionView[];
  counts: { total: number; connected: number };
  live_engine_configured: boolean;
}

export interface DashboardMarketData {
  snapshots: Array<{
    snapshot_id: string | null;
    provider: string;
    dataset: string | null;
    entitlement_class: string | null;
    as_of: string | null;
    created_at: string | null;
  }>;
  quote_providers: DashboardProviderConnectionView[];
}

export type DashboardActivityResponse = DashboardReadEnvelope<DashboardActivityData>;
export type DashboardProviderStatusResponse = DashboardReadEnvelope<DashboardProviderStatusData>;
export type DashboardMarketResponse = DashboardReadEnvelope<DashboardMarketData>;

// Backtest result `data` shape (from INTERFACES.md / doomberg_core).
export interface BacktestResult {
  equityCurve: { d: string; v: number }[];
  comparisonCurve?: { d: string; strategy: number; benchmark: number }[];
  stats: Record<string, number>;
  benchmark?: {
    name: string;
    label?: string;
    equityCurve: { d: string; v: number }[];
    stats: Record<string, number>;
  };
  comparison?: {
    benchmark: string;
    activeTotalReturnPct: number;
    trackingErrorPct: number;
    informationRatio: number;
    outperformed: boolean;
  };
  execution?: {
    cost_bps: number;
    slippage_bps: number;
    all_in_cost_bps: number;
    avg_daily_turnover: number;
    total_cost_pct: number;
  };
  integrity?: {
    noLookahead: boolean;
    decisionLagBars: number;
    signalUses: string;
    returnApplied: string;
    benchmark: string;
  };
  dataQuality?: {
    pointInTime: boolean;
    ohlcv: Record<string, {
      raw: number;
      clean: number;
      dropped: number;
      deduped: number;
      sorted: boolean;
      input_sorted: boolean;
    }>;
  };
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
