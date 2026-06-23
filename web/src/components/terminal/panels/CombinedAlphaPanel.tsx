// @ts-nocheck
import React from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
  BarChart,
  Bar,
  Cell,
} from "recharts";

interface ICStat {
  mean: number;
  std: number;
  ir: number;
  tStat: number;
  hitRate: number;
  n: number;
}

interface CompositeBlock {
  label: string;
  ic: ICStat;
  decay: { horizon: number; ic: number }[];
  quantileReturns: { quantile: number; ret: number }[];
  spread: { t: string; value: number; long: number; short: number }[];
  spreadStats: { totalReturn: number; sharpe: number; cagr: number };
  turnover: number;
  turnoverAnnual: number;
  rebalances: number;
  included: number;
}

interface Row {
  signal: string;
  label: string;
  weight: number | null;
  meanIC: number;
  icIR: number;
  tStat: number;
  hitRate: number;
  turnover: number;
  spreadReturn: number;
  spreadSharpe: number;
  included: number;
  spark: number[];
  isComposite: boolean;
}

interface CombinedAlphaData {
  signal: string;
  label: string;
  method: string;
  methodLabel: string;
  description: string;
  universe: string;
  universeSize: number;
  included: number;
  excluded: number;
  excludedNames: { symbol: string; reason: string }[];
  holding: number;
  quantiles: number;
  weights: { signal: string; label: string; weight: number }[];
  correlation: { signals: string[]; labels: string[]; matrix: number[][] };
  composite: CompositeBlock;
  rows: Row[];
}

function fmt(v: number, d = 3): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(d);
}

function icTone(v: number): string {
  if (v > 0.03) return "text-emerald-400";
  if (v > 0) return "text-emerald-400/70";
  if (v < -0.03) return "text-red-400";
  if (v < 0) return "text-red-400/70";
  return "text-muted-foreground";
}

function corrColor(v: number): string {
  // Diverging: red (high positive overlap) → neutral → blue (negative).
  const a = Math.max(-1, Math.min(1, v));
  if (a >= 0) {
    const alpha = 0.12 + a * 0.6;
    return `rgba(239, 68, 68, ${alpha.toFixed(3)})`;
  }
  const alpha = 0.12 + Math.abs(a) * 0.6;
  return `rgba(59, 130, 246, ${alpha.toFixed(3)})`;
}

function Sparkline({ data, positive }: { data: number[]; positive: boolean }) {
  if (!data || data.length < 2) return <div className="h-5" />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 64;
  const h = 18;
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * h}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline
        points={pts}
        fill="none"
        stroke={positive ? "#34d399" : "#f87171"}
        strokeWidth={1}
      />
    </svg>
  );
}

