import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const srcDir = path.dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return fs.readFileSync(path.join(srcDir, rel), "utf8");
}

describe("interactive backtest workspace contract", () => {
  it("lets signed-in users create and rerun backtests from the web app", () => {
    const backtests = read("pages/Backtests.tsx");

    expect(backtests).toContain("New backtest");
    expect(backtests).toContain("Create first backtest");
    expect(backtests).toContain("Run again");
    expect(backtests).toContain("api.proposeStrategy");
    expect(backtests).toContain("api.createRun");
    expect(backtests).toContain("buildStrategySpec");
  });
});
