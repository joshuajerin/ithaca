import React from "react";
import type { OptionsStrategyData } from "@workspace/api-client-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

interface OptionsStrategyPanelProps {
  data: OptionsStrategyData;
}

function greek(val: number, decimals = 4) {
  const s = val >= 0 ? "+" : "";
  return `${s}${val.toFixed(decimals)}`;
}

export function OptionsStrategyPanel({ data }: OptionsStrategyPanelProps) {
  const netCost = data.netGreeks.cost;
  const isDebit = netCost > 0;

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const pnl = payload[0].value as number;
      return (
        <div className="bg-black border border-border p-2 text-xs">
          <div className="text-muted-foreground">Spot: ${Number(label).toFixed(2)}</div>
          <div className={`font-bold mt-0.5 ${pnl >= 0 ? "text-white" : "text-gray-400"}`}>
            P&L: {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}
          </div>
        </div>
      );
    }
    return null;
  };

  // Domain for chart Y axis
  const pnlValues = data.payoff.map((p) => p.pnl);
  const yMin = Math.min(...pnlValues);
  const yMax = Math.max(...pnlValues);
  const yPad = (yMax - yMin) * 0.1 || 1;

  return (
    <div className="flex flex-col h-full w-full gap-2">
      {/* Header */}
      <div className="flex justify-between items-baseline shrink-0">
        <div className="flex items-baseline gap-2">
          <span className="text-xl font-bold">{data.symbol}</span>
          <span className="text-sm font-bold uppercase tracking-wider text-white/80">
            {data.strategyName}
          </span>
        </div>
        <div className="text-right">
          <span className="text-xs text-muted-foreground mr-1">Net</span>
          <span className={`text-sm font-bold font-mono ${isDebit ? "text-gray-400" : "text-white"}`}>
            {isDebit ? "-" : "+"} ${Math.abs(netCost).toFixed(2)}
          </span>
          <span className="text-[10px] text-muted-foreground ml-1">{isDebit ? "debit" : "credit"}</span>
        </div>
      </div>

      {/* Key stats strip */}
      <div className="flex gap-4 text-[10px] shrink-0">
        <div>
          <span className="text-muted-foreground uppercase">Max Profit </span>
          <span className="font-bold font-mono">
            {data.maxProfit !== null && data.maxProfit !== undefined
              ? `$${data.maxProfit.toFixed(2)}`
              : "Unlimited"}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground uppercase">Max Loss </span>
          <span className="font-bold font-mono">
            {data.maxLoss !== null && data.maxLoss !== undefined
              ? `$${Math.abs(data.maxLoss).toFixed(2)}`
              : "Unlimited"}
          </span>
        </div>
        {data.breakevens.map((be, i) => (
          <div key={i}>
            <span className="text-muted-foreground uppercase">B/E{data.breakevens.length > 1 ? i + 1 : ""} </span>
            <span className="font-bold font-mono">${be.toFixed(2)}</span>
          </div>
        ))}
      </div>

      {/* Payoff diagram */}
      <div className="flex-1 w-full min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.payoff} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="#222" vertical={false} />
            <XAxis
              dataKey="price"
              tick={{ fontSize: 9, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
              minTickGap={30}
            />
            <YAxis
              domain={[yMin - yPad, yMax + yPad]}
              tick={{ fontSize: 9, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine y={0} stroke="#555" strokeWidth={1} />
            <ReferenceLine
              x={data.underlyingPrice}
              stroke="#666"
              strokeDasharray="3 3"
              label={{ value: "Spot", position: "top", fontSize: 9, fill: "#666" }}
            />
            {data.breakevens.map((be, i) => (
              <ReferenceLine
                key={i}
                x={be}
                stroke="#888"
                strokeDasharray="2 2"
              />
            ))}
            <Line
              type="monotone"
              dataKey="pnl"
              stroke="#fff"
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, fill: "#000", stroke: "#fff", strokeWidth: 1.5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Legs + Greeks table */}
      <div className="shrink-0 border-t border-border pt-1.5">
        <table className="w-full text-[10px]">
          <thead>
            <tr className="text-muted-foreground uppercase">
              <th className="text-left font-normal pb-1">Leg</th>
              <th className="text-right font-normal pb-1">Strike</th>
              <th className="text-right font-normal pb-1">Prem</th>
              <th className="text-right font-normal pb-1">Δ</th>
              <th className="text-right font-normal pb-1">Γ</th>
              <th className="text-right font-normal pb-1">Θ</th>
              <th className="text-right font-normal pb-1">V</th>
            </tr>
          </thead>
          <tbody>
            {data.legs.map((leg, i) => (
              <tr key={i} className="border-t border-border/40">
                <td className="py-0.5 font-bold uppercase">
                  {leg.action === "long" ? "+" : "−"}{leg.type[0].toUpperCase()}
                </td>
                <td className="text-right font-mono">${leg.strike.toFixed(0)}</td>
                <td className="text-right font-mono">${leg.premium.toFixed(2)}</td>
                <td className={`text-right font-mono ${leg.delta >= 0 ? "text-white" : "text-gray-400"}`}>
                  {greek(leg.delta, 3)}
                </td>
                <td className="text-right font-mono text-muted-foreground">{leg.gamma.toFixed(4)}</td>
                <td className={`text-right font-mono ${leg.theta >= 0 ? "text-white" : "text-gray-400"}`}>
                  {greek(leg.theta, 3)}
                </td>
                <td className="text-right font-mono text-muted-foreground">{leg.vega.toFixed(3)}</td>
              </tr>
            ))}
            {/* Net row */}
            <tr className="border-t border-border font-bold">
              <td className="py-0.5 uppercase text-muted-foreground">Net</td>
              <td />
              <td className={`text-right font-mono ${isDebit ? "text-gray-400" : "text-white"}`}>
                {isDebit ? "-" : "+"}${Math.abs(netCost).toFixed(2)}
              </td>
              <td className={`text-right font-mono ${data.netGreeks.delta >= 0 ? "text-white" : "text-gray-400"}`}>
                {greek(data.netGreeks.delta, 3)}
              </td>
              <td className="text-right font-mono text-muted-foreground">{data.netGreeks.gamma.toFixed(4)}</td>
              <td className={`text-right font-mono ${data.netGreeks.theta >= 0 ? "text-white" : "text-gray-400"}`}>
                {greek(data.netGreeks.theta, 3)}
              </td>
              <td className="text-right font-mono text-muted-foreground">{data.netGreeks.vega.toFixed(3)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
