import { useState } from "react";
import { Dashboard as TerminalDashboard } from "../components/terminal/Dashboard";
import { sampleDashboard } from "../sampleDashboard";
import type { DashboardSpec, Panel } from "@workspace/api-client-react";

export function Dashboard() {
  const [terminalDashboard, setTerminalDashboard] = useState<DashboardSpec>(sampleDashboard);

  function updateTerminalPanel(updatedPanel: Panel) {
    setTerminalDashboard((current) => ({
      ...current,
      panels: current.panels.map((panel) => (panel.id === updatedPanel.id ? updatedPanel : panel)),
    }));
  }

  return (
    <div className="page live-dashboard-page">
      <div className="live-hero">
        <div className="page-title">Doomberg</div>
        <button className="btn" type="button" onClick={() => setTerminalDashboard(sampleDashboard)}>
          Refresh
        </button>
      </div>

      <section className="terminal-showcase" aria-label="Dashboard">
        <div className="terminal-canvas-shell">
          <div className="terminal-canvas-head">
            <div className="terminal-canvas-title">Markets</div>
          </div>
          <TerminalDashboard dashboard={terminalDashboard} onPanelRefined={updateTerminalPanel} />
        </div>
      </section>
    </div>
  );
}
