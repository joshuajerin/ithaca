import { describe, expect, it } from "vitest";
import { performanceFromDashboard, riskFromDashboard } from "./data";
import type { DashboardRiskResponse, DashboardSummaryResponse } from "../types";

function envelope<T>(data: T): {
  status: "ready";
  as_of: string;
  source: string;
  entitlement_class: null;
  freshness_ms: number;
  data: T;
  error: null;
} {
  return {
    status: "ready",
    as_of: "2026-07-12T00:00:00Z",
    source: "doomberg-platform",
    entitlement_class: null,
    freshness_ms: 100,
    data,
    error: null,
  };
}

describe("truthful dashboard data adapters", () => {
  it("returns no performance panel without completed evidence", () => {
    const response = envelope({
      run_counts: { total: 0, active: 0, by_state: {} },
      latest_run: null,
      latest_backtest: null,
      latest_paper: null,
    }) satisfies DashboardSummaryResponse;

    expect(performanceFromDashboard(response)).toBeNull();
  });

  it("derives return and drawdown only from recorded equity points", () => {
    const response = envelope({
      run_counts: { total: 1, active: 0, by_state: { succeeded: 1 } },
      latest_run: null,
      latest_paper: null,
      latest_backtest: {
        run_id: "run-1",
        kind: "backtest",
        state: "succeeded",
        strategy_id: null,
        created_at: "2026-07-01T00:00:00Z",
        updated_at: "2026-07-03T00:00:00Z",
        equity_curve: [
          { d: "2026-07-01", v: 100 },
          { d: "2026-07-02", v: 110 },
          { d: "2026-07-03", v: 99 },
        ],
        stats: { sharpe: 1.25 },
      },
    }) satisfies DashboardSummaryResponse;

    const result = performanceFromDashboard(response);

    expect(result?.series.map(({ book, drawdown }) => ({ book, drawdown }))).toEqual([
      { book: 0, drawdown: 0 },
      { book: 10, drawdown: 0 },
      { book: -1, drawdown: -10 },
    ]);
    expect(result?.stats).toMatchObject({ totalReturn: -1, sharpe: 1.25, maxDD: -10 });
    expect(result?.stale).toBe(false);
    expect(result?.stats.cagr).toBeUndefined();
  });

  it("renders only recorded risk metrics and positions", () => {
    const response = envelope({
      backtest: { run_id: "run-1", metrics: { beta: 0.8, var95: 1.2 } },
      paper_exposure: {
        run_id: "paper-1",
        capital: 100_000,
        gross: 0.6,
        cash: 40_000,
        weights: { AAPL: 0.4, MSFT: -0.2 },
        updated_at: "2026-07-12T00:00:00Z",
      },
    }) satisfies DashboardRiskResponse;

    const result = riskFromDashboard(response);

    expect(result?.metrics).toEqual({ beta: 0.8, var95: 1.2 });
    expect(result?.holdings).toEqual([
      { symbol: "AAPL", weight: 0.4 },
      { symbol: "MSFT", weight: -0.2 },
    ]);
  });

  it("never creates a risk panel from an empty response", () => {
    const response: DashboardRiskResponse = {
      ...envelope({ backtest: null, paper_exposure: null }),
      status: "empty",
    };

    expect(riskFromDashboard(response)).toBeNull();
  });
});
