import React from "react";
import type { FundamentalsData } from "@workspace/api-client-react";
import { ScrollArea } from "@/components/ui/scroll-area";

export function FundamentalsPanel({ data }: { data: FundamentalsData }) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-baseline gap-3 mb-4 shrink-0">
        <span className="font-serif text-3xl leading-none">{data.symbol}</span>
        <span className="editorial-label text-[9px] text-muted-foreground truncate">{data.name}</span>
      </div>

      <ScrollArea className="flex-1 pr-2">
        <div className="grid grid-cols-2 gap-x-8 gap-y-0">
          {data.metrics.map((metric, i) => (
            <div key={i} className="flex justify-between items-baseline gap-2 min-w-0 py-2 border-b border-border group">
              <span className="editorial-label text-[8.5px] text-muted-foreground truncate min-w-0 group-hover:text-gray-300 transition-colors" title={metric.hint || metric.label}>
                {metric.label}
              </span>
              <div className="flex items-baseline gap-1.5 shrink-0">
                <span className="font-serif text-base nums-tabular text-right whitespace-nowrap">{metric.value}</span>
                {metric.change !== undefined && metric.change !== null && (
                  <span className={`font-serif text-xs nums-oldstyle ${metric.change >= 0 ? 'text-white' : 'text-muted-foreground'}`}>
                    {metric.change > 0 ? '+' : ''}{metric.change}%
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
