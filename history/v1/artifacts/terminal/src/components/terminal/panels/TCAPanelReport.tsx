import React, { useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { AlertTriangle } from "lucide-react";

interface AlgoFill {
  avgFill: number;
  fillRate: number;
  isBps: number;
  vwapSlipBps: number;
}

interface Order {
  symbol: string;
  name: string;
  side: string;
  shares: number;
  notional: number;
  price?: number;
  targetWeight?: number;
  currentWeight?: number;
  deltaWeight?: number;
  supported: boolean;
  reason?: string;
  arrivalPrice?: number;
  intervalVwap?: number;
  chosenAlgo?: string;
  algos?: Record<string, AlgoFill>;
  schedule?: Array<{
    time: string;
    price: number;
    marketVolume: number;
    childShares: number;
    participation: number;
    cumPct: number;
  }>;
  isBps?: number;
  vwapSlipBps?: number;
  impactBps?: number;
  allInBps?: number;
  costUsd?: number;
  fillRate?: number;
  adv?: number;
  dailyVol?: number;
}

function fmtUsd(n?: number): string {
  if (n == null) return "—";
  const a = Math.abs(n);
  if (a >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

function fmtBps(n?: number): string {
  if (n == null) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}`;
}

function bpsColor(n?: number): string {
  if (n == null) return "text-muted-foreground";
  if (n > 1) return "text-rose-400";
  if (n < -1) return "text-emerald-400";
  return "text-white";
}

function Metric({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="border-t border-border pt-2">
      <div className="text-[9px] uppercase tracking-widest text-muted-foreground mb-0.5">{label}</div>
      <div className={`text-base font-bold font-mono leading-none ${color || "text-white"}`}>{value}</div>
      {sub && <div className="text-[8.5px] text-muted-foreground mt-0.5">{sub}</div>}
    </div>
  );
}

const ScheduleTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-black border border-border text-xs p-2 space-y-1">
      <div className="font-bold text-[10px] uppercase tracking-wider">{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex justify-between gap-3">
          <span className="text-muted-foreground">{p.name}</span>
          <span className="font-mono">
            {p.dataKey === "participation"
              ? `${(p.value * 100).toFixed(1)}%`
              : `$${Number(p.value).toFixed(2)}`}
          </span>
        </div>
      ))}
    </div>
  );
};

export function TCAPanelReport({ data }: { data: any }) {
  const orders: Order[] = data.orders || [];
  const agg = data.aggregate || {};
  const supported = orders.filter((o) => o.supported);

  const [selected, setSelected] = useState<string>(supported[0]?.symbol || orders[0]?.symbol || "");
  const focus = orders.find((o) => o.symbol === selected) || supported[0] || orders[0];

  return (
    <div className="flex flex-col h-full gap-3 text-xs">
      {/* Aggregate header */}
      <div className="grid grid-cols-5 gap-x-4 shrink-0">
        <Metric label="Gross Notional" value={fmtUsd(agg.grossNotional)} sub={`${agg.supportedCount}/${agg.orderCount} orders`} />
        <Metric label="Impl. Shortfall" value={`${fmtBps(agg.isBps)} bps`} color={bpsColor(agg.isBps)} sub="vs arrival · real" />
        <Metric label="VWAP Slippage" value={`${fmtBps(agg.vwapSlipBps)} bps`} color={bpsColor(agg.vwapSlipBps)} sub="vs interval · real" />
        <Metric label="Impact (model)" value={`${fmtBps(agg.impactBps)} bps`} color="text-amber-300" sub="square-root" />
        <Metric label="All-in Cost" value={fmtUsd(agg.totalCostUsd)} color={bpsColor(agg.allInBps)} sub={`${fmtBps(agg.allInBps)} bps`} />
      </div>

      {/* Benchmark/model note */}
      <div className="shrink-0 text-[9px] text-muted-foreground leading-snug border-l-2 border-amber-300/40 pl-2">
        {data.benchmarkNote}
        {data.model && (
          <span className="text-muted-foreground/70">
            {" "}· {data.model.name}: <span className="font-mono">{data.model.formula}</span>
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 flex-1 min-h-0">
        {/* Orders table */}
        <div className="flex flex-col min-h-0 overflow-hidden">
          <div className="text-[9px] uppercase tracking-widest text-muted-foreground mb-1 shrink-0 flex justify-between">
            <span>Orders ({data.intervalLabel} · {data.rangeLabel})</span>
            <span className="text-muted-foreground/60">algo: {String(data.chosenAlgo).toUpperCase()}</span>
          </div>
          <div className="overflow-auto flex-1 -mx-1 px-1">
            <table className="w-full text-[10px]">
              <thead className="sticky top-0 bg-black">
                <tr className="text-muted-foreground uppercase tracking-wider text-[8.5px] border-b border-border">
                  <th className="text-left py-1 font-normal">Order</th>
                  <th className="text-right py-1 font-normal">Notional</th>
                  <th className="text-right py-1 font-normal" title="Implementation shortfall vs arrival (real)">IS</th>
                  <th className="text-right py-1 font-normal" title="Slippage vs interval VWAP (real)">VWAP</th>
                  <th className="text-right py-1 font-normal text-amber-300/80" title="Modeled square-root impact">Impact</th>
                  <th className="text-right py-1 font-normal" title="All-in = realized IS + modeled impact">All-in</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => {
                  const isSel = o.symbol === selected;
                  if (!o.supported) {
                    return (
                      <tr key={o.symbol} className="border-b border-border/30 text-muted-foreground/60">
                        <td className="py-1.5">
                          <div className="flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3 text-amber-300/60" strokeWidth={1.5} />
                            <span className="uppercase font-mono">{o.symbol}</span>
                          </div>
                          <div className="text-[8px] italic">{o.reason || "unsupported"}</div>
                        </td>
                        <td className="text-right py-1.5 font-mono">{fmtUsd(o.notional)}</td>
                        <td colSpan={4} className="text-right py-1.5 text-[8.5px] uppercase tracking-wider">no real intraday data</td>
                      </tr>
                    );
                  }
                  return (
                    <tr
                      key={o.symbol}
                      onClick={() => setSelected(o.symbol)}
                      className={`border-b border-border/30 cursor-pointer transition-colors ${isSel ? "bg-white/5" : "hover:bg-white/[0.02]"}`}
                    >
                      <td className="py-1.5">
                        <div className="flex items-center gap-1.5">
                          <span className={`text-[8px] uppercase font-bold px-1 rounded-sm ${o.side === "buy" ? "bg-emerald-400/15 text-emerald-300" : "bg-rose-400/15 text-rose-300"}`}>
                            {o.side}
                          </span>
                          <span className="uppercase font-mono">{o.symbol}</span>
                        </div>
                        <div className="text-[8px] text-muted-foreground">
                          {Math.round(o.shares).toLocaleString()} sh
                          {o.fillRate != null && o.fillRate < 0.999 ? ` · ${(o.fillRate * 100).toFixed(0)}% filled` : ""}
                        </div>
                      </td>
                      <td className="text-right py-1.5 font-mono">{fmtUsd(o.notional)}</td>
                      <td className={`text-right py-1.5 font-mono ${bpsColor(o.isBps)}`}>{fmtBps(o.isBps)}</td>
                      <td className={`text-right py-1.5 font-mono ${bpsColor(o.vwapSlipBps)}`}>{fmtBps(o.vwapSlipBps)}</td>
                      <td className="text-right py-1.5 font-mono text-amber-300/90">{fmtBps(o.impactBps)}</td>
                      <td className={`text-right py-1.5 font-mono font-bold ${bpsColor(o.allInBps)}`}>{fmtBps(o.allInBps)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Focus order: algo comparison + schedule */}
        <div className="flex flex-col min-h-0 overflow-hidden">
          {focus && focus.supported && focus.algos ? (
            <>
              <div className="text-[9px] uppercase tracking-widest text-muted-foreground mb-1 shrink-0 flex justify-between">
                <span>{focus.symbol} · Algo Comparison</span>
                <span className="font-mono text-muted-foreground/70">
                  arr ${focus.arrivalPrice?.toFixed(2)} · vwap ${focus.intervalVwap?.toFixed(2)}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 shrink-0 mb-2">
                {(["vwap", "twap", "pov"] as const).map((a) => {
                  const f = focus.algos![a];
                  if (!f) return null;
                  const isChosen = a === focus.chosenAlgo;
                  return (
                    <div key={a} className={`border p-1.5 ${isChosen ? "border-white/40" : "border-border"}`}>
                      <div className="text-[8px] uppercase tracking-widest text-muted-foreground flex justify-between">
                        <span>{a}</span>
                        {f.fillRate < 0.999 && <span className="text-amber-300/80">{(f.fillRate * 100).toFixed(0)}%</span>}
                      </div>
                      <div className="font-mono text-sm">${f.avgFill.toFixed(2)}</div>
                      <div className={`font-mono text-[9px] ${bpsColor(f.isBps)}`}>{fmtBps(f.isBps)} bps IS</div>
                    </div>
                  );
                })}
              </div>
              <div className="text-[9px] uppercase tracking-widest text-muted-foreground mb-1 shrink-0">
                {String(focus.chosenAlgo).toUpperCase()} Schedule vs Volume
              </div>
              <div className="flex-1 min-h-0">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={focus.schedule} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" />
                    <XAxis dataKey="time" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                    <YAxis yAxisId="price" domain={["auto", "auto"]} tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v.toFixed(0)}`} />
                    <YAxis yAxisId="part" orientation="right" domain={[0, "auto"]} tick={{ fontSize: 8, fill: "#444" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                    <Tooltip content={<ScheduleTooltip />} />
                    <Bar yAxisId="part" dataKey="participation" name="Participation" fill="#ffffff" opacity={0.14} barSize={8} />
                    <Line yAxisId="price" type="monotone" dataKey="price" name="Bucket Px" stroke="#ffffff" strokeWidth={1.5} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-2 text-center">
              <AlertTriangle className="w-5 h-5 text-amber-300/60" strokeWidth={1.25} />
              <span className="text-[9px] uppercase tracking-widest">
                {orders.length && !supported.length
                  ? "No real intraday data for any order"
                  : "Select a supported order"}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
