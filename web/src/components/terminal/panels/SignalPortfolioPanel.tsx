// @ts-nocheck
import React from "react";
import { CoverageBadge, type DataCoverage } from "./CoverageBadge";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

interface Holding {
  symbol: string;
  name?: string;
  side: "long" | "short";
  weight: number;
  score: number;
}

interface StatBlock {
  sharpe: number;
  sortino: number;
  cagr: number;
  totalReturn: number;
  vol: number;
  maxDD: number;
  winRate: number;
  turnover: number;
  var95: number;
  cvar95: number;
}

interface SignalPortfolioData {
  signal: string;
  label: string;
  description: string;
  scheme: string;
  schemeLabel: string;
  universe: string;
  universeSize: number;
  included: number;
  excluded: number;
  excludedNames: { symbol: string; reason: string }[];
  holding: number;
  quantiles: number;
  rebalances: number;
  longCount: number;
  shortCount: number;
  gross: number;
  net: number;
  holdings: Holding[];
  curve: { t: string; strategy: number; benchmark: number }[];
  drawdown: { t: string; dd: number }[];
  stats: StatBlock;
  benchStats: StatBlock;
  turnover: number;
  turnoverAnnual: number;
  borrowDragBpsAnnual?: number | null;
  borrowCostTotalPct?: number | null;
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[8px] text-muted-foreground uppercase tracking-widest">{label}</span>
      <span className={`font-mono text-[13px] leading-tight ${tone ?? "text-white"}`}>{value}</span>
    </div>
  );
}

