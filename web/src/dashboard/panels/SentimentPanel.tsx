// @ts-nocheck
// Light-theme copy of web/src/components/terminal/panels/SentimentPanel.tsx
// DO NOT edit the original at web/src/components/terminal/panels/.
import React from "react";
import type { SentimentData } from "@workspace/api-client-react";
import { ResponsiveContainer, AreaChart, Area, XAxis, Tooltip, CartesianGrid } from "recharts";

export function SentimentPanel({ data }: { data: SentimentData }) {
  const isPositive = data.overall > 0;

  return (
    <div className="panel-light" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20, flexShrink: 0 }}>
        <div>
          <div className="editorial-label" style={{ fontSize: 9, color: "var(--muted)", marginBottom: 6 }}>{data.scope} Sentiment</div>
          <div style={{ fontFamily: "Georgia, serif", fontSize: 28, lineHeight: 1, color: "var(--fg)", textTransform: "capitalize" }}>
            {data.label.replace('_', ' ').toLowerCase()}
          </div>
        </div>
        <div style={{ fontFamily: "Georgia, serif", fontSize: 36, lineHeight: 1, color: isPositive ? "var(--pos)" : "var(--neg)" }}>
          {data.overall > 0 ? '+' : ''}{data.overall.toFixed(2)}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 24px", marginBottom: 20, flexShrink: 0 }}>
        {data.sources.map((source: any) => (
          <div key={source.channel} style={{ borderTop: "1px solid var(--border-soft)", paddingTop: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
              <span className="editorial-label" style={{ fontSize: 8.5, color: "var(--muted)" }}>{source.channel}</span>
              <span style={{ fontFamily: "Georgia, serif", fontSize: 13, color: source.score > 0 ? "var(--pos)" : "var(--neg)" }}>
                {source.score > 0 ? '+' : ''}{source.score.toFixed(1)}
              </span>
            </div>
            <div style={{ width: "100%", height: 4, background: "var(--panel-2)", borderRadius: 999, overflow: "hidden" }}>
              <div style={{
                height: "100%",
                background: source.score > 0 ? "var(--pos)" : "var(--neg)",
                width: `${Math.min(100, Math.abs(source.score) * 100)}%`,
                marginLeft: source.score < 0 ? `${100 - Math.min(100, Math.abs(source.score) * 100)}%` : '0',
                borderRadius: 999,
              }} />
            </div>
          </div>
        ))}
      </div>

      <div style={{ flex: 1, minHeight: 80 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data.trend} margin={{ top: 5, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="sentGradLight" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={isPositive ? "var(--pos)" : "var(--neg)"} stopOpacity={0.25} />
                <stop offset="95%" stopColor={isPositive ? "var(--pos)" : "var(--neg)"} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="1 3" stroke="var(--border-soft)" vertical={false} />
            <XAxis dataKey="t" tick={{ fontSize: 9, fill: "var(--muted)", fontFamily: "var(--font-sans)", letterSpacing: "0.08em" }} tickLine={false} axisLine={false} minTickGap={20} />
            <Tooltip
              contentStyle={{ backgroundColor: "var(--surface)", borderColor: "var(--border)", borderRadius: "var(--radius-sm)", color: "var(--fg)", fontFamily: "var(--font-mono)" }}
              itemStyle={{ color: "var(--fg)" }}
              labelStyle={{ color: "var(--muted)", fontFamily: "var(--font-sans)", textTransform: "uppercase", letterSpacing: "0.12em", fontSize: 9 }}
              formatter={(value: number) => [value.toFixed(2), 'Score']}
            />
            <Area type="monotone" dataKey="score" stroke={isPositive ? "var(--pos)" : "var(--neg)"} fillOpacity={1} fill="url(#sentGradLight)" strokeWidth={1.5} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
