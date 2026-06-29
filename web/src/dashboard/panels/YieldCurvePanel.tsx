// @ts-nocheck
// Light-theme copy of web/src/components/terminal/panels/YieldCurvePanel.tsx
// DO NOT edit the original at web/src/components/terminal/panels/.
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

interface YieldCurvePanelProps {
  data: any;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", padding: 8, fontSize: 11, boxShadow: "0 4px 12px rgba(26,26,20,0.1)" }}>
        <p style={{ color: "var(--muted)", marginBottom: 4 }}>{label}</p>
        {payload.map((p: any) => (
          <p key={p.dataKey} style={{ color: p.color, fontFamily: "var(--font-mono)" }}>{p.name}: {p.value?.toFixed(2)}%</p>
        ))}
      </div>
    );
  }
  return null;
};

const RECESSION_STYLES: Record<string, { border: string; bg: string; dot: string; label: string }> = {
  warning: { border: "rgba(182,66,53,0.35)", bg: "rgba(182,66,53,0.07)", dot: "var(--neg)", label: "var(--neg)" },
  watch: { border: "rgba(201,121,26,0.35)", bg: "rgba(201,121,26,0.07)", dot: "var(--warn)", label: "var(--warn)" },
  normal: { border: "rgba(47,143,73,0.3)", bg: "rgba(47,143,73,0.07)", dot: "var(--pos)", label: "var(--pos)" },
};

export function YieldCurvePanel({ data }: YieldCurvePanelProps) {
  const inversionZone = data.spreads.find((s: any) => s.label === "2Y–10Y");
  const isInverted = inversionZone?.inverted ?? false;
  const recession = data.recession;
  const style = RECESSION_STYLES[recession?.level as string] ?? RECESSION_STYLES.normal;

  return (
    <div className="panel-light" style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12, flexShrink: 0 }}>
        <div>
          <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 6 }}>{data.title}</div>
          {recession ? (
            <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: style.label, border: `1px solid ${style.border}`, background: style.bg, padding: "2px 8px", display: "inline-flex", alignItems: "center", gap: 6, borderRadius: "var(--radius-sm)" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: style.dot, display: "inline-block" }} />
              {recession.headline}
            </div>
          ) : isInverted ? (
            <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--warn)", border: "1px solid rgba(201,121,26,0.35)", background: "rgba(201,121,26,0.07)", padding: "2px 8px", display: "inline-block", borderRadius: "var(--radius-sm)" }}>
              ⚠ Curve Inverted
            </div>
          ) : null}
        </div>
        <div style={{ display: "flex", gap: 12, flexShrink: 0 }}>
          {data.spreads.map((s: { label: string; value: number; inverted: boolean }) => (
            <div key={s.label} style={{ textAlign: "right" }}>
              <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em" }}>{s.label}</div>
              <div style={{ fontSize: 13, fontWeight: 700, fontFamily: "var(--font-mono)", color: s.inverted ? "var(--warn)" : "var(--fg)" }}>{s.value > 0 ? "+" : ""}{s.value.toFixed(0)}bp</div>
            </div>
          ))}
        </div>
      </div>

      {recession && (
        <div style={{ marginBottom: 12, flexShrink: 0, border: `1px solid ${style.border}`, background: style.bg, padding: "10px 12px", borderRadius: "var(--radius-sm)" }}>
          <p style={{ fontSize: 11, lineHeight: 1.5, color: "var(--fg)", margin: 0 }}>{recession.detail}</p>
          {recession.segments?.some((seg: any) => seg.inverted && seg.days) && (
            <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: "4px 16px" }}>
              {recession.segments.filter((seg: any) => seg.inverted && seg.days).map((seg: any) => (
                <div key={seg.label} style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--muted)" }}>
                  {seg.label} inverted <span style={{ fontFamily: "var(--font-mono)", color: style.label }}>{seg.days}d</span>
                  {seg.since ? <span style={{ color: "var(--muted-dim)" }}> · since {seg.since}</span> : null}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ flex: 1, minHeight: 0, width: "100%" }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.points} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="var(--border-soft)" vertical={false} />
            <XAxis dataKey="tenor" tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} />
            <YAxis domain={["auto", "auto"]} tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v.toFixed(1)}%`} />
            <Tooltip content={<CustomTooltip />} />
            {isInverted && (
              <ReferenceLine y={data.points.find((p: any) => p.tenor === "2Y")?.spot ?? 0} stroke="var(--warn)" strokeDasharray="3 3" strokeOpacity={0.5} />
            )}
            <Line type="monotone" dataKey="spot" name="Current" stroke="var(--fg)" strokeWidth={2} dot={false} activeDot={{ r: 3, fill: "var(--surface)", stroke: "var(--fg)", strokeWidth: 1.5 }} />
            <Line type="monotone" dataKey="ago1y" name="1Y Ago" stroke="var(--muted)" strokeWidth={1.5} strokeDasharray="4 2" dot={false} />
            <Line type="monotone" dataKey="ago2y" name="2Y Ago" stroke="var(--border)" strokeWidth={1.5} strokeDasharray="2 3" dot={false} />
            <Legend iconType="line" iconSize={12} wrapperStyle={{ fontSize: "9px", color: "var(--muted)", paddingTop: "4px" }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