export function SignalPortfolioPanel({ data }: { data: SignalPortfolioData }) {
  const {
    label,
    schemeLabel,
    universe,
    universeSize,
    included,
    excluded,
    excludedNames,
    holding,
    quantiles,
    rebalances,
    longCount,
    shortCount,
    gross,
    net,
    holdings,
    curve,
    drawdown,
    stats,
    benchStats,
    turnover,
    turnoverAnnual,
    borrowDragBpsAnnual,
  } = data;

  const retTone = stats.totalReturn > 0 ? "text-emerald-400" : stats.totalReturn < 0 ? "text-red-400" : "text-white";
  const vsB = stats.totalReturn - benchStats.totalReturn;
  const vsTone = vsB > 0 ? "text-emerald-400" : vsB < 0 ? "text-red-400" : "text-muted-foreground";

  const dsCurve = curve.filter((_, i) => i % Math.max(1, Math.floor(curve.length / 120)) === 0);
  const dsDD = drawdown.filter((_, i) => i % Math.max(1, Math.floor(drawdown.length / 120)) === 0);

  const longs = holdings.filter((h) => h.side === "long");
  const shorts = holdings.filter((h) => h.side === "short");
  const coverage = (data as unknown as { coverage?: DataCoverage }).coverage;

  const CurveTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div className="bg-black border border-white/20 p-2 text-[10px] space-y-1 font-mono min-w-[150px]">
          <p className="text-muted-foreground mb-1">{label}</p>
          {payload.map((p: any) => (
            <p key={p.name} style={{ color: p.color }} className="flex justify-between gap-3">
              <span>{p.name}</span>
              <span>{Number(p.value).toFixed(2)}</span>
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex flex-col h-full gap-2">
      <div className="shrink-0 flex items-start justify-between gap-3">
        <div>
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
            Portfolio · {label}
          </div>
          <div className="text-[9px] text-muted-foreground/70 mt-0.5">{schemeLabel}</div>
        </div>
        <div className="text-[8px] text-muted-foreground uppercase tracking-widest text-right shrink-0">
          {longCount} long{shortCount ? ` / ${shortCount} short` : ""}
          <br />
          gross {gross.toFixed(2)}× · net {net.toFixed(2)}
        </div>
      </div>
      <CoverageBadge coverage={coverage} />

      {/* Headline realized stats */}
      <div className="grid grid-cols-4 gap-2 shrink-0 border-y border-border/40 py-2">
        <Stat label="Total Return" value={`${stats.totalReturn > 0 ? "+" : ""}${stats.totalReturn.toFixed(1)}%`} tone={retTone} />
        <Stat label="Sharpe" value={stats.sharpe.toFixed(2)} tone={stats.sharpe > 1 ? "text-emerald-400" : "text-white"} />
        <Stat label="CAGR" value={`${stats.cagr.toFixed(1)}%`} />
        <Stat label="Max DD" value={`${stats.maxDD.toFixed(1)}%`} tone="text-red-400" />
        <Stat label="Vol (ann)" value={`${stats.vol.toFixed(1)}%`} />
        <Stat label="VaR 95" value={`${stats.var95.toFixed(1)}%`} tone="text-muted-foreground" />
        {shortCount > 0 && borrowDragBpsAnnual != null ? (
          <Stat label="Borrow Drag" value={`${borrowDragBpsAnnual.toFixed(0)} bps/yr`} tone="text-orange-300" />
        ) : (
          <Stat label="Ann. Turnover" value={`${turnoverAnnual.toFixed(0)}%`} />
        )}
        <Stat label="vs Benchmark" value={`${vsB > 0 ? "+" : ""}${vsB.toFixed(1)}%`} tone={vsTone} />
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        {/* Realized equity + drawdown */}
        <div className="flex-[3] min-h-0 flex flex-col gap-2">
          <div className="flex-[2] min-h-0 flex flex-col">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
              Realized Equity vs Equal-Weight Benchmark (rebased 100)
            </div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={dsCurve} margin={{ top: 2, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                  <XAxis dataKey="t" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} minTickGap={36} tickFormatter={(v) => String(v).slice(5)} />
                  <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
                  <Tooltip content={<CurveTooltip />} />
                  <ReferenceLine y={100} stroke="#444" strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="strategy" stroke="#ffffff" strokeWidth={1.5} dot={false} name="Portfolio" />
                  <Line type="monotone" dataKey="benchmark" stroke="#666666" strokeWidth={1} dot={false} name="Benchmark" strokeDasharray="4 2" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="flex-1 min-h-0 flex flex-col">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">Drawdown</div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={dsDD} margin={{ top: 2, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                  <XAxis dataKey="t" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} minTickGap={36} tickFormatter={(v) => String(v).slice(5)} />
                  <YAxis tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                  <Tooltip contentStyle={{ background: "#000", border: "1px solid #ffffff33", fontSize: 10 }} formatter={(v: any) => [`${Number(v).toFixed(2)}%`, "DD"]} />
                  <defs>
                    <linearGradient id="spDDGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#ef4444" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#ef4444" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <Area type="monotone" dataKey="dd" stroke="#ef4444" strokeWidth={1} fill="url(#spDDGrad)" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Holdings book */}
        <div className="flex-[2] min-h-0 flex flex-col">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
            Current Book · rebalanced every {holding}d
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-2">
            <HoldingGroup title={`Long (Q${quantiles})`} rows={longs} tone="text-emerald-400" />
            {shorts.length > 0 && <HoldingGroup title="Short (Q1)" rows={shorts} tone="text-red-400" />}
          </div>
        </div>
      </div>

      {/* Coverage footer */}
      <div className="shrink-0 border-t border-border/40 pt-1.5 flex items-center justify-between gap-3">
        <div className="text-[8px] text-muted-foreground uppercase tracking-widest">
          {universe} · {included}/{universeSize} included · {rebalances} rebalances · {turnover.toFixed(0)}% churn
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

function HoldingGroup({ title, rows, tone }: { title: string; rows: Holding[]; tone: string }) {
  if (rows.length === 0) return null;
  return (
    <div>
      <div className="text-[8px] text-muted-foreground uppercase tracking-widest mb-1 flex justify-between">
        <span>{title}</span>
        <span>{rows.length} names</span>
      </div>
      <div className="space-y-0.5">
        {rows.map((h) => (
          <div key={`${h.side}-${h.symbol}`} className="flex items-center justify-between gap-2 text-[10px] font-mono">
            <span className="text-white truncate flex-1" title={h.name}>{h.symbol}</span>
            <span className="text-muted-foreground/70 tabular-nums w-14 text-right">{h.score.toFixed(3)}</span>
            <span className={`${tone} tabular-nums w-14 text-right`}>
              {h.weight > 0 ? "+" : ""}{(h.weight * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
