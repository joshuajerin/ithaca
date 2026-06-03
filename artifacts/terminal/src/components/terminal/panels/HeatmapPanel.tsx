import React from "react";
import type { HeatmapData, HeatmapCell } from "@workspace/api-client-react";

export function HeatmapPanel({ data }: { data: HeatmapData }) {
  // Simple treemap layout approximation for a monochrome heatmap
  // Real treemaps are complex to calculate perfectly in CSS, 
  // so we'll use flex/wrap sizing based on market cap relative to total
  
  const totalCap = data.cells.reduce((sum, cell) => sum + cell.marketCap, 0);
  
  // Sort by market cap descending
  const sortedCells = [...data.cells].sort((a, b) => b.marketCap - a.marketCap);

  return (
    <div className="flex flex-col h-full">
      <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-2 shrink-0">
        {data.title}
      </div>
      
      <div className="flex-1 w-full flex flex-wrap content-start gap-1 min-h-0 overflow-y-auto">
        {sortedCells.map((cell) => {
          // Approximate area
          const pctOfTotal = cell.marketCap / totalCap;
          // Scale sizing logic somewhat arbitrarily for a good display
          const basis = Math.max(10, Math.min(100, Math.sqrt(pctOfTotal) * 150));
          
          // Color based on changePct - MONOCHROME RULES
          // Positive: White background, black text
          // Negative: Black background, gray border, gray text
          // Neutral: Gray background
          
          const isPositive = cell.changePct > 0;
          const isNegative = cell.changePct < 0;
          
          // The more positive, the brighter white
          // The more negative, the darker/more opaque gray
          const absChange = Math.abs(cell.changePct);
          const intensity = Math.min(1, absChange / 5); // cap at 5%
          
          let bgClass = "bg-transparent";
          let borderClass = "border border-border";
          let textClass = "text-white";
          
          if (isPositive) {
            bgClass = intensity > 0.6 ? "bg-white" : "bg-white/70";
            textClass = "text-black";
            borderClass = "border border-white";
          } else if (isNegative) {
            bgClass = intensity > 0.6 ? "bg-black" : "bg-[#111]";
            textClass = "text-muted-foreground";
            borderClass = "border border-[#333]";
          } else {
            bgClass = "bg-[#222]";
          }

          return (
            <div 
              key={cell.symbol}
              className={`flex flex-col items-center justify-center p-1 overflow-hidden hover:ring-1 hover:ring-white z-10 transition-all ${bgClass} ${borderClass} ${textClass}`}
              style={{
                flexBasis: `${basis}%`,
                flexGrow: pctOfTotal > 0.05 ? 1 : 0,
                minHeight: '60px'
              }}
              title={`${cell.name}: ${cell.changePct}%`}
            >
              <span className="font-bold text-sm tracking-tight">{cell.symbol}</span>
              <span className="text-[10px]">{cell.changePct > 0 ? '+' : ''}{cell.changePct}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
