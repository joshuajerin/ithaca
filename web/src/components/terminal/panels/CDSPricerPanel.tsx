// @ts-nocheck
import React, { useMemo, useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { Slider } from "@/components/ui/slider";

interface CDSPricerPanelProps {
  data: any;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const pt = payload[0]?.payload;
    return (
      <div className="bg-black border border-white/20 p-2 shadow-xl text-xs">
        <p className="text-muted-foreground mb-1">{label}</p>
        <p className="font-mono text-white">
          Survival: {(pt?.survivalProb * 100).toFixed(2)}%
        </p>
        <p className="font-mono text-red-400">
          Default: {(pt?.defaultProb * 100).toFixed(2)}%
        </p>
        <p className="font-mono text-muted-foreground">
          Hazard: {(pt?.hazardRate * 10000).toFixed(1)}bp
        </p>
      </div>
    );
  }
  return null;
};

const CDS_TENORS: [string, number][] = [
  ["1Y", 1],
  ["2Y", 2],
  ["3Y", 3],
  ["5Y", 5],
  ["7Y", 7],
  ["10Y", 10],
];

// Mirror of api-server _cds_survival (skills.py)
function cdsSurvival(spreadBps: number, recovery: number, t: number): number {
  const lg = spreadBps / 10000 / (1 - recovery);
  return Math.exp(-lg * t);
}

// Mirror of api-server build_cds_pricer math (skills.py)
function computeCds(spread: number, recovery: number) {
  const survivalCurve = CDS_TENORS.map(([label, years]) => {
    const sp = cdsSurvival(spread, recovery, years);
    return {
      tenor: label,
      years,
      survivalProb: sp,
      hazardRate: spread / 10000 / (1 - recovery),
      defaultProb: 1 - sp,
    };
  });

  const impliedPd1y = 1 - cdsSurvival(spread, recovery, 1);
  const impliedPd5y = 1 - cdsSurvival(spread, recovery, 5);

  const standardSpread = 100;
  const riskyAnnuity =
    CDS_TENORS.slice(0, 4).reduce(
      (s, [, t]) => s + (cdsSurvival(spread, recovery, t) * t) / Math.max(t, 1),
      0,
    ) / 4;
  const upfront = ((spread - standardSpread) / 10000) * riskyAnnuity * 100;

  return { survivalCurve, impliedPd1y, impliedPd5y, upfront };
}

