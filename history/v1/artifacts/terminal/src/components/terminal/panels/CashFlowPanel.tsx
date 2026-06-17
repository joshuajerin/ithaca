import React, { useMemo, useState } from "react";
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
import { Slider } from "@/components/ui/slider";

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

const FREQ = 2;

// Mirror of api-server _bond_price (skills.py)
function bondPrice(couponRate: number, ytm: number, years: number, freq = FREQ): number {
  const n = Math.round(years * freq);
  const c = couponRate / 100 / freq;
  const y = ytm / 100 / freq;
  if (n === 0) return 100;
  const pvCoupons = y !== 0 ? (c * (1 - Math.pow(1 + y, -n))) / y : c * n;
  const pvPrincipal = 1 / Math.pow(1 + y, n);
  return (pvCoupons + pvPrincipal) * 100;
}

// Mirror of api-server build_cashflow_duration metric math (skills.py)
function computeMetrics(
  coupon: number,
  ytm: number,
  years: number,
  face = 100,
  freq = FREQ,
) {
  const n = Math.round(years * freq);
  const c = coupon / 100 / freq;
  const y = ytm / 100 / freq;
  const price = bondPrice(coupon, ytm, years, freq);

  let totalPv = 0;
  let weightedTime = 0;
  const totals: number[] = [];
  for (let i = 1; i <= n; i++) {
    const tYears = i / freq;
    const cfCoupon = face * c;
    const cfPrincipal = i === n ? face : 0;
    const cfTotal = cfCoupon + cfPrincipal;
    const discount = Math.pow(1 + y, i);
    const cfPv = cfTotal / discount;
    totalPv += cfPv;
    weightedTime += cfPv * tYears;
    totals.push(cfTotal);
  }

  const macaulay = totalPv ? weightedTime / totalPv : 0;
  const modDuration = macaulay / (1 + y);

  let conv = 0;
  for (let i = 1; i <= n; i++) {
    const tYears = i / freq;
    const discount = Math.pow(1 + y, i);
    conv += (totals[i - 1] / discount) * tYears * (tYears + 1 / freq);
  }
  const convexity = totalPv ? conv / totalPv / Math.pow(1 + y, 2) : 0;
  const dv01 = (modDuration * price) / 10000;

  return { price, modDuration, effDuration: modDuration, convexity, dv01 };
}

export function CashFlowPanel({ data }: CashFlowPanelProps) {
  const [shiftBps, setShiftBps] = useState(0);

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

  // Years to maturity, mirroring the Python builder (floor of 0.5y)
  const yearsToMat = useMemo(() => {
    const mat = new Date(data.maturityDate).getTime();
    const days = (mat - Date.now()) / (1000 * 60 * 60 * 24);
    return Math.max(days / 365.25, 0.5);
  }, [data.maturityDate]);

  const live = useMemo(
    () =>
      computeMetrics(data.coupon, data.yieldPct + shiftBps / 100, yearsToMat, data.faceValue ?? 100),
    [data.coupon, data.yieldPct, data.faceValue, yearsToMat, shiftBps],
  );

  const livePrice = shiftBps === 0 ? basePrice : live.price;
  const priceChg = livePrice - basePrice;
  const priceChgPct = basePrice ? (priceChg / basePrice) * 100 : 0;
  const liveYield = data.yieldPct + shiftBps / 100;
  const isShifted = shiftBps !== 0;
  const chgPositive = priceChg >= 0;

  const metricCards = [
    { label: "Mod Dur", value: live.modDuration.toFixed(2), unit: "yr" },
    { label: "Eff Dur", value: live.effDuration.toFixed(2), unit: "yr" },
    { label: "Convexity", value: live.convexity.toFixed(2), unit: "" },
    { label: "DV01", value: (live.dv01 * 100).toFixed(4), unit: "¢" },
  ];

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex justify-between items-start mb-2 shrink-0">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">
            Cash Flow & Duration
          </div>
          <div className="text-base font-bold leading-tight">{data.issuer}</div>
          <div className="text-[10px] text-muted-foreground mt-0.5">
            {data.coupon}% · Matures {data.maturityDate} · YTM {liveYield.toFixed(2)}%
          </div>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-bold font-mono ${isShifted ? (chgPositive ? "text-green-400" : "text-red-400") : ""}`}>
            {livePrice.toFixed(2)}
          </div>
          <div className="text-[10px] text-muted-foreground">
            {isShifted ? (
              <span className={chgPositive ? "text-green-400" : "text-red-400"}>
                {chgPositive ? "+" : ""}
                {priceChg.toFixed(2)} ({chgPositive ? "+" : ""}
                {priceChgPct.toFixed(2)}%)
              </span>
            ) : (
              "Price (per 100)"
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2 mb-2 shrink-0">
        {metricCards.map(({ label, value, unit }) => (
          <div key={label} className="border border-border px-2 py-1.5 text-center">
            <div className="text-[9px] text-muted-foreground uppercase tracking-wider">{label}</div>
            <div className="text-sm font-bold font-mono">{value}{unit}</div>
          </div>
        ))}
      </div>

      <div className="border border-border px-3 py-2 mb-2 shrink-0">
        <div className="flex justify-between items-center mb-1.5">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest">Rate Shift</div>
          <div className="flex items-center gap-2">
            <span
              className={`text-xs font-bold font-mono ${
                isShifted ? (shiftBps > 0 ? "text-red-400" : "text-green-400") : "text-white"
              }`}
            >
              {shiftBps > 0 ? "+" : ""}
              {shiftBps}bp
            </span>
            {isShifted && (
              <button
                onClick={() => setShiftBps(0)}
                className="text-[9px] text-muted-foreground hover:text-white uppercase tracking-wider border border-border px-1.5 py-0.5 transition-colors"
              >
                Reset
              </button>
            )}
          </div>
        </div>
        <Slider
          value={[shiftBps]}
          min={-300}
          max={300}
          step={5}
          onValueChange={(v) => setShiftBps(v[0])}
        />
        <div className="flex justify-between text-[8px] text-muted-foreground mt-1 font-mono">
          <span>-300bp</span>
          <span>0</span>
          <span>+300bp</span>
        </div>
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
