// @ts-nocheck
// Light-theme copy of web/src/components/terminal/panels/MacroDashboardPanel.tsx
// DO NOT edit the original at web/src/components/terminal/panels/.
import React from "react";
import { LineChart, Line, ResponsiveContainer } from "recharts";

function formatPrice(price: number, unit: string): string {
  if (unit === "%") return `${price.toFixed(2)}%`;
  if (unit === "bps") return `${price >= 0 ? "+" : ""}${price.toFixed(0)} bps`;
  if (unit === "FX") return price.toFixed(4);
  if (price >= 10000) return price.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (price >= 100) return price.toFixed(2);
  return price.toFixed(4);
}

function Sparkline({ data, positive }: { data: number[]; positive: boolean }) {
  const points = data.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={28}>
      <LineChart data={points} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
        <Line type="monotone" dataKey="v" stroke={positive ? "var(--pos)" : "var(--neg)"} strokeWidth={1.2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

const REGIME_STYLES: Record<string, { border: string; bg: string; dot: string; text: string }> = {
  risk_on: { border: "rgba(47,143,73,0.35)", bg: "rgba(47,143,73,0.08)", dot: "var(--pos)", text: "var(--pos)" },
  risk_off: { border: "rgba(182,66,53,0.35)", bg: "rgba(182,66,53,0.08)", dot: "var(--neg)", text: "var(--neg)" },
  stagflation: { border: "rgba(201,121,26,0.35)", bg: "rgba(201,121,26,0.08)", dot: "var(--warn)", text: "var(--warn)" },
  soft_landing: { border: "rgba(47,107,229,0.35)", bg: "rgba(47,107,229,0.08)", dot: "var(--info)", text: "var(--info)" },
  neutral: { border: "var(--border-soft)", bg: "transparent", dot: "var(--muted)", text: "var(--muted)" },
};

function RegimeBanner({ regime }: { regime: any }) {
  const style = REGIME_STYLES[regime.label] ?? REGIME_STYLES.neutral;
  const headline = regime.headline ?? String(regime.label ?? "").replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", border: `1px solid ${style.border}`, background: style.bg, borderRadius: "var(--radius-sm)", flexShrink: 0 }}>
      <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: style.dot, flexShrink: 0 }} />
      <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.16em", color: style.text, flexShrink: 0 }}>{headline}</span>
      <span style={{ fontSize: 9, color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{regime.rationale}</span>
    </div>
  );
}

function AssetTile({ tile }: { tile: any }) {
  const isPositive = tile.changePct >= 0;
  return (
    <div style={{
      display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 8, minWidth: 0,
      border: `1px solid ${isPositive ? "rgba(47,143,73,0.2)" : "rgba(182,66,53,0.18)"}`,
      background: isPositive ? "rgba(47,143,73,0.04)" : "rgba(182,66,53,0.03)",
      borderRadius: "var(--radius-sm)",
      transition: "border-color .14s",
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 4, minWidth: 0 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: tile.isLive ? "var(--pos)" : "var(--muted-dim)", opacity: tile.isLive ? 1 : 0.4, display: "inline-block", flexShrink: 0 }} />
            <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{tile.symbol}</div>
          </div>
          <div style={{ fontSize: 9, color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{tile.name}</div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontSize: 10, fontWeight: 700, fontFamily: "var(--font-mono)", color: isPositive ? "var(--pos)" : "var(--neg)" }}>{isPositive ? "+" : ""}{tile.changePct.toFixed(2)}%</div>
        </div>
      </div>
      <div style={{ margin: "4px 0" }}>
        <Sparkline data={tile.sparkline} positive={isPositive} />
      </div>
      <div style={{ fontSize: 11, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--fg)", lineHeight: 1 }}>{formatPrice(tile.price, tile.unit)}</div>
    </div>
  );
}

export function MacroDashboardPanel({ data }: { data: any }) {
  return (
    <div className="panel-light" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 12, overflowY: "auto" }}>
      {data.regime && <RegimeBanner regime={data.regime} />}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, fontSize: 8.5, color: "var(--muted)", flexShrink: 0, marginBottom: -4 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--pos)", display: "inline-block" }} /> live</span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--muted-dim)", opacity: 0.5, display: "inline-block" }} /> reference</span>
        <span className="editorial-label" style={{ fontSize: 8 }}>% = 1D change</span>
      </div>
      {data.groups.map((group: any) => (
        <div key={group.label} style={{ flexShrink: 0 }}>
          <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.2em", marginBottom: 6, paddingBottom: 4, borderBottom: "1px solid var(--border-soft)", color: "var(--muted)" }}>
            {group.label}
          </div>
          <div style={{ display: "grid", gap: 6, gridTemplateColumns: `repeat(${Math.min(group.tiles.length, 5)}, minmax(0, 1fr))` }}>
            {group.tiles.map((tile: any) => <AssetTile key={tile.symbol} tile={tile} />)}
          </div>
        </div>
      ))}
    </div>
  );
}
