import React, { useState, useEffect } from "react";
import { useGetDefaultDashboard, useOrchestrate } from "@workspace/api-client-react";
import type { DashboardSpec } from "@workspace/api-client-react";
import { Dashboard } from "@/components/terminal/Dashboard";
import { ChatPanel } from "@/components/terminal/ChatPanel";
import { Loader2 } from "lucide-react";

export default function Terminal() {
  const [activeDashboard, setActiveDashboard] = useState<DashboardSpec | null>(null);
  
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
      <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center font-mono">
        <Loader2 className="w-6 h-6 animate-spin mb-4" />
        <p className="text-muted-foreground uppercase text-xs tracking-widest">Initializing Terminal...</p>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full bg-black text-white overflow-hidden font-mono">
      <main className="flex-1 flex flex-col min-w-0 border-r border-border overflow-y-auto">
        <header className="h-12 border-b border-border flex items-center px-4 shrink-0 bg-black/50 backdrop-blur-sm z-10 sticky top-0">
          <div className="flex items-center gap-4">
            <span className="font-bold tracking-widest text-sm uppercase">SYS.TERMINAL // 01</span>
            <div className="h-4 w-px bg-border" />
            <span className="text-xs text-muted-foreground uppercase">
              {activeDashboard?.sessionId ? `SESSION: ${activeDashboard.sessionId.slice(0, 8)}` : 'READY'}
            </span>
          </div>
        </header>
        
        <div className="flex-1 p-4">
          {activeDashboard && (
            <Dashboard 
              dashboard={activeDashboard} 
              onPanelRefined={handlePanelRefined} 
            />
          )}
        </div>
      </main>
      
      <aside className="w-[400px] flex-shrink-0 flex flex-col bg-black relative">
        <ChatPanel 
          sessionId={activeDashboard?.sessionId}
          onCommand={handleCommand}
          isProcessing={orchestrate.isPending}
          lastSummary={activeDashboard?.summary}
        />
      </aside>
    </div>
  );
}
