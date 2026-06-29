// @ts-nocheck
import React, { useEffect, useState } from "react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine } from "recharts";
import { Clock, AlertTriangle, Loader2 } from "lucide-react";
import { Sparkline } from "../Sparkline";

interface IntradayPoint {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

interface IntradayChartData {
  symbol: string;
  name: string;
  interval: string;
  intervalLabel: string;
  range: string;
  rangeLabel: string;
  currency?: string;
  available: boolean;
  reason?: string | null;
  bars?: number;
  points: IntradayPoint[];
  last: number | null;
  change: number | null;
  changePct: number | null;
  asOf?: string | null;
  source: string;
}

interface Selection {
  interval: string;
  range: string;
}

const RESOLUTIONS: { value: string; label: string }[] = [
  { value: "1m", label: "1m" },
  { value: "5m", label: "5m" },
  { value: "15m", label: "15m" },
  { value: "30m", label: "30m" },
  { value: "1h", label: "1H" },
];

const WINDOWS: { value: string; label: string }[] = [
  { value: "1d", label: "1D" },
  { value: "5d", label: "5D" },
  { value: "1mo", label: "1M" },
  { value: "3mo", label: "3M" },
  { value: "6mo", label: "6M" },
  { value: "1y", label: "1Y" },
];

function fmtTime(t: string): string {
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) return t;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function ControlBar({
  sel,
  onChoose,
  pending,
}: {
  sel: Selection;
  onChoose: (next: Partial<Selection>) => void;
  pending?: boolean;
}) {
  const segBtn = (active: boolean) =>
    `editorial-label text-[8px] px-1.5 py-0.5 border transition-colors ${
      active
        ? "text-black bg-white border-white"
        : "text-muted-foreground border-border hover:text-white hover:border-white/40"
    } ${pending ? "opacity-60" : ""}`;

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 shrink-0">
      <div className="flex items-center gap-2">
        <span className="editorial-label text-[8px] text-muted-foreground/70">Resolution</span>
        <div className="flex items-center gap-1">
          {RESOLUTIONS.map((r) => (
            <button
              key={r.value}
              type="button"
              disabled={pending}
              onClick={() => onChoose({ interval: r.value })}
              className={segBtn(sel.interval === r.value)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className="editorial-label text-[8px] text-muted-foreground/70">Window</span>
        <div className="flex items-center gap-1">
          {WINDOWS.map((w) => (
            <button
              key={w.value}
              type="button"
              disabled={pending}
              onClick={() => onChoose({ range: w.value })}
              className={segBtn(sel.range === w.value)}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>
      {pending && (
        <span className="text-muted-foreground">
          <Loader2 className="w-3 h-3 animate-spin" strokeWidth={1.5} />
        </span>
      )}
    </div>
  );
}

export function IntradayChartPanel({
  data,
  onSelect,
  pending,
}: {
  data: IntradayChartData;
  onSelect?: (sel: Selection) => void;
  pending?: boolean;
}) {
  const [sel, setSel] = useState<Selection>({
    interval: data.interval,
    range: data.range,
  });

  useEffect(() => {
    setSel({ interval: data.interval, range: data.range });
  }, [data.interval, data.range]);

  const choose = (next: Partial<Selection>) => {
    const merged = { ...sel, ...next };
    if (merged.interval === sel.interval && merged.range === sel.range) return;
    if (!merged.range) merged.range = "1d";
    setSel(merged);
    onSelect?.(merged);
  };

  if (!data.available) {
    return (
      <div className="flex flex-col h-full w-full">
        <div className="flex items-center gap-3 mb-4 shrink-0">
          <span className="font-serif text-4xl leading-none tracking-tight">{data.symbol}</span>
          <span className="editorial-label text-[9px] text-muted-foreground border border-border px-1.5 py-0.5">
            {data.intervalLabel}
          </span>
        </div>
        {onSelect && (
          <div className="mb-4 shrink-0">
            <ControlBar sel={sel} onChoose={choose} pending={pending} />
          </div>
        )}
        <div className="flex-1 border-t border-border flex flex-col items-center justify-center text-center gap-3 text-muted-foreground px-6">
          <AlertTriangle className="w-5 h-5" strokeWidth={1.25} />
          <span className="editorial-label text-[9px]">Intraday Data Unavailable</span>
          <p className="font-serif text-sm leading-snug max-w-xs text-muted-foreground/90">
            {data.reason || "This resolution or window is not available from the data source."}
          </p>
        </div>
      </div>
    );
  }

  const isPositive = (data.change ?? 0) >= 0;
  const spark = data.points.map((p) => p.c);

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-black border border-white px-3 py-2">
          <p className="editorial-label text-[8px] text-muted-foreground">{fmtTime(label)}</p>
          <p className="font-serif text-lg nums-tabular mt-0.5">{payload[0].value.toFixed(2)}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex justify-between items-start mb-5 shrink-0">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <span className="font-serif text-4xl leading-none tracking-tight">{data.symbol}</span>
            <span className="text-muted-foreground mt-1">
              <Sparkline data={spark} width={56} height={22} />
            </span>
          </div>
          <div className="flex items-center gap-2 mt-2.5">
            <span className="editorial-label text-[8px] text-white border border-white/40 bg-white/5 px-1.5 py-0.5 flex items-center gap-1">
              <Clock className="w-2.5 h-2.5" strokeWidth={2} />
              {data.intervalLabel}
            </span>
            <span className="editorial-label text-[8px] text-muted-foreground border border-border px-1.5 py-0.5">
              {data.rangeLabel} window
            </span>
            {data.bars ? (
              <span className="editorial-label text-[8px] text-muted-foreground">{data.bars} bars</span>
            ) : null}
          </div>
          <div className="editorial-label text-[9px] text-muted-foreground mt-1.5 truncate">{data.name}</div>
        </div>
        <div className="text-right shrink-0 ml-4">
          <div className="font-serif text-3xl leading-none nums-oldstyle">
            {data.last != null ? data.last.toFixed(2) : "—"}
          </div>
          <div className="editorial-label text-[8px] text-muted-foreground mt-1.5 mb-1">{data.currency || "USD"}</div>
          {data.change != null && data.changePct != null && (
            <div className={`font-serif text-base nums-oldstyle ${isPositive ? "text-white" : "text-muted-foreground"}`}>
              {isPositive ? "+" : ""}{data.change.toFixed(2)} ({isPositive ? "+" : ""}{data.changePct.toFixed(2)}%)
            </div>
          )}
        </div>
      </div>

      {onSelect && (
        <div className="mb-3 shrink-0">
          <ControlBar sel={sel} onChoose={choose} pending={pending} />
        </div>
      )}

      <div className="border-t border-border flex-1 w-full min-h-0 pt-3 relative">
        {pending && (
          <div className="absolute inset-0 z-10 bg-black/40 flex items-center justify-center">
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" strokeWidth={1.5} />
          </div>
        )}
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={160}>
          <LineChart data={data.points} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="1 3" stroke="#2a2a2a" vertical={false} />
            <XAxis
              dataKey="t"
              tickFormatter={fmtTime}
              tick={{ fontSize: 9, fill: "#777", fontFamily: "var(--font-sans)" }}
              tickLine={false}
              axisLine={false}
              minTickGap={40}
            />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fontSize: 10, fill: "#777", fontFamily: "var(--font-sans)" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(val) => val.toFixed(1)}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ stroke: "#555", strokeWidth: 1 }} />
            {data.points.length > 0 && (
              <ReferenceLine y={data.points[0].o} stroke="#3a3a3a" strokeDasharray="2 4" />
            )}
            <Line
              type="monotone"
              dataKey="c"
              stroke="#fff"
              strokeWidth={1.25}
              dot={false}
              activeDot={{ r: 3, fill: "#000", stroke: "#fff", strokeWidth: 1.5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
