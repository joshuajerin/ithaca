// @ts-nocheck
import React, { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AlertTriangle, Loader2, Search } from "lucide-react";

interface VintagePrint {
  vintage: string;
  value: number;
  change: number | null;
}

interface RevisionPeriod {
  period: string;
  prints: VintagePrint[];
  initial: number;
  current: number;
  totalRevision: number;
  vintageCount: number;
  revised: boolean;
}

interface SeriesMeta {
  title?: string | null;
  units?: string | null;
  unitsShort?: string | null;
  frequency?: string | null;
  seasonalAdjustment?: string | null;
  lastUpdated?: string | null;
  observationStart?: string | null;
  observationEnd?: string | null;
}

interface SeriesRevisionsData {
  title: string;
  seriesId: string;
  meta?: SeriesMeta;
  chart: Array<{ date: string; initial: number; current: number }>;
  periods: RevisionPeriod[];
  revisedPeriods?: number;
  totalPeriods?: number;
  note?: string;
}

interface Props {
  data: SeriesRevisionsData;
  source?: string | null;
  onRefine?: (params: Record<string, unknown>) => void;
  pending?: boolean;
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

function fmtPeriod(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

const RevTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-black border border-white/20 p-2 shadow-xl text-xs">
        <p className="text-muted-foreground mb-1">{label}</p>
        {payload.map((p: any) => (
          <p key={p.dataKey} style={{ color: p.color }} className="font-mono">
            {p.name}: {fmtNum(p.value)}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

export function SeriesRevisionsPanel({ data, source, onRefine, pending }: Props) {
  const [seriesInput, setSeriesInput] = useState(data?.seriesId ?? "");

  useEffect(() => {
    setSeriesInput(data?.seriesId ?? "");
  }, [data?.seriesId]);

  const unavailable = source === "unavailable" || !data?.chart?.length;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const id = seriesInput.trim().toUpperCase();
    if (id && onRefine && !pending) onRefine({ series_id: id });
  };

  // Most-revised recent period for the vintage timeline highlight.
  const focusPeriod = useMemo(() => {
    const periods = data?.periods ?? [];
    const revised = periods.filter((p) => p.revised && p.prints.length > 1);
    if (revised.length) return revised[0];
    return periods.find((p) => p.prints.length > 1) ?? periods[0] ?? null;
  }, [data?.periods]);

  const meta = data?.meta;
  const unit = meta?.unitsShort || meta?.units || "";

  return (
    <div className="flex flex-col h-full w-full">
      {/* Series id picker */}
      <form onSubmit={submit} className="shrink-0 flex items-center gap-2 mb-2">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
          <input
            value={seriesInput}
            onChange={(e) => setSeriesInput(e.target.value)}
            placeholder="FRED series id (e.g. GDPC1, PAYEMS, CPIAUCSL)"
            spellCheck={false}
            className="w-full bg-white/[0.03] border border-border pl-7 pr-2 py-1 text-xs font-mono text-white placeholder:text-muted-foreground/60 focus:outline-none focus:border-sky-500/50 uppercase"
          />
        </div>
        <button
          type="submit"
          disabled={pending}
          className="shrink-0 text-[10px] uppercase tracking-wider border border-border px-2.5 py-1.5 text-white hover:bg-white/[0.05] disabled:opacity-50 flex items-center gap-1"
        >
          {pending ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
          Load
        </button>
      </form>

      {unavailable ? (
        <div className="flex flex-col items-center justify-center flex-1 text-center px-6">
          <AlertTriangle className="w-6 h-6 text-yellow-400 mb-2" />
          <div className="text-sm text-white font-medium mb-1">
            No revision history
          </div>
          <div className="text-[11px] text-muted-foreground max-w-sm leading-snug">
            {data?.note ||
              "Live FRED/ALFRED vintage data is unavailable. No synthetic revisions are shown."}
          </div>
        </div>
      ) : (
        <>
          {/* Summary strip */}
          <div className="shrink-0 flex flex-wrap items-center gap-x-4 gap-y-1 mb-2 text-[10px] text-muted-foreground">
            <span className="text-white font-medium">{meta?.title || data.seriesId}</span>
            {unit && <span>· {unit}</span>}
            {meta?.frequency && <span>· {meta.frequency}</span>}
            {meta?.seasonalAdjustment && <span>· {meta.seasonalAdjustment}</span>}
            {typeof data.revisedPeriods === "number" && (
              <span className="text-amber-300">
                · {data.revisedPeriods}/{data.totalPeriods} periods revised
              </span>
            )}
          </div>

          {/* Current vs initial-print overlay */}
          <div className="h-[42%] min-h-0 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.chart} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 2" stroke="#333" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 9, fill: "#666" }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={36}
                  tickFormatter={(v) => (typeof v === "string" ? v.slice(0, 7) : v)}
                />
                <YAxis
                  domain={["auto", "auto"]}
                  tick={{ fontSize: 9, fill: "#666" }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${fmtNum(v)}`}
                />
                <Tooltip content={<RevTooltip />} />
                <Legend
                  wrapperStyle={{ fontSize: 9, paddingTop: 2 }}
                  iconType="plainline"
                />
                <Line
                  type="monotone"
                  dataKey="current"
                  name="Current (revised)"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="initial"
                  name="Initial print"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Vintage timeline for the focus period */}
          {focusPeriod && focusPeriod.prints.length > 1 && (
            <div className="shrink-0 mt-2 border border-border bg-white/[0.015] px-2.5 py-1.5">
              <div className="text-[9px] uppercase tracking-wider text-muted-foreground mb-1">
                Revision sequence · {fmtPeriod(focusPeriod.period)} ({focusPeriod.vintageCount} vintages)
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {focusPeriod.prints.map((pr, i) => {
                  const isInitial = i === 0;
                  const isCurrent = i === focusPeriod.prints.length - 1;
                  return (
                    <div
                      key={pr.vintage}
                      className={`flex flex-col items-center px-1.5 py-0.5 border ${
                        isCurrent
                          ? "border-sky-500/50 bg-sky-500/10"
                          : isInitial
                          ? "border-amber-500/50 bg-amber-500/10"
                          : "border-border"
                      }`}
                    >
                      <span className="text-[8px] text-muted-foreground font-mono">{pr.vintage}</span>
                      <span className="text-[11px] font-mono text-white font-semibold">
                        {fmtNum(pr.value)}
                      </span>
                      <span className="text-[8px] uppercase tracking-wide text-muted-foreground">
                        {isInitial ? "initial" : isCurrent ? "current" : pr.change !== null ? `${pr.change > 0 ? "+" : ""}${fmtNum(pr.change)}` : ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Per-period revision table */}
          <ScrollArea className="flex-1 min-h-0 mt-2">
            <table className="w-full text-xs border-collapse">
              <thead className="sticky top-0 bg-black z-10">
                <tr className="text-[9px] uppercase tracking-wider text-muted-foreground border-b border-border">
                  <th className="text-left font-medium py-1 pr-2">Period</th>
                  <th className="text-right font-medium py-1 px-2">Initial</th>
                  <th className="text-right font-medium py-1 px-2">Current</th>
                  <th className="text-right font-medium py-1 px-2">Revision</th>
                  <th className="text-right font-medium py-1 pl-2">Prints</th>
                </tr>
              </thead>
              <tbody>
                {data.periods.map((p) => {
                  const up = p.totalRevision > 0;
                  const dn = p.totalRevision < 0;
                  return (
                    <tr key={p.period} className="border-b border-border/40 hover:bg-white/[0.02]">
                      <td className="py-1 pr-2 font-mono text-white/90 whitespace-nowrap">
                        {fmtPeriod(p.period)}
                      </td>
                      <td className="text-right py-1 px-2 font-mono text-amber-300/90">
                        {fmtNum(p.initial)}
                      </td>
                      <td className="text-right py-1 px-2 font-mono text-sky-300">
                        {fmtNum(p.current)}
                      </td>
                      <td
                        className={`text-right py-1 px-2 font-mono ${
                          up ? "text-emerald-400" : dn ? "text-red-400" : "text-muted-foreground"
                        }`}
                      >
                        {p.revised ? `${up ? "+" : ""}${fmtNum(p.totalRevision)}` : "—"}
                      </td>
                      <td className="text-right py-1 pl-2 font-mono text-muted-foreground">
                        {p.vintageCount}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </ScrollArea>

          <div className="shrink-0 text-[8px] text-muted-foreground mt-1.5 uppercase tracking-widest">
            Source: FRED / ALFRED vintages · initial = first published · current = latest revision
          </div>
        </>
      )}
    </div>
  );
}
