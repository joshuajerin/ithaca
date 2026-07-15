import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const appSource = readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "App.tsx"), "utf8");

describe("route-level code splitting", () => {
  it("loads authenticated pages through React.lazy boundaries", () => {
    for (const page of [
      "Dashboard",
      "SessionsList",
      "SessionDetail",
      "Backtests",
      "DeploymentDetail",
      "Settings",
      "AgentLink",
    ]) {
      expect(appSource).toContain(`const ${page} = lazy(`);
      expect(appSource).not.toContain(`import { ${page} } from \"./pages/${page}\"`);
    }
    expect(appSource).toContain("<Suspense fallback={<RouteLoading />}>");
  });

  it("keeps the authentication entry screen eager", () => {
    expect(appSource).toContain('import { AuthPage, isAgentLinkLocation } from "./pages/AuthPage"');
    expect(appSource).toContain("isAgentLinkLocation(location.pathname, location.hash)");
  });

  it("loads expensive dashboard panels only when evidence exists", () => {
    const dashboardSource = readFileSync(
      path.join(path.dirname(fileURLToPath(import.meta.url)), "pages", "Dashboard.tsx"),
      "utf8",
    );
    expect(dashboardSource).toContain('import("../dashboard/panels/PerformancePnlPanel")');
    expect(dashboardSource).toContain('import("../dashboard/panels/PortfolioRiskPanel")');
    expect(dashboardSource).toContain("<Suspense fallback={<PanelLoading />}>");
  });
});
