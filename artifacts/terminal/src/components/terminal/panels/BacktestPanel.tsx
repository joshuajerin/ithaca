import React from "react";
import type { BacktestData } from "@workspace/api-client-react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";

export function BacktestPanel({ data }: { data: BacktestData }) {
  const { stats, curve, drawdown } = data;

  const CurveTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div className="bg-black border border-white/20 p-2 text-xs space-y-1">
          <p className="text-muted-foreground">{label}</p>
          {payload.map((p: any) => (
            <p key={p.name} style={{ color: p.color }} className="font-mono">
              {p.name}: {p.value.toFixed(2)}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  const DDTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div className="bg-black border border-white/20 p-2 text-xs">
          <p className="text-muted-foreground">{label}</p>
          <p className="text-red-400 font-mono">DD: {payload[0].value.toFixed(2)}%</p>
        </div>
      );
    }
    return null;
  };

  const statItems = [
    { label: "Sharpe", value: stats.sharpe.toFixed(2), positive: stats.sharpe > 1 },
    { label: "Sortino", value: stats.sortino.toFixed(2), positive: stats.sortino > 1 },
    { label: "CAGR", value: `${stats.cagr.toFixed(1)}%`, positive: stats.cagr > 0 },
    { label: "Max DD", value: `${stats.maxDD.toFixed(1)}%`, positive: false, alwaysRed: true },
    { label: "Win Rate", value: `${stats.winRate.toFixed(1)}%`, positive: stats.winRate > 50 },
  ];

  const downsampledCurve = curve.filter((_, i) => i % Math.max(1, Math.floor(curve.length / 120)) === 0);
  const downsampledDD = drawdown.filter((_, i) => i % Math.max(1, Math.floor(drawdown.length / 120)) === 0);

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="grid grid-cols-5 gap-2 shrink-0">
        {statItems.map((item) => (
          <div key={item.label} className="border border-border p-2">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">{item.label}</div>
            <div
              className={`text-sm font-bold font-mono ${
                item.alwaysRed ? "text-red-400" : item.positive ? "text-white" : "text-muted-foreground"
              }`}
            >
              {item.value}
            </div>
          </div>
        ))}
      </div>

      <div className="flex-1 min-h-0 flex flex-col gap-2">
        <div className="flex-[2] min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
            {data.strategy.replace(/_/g, " ").toUpperCase()} · {data.symbol} vs Benchmark (rebased 100)
          </div>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={downsampledCurve} margin={{ top: 2, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
              <XAxis dataKey="t" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} minTickGap={40} />
              <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
              <Tooltip content={<CurveTooltip />} />
              <Line type="monotone" dataKey="strategy" stroke="#ffffff" strokeWidth={1.5} dot={false} name="Strategy" />
              <Line type="monotone" dataKey="benchmark" stroke="#555555" strokeWidth={1} dot={false} name="Benchmark" strokeDasharray="4 2" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="flex-1 min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Drawdown</div>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={downsampledDD} margin={{ top: 2, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
              <XAxis dataKey="t" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} minTickGap={40} />
              <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
              <Tooltip content={<DDTooltip />} />
              <defs>
                <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ef4444" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#ef4444" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <Area type="monotone" dataKey="dd" stroke="#ef4444" strokeWidth={1} fill="url(#ddGrad)" name="Drawdown" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
