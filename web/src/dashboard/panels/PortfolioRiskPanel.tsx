// @ts-nocheck
// Light-theme copy of web/src/components/terminal/panels/PortfolioRiskPanel.tsx
// DO NOT edit the original at web/src/components/terminal/panels/.
import React, { useState } from "react";
import type { PortfolioRiskData } from "@workspace/api-client-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  ReferenceLine,
} from "recharts";

interface Props {
  data: PortfolioRiskData;
  onRefine?: (params: Record<string, unknown>) => void;
  pending?: boolean;
}

export function PortfolioRiskPanel({ data, onRefine, pending }: Props) {
  const { summary, varHistogram, factorExposures } = data;
  const [draft, setDraft] = useState("");
  const symbols = data.symbols;

  const removeSymbol = (s: string) => {
    if (symbols.length <= 1) return;
    onRefine?.({ symbols: symbols.filter((x) => x !== s) });
  };

  const addSymbol = (e: React.FormEvent) => {
    e.preventDefault();
    const t = draft.trim().toUpperCase();
    setDraft("");
    if (!t || symbols.includes(t)) return;
    onRefine?.({ symbols: [...symbols, t] });
  };

  const maxCount = Math.max(...varHistogram.map((b) => b.count));

  const VarTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", padding: 8, fontSize: 11 }}>
          <p style={{ color: "var(--muted)" }}>P&L: {label}%</p>
          <p style={{ color: "var(--fg)", fontWeight: 700 }}>Count: {payload[0].value}</p>
        </div>
      );
    }
    return null;
  };

  const FactorTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", padding: 8, fontSize: 11 }}>
          <p style={{ color: "var(--muted)" }}>{label}</p>
          <p style={{ color: "var(--fg)", fontWeight: 700 }}>Exposure: {payload[0].value.toFixed(2)}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="panel-light" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 12 }}>
      <div style={{ position: "relative", flex: 1, display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
        {pending && (
          <div style={{ position: "absolute", inset: 0, zIndex: 10, background: "rgba(255,253,247,0.7)", display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
            <span style={{ color: "var(--muted)", fontSize: 11 }}>Updating…</span>
          </div>
        )}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, flexShrink: 0 }}>
          <div style={{ border: "1px solid var(--border-soft)", padding: 8, borderRadius: "var(--radius-sm)" }}>
            <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 4 }}>1-Day 95% VaR</div>
            <div style={{ fontSize: 18, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--neg)" }}>-{summary.var95.toFixed(2)}%</div>
          </div>
          <div style={{ border: "1px solid var(--border-soft)", padding: 8, borderRadius: "var(--radius-sm)" }}>
            <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 4 }}>Tracking Error</div>
            <div style={{ fontSize: 18, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--fg)" }}>{summary.trackingError.toFixed(2)}%</div>
          </div>
          <div style={{ border: "1px solid var(--border-soft)", padding: 8, borderRadius: "var(--radius-sm)" }}>
            <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 4 }}>Portfolio Beta</div>
            <div style={{ fontSize: 18, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--fg)" }}>{summary.beta.toFixed(2)}</div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 12, flex: 1, minHeight: 0 }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 4, flexShrink: 0 }}>P&L Distribution (VaR)</div>
            <div style={{ flex: 1, minHeight: 80 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={varHistogram} margin={{ top: 2, right: 0, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="var(--border-soft)" vertical={false} />
                  <XAxis dataKey="bin" tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} minTickGap={20} tickFormatter={(v) => `${v}%`} />
                  <YAxis tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} />
                  <Tooltip content={<VarTooltip />} />
                  <ReferenceLine x={-summary.var95} stroke="var(--neg)" strokeDasharray="3 3" strokeWidth={1.5} />
                  <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                    {varHistogram.map((entry, idx) => (
                      <Cell
                        key={idx}
                        fill={entry.bin <= -summary.var95 ? "var(--neg)" : "var(--accent)"}
                        fillOpacity={entry.bin <= -summary.var95 ? 0.6 : 0.25 + 0.5 * (entry.count / maxCount)}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div style={{ width: 140, display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 4, flexShrink: 0 }}>Factor Exposures</div>
            <div style={{ flex: 1, minHeight: 80 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={factorExposures} layout="vertical" margin={{ top: 2, right: 8, left: 8, bottom: 2 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="var(--border-soft)" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} domain={[-1, 2]} />
                  <YAxis type="category" dataKey="factor" tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} width={52} />
                  <Tooltip content={<FactorTooltip />} />
                  <ReferenceLine x={0} stroke="var(--border)" strokeWidth={1} />
                  <Bar dataKey="exposure" radius={[0, 2, 2, 0]}>
                    {factorExposures.map((entry, idx) => (
                      <Cell key={idx} fill={entry.exposure >= 0 ? "var(--fg)" : "var(--muted)"} fillOpacity={0.6} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      <div style={{ flexShrink: 0 }}>
        <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 6 }}>Holdings</div>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
          {symbols.map((s) => (
            <span key={s} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, border: "1px solid var(--border-soft)", padding: "2px 8px", fontFamily: "var(--font-mono)", color: "var(--fg)", borderRadius: "var(--radius-sm)" }}>
              {s}
              {onRefine && symbols.length > 1 && (
                <button type="button" disabled={pending} onClick={() => removeSymbol(s)} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", padding: 0, fontSize: 11, lineHeight: 1 }} aria-label={`Remove ${s}`}>×</button>
              )}
            </span>
          ))}
          {onRefine && (
            <form onSubmit={addSymbol}>
              <input value={draft} disabled={pending} onChange={(e) => setDraft(e.target.value)} placeholder="+ ticker" aria-label="Add ticker" spellCheck={false}
                style={{ width: 60, background: "transparent", border: "1px dashed var(--border)", padding: "2px 6px", fontSize: 10, fontFamily: "var(--font-mono)", textTransform: "uppercase", color: "var(--fg)", outline: "none", borderRadius: "var(--radius-sm)" }} />
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
