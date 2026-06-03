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
      <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin mb-5" strokeWidth={1.25} />
        <p className="editorial-label text-muted-foreground text-[10px]">Initializing Terminal</p>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full bg-black text-white overflow-hidden">
      <main className="flex-1 flex flex-col min-w-0 border-r border-border overflow-y-auto">
        <header className="h-16 border-b border-border flex items-end justify-between px-8 pb-3 shrink-0 bg-black/70 backdrop-blur-sm z-10 sticky top-0">
          <div className="flex flex-col">
            <span className="font-serif text-2xl leading-none tracking-tight">Agentic&nbsp;Terminal</span>
            <span className="editorial-label text-[9px] text-muted-foreground mt-1.5">
              Synthetic Market Intelligence
            </span>
          </div>
          <div className="flex items-center gap-6">
            <div className="flex flex-col items-end">
              <span className="editorial-label text-[9px] text-muted-foreground">Session</span>
              <span className="font-serif text-sm nums-tabular mt-0.5">
                {activeDashboard?.sessionId ? activeDashboard.sessionId.slice(0, 8) : '—'}
              </span>
            </div>
            <div className="h-7 w-px bg-border" />
            <div className="flex flex-col items-end">
              <span className="editorial-label text-[9px] text-muted-foreground">Status</span>
              <span className="font-serif text-sm mt-0.5">
                {activeDashboard?.sessionId ? 'Live' : 'Ready'}
              </span>
            </div>
          </div>
        </header>
        
        <div className="flex-1 px-8 py-7">
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
