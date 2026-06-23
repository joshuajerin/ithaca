// @ts-nocheck
import React from "react";
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";

function DarkPoolGauge({ pct }: { pct: number }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="text-[10px] uppercase tracking-widest text-muted-foreground">Dark Pool</div>
      <div className="relative w-full h-2 bg-[#111] overflow-hidden">
        <div className="absolute inset-y-0 left-0 bg-white/50" style={{ width: `${pct}%` }} />
      </div>
      <div className="text-sm font-bold font-mono">{pct.toFixed(1)}%</div>
    </div>
  );
}

export function TradeFlowPanel({ data }: { data: any }) {
  const imbalancePct = Math.round(data.buyImbalance * 100);
  const netBuy = data.buyImbalance >= 0.5;

  const scatterData = data.prints.map((p: any) => ({
    x: p.time,
    y: p.price,
    z: Math.sqrt(p.size) * 0.4,
    side: p.side,
    isBlock: p.isBlock,
    isDark: p.isDark,
    size: p.size,
    venue: p.venue,
  }));

  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0]?.payload;
    if (!d) return null;
    return (
      <div className="bg-black border border-border text-xs p-2 space-y-0.5">
        <div className="font-bold uppercase text-[10px] tracking-wider">{d.isBlock ? "BLOCK" : "PRINT"}{d.isDark ? " · DARK" : ""}</div>
        <div className="font-mono">{d.x} · ${d.y.toFixed(2)}</div>
        <div className="text-muted-foreground">{d.size.toLocaleString()} shares · {d.venue}</div>
        <div className={d.side === "buy" ? "text-white" : "text-gray-500"}>{d.side.toUpperCase()}</div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest">
            {data.symbol} · Trade Flow
          </div>
          <div className="text-sm font-bold uppercase">
            {netBuy ? "Net Buy" : "Net Sell"}{" "}
            <span className="font-mono text-muted-foreground text-xs">
              {imbalancePct}% buy
            </span>
          </div>
        </div>
        <div className="text-right text-[10px] text-muted-foreground uppercase tracking-widest">
          <div>{(data.totalVolume / 1_000_000).toFixed(1)}M vol</div>
          <div>{data.prints.filter((p: any) => p.isBlock).length} blocks</div>
        </div>
      </div>

      <div className="flex gap-4 shrink-0">
        <div className="flex-1">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Buy / Sell Imbalance</div>
          <div className="relative h-2 bg-[#111] overflow-hidden">
            <div
              className="absolute inset-y-0 left-0 bg-white"
              style={{ width: `${imbalancePct}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] font-mono mt-0.5">
            <span className="text-white">{imbalancePct}% B</span>
            <span className="text-gray-500">{100 - imbalancePct}% S</span>
          </div>
        </div>
        <div className="w-24">
          <DarkPoolGauge pct={data.darkPoolPct} />
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" />
            <XAxis
              dataKey="x"
              type="category"
              tick={{ fontSize: 9, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              dataKey="y"
              type="number"
              domain={["auto", "auto"]}
              tick={{ fontSize: 9, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `$${v.toFixed(0)}`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Scatter data={scatterData}>
              {scatterData.map((entry: any, idx: any) => (
                <Cell
                  key={idx}
                  fill={entry.isBlock ? "#ffffff" : entry.side === "buy" ? "#888888" : "#333333"}
                  opacity={entry.isDark ? 0.5 : 1}
                  r={entry.isBlock ? Math.max(4, entry.z / 4) : Math.max(2, entry.z / 8)}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <div className="shrink-0 flex gap-3 text-[9px] text-muted-foreground uppercase tracking-widest">
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-white" />
          Block ≥{(data.blockThreshold / 1000).toFixed(0)}K
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-white/40" />
          Dark Pool
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-[#888]" />
          Buy
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-[#333]" />
          Sell
        </span>
      </div>
    </div>
  );
}
