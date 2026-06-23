// @ts-nocheck
import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

interface BrinsonRow {
  sector: string;
  sectorLabel: string;
  portWeight: number;
  benchWeight: number;
  portReturn: number;
  benchReturn: number;
  allocation: number;
  selection: number;
  interaction: number;
  total: number;
}
interface BrinsonTotals {
  allocation: number;
  selection: number;
  interaction: number;
  total: number;
  portReturn: number;
  benchReturn: number;
  activeReturn: number;
}
export interface BrinsonData {
  portfolioName: string;
  benchmarkName: string;
  rangeLabel: string;
  windowDays: number;
  rows: BrinsonRow[];
  totals: BrinsonTotals;
}

const COLORS = { allocation: "#ffffff", selection: "#888888", interaction: "#444444" };
const sign = (n: number) => `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
const tone = (n: number) => (n > 0 ? "text-emerald-400" : n < 0 ? "text-red-400" : "text-muted-foreground");

export function BrinsonPanel({ data }: { data: BrinsonData }) {
  const { rows, totals } = data;
  const chartData = rows.map((r) => ({
    sector: r.sectorLabel,
    allocation: r.allocation,
    selection: r.selection,
    interaction: r.interaction,
  }));

  const Tip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const t = payload.reduce((s: number, p: any) => s + (p.value || 0), 0);
    return (
      <div className="bg-black border border-white/20 p-2 text-[10px] space-y-1 min-w-[150px]">
        <p className="text-muted-foreground mb-1">{label}</p>
        {payload.map((p: any) => (
          <p key={p.name} style={{ color: p.fill }} className="flex justify-between gap-3">
            <span className="capitalize">{p.name}</span>
            <span className="font-mono">{sign(p.value)}</span>
          </p>
        ))}
        <p className="text-white border-t border-border/50 pt-1 flex justify-between gap-3 font-bold">
          <span>Total</span><span className="font-mono">{sign(t)}</span>
        </p>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="shrink-0 flex items-baseline justify-between">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          {data.portfolioName} · Brinson Attribution vs {data.benchmarkName}
        </div>
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">{data.rangeLabel} · {data.windowDays}d</div>
      </div>

      <div className="flex gap-4 flex-1 min-h-0">
        <div className="flex-[3] min-h-0 flex flex-col">
          <div className="text-[8.5px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">Active Return by Sector (%)</div>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 2, right: 0, left: -20, bottom: 0 }} stackOffset="sign">
                <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                <XAxis dataKey="sector" tick={{ fontSize: 8.5, fill: "#555" }} tickLine={false} axisLine={false} interval={0} angle={-25} textAnchor="end" height={42} />
                <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                <Tooltip content={<Tip />} />
                <ReferenceLine y={0} stroke="#444" strokeWidth={1} />
                <Bar dataKey="allocation" stackId="a" fill={COLORS.allocation} name="allocation" />
                <Bar dataKey="selection" stackId="a" fill={COLORS.selection} name="selection" />
                <Bar dataKey="interaction" stackId="a" fill={COLORS.interaction} name="interaction" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex gap-3 mt-1 shrink-0">
            {Object.entries(COLORS).map(([f, c]) => (
              <div key={f} className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: c }} />
                <span className="text-[9px] text-muted-foreground capitalize">{f}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex-[4] min-h-0 overflow-auto">
          <table className="text-[10px] font-mono w-full border-collapse">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="text-left font-normal pb-1 pr-2">Sector</th>
                <th className="text-right font-normal pb-1 pr-2">wP</th>
                <th className="text-right font-normal pb-1 pr-2">wB</th>
                <th className="text-right font-normal pb-1 pr-2">Alloc</th>
                <th className="text-right font-normal pb-1 pr-2">Sel</th>
                <th className="text-right font-normal pb-1 pr-2">Inter</th>
                <th className="text-right font-normal pb-1">Total</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.sector} className="border-b border-border/30">
                  <td className="py-1 pr-2 text-muted-foreground whitespace-nowrap">{r.sectorLabel}</td>
                  <td className="py-1 pr-2 text-right text-white/80">{r.portWeight.toFixed(0)}%</td>
                  <td className="py-1 pr-2 text-right text-muted-foreground">{r.benchWeight.toFixed(0)}%</td>
                  <td className={`py-1 pr-2 text-right ${tone(r.allocation)}`}>{sign(r.allocation)}</td>
                  <td className={`py-1 pr-2 text-right ${tone(r.selection)}`}>{sign(r.selection)}</td>
                  <td className={`py-1 pr-2 text-right ${tone(r.interaction)}`}>{sign(r.interaction)}</td>
                  <td className={`py-1 text-right font-bold ${tone(r.total)}`}>{sign(r.total)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-white/30 text-white">
                <td className="py-1 pr-2">Total</td>
                <td className="py-1 pr-2 text-right">{totals.portReturn.toFixed(0)}%</td>
                <td className="py-1 pr-2 text-right">{totals.benchReturn.toFixed(0)}%</td>
                <td className={`py-1 pr-2 text-right ${tone(totals.allocation)}`}>{sign(totals.allocation)}</td>
                <td className={`py-1 pr-2 text-right ${tone(totals.selection)}`}>{sign(totals.selection)}</td>
                <td className={`py-1 pr-2 text-right ${tone(totals.interaction)}`}>{sign(totals.interaction)}</td>
                <td className={`py-1 text-right font-bold ${tone(totals.total)}`}>{sign(totals.total)}</td>
              </tr>
            </tfoot>
          </table>
          <div className="mt-2 text-[9px] text-muted-foreground leading-relaxed">
            Active return {sign(totals.activeReturn)} = allocation {sign(totals.allocation)} + selection {sign(totals.selection)} + interaction {sign(totals.interaction)}.
          </div>
        </div>
      </div>
    </div>
  );
}
