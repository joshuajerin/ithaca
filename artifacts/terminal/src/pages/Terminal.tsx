import React, { useState, useEffect } from "react";
import { useGetDefaultDashboard, useOrchestrate } from "@workspace/api-client-react";
import type { DashboardSpec } from "@workspace/api-client-react";
import { Dashboard } from "@/components/terminal/Dashboard";
import { ChatPanel } from "@/components/terminal/ChatPanel";
import { Loader2, ChevronLeft, ChevronRight } from "lucide-react";

export default function Terminal() {
  const [activeDashboard, setActiveDashboard] = useState<DashboardSpec | null>(null);
  const [chatOpen, setChatOpen] = useState(true);
  
  const { data: defaultDashboard, isLoading: isLoadingDefault } = useGetDefaultDashboard();
  
  useEffect(() => {
    if (defaultDashboard && !activeDashboard) {
      setActiveDashboard(defaultDashboard);
    }
  }, [defaultDashboard, activeDashboard]);

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

  if (isLoadingDefault) {
    return (
      <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin mb-5" strokeWidth={1.25} />
        <p className="editorial-label text-muted-foreground text-[10px]">Initializing Terminal</p>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full bg-black text-white overflow-hidden">
      <main className="flex-1 flex flex-col min-w-0 border-r border-border overflow-y-auto scrollbar-none">
        <div className="flex-1 px-8 py-7">
          {activeDashboard && (
            <Dashboard 
              dashboard={activeDashboard} 
              onPanelRefined={handlePanelRefined} 
            />
          )}
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
