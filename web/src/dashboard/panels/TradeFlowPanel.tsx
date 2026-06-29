// @ts-nocheck
// Light-theme copy of web/src/components/terminal/panels/TradeFlowPanel.tsx
// DO NOT edit the original at web/src/components/terminal/panels/.
import React from "react";
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";

function DarkPoolGauge({ pct }: { pct: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted)" }}>Dark Pool</div>
      <div style={{ position: "relative", width: "100%", height: 6, background: "var(--panel-2)", borderRadius: 999, overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: "0 auto 0 0", background: "var(--muted)", width: `${pct}%` }} />
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--fg)" }}>{pct.toFixed(1)}%</div>
    </div>
  );
}

export function TradeFlowPanel({ data }: { data: any }) {
  const imbalancePct = Math.round(data.buyImbalance * 100);
  const netBuy = data.buyImbalance >= 0.5;

  const scatterData = data.prints.map((p: any) => ({
    x: p.time, y: p.price,
    z: Math.sqrt(p.size) * 0.4,
    side: p.side, isBlock: p.isBlock, isDark: p.isDark,
    size: p.size, venue: p.venue,
  }));

  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0]?.payload;
    if (!d) return null;
    return (
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", fontSize: 11, padding: 8 }}>
        <div style={{ fontWeight: 700, textTransform: "uppercase", fontSize: 10, letterSpacing: "0.1em", color: "var(--fg)" }}>{d.isBlock ? "BLOCK" : "PRINT"}{d.isDark ? " · DARK" : ""}</div>
        <div style={{ fontFamily: "var(--font-mono)", color: "var(--fg)" }}>{d.x} · ${d.y.toFixed(2)}</div>
        <div style={{ color: "var(--muted)" }}>{d.size.toLocaleString()} shares · {d.venue}</div>
        <div style={{ color: d.side === "buy" ? "var(--pos)" : "var(--neg)" }}>{d.side.toUpperCase()}</div>
      </div>
    );
  };

  return (
    <div className="panel-light" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <div>
          <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em" }}>{data.symbol} · Trade Flow</div>
          <div style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", color: "var(--fg)" }}>
            {netBuy ? "Net Buy" : "Net Sell"}{" "}
            <span style={{ fontFamily: "var(--font-mono)", color: "var(--muted)", fontSize: 11 }}>{imbalancePct}% buy</span>
          </div>
        </div>
        <div style={{ textAlign: "right", fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em" }}>
          <div>{(data.totalVolume / 1_000_000).toFixed(1)}M vol</div>
          <div>{data.prints.filter((p: any) => p.isBlock).length} blocks</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 16, flexShrink: 0 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted)", marginBottom: 4 }}>Buy / Sell Imbalance</div>
          <div style={{ position: "relative", height: 6, background: "var(--panel-2)", borderRadius: 999, overflow: "hidden" }}>
            <div style={{ position: "absolute", inset: "0 auto 0 0", background: "var(--pos)", width: `${imbalancePct}%` }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, fontFamily: "var(--font-mono)", marginTop: 3 }}>
            <span style={{ color: "var(--pos)" }}>{imbalancePct}% B</span>
            <span style={{ color: "var(--neg)" }}>{100 - imbalancePct}% S</span>
          </div>
        </div>
        <div style={{ width: 96 }}>
          <DarkPoolGauge pct={data.darkPoolPct} />
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 80 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="var(--border-soft)" />
            <XAxis dataKey="x" type="category" tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
            <YAxis dataKey="y" type="number" domain={["auto", "auto"]} tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v.toFixed(0)}`} />
            <Tooltip content={<CustomTooltip />} />
            <Scatter data={scatterData}>
              {scatterData.map((entry: any, idx: any) => (
                <Cell
                  key={idx}
                  fill={entry.isBlock ? "var(--fg)" : entry.side === "buy" ? "var(--pos)" : "var(--neg)"}
                  opacity={entry.isDark ? 0.45 : 0.75}
                  r={entry.isBlock ? Math.max(4, entry.z / 4) : Math.max(2, entry.z / 8)}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <div style={{ flexShrink: 0, display: "flex", gap: 12, fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--fg)", opacity: 0.7 }} /> Block ≥{(data.blockThreshold / 1000).toFixed(0)}K
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--muted)", opacity: 0.4 }} /> Dark Pool
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--pos)" }} /> Buy
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--neg)" }} /> Sell
        </span>
      </div>
    </div>
  );
}
