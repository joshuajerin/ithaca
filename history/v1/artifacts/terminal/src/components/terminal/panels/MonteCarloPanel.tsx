import React from "react";
import type { MonteCarloData } from "@workspace/api-client-react";
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

export function MonteCarloPanel({ data }: { data: MonteCarloData }) {
  const { fan, summary, startValue, symbol, method, horizon } = data;

  // Build a single dataset: the band edges expressed so stacked Areas render a
  // p5-p95 envelope, a p25-p75 inner band, and the median line.
  const chartData = fan.map((f) => ({
    step: f.step,
    p5: f.p5,
    lowBand: Math.max(0, f.p25 - f.p5),
    p25: f.p25,
    midBand: Math.max(0, f.p75 - f.p25),
    p75: f.p75,
    highBand: Math.max(0, f.p95 - f.p75),
    p50: f.p50,
  }));

  const FanTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      const row = fan[label] ?? fan.find((f) => f.step === label);
      if (!row) return null;
      return (
        <div className="bg-black border border-white/20 p-2 text-xs space-y-0.5">
          <p className="text-muted-foreground">Day {row.step}</p>
          <p className="text-emerald-400 font-mono">p95: {row.p95.toFixed(2)}</p>
          <p className="text-white/70 font-mono">p75: {row.p75.toFixed(2)}</p>
          <p className="text-white font-mono">median: {row.p50.toFixed(2)}</p>
          <p className="text-white/70 font-mono">p25: {row.p25.toFixed(2)}</p>
          <p className="text-red-400 font-mono">p5: {row.p5.toFixed(2)}</p>
        </div>
      );
    }
    return null;
  };

  const stats = [
    {
      label: "Exp. Return",
      value: `${summary.expectedReturn >= 0 ? "+" : ""}${summary.expectedReturn.toFixed(1)}%`,
      tone: summary.expectedReturn >= 0 ? "text-emerald-400" : "text-red-400",
    },
    {
      label: "Prob. Loss",
      value: `${summary.probLoss.toFixed(1)}%`,
      tone: summary.probLoss > 50 ? "text-red-400" : "text-white",
    },
    { label: "Median End", value: summary.medianTerminal.toFixed(2), tone: "text-white" },
    { label: "VaR 95", value: `${summary.var95.toFixed(1)}%`, tone: "text-red-400" },
    { label: "CVaR 95", value: `${summary.cvar95.toFixed(1)}%`, tone: "text-red-400" },
  ];

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="grid grid-cols-5 gap-2 shrink-0">
        {stats.map((s) => (
          <div key={s.label} className="border border-border p-2">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">
              {s.label}
            </div>
            <div className={`text-sm font-bold font-mono ${s.tone}`}>{s.value}</div>
          </div>
        ))}
      </div>

      <div className="flex-1 min-h-0 flex flex-col">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
          {symbol} · {method.toUpperCase()} · {horizon}d forward · {summary.paths.toLocaleString()} paths · p5–p95 fan
        </div>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 2, right: 0, left: -20, bottom: 0 }} stackOffset="none">
            <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
            <XAxis
              dataKey="step"
              tick={{ fontSize: 9, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              minTickGap={40}
              tickFormatter={(v) => `${v}d`}
            />
            <YAxis
              tick={{ fontSize: 9, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              domain={["auto", "auto"]}
            />
            <Tooltip content={<FanTooltip />} />
            <ReferenceLine y={startValue} stroke="#666" strokeDasharray="4 2" />
            {/* Stacked transparent base + colored bands form the percentile envelope. */}
            <Area type="monotone" dataKey="p5" stackId="fan" stroke="none" fill="transparent" isAnimationActive={false} />
            <Area type="monotone" dataKey="lowBand" stackId="fan" stroke="none" fill="#ef4444" fillOpacity={0.12} isAnimationActive={false} />
            <Area type="monotone" dataKey="midBand" stackId="fan" stroke="none" fill="#3b82f6" fillOpacity={0.18} isAnimationActive={false} />
            <Area type="monotone" dataKey="highBand" stackId="fan" stroke="none" fill="#10b981" fillOpacity={0.12} isAnimationActive={false} />
            <Line type="monotone" dataKey="p50" stroke="#ffffff" strokeWidth={1.5} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
