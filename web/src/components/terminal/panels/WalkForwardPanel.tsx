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
} from "recharts";

interface CurvePoint {
  t: string;
  strategy: number;
  benchmark: number;
}
interface Stats {
  sharpe: number;
  sortino: number;
  cagr: number;
  totalReturn: number;
  vol: number;
  maxDD: number;
  winRate: number;
  turnover: number;
}
interface Fold {
  fold: number;
  isStart: string;
  isEnd: string;
  oosStart: string;
  oosEnd: string;
  isBars: number;
  oosBars: number;
  paramLabel: string;
  isSharpe: number;
  oosSharpe: number;
}
interface DeflatedSharpe {
  observed: number;
  benchmark: number;
  haircutSharpe: number;
  haircutPct: number;
  dsr: number;
  nTrials: number;
  skew: number;
  kurtosis: number;
}
interface Pbo {
  pbo: number;
  nTrials: number;
  nSplits: number;
  nCombos: number;
  medianLogit: number;
}
interface Verdict {
  label: string;
  summary: string;
}
interface Coverage {
  usable: boolean;
  bars: number;
  folds: number;
  neededBars: number;
  note: string;
}

export interface WalkForwardData {
  symbol?: string;
  name?: string;
  strategy: string;
  barCount: number;
  nSplits: number;
  paramGridSize: number;
  isCurve: CurvePoint[];
  oosCurve: CurvePoint[];
  isStats: Stats;
  oosStats: Stats;
  degradationPct: number;
  folds: Fold[];
  deflatedSharpe: DeflatedSharpe;
  pbo: Pbo | null;
  verdict: Verdict;
  coverage: Coverage;
  bestFullParam?: string;
  source?: string;
  asOf?: string | null;
}

interface Props {
  data: WalkForwardData;
  onRefine?: (params: Record<string, unknown>) => void;
}

const STRATEGIES: { value: string; label: string }[] = [
  { value: "momentum", label: "Momentum" },
  { value: "mean_reversion", label: "Mean Reversion" },
  { value: "ma_crossover", label: "MA Crossover" },
  { value: "buy_and_hold", label: "Buy & Hold" },
];

