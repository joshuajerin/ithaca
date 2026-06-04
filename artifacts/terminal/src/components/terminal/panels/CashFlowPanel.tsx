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
} from "recharts";
import { ScrollArea } from "@/components/ui/scroll-area";

interface CashFlowPanelProps {
  data: any;
}

const CustomBarTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const pt = payload[0]?.payload;
    return (
      <div className="bg-black border border-white/20 p-2 shadow-xl text-xs">
        <p className="text-muted-foreground mb-1">{label}</p>
        {pt?.principal > 0 && (
          <p className="font-mono text-white">Principal: {pt.principal.toFixed(2)}</p>
        )}
        <p className="font-mono text-muted-foreground">Coupon: {pt?.coupon.toFixed(2)}</p>
        <p className="font-mono text-gray-400">PV: {pt?.pv.toFixed(2)}</p>
      </div>
    );
  }
  return null;
};

export function CashFlowPanel({ data }: CashFlowPanelProps) {
  const yearLabels = data.payments.map((p: any) => p.date.slice(0, 4));
  const uniqueYears = Array.from(new Set(yearLabels));
  const annualPayments = uniqueYears.map((yr: any) => {
    const pts = data.payments.filter((p: any) => p.date.startsWith(yr));
    return {
      year: yr,
      coupon: parseFloat(pts.reduce((s: any, p: any) => s + p.coupon, 0).toFixed(2)),
      principal: parseFloat(pts.reduce((s: any, p: any) => s + p.principal, 0).toFixed(2)),
      pv: parseFloat(pts.reduce((s: any, p: any) => s + p.pv, 0).toFixed(2)),
    };
  });

  const scenarioZero = data.scenarios.find((s: any) => s.shiftBps === 0);
  const basePrice = scenarioZero?.newPrice ?? data.price;

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex justify-between items-start mb-2 shrink-0">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">
            Cash Flow & Duration
          </div>
          <div className="text-base font-bold leading-tight">{data.issuer}</div>
          <div className="text-[10px] text-muted-foreground mt-0.5">
            {data.coupon}% · Matures {data.maturityDate} · YTM {data.yieldPct.toFixed(2)}%
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold font-mono">{basePrice.toFixed(2)}</div>
          <div className="text-[10px] text-muted-foreground">Price (per 100)</div>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2 mb-2 shrink-0">
        {[
          { label: "Mod Dur", value: data.modifiedDuration.toFixed(2), unit: "yr" },
          { label: "Eff Dur", value: data.effectiveDuration.toFixed(2), unit: "yr" },
          { label: "Convexity", value: data.convexity.toFixed(2), unit: "" },
          { label: "DV01", value: (data.dv01 * 100).toFixed(4), unit: "¢" },
        ].map(({ label, value, unit }) => (
          <div key={label} className="border border-border px-2 py-1.5 text-center">
            <div className="text-[9px] text-muted-foreground uppercase tracking-wider">{label}</div>
            <div className="text-sm font-bold font-mono">{value}{unit}</div>
          </div>
        ))}
      </div>

      <div className="h-28 w-full shrink-0 mb-2">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Cash Flow Schedule</div>
        <ResponsiveContainer width="100%" height="90%">
          <BarChart data={annualPayments} margin={{ top: 2, right: 4, left: -24, bottom: 0 }} barCategoryGap="15%">
            <CartesianGrid strokeDasharray="2 2" stroke="#222" vertical={false} />
            <XAxis
              dataKey="year"
              tick={{ fontSize: 8, fill: "#666" }}
              tickLine={false}
              axisLine={false}
              interval={Math.floor(annualPayments.length / 8)}
            />
            <YAxis
              tick={{ fontSize: 8, fill: "#666" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => v.toFixed(0)}
            />
            <Tooltip content={<CustomBarTooltip />} />
            <Bar dataKey="coupon" stackId="a" fill="#4b5563" name="Coupon" radius={[0, 0, 0, 0]} />
            <Bar dataKey="principal" stackId="a" name="Principal" radius={[2, 2, 0, 0]}>
              {annualPayments.map((entry, i) => (
                <Cell key={i} fill={entry.principal > 0 ? "#ffffff" : "#4b5563"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="flex-1 min-h-0">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Parallel Shift Scenarios</div>
        <div className="border border-border">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-muted-foreground text-[9px]">
                <th className="text-left py-1.5 px-2 uppercase tracking-wider">Shift</th>
                <th className="text-right py-1.5 px-2 uppercase tracking-wider">New Yield</th>
                <th className="text-right py-1.5 px-2 uppercase tracking-wider">New Price</th>
                <th className="text-right py-1.5 px-2 uppercase tracking-wider">Chg (pts)</th>
                <th className="text-right py-1.5 px-2 uppercase tracking-wider">Chg %</th>
              </tr>
            </thead>
            <tbody>
              {data.scenarios.map((s: any) => {
                const isBase = s.shiftBps === 0;
                const isPos = s.priceChange > 0;
                return (
                  <tr
                    key={s.shiftBps}
                    className={`border-b border-border/40 hover:bg-white/5 transition-colors ${isBase ? "bg-white/5" : ""}`}
                  >
                    <td className={`py-1.5 px-2 font-bold font-mono ${isBase ? "text-white" : s.shiftBps > 0 ? "text-red-400" : "text-green-400"}`}>
                      {s.shiftBps === 0 ? "Base" : s.shiftBps > 0 ? `+${s.shiftBps}bp` : `${s.shiftBps}bp`}
                    </td>
                    <td className="py-1.5 px-2 text-right font-mono">{s.newYield.toFixed(2)}%</td>
                    <td className="py-1.5 px-2 text-right font-mono font-bold">{s.newPrice.toFixed(2)}</td>
                    <td className={`py-1.5 px-2 text-right font-mono ${isBase ? "text-muted-foreground" : isPos ? "text-green-400" : "text-red-400"}`}>
                      {isBase ? "—" : (isPos ? "+" : "") + s.priceChange.toFixed(2)}
                    </td>
                    <td className={`py-1.5 px-2 text-right font-mono ${isBase ? "text-muted-foreground" : isPos ? "text-green-400" : "text-red-400"}`}>
                      {isBase ? "—" : (isPos ? "+" : "") + s.priceChangePct.toFixed(2) + "%"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
