// @ts-nocheck
import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AlertTriangle, ShieldCheck, ShieldAlert, ShieldX, HelpCircle } from "lucide-react";

type Verdict =
  | "robust"
  | "some_overfitting"
  | "likely_overfit"
  | "severe_overfitting"
  | "inconclusive";

interface Card {
  symbol: string;
  name: string;
  verdict: Verdict;
  verdictLabel: string;
  summary?: string | null;
  isSharpe?: number | null;
  oosSharpe?: number | null;
  degradationPct?: number | null;
  dsr?: number | null;
  haircutPct?: number | null;
  pbo?: number | null;
  nSplits?: number | null;
  paramGridSize?: number | null;
  usable?: boolean;
  bars?: number | null;
  folds?: number | null;
  coverageNote?: string | null;
}

interface Aggregate {
  label: "robust" | "mixed" | "fragile" | "inconclusive";
  summary: string;
  robustnessScore?: number | null;
  consistencyPct?: number | null;
  judged: number;
  inconclusive: number;
  total: number;
  verdictCounts: Record<string, number>;
  meanDegradationPct?: number | null;
  meanOosSharpe?: number | null;
  meanDsr?: number | null;
}

interface Failed {
  symbol: string;
  reason?: string;
}

export interface WalkForwardCompareData {
  title: string;
  strategy: string;
  nSplits: number;
  cards: Card[];
  failed?: Failed[];
  aggregate: Aggregate;
  source?: string;
  asOf?: string | null;
}

