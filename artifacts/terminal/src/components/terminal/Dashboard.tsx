import React from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { DashboardSpec } from "@workspace/api-client-react";
import { PanelContainer } from "./PanelContainer";

interface DashboardProps {
  dashboard: DashboardSpec;
  onPanelRefined: (updatedPanel: any) => void;
  highlightedPanelId?: string | null;
}

export function Dashboard({ dashboard, onPanelRefined, highlightedPanelId }: DashboardProps) {
  if (!dashboard.panels || dashboard.panels.length === 0) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center gap-2 py-24 text-center">
        <span className="font-serif text-xl text-muted-foreground">No active panels</span>
        <span className="editorial-label text-[9px] text-muted-foreground">Enter a command to synthesize data</span>
      </div>
    );
  }

  // Row height is ~100px. We use CSS Grid where each unit of height represents roughly that.
  return (
    <div 
      className="grid gap-6 w-full"
      style={{
        gridTemplateColumns: "repeat(12, minmax(0, 1fr))",
        gridAutoRows: "120px"
      }}
    >
      <AnimatePresence>
        {dashboard.panels.map((panel) => (
          <motion.div
            key={panel.id}
            initial={{ opacity: 0, y: 14, scale: 0.98, filter: "blur(2px)" }}
            animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 0.97, filter: "blur(2px)" }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            className="min-h-0"
            style={{
              gridColumnStart: panel.layout.x + 1,
              gridColumnEnd: `span ${panel.layout.w}`,
              gridRowStart: panel.layout.y + 1,
              gridRowEnd: `span ${panel.layout.h}`,
            }}
          >
            <PanelContainer
              panel={panel}
              sessionId={dashboard.sessionId}
              onRefined={onPanelRefined}
              highlighted={highlightedPanelId === panel.id}
            />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
