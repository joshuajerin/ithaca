// @ts-nocheck
// Light-theme copy of web/src/components/terminal/panels/PerformancePnlPanel.tsx
// DO NOT edit the original at web/src/components/terminal/panels/.
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
function toneColor(n: number): string {
  return n > 0 ? "var(--pos)" : n < 0 ? "var(--neg)" : "var(--muted)";
}

const Stat = ({ label, value, color }: { label: string; value: string; color?: string }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
    <span style={{ fontSize: 8.5, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted)" }}>{label}</span>
    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: color ?? "var(--fg)" }}>{value}</span>
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
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", padding: 8, fontSize: 10, minWidth: 150 }}>
        <p style={{ color: "var(--muted)", marginBottom: 4 }}>{label}</p>
        <p style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><span>Book</span><span style={{ fontFamily: "var(--font-mono)", color: toneColor(row.book) }}>{sign(row.book)}</span></p>
        <p style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><span>Benchmark</span><span style={{ fontFamily: "var(--font-mono)", color: toneColor(row.bench) }}>{sign(row.bench)}</span></p>
        <p style={{ display: "flex", justifyContent: "space-between", gap: 12, borderTop: "1px solid var(--border-soft)", paddingTop: 4, marginTop: 4 }}><span>Drawdown</span><span style={{ fontFamily: "var(--font-mono)", color: "var(--neg)" }}>{sign(row.drawdown)}</span></p>
      </div>
    );
  };

  return (
    <div className="panel-light" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexShrink: 0 }}>
        <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em" }}>
          {data.portfolioName} · P&amp;L vs {data.benchmarkName}
        </div>
        <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em" }}>
          {data.rangeLabel} · {data.windowDays}d
          {data.benchmarkSource ? ` · ${data.benchmarkSource}` : ""}
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        <ResponsiveContainer width="100%" height="65%">
          <ComposedChart data={data.series} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="var(--border-soft)" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} minTickGap={40} tickFormatter={(v) => String(v).slice(5)} />
            <YAxis tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
            <Tooltip content={<ChartTip />} />
            <ReferenceLine y={0} stroke="var(--border)" strokeWidth={1} />
            <Line type="monotone" dataKey="book" stroke="var(--fg)" strokeWidth={1.6} dot={false} name="Book" />
            <Line type="monotone" dataKey="bench" stroke="var(--accent)" strokeWidth={1.2} strokeDasharray="4 3" dot={false} name="Benchmark" />
          </ComposedChart>
        </ResponsiveContainer>
        <div style={{ fontSize: 8.5, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em", marginTop: 4, marginBottom: 2 }}>Drawdown</div>
        <ResponsiveContainer width="100%" height="35%">
          <ComposedChart data={data.series} margin={{ top: 0, right: 4, left: -22, bottom: 0 }}>
            <defs>
              <linearGradient id="ddFillLight" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--neg)" stopOpacity={0.3} />
                <stop offset="100%" stopColor="var(--neg)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" hide />
            <YAxis tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
            <Tooltip content={<ChartTip />} />
            <Area type="monotone" dataKey="drawdown" stroke="var(--neg)" strokeWidth={1} fill="url(#ddFillLight)" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div style={{ flexShrink: 0, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px 16px", borderTop: "1px solid var(--border-soft)", paddingTop: 10 }}>
        <Stat label="Return" value={sign(b.totalReturn)} color={toneColor(b.totalReturn)} />
        <Stat label="Active" value={sign(a.activeReturn)} color={toneColor(a.activeReturn)} />
        <Stat label="Vol (ann)" value={`${b.vol.toFixed(1)}%`} />
        <Stat label="Sharpe" value={b.sharpe.toFixed(2)} color={toneColor(b.sharpe)} />
        <Stat label="Max DD" value={`${b.maxDD.toFixed(1)}%`} color="var(--neg)" />
        <Stat label="Hit Rate" value={`${b.hitRate.toFixed(0)}%`} />
        <Stat label="Tracking Err" value={`${a.trackingError.toFixed(1)}%`} />
        <Stat label="Info Ratio" value={a.informationRatio.toFixed(2)} color={toneColor(a.informationRatio)} />
        <Stat label="Beta" value={a.beta.toFixed(2)} />
        <Stat label="Alpha (ann)" value={sign(a.alpha)} color={toneColor(a.alpha)} />
        <Stat label="Up Capture" value={`${a.upCapture.toFixed(0)}%`} />
        <Stat label="Down Capture" value={`${a.downCapture.toFixed(0)}%`} />
      </div>
    </div>
  );
}
