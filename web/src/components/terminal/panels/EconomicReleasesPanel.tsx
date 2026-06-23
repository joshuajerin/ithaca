// @ts-nocheck
import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { CalendarClock, AlertTriangle } from "lucide-react";

interface ReleaseRow {
  seriesId: string;
  name: string;
  short?: string | null;
  units?: string | null;
  frequency?: string | null;
  reported: number | null;
  reportedPeriod: string | null;
  prior: number | null;
  priorPeriod: string | null;
  change: number | null;
  lastUpdated?: string | null;
  nextRelease?: string | null;
}

interface EconomicReleasesData {
  title: string;
  rows: ReleaseRow[];
  note?: string;
  asOf?: string | null;
}

interface Props {
  data: EconomicReleasesData;
  source?: string | null;
}

function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  const digits = abs >= 1000 ? 0 : abs >= 100 ? 1 : 2;
  return v.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtPeriod(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00").getTime();
  if (Number.isNaN(d)) return null;
  return Math.round((d - Date.now()) / 86400000);
}

export function EconomicReleasesPanel({ data, source }: Props) {
  const rows = data?.rows ?? [];
  const unavailable = source === "unavailable" || rows.length === 0;

  if (unavailable) {
    return (
      <div className="flex flex-col items-center justify-center h-full w-full text-center px-6">
        <AlertTriangle className="w-6 h-6 text-yellow-400 mb-2" />
        <div className="text-sm text-white font-medium mb-1">
          Economic releases unavailable
        </div>
        <div className="text-[11px] text-muted-foreground max-w-sm leading-snug">
          {data?.note ||
            "Live FRED economic-release data is unavailable. No synthetic releases are shown."}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full w-full">
      <div className="shrink-0 flex items-center gap-2 mb-2 text-[10px] uppercase tracking-widest text-muted-foreground">
        <CalendarClock className="w-3.5 h-3.5 text-sky-300" />
        <span>Key US economic releases · reported vs prior · next scheduled</span>
      </div>

      <ScrollArea className="flex-1 min-h-0">
        <table className="w-full text-xs border-collapse">
          <thead className="sticky top-0 bg-black z-10">
            <tr className="text-[9px] uppercase tracking-wider text-muted-foreground border-b border-border">
              <th className="text-left font-medium py-1.5 pr-2">Indicator</th>
              <th className="text-right font-medium py-1.5 px-2">Period</th>
              <th className="text-right font-medium py-1.5 px-2">Reported</th>
              <th className="text-right font-medium py-1.5 px-2">Prior</th>
              <th className="text-right font-medium py-1.5 px-2">Change</th>
              <th className="text-right font-medium py-1.5 pl-2">Next release</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const up = r.change !== null && r.change > 0;
              const dn = r.change !== null && r.change < 0;
              const du = daysUntil(r.nextRelease);
              return (
                <tr
                  key={r.seriesId}
                  className="border-b border-border/40 hover:bg-white/[0.02]"
                >
                  <td className="py-1.5 pr-2">
                    <div className="text-white font-medium leading-tight">
                      {r.short || r.name}
                    </div>
                    <div className="text-[9px] text-muted-foreground font-mono leading-tight">
                      {r.seriesId}
                      {r.units ? ` · ${r.units}` : ""}
                      {r.frequency ? ` · ${r.frequency}` : ""}
                    </div>
                  </td>
                  <td className="text-right py-1.5 px-2 font-mono text-muted-foreground whitespace-nowrap">
                    {fmtPeriod(r.reportedPeriod)}
                  </td>
                  <td className="text-right py-1.5 px-2 font-mono text-white font-semibold">
                    {fmtNum(r.reported)}
                  </td>
                  <td className="text-right py-1.5 px-2 font-mono text-muted-foreground">
                    {fmtNum(r.prior)}
                  </td>
                  <td
                    className={`text-right py-1.5 px-2 font-mono ${
                      up ? "text-emerald-400" : dn ? "text-red-400" : "text-muted-foreground"
                    }`}
                  >
                    {r.change === null ? "—" : `${up ? "+" : ""}${fmtNum(r.change)}`}
                  </td>
                  <td className="text-right py-1.5 pl-2 whitespace-nowrap">
                    <div className="font-mono text-white/90">{fmtDate(r.nextRelease)}</div>
                    {du !== null && (
                      <div
                        className={`text-[9px] ${
                          du <= 0
                            ? "text-yellow-300"
                            : du <= 7
                            ? "text-sky-300"
                            : "text-muted-foreground"
                        }`}
                      >
                        {du <= 0 ? "due" : `in ${du}d`}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </ScrollArea>

      <div className="shrink-0 text-[8px] text-muted-foreground mt-1.5 uppercase tracking-widest">
        Source: U.S. Federal Reserve (FRED) · reported = latest published vintage
      </div>
    </div>
  );
}
