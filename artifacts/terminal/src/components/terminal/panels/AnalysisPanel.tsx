import React from "react";
import type { AnalysisData } from "@workspace/api-client-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ArrowUpRight, ArrowRight, ArrowDownRight } from "lucide-react";

export function AnalysisPanel({ data }: { data: AnalysisData }) {
  const getStanceDisplay = () => {
    switch (data.stance) {
      case 'bullish': return { icon: ArrowUpRight, color: 'text-white border-white bg-white/10' };
      case 'bearish': return { icon: ArrowDownRight, color: 'text-muted-foreground border-muted-foreground bg-muted/10' };
      default: return { icon: ArrowRight, color: 'text-gray-400 border-gray-600 bg-transparent' };
    }
  };

  const stance = getStanceDisplay();
  const StanceIcon = stance.icon;

  return (
    <div className="flex flex-col h-full relative">
      <div className="flex justify-between items-start mb-4 shrink-0 border-b border-border pb-4">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">
            {data.scope} Analysis
          </div>
          <h3 className="text-lg font-bold leading-tight">{data.headline}</h3>
        </div>
        
        <div className="flex flex-col items-end gap-1 ml-4 shrink-0">
          <div className={`flex items-center gap-1.5 px-2 py-1 border text-xs font-bold uppercase tracking-wider ${stance.color}`}>
            <StanceIcon className="w-3.5 h-3.5" />
            {data.stance}
          </div>
          <div className="text-[10px] text-muted-foreground">
            CONF: {(data.confidence * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      <ScrollArea className="flex-1 pr-2">
        <p className="text-sm text-gray-300 mb-4 leading-relaxed font-serif">
          {data.summary}
        </p>

        <div className="space-y-2">
          {data.bullets.map((bullet, i) => (
            <div key={i} className="flex items-start gap-2 text-sm">
              <span className="text-white mt-1.5 block w-1 h-1 shrink-0 bg-white rounded-full" />
              <span className="text-gray-400">{bullet}</span>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
