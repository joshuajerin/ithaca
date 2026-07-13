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
      read("pages/Settings.tsx"),
    ].join("\n");

    expect(text).toContain("Doomberg");
    expect(text).toContain("Doomberg MCP");
    expect(text).toContain("Doomberg user");
    expect(text).toContain("docs.doomberg.me");
    expect(text).not.toMatch(/>\s*Ithaca\s*</);
    expect(text).not.toContain("Ithaca MCP");
    expect(text).not.toContain("Ithaca user");
    expect(text).not.toContain("ithaca.mintlify.app");
  });

  it("does not ship the old sliding sessions detail pane", () => {
    expect(read("pages/SessionsList.tsx")).not.toContain("detail-pane");
    expect(read("index.css")).not.toContain(".detail-pane");
    expect(read("index.css")).toContain(".step-detail");
  });

  it("does not render the old operational left rail buttons", () => {
    const app = read("App.tsx");

    expect(app).toContain("navItems");
    expect(app).toContain("Dashboard");
    expect(app).toContain("Sessions");
    expect(app).toContain("Backtests");
    expect(app).not.toMatch(/\b(Runs|Orders|Approvals|Triggers|Artifacts|Providers|Trades|Docs)\b/);
    expect(app).not.toMatch(/path="\/(?:runs|runs\/:id|deploys|trades|docs)"/);
  });

  it("uses browser history routing without hash URLs", () => {
    const main = read("main.tsx");

    expect(main).toContain("BrowserRouter");
    expect(main).not.toContain("HashRouter");
  });

  it("loads and applies Pliant as the single product font", () => {
    const webHtml = read("../index.html");
    const webCss = read("index.css");
    const siteHtml = read("../../site/index.html");
    const siteCss = read("../../site/src/index.css");
    const text = [webHtml, webCss, siteHtml, siteCss].join("\n");

    expect(webHtml).toContain("fonts.googleapis.com/css2?family=Pliant");
    expect(siteHtml).toContain("fonts.googleapis.com/css2?family=Pliant");
    expect(text).toContain('"Pliant"');
    expect(text).not.toMatch(/DM\+Sans|DM Sans|JetBrains\+Mono|JetBrains Mono/);
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