const VERDICT_STYLE: Record<Verdict, { color: string; bg: string; border: string }> = {
  robust: { color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/40" },
  some_overfitting: { color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/40" },
  likely_overfit: { color: "text-orange-400", bg: "bg-orange-500/10", border: "border-orange-500/40" },
  severe_overfitting: { color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/40" },
  inconclusive: { color: "text-muted-foreground", bg: "bg-white/5", border: "border-border" },
};

const AGG_STYLE: Record<Aggregate["label"], { color: string; bg: string; border: string; Icon: React.ElementType; label: string }> = {
  robust: { color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/40", Icon: ShieldCheck, label: "ROBUST ACROSS UNIVERSE" },
  mixed: { color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/40", Icon: ShieldAlert, label: "MIXED ACROSS UNIVERSE" },
  fragile: { color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/40", Icon: ShieldX, label: "FRAGILE ACROSS UNIVERSE" },
  inconclusive: { color: "text-muted-foreground", bg: "bg-white/5", border: "border-border", Icon: HelpCircle, label: "INCONCLUSIVE" },
};

// Rank verdicts worst-to-best so the scoreboard surfaces the weakest names first.
const VERDICT_RANK: Record<Verdict, number> = {
  severe_overfitting: 0,
  likely_overfit: 1,
  some_overfitting: 2,
  robust: 3,
  inconclusive: 4,
};

const fmt = (v?: number | null, d = 2) =>
  typeof v === "number" && isFinite(v) ? v.toFixed(d) : "—";
const fmtPct = (v?: number | null, d = 0) =>
  typeof v === "number" && isFinite(v) ? `${v.toFixed(d)}%` : "—";

export function WalkForwardComparePanel({ data }: { data: WalkForwardCompareData }) {
  const cards = [...(data.cards || [])].sort(
    (a, b) => VERDICT_RANK[a.verdict] - VERDICT_RANK[b.verdict]
  );
  const agg = data.aggregate;
  const aStyle = AGG_STYLE[agg?.label] ?? AGG_STYLE.inconclusive;
  const Icon = aStyle.Icon;
  const score = agg?.robustnessScore;

  return (
    <ScrollArea className="h-full pr-1">
      <div className="flex flex-col gap-3 pb-2">
        <div className="editorial-label text-[9px] text-muted-foreground shrink-0">
          {data.title}
        </div>

        {/* Aggregate verdict banner */}
        <div className={`border ${aStyle.border} ${aStyle.bg} p-2.5`}>
          <div className="flex items-center gap-2 mb-1">
            <Icon className={`w-3.5 h-3.5 ${aStyle.color}`} strokeWidth={2} />
            <span className={`text-[10px] font-bold tracking-widest ${aStyle.color}`}>{aStyle.label}</span>
            <span className="text-[9px] text-muted-foreground uppercase tracking-widest">
              {data.strategy.replace(/_/g, " ")} · {agg?.total} names · {data.nSplits} folds
            </span>
          </div>
          <p className="text-[11px] leading-relaxed text-white/80">{agg?.summary}</p>
        </div>

        {/* Aggregate diagnostics */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[
            {
              label: "Robustness",
              value: typeof score === "number" ? `${score.toFixed(0)}/100` : "n/a",
              sub: `${agg?.judged ?? 0} of ${agg?.total ?? 0} judged`,
              tone: typeof score !== "number" ? "text-muted-foreground" : score >= 80 ? "text-emerald-400" : score >= 55 ? "text-yellow-400" : "text-red-400",
            },
            {
              label: "Consistency",
              value: fmtPct(agg?.consistencyPct),
              sub: "judged names robust",
              tone: (agg?.consistencyPct ?? 0) >= 70 ? "text-emerald-400" : (agg?.consistencyPct ?? 0) >= 40 ? "text-yellow-400" : "text-red-400",
            },
            {
              label: "Mean OOS Sharpe",
              value: fmt(agg?.meanOosSharpe),
              sub: "across judged names",
              tone: (agg?.meanOosSharpe ?? 0) > 0 ? "text-emerald-400" : "text-red-400",
            },
            {
              label: "Mean Decay",
              value: fmtPct(agg?.meanDegradationPct),
              sub: "IS → OOS Sharpe",
              tone: (agg?.meanDegradationPct ?? 0) <= 20 ? "text-emerald-400" : (agg?.meanDegradationPct ?? 0) <= 50 ? "text-yellow-400" : "text-red-400",
            },
          ].map((m) => (
            <div key={m.label} className="border border-border p-2">
              <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">{m.label}</div>
              <div className={`text-sm font-bold font-mono ${m.tone}`}>{m.value}</div>
              <div className="text-[9px] text-muted-foreground mt-0.5">{m.sub}</div>
            </div>
          ))}
        </div>

        {/* Per-name scoreboard */}
        <div className="flex flex-col">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
            Per-name out-of-sample verdicts
          </div>
          <div className="overflow-auto border border-border">
            <table className="w-full text-[10px] font-mono">
              <thead className="sticky top-0 bg-black">
                <tr className="text-muted-foreground uppercase tracking-widest text-[8px]">
                  <th className="text-left p-1.5 font-normal">Name</th>
                  <th className="text-left p-1.5 font-normal">Verdict</th>
                  <th className="text-right p-1.5 font-normal">IS → OOS</th>
                  <th className="text-right p-1.5 font-normal">Decay</th>
                  <th className="text-right p-1.5 font-normal">DSR</th>
                  <th className="text-right p-1.5 font-normal">PBO</th>
                </tr>
              </thead>
              <tbody>
                {cards.map((c) => {
                  const vs = VERDICT_STYLE[c.verdict] ?? VERDICT_STYLE.inconclusive;
                  return (
                    <tr key={c.symbol} className="border-t border-border/50">
                      <td className="p-1.5">
                        <div className="flex flex-col">
                          <span className="text-white">{c.symbol}</span>
                          <span className="text-[8px] text-muted-foreground truncate max-w-[120px]">{c.name}</span>
                        </div>
                      </td>
                      <td className="p-1.5">
                        <span className={`inline-block px-1.5 py-0.5 border text-[8px] tracking-widest ${vs.color} ${vs.bg} ${vs.border}`}>
                          {c.verdictLabel}
                        </span>
                      </td>
                      <td className="p-1.5 text-right text-white/80">
                        {fmt(c.isSharpe)} → {c.usable ? fmt(c.oosSharpe) : "—"}
                      </td>
                      <td className={`p-1.5 text-right ${!c.usable ? "text-muted-foreground" : (c.degradationPct ?? 0) <= 20 ? "text-emerald-400" : (c.degradationPct ?? 0) <= 50 ? "text-yellow-400" : "text-red-400"}`}>
                        {c.usable ? fmtPct(c.degradationPct) : "—"}
                      </td>
                      <td className="p-1.5 text-right text-white/70">{fmtPct(c.dsr)}</td>
                      <td className="p-1.5 text-right text-white/70">{typeof c.pbo === "number" ? fmtPct(c.pbo) : "n/a"}</td>
                    </tr>
                  );
                })}
                {!cards.length && (
                  <tr>
                    <td colSpan={6} className="p-3 text-center text-muted-foreground">
                      No names could be validated.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Honest-coverage callout: names excluded from the score */}
        {cards.some((c) => !c.usable) && (
          <div className="flex items-start gap-2 border border-yellow-500/40 bg-yellow-500/10 p-2">
            <AlertTriangle className="w-3 h-3 text-yellow-300 mt-0.5 shrink-0" strokeWidth={1.5} />
            <p className="text-[9px] text-yellow-300/90 leading-relaxed">
              {cards.filter((c) => !c.usable).map((c) => c.symbol).join(", ")} flagged
              inconclusive — too little real out-of-sample history to judge, so excluded from the robustness score rather than hidden.
            </p>
          </div>
        )}

        {/* Names that failed to build entirely */}
        {data.failed && data.failed.length > 0 && (
          <div className="flex items-start gap-2 border-t border-border pt-2.5">
            <AlertTriangle className="w-3 h-3 text-muted-foreground mt-0.5 shrink-0" strokeWidth={1.5} />
            <p className="editorial-label text-[8px] text-muted-foreground leading-relaxed">
              Could not validate {data.failed.map((f) => f.symbol).join(", ")} — skipped.
            </p>
          </div>
        )}

        <div className="text-[8px] text-muted-foreground/70 flex items-center justify-between border-t border-border pt-2">
          <span>
            {data.source === "live" ? "live" : "mock"} data
            {data.asOf ? ` · as of ${data.asOf}` : ""}
          </span>
          <span>Anchored walk-forward · DSR &amp; PBO per Bailey–López de Prado</span>
        </div>
      </div>
    </ScrollArea>
  );
}