export function CombinedAlphaPanel({ data }: { data: CombinedAlphaData }) {
  const {
    methodLabel,
    universe,
    universeSize,
    included,
    excluded,
    excludedNames,
    holding,
    quantiles,
    weights,
    correlation,
    composite,
    rows,
  } = data;

  const dsSpread = composite.spread.filter(
    (_, i) => i % Math.max(1, Math.floor(composite.spread.length / 120)) === 0,
  );

  const labels = correlation?.labels ?? [];
  const matrix = correlation?.matrix ?? [];

  const compRet = composite.spreadStats.totalReturn;
  const retTone = compRet > 0 ? "text-emerald-400" : compRet < 0 ? "text-red-400" : "text-white";

  const decayData = composite.decay.map((d) => ({ ...d, horizon: `${d.horizon}d` }));
  const qData = composite.quantileReturns;

  const SpreadTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div className="bg-black border border-white/20 p-2 text-[10px] space-y-1 font-mono min-w-[140px]">
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
            Combined Alpha · Composite Blend
          </div>
          <div className="text-[9px] text-muted-foreground/70 mt-0.5">
            {weights.length} signals · {methodLabel}
          </div>
        </div>
        <div className="text-[8px] text-muted-foreground uppercase tracking-widest text-right shrink-0">
          rebalanced every {holding}d
          <br />
          {composite.rebalances} rebalances · Q{quantiles}
        </div>
      </div>

      {/* Headline composite stats */}
      <div className="grid grid-cols-5 gap-2 shrink-0 border-y border-border/40 py-2">
        <Stat label="Composite IC" value={fmt(composite.ic.mean, 4)} tone={icTone(composite.ic.mean)} />
        <Stat label="IC IR" value={fmt(composite.ic.ir, 2)} tone={composite.ic.ir > 0.5 ? "text-emerald-400" : "text-white"} />
        <Stat label="t-stat" value={fmt(composite.ic.tStat, 2)} />
        <Stat label="LS Spread" value={`${compRet > 0 ? "+" : ""}${fmt(compRet, 1)}%`} tone={retTone} />
        <Stat label="Spread Sharpe" value={fmt(composite.spreadStats.sharpe, 2)} tone={composite.spreadStats.sharpe > 1 ? "text-emerald-400" : "text-white"} />
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        {/* Left: blend vs components table + weights */}
        <div className="flex-[3] min-h-0 flex flex-col gap-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest shrink-0">
            Blend vs Components
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto pr-1">
            <table className="w-full text-[10px] font-mono">
              <thead className="text-muted-foreground sticky top-0 bg-black">
                <tr className="border-b border-border/40 text-[8px] uppercase tracking-widest">
                  <th className="text-left font-normal py-1">Signal</th>
                  <th className="text-right font-normal">Wt</th>
                  <th className="text-right font-normal">IC</th>
                  <th className="text-right font-normal">IC IR</th>
                  <th className="text-right font-normal">Hit%</th>
                  <th className="text-right font-normal">Spread</th>
                  <th className="text-right font-normal">Turn</th>
                  <th className="text-right font-normal pl-2">Curve</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.signal}
                    className={`border-b border-border/20 ${
                      r.isComposite ? "bg-white/[0.04] text-white font-medium" : ""
                    }`}
                  >
                    <td className="text-left py-1 truncate max-w-[110px]">
                      {r.isComposite ? "▸ " : ""}
                      {r.label}
                    </td>
                    <td className="text-right text-muted-foreground tabular-nums">
                      {r.weight === null ? "—" : `${(r.weight * 100).toFixed(0)}%`}
                    </td>
                    <td className={`text-right tabular-nums ${icTone(r.meanIC)}`}>{fmt(r.meanIC, 4)}</td>
                    <td className="text-right tabular-nums">{fmt(r.icIR, 2)}</td>
                    <td className="text-right tabular-nums text-muted-foreground">{fmt(r.hitRate, 0)}</td>
                    <td className={`text-right tabular-nums ${r.spreadReturn > 0 ? "text-emerald-400/80" : "text-red-400/80"}`}>
                      {r.spreadReturn > 0 ? "+" : ""}
                      {fmt(r.spreadReturn, 1)}%
                    </td>
                    <td className="text-right tabular-nums text-muted-foreground">{fmt(r.turnover, 0)}%</td>
                    <td className="text-right pl-2">
                      <div className="flex justify-end">
                        <Sparkline data={r.spark} positive={r.spreadReturn >= 0} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Composite equity curve */}
          <div className="flex-1 min-h-0 flex flex-col">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
              Composite Long-Short Spread (rebased 100)
            </div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={dsSpread} margin={{ top: 2, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                  <XAxis dataKey="t" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} minTickGap={36} tickFormatter={(v) => String(v).slice(5)} />
                  <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
                  <Tooltip content={<SpreadTooltip />} />
                  <ReferenceLine y={100} stroke="#444" strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="value" stroke="#ffffff" strokeWidth={1.5} dot={false} name="Composite" />
                  <Line type="monotone" dataKey="long" stroke="#34d399" strokeWidth={1} dot={false} name="Long" />
                  <Line type="monotone" dataKey="short" stroke="#f87171" strokeWidth={1} dot={false} name="Short" strokeDasharray="4 2" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Right: correlation overlap + decay + quantiles */}
        <div className="flex-[2] min-h-0 flex flex-col gap-2">
          <div className="shrink-0">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
              Component Overlap (rank corr)
            </div>
            <div className="overflow-x-auto">
              <table className="text-[8px] font-mono border-collapse">
                <thead>
                  <tr>
                    <th className="w-12" />
                    {labels.map((l) => (
                      <th key={l} className="px-1 py-0.5 text-muted-foreground font-normal text-center max-w-[42px] truncate" title={l}>
                        {l.slice(0, 4)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matrix.map((row, a) => (
                    <tr key={labels[a]}>
                      <td className="pr-1 text-muted-foreground text-right truncate max-w-[48px]" title={labels[a]}>
                        {labels[a].slice(0, 6)}
                      </td>
                      {row.map((v, b) => (
                        <td
                          key={b}
                          className="text-center tabular-nums text-white/90 border border-black/40"
                          style={{ background: a === b ? "rgba(255,255,255,0.08)" : corrColor(v), minWidth: 30, height: 20 }}
                          title={`${labels[a]} vs ${labels[b]}: ${v.toFixed(2)}`}
                        >
                          {v.toFixed(2)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="flex-1 min-h-0 flex flex-col">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
              Composite IC Decay
            </div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={decayData} margin={{ top: 2, right: 4, left: -24, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                  <XAxis dataKey="horizon" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ background: "#000", border: "1px solid #ffffff33", fontSize: 10 }} formatter={(v: any) => [Number(v).toFixed(4), "IC"]} />
                  <ReferenceLine y={0} stroke="#444" />
                  <Bar dataKey="ic">
                    {decayData.map((d, i) => (
                      <Cell key={i} fill={d.ic >= 0 ? "#34d399" : "#f87171"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="flex-1 min-h-0 flex flex-col">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
              Composite Quantile Returns (mean fwd)
            </div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={qData} margin={{ top: 2, right: 4, left: -24, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                  <XAxis dataKey="quantile" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `Q${v}`} />
                  <YAxis tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                  <Tooltip contentStyle={{ background: "#000", border: "1px solid #ffffff33", fontSize: 10 }} formatter={(v: any) => [`${Number(v).toFixed(2)}%`, "Fwd Ret"]} />
                  <ReferenceLine y={0} stroke="#444" />
                  <Bar dataKey="ret">
                    {qData.map((d, i) => (
                      <Cell key={i} fill={d.ret >= 0 ? "#34d399" : "#f87171"} />
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
          {universe} · {included}/{universeSize} included · ann. turnover {composite.turnoverAnnual.toFixed(0)}%
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

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[8px] text-muted-foreground uppercase tracking-widest">{label}</span>
      <span className={`font-mono text-[13px] leading-tight ${tone ?? "text-white"}`}>{value}</span>
    </div>
  );
}
