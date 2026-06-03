import React from "react";
import type { FactorAnalysisData } from "@workspace/api-client-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
  Legend,
} from "recharts";
import { ScrollArea } from "@/components/ui/scroll-area";

const FACTOR_COLORS: Record<string, string> = {
  momentum: "#ffffff",
  value: "#aaaaaa",
  size: "#666666",
  quality: "#dddddd",
  residual: "#333333",
};

interface Props {
  data: FactorAnalysisData;
}

export function FactorAnalysisPanel({ data }: Props) {
  const { monthlyAttribution, loadings } = data;

  const AttributionTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      const total = payload.reduce((s: number, p: any) => s + (p.value || 0), 0);
      return (
        <div className="bg-black border border-white/20 p-2 text-xs space-y-1 min-w-[130px]">
          <p className="text-muted-foreground mb-1">{label}</p>
          {payload.map((p: any) => (
            <p key={p.name} style={{ color: p.fill }} className="flex justify-between gap-3">
              <span className="capitalize">{p.name}</span>
              <span className="font-mono">{p.value?.toFixed(2)}%</span>
            </p>
          ))}
          <p className="text-white border-t border-border/50 pt-1 flex justify-between gap-3 font-bold">
            <span>Total</span>
            <span className="font-mono">{total.toFixed(2)}%</span>
          </p>
        </div>
      );
    }
    return null;
  };

  const downsampledMonths = monthlyAttribution.slice(-12);

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="shrink-0">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          {data.name} ({data.symbol}) · Factor Return Attribution
        </div>
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        <div className="flex-[3] min-h-0 flex flex-col">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
            Monthly Attribution (%)
          </div>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={downsampledMonths} margin={{ top: 2, right: 0, left: -20, bottom: 0 }} stackOffset="sign">
                <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                <XAxis
                  dataKey="month"
                  tick={{ fontSize: 9, fill: "#555" }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={20}
                  tickFormatter={(v) => v.slice(5)}
                />
                <YAxis
                  tick={{ fontSize: 9, fill: "#555" }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v}%`}
                />
                <Tooltip content={<AttributionTooltip />} />
                <ReferenceLine y={0} stroke="#444" strokeWidth={1} />
                <Bar dataKey="momentum" stackId="a" fill={FACTOR_COLORS.momentum} name="momentum" />
                <Bar dataKey="value" stackId="a" fill={FACTOR_COLORS.value} name="value" />
                <Bar dataKey="size" stackId="a" fill={FACTOR_COLORS.size} name="size" />
                <Bar dataKey="quality" stackId="a" fill={FACTOR_COLORS.quality} name="quality" />
                <Bar dataKey="residual" stackId="a" fill={FACTOR_COLORS.residual} name="residual" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex gap-3 mt-1 shrink-0">
            {Object.entries(FACTOR_COLORS).map(([f, c]) => (
              <div key={f} className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: c }} />
                <span className="text-[9px] text-muted-foreground capitalize">{f}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex-[2] min-h-0 flex flex-col">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
            Factor Loadings
          </div>
          <div className="overflow-auto flex-1">
            <table className="text-[10px] font-mono w-full border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-muted-foreground font-normal pb-1 pr-3">Factor</th>
                  <th className="text-right text-muted-foreground font-normal pb-1 pr-3">Loading</th>
                  <th className="text-right text-muted-foreground font-normal pb-1 pr-3">t-Stat</th>
                  <th className="text-right text-muted-foreground font-normal pb-1">Contrib</th>
                </tr>
              </thead>
              <tbody>
                {loadings.map((row) => {
                  const sigColor = Math.abs(row.tStat) > 2 ? "text-white" : "text-muted-foreground";
                  const loadingColor = row.loading > 0 ? "text-white" : "text-muted-foreground";
                  const contribColor = row.contribution > 0 ? "text-white" : "text-red-400";
                  return (
                    <tr key={row.factor} className="border-b border-border/30">
                      <td className="py-1 pr-3 text-muted-foreground">{row.factor}</td>
                      <td className={`py-1 pr-3 text-right ${loadingColor}`}>
                        {row.loading > 0 ? "+" : ""}{row.loading.toFixed(2)}
                      </td>
                      <td className={`py-1 pr-3 text-right ${sigColor}`}>
                        {row.tStat > 0 ? "+" : ""}{row.tStat.toFixed(1)}
                      </td>
                      <td className={`py-1 text-right ${contribColor}`}>
                        {row.contribution > 0 ? "+" : ""}{row.contribution.toFixed(2)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
