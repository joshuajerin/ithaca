// @ts-nocheck
import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ArrowUpRight, ArrowDownRight, ArrowRight, Zap, Calendar, Trophy } from "lucide-react";

interface Driver {
  title: string;
  tag: "bullish" | "bearish" | "neutral";
  explanation: string;
}

interface Catalyst {
  event: string;
  date: string;
  impact: "High" | "Medium" | "Low";
  description: string;
}

interface PeriodReturns {
  "1D"?: number | null;
  "1M"?: number | null;
  YTD?: number | null;
  "1Y"?: number | null;
}

interface CompanySide {
  symbol: string;
  name: string;
  priceTrendPct: number;
  returns?: PeriodReturns;
  revenueGrowth: number | null;
  opMargin: number | null;
  pe: number | null;
  marketCapB: number;
  drivers: Driver[];
  catalysts: Catalyst[];
}

interface ComparisonRow {
  metric: string;
  unit: string;
  a: number | null;
  b: number | null;
  higherIsBetter: boolean;
  leader: string | null;
}

interface CompareData {
  symbols: [string, string];
  companies: [CompanySide, CompanySide];
  comparison: ComparisonRow[];
  scoreboard: Record<string, number>;
  asOf?: string | null;
  source?: string | null;
}

function TagBadge({ tag }: { tag: "bullish" | "bearish" | "neutral" }) {
  const styles = {
    bullish: "border-white/40 text-white bg-white/8",
    bearish: "border-muted-foreground/40 text-muted-foreground bg-muted/10",
    neutral: "border-border text-gray-500 bg-transparent",
  };
  const icons = {
    bullish: <ArrowUpRight className="w-2.5 h-2.5" strokeWidth={2} />,
    bearish: <ArrowDownRight className="w-2.5 h-2.5" strokeWidth={2} />,
    neutral: <ArrowRight className="w-2.5 h-2.5" strokeWidth={2} />,
  };
  return (
    <span className={`flex items-center gap-1 px-1.5 py-0.5 border editorial-label text-[8px] shrink-0 ${styles[tag]}`}>
      {icons[tag]}
      {tag}
    </span>
  );
}

function ImpactBadge({ impact }: { impact: "High" | "Medium" | "Low" }) {
  const styles = {
    High: "border-white/50 text-white",
    Medium: "border-gray-500 text-gray-400",
    Low: "border-border text-muted-foreground",
  };
  return (
    <span className={`px-1.5 py-0.5 border editorial-label text-[8px] shrink-0 ${styles[impact]}`}>
      {impact}
    </span>
  );
}

function fmtMetric(v: number | null, unit: string): string {
  if (v === null || v === undefined) return "—";
  if (unit === "x") return `${v.toFixed(1)}x`;
  if (unit === "B") {
    if (v >= 1000) return `$${(v / 1000).toFixed(1)}T`;
    return `$${v.toFixed(0)}B`;
  }
  if (unit === "%") return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
  return v.toFixed(1);
}

function ReturnStat({ label, value }: { label: string; value?: number | null }) {
  const has = value !== null && value !== undefined;
  const pos = has && value! >= 0;
  return (
    <div className="flex flex-col items-end gap-0.5 min-w-[2.5rem]">
      <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">{label}</span>
      <span className={`editorial-label text-[9px] nums-tabular ${!has ? "text-gray-600" : pos ? "text-white" : "text-muted-foreground"}`}>
        {!has ? "—" : `${value! > 0 ? "+" : ""}${value!.toFixed(label === "1D" ? 2 : 1)}%`}
      </span>
    </div>
  );
}

