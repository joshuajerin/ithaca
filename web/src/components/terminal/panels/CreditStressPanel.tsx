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
} from "recharts";

interface CreditSeries {
  code: string;
  name: string;
  color: string;
}

interface CreditMetric {
  code: string;
  label: string;
  current: number;
  monthAgo: number;
  change1m: number;
  changeWindow: number;
  min: number;
  max: number;
  percentile: number;
  widening: boolean;
}

interface CreditRegime {
  label: string;
  tone: "risk-off" | "risk-on" | "neutral";
  note: string;
}

interface CreditStressPanelProps {
  data: {
    title: string;
    series: CreditSeries[];
    points: Array<Record<string, number | string>>;
    metrics: CreditMetric[];
    regime: CreditRegime;
    windowDays?: number;
  };
}

const TONE_STYLES: Record<string, { dot: string; text: string; border: string }> = {
  "risk-off": { dot: "bg-red-400", text: "text-red-300", border: "border-red-500/40" },
  "risk-on": { dot: "bg-emerald-400", text: "text-emerald-300", border: "border-emerald-500/40" },
  neutral: { dot: "bg-yellow-300", text: "text-yellow-200", border: "border-yellow-500/30" },
};

const colorFor = (series: CreditSeries[], code: string) =>
  series.find((s) => s.code === code)?.color ?? "#999";

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-black border border-white/20 p-2 shadow-xl text-xs">
        <p className="text-muted-foreground mb-1">{label}</p>
        {payload.map((p: any) => (
          <p key={p.dataKey} style={{ color: p.color }} className="font-mono">
            {p.name}: {p.value?.toFixed(0)}bp
          </p>
        ))}
      </div>
    );
  }
  return null;
};

export function CreditStressPanel({ data }: CreditStressPanelProps) {
  const { series, points, metrics, regime } = data;
  const tone = TONE_STYLES[regime?.tone] ?? TONE_STYLES.neutral;

  return (
    <div className="flex flex-col h-full w-full">
      {/* Regime banner */}
      <div
        className={`shrink-0 mb-3 flex items-start gap-2 border px-3 py-2 ${tone.border} bg-white/[0.02]`}
      >
        <span className={`mt-1 inline-block w-2 h-2 rounded-full ${tone.dot}`} />
        <div className="min-w-0">
          <div className={`text-[11px] font-semibold uppercase tracking-widest ${tone.text}`}>
            {regime?.label}
          </div>
          {regime?.note && (
            <div className="text-[10px] text-muted-foreground mt-0.5 leading-snug">
              {regime.note}
            </div>
          )}
        </div>
      </div>

      {/* Metric tiles */}
      <div className="shrink-0 grid grid-cols-2 gap-2 mb-3">
        {metrics.map((m) => {
          const up = m.change1m > 0;
          return (
            <div
              key={m.code}
              className="border border-border px-3 py-2 bg-white/[0.015]"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
                    style={{ backgroundColor: colorFor(series, m.code) }}
                  />
                  <span className="text-[10px] text-white font-medium truncate">
                    {m.label}
                  </span>
                </div>
                {m.widening && (
                  <span className="text-[8px] uppercase tracking-wider text-red-300 border border-red-500/40 px-1 py-px shrink-0">
                    Widening
                  </span>
                )}
              </div>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-xl font-bold font-mono text-white">
                  {m.current.toFixed(0)}
                  <span className="text-[10px] text-muted-foreground ml-0.5">bp</span>
                </span>
                <span
                  className={`text-[11px] font-mono ${up ? "text-red-400" : "text-emerald-400"}`}
                >
                  {up ? "+" : ""}
                  {m.change1m.toFixed(0)}bp 1M
                </span>
              </div>
              <div className="flex items-center justify-between text-[9px] text-muted-foreground mt-1 font-mono">
                <span>
                  range {m.min.toFixed(0)}–{m.max.toFixed(0)}
                </span>
                <span>{m.percentile.toFixed(0)}th pct</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Trend chart */}
      <div className="flex-1 w-full min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 4, right: 6, left: -18, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="#333" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 9, fill: "#666" }}
              tickLine={false}
              axisLine={false}
              minTickGap={40}
              tickFormatter={(v) =>
                typeof v === "string" ? v.slice(5) : v
              }
            />
            <YAxis
              yAxisId="ig"
              domain={["auto", "auto"]}
              tick={{ fontSize: 9, fill: "#666" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v.toFixed(0)}`}
            />
            <YAxis
              yAxisId="hy"
              orientation="right"
              domain={["auto", "auto"]}
              tick={{ fontSize: 9, fill: "#666" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v.toFixed(0)}`}
            />
            <Tooltip content={<CustomTooltip />} />
            {series.map((s) => (
              <Line
                key={s.code}
                yAxisId={s.code === "HY" ? "hy" : "ig"}
                type="monotone"
                dataKey={s.code}
                name={s.name}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 3, fill: "#000", stroke: s.color, strokeWidth: 1.5 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="shrink-0 flex items-center justify-between text-[8px] text-muted-foreground mt-1.5 uppercase tracking-widest">
        <span>
          <span style={{ color: colorFor(series, "IG") }}>IG</span> left axis ·{" "}
          <span style={{ color: colorFor(series, "HY") }}>HY</span> right axis (bp)
        </span>
        {data.windowDays && <span>{data.windowDays}-day window</span>}
      </div>
    </div>
  );
}
