import { describe, expect, it } from "vitest";
import {
  recentResearchSessions,
  shouldShowAdaptiveEmptyState,
  visibleAdaptiveWidgets,
  warningCounts,
} from "./pages/Dashboard";
import type { AdaptiveDashboardWidget, DashboardActivityData, DashboardRunView } from "./types";

function widget(id: string, priority: number): AdaptiveDashboardWidget {
  return {
    id,
    title: id,
    priority,
    layout: { x: priority, y: 0, w: 4, h: 3 },
    reason: "test",
  };
}

describe("adaptive dashboard frontend mapping", () => {
  it("filters unknown widget ids before rendering", () => {
    const visible = visibleAdaptiveWidgets([
      widget("performance_pnl", 2),
      widget("unknown_widget", 1),
    ], "");

    expect(visible.map((item) => item.id)).toEqual(["performance_pnl"]);
  });

  it("orders pending or ready widgets by priority", () => {
    const visible = visibleAdaptiveWidgets([
      widget("sentiment", 3),
      widget("performance_pnl", 1),
      widget("portfolio_risk", 2),
    ], "");

    expect(visible.map((item) => item.id)).toEqual([
      "performance_pnl",
      "portfolio_risk",
      "sentiment",
    ]);
  });

  it("applies dashboard search to adaptive widget titles", () => {
    const visible = visibleAdaptiveWidgets([
      { ...widget("recent_sessions", 1), title: "Recent Sessions" },
      { ...widget("yield_curve", 2), title: "Yield Curve" },
    ], "yield");

    expect(visible.map((item) => item.id)).toEqual(["yield_curve"]);
  });

  it("shows the empty state when the adaptive endpoint is stale", () => {
    expect(shouldShowAdaptiveEmptyState({
      adaptive: null,
      adaptiveError: "GET /dashboard/adaptive -> 404 Not Found",
    })).toBe(true);
  });

  it("does not infer personal dashboard history from tenant-wide sessions on adaptive failure", () => {
    expect(shouldShowAdaptiveEmptyState({
      adaptive: null,
      adaptiveError: "GET /dashboard/adaptive -> 404 Not Found",
    })).toBe(true);
  });

  it("uses only recorded research sessions for the recent-session widget", () => {
    const row = (run_id: string, kind: string): DashboardRunView => ({
      run_id,
      kind,
      state: "succeeded",
      strategy_id: null,
      created_at: "2026-07-12T00:00:00Z",
      updated_at: "2026-07-12T00:00:00Z",
    });

    expect(recentResearchSessions([
      row("backtest", "backtest"),
      row("research-1", "research"),
      row("research-2", "research"),
    ]).map((run) => run.run_id)).toEqual(["research-1", "research-2"]);
  });

  it("derives warning counts from real alerts and terminal run states", () => {
    const activity: DashboardActivityData = {
      runs: [
        { run_id: "failed", kind: "backtest", state: "failed", strategy_id: null, created_at: null, updated_at: null },
        { run_id: "ok", kind: "research", state: "succeeded", strategy_id: null, created_at: null, updated_at: null },
      ],
      triggers: [],
      alerts: [
        { notification_id: "alert-1", event_type: "run.warning", subject_type: "run", subject_id: "failed", priority: "high", state: "queued", payload: {}, created_at: null, updated_at: null },
      ],
    };

    expect(warningCounts(activity)).toEqual({ failed: 1, alerts: 1 });
  });
});
