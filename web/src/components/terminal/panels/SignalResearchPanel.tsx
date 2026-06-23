// @ts-nocheck
import React from "react";
import type { SignalResearchData } from "@workspace/api-client-react";
import { CoverageBadge, type DataCoverage } from "./CoverageBadge";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
  Cell,
} from "recharts";

interface Props {
  data: SignalResearchData;
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[8px] text-muted-foreground uppercase tracking-widest">{label}</span>
      <span className={`font-mono text-[13px] leading-tight ${tone ?? "text-white"}`}>{value}</span>
    </div>
  );
}

export function SignalResearchPanel({ data }: Props) {
  const {
    label,
    description,
    universe,
    universeSize,
    included,
    excluded,
    excludedNames,
    holding,
    quantiles,
    ic,
    decay,
    turnover,
    turnoverAnnual,
    rebalances,
    quantileReturns,
    spread,
    spreadStats,
  } = data;

  const icTone = ic.mean > 0 ? "text-emerald-400" : ic.mean < 0 ? "text-red-400" : "text-white";
  const spreadTone =
    spreadStats.totalReturn > 0 ? "text-emerald-400" : spreadStats.totalReturn < 0 ? "text-red-400" : "text-white";

  const decayData = decay.map((d) => ({ horizon: `${d.horizon}d`, ic: d.ic }));
  const qData = quantileReturns.map((q) => ({ q: `Q${q.quantile}`, ret: q.ret }));

  const SpreadTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div className="bg-black border border-white/20 p-2 text-[10px] space-y-1 min-w-[140px] font-mono">
          <p className="text-muted-foreground mb-1">{label}</p>
          {payload.map((p: any) => (
            <p key={p.name} style={{ color: p.stroke }} className="flex justify-between gap-3">
              <span className="capitalize">{p.name}</span>
              <span>{p.value?.toFixed(1)}</span>
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  const coverage = (data as unknown as { coverage?: DataCoverage }).coverage;

  return (
    <div className="flex flex-col h-full gap-2">
      <div className="shrink-0">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          Alpha Signal · {label}
        </div>
        <div className="text-[9px] text-muted-foreground/70 mt-0.5">{description}</div>
      </div>
      <CoverageBadge coverage={coverage} />

      {/* Headline stats */}
      <div className="grid grid-cols-4 gap-2 shrink-0 border-y border-border/40 py-2">
        <Stat label={`Rank IC (${holding}d)`} value={ic.mean.toFixed(3)} tone={icTone} />
        <Stat label="IC IR" value={ic.ir.toFixed(2)} />
        <Stat label="t-Stat" value={ic.tStat.toFixed(2)} tone={Math.abs(ic.tStat) > 2 ? "text-white" : "text-muted-foreground"} />
        <Stat label="Hit Rate" value={`${ic.hitRate.toFixed(0)}%`} />
        <Stat label="L/S Return" value={`${spreadStats.totalReturn > 0 ? "+" : ""}${spreadStats.totalReturn.toFixed(1)}%`} tone={spreadTone} />
        <Stat label="L/S Sharpe" value={spreadStats.sharpe.toFixed(2)} />
        <Stat label="Turnover" value={`${turnover.toFixed(0)}%`} />
        <Stat label="Ann. Turnover" value={`${turnoverAnnual.toFixed(0)}%`} />
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        {/* Long-short spread equity curve */}
        <div className="flex-[3] min-h-0 flex flex-col">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
            Long-Short Spread · Equity Curve (rebased 100)
          </div>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={spread} margin={{ top: 2, right: 4, left: -22, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                <XAxis dataKey="t" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} minTickGap={28} tickFormatter={(v) => String(v).slice(5)} />
                <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
                <Tooltip content={<SpreadTooltip />} />
                <ReferenceLine y={100} stroke="#444" strokeDasharray="3 3" />
                <Line type="monotone" dataKey="value" name="spread" stroke="#ffffff" strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="long" name="long" stroke="#4ade80" strokeWidth={1} dot={false} strokeOpacity={0.7} />
                <Line type="monotone" dataKey="short" name="short" stroke="#f87171" strokeWidth={1} dot={false} strokeOpacity={0.7} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* IC decay + quantile returns */}
        <div className="flex-[2] min-h-0 flex flex-col gap-2">
          <div className="flex-1 min-h-0 flex flex-col">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
              IC Decay by Horizon
            </div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={decayData} margin={{ top: 2, right: 4, left: -24, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                  <XAxis dataKey="horizon" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} />
                  <Tooltip
                    cursor={{ fill: "#ffffff10" }}
                    contentStyle={{ background: "#000", border: "1px solid #ffffff33", fontSize: 10 }}
                    formatter={(v: any) => [Number(v).toFixed(3), "IC"]}
                  />
                  <ReferenceLine y={0} stroke="#444" />
                  <Bar dataKey="ic" radius={[1, 1, 0, 0]}>
                    {decayData.map((d, i) => (
                      <Cell key={i} fill={d.ic >= 0 ? "#4ade80" : "#f87171"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="flex-1 min-h-0 flex flex-col">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
              Mean Fwd Return by Quantile (Q1 low → Q{quantiles} high)
            </div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={qData} margin={{ top: 2, right: 4, left: -24, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                  <XAxis dataKey="q" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    cursor={{ fill: "#ffffff10" }}
                    contentStyle={{ background: "#000", border: "1px solid #ffffff33", fontSize: 10 }}
                    formatter={(v: any) => [`${Number(v).toFixed(2)}%`, "Mean Fwd"]}
                  />
                  <ReferenceLine y={0} stroke="#444" />
                  <Bar dataKey="ret" radius={[1, 1, 0, 0]}>
                    {qData.map((d, i) => (
                      <Cell key={i} fill={d.ret >= 0 ? "#4ade80" : "#f87171"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      {/* Coverage footer */}
      <div className="shrink-0 border-t border-border/40 pt-1.5 flex items-center justify-between gap-3">
        <div className="text-[8px] text-muted-foreground uppercase tracking-widest">
          {universe} · {included}/{universeSize} included · {rebalances} rebalances
        </div>
        {excluded > 0 ? (
          <div className="text-[8px] text-amber-400/80 font-mono truncate max-w-[55%]" title={excludedNames.map((e) => `${e.symbol}: ${e.reason}`).join(", ")}>
            {excluded} excluded: {excludedNames.slice(0, 4).map((e) => e.symbol).join(", ")}
            {excludedNames.length > 4 ? "…" : ""}
          </div>
        ) : (
          <div className="text-[8px] text-emerald-400/70 uppercase tracking-widest">full coverage</div>
        )}
      </div>
    </div>
  );
}