function CompanyColumn({ c }: { c: CompanySide }) {
  const r = c.returns ?? { "1D": c.priceTrendPct };
  const trend = c.priceTrendPct >= 0;
  return (
    <div className="flex flex-col gap-4 min-w-0">
      {/* Header */}
      <div className="border-b border-border pb-3">
        <div className="flex items-baseline gap-2 mb-2">
          <span className="font-serif text-xl text-white">{c.symbol}</span>
          <span className="editorial-label text-[8.5px] text-muted-foreground truncate">{c.name}</span>
        </div>
        <div className="flex items-end justify-between gap-3">
          <ReturnStat label="1D" value={r["1D"] ?? c.priceTrendPct} />
          <ReturnStat label="1M" value={r["1M"]} />
          <ReturnStat label="YTD" value={r.YTD} />
          <ReturnStat label="1Y" value={r["1Y"]} />
        </div>
      </div>

      {/* Price Drivers */}
      <section>
        <div className="flex items-center gap-2 mb-2">
          <Zap className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
          <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">Price Drivers</span>
          <span className={`editorial-label text-[8.5px] ml-auto nums-tabular ${trend ? "text-white" : "text-muted-foreground"}`}>
            {trend ? "+" : ""}{c.priceTrendPct.toFixed(2)}% 1D
          </span>
        </div>
        <div className="flex flex-col border-t border-border">
          {c.drivers.map((d, i) => (
            <div key={i} className="flex gap-2.5 py-2.5 border-b border-border last:border-b-0">
              <span className="editorial-label text-[8px] text-muted-foreground mt-0.5 nums-tabular shrink-0 w-4">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-start gap-2 mb-1">
                  <span className="font-serif text-[13px] text-white leading-tight">{d.title}</span>
                  <TagBadge tag={d.tag} />
                </div>
                <p className="editorial-label text-[8.5px] text-muted-foreground leading-relaxed">{d.explanation}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Catalyst Watch */}
      <section>
        <div className="flex items-center gap-2 mb-2">
          <Calendar className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
          <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">Catalyst Watch</span>
        </div>
        <div className="flex flex-col border-t border-border">
          {c.catalysts.length === 0 && (
            <div className="py-2.5 editorial-label text-[8.5px] text-muted-foreground">No upcoming catalysts tracked.</div>
          )}
          {c.catalysts.map((cat, i) => (
            <div key={i} className="flex gap-2.5 py-2.5 border-b border-border last:border-b-0">
              <div className="flex flex-col gap-0.5 shrink-0 w-14">
                <span className="editorial-label text-[7.5px] text-muted-foreground nums-tabular">
                  {new Date(cat.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                </span>
                <ImpactBadge impact={cat.impact} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-serif text-[13px] text-white leading-tight mb-1">{cat.event}</div>
                <p className="editorial-label text-[8.5px] text-muted-foreground leading-relaxed">{cat.description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function CompanyAnalyticsComparePanel({ data }: { data: CompareData }) {
  const [a, b] = data.companies;
  const aSym = data.symbols[0];
  const bSym = data.symbols[1];
  const aScore = data.scoreboard?.[aSym] ?? 0;
  const bScore = data.scoreboard?.[bSym] ?? 0;

  return (
    <ScrollArea className="h-full pr-1">
      <div className="flex flex-col gap-5 pb-2">

        {/* ── Scoreboard ── */}
        <section className="border border-border">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-white/[0.02]">
            <Trophy className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
            <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">Competitive Scoreboard</span>
            <span className="editorial-label text-[8.5px] ml-auto nums-tabular">
              <span className={aScore >= bScore ? "text-white" : "text-muted-foreground"}>{aSym} {aScore}</span>
              <span className="text-gray-600 mx-1.5">·</span>
              <span className={bScore >= aScore ? "text-white" : "text-muted-foreground"}>{bSym} {bScore}</span>
            </span>
          </div>
          <div className="flex flex-col">
            {/* header row */}
            <div className="grid grid-cols-[1.4fr_1fr_1fr] items-center px-3 py-1.5 border-b border-border">
              <span className="editorial-label text-[8px] text-muted-foreground">Metric</span>
              <span className="editorial-label text-[8px] text-muted-foreground text-right">{aSym}</span>
              <span className="editorial-label text-[8px] text-muted-foreground text-right">{bSym}</span>
            </div>
            {data.comparison.map((row, i) => {
              const aLeads = row.leader === aSym;
              const bLeads = row.leader === bSym;
              return (
                <div key={i} className="grid grid-cols-[1.4fr_1fr_1fr] items-center px-3 py-2 border-b border-border last:border-b-0">
                  <span className="font-serif text-xs text-gray-300 leading-tight">{row.metric}</span>
                  <div className="flex items-center justify-end gap-1.5">
                    {aLeads && <Trophy className="w-2.5 h-2.5 text-white" strokeWidth={2} />}
                    <span className={`font-serif text-sm nums-tabular ${aLeads ? "text-white" : "text-muted-foreground"}`}>
                      {fmtMetric(row.a, row.unit)}
                    </span>
                  </div>
                  <div className="flex items-center justify-end gap-1.5">
                    {bLeads && <Trophy className="w-2.5 h-2.5 text-white" strokeWidth={2} />}
                    <span className={`font-serif text-sm nums-tabular ${bLeads ? "text-white" : "text-muted-foreground"}`}>
                      {fmtMetric(row.b, row.unit)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="px-3 py-1.5 border-t border-border">
            <span className="editorial-label text-[7.5px] text-gray-600">
              Trophy marks the leader on each metric (lower is better for P/E).
            </span>
          </div>
        </section>

        {/* ── Two columns ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-6">
          <CompanyColumn c={a} />
          <div className="md:border-l md:border-border md:pl-6">
            <CompanyColumn c={b} />
          </div>
        </div>

      </div>
    </ScrollArea>
  );
}
