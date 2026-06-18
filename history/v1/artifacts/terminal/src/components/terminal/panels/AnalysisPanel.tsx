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
        <div className="min-w-0">
          <div className="editorial-label text-[9px] text-muted-foreground mb-2">
            {data.scope} Analysis
          </div>
          <h3 className="font-serif text-2xl leading-tight">{data.headline}</h3>
        </div>
        
        <div className="flex flex-col items-end gap-1.5 ml-4 shrink-0">
          <div className={`flex items-center gap-1.5 px-2 py-1 border editorial-label text-[9px] ${stance.color}`}>
            <StanceIcon className="w-3 h-3" strokeWidth={1.75} />
            {data.stance}
          </div>
          <div className="editorial-label text-[8.5px] text-muted-foreground">
            Conf <span className="nums-tabular">{(data.confidence * 100).toFixed(0)}%</span>
          </div>
        </div>
      </div>

      <ScrollArea className="flex-1 pr-2">
        <p className="font-serif text-base text-gray-200 mb-5 leading-relaxed first-letter:text-3xl first-letter:font-medium first-letter:mr-0.5 first-letter:float-left first-letter:leading-[0.85]">
          {data.summary}
        </p>

        <div className="flex flex-col">
          {data.bullets.map((bullet, i) => (
            <div key={i} className="flex items-start gap-3 font-serif text-sm border-t border-border py-2.5">
              <span className="editorial-label text-[8.5px] text-muted-foreground mt-1 nums-tabular shrink-0">{String(i + 1).padStart(2, '0')}</span>
              <span className="text-gray-300 leading-snug">{bullet}</span>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
