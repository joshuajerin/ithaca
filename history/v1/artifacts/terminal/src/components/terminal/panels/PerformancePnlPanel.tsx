import React from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

interface SeriesPoint {
  date: string;
  book: number;
  bench: number;
  drawdown: number;
}
interface StatBlock {
  totalReturn: number;
  cagr: number;
  vol: number;
  sharpe: number;
  sortino: number;
  maxDD: number;
  hitRate: number;
}
interface ActiveBlock {
  activeReturn: number;
  trackingError: number;
  informationRatio: number;
  beta: number;
  alpha: number;
  correlation: number;
  upCapture: number;
  downCapture: number;
}
export interface PerformancePnlData {
  portfolioName: string;
  benchmarkName: string;
  benchmarkTicker?: string;
  benchmarkSource?: string;
  benchmarkMissingDays?: number;
  rangeLabel: string;
  windowDays: number;
  series: SeriesPoint[];
  stats: { book: StatBlock; benchmark: StatBlock; active: ActiveBlock };
}

function sign(n: number, digits = 2, suffix = "%") {
  return `${n > 0 ? "+" : ""}${n.toFixed(digits)}${suffix}`;
}
function tone(n: number) {
  return n > 0 ? "text-emerald-400" : n < 0 ? "text-red-400" : "text-muted-foreground";
}

const Stat = ({ label, value, color }: { label: string; value: string; color?: string }) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-[8.5px] uppercase tracking-widest text-muted-foreground">{label}</span>
    <span className={`font-mono text-[12px] ${color ?? "text-white"}`}>{value}</span>
  </div>
);

export function PerformancePnlPanel({ data }: { data: PerformancePnlData }) {
  const { stats } = data;
  const b = stats.book;
  const a = stats.active;

  const ChartTip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const row = payload[0]?.payload as SeriesPoint;
    return (
      <div className="bg-black border border-white/20 p-2 text-[10px] space-y-1 min-w-[150px]">
        <p className="text-muted-foreground mb-1">{label}</p>
        <p className="flex justify-between gap-3"><span>Book</span><span className={`font-mono ${tone(row.book)}`}>{sign(row.book)}</span></p>
        <p className="flex justify-between gap-3"><span>Benchmark</span><span className={`font-mono ${tone(row.bench)}`}>{sign(row.bench)}</span></p>
        <p className="flex justify-between gap-3 border-t border-border/50 pt-1"><span>Drawdown</span><span className="font-mono text-red-400">{sign(row.drawdown)}</span></p>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="shrink-0 flex items-baseline justify-between">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          {data.portfolioName} · P&amp;L vs {data.benchmarkName}
        </div>
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          {data.rangeLabel} · {data.windowDays}d
          {data.benchmarkSource ? ` · ${data.benchmarkSource} benchmark` : ""}
          {data.benchmarkMissingDays ? ` · ${data.benchmarkMissingDays} bench gap${data.benchmarkMissingDays > 1 ? "s" : ""}` : ""}
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col">
        <ResponsiveContainer width="100%" height="65%">
          <ComposedChart data={data.series} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} minTickGap={40} tickFormatter={(v) => String(v).slice(5)} />
            <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
            <Tooltip content={<ChartTip />} />
            <ReferenceLine y={0} stroke="#444" strokeWidth={1} />
            <Line type="monotone" dataKey="book" stroke="#ffffff" strokeWidth={1.6} dot={false} name="Book" />
            <Line type="monotone" dataKey="bench" stroke="#888888" strokeWidth={1.2} strokeDasharray="4 3" dot={false} name="Benchmark" />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="text-[8.5px] text-muted-foreground uppercase tracking-widest mt-1 mb-0.5">Drawdown</div>
        <ResponsiveContainer width="100%" height="35%">
          <ComposedChart data={data.series} margin={{ top: 0, right: 4, left: -22, bottom: 0 }}>
            <defs>
              <linearGradient id="ddFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#ef4444" stopOpacity={0.4} />
                <stop offset="100%" stopColor="#ef4444" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" hide />
            <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
            <Tooltip content={<ChartTip />} />
            <Area type="monotone" dataKey="drawdown" stroke="#ef4444" strokeWidth={1} fill="url(#ddFill)" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="shrink-0 grid grid-cols-4 gap-x-4 gap-y-2.5 border-t border-border pt-2.5">
        <Stat label="Return" value={sign(b.totalReturn)} color={tone(b.totalReturn)} />
        <Stat label="Active" value={sign(a.activeReturn)} color={tone(a.activeReturn)} />
        <Stat label="Vol (ann)" value={`${b.vol.toFixed(1)}%`} />
        <Stat label="Sharpe" value={b.sharpe.toFixed(2)} color={tone(b.sharpe)} />
        <Stat label="Max DD" value={`${b.maxDD.toFixed(1)}%`} color="text-red-400" />
        <Stat label="Hit Rate" value={`${b.hitRate.toFixed(0)}%`} />
        <Stat label="Tracking Err" value={`${a.trackingError.toFixed(1)}%`} />
        <Stat label="Info Ratio" value={a.informationRatio.toFixed(2)} color={tone(a.informationRatio)} />
        <Stat label="Beta" value={a.beta.toFixed(2)} />
        <Stat label="Alpha (ann)" value={sign(a.alpha)} color={tone(a.alpha)} />
        <Stat label="Up Capture" value={`${a.upCapture.toFixed(0)}%`} />
        <Stat label="Down Capture" value={`${a.downCapture.toFixed(0)}%`} />
      </div>
    </div>
  );
}
