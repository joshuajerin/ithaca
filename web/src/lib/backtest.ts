import type { BacktestResult, RunRow } from "../types";

export function unwrapBacktestResult(run: RunRow | null): Partial<BacktestResult> {
  const result = (run?.result ?? {}) as Partial<BacktestResult> & { data?: Partial<BacktestResult> };
  return result.data ?? result;
}
