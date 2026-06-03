import React, { useState } from "react";
import type { Panel } from "@workspace/api-client-react";
import { useRefinePanel } from "@workspace/api-client-react";
import { Loader2, Maximize2, Minimize2, MoreHorizontal, Settings2, AlertTriangle } from "lucide-react";
import { PriceChartPanel } from "./panels/PriceChartPanel";
import { NewsPanel } from "./panels/NewsPanel";
import { AnalysisPanel } from "./panels/AnalysisPanel";
import { FundamentalsPanel } from "./panels/FundamentalsPanel";
import { ScreenerPanel } from "./panels/ScreenerPanel";
import { HeatmapPanel } from "./panels/HeatmapPanel";
import { SentimentPanel } from "./panels/SentimentPanel";
import { ComparisonPanel } from "./panels/ComparisonPanel";

interface PanelContainerProps {
  panel: Panel;
  sessionId: string;
  onRefined: (updatedPanel: Panel) => void;
}

export function PanelContainer({ panel, sessionId, onRefined }: PanelContainerProps) {
  const [isRefining, setIsRefining] = useState(false);
  const [refineText, setRefineText] = useState("");
  
  const refineMutation = useRefinePanel();

  const handleRefine = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!refineText.trim()) {
      setIsRefining(false);
      return;
    }
    
    try {
      const result = await refineMutation.mutateAsync({
        data: {
          sessionId,
          panelId: panel.id,
          instruction: refineText
        }
      });
      onRefined(result);
      setIsRefining(false);
      setRefineText("");
    } catch (e) {
      console.error("Failed to refine panel", e);
    }
  };

  const renderContent = () => {
    if (panel.status === "loading" || refineMutation.isPending) {
      return (
        <div className="w-full h-full flex flex-col items-center justify-center text-muted-foreground gap-3">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span className="text-[10px] tracking-widest uppercase animate-pulse">Processing...</span>
        </div>
      );
    }

    if (panel.status === "error" || !panel.data) {
      return (
        <div className="w-full h-full flex flex-col items-center justify-center text-destructive gap-3 border border-destructive/20 bg-destructive/5 p-4 text-center">
          <AlertTriangle className="w-6 h-6" />
          <span className="text-[10px] tracking-widest uppercase">ERR: Data Acquisition Failed</span>
        </div>
      );
    }

    switch (panel.type) {
      case "price_chart": return <PriceChartPanel data={panel.data as any} />;
      case "news": return <NewsPanel data={panel.data as any} />;
      case "analysis": return <AnalysisPanel data={panel.data as any} />;
      case "fundamentals": return <FundamentalsPanel data={panel.data as any} />;
      case "screener": return <ScreenerPanel data={panel.data as any} />;
      case "heatmap": return <HeatmapPanel data={panel.data as any} />;
      case "sentiment": return <SentimentPanel data={panel.data as any} />;
      case "comparison": return <ComparisonPanel data={panel.data as any} />;
      default: return <div className="p-4 text-xs">Unknown panel type: {panel.type}</div>;
    }
  };

  return (
    <div
      className="bg-black border border-border flex flex-col overflow-hidden relative group"
      style={{
        gridColumnStart: panel.layout.x + 1,
        gridColumnEnd: `span ${panel.layout.w}`,
        gridRowStart: panel.layout.y + 1,
        gridRowEnd: `span ${panel.layout.h}`,
      }}
    >
      <div className="h-8 shrink-0 border-b border-border bg-[#050505] flex items-center justify-between px-3">
        <div className="flex items-center gap-2 overflow-hidden">
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground shrink-0">{panel.type.replace('_', ' ')}</span>
          <span className="text-xs font-bold uppercase truncate">{panel.title}</span>
        </div>
        <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <button 
            onClick={() => setIsRefining(!isRefining)}
            className="text-muted-foreground hover:text-white transition-colors"
          >
            <Settings2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {isRefining && (
        <form onSubmit={handleRefine} className="p-2 border-b border-border bg-muted/20">
          <input
            type="text"
            value={refineText}
            onChange={e => setRefineText(e.target.value)}
            placeholder="Refine this panel..."
            autoFocus
            className="w-full bg-black border border-border px-2 py-1 text-xs text-white focus:outline-none focus:border-white transition-colors"
          />
        </form>
      )}

      {panel.note && (
        <div className="bg-white text-black px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider shrink-0 border-b border-white">
          {panel.note}
        </div>
      )}

      <div className="flex-1 overflow-hidden p-3 relative">
        {renderContent()}
      </div>
    </div>
  );
}
