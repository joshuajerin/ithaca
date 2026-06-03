import React from "react";
import type { DashboardSpec } from "@workspace/api-client-react/src/generated/api.schemas";
import { PanelContainer } from "./PanelContainer";

interface DashboardProps {
  dashboard: DashboardSpec;
  onPanelRefined: (updatedPanel: any) => void;
}

export function Dashboard({ dashboard, onPanelRefined }: DashboardProps) {
  if (!dashboard.panels || dashboard.panels.length === 0) {
    return (
      <div className="w-full h-full flex items-center justify-center border border-dashed border-border bg-black/50 text-muted-foreground uppercase text-xs tracking-widest p-4 text-center">
        No active panels. Enter a command to synthesize data.
      </div>
    );
  }

  // Row height is ~100px. We use CSS Grid where each unit of height represents roughly that.
  return (
    <div 
      className="grid gap-4 w-full"
      style={{
        gridTemplateColumns: "repeat(12, minmax(0, 1fr))",
        gridAutoRows: "120px"
      }}
    >
      {dashboard.panels.map((panel) => (
        <PanelContainer
          key={panel.id}
          panel={panel}
          sessionId={dashboard.sessionId}
          onRefined={onPanelRefined}
        />
      ))}
    </div>
  );
}
