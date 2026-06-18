import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ArrowUpRight, ArrowDownRight, ArrowRight, AlertTriangle } from "lucide-react";

interface Distribution {
  strongBuy: number;
  buy: number;
  hold: number;
  sell: number;
  strongSell: number;
}

interface Consensus {
  key?: string | null;
  label?: string | null;
  mean?: number | null;
  numAnalysts?: number | null;
  distribution?: Distribution | null;
}

interface PriceTarget {
  current?: number | null;
  mean?: number | null;
  high?: number | null;
  low?: number | null;
  median?: number | null;
  impliedUpsidePct?: number | null;
}

interface RatingChange {
  date?: string | null;
  firm?: string | null;
  action?: string | null;
  fromGrade?: string | null;
  toGrade?: string | null;
}

interface AnalystRatingsData {
  symbol: string;
  name: string;
  covered: boolean;
  consensus: Consensus;
  priceTarget: PriceTarget;
  changes?: RatingChange[];
  note?: string | null;
}

const DIST_ROWS: { key: keyof Distribution; label: string }[] = [
  { key: "strongBuy", label: "Strong Buy" },
  { key: "buy", label: "Buy" },
  { key: "hold", label: "Hold" },
  { key: "sell", label: "Sell" },
  { key: "strongSell", label: "Strong Sell" },
];

const BULLISH = new Set(["strong buy", "buy", "moderate buy", "outperform", "overweight"]);
const BEARISH = new Set(["strong sell", "sell", "moderate sell", "underperform", "underweight"]);

function fmtUsd(n?: number | null): string {
  if (n === null || n === undefined) return "n/a";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function consensusTone(label?: string | null): string {
  const l = (label || "").toLowerCase();
  if (BULLISH.has(l)) return "text-white";
  if (BEARISH.has(l)) return "text-muted-foreground";
  return "text-gray-300";
}

function ActionIcon({ action }: { action?: string | null }) {
  const a = (action || "").toLowerCase();
  if (a === "upgrade") return <ArrowUpRight className="w-3 h-3 text-white" strokeWidth={2} />;
  if (a === "downgrade") return <ArrowDownRight className="w-3 h-3 text-muted-foreground" strokeWidth={2} />;
  return <ArrowRight className="w-3 h-3 text-gray-500" strokeWidth={2} />;
}

export function AnalystRatingsPanel({ data }: { data: AnalystRatingsData }) {
  const { consensus, priceTarget } = data;

  if (!data.covered) {
    return (
      <ScrollArea className="h-full pr-1">
        <div className="flex flex-col gap-3 pb-2">
          <div className="editorial-label text-[9px] text-muted-foreground shrink-0">
            {data.symbol} · Analyst Ratings
          </div>
          <div className="flex items-start gap-2 border border-border bg-white/[0.02] p-3">
            <AlertTriangle className="w-3.5 h-3.5 text-muted-foreground mt-0.5 shrink-0" strokeWidth={1.5} />
            <p className="font-serif text-[12px] text-gray-200 leading-relaxed">
              {data.note || `No analyst coverage found for ${data.symbol}.`}
            </p>
          </div>
        </div>
      </ScrollArea>
    );
  }

  const dist = consensus.distribution;
  const total = dist
    ? dist.strongBuy + dist.buy + dist.hold + dist.sell + dist.strongSell
    : 0;
  const implied = priceTarget.impliedUpsidePct;
  const changes = (data.changes || []).filter((c) => c.firm || c.toGrade);

  return (
    <ScrollArea className="h-full pr-1">
      <div className="flex flex-col gap-3 pb-2">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-col min-w-0">
            <span className="font-serif text-base text-white leading-none">{data.symbol}</span>
            <span className="editorial-label text-[8px] text-muted-foreground truncate mt-1">
              {data.name}
            </span>
          </div>
          <div className="flex flex-col items-end shrink-0">
            <span className={`font-serif text-lg leading-none ${consensusTone(consensus.label)}`}>
              {consensus.label || "n/a"}
            </span>
            <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase mt-1">
              {consensus.numAnalysts ? `${consensus.numAnalysts} analysts` : "consensus"}
              {consensus.mean != null ? ` · ${consensus.mean.toFixed(2)}/5` : ""}
            </span>
          </div>
        </div>

        {/* Price target band */}
        <div className="grid grid-cols-4 gap-x-3 gap-y-1.5 border-t border-border pt-2.5">
          <div className="flex flex-col gap-0.5">
            <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">Current</span>
            <span className="font-serif text-xs text-white nums-tabular">{fmtUsd(priceTarget.current)}</span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">Target</span>
            <span className="font-serif text-xs text-white nums-tabular">{fmtUsd(priceTarget.mean)}</span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">Range</span>
            <span className="font-serif text-xs text-gray-300 nums-tabular">
              {priceTarget.low != null && priceTarget.high != null
                ? `${fmtUsd(priceTarget.low)}–${fmtUsd(priceTarget.high)}`
                : "n/a"}
            </span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">Implied</span>
            <span
              className={`font-serif text-xs nums-tabular ${
                implied == null ? "text-gray-300" : implied >= 0 ? "text-white" : "text-muted-foreground"
              }`}
            >
              {implied == null ? "n/a" : `${implied >= 0 ? "+" : ""}${implied.toFixed(1)}%`}
            </span>
          </div>
        </div>

        {/* Rating distribution */}
        {dist && total > 0 && (
          <div className="flex flex-col gap-1.5 border-t border-border pt-2.5">
            <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">
              Rating Distribution
            </span>
            {DIST_ROWS.map((r) => {
              const v = dist[r.key];
              const pct = total > 0 ? Math.round((v / total) * 100) : 0;
              return (
                <div key={r.key} className="flex items-center gap-2">
                  <span className="editorial-label text-[8px] text-muted-foreground w-16 shrink-0 uppercase tracking-wide">
                    {r.label}
                  </span>
                  <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
                    <div className="h-full rounded-full bg-white" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="editorial-label text-[8.5px] text-white nums-tabular w-6 text-right">{v}</span>
                </div>
              );
            })}
          </div>
        )}

        {/* Recent rating changes */}
        {changes.length > 0 && (
          <div className="flex flex-col gap-1.5 border-t border-border pt-2.5">
            <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">
              Recent Upgrades / Downgrades
            </span>
            {changes.map((c, i) => (
              <div key={i} className="flex items-center gap-2">
                <ActionIcon action={c.action} />
                <span className="font-serif text-[11px] text-white truncate flex-1 min-w-0">{c.firm || "—"}</span>
                <span className="editorial-label text-[8px] text-gray-300 truncate max-w-[45%] text-right">
                  {c.fromGrade && c.toGrade && c.fromGrade !== c.toGrade
                    ? `${c.fromGrade} → ${c.toGrade}`
                    : c.toGrade || c.action || ""}
                </span>
                {c.date && (
                  <span className="editorial-label text-[7px] text-muted-foreground nums-tabular w-16 text-right shrink-0">
                    {c.date}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </ScrollArea>
  );
}
