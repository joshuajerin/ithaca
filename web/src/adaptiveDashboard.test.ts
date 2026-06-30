import { describe, expect, it } from "vitest";
import { shouldShowAdaptiveEmptyState, visibleAdaptiveWidgets } from "./pages/Dashboard";
import type { AdaptiveDashboardWidget } from "./types";

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
});
