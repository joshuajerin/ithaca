import React, { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useOrchestrate } from "@workspace/api-client-react";
import type { DashboardSpec } from "@workspace/api-client-react";
import { Dashboard } from "@/components/terminal/Dashboard";
import { ChatPanel } from "@/components/terminal/ChatPanel";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { DotWaveCanvas } from "@/components/terminal/DotWaveCanvas";

export default function Terminal() {
  const [activeDashboard, setActiveDashboard] = useState<DashboardSpec | null>(null);
  const [chatOpen, setChatOpen] = useState(true);

  const orchestrate = useOrchestrate();

  const handleCommand = async (command: string) => {
    try {
      const result = await orchestrate.mutateAsync({
        data: {
          query: command,
          sessionId: activeDashboard?.sessionId || undefined
        }
      });
      setActiveDashboard(result);
    } catch (e) {
      console.error("Orchestration failed", e);
    }
  };

  const handlePanelRefined = (updatedPanel: any) => {
    setActiveDashboard(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        panels: prev.panels.map(p => p.id === updatedPanel.id ? updatedPanel : p)
      };
    });
  };

  const hasPanels = !!activeDashboard && activeDashboard.panels.length > 0;

  return (
    <div className="flex h-screen w-full bg-black text-white overflow-hidden">
      <main className="flex-1 flex flex-col min-w-0 border-r border-border overflow-y-auto scrollbar-none">
        <div className="flex-1 relative">
          <AnimatePresence mode="wait">
            {hasPanels ? (
              <motion.div
                key={`dashboard-${activeDashboard!.sessionId}`}
                initial={{ opacity: 0, y: 10, filter: "blur(3px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                exit={{ opacity: 0, y: -10, filter: "blur(3px)" }}
                transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
                className="px-8 py-7"
              >
                <Dashboard
                  dashboard={activeDashboard!}
                  onPanelRefined={handlePanelRefined}
                />
              </motion.div>
            ) : (
              <motion.div
                key="dotwave"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
                className="absolute inset-0"
              >
                <DotWaveCanvas />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>
      
      <div className="relative flex-shrink-0 flex">
        <button
          onClick={() => setChatOpen(o => !o)}
          className="absolute left-0 top-1/2 -translate-x-full -translate-y-1/2 z-20 h-12 w-5 flex items-center justify-center bg-black border border-border border-r-0 text-muted-foreground hover:text-white transition-colors"
          aria-label={chatOpen ? "Collapse chat panel" : "Expand chat panel"}
        >
          {chatOpen ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
        </button>

        <aside
          className="flex flex-col bg-black overflow-hidden border-l border-border transition-all duration-300 ease-in-out"
          style={{ width: chatOpen ? 400 : 0 }}
        >
          <div style={{ width: 400, minWidth: 400 }} className="flex flex-col h-full">
            <ChatPanel 
              sessionId={activeDashboard?.sessionId}
              onCommand={handleCommand}
              isProcessing={orchestrate.isPending}
              lastSummary={activeDashboard?.summary}
            />
          </div>
        </aside>
      </div>
    </div>
  );
}
