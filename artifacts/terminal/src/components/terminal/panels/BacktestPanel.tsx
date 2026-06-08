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

const STRATEGIES: { value: string; label: string }[] = [
  { value: "momentum", label: "Momentum" },
  { value: "mean_reversion", label: "Mean Reversion" },
  { value: "buy_and_hold", label: "Buy & Hold" },
];
const RANGES = ["1M", "3M", "6M", "1Y"] as const;

interface Props {
  data: BacktestData;
  onRefine?: (params: Record<string, unknown>) => void;
}

export function BacktestPanel({ data, onRefine }: Props) {
  const { stats, curve, drawdown } = data;
  const range = (data.range ?? "1Y").toUpperCase();

  const closedTrades = (data.tradeLog ?? []).filter(
    (t) => typeof t.pnl === "number" && t.pnl !== 0,
  );
  const bestTrade = closedTrades.length
    ? closedTrades.reduce((a, b) => ((b.pnl ?? 0) > (a.pnl ?? 0) ? b : a))
    : null;
  const worstTrade = closedTrades.length
    ? closedTrades.reduce((a, b) => ((b.pnl ?? 0) < (a.pnl ?? 0) ? b : a))
    : null;

  const fmtPts = (v?: number) => `${(v ?? 0) >= 0 ? "+" : ""}${(v ?? 0).toFixed(2)}`;

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
      {onRefine && (
        <div className="flex items-center justify-between gap-2 shrink-0 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] text-muted-foreground uppercase tracking-widest">Strategy</span>
            <select
              value={data.strategy}
              onChange={(e) => onRefine({ symbol: data.symbol, strategy: e.target.value, range })}
              className="text-[10px] bg-black border border-border px-1.5 py-0.5 font-mono text-white focus:outline-none focus:border-white/60 transition-colors"
            >
              {STRATEGIES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex gap-1">
            {RANGES.map((r) => (
              <button
                key={r}
                onClick={() => {
                  if (r !== range) onRefine({ symbol: data.symbol, strategy: data.strategy, range: r });
                }}
                className={`text-[9px] px-2 py-0.5 border uppercase tracking-widest transition-colors ${
                  range === r
                    ? "border-white text-white bg-white/10"
                    : "border-border text-muted-foreground hover:border-white/40"
                }`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
      )}
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

      {(bestTrade || worstTrade) && (
        <div className="grid grid-cols-2 gap-2 shrink-0">
          {[
            { label: "Best Trade", trade: bestTrade, color: "text-emerald-400" },
            { label: "Worst Trade", trade: worstTrade, color: "text-red-400" },
          ].map(({ label, trade, color }) => (
            <div key={label} className="border border-border p-2">
              <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">{label}</div>
              {trade ? (
                <div className="flex items-baseline justify-between gap-2">
                  <span className={`text-sm font-bold font-mono ${color}`}>
                    {fmtPts(trade.pnl)} <span className="text-[10px]">pts</span>
                  </span>
                  <span className="text-[10px] font-mono text-muted-foreground">
                    {fmtPts(trade.pnlPct)}% · {trade.action} @ {trade.price} · {trade.t}
                  </span>
                </div>
              ) : (
                <div className="text-sm font-mono text-muted-foreground">—</div>
              )}
            </div>
          ))}
        </div>
      )}

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
