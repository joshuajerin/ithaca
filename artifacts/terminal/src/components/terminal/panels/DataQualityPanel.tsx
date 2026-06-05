import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CheckCircle2, AlertTriangle, Clock, CircleDashed } from "lucide-react";

interface QualitySeries {
  symbol: string;
  name: string;
  interval: string;
  source: string;
  asOf?: string | null;
  status: "ok" | "warn" | "stale" | "mock";
  rows: number;
  gaps: number;
  duplicates: number;
  nanRows: number;
  zeroVolume: number;
  droppedRows: number;
  firstDate?: string | null;
  lastDate?: string | null;
  stale: boolean;
  staleSeconds?: number | null;
  issues: string[];
}

interface DataQualityData {
  title: string;
  series: QualitySeries[];
  summary: {
    seriesCount: number;
    okCount: number;
    issueCount: number;
    mockCount: number;
    asOf?: string | null;
  };
  source: string;
}

const STATUS: Record<string, { icon: React.ElementType; cls: string; label: string }> = {
  ok: { icon: CheckCircle2, cls: "text-emerald-400", label: "Clean" },
  warn: { icon: AlertTriangle, cls: "text-amber-400", label: "Issues" },
  stale: { icon: Clock, cls: "text-amber-400", label: "Stale" },
  mock: { icon: CircleDashed, cls: "text-muted-foreground/50", label: "Mock" },
};

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

function Cell({ n }: { n: number }) {
  return (
    <span className={`font-serif text-xs nums-tabular ${n > 0 ? "text-white" : "text-muted-foreground/40"}`}>
      {n > 0 ? n : "·"}
    </span>
  );
}

function freshness(asOf?: string | null): string {
  if (!asOf) return "—";
  const then = new Date(asOf).getTime();
  if (Number.isNaN(then)) return "—";
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

export function DataQualityPanel({ data }: { data: DataQualityData }) {
  const s = data.summary;
  return (
    <div className="flex flex-col h-full w-full">
      <div className="grid grid-cols-4 gap-4 shrink-0 pb-4">
        <Stat label="Series" value={s.seriesCount} accent />
        <Stat label="Clean" value={s.okCount} accent={s.okCount > 0} />
        <Stat label="Flagged" value={s.issueCount} accent={s.issueCount > 0} />
        <Stat label="Mock" value={s.mockCount} />
      </div>

      <ScrollArea className="flex-1 min-h-0 border-t border-border -mx-1">
        <Table>
          <TableHeader>
            <TableRow className="border-border hover:bg-transparent">
              <TableHead className="editorial-label text-[8px] h-7">Series</TableHead>
              <TableHead className="editorial-label text-[8px] h-7 text-center">Rows</TableHead>
              <TableHead className="editorial-label text-[8px] h-7 text-center">Gaps</TableHead>
              <TableHead className="editorial-label text-[8px] h-7 text-center">Dup</TableHead>
              <TableHead className="editorial-label text-[8px] h-7 text-center">NaN</TableHead>
              <TableHead className="editorial-label text-[8px] h-7 text-center">0-Vol</TableHead>
              <TableHead className="editorial-label text-[8px] h-7 text-center">Drop</TableHead>
              <TableHead className="editorial-label text-[8px] h-7 text-center">Source</TableHead>
              <TableHead className="editorial-label text-[8px] h-7 text-right">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.series.map((row) => {
              const st = STATUS[row.status] || STATUS.mock;
              const Icon = st.icon;
              return (
                <TableRow key={row.symbol} className="border-border/50 hover:bg-white/[0.02]">
                  <TableCell className="py-1.5">
                    <div className="font-serif text-sm">{row.symbol}</div>
                    <div className="editorial-label text-[7.5px] text-muted-foreground truncate max-w-[130px]">
                      {row.lastDate ? `to ${String(row.lastDate).slice(0, 10)}` : row.name}
                    </div>
                  </TableCell>
                  <TableCell className="py-1.5 text-center"><Cell n={row.rows} /></TableCell>
                  <TableCell className="py-1.5 text-center"><Cell n={row.gaps} /></TableCell>
                  <TableCell className="py-1.5 text-center"><Cell n={row.duplicates} /></TableCell>
                  <TableCell className="py-1.5 text-center"><Cell n={row.nanRows} /></TableCell>
                  <TableCell className="py-1.5 text-center"><Cell n={row.zeroVolume} /></TableCell>
                  <TableCell className="py-1.5 text-center"><Cell n={row.droppedRows} /></TableCell>
                  <TableCell className="py-1.5">
                    <div
                      className="flex items-center justify-center gap-1"
                      title={row.asOf ? `As of ${new Date(row.asOf).toLocaleString()}` : "no timestamp"}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${row.source === "live" ? "bg-emerald-400" : "bg-muted-foreground/40"}`} />
                      <span className="editorial-label text-[8px] text-muted-foreground">
                        {row.source === "live" ? freshness(row.asOf) : row.source}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="py-1.5">
                    <div className={`flex items-center justify-end gap-1 ${st.cls}`}>
                      <Icon className="w-3 h-3" strokeWidth={1.75} />
                      <span className="editorial-label text-[8px]">{st.label}</span>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </ScrollArea>
    </div>
  );
}
