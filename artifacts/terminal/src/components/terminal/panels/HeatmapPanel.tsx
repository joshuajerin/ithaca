import type { HeatmapData } from "@workspace/api-client-react";

export function HeatmapPanel({ data }: { data: HeatmapData }) {
  // Sort by market cap descending for a stable "memory map" order
  const sortedCells = [...data.cells].sort((a, b) => b.marketCap - a.marketCap);

  // Deterministic hex byte from a numeric value (0x00–0xFF)
  const hex = (v: number) =>
    "0x" +
    (Math.abs(Math.round(v)) % 256).toString(16).toUpperCase().padStart(2, "0");

  return (
    <div className="flex flex-col h-full">
      <div className="editorial-label text-[9px] text-muted-foreground mb-3 shrink-0">
        {data.title}
      </div>

      <div className="flex-1 w-full min-h-0 overflow-y-auto font-mono text-[12px] leading-none border-t border-border">
        {sortedCells.map((cell, i) => {
          const isPositive = cell.changePct > 0;
          const isNegative = cell.changePct < 0;

          const b1 = hex(cell.marketCap / 1e9);
          const b2 = hex(cell.changePct * 41 + cell.symbol.charCodeAt(0));

          const indicator = isPositive ? "›" : isNegative ? "‹" : ":";

          return (
            <div
              key={cell.symbol}
              className="group flex items-stretch border-b border-border hover:bg-white/[0.06] transition-colors"
              title={`${cell.name} · ${cell.sector} · ${cell.changePct}%`}
            >
              {/* Row index */}
              <div className="w-9 shrink-0 flex items-center justify-end pr-2 py-3 text-muted-foreground/60 border-r border-border tabular-nums">
                {i.toString().padStart(2, "0")}
              </div>

              {/* Data column */}
              <div className="flex-1 min-w-0 flex items-center gap-3 px-3 py-3">
                <span className="text-white font-semibold tracking-wide w-12 shrink-0">
                  {cell.symbol}
                </span>
                <span className="text-muted-foreground/70 tracking-tight">
                  {b1} {b2}
                </span>
                <span
                  className={`tracking-tight ${
                    isPositive
                      ? "text-white/80"
                      : isNegative
                      ? "text-muted-foreground/50"
                      : "text-muted-foreground/60"
                  }`}
                >
                  [ACT]
                </span>
                <span
                  className={`ml-auto tabular-nums ${
                    isPositive
                      ? "text-white"
                      : isNegative
                      ? "text-muted-foreground"
                      : "text-muted-foreground/70"
                  }`}
                >
                  {cell.changePct > 0 ? "+" : ""}
                  {cell.changePct.toFixed(2)}%
                </span>
              </div>

              {/* Indicator column */}
              <div className="w-8 shrink-0 flex items-center justify-center py-3 text-muted-foreground/60 border-l border-border">
                {indicator}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
