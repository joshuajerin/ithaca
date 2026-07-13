import { describe, expect, it } from "vitest";
import { StrategySpec } from "@doomberg/contracts";
import { buildStrategySpec, normalizeSymbols, type BacktestBuilderState } from "./pages/Backtests";

const base: BacktestBuilderState = {
  name: "Momentum research",
  symbols: "AAPL, MSFT",
  primitive: "momentum",
  scheme: "rank_weight",
  range: "1y",
  lookback: 90,
  fast: 20,
  slow: 50,
  threshold: 1,
  top: 2,
  gross: 1,
  maxName: 0.5,
  costBps: 5,
  slippageBps: 2,
  rebalance: "monthly@close",
  seed: 42,
};

describe("backtest builder", () => {
  it("normalizes and deduplicates symbols", () => {
    expect(normalizeSymbols("aapl, MSFT aapl\nNVDA")).toEqual(["AAPL", "MSFT", "NVDA"]);
  });

  it("builds a contract-valid momentum StrategySpec", () => {
    const spec = StrategySpec.parse(buildStrategySpec(base));
    expect(spec.strategy).toEqual({ id: "momentum", params: { lookback: 90 } });
  });

  it("uses only the selected primitive parameters", () => {
    const spec = StrategySpec.parse(
      buildStrategySpec({ ...base, primitive: "ma_cross", fast: 10, slow: 40 }),
    );
    expect(spec.strategy.params).toEqual({ fast: 10, slow: 40 });
  });
});
