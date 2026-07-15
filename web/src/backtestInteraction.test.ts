import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const srcDir = path.dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return fs.readFileSync(path.join(srcDir, rel), "utf8");
}

describe("interactive backtest workspace contract", () => {
  it("keeps backtest creation out of the web app", () => {
    const backtests = read("pages/Backtests.tsx");
    const detail = read("pages/DeploymentDetail.tsx");

    expect(backtests).not.toContain("New backtest");
    expect(backtests).not.toContain("Create first backtest");
    expect(backtests).not.toContain("Run again");
    expect(backtests).not.toContain("api.proposeStrategy");
    expect(backtests).not.toContain("api.createRun");
    expect(detail).not.toContain("Run again");
    expect(detail).not.toContain("api.createRun");
    expect(backtests).toContain("buildStrategySpec");
  });
});
