import React from "react";
import type { FactorExposureData } from "@workspace/api-client-react";
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

const STYLE_COLS = ["market", "size", "value", "momentum", "volatility", "quality"] as const;

function expoColor(v: number): string {
  if (v >= 0.5) return "#ffffff";
  if (v > 0) return "#bbbbbb";
  if (v > -0.5) return "#777777";
  return "#ef4444";
}

export function FactorExposurePanel({ data }: { data: FactorExposureData }) {
  const { portfolioName, exposures, holdings, coverage } = data;

  const ExpoTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      const d = payload[0].payload;
      const sig = Math.abs(d.tStat) > 2;
      return (
        <div className="bg-black border border-white/20 p-2 text-xs space-y-0.5 min-w-[160px]">
          <p className="text-white mb-1">{label}</p>
          <p className="flex justify-between gap-3 text-muted-foreground">
            <span>Exposure</span>
            <span className="font-mono">{d.exposure.toFixed(2)}</span>
          </p>
          <p className="flex justify-between gap-3 text-muted-foreground">
            <span>Factor return (ann.)</span>
            <span className="font-mono">{d.factorReturn.toFixed(1)}%</span>
          </p>
          <p className={`flex justify-between gap-3 ${sig ? "text-white" : "text-muted-foreground"}`}>
            <span>t-stat{sig ? " ✓" : ""}</span>
            <span className="font-mono">{d.tStat.toFixed(2)}</span>
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="shrink-0">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          {portfolioName} · Factor Exposures
        </div>
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        {/* Portfolio tilt bars */}
        <div className="flex-[2] flex flex-col min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
            Portfolio Tilt (std. exposure)
          </div>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={exposures} layout="vertical" margin={{ top: 2, right: 12, left: 8, bottom: 2 }}>
                <CartesianGrid strokeDasharray="2 2" stroke="#222" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="factor" tick={{ fontSize: 9, fill: "#888" }} tickLine={false} axisLine={false} width={64} />
                <Tooltip content={<ExpoTooltip />} cursor={{ fill: "#ffffff08" }} />
                <ReferenceLine x={0} stroke="#444" strokeWidth={1} />
                <Bar dataKey="exposure" radius={[0, 2, 2, 0]}>
                  {exposures.map((entry, idx) => (
                    <Cell key={idx} fill={expoColor(entry.exposure)} fillOpacity={0.8} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Factor premia table */}
        <div className="flex-[2] flex flex-col min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
            Realized Factor Premia
          </div>
          <div className="overflow-auto flex-1">
            <table className="text-[10px] font-mono w-full border-collapse">
              <thead>
                <tr className="border-b border-border sticky top-0 bg-background">
                  <th className="text-left text-muted-foreground font-normal pb-1 pr-2">Factor</th>
                  <th className="text-right text-muted-foreground font-normal pb-1 pr-2">Expo</th>
                  <th className="text-right text-muted-foreground font-normal pb-1 pr-2">Ret</th>
                  <th className="text-right text-muted-foreground font-normal pb-1">t</th>
                </tr>
              </thead>
              <tbody>
                {exposures.map((r) => {
                  const sig = Math.abs(r.tStat) > 2;
                  return (
                    <tr key={r.factor} className="border-b border-border/30">
                      <td className="py-1 pr-2 text-muted-foreground">{r.factor}</td>
                      <td className="py-1 pr-2 text-right text-white">
                        {r.exposure > 0 ? "+" : ""}{r.exposure.toFixed(2)}
                      </td>
                      <td className={`py-1 pr-2 text-right ${r.factorReturn >= 0 ? "text-white" : "text-red-400"}`}>
                        {r.factorReturn > 0 ? "+" : ""}{r.factorReturn.toFixed(1)}%
                      </td>
                      <td className={`py-1 text-right ${sig ? "text-white" : "text-muted-foreground"}`}>
                        {r.tStat.toFixed(1)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Per-holding exposure grid */}
      <div className="shrink-0 flex flex-col min-h-0" style={{ maxHeight: "40%" }}>
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
          Per-Holding Exposures
        </div>
        <div className="overflow-auto">
          <table className="text-[10px] font-mono w-full border-collapse">
            <thead>
              <tr className="border-b border-border sticky top-0 bg-background">
                <th className="text-left text-muted-foreground font-normal pb-1 pr-2">Sym</th>
                {STYLE_COLS.map((c) => (
                  <th key={c} className="text-right text-muted-foreground font-normal pb-1 pr-2 capitalize">
                    {c.slice(0, 3)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {holdings.map((h) => (
                <tr key={h.symbol} className="border-b border-border/30">
                  <td className="py-1 pr-2 text-white/80">{h.symbol}</td>
                  {STYLE_COLS.map((c) => {
                    const v = h[c] as number;
                    return (
                      <td key={c} className="py-1 pr-2 text-right" style={{ color: expoColor(v) }}>
                        {v > 0 ? "+" : ""}{v.toFixed(1)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="shrink-0 flex items-center justify-between text-[9px] text-muted-foreground font-mono border-t border-border/50 pt-1.5">
        <span>{coverage.included} modeled · {coverage.days}d · {coverage.source}</span>
        {coverage.excluded > 0 && (
          <span className="text-red-400/70" title={coverage.excludedNames.map((e) => `${e.symbol}: ${e.reason}`).join("\n")}>
            {coverage.excluded} excluded
          </span>
        )}
      </div>
    </div>
  );
}
