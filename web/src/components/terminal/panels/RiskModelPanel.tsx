// @ts-nocheck
import React from "react";
import type { RiskModelData } from "@workspace/api-client-react";
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

export function RiskModelPanel({ data }: { data: RiskModelData }) {
  const {
    portfolioName,
    totalVol,
    factorVol,
    specificVol,
    factorVarPct,
    specificVarPct,
    diversificationRatio,
    rSquared,
    factorContributions,
    holdings,
    coverage,
  } = data;

  const factorData = factorContributions
    .filter((f) => Math.abs(f.pctOfRisk) > 0.001)
    .map((f) => ({ ...f }));
  const maxPct = Math.max(...holdings.map((h) => Math.abs(h.pctOfRisk)), 1);

  const FactorTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      const d = payload[0].payload;
      return (
        <div className="bg-black border border-white/20 p-2 text-xs space-y-0.5 min-w-[150px]">
          <p className="text-white mb-1">{label}</p>
          <p className="flex justify-between gap-3 text-muted-foreground">
            <span>Exposure</span>
            <span className="font-mono">{d.exposure.toFixed(2)}</span>
          </p>
          <p className="flex justify-between gap-3 text-muted-foreground">
            <span>Vol contrib</span>
            <span className="font-mono">{d.volContribution.toFixed(2)}%</span>
          </p>
          <p className="flex justify-between gap-3 text-white">
            <span>% of risk</span>
            <span className="font-mono">{d.pctOfRisk.toFixed(1)}%</span>
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="shrink-0 flex items-baseline justify-between">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          {portfolioName} · Multi-Factor Risk
        </div>
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest font-mono">
          R² {rSquared.toFixed(2)} · DR {diversificationRatio.toFixed(2)}
        </div>
      </div>

      {/* Vol summary cards */}
      <div className="grid grid-cols-3 gap-3 shrink-0">
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Total Vol (ann.)</div>
          <div className="text-lg font-bold font-mono">{totalVol.toFixed(1)}%</div>
        </div>
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Factor</div>
          <div className="text-lg font-bold font-mono">{factorVol.toFixed(1)}%</div>
        </div>
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Specific</div>
          <div className="text-lg font-bold font-mono text-muted-foreground">{specificVol.toFixed(1)}%</div>
        </div>
      </div>

      {/* Factor vs specific variance split bar */}
      <div className="shrink-0">
        <div className="flex h-3 w-full overflow-hidden border border-border">
          <div
            className="bg-white/70 h-full"
            style={{ width: `${factorVarPct}%` }}
            title={`Factor ${factorVarPct.toFixed(0)}%`}
          />
          <div
            className="bg-white/20 h-full"
            style={{ width: `${specificVarPct}%` }}
            title={`Specific ${specificVarPct.toFixed(0)}%`}
          />
        </div>
        <div className="flex justify-between text-[9px] text-muted-foreground mt-1 font-mono">
          <span>Factor {factorVarPct.toFixed(0)}% of variance</span>
          <span>Specific {specificVarPct.toFixed(0)}%</span>
        </div>
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        {/* Per-factor risk contribution */}
        <div className="flex-1 flex flex-col min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
            Risk Contribution by Factor (%)
          </div>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={factorData} layout="vertical" margin={{ top: 2, right: 12, left: 8, bottom: 2 }}>
                <CartesianGrid strokeDasharray="2 2" stroke="#222" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                <YAxis type="category" dataKey="factor" tick={{ fontSize: 9, fill: "#888" }} tickLine={false} axisLine={false} width={64} />
                <Tooltip content={<FactorTooltip />} cursor={{ fill: "#ffffff08" }} />
                <ReferenceLine x={0} stroke="#444" strokeWidth={1} />
                <Bar dataKey="pctOfRisk" radius={[0, 2, 2, 0]}>
                  {factorData.map((entry, idx) => (
                    <Cell key={idx} fill={entry.pctOfRisk >= 0 ? "#ffffff" : "#ef4444"} fillOpacity={0.75} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* MCTR per holding */}
        <div className="flex-1 flex flex-col min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
            Marginal Contribution to Risk
          </div>
          <div className="overflow-auto flex-1">
            <table className="text-[10px] font-mono w-full border-collapse">
              <thead>
                <tr className="border-b border-border sticky top-0 bg-background">
                  <th className="text-left text-muted-foreground font-normal pb-1 pr-2">Holding</th>
                  <th className="text-right text-muted-foreground font-normal pb-1 pr-2">Wt</th>
                  <th className="text-right text-muted-foreground font-normal pb-1 pr-2">MCTR</th>
                  <th className="text-right text-muted-foreground font-normal pb-1">% Risk</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((h) => (
                  <tr key={h.symbol} className="border-b border-border/30">
                    <td className="py-1 pr-2 text-white/80">{h.symbol}</td>
                    <td className="py-1 pr-2 text-right text-muted-foreground">{h.weight.toFixed(0)}%</td>
                    <td className="py-1 pr-2 text-right text-white">{h.mctr.toFixed(2)}%</td>
                    <td className="py-1 text-right relative">
                      <div
                        className="absolute inset-y-0 right-0 bg-white/10"
                        style={{ width: `${(Math.abs(h.pctOfRisk) / maxPct) * 100}%` }}
                      />
                      <span className="relative text-white">{h.pctOfRisk.toFixed(1)}%</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Coverage footer */}
      <div className="shrink-0 flex items-center justify-between text-[9px] text-muted-foreground font-mono border-t border-border/50 pt-1.5">
        <span>
          {coverage.included} modeled · {coverage.days}d · {coverage.source}
          {coverage.pcaVarExplained.length > 0 && (
            <> · PC1 {(coverage.pcaVarExplained[0] * 100).toFixed(0)}%</>
          )}
        </span>
        {coverage.excluded > 0 && (
          <span className="text-red-400/70" title={coverage.excludedNames.map((e) => `${e.symbol}: ${e.reason}`).join("\n")}>
            {coverage.excluded} excluded
          </span>
        )}
      </div>
    </div>
  );
}
