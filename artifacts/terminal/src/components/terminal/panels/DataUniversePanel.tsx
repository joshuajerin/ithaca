import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

interface UniverseRow {
  symbol: string;
  name: string;
  sector?: string | null;
  sectorName?: string | null;
  industry?: string | null;
  country?: string | null;
  exchange?: string | null;
  tracked: boolean;
  price?: number | null;
  marketCap?: number | null;
  source: string;
  asOf?: string | null;
}

interface SectorCoverage {
  id: string;
  name: string;
  count: number;
  liveCount: number;
}

interface UniverseSummary {
  totalSymbols: number;
  liveSymbols: number;
  mockSymbols: number;
  trackedSymbols: number;
  sectorCount: number;
  exchanges: string[];
  asOf?: string | null;
}

interface DataUniverseData {
  title: string;
  summary: UniverseSummary;
  sectors: SectorCoverage[];
  rows: UniverseRow[];
  rowsShown: number;
  source: string;
}

function fmtCap(v?: number | null): string {
  if (v == null) return "—";
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(0)}M`;
  return v.toFixed(0);
}

function Stat({ label, value, accent }: { label: string; value: string | number; accent?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="editorial-label text-[8px] text-muted-foreground">{label}</span>
      <span className={`font-serif text-2xl leading-none nums-oldstyle ${accent ? "text-white" : "text-muted-foreground"}`}>
        {value}
      </span>
    </div>
  );
}

function SourceTag({ source }: { source: string }) {
  const live = source === "live";
  return (
    <span className="flex items-center gap-1 editorial-label text-[8px] text-muted-foreground">
      <span className={`w-1.5 h-1.5 rounded-full ${live ? "bg-emerald-400" : "bg-muted-foreground/40"}`} />
      {live ? "live" : "mock"}
    </span>
  );
}

export function DataUniversePanel({ data }: { data: DataUniverseData }) {
  const s = data.summary;
  const livePct = s.totalSymbols ? Math.round((s.liveSymbols / s.totalSymbols) * 100) : 0;
  const topSectors = data.sectors.slice(0, 6);
  const maxCount = topSectors.reduce((m, x) => Math.max(m, x.count), 1);

  return (
    <div className="flex flex-col h-full w-full">
      <div className="grid grid-cols-4 gap-4 shrink-0 pb-4">
        <Stat label="Symbols" value={s.totalSymbols} accent />
        <Stat label="Live" value={`${s.liveSymbols} · ${livePct}%`} accent={s.liveSymbols > 0} />
        <Stat label="Tracked" value={s.trackedSymbols} />
        <Stat label="Sectors" value={s.sectorCount} />
      </div>

      {topSectors.length > 0 && (
        <div className="shrink-0 border-t border-border pt-3 pb-3 space-y-1.5">
          {topSectors.map((sec) => (
            <div key={sec.id} className="flex items-center gap-2">
              <span className="editorial-label text-[8px] text-muted-foreground w-28 truncate shrink-0">{sec.name}</span>
              <div className="flex-1 h-2 bg-muted/10 relative overflow-hidden">
                <div className="absolute inset-y-0 left-0 bg-white/15" style={{ width: `${(sec.count / maxCount) * 100}%` }} />
                <div className="absolute inset-y-0 left-0 bg-emerald-400/50" style={{ width: `${(sec.liveCount / maxCount) * 100}%` }} />
              </div>
              <span className="font-serif text-xs nums-tabular w-8 text-right shrink-0">{sec.count}</span>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between border-t border-border pt-2 pb-1 shrink-0">
        <span className="editorial-label text-[8px] text-muted-foreground">
          Showing {data.rowsShown} of {s.totalSymbols}
        </span>
        {s.exchanges.length > 0 && (
          <span className="editorial-label text-[8px] text-muted-foreground truncate ml-3">
            {s.exchanges.join(" · ")}
          </span>
        )}
      </div>

      <ScrollArea className="flex-1 min-h-0 -mx-1">
        <Table>
          <TableHeader>
            <TableRow className="border-border hover:bg-transparent">
              <TableHead className="editorial-label text-[8px] h-7">Symbol</TableHead>
              <TableHead className="editorial-label text-[8px] h-7">Sector / Industry</TableHead>
              <TableHead className="editorial-label text-[8px] h-7">Venue</TableHead>
              <TableHead className="editorial-label text-[8px] h-7 text-right">Mkt Cap</TableHead>
              <TableHead className="editorial-label text-[8px] h-7 text-right">Source</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.rows.map((r) => (
              <TableRow key={r.symbol} className="border-border/50 hover:bg-white/[0.02]">
                <TableCell className="py-1.5">
                  <div className="flex items-center gap-1.5">
                    <span className="font-serif text-sm">{r.symbol}</span>
                    {r.tracked && <span className="w-1 h-1 rounded-full bg-white/60" title="Tracked live" />}
                  </div>
                  <div className="editorial-label text-[7.5px] text-muted-foreground truncate max-w-[120px]">{r.name}</div>
                </TableCell>
                <TableCell className="py-1.5">
                  <div className="text-xs text-muted-foreground">{r.sectorName || "—"}</div>
                  <div className="editorial-label text-[7.5px] text-muted-foreground/70 truncate max-w-[140px]">{r.industry || ""}</div>
                </TableCell>
                <TableCell className="py-1.5 editorial-label text-[8px] text-muted-foreground">
                  {r.exchange || "—"}
                </TableCell>
                <TableCell className="py-1.5 text-right font-serif text-xs nums-tabular">{fmtCap(r.marketCap)}</TableCell>
                <TableCell className="py-1.5">
                  <div className="flex justify-end">
                    <SourceTag source={r.source} />
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ScrollArea>
    </div>
  );
}
