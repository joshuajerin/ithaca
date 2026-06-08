import React from "react";
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

type Holding = {
  symbol: string;
  name: string;
  sector: string;
  weight: number;
  benchWeight: number;
  activeWeight: number;
  expReturn: number;
  riskContribPct: number;
  currentWeight?: number;
  trade?: number;
  priorReturn?: number;
};

type Tilt = { factor: string; tilt: number; factorReturn: number };

export function PortfolioOptimizerPanel({ data }: { data: any }) {
  const {
    methodLabel,
    universeLabel,
    longOnly,
    objective,
    constraints,
    holdings = [],
    factorTilts = [],
    sectorAllocation = [],
    turnover,
    coverage,
    notes = [],
    shorting,
  } = data;

  const hs: Holding[] = holdings;
  const tilts: Tilt[] = factorTilts;
  const maxW = Math.max(...hs.map((h) => Math.abs(h.weight)), 1);

  const TiltTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      const d = payload[0].payload;
      return (
        <div className="bg-black border border-white/20 p-2 text-xs space-y-0.5 min-w-[150px]">
          <p className="text-white mb-1">{label}</p>
          <p className="flex justify-between gap-3 text-muted-foreground">
            <span>Portfolio tilt</span>
            <span className="font-mono">{d.tilt.toFixed(2)}</span>
          </p>
          <p className="flex justify-between gap-3 text-muted-foreground">
            <span>Factor premium</span>
            <span className="font-mono">{d.factorReturn.toFixed(1)}%</span>
          </p>
        </div>
      );
    }
    return null;
  };

  const fmtPct = (v: number) => `${v >= 0 ? "" : "-"}${Math.abs(v).toFixed(1)}%`;

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="shrink-0 flex items-baseline justify-between">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          {methodLabel} · {universeLabel}
        </div>
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest font-mono">
          {longOnly ? "Long-only" : "Long / short"}
          {constraints && <> · max {constraints.maxPosition.toFixed(0)}%</>}
        </div>
      </div>

      {/* Constraint diagnostics (relaxed / overridden requests) */}
      {notes.length > 0 && (
        <div className="shrink-0 border-l-2 border-amber-500/50 bg-amber-500/5 px-2 py-1 space-y-0.5">
          {notes.map((n: string, i: number) => (
            <div key={i} className="text-[9px] text-amber-200/80 font-mono leading-snug">
              {n}
            </div>
          ))}
        </div>
      )}

      {/* Objective summary cards */}
      <div className="grid grid-cols-5 gap-2 shrink-0">
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Exp Return</div>
          <div className="text-base font-bold font-mono">{objective.expReturn.toFixed(1)}%</div>
        </div>
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Volatility</div>
          <div className="text-base font-bold font-mono">{objective.vol.toFixed(1)}%</div>
        </div>
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Sharpe</div>
          <div className="text-base font-bold font-mono text-emerald-400">{objective.sharpe.toFixed(2)}</div>
        </div>
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Holdings</div>
          <div className="text-base font-bold font-mono">{objective.nHoldings}</div>
        </div>
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Gross / Net</div>
          <div className="text-base font-bold font-mono">
            {objective.gross.toFixed(0)}<span className="text-muted-foreground">/{objective.net.toFixed(0)}</span>
          </div>
        </div>
      </div>

      {/* Binding constraints */}
      {constraints?.binding?.length > 0 && (
        <div className="shrink-0 flex items-center gap-1.5 flex-wrap">
          <span className="text-[9px] text-muted-foreground uppercase tracking-widest">Binding</span>
          {constraints.binding.map((b: string) => (
            <span key={b} className="text-[9px] font-mono px-1.5 py-0.5 border border-amber-500/40 text-amber-300/90">
              {b}
            </span>
          ))}
          {turnover != null && (
            <span className="text-[9px] font-mono px-1.5 py-0.5 border border-border text-muted-foreground ml-auto">
              turnover {turnover.toFixed(0)}%
            </span>
          )}
        </div>
      )}

      {/* Short-availability / borrow / margin (long-short books only) */}
      {shorting && (
        <div className="shrink-0 border border-border/60 px-2 py-1.5 space-y-1">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <span className="text-[9px] text-muted-foreground uppercase tracking-widest">
              Short-Aware · GC {shorting.financing?.gcRatePct?.toFixed(2)}% ({shorting.financing?.source})
            </span>
            {shorting.margin && (
              <span className="text-[9px] font-mono flex items-center gap-2">
                <span className={shorting.margin.grossLeverage > 4 ? "text-red-400" : shorting.margin.grossLeverage > 2 ? "text-amber-300" : "text-white"}>
                  lev {shorting.margin.grossLeverage.toFixed(2)}×
                </span>
                <span className={shorting.margin.excessLiquidityPct < 0 ? "text-red-400" : "text-emerald-400/80"}>
                  excess liq {shorting.margin.excessLiquidityPct.toFixed(0)}%
                </span>
                {shorting.margin.breach && <span className="text-red-400">⚠ BREACH</span>}
              </span>
            )}
          </div>
          {shorting.blocked?.length > 0 && (
            <div className="text-[9px] text-amber-300/80 font-mono">
              Short blocked (locate-infeasible): {shorting.blocked.join(", ")}
            </div>
          )}
          {shorting.borrow?.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {shorting.borrow.slice(0, 8).map((b: any) => (
                <span
                  key={b.symbol}
                  className={`text-[9px] font-mono px-1.5 py-0.5 border ${
                    !b.shortable
                      ? "border-red-500/40 text-red-300/90"
                      : b.tier === "htb"
                      ? "border-orange-500/40 text-orange-300/90"
                      : "border-border text-muted-foreground"
                  }`}
                  title={b.tierLabel}
                >
                  {b.symbol} {b.feeBps != null ? `${b.feeBps.toFixed(0)}bp` : ""}
                  {!b.shortable && " ✕"}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex gap-3 flex-1 min-h-0">
        {/* Weights table */}
        <div className="flex-[1.4] flex flex-col min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
            Target Weights vs Benchmark
          </div>
          <div className="overflow-auto flex-1">
            <table className="text-[10px] font-mono w-full border-collapse">
              <thead>
                <tr className="border-b border-border sticky top-0 bg-background">
                  <th className="text-left text-muted-foreground font-normal pb-1 pr-2">Name</th>
                  <th className="text-right text-muted-foreground font-normal pb-1 pr-2">Weight</th>
                  <th className="text-right text-muted-foreground font-normal pb-1 pr-2">Active</th>
                  <th className="text-right text-muted-foreground font-normal pb-1 pr-2">E[r]</th>
                  <th className="text-right text-muted-foreground font-normal pb-1">% Risk</th>
                </tr>
              </thead>
              <tbody>
                {hs.map((h) => (
                  <tr key={h.symbol} className="border-b border-border/30">
                    <td className="py-1 pr-2 text-white/80">
                      {h.symbol}
                      <span className="text-muted-foreground/60 ml-1">{h.sector}</span>
                    </td>
                    <td className="py-1 pr-2 text-right relative">
                      <div
                        className={`absolute inset-y-0 right-0 ${h.weight >= 0 ? "bg-white/10" : "bg-red-500/20"}`}
                        style={{ width: `${(Math.abs(h.weight) / maxW) * 100}%` }}
                      />
                      <span className="relative text-white">{h.weight.toFixed(1)}%</span>
                    </td>
                    <td className={`py-1 pr-2 text-right ${h.activeWeight >= 0 ? "text-emerald-400/80" : "text-red-400/80"}`}>
                      {fmtPct(h.activeWeight)}
                    </td>
                    <td className="py-1 pr-2 text-right text-muted-foreground">{h.expReturn.toFixed(0)}%</td>
                    <td className="py-1 text-right text-white/70">{h.riskContribPct.toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Factor tilts + sector allocation */}
        <div className="flex-1 flex flex-col min-h-0 gap-3">
          <div className="flex flex-col min-h-0 flex-1">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
              Factor Tilts
            </div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={tilts} layout="vertical" margin={{ top: 2, right: 12, left: 8, bottom: 2 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#222" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="factor" tick={{ fontSize: 9, fill: "#888" }} tickLine={false} axisLine={false} width={56} />
                  <Tooltip content={<TiltTooltip />} cursor={{ fill: "#ffffff08" }} />
                  <ReferenceLine x={0} stroke="#444" strokeWidth={1} />
                  <Bar dataKey="tilt" radius={[0, 2, 2, 0]}>
                    {tilts.map((entry, idx) => (
                      <Cell key={idx} fill={entry.tilt >= 0 ? "#ffffff" : "#ef4444"} fillOpacity={0.75} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="shrink-0">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Sector Allocation</div>
            <div className="space-y-1">
              {sectorAllocation.slice(0, 5).map((s: any) => (
                <div key={s.sector} className="flex items-center gap-2 text-[10px] font-mono">
                  <span className="text-muted-foreground w-28 truncate">{s.sector}</span>
                  <div className="flex-1 h-2 bg-white/5 relative overflow-hidden">
                    <div
                      className={`absolute inset-y-0 left-0 ${s.weight >= 0 ? "bg-white/40" : "bg-red-500/40"}`}
                      style={{ width: `${Math.min(Math.abs(s.weight), 100)}%` }}
                    />
                  </div>
                  <span className="text-white/80 w-12 text-right">{s.weight.toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Coverage footer */}
      {coverage && (
        <div className="shrink-0 flex items-center justify-between text-[9px] text-muted-foreground font-mono border-t border-border/50 pt-1.5">
          <span>
            {coverage.included} modeled · {coverage.days}d · {coverage.source} · μ: factor premia · Σ: risk model
          </span>
          {coverage.excluded > 0 && (
            <span
              className="text-red-400/70"
              title={coverage.excludedNames.map((e: any) => `${e.symbol}: ${e.reason}`).join("\n")}
            >
              {coverage.excluded} excluded
            </span>
          )}
        </div>
      )}
    </div>
  );
}
