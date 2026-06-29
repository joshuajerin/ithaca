import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const srcDir = path.dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return fs.readFileSync(path.join(srcDir, rel), "utf8");
}

describe("customer-facing UI cleanup guards", () => {
  it("uses Doomberg product copy in auth and agent-link surfaces", () => {
    const text = [
      read("main.tsx"),
      read("pages/AuthPage.tsx"),
      read("pages/AgentLink.tsx"),
      read("auth/AuthContext.tsx"),
    ].join("\n");

    expect(text).toContain("Doomberg");
    expect(text).not.toMatch(/\bIthaca(?: MCP| user)?\b/);
  });

  it("does not ship the old sliding sessions detail pane", () => {
    expect(read("pages/SessionsList.tsx")).not.toContain("detail-pane");
    expect(read("index.css")).not.toContain(".detail-pane");
    expect(read("index.css")).toContain(".step-detail");
  });

  it("does not render the old operational left rail buttons", () => {
    const app = read("App.tsx");

    expect(app).not.toContain('className="rail"');
    expect(app).not.toContain("rail-nav");
    expect(app).not.toMatch(/\b(Runs|Orders|Approvals|Triggers|Artifacts|Providers|Trades)\b/);
  });

  it("shows reference labels instead of sample or mock badges on customer panels", () => {
    const text = [
      read("dashboard/panels/CongressTradesPanel.tsx"),
      read("components/terminal/panels/CongressTradesPanel.tsx"),
      read("components/terminal/panels/DataUniversePanel.tsx"),
      read("components/terminal/panels/DataQualityPanel.tsx"),
      read("components/terminal/panels/WalkForwardPanel.tsx"),
      read("components/terminal/panels/WalkForwardComparePanel.tsx"),
      read("components/terminal/panels/OptionsScreenerPanel.tsx"),
    ].join("\n");

    expect(text).toContain("reference");
    expect(text).not.toMatch(/>\s*sample\s*</i);
    expect(text).not.toMatch(/>\s*mock\s*</i);
    expect(text).not.toContain('label: "Mock"');
    expect(text).not.toContain('label="Mock"');
  });
});
