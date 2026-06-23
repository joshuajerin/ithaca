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
  Legend,
} from "recharts";

interface SovereignSeries {
  code: string;
  name: string;
  currency: string;
  color: string;
}

interface SovereignSpread {
  label: string;
  tenor: string;
  value: number;
  base: string;
  other: string;
}

interface SovereignComparePanelProps {
  data: {
    title: string;
    series: SovereignSeries[];
    points: Array<Record<string, number | string>>;
    spreads: SovereignSpread[];
  };
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-black border border-white/20 p-2 shadow-xl text-xs">
        <p className="text-muted-foreground mb-1">{label}</p>
        {payload.map((p: any) => (
          <p key={p.dataKey} style={{ color: p.color }} className="font-mono">
            {p.name}: {p.value?.toFixed(2)}%
          </p>
        ))}
      </div>
    );
  }
  return null;
};

export function SovereignComparePanel({ data }: SovereignComparePanelProps) {
  const { series, points, spreads } = data;

  // Group spreads by tenor so each tenor block lists its cross-market values.
  const tenors = Array.from(new Set(spreads.map((s) => s.tenor)));

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex justify-between items-start mb-3 shrink-0 gap-3">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">
            {data.title}
          </div>
          <div className="flex flex-wrap gap-2">
            {series.map((s) => (
              <div key={s.code} className="flex items-center gap-1.5">
                <span
                  className="inline-block w-2.5 h-2.5 rounded-sm"
                  style={{ backgroundColor: s.color }}
                />
                <span className="text-[10px] text-white font-medium">{s.name}</span>
                <span className="text-[9px] text-muted-foreground">{s.currency}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="flex gap-3 shrink-0 flex-wrap justify-end">
          {tenors.map((tenor) => (
            <div key={tenor} className="text-right">
              <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">
                {tenor} spread
              </div>
              {spreads
                .filter((s) => s.tenor === tenor)
                .map((s) => (
                  <div key={s.label} className="flex items-center justify-end gap-1.5">
                    <span className="text-[8px] text-muted-foreground uppercase">
                      {s.base}–{s.other}
                    </span>
                    <span
                      className={`text-sm font-bold font-mono ${
                        s.value < 0 ? "text-red-400" : "text-white"
                      }`}
                    >
                      {s.value > 0 ? "+" : ""}
                      {s.value.toFixed(0)}bp
                    </span>
                  </div>
                ))}
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 w-full min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="#333" vertical={false} />
            <XAxis
              dataKey="tenor"
              tick={{ fontSize: 9, fill: "#666" }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fontSize: 9, fill: "#666" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v.toFixed(1)}%`}
            />
            <Tooltip content={<CustomTooltip />} />
            {series.map((s, i) => (
              <Line
                key={s.code}
                type="monotone"
                dataKey={s.code}
                name={s.name}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 3, fill: "#000", stroke: s.color, strokeWidth: 1.5 }}
                strokeDasharray={i === 0 ? undefined : i === 1 ? "4 2" : i === 2 ? "2 3" : "6 3"}
              />
            ))}
            <Legend
              iconType="line"
              iconSize={12}
              wrapperStyle={{ fontSize: "9px", color: "#666", paddingTop: "4px" }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
