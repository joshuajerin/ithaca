import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildBacktestCards, filterBacktestCards } from "./pages/Backtests";
import { unwrapBacktestResult } from "./lib/backtest";
import type { RunRow, StrategyRow } from "./types";

const srcDir = path.dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return fs.readFileSync(path.join(srcDir, rel), "utf8");
}

describe("backtest UI boundary", () => {
  it("keeps backtest creation and reruns out of the browser UI", () => {
    const text = [read("pages/Backtests.tsx"), read("pages/DeploymentDetail.tsx")].join("\n");

    expect(text).not.toContain("New backtest");
    expect(text).not.toContain("Create first backtest");
    expect(text).not.toContain("Run again");
    expect(text).not.toContain("api.createRun(");
    expect(text).not.toContain("api.proposeStrategy(");
    expect(text).toContain("through Doomberg MCP");
  });

  it("normalizes direct and nested backtest results", () => {
    const direct = { id: "r1", tenant_id: "t1", kind: "backtest", state: "completed", strategy_id: "s1", result: { stats: { sharpe: 1.2 } } } satisfies RunRow;
    const nested = { ...direct, id: "r2", result: { data: { stats: { sharpe: 2.4 } } } } satisfies RunRow;

    expect(unwrapBacktestResult(direct).stats).toEqual({ sharpe: 1.2 });
    expect(unwrapBacktestResult(nested).stats).toEqual({ sharpe: 2.4 });
    expect(unwrapBacktestResult(null)).toEqual({});
  });

  it("correlates runs by strategy and selects the newest run", () => {
    const strategies: StrategyRow[] = [
      { id: "s1", tenant_id: "t1", version: 1, name: "Momentum" },
      { id: "s2", tenant_id: "t1", version: 1, name: "Value" },
    ];
    const runs: RunRow[] = [
      { id: "old", tenant_id: "t1", kind: "backtest", state: "completed", strategy_id: "s1", updated_at: "2026-01-01" },
      { id: "new", tenant_id: "t1", kind: "backtest", state: "completed", strategy_id: "s1", updated_at: "2026-02-01" },
    ];

    const cards = buildBacktestCards(strategies, runs);
    expect(cards[0]).toMatchObject({ latestRun: { id: "new" }, runCount: 2 });
    expect(cards[1]).toMatchObject({ latestRun: null, runCount: 0 });
  });

  it("filters cards case-insensitively after trimming whitespace", () => {
    const cards = buildBacktestCards([
      { id: "s1", tenant_id: "t1", version: 1, name: "NVDA Momentum" },
      { id: "rate-cut", tenant_id: "t1", version: 1 },
    ], []);

    expect(filterBacktestCards(cards, "  momentum ").map(({ strategy }) => strategy.id)).toEqual(["s1"]);
    expect(filterBacktestCards(cards, "RATE").map(({ strategy }) => strategy.id)).toEqual(["rate-cut"]);
    expect(filterBacktestCards(cards, "")).toHaveLength(2);
  });
});
