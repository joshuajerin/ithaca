import React, { useEffect, useMemo, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { CalendarClock, Sunrise, Moon, AlertTriangle } from "lucide-react";

export interface EarningsRow {
  symbol: string;
  name: string;
  sector: string;
  sectorName: string;
  reportDate: string;
  reportDateTime: string;
  timing: "bmo" | "amc";
  timingLabel: string;
  epsEstimate: number | null;
  quarter: string;
  daysUntil: number;
  hoursUntil: number;
  imminent: boolean;
  marketCap?: number | null;
}

interface EarningsCalendarData {
  title: string;
  rows: EarningsRow[];
  imminent: EarningsRow[];
  imminentCount: number;
  nextReport: EarningsRow | null;
  horizonDays: number;
  count: number;
  watchlistSize: number;
  scope: string;
  asOf?: string;
  source?: string;
}

// Live countdown from now to the report datetime. Returns null once elapsed.
export function formatEarningsCountdown(reportDateTime: string, now: number): string {
  const target = new Date(reportDateTime).getTime();
  let diff = Math.floor((target - now) / 1000);
  if (diff <= 0) return "reporting now";
  const days = Math.floor(diff / 86400);
  diff -= days * 86400;
  const hours = Math.floor(diff / 3600);
  diff -= hours * 3600;
  const mins = Math.floor(diff / 60);
  const secs = diff - mins * 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

function fmtDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function fmtEps(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return `${v < 0 ? "-" : ""}$${Math.abs(v).toFixed(2)}`;
}

export function EarningsCalendarPanel({ data }: { data: EarningsCalendarData }) {
  const [now, setNow] = useState(() => Date.now());
  const [filter, setFilter] = useState<"all" | "imminent">("all");

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const rows = useMemo(
    () => (filter === "imminent" ? data.rows.filter(r => r.imminent) : data.rows),
    [data.rows, filter],
  );

  const imminentCount = data.imminentCount ?? data.rows.filter(r => r.imminent).length;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <CalendarClock className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
          <span className="text-xs font-bold uppercase truncate">{data.title}</span>
        </div>
        <span className="text-[9px] text-muted-foreground uppercase tracking-wider shrink-0 ml-2">
          {data.count} · next {data.horizonDays}d
        </span>
      </div>

      {/* Imminent banner (within the panel) */}
      {imminentCount > 0 && (
        <div className="mb-2 shrink-0 flex items-center gap-2 border border-amber-400/50 bg-amber-400/10 px-2.5 py-1.5">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" strokeWidth={1.8} />
          <span className="text-[10px] text-amber-300 leading-tight">
            {imminentCount === 1
              ? `${data.imminent[0]?.symbol} reports within 24h`
              : `${imminentCount} companies report within 24h`}
            {" — "}
            {data.imminent.slice(0, 3).map((r, i) => (
              <span key={r.symbol}>
                {i > 0 && ", "}
                <span className="font-bold">{r.symbol}</span> {formatEarningsCountdown(r.reportDateTime, now)}
              </span>
            ))}
          </span>
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex gap-1 mb-2 shrink-0">
        {(["all", "imminent"] as const).map(t => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            disabled={t === "imminent" && imminentCount === 0}
            className={`text-[10px] uppercase tracking-widest px-2 py-0.5 border transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
              filter === t ? "border-white text-white bg-white/10" : "border-border text-muted-foreground hover:border-gray-500"
            }`}
          >
            {t === "imminent" ? `Within 24h${imminentCount ? ` (${imminentCount})` : ""}` : "Upcoming"}
          </button>
        ))}
      </div>

      {/* Column header */}
      <div className="grid grid-cols-[1.6fr_1.1fr_0.7fr_0.7fr_0.9fr] gap-2 px-2 pb-1 shrink-0 text-[9px] text-muted-foreground uppercase tracking-wider border-b border-border">
        <span>Company</span>
        <span>Report Date</span>
        <span className="text-center">When</span>
        <span className="text-right">EPS Est</span>
        <span className="text-right">Countdown</span>
      </div>

      {/* Rows */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="flex flex-col">
          {rows.length === 0 && (
            <div className="text-xs text-muted-foreground px-2 py-4">No scheduled reports in this window.</div>
          )}
          {rows.map(r => (
            <div
              key={r.symbol}
              className={`grid grid-cols-[1.6fr_1.1fr_0.7fr_0.7fr_0.9fr] gap-2 items-center px-2 py-1.5 border-b border-border/40 ${
                r.imminent ? "bg-amber-400/5" : "hover:bg-white/3"
              }`}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-bold uppercase">{r.symbol}</span>
                  {r.imminent && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0 animate-pulse" />}
                </div>
                <div className="text-[9px] text-muted-foreground truncate">{r.name}</div>
              </div>
              <div className="min-w-0">
                <div className="text-[10px] text-gray-200">{fmtDate(r.reportDate)}</div>
                <div className="text-[9px] text-muted-foreground">{r.quarter}</div>
              </div>
              <div className="flex justify-center" title={r.timingLabel}>
                {r.timing === "bmo" ? (
                  <span className="flex items-center gap-1 text-[9px] text-sky-300 border border-sky-400/30 bg-sky-400/5 px-1 py-0.5 uppercase">
                    <Sunrise className="w-2.5 h-2.5" strokeWidth={1.8} /> BMO
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-[9px] text-indigo-300 border border-indigo-400/30 bg-indigo-400/5 px-1 py-0.5 uppercase">
                    <Moon className="w-2.5 h-2.5" strokeWidth={1.8} /> AMC
                  </span>
                )}
              </div>
              <div className="text-right text-[10px] nums-tabular text-gray-200">{fmtEps(r.epsEstimate)}</div>
              <div className={`text-right text-[10px] nums-tabular ${r.imminent ? "text-amber-300 font-bold" : "text-gray-300"}`}>
                {formatEarningsCountdown(r.reportDateTime, now)}
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>

      <div className="shrink-0 pt-1.5 text-[9px] text-muted-foreground flex items-center justify-between">
        <span>{data.watchlistSize} names tracked</span>
        <span className="flex items-center gap-2">
          <span className="flex items-center gap-1"><Sunrise className="w-2.5 h-2.5" /> before open</span>
          <span className="flex items-center gap-1"><Moon className="w-2.5 h-2.5" /> after close</span>
        </span>
      </div>
    </div>
  );
}
