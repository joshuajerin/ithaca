import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { PieChart, Layers, Info } from "lucide-react";

interface HoldingRow {
  rank: number;
  symbol: string;
  name: string;
  weight: number;
}

interface SectorRow {
  sector: string;
  label: string;
  weight: number;
}

interface ETFHoldingsData {
  title: string;
  etf: string;
  etfName: string;
  rows: HoldingRow[];
  holdingsCount: number;
  coverage: number | null;
  top5: number | null;
  top10: number | null;
  sectorBreakdown: SectorRow[];
  note?: string;
  source?: string;
  asOf?: string;
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(2)}%`;
}

const SECTOR_COLORS = [
  "#60a5fa", "#34d399", "#fbbf24", "#f87171", "#a78bfa",
  "#22d3ee", "#fb923c", "#f472b6", "#4ade80", "#94a3b8", "#e879f9",
];

export function ETFHoldingsPanel({ data }: { data: ETFHoldingsData }) {
  const rows = data.rows ?? [];
  const sectors = data.sectorBreakdown ?? [];
  const maxWeight = rows.length ? Math.max(...rows.map(r => r.weight)) : 1;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <PieChart className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
          <span className="text-xs font-bold uppercase truncate">{data.title}</span>
        </div>
        <span className="text-[9px] text-muted-foreground uppercase tracking-wider shrink-0 ml-2">
          {data.etfName}
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="text-xs text-muted-foreground text-center leading-relaxed">
            {data.note || `No real holdings available for ${data.etf}.`}
          </div>
        </div>
      ) : (
        <>
          {/* Concentration stats */}
          <div className="grid grid-cols-3 gap-2 mb-2 shrink-0">
            <div className="border border-border bg-white/3 px-2 py-1.5">
              <div className="text-[8px] text-muted-foreground uppercase tracking-wider">Top 5</div>
              <div className="text-[13px] font-bold nums-tabular text-gray-100">{fmtPct(data.top5)}</div>
            </div>
            <div className="border border-border bg-white/3 px-2 py-1.5">
              <div className="text-[8px] text-muted-foreground uppercase tracking-wider">Top 10</div>
              <div className="text-[13px] font-bold nums-tabular text-gray-100">{fmtPct(data.top10)}</div>
            </div>
            <div className="border border-border bg-white/3 px-2 py-1.5">
              <div className="text-[8px] text-muted-foreground uppercase tracking-wider">Listed</div>
              <div className="text-[13px] font-bold nums-tabular text-gray-100">{fmtPct(data.coverage)}</div>
            </div>
          </div>

          {/* Holdings list */}
          <div className="grid grid-cols-[auto_1.6fr_0.8fr] gap-2 px-2 pb-1 shrink-0 text-[9px] text-muted-foreground uppercase tracking-wider border-b border-border">
            <span>#</span>
            <span>Holding</span>
            <span className="text-right">Weight</span>
          </div>
          <ScrollArea className="flex-1 min-h-0">
            <div className="flex flex-col">
              {rows.map(r => (
                <div
                  key={r.symbol + r.rank}
                  className="grid grid-cols-[auto_1.6fr_0.8fr] gap-2 items-center px-2 py-1.5 border-b border-border/40 hover:bg-white/3 relative"
                >
                  <span className="text-[10px] text-muted-foreground nums-tabular w-4">{r.rank}</span>
                  <div className="min-w-0 relative">
                    <div
                      className="absolute inset-y-0 left-0 bg-sky-400/10 pointer-events-none"
                      style={{ width: `${(r.weight / maxWeight) * 100}%` }}
                    />
                    <div className="relative">
                      <span className="text-[11px] font-bold uppercase">{r.symbol}</span>
                      <div className="text-[9px] text-muted-foreground truncate">{r.name}</div>
                    </div>
                  </div>
                  <span className="text-right text-[11px] nums-tabular font-bold text-gray-100">{fmtPct(r.weight)}</span>
                </div>
              ))}
            </div>
          </ScrollArea>

          {/* Sector breakdown */}
          {sectors.length > 0 && (
            <div className="shrink-0 mt-2 border-t border-border/40 pt-2">
              <div className="flex items-center gap-1.5 mb-1.5">
                <Layers className="w-2.5 h-2.5 text-muted-foreground" strokeWidth={1.8} />
                <span className="text-[9px] text-muted-foreground uppercase tracking-wider">Sector Breakdown</span>
              </div>
              <div className="flex w-full h-2 overflow-hidden rounded-sm mb-1.5">
                {sectors.map((s, i) => (
                  <div
                    key={s.sector}
                    title={`${s.label} ${fmtPct(s.weight)}`}
                    style={{ width: `${s.weight}%`, backgroundColor: SECTOR_COLORS[i % SECTOR_COLORS.length] }}
                  />
                ))}
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                {sectors.slice(0, 6).map((s, i) => (
                  <div key={s.sector} className="flex items-center justify-between text-[9px]">
                    <span className="flex items-center gap-1 min-w-0">
                      <span className="w-1.5 h-1.5 shrink-0" style={{ backgroundColor: SECTOR_COLORS[i % SECTOR_COLORS.length] }} />
                      <span className="text-gray-300 truncate">{s.label}</span>
                    </span>
                    <span className="nums-tabular text-muted-foreground shrink-0">{fmtPct(s.weight)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Footer / honesty note */}
      <div className="shrink-0 pt-1.5 mt-1 text-[9px] text-muted-foreground flex items-start gap-1.5 border-t border-border/40">
        <Info className="w-2.5 h-2.5 shrink-0 mt-0.5" strokeWidth={1.8} />
        <span className="leading-tight">
          {data.note}
          {data.asOf ? ` · as of ${data.asOf}` : ""}
          {data.source === "live" ? " · live" : ""}
        </span>
      </div>
    </div>
  );
}
