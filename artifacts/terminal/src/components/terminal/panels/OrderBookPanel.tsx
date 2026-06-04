import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";

export function OrderBookPanel({ data }: { data: any }) {
  return (
    <div className="flex flex-col h-full gap-3">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest">
            {data.symbol} · Order Book
          </div>
          <div className="text-xl font-bold font-mono">${data.lastPrice.toFixed(2)}</div>
        </div>
        <div className="text-right">
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest">Spread</div>
          <div className="text-sm font-mono text-white">${data.spread.toFixed(2)}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 flex-1 min-h-0">
        <div className="flex flex-col min-h-0">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1 shrink-0">Bids</div>
          <div className="flex-1 min-h-0 overflow-hidden space-y-0.5">
            {data.bids.map((level: any, i: any) => (
              <div key={i} className="relative flex items-center justify-between px-1.5 py-0.5 text-[11px] font-mono overflow-hidden">
                <div
                  className="absolute inset-0 bg-white/8"
                  style={{ width: `${level.depth * 100}%` }}
                />
                <span className="relative z-10 text-white font-bold">${level.price.toFixed(2)}</span>
                <span className="relative z-10 text-muted-foreground">{level.size.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-col min-h-0">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1 shrink-0">Asks</div>
          <div className="flex-1 min-h-0 overflow-hidden space-y-0.5">
            {data.asks.map((level: any, i: any) => (
              <div key={i} className="relative flex items-center justify-between px-1.5 py-0.5 text-[11px] font-mono overflow-hidden">
                <div
                  className="absolute right-0 top-0 bottom-0 bg-white/5"
                  style={{ width: `${level.depth * 100}%` }}
                />
                <span className="relative z-10 text-muted-foreground">${level.price.toFixed(2)}</span>
                <span className="relative z-10 text-white/70">{level.size.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="shrink-0 border-t border-border pt-2">
        <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Recent Tape</div>
        <ScrollArea className="h-[80px]">
          <div className="space-y-0.5">
            {data.tape.map((print: any, i: any) => (
              <div key={i} className="flex items-center justify-between text-[10px] font-mono gap-2">
                <span className="text-muted-foreground w-16 shrink-0">{print.time}</span>
                <span className={`font-bold w-14 shrink-0 ${print.side === "buy" ? "text-white" : "text-gray-500"}`}>
                  ${print.price.toFixed(2)}
                </span>
                <span className="text-muted-foreground w-14 shrink-0 text-right">{print.size.toLocaleString()}</span>
                <span className={`w-10 shrink-0 text-right uppercase text-[9px] tracking-wider ${print.side === "buy" ? "text-white/60" : "text-gray-600"}`}>
                  {print.side}
                </span>
                <span className="text-muted-foreground/50 text-[9px] shrink-0">{print.venue}</span>
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