const VERDICT_STYLE: Record<string, { label: string; color: string; bg: string; border: string }> = {
  robust: { label: "ROBUST", color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/40" },
  some_decay: { label: "SOME DECAY", color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/40" },
  likely_overfit: { label: "LIKELY OVERFIT", color: "text-orange-400", bg: "bg-orange-500/10", border: "border-orange-500/40" },
  severe_overfitting: { label: "SEVERE OVERFITTING", color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/40" },
  inconclusive: { label: "INCONCLUSIVE", color: "text-muted-foreground", bg: "bg-white/5", border: "border-border" },
};

export function WalkForwardPanel({ data, onRefine }: Props) {
  const {
    strategy,
    isCurve,
    oosCurve,
    isStats,
    oosStats,
    degradationPct,
    folds,
    deflatedSharpe: dsr,
    pbo,
    verdict,
    coverage,
  } = data;

  const vStyle = VERDICT_STYLE[verdict?.label] ?? VERDICT_STYLE.inconclusive;

  const fmt = (v?: number, d = 2) =>
    typeof v === "number" && isFinite(v) ? v.toFixed(d) : "—";
  const fmtPct = (v?: number, d = 1) =>
    typeof v === "number" && isFinite(v) ? `${v.toFixed(d)}%` : "—";

  const downsample = (arr: CurvePoint[]) =>
    arr.filter((_, i) => i % Math.max(1, Math.floor(arr.length / 90)) === 0);

  const CurveTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div className="bg-black border border-white/20 p-2 text-xs space-y-1">
          <p className="text-muted-foreground">{label}</p>
          {payload.map((p: any) => (
            <p key={p.name} style={{ color: p.color }} className="font-mono">
              {p.name}: {p.value?.toFixed(2)}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  const Curve = ({ rows, title }: { rows: CurvePoint[]; title: string }) => (
    <div className="flex-1 min-h-0 flex flex-col">
      <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">{title}</div>
      <div className="flex-1 min-h-0">
        {rows.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={downsample(rows)} margin={{ top: 2, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
              <XAxis dataKey="t" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} minTickGap={40} />
              <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
              <Tooltip content={<CurveTooltip />} />
              <Line type="monotone" dataKey="strategy" stroke="#ffffff" strokeWidth={1.5} dot={false} name="Strategy" />
              <Line type="monotone" dataKey="benchmark" stroke="#555555" strokeWidth={1} dot={false} name="Benchmark" strokeDasharray="4 2" />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center text-[10px] text-muted-foreground">
            No data
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full gap-3">
      {onRefine && (
        <div className="flex items-center justify-between gap-2 shrink-0 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] text-muted-foreground uppercase tracking-widest">Strategy</span>
            <select
              value={strategy}
              onChange={(e) => onRefine({ symbol: data.symbol, strategy: e.target.value, splits: data.nSplits })}
              className="text-[10px] bg-black border border-border px-1.5 py-0.5 font-mono text-white focus:outline-none focus:border-white/60 transition-colors"
            >
              {STRATEGIES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] text-muted-foreground uppercase tracking-widest">Folds</span>
            <div className="flex gap-1">
              {[3, 4, 5, 6].map((n) => (
                <button
                  key={n}
                  onClick={() => {
                    if (n !== data.nSplits) onRefine({ symbol: data.symbol, strategy, splits: n });
                  }}
                  className={`text-[9px] px-2 py-0.5 border tracking-widest transition-colors ${
                    data.nSplits === n
                      ? "border-white text-white bg-white/10"
                      : "border-border text-muted-foreground hover:border-white/40"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Verdict banner */}
      <div className={`shrink-0 border ${vStyle.border} ${vStyle.bg} p-2.5`}>
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-[10px] font-bold tracking-widest ${vStyle.color}`}>{vStyle.label}</span>
          <span className="text-[9px] text-muted-foreground uppercase tracking-widest">
            {data.symbol} · {strategy.replace(/_/g, " ")} · {data.paramGridSize} configs · {data.nSplits} folds
          </span>
        </div>
        <p className="text-[11px] leading-relaxed text-white/80">{verdict?.summary}</p>
      </div>

      {!coverage?.usable && coverage?.note && (
        <div className="shrink-0 border border-yellow-500/40 bg-yellow-500/10 p-2 text-[10px] text-yellow-300/90">
          {coverage.note}
        </div>
      )}

      {/* Headline diagnostics */}
      <div className="grid grid-cols-4 gap-2 shrink-0">
        {[
          {
            label: "IS → OOS Sharpe",
            value: `${fmt(isStats?.sharpe)} → ${fmt(oosStats?.sharpe)}`,
            sub: `${fmtPct(degradationPct)} decay`,
            tone:
              degradationPct <= 20 ? "text-emerald-400" : degradationPct <= 50 ? "text-yellow-400" : "text-red-400",
          },
          {
            label: "Deflated Sharpe",
            value: fmtPct(dsr?.dsr, 0),
            sub: "confidence it's real",
            tone: (dsr?.dsr ?? 0) >= 90 ? "text-emerald-400" : (dsr?.dsr ?? 0) >= 60 ? "text-yellow-400" : "text-red-400",
          },
          {
            label: "MT Haircut",
            value: `${fmt(dsr?.observed)} → ${fmt(dsr?.haircutSharpe)}`,
            sub: `${fmtPct(dsr?.haircutPct, 0)} cut · ${dsr?.nTrials ?? "—"} trials`,
            tone: (dsr?.haircutPct ?? 0) <= 25 ? "text-emerald-400" : (dsr?.haircutPct ?? 0) <= 60 ? "text-yellow-400" : "text-red-400",
          },
          {
            label: "PBO",
            value: pbo ? fmtPct(pbo.pbo, 0) : "n/a",
            sub: pbo ? `${pbo.nCombos} CSCV splits` : "needs ≥2 configs",
            tone: !pbo
              ? "text-muted-foreground"
              : pbo.pbo <= 20
                ? "text-emerald-400"
                : pbo.pbo <= 50
                  ? "text-yellow-400"
                  : "text-red-400",
          },
        ].map((m) => (
          <div key={m.label} className="border border-border p-2">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">{m.label}</div>
            <div className={`text-sm font-bold font-mono ${m.tone}`}>{m.value}</div>
            <div className="text-[9px] text-muted-foreground mt-0.5">{m.sub}</div>
          </div>
        ))}
      </div>

      {/* Curves */}
      <div className="flex gap-2 shrink-0 h-32">
        <Curve rows={isCurve} title="In-Sample (best fit per fold)" />
        <Curve rows={oosCurve} title="Out-of-Sample (stitched, untouched)" />
      </div>

      {/* Per-fold table */}
      <div className="flex-1 min-h-0 flex flex-col">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
          Walk-Forward Folds — in-sample pick vs out-of-sample result
        </div>
        <div className="flex-1 min-h-0 overflow-auto border border-border">
          <table className="w-full text-[10px] font-mono">
            <thead className="sticky top-0 bg-black">
              <tr className="text-muted-foreground uppercase tracking-widest text-[8px]">
                <th className="text-left p-1.5 font-normal">Fold</th>
                <th className="text-left p-1.5 font-normal">IS Window</th>
                <th className="text-left p-1.5 font-normal">OOS Window</th>
                <th className="text-left p-1.5 font-normal">Chosen Params</th>
                <th className="text-right p-1.5 font-normal">IS Sharpe</th>
                <th className="text-right p-1.5 font-normal">OOS Sharpe</th>
              </tr>
            </thead>
            <tbody>
              {folds.map((f) => {
                const held = f.oosSharpe >= f.isSharpe * 0.5;
                return (
                  <tr key={f.fold} className="border-t border-border/50">
                    <td className="p-1.5">{f.fold}</td>
                    <td className="p-1.5 text-muted-foreground">
                      {f.isStart} → {f.isEnd}
                    </td>
                    <td className="p-1.5 text-muted-foreground">
                      {f.oosStart} → {f.oosEnd}
                    </td>
                    <td className="p-1.5 text-white/70">{f.paramLabel}</td>
                    <td className="p-1.5 text-right text-white">{fmt(f.isSharpe)}</td>
                    <td className={`p-1.5 text-right font-bold ${held ? "text-emerald-400" : "text-red-400"}`}>
                      {fmt(f.oosSharpe)}
                    </td>
                  </tr>
                );
              })}
              {!folds.length && (
                <tr>
                  <td colSpan={6} className="p-3 text-center text-muted-foreground">
                    Not enough history to form walk-forward folds.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="shrink-0 text-[8px] text-muted-foreground/70 flex items-center justify-between">
        <span>
          {data.barCount} bars · {data.source === "live" ? "live" : "reference"} data
          {data.asOf ? ` · as of ${data.asOf}` : ""}
        </span>
        <span>Anchored walk-forward · DSR &amp; PBO per Bailey–López de Prado</span>
      </div>
    </div>
  );
}
