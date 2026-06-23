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
  Cell,
} from "recharts";

interface FactorRow {
  factor: string;
  exposure: number | null;
  factorReturn: number | null;
  contribution: number;
}
export interface FactorAttributionData {
  portfolioName: string;
  rangeLabel: string;
  windowDays: number;
  rows: FactorRow[];
  realizedReturn: number;
  factorReturn: number;
  specificReturn: number;
}

const sign = (n: number, d = 2) => `${n > 0 ? "+" : ""}${n.toFixed(d)}%`;
const tone = (n: number) => (n > 0 ? "text-emerald-400" : n < 0 ? "text-red-400" : "text-muted-foreground");

export function FactorAttributionPanel({ data }: { data: FactorAttributionData }) {
  const { rows } = data;
  const chartData = rows.map((r) => ({ factor: r.factor, contribution: r.contribution }));

  const Tip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const v = payload[0]?.value as number;
    return (
      <div className="bg-black border border-white/20 p-2 text-[10px] min-w-[120px]">
        <p className="text-muted-foreground mb-1">{label}</p>
        <p className="flex justify-between gap-3"><span>Contribution</span><span className={`font-mono ${tone(v)}`}>{sign(v)}</span></p>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="shrink-0 flex items-baseline justify-between">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          {data.portfolioName} · Factor Return Attribution
        </div>
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">{data.rangeLabel} · {data.windowDays}d</div>
      </div>

      <div className="flex gap-4 flex-1 min-h-0">
        <div className="flex-[3] min-h-0 flex flex-col">
          <div className="text-[8.5px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">Contribution to Return (%)</div>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 2, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                <XAxis dataKey="factor" tick={{ fontSize: 8.5, fill: "#555" }} tickLine={false} axisLine={false} interval={0} angle={-25} textAnchor="end" height={48} />
                <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                <Tooltip content={<Tip />} cursor={{ fill: "#ffffff10" }} />
                <ReferenceLine y={0} stroke="#444" strokeWidth={1} />
                <Bar dataKey="contribution" radius={[2, 2, 0, 0]}>
                  {chartData.map((d, i) => (
                    <Cell key={i} fill={d.factor === "Specific" ? "#666" : d.contribution >= 0 ? "#ffffff" : "#ef4444"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="flex-[2] min-h-0 flex flex-col">
          <div className="overflow-auto flex-1">
            <table className="text-[10px] font-mono w-full border-collapse">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="text-left font-normal pb-1 pr-3">Factor</th>
                  <th className="text-right font-normal pb-1 pr-3">Expo</th>
                  <th className="text-right font-normal pb-1 pr-3">Ret</th>
                  <th className="text-right font-normal pb-1">Contrib</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.factor} className="border-b border-border/30">
                    <td className="py-1 pr-3 text-muted-foreground">{r.factor}</td>
                    <td className="py-1 pr-3 text-right text-white/80">{r.exposure == null ? "—" : r.exposure.toFixed(2)}</td>
                    <td className="py-1 pr-3 text-right text-muted-foreground">{r.factorReturn == null ? "—" : sign(r.factorReturn)}</td>
                    <td className={`py-1 text-right ${tone(r.contribution)}`}>{sign(r.contribution)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-white/30 text-white">
                  <td className="py-1 pr-3">Realized</td>
                  <td className="py-1 pr-3"></td>
                  <td className="py-1 pr-3"></td>
                  <td className={`py-1 text-right font-bold ${tone(data.realizedReturn)}`}>{sign(data.realizedReturn)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          <div className="mt-2 text-[9px] text-muted-foreground leading-relaxed shrink-0">
            Factor {sign(data.factorReturn)} + specific {sign(data.specificReturn)} = realized {sign(data.realizedReturn)}.
          </div>
        </div>
      </div>
    </div>
  );
}
