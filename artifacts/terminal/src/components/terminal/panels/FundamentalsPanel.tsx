import React from "react";
import type { FundamentalsData } from "@workspace/api-client-react/src/generated/api.schemas";
import { ScrollArea } from "@/components/ui/scroll-area";

export function FundamentalsPanel({ data }: { data: FundamentalsData }) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-baseline gap-2 mb-4 shrink-0">
        <span className="text-xl font-bold">{data.symbol}</span>
        <span className="text-xs text-muted-foreground uppercase">{data.name}</span>
      </div>

      <ScrollArea className="flex-1 pr-2">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          {data.metrics.map((metric, i) => (
            <div key={i} className="flex justify-between items-baseline gap-2 min-w-0 py-1.5 border-b border-border/50 group">
              <span className="text-xs text-muted-foreground uppercase tracking-wider truncate min-w-0 group-hover:text-gray-300 transition-colors" title={metric.hint || metric.label}>
                {metric.label}
              </span>
              <div className="flex items-center gap-1.5 shrink-0">
                <span className="text-sm font-bold font-mono text-right whitespace-nowrap">{metric.value}</span>
                {metric.change !== undefined && metric.change !== null && (
                  <span className={`text-[10px] ${metric.change >= 0 ? 'text-white' : 'text-muted-foreground'}`}>
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
