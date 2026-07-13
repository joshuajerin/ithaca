import { describe, expect, it } from "vitest";
import {
  recentResearchSessions,
  resolveAdaptiveDashboardState,
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

  it("waits for both session and adaptive state before choosing a dashboard", () => {
    expect(resolveAdaptiveDashboardState({
      adaptive: null,
      adaptiveError: null,
      adaptiveLoading: true,
      runs: null,
      runsError: null,
      runsLoading: true,
    })).toBe("loading");
  });

  it("never shows onboarding when a research session already exists", () => {
    expect(resolveAdaptiveDashboardState({
      adaptive: null,
      adaptiveError: "GET /dashboard/adaptive -> 401 Unauthorized",
      adaptiveLoading: false,
      runs: [{
        id: "session-1",
        tenant_id: "tenant-1",
        kind: "research",
        state: "running",
        strategy_id: null,
      }],
      runsError: null,
      runsLoading: false,
    })).toBe("fallback");
  });

  it("renders a ready adaptive dashboard after both requests resolve", () => {
    expect(resolveAdaptiveDashboardState({
      adaptive: {
        status: "ready",
        spec: { summary: "Ready", widgets: [] },
        model: "test-model",
        source_session_count: 1,
        source_event_count: 1,
        generated_for_date: "2026-07-12",
        created_at: "2026-07-12T00:00:00Z",
        updated_at: "2026-07-12T00:00:00Z",
      },
      adaptiveError: null,
      adaptiveLoading: false,
      runs: [],
      runsError: null,
      runsLoading: false,
    })).toBe("adaptive");
  });

  it("shows onboarding only after both requests resolve with no research history", () => {
    expect(resolveAdaptiveDashboardState({
      adaptive: { status: "empty" },
      adaptiveError: null,
      adaptiveLoading: false,
      runs: [],
      runsError: null,
      runsLoading: false,
    })).toBe("empty");
  });

  it("does not misclassify an unknown double-error state as a new user", () => {
    expect(resolveAdaptiveDashboardState({
      adaptive: null,
      adaptiveError: "GET /dashboard/adaptive -> 401 Unauthorized",
      adaptiveLoading: false,
      runs: null,
      runsError: "GET /runs -> 401 Unauthorized",
      runsLoading: false,
    })).toBe("fallback");
  });

  it("uses onboarding when adaptive loading fails but runs resolve empty", () => {
    expect(resolveAdaptiveDashboardState({
      adaptive: null,
      adaptiveError: "temporary failure",
      adaptiveLoading: false,
      runs: [],
      runsError: null,
      runsLoading: false,
    })).toBe("empty");
  });

  it("falls back when resolved responses do not establish another state", () => {
    expect(resolveAdaptiveDashboardState({
      adaptive: null,
      adaptiveError: null,
      adaptiveLoading: false,
      runs: [],
      runsError: null,
      runsLoading: false,
    })).toBe("fallback");
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
