import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Boxes, Info } from "lucide-react";

interface ExposureRow {
  etf: string;
  etfName: string;
  weight: number;
  asOf?: string | null;
}

interface ETFExposureData {
  title: string;
  symbol: string;
  stockName: string;
  rows: ExposureRow[];
  count: number;
  scannedCount: number;
  scanned?: string[];
  note?: string;
  source?: string;
  asOf?: string;
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(2)}%`;
}

export function ETFExposurePanel({ data }: { data: ETFExposureData }) {
  const rows = data.rows ?? [];
  const maxWeight = rows.length ? Math.max(...rows.map(r => r.weight)) : 1;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Boxes className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
          <span className="text-xs font-bold uppercase truncate">{data.title}</span>
        </div>
        <span className="text-[9px] text-muted-foreground uppercase tracking-wider shrink-0 ml-2">
          {data.count} of {data.scannedCount} scanned
        </span>
      </div>

      {data.stockName && data.stockName !== data.symbol && (
        <div className="text-[10px] text-muted-foreground mb-2 shrink-0 truncate">{data.stockName}</div>
      )}

      {rows.length === 0 ? (
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="text-xs text-muted-foreground text-center leading-relaxed">
            {data.note || `${data.symbol} is not in the top holdings of any scanned ETF.`}
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-[1.8fr_0.8fr] gap-2 px-2 pb-1 shrink-0 text-[9px] text-muted-foreground uppercase tracking-wider border-b border-border">
            <span>ETF</span>
            <span className="text-right">Weight</span>
          </div>
          <ScrollArea className="flex-1 min-h-0">
            <div className="flex flex-col">
              {rows.map(r => (
                <div
                  key={r.etf}
                  className="grid grid-cols-[1.8fr_0.8fr] gap-2 items-center px-2 py-1.5 border-b border-border/40 hover:bg-white/3 relative"
                >
                  <div className="min-w-0 relative">
                    <div
                      className="absolute inset-y-0 left-0 bg-emerald-400/10 pointer-events-none"
                      style={{ width: `${(r.weight / maxWeight) * 100}%` }}
                    />
                    <div className="relative">
                      <span className="text-[11px] font-bold uppercase">{r.etf}</span>
                      <div className="text-[9px] text-muted-foreground truncate">{r.etfName}</div>
                    </div>
                  </div>
                  <span className="text-right text-[11px] nums-tabular font-bold text-gray-100">{fmtPct(r.weight)}</span>
                </div>
              ))}
            </div>
          </ScrollArea>
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
