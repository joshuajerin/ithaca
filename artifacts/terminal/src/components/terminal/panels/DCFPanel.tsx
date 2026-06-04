import React, { useState, useMemo } from "react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell } from "recharts";

interface DCFAssumptions {
  revenueGrowth: number;
  ebitdaMargin: number;
  wacc: number;
  exitMultiple: number;
  taxRate: number;
  capexPct: number;
}

interface DCFProjectionYear {
  year: number;
  revenue: number;
  fcf: number;
  pvFcf: number;
}

interface DCFSensCell {
  wacc: number;
  exitMultiple: number;
  impliedPrice: number;
}

interface DCFData {
  symbol: string;
  name: string;
  currentPrice: number;
  baseRevenue: number;
  sharesOut: number;
  netDebt: number;
  assumptions: DCFAssumptions;
  projections: DCFProjectionYear[];
  impliedPriceLow: number;
  impliedPriceMid: number;
  impliedPriceHigh: number;
  sensitivity: DCFSensCell[];
}

function fmtB(n: number): string {
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toFixed(0)}`;
}

function runClientDCF(
  baseRevenue: number,
  sharesOut: number,
  netDebt: number,
  assumptions: DCFAssumptions,
  baseYear: number
): { projections: DCFProjectionYear[]; impliedMid: number } {
  const g = assumptions.revenueGrowth / 100;
  const margin = assumptions.ebitdaMargin / 100;
  const wacc = assumptions.wacc / 100;
  const tax = assumptions.taxRate / 100;
  const capex = assumptions.capexPct / 100;

  let rev = baseRevenue;
  const projections: DCFProjectionYear[] = [];
  let pvSum = 0;
  for (let t = 1; t <= 5; t++) {
    rev = rev * (1 + g);
    const fcf = rev * margin * (1 - tax) - rev * capex;
    const pvFcf = fcf / Math.pow(1 + wacc, t);
    pvSum += pvFcf;
    projections.push({ year: baseYear + t, revenue: rev, fcf, pvFcf });
  }
  const tv = projections[4].fcf * assumptions.exitMultiple;
  const pvTv = tv / Math.pow(1 + wacc, 5);
  const ev = pvSum + pvTv - netDebt;
  const impliedMid = sharesOut > 0 ? ev / sharesOut : 0;
  return { projections, impliedMid };
}

function getSensitivityColor(price: number, current: number): string {
  const ratio = price / current;
  if (ratio >= 1.4) return "bg-emerald-900/80 text-emerald-300";
  if (ratio >= 1.15) return "bg-emerald-900/50 text-emerald-400";
  if (ratio >= 0.9) return "bg-white/5 text-gray-300";
  if (ratio >= 0.7) return "bg-red-900/40 text-red-400";
  return "bg-red-900/70 text-red-300";
}

export function DCFPanel({ data }: { data: DCFData }) {
  const [assumptions, setAssumptions] = useState<DCFAssumptions>({ ...data.assumptions });
  const baseYear = data.projections[0]?.year ? data.projections[0].year - 1 : new Date().getFullYear();

  const { projections, impliedMid } = useMemo(
    () => runClientDCF(data.baseRevenue, data.sharesOut * 1e6, data.netDebt, assumptions, baseYear),
    [assumptions, data.baseRevenue, data.sharesOut, data.netDebt, baseYear]
  );

  const upside = ((impliedMid - data.currentPrice) / data.currentPrice) * 100;
  const isUpside = upside >= 0;

  const waccValues = [...new Set(data.sensitivity.map(c => c.wacc))].sort((a, b) => a - b);
  const emValues = [...new Set(data.sensitivity.map(c => c.exitMultiple))].sort((a, b) => a - b);

  const inputCls = "w-full bg-black border border-border px-1.5 py-0.5 text-xs font-mono text-white focus:outline-none focus:border-white transition-colors";

  function numInput(
    label: string,
    key: keyof DCFAssumptions,
    unit: string,
    step: number
  ) {
    return (
      <div key={key} className="flex flex-col gap-0.5">
        <label className="text-[9px] text-muted-foreground uppercase tracking-wider">{label}</label>
        <div className="flex items-center gap-1">
          <input
            type="number"
            step={step}
            value={assumptions[key]}
            onChange={e => setAssumptions(prev => ({ ...prev, [key]: parseFloat(e.target.value) || 0 }))}
            className={inputCls}
          />
          <span className="text-[10px] text-muted-foreground shrink-0">{unit}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-baseline gap-2 mb-3 shrink-0">
        <span className="text-xs font-bold uppercase">{data.symbol}</span>
        <span className="text-[10px] text-muted-foreground uppercase">DCF · 5-Year Model</span>
        <span className="ml-auto text-[10px] text-muted-foreground">Current ${data.currentPrice.toFixed(2)}</span>
      </div>

      <div className="flex-1 min-h-0 flex gap-3">
        {/* Assumptions sidebar */}
        <div className="w-32 shrink-0 flex flex-col gap-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Assumptions</div>
          {numInput("Rev Growth", "revenueGrowth", "%", 0.5)}
          {numInput("EBITDA Margin", "ebitdaMargin", "%", 0.5)}
          {numInput("WACC", "wacc", "%", 0.5)}
          {numInput("Exit Multiple", "exitMultiple", "x", 0.5)}
          {numInput("Tax Rate", "taxRate", "%", 1)}
          {numInput("Capex %Rev", "capexPct", "%", 0.5)}

          <div className="mt-auto pt-2 border-t border-border">
            <div className="text-[9px] text-muted-foreground uppercase mb-1">Implied Price</div>
            <div className={`text-lg font-bold font-mono ${isUpside ? "text-white" : "text-red-400"}`}>
              ${impliedMid.toFixed(2)}
            </div>
            <div className={`text-[10px] font-bold ${isUpside ? "text-emerald-400" : "text-red-400"}`}>
              {isUpside ? "+" : ""}{upside.toFixed(1)}% upside
            </div>
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1 min-w-0 flex flex-col gap-3">
          {/* FCF bar chart */}
          <div className="flex-1 min-h-0">
            <div className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1">Projected FCF (PV)</div>
            <ResponsiveContainer width="100%" height="80%">
              <BarChart data={projections} margin={{ top: 2, right: 2, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                <XAxis dataKey="year" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={v => fmtB(v)} width={40} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#000", borderColor: "#333", borderRadius: 0, fontSize: 10 }}
                  formatter={(v: number, name: string) => [fmtB(v), name === "pvFcf" ? "PV FCF" : "FCF"]}
                />
                <Bar dataKey="fcf" name="FCF" fill="#444" radius={[2, 2, 0, 0]}>
                  {projections.map((_, i) => (
                    <Cell key={i} fill={`hsl(${200 + i * 10}, 60%, ${35 + i * 5}%)`} />
                  ))}
                </Bar>
                <Bar dataKey="pvFcf" name="PV FCF" fill="#fff" opacity={0.7} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Sensitivity grid */}
          <div className="shrink-0">
            <div className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1">Sensitivity — Implied Price (WACC × Exit Multiple)</div>
            <div className="overflow-x-auto">
              <table className="text-[9px] border-collapse w-full">
                <thead>
                  <tr>
                    <th className="text-muted-foreground text-right pr-1 pb-0.5 font-normal">WACC ↓ \ EM →</th>
                    {emValues.map(em => (
                      <th key={em} className="text-muted-foreground text-center pb-0.5 font-normal px-0.5">{em}x</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {waccValues.map(w => (
                    <tr key={w}>
                      <td className="text-muted-foreground text-right pr-1 py-0.5">{w}%</td>
                      {emValues.map(em => {
                        const cell = data.sensitivity.find(c => c.wacc === w && c.exitMultiple === em);
                        const price = cell?.impliedPrice ?? 0;
                        const cls = getSensitivityColor(price, data.currentPrice);
                        return (
                          <td key={em} className={`text-center px-1 py-0.5 font-mono ${cls}`}>
                            ${price.toFixed(0)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
