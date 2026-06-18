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
  tenant_id: string;
  kind: "backtest" | "paper" | string;
  state: string;
  strategy_id: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  spec?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
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