export function CDSPricerPanel({ data }: CDSPricerPanelProps) {
  const baseSpread: number = data.runningSpread;
  const recovery: number = data.recoveryRate;
  const [spread, setSpread] = useState<number>(Math.round(baseSpread));
  const [draft, setDraft] = useState<string>(String(Math.round(baseSpread)));

  const live = useMemo(() => computeCds(spread, recovery), [spread, recovery]);

  const upfrontSign = live.upfront >= 0 ? "+" : "";
  const isHighRisk = spread > 200;
  const isShifted = Math.round(spread) !== Math.round(baseSpread);

  const chartData = live.survivalCurve.map((pt: any) => ({
    ...pt,
    survivalPct: parseFloat((pt.survivalProb * 100).toFixed(2)),
    defaultPct: parseFloat((pt.defaultProb * 100).toFixed(2)),
  }));

  const commitDraft = () => {
    const parsed = parseFloat(draft);
    if (!Number.isNaN(parsed)) {
      const clamped = Math.min(2000, Math.max(1, parsed));
      setSpread(clamped);
      setDraft(String(Math.round(clamped)));
    } else {
      setDraft(String(Math.round(spread)));
    }
  };

  const reset = () => {
    setSpread(Math.round(baseSpread));
    setDraft(String(Math.round(baseSpread)));
  };

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex justify-between items-start mb-3 shrink-0">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">CDS Pricer</div>
          <div className="text-xl font-bold">{data.entity}</div>
          <div className="text-[10px] text-muted-foreground mt-0.5">{data.ticker} · {data.rating}</div>
        </div>
        <div className="text-right flex gap-4 items-start">
          <div>
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest">Running Spd</div>
            <div className={`text-2xl font-bold font-mono ${isHighRisk ? "text-red-400" : "text-white"}`}>
              {spread.toFixed(0)}bp
            </div>
          </div>
          <div>
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest">Upfront</div>
            <div className="text-lg font-bold font-mono text-white">
              {upfrontSign}{live.upfront.toFixed(2)}%
            </div>
          </div>
        </div>
      </div>

      <div className="border border-border px-3 py-2 mb-3 shrink-0">
        <div className="flex justify-between items-center mb-1.5">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest">CDS Spread (bp)</div>
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commitDraft}
              onKeyDown={(e) => {
                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
              }}
              className="w-16 bg-black border border-border px-2 py-0.5 text-right text-xs font-mono text-white focus:outline-none focus:border-white/50"
            />
            {isShifted && (
              <button
                onClick={reset}
                className="text-[9px] text-muted-foreground hover:text-white uppercase tracking-wider border border-border px-1.5 py-0.5 transition-colors"
              >
                Reset
              </button>
            )}
          </div>
        </div>
        <Slider
          value={[spread]}
          min={1}
          max={1000}
          step={1}
          onValueChange={(v) => {
            setSpread(v[0]);
            setDraft(String(v[0]));
          }}
        />
        <div className="flex justify-between text-[8px] text-muted-foreground mt-1 font-mono">
          <span>1bp</span>
          <span className="text-muted-foreground">
            base {Math.round(baseSpread)}bp
          </span>
          <span>1000bp</span>
        </div>
      </div>

      <div className="flex gap-4 mb-3 shrink-0">
        <div className="border border-border px-3 py-1.5 flex-1 text-center">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest">1Y Impl. PD</div>
          <div className={`text-base font-bold font-mono ${isHighRisk ? "text-red-400" : "text-white"}`}>
            {(live.impliedPd1y * 100).toFixed(2)}%
          </div>
        </div>
        <div className="border border-border px-3 py-1.5 flex-1 text-center">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest">5Y Impl. PD</div>
          <div className={`text-base font-bold font-mono ${isHighRisk ? "text-red-400" : "text-white"}`}>
            {(live.impliedPd5y * 100).toFixed(2)}%
          </div>
        </div>
        <div className="border border-border px-3 py-1.5 flex-1 text-center">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest">Recovery</div>
          <div className="text-base font-bold font-mono text-white">
            {(recovery * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Survival Probability Curve</div>
        <ResponsiveContainer width="100%" height="80%">
          <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="survivalGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ffffff" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#ffffff" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="defaultGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#ef4444" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 2" stroke="#222" vertical={false} />
            <XAxis dataKey="tenor" tick={{ fontSize: 9, fill: "#666" }} tickLine={false} axisLine={false} />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 9, fill: "#666" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="survivalPct"
              name="Survival"
              stroke="#ffffff"
              strokeWidth={1.5}
              fill="url(#survivalGrad)"
              dot={false}
            />
            <Area
              type="monotone"
              dataKey="defaultPct"
              name="Default"
              stroke="#ef4444"
              strokeWidth={1.5}
              fill="url(#defaultGrad)"
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>

        <div className="mt-1 border border-border">
          <table className="w-full text-[10px]">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="text-left py-1 px-2 uppercase tracking-wider text-[9px]">Tenor</th>
                <th className="text-right py-1 px-2 uppercase tracking-wider text-[9px]">Survival</th>
                <th className="text-right py-1 px-2 uppercase tracking-wider text-[9px]">Def Prob</th>
                <th className="text-right py-1 px-2 uppercase tracking-wider text-[9px]">Hazard (bp)</th>
              </tr>
            </thead>
            <tbody>
              {live.survivalCurve.map((pt: any) => (
                <tr key={pt.tenor} className="border-b border-border/40 hover:bg-white/5">
                  <td className="py-1 px-2 font-bold">{pt.tenor}</td>
                  <td className="py-1 px-2 text-right font-mono">{(pt.survivalProb * 100).toFixed(2)}%</td>
                  <td className={`py-1 px-2 text-right font-mono ${pt.defaultProb > 0.1 ? "text-red-400" : "text-white"}`}>
                    {(pt.defaultProb * 100).toFixed(2)}%
                  </td>
                  <td className="py-1 px-2 text-right font-mono text-muted-foreground">
                    {(pt.hazardRate * 10000).toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
