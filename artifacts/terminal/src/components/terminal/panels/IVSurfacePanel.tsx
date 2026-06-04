import React, { useMemo } from "react";

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

interface IVSurfacePanelProps {
  data: any;
}

function ivColor(iv: number, minIv: number, maxIv: number): string {
  const t = maxIv === minIv ? 0.5 : (iv - minIv) / (maxIv - minIv);
  // dark blue -> white -> deep amber
  if (t < 0.5) {
    const u = t * 2;
    const r = Math.round(20 + u * 235);
    const g = Math.round(40 + u * 215);
    const b = Math.round(180 + u * 75);
    return `rgb(${r},${g},${b})`;
  } else {
    const u = (t - 0.5) * 2;
    const r = Math.round(255);
    const g = Math.round(255 - u * 170);
    const b = Math.round(255 - u * 240);
    return `rgb(${r},${g},${b})`;
  }
}

export function IVSurfacePanel({ data }: IVSurfacePanelProps) {
  const ivValues = data.surface.map((c: any) => c.iv);
  const minIv = Math.min(...ivValues);
  const maxIv = Math.max(...ivValues);

  // Build cell lookup: expiry -> strike -> iv
  const cellMap = useMemo(() => {
    const m: Record<string, Record<number, number>> = {};
    for (const cell of data.surface) {
      if (!m[cell.expiry]) m[cell.expiry] = {};
      m[cell.expiry][cell.strike] = cell.iv;
    }
    return m;
  }, [data.surface]);

  const atmStrike = data.strikes.reduce((closest: any, s: any) =>
    Math.abs(s - data.underlyingPrice) < Math.abs(closest - data.underlyingPrice) ? s : closest
  );

  return (
    <div className="flex flex-col h-full w-full gap-2">
      {/* Header */}
      <div className="flex justify-between items-baseline shrink-0">
        <div className="flex items-baseline gap-2">
          <span className="text-xl font-bold">{data.symbol}</span>
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest">
            IV Surface
          </span>
        </div>
        <div className="text-right">
          <span className="text-xs text-muted-foreground mr-2">Spot</span>
          <span className="text-sm font-bold font-mono">${data.underlyingPrice.toFixed(2)}</span>
          <span className="ml-3 text-xs text-muted-foreground mr-1">ATM IV</span>
          <span className="text-sm font-bold font-mono text-white">{data.atmIv.toFixed(1)}%</span>
        </div>
      </div>

      {/* Heatmap grid */}
      <div className="flex-1 overflow-auto min-h-0">
        <table className="w-full text-[10px] border-collapse">
          <thead>
            <tr>
              <th className="text-left text-muted-foreground py-1 pr-2 font-normal w-10">Strike</th>
              {data.expiries.map((exp: any) => (
                <th key={exp} className="text-center text-muted-foreground py-1 font-normal px-0.5">
                  {exp}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.strikes.map((strike: any) => {
              const isAtm = strike === atmStrike;
              return (
                <tr key={strike} className={isAtm ? "outline outline-1 outline-white/40" : ""}>
                  <td className={`pr-2 py-0.5 font-mono font-bold text-right ${isAtm ? "text-white" : "text-muted-foreground"}`}>
                    {strike.toFixed(0)}
                    {isAtm && <span className="ml-1 text-[8px] text-white/60">ATM</span>}
                  </td>
                  {data.expiries.map((exp: any) => {
                    const iv = cellMap[exp]?.[strike];
                    if (iv === undefined) return <td key={exp} className="px-0.5" />;
                    const bg = ivColor(iv, minIv, maxIv);
                    return (
                      <td
                        key={exp}
                        className="text-center py-0.5 px-0.5 font-mono cursor-default"
                        style={{ backgroundColor: bg, color: iv > (minIv + maxIv) / 2 ? "#000" : "#fff" }}
                        title={`${exp} / $${strike} → IV ${iv.toFixed(1)}%`}
                      >
                        {iv.toFixed(1)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Skew strip */}
      <div className="shrink-0 h-20 w-full border-t border-border pt-1">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
          1M Skew Strip
        </div>
        <ResponsiveContainer width="100%" height="80%">
          <LineChart data={data.skew} margin={{ top: 2, right: 4, left: -28, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="#222" vertical={false} />
            <XAxis
              dataKey="moneyness"
              tick={{ fontSize: 8, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v > 0 ? "+" : ""}${v.toFixed(0)}%`}
            />
            <YAxis
              tick={{ fontSize: 8, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v.toFixed(0)}%`}
            />
            <Tooltip
              contentStyle={{ backgroundColor: "#000", borderColor: "#333", fontSize: 10 }}
              formatter={(v: number) => [`${v.toFixed(1)}%`, "IV"]}
              labelFormatter={(v) => `Moneyness ${v}%`}
            />
            <ReferenceLine x={0} stroke="#444" strokeDasharray="3 3" />
            <Line
              type="monotone"
              dataKey="iv"
              stroke="#fff"
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, fill: "#000", stroke: "#fff", strokeWidth: 1 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
