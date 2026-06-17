import React from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import type { PerformancePnlData } from "./PerformancePnlPanel";
import type { BrinsonData } from "./BrinsonPanel";
import type { FactorAttributionData } from "./FactorAttributionPanel";

export interface TearSheetData {
  portfolioName: string;
  benchmarkName: string;
  rangeLabel: string;
  windowDays: number;
  series: PerformancePnlData["series"];
  stats: PerformancePnlData["stats"];
  brinson: { rows: BrinsonData["rows"]; totals: BrinsonData["totals"]; benchmarkName?: string };
  factor: {
    rows: FactorAttributionData["rows"];
    realizedReturn: number;
    factorReturn: number;
    specificReturn: number;
  };
}

const sign = (n: number, d = 2) => `${n > 0 ? "+" : ""}${n.toFixed(d)}%`;
const tone = (n: number) => (n > 0 ? "text-emerald-400" : n < 0 ? "text-red-400" : "text-muted-foreground");

const Stat = ({ label, value, color }: { label: string; value: string; color?: string }) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-[8px] uppercase tracking-widest text-muted-foreground">{label}</span>
    <span className={`font-mono text-[11px] ${color ?? "text-white"}`}>{value}</span>
  </div>
);

const SectionLabel = ({ children }: { children: React.ReactNode }) => (
  <div className="text-[8.5px] text-muted-foreground uppercase tracking-widest mb-1.5">{children}</div>
);

export function TearSheetPanel({ data }: { data: TearSheetData }) {
  const b = data.stats.book;
  const a = data.stats.active;
  const brinsonChart = data.brinson.rows.map((r) => ({ sector: r.sectorLabel, total: r.total }));
  const factorChart = data.factor.rows.map((r) => ({ factor: r.factor, contribution: r.contribution }));

  return (
    <div className="flex flex-col h-full gap-3 overflow-auto">
      <div className="shrink-0 flex items-baseline justify-between">
        <div className="text-[9px] text-white uppercase tracking-widest">
          {data.portfolioName} · Performance Tear Sheet
        </div>
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          vs {data.benchmarkName} · {data.rangeLabel} · {data.windowDays}d
        </div>
      </div>

      <div className="shrink-0 grid grid-cols-6 gap-x-3 gap-y-2.5 border-y border-border py-2.5">
        <Stat label="Return" value={sign(b.totalReturn)} color={tone(b.totalReturn)} />
        <Stat label="Active" value={sign(a.activeReturn)} color={tone(a.activeReturn)} />
        <Stat label="Vol" value={`${b.vol.toFixed(1)}%`} />
        <Stat label="Sharpe" value={b.sharpe.toFixed(2)} color={tone(b.sharpe)} />
        <Stat label="Max DD" value={`${b.maxDD.toFixed(1)}%`} color="text-red-400" />
        <Stat label="Hit Rate" value={`${b.hitRate.toFixed(0)}%`} />
        <Stat label="Track Err" value={`${a.trackingError.toFixed(1)}%`} />
        <Stat label="Info Ratio" value={a.informationRatio.toFixed(2)} color={tone(a.informationRatio)} />
        <Stat label="Beta" value={a.beta.toFixed(2)} />
        <Stat label="Alpha" value={sign(a.alpha)} color={tone(a.alpha)} />
        <Stat label="Up Cap" value={`${a.upCapture.toFixed(0)}%`} />
        <Stat label="Down Cap" value={`${a.downCapture.toFixed(0)}%`} />
      </div>

      <div className="grid grid-cols-2 gap-5 flex-1 min-h-0">
        <div className="flex flex-col min-h-[160px]">
          <SectionLabel>Cumulative Return &amp; Drawdown</SectionLabel>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="70%">
              <ComposedChart data={data.series} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} minTickGap={40} tickFormatter={(v) => String(v).slice(5)} />
                <YAxis tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                <Tooltip contentStyle={{ background: "#000", border: "1px solid #ffffff33", fontSize: 10 }} />
                <ReferenceLine y={0} stroke="#444" strokeWidth={1} />
                <Line type="monotone" dataKey="book" stroke="#ffffff" strokeWidth={1.5} dot={false} name="Book" />
                <Line type="monotone" dataKey="bench" stroke="#888" strokeWidth={1.1} strokeDasharray="4 3" dot={false} name="Benchmark" />
              </ComposedChart>
            </ResponsiveContainer>
            <ResponsiveContainer width="100%" height="30%">
              <ComposedChart data={data.series} margin={{ top: 0, right: 4, left: -22, bottom: 0 }}>
                <defs>
                  <linearGradient id="tsDd" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#ef4444" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#ef4444" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" hide />
                <YAxis tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                <Area type="monotone" dataKey="drawdown" stroke="#ef4444" strokeWidth={1} fill="url(#tsDd)" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="grid grid-rows-2 gap-3 min-h-[160px]">
          <div className="flex flex-col min-h-0">
            <SectionLabel>
              Brinson Active Return by Sector (%)
              {data.brinson.benchmarkName ? ` · vs ${data.brinson.benchmarkName}` : ""}
            </SectionLabel>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={brinsonChart} margin={{ top: 2, right: 0, left: -22, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                  <XAxis dataKey="sector" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} interval={0} angle={-20} textAnchor="end" height={34} />
                  <YAxis tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                  <Tooltip contentStyle={{ background: "#000", border: "1px solid #ffffff33", fontSize: 10 }} />
                  <ReferenceLine y={0} stroke="#444" strokeWidth={1} />
                  <Bar dataKey="total" radius={[2, 2, 0, 0]}>
                    {brinsonChart.map((d, i) => (
                      <Cell key={i} fill={d.total >= 0 ? "#ffffff" : "#ef4444"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="flex flex-col min-h-0">
            <SectionLabel>Factor Contribution to Return (%)</SectionLabel>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={factorChart} margin={{ top: 2, right: 0, left: -22, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                  <XAxis dataKey="factor" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} interval={0} angle={-20} textAnchor="end" height={34} />
                  <YAxis tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                  <Tooltip contentStyle={{ background: "#000", border: "1px solid #ffffff33", fontSize: 10 }} />
                  <ReferenceLine y={0} stroke="#444" strokeWidth={1} />
                  <Bar dataKey="contribution" radius={[2, 2, 0, 0]}>
                    {factorChart.map((d, i) => (
                      <Cell key={i} fill={d.factor === "Specific" ? "#666" : d.contribution >= 0 ? "#ffffff" : "#ef4444"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      <div className="shrink-0 text-[9px] text-muted-foreground leading-relaxed border-t border-border pt-2">
        Active {sign(data.brinson.totals.activeReturn)} = allocation {sign(data.brinson.totals.allocation)} + selection {sign(data.brinson.totals.selection)} + interaction {sign(data.brinson.totals.interaction)}.
        Realized {sign(data.factor.realizedReturn)} = factor {sign(data.factor.factorReturn)} + specific {sign(data.factor.specificReturn)}.
      </div>
    </div>
  );
}
