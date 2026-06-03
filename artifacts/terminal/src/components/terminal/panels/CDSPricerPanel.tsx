import React from "react";
import type { CDSPricerData } from "@workspace/api-client-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import { ScrollArea } from "@/components/ui/scroll-area";

interface CDSPricerPanelProps {
  data: CDSPricerData;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const pt = payload[0]?.payload;
    return (
      <div className="bg-black border border-white/20 p-2 shadow-xl text-xs">
        <p className="text-muted-foreground mb-1">{label}</p>
        <p className="font-mono text-white">
          Survival: {(pt?.survivalProb * 100).toFixed(2)}%
        </p>
        <p className="font-mono text-red-400">
          Default: {(pt?.defaultProb * 100).toFixed(2)}%
        </p>
        <p className="font-mono text-muted-foreground">
          Hazard: {(pt?.hazardRate * 10000).toFixed(1)}bp
        </p>
      </div>
    );
  }
  return null;
};

export function CDSPricerPanel({ data }: CDSPricerPanelProps) {
  const upfrontSign = data.upfrontFee >= 0 ? "+" : "";
  const isHighRisk = data.runningSpread > 200;

  const chartData = data.survivalCurve.map((pt) => ({
    ...pt,
    survivalPct: parseFloat((pt.survivalProb * 100).toFixed(2)),
    defaultPct: parseFloat((pt.defaultProb * 100).toFixed(2)),
  }));

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex justify-between items-start mb-3 shrink-0">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">CDS Pricer</div>
          <div className="text-xl font-bold">{data.entity}</div>
          <div className="text-[10px] text-muted-foreground mt-0.5">{data.ticker} · {data.rating}</div>
        </div>
        <div className="text-right flex gap-4 items-start">
          <div>
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest">Running Spd</div>
            <div className={`text-2xl font-bold font-mono ${isHighRisk ? "text-red-400" : "text-white"}`}>
              {data.runningSpread.toFixed(0)}bp
            </div>
          </div>
          <div>
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest">Upfront</div>
            <div className="text-lg font-bold font-mono text-white">
              {upfrontSign}{data.upfrontFee.toFixed(2)}%
            </div>
          </div>
        </div>
      </div>

      <div className="flex gap-4 mb-3 shrink-0">
        <div className="border border-border px-3 py-1.5 flex-1 text-center">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest">1Y Impl. PD</div>
          <div className={`text-base font-bold font-mono ${isHighRisk ? "text-red-400" : "text-white"}`}>
            {(data.impliedPd1y * 100).toFixed(2)}%
          </div>
        </div>
        <div className="border border-border px-3 py-1.5 flex-1 text-center">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest">5Y Impl. PD</div>
          <div className={`text-base font-bold font-mono ${isHighRisk ? "text-red-400" : "text-white"}`}>
            {(data.impliedPd5y * 100).toFixed(2)}%
          </div>
        </div>
        <div className="border border-border px-3 py-1.5 flex-1 text-center">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest">Recovery</div>
          <div className="text-base font-bold font-mono text-white">
            {(data.recoveryRate * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Survival Probability Curve</div>
        <ResponsiveContainer width="100%" height="80%">
          <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="survivalGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ffffff" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#ffffff" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="defaultGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#ef4444" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 2" stroke="#222" vertical={false} />
            <XAxis dataKey="tenor" tick={{ fontSize: 9, fill: "#666" }} tickLine={false} axisLine={false} />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 9, fill: "#666" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="survivalPct"
              name="Survival"
              stroke="#ffffff"
              strokeWidth={1.5}
              fill="url(#survivalGrad)"
              dot={false}
            />
            <Area
              type="monotone"
              dataKey="defaultPct"
              name="Default"
              stroke="#ef4444"
              strokeWidth={1.5}
              fill="url(#defaultGrad)"
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>

        <div className="mt-1 border border-border">
          <table className="w-full text-[10px]">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="text-left py-1 px-2 uppercase tracking-wider text-[9px]">Tenor</th>
                <th className="text-right py-1 px-2 uppercase tracking-wider text-[9px]">Survival</th>
                <th className="text-right py-1 px-2 uppercase tracking-wider text-[9px]">Def Prob</th>
                <th className="text-right py-1 px-2 uppercase tracking-wider text-[9px]">Hazard (bp)</th>
              </tr>
            </thead>
            <tbody>
              {data.survivalCurve.map((pt) => (
                <tr key={pt.tenor} className="border-b border-border/40 hover:bg-white/5">
                  <td className="py-1 px-2 font-bold">{pt.tenor}</td>
                  <td className="py-1 px-2 text-right font-mono">{(pt.survivalProb * 100).toFixed(2)}%</td>
                  <td className={`py-1 px-2 text-right font-mono ${pt.defaultProb > 0.1 ? "text-red-400" : "text-white"}`}>
                    {(pt.defaultProb * 100).toFixed(2)}%
                  </td>
                  <td className="py-1 px-2 text-right font-mono text-muted-foreground">
                    {(pt.hazardRate * 10000).toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
