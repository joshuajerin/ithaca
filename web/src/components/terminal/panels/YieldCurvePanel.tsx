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
  ReferenceLine,
} from "recharts";
import { ScrollArea } from "@/components/ui/scroll-area";

interface YieldCurvePanelProps {
  data: any;
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

const RECESSION_STYLES: Record<string, { wrap: string; dot: string; label: string }> = {
  warning: {
    wrap: "border-red-500/40 bg-red-500/10",
    dot: "bg-red-400",
    label: "text-red-300",
  },
  watch: {
    wrap: "border-yellow-400/40 bg-yellow-400/10",
    dot: "bg-yellow-400",
    label: "text-yellow-300",
  },
  normal: {
    wrap: "border-emerald-500/30 bg-emerald-500/10",
    dot: "bg-emerald-400",
    label: "text-emerald-300",
  },
};

export function YieldCurvePanel({ data }: YieldCurvePanelProps) {
  const inversionZone = data.spreads.find((s: any) => s.label === "2Y–10Y");
  const isInverted = inversionZone?.inverted ?? false;
  const recession = data.recession;
  const style = RECESSION_STYLES[recession?.level as string] ?? RECESSION_STYLES.normal;

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex justify-between items-start mb-3 shrink-0">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">
            {data.title}
          </div>
          {recession ? (
            <div
              className={`text-[10px] font-bold uppercase tracking-wider ${style.label} border ${style.wrap} px-2 py-0.5 inline-flex items-center gap-1.5`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${style.dot} ${recession.level !== "normal" ? "animate-pulse" : ""}`} />
              {recession.headline}
            </div>
          ) : (
            isInverted && (
              <div className="text-[10px] font-bold uppercase tracking-wider text-yellow-400 border border-yellow-400/40 bg-yellow-400/10 px-2 py-0.5 inline-block">
                ⚠ Curve Inverted
              </div>
            )
          )}
        </div>
        <div className="flex gap-3 shrink-0">
          {data.spreads.map((s: { label: string; value: number; inverted: boolean }) => (
            <div key={s.label} className="text-right">
              <div className="text-[9px] text-muted-foreground uppercase tracking-widest">{s.label}</div>
              <div className={`text-sm font-bold font-mono ${s.inverted ? "text-yellow-400" : "text-white"}`}>
                {s.value > 0 ? "+" : ""}{s.value.toFixed(0)}bp
              </div>
            </div>
          ))}
        </div>
      </div>

      {recession && (
        <div className={`mb-3 shrink-0 border ${style.wrap} px-3 py-2`}>
          <p className="text-[11px] leading-snug text-foreground/90">{recession.detail}</p>
          {recession.segments?.some((seg: any) => seg.inverted && seg.days) && (
            <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
              {recession.segments
                .filter((seg: any) => seg.inverted && seg.days)
                .map((seg: any) => (
                  <div key={seg.label} className="text-[9px] uppercase tracking-widest text-muted-foreground">
                    {seg.label} inverted{" "}
                    <span className={`font-mono ${style.label}`}>{seg.days}d</span>
                    {seg.since ? <span className="text-muted-foreground/70"> · since {seg.since}</span> : null}
                  </div>
                ))}
            </div>
          )}
        </div>
      )}

      <div className="flex-1 w-full min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.points} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
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
            {isInverted && (
              <ReferenceLine
                y={data.points.find((p: { tenor: string; spot: number }) => p.tenor === "2Y")?.spot ?? 0}
                stroke="#fbbf24"
                strokeDasharray="3 3"
                strokeOpacity={0.4}
              />
            )}
            <Line
              type="monotone"
              dataKey="spot"
              name="Current"
              stroke="#ffffff"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 3, fill: "#000", stroke: "#fff", strokeWidth: 1.5 }}
            />
            <Line
              type="monotone"
              dataKey="ago1y"
              name="1Y Ago"
              stroke="#6b7280"
              strokeWidth={1.5}
              strokeDasharray="4 2"
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="ago2y"
              name="2Y Ago"
              stroke="#374151"
              strokeWidth={1.5}
              strokeDasharray="2 3"
              dot={false}
            />
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
