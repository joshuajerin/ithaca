// @ts-nocheck
import React from "react";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
  Area,
  AreaChart,
  Dot,
} from "recharts";

interface VolTermStructurePanelProps {
  data: any;
}

function regimeColor(regime: string) {
  if (regime === "contango") return "text-white";
  if (regime === "backwardation") return "text-gray-400";
  return "text-muted-foreground";
}

function regimeLabel(regime: string) {
  if (regime === "contango") return "Contango ↗";
  if (regime === "backwardation") return "Backwardation ↘";
  return "Flat ↔";
}

const CustomDot = (props: any) => {
  const { cx, cy, payload } = props;
  const color = payload.isContango ? "#ffffff" : "#666";
  return <circle cx={cx} cy={cy} r={3} fill={color} stroke={color} strokeWidth={1} />;
};

export function VolTermStructurePanel({ data }: VolTermStructurePanelProps) {
  const ivValues = data.expiries.map((e: any) => e.iv);
  const yMin = Math.max(0, Math.min(...ivValues) - 3);
  const yMax = Math.max(...ivValues) + 3;

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const exp = data.expiries.find((e: any) => e.label === label);
      return (
        <div className="bg-black border border-border p-2 text-xs">
          <div className="text-muted-foreground">{label} · {exp?.daysToExpiry}d</div>
          <div className="font-bold mt-0.5">IV {payload[0].value.toFixed(1)}%</div>
          {exp && (
            <div className="text-muted-foreground mt-0.5">
              ATM Prem ${exp.atmPremium.toFixed(2)}
            </div>
          )}
          {exp && (
            <div className={`mt-0.5 ${exp.isContango ? "text-white" : "text-gray-400"}`}>
              {exp.isContango ? "↗ Contango" : "↘ Backwardation"}
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex flex-col h-full w-full gap-2">
      {/* Header */}
      <div className="flex justify-between items-baseline shrink-0">
        <div className="flex items-baseline gap-2">
          <span className="text-xl font-bold">{data.symbol}</span>
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest">
            Vol Term Structure
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div>
            <span className="text-[10px] text-muted-foreground mr-1">Spot VIX</span>
            <span className="text-sm font-bold font-mono">{data.spotVix.toFixed(1)}</span>
          </div>
          <div>
            <span className="text-[10px] text-muted-foreground mr-1">ATM IV</span>
            <span className="text-sm font-bold font-mono">{data.atmIv.toFixed(1)}%</span>
          </div>
          <div className={`text-xs font-bold uppercase tracking-wider ${regimeColor(data.regime)}`}>
            {regimeLabel(data.regime)}
          </div>
        </div>
      </div>

      {/* Term structure chart */}
      <div className="flex-1 w-full min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data.expiries} margin={{ top: 8, right: 4, left: -16, bottom: 0 }}>
            <defs>
              <linearGradient id="volGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#fff" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#fff" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 2" stroke="#222" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 9, fill: "#555" }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              domain={[yMin, yMax]}
              tick={{ fontSize: 9, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v.toFixed(0)}%`}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine
              y={data.spotVix}
              stroke="#555"
              strokeDasharray="3 3"
              label={{ value: "VIX", position: "right", fontSize: 8, fill: "#555" }}
            />
            <Area
              type="monotone"
              dataKey="iv"
              stroke="#fff"
              strokeWidth={1.5}
              fill="url(#volGrad)"
              dot={<CustomDot />}
              activeDot={{ r: 4, fill: "#000", stroke: "#fff", strokeWidth: 1.5 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Expiry strip table */}
      <div className="shrink-0 border-t border-border pt-1.5 overflow-x-auto">
        <table className="w-full text-[10px]">
          <thead>
            <tr className="text-muted-foreground uppercase">
              {data.expiries.map((e: any) => (
                <th key={e.label} className="text-center font-normal pb-1 px-1">
                  {e.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {data.expiries.map((e: any) => (
                <td
                  key={e.label}
                  className={`text-center font-bold font-mono px-1 py-0.5 border-t border-border/40 ${e.isContango ? "text-white" : "text-gray-500"}`}
                >
                  {e.iv.toFixed(1)}%
                </td>
              ))}
            </tr>
            <tr>
              {data.expiries.map((e: any) => (
                <td key={e.label} className="text-center font-mono text-muted-foreground px-1 py-0.5">
                  ${e.atmPremium.toFixed(1)}
                </td>
              ))}
            </tr>
            <tr>
              {data.expiries.map((e: any) => (
                <td key={e.label} className="text-center px-1 py-0.5">
                  <span className={`text-[8px] ${e.isContango ? "text-white/60" : "text-gray-600"}`}>
                    {e.isContango ? "↗" : "↘"}
                  </span>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
