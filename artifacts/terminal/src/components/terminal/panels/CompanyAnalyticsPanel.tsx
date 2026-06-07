import React, { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ArrowUpRight, ArrowDownRight, ArrowRight, Zap, BarChart2, GitBranch, Calendar, ChevronDown } from "lucide-react";

interface Driver {
  title: string;
  tag: "bullish" | "bearish" | "neutral";
  explanation: string;
  detail?: string;
}

interface Peer {
  symbol: string;
  name: string;
  isSubject: boolean;
  revenueGrowth: number | null;
  opMargin: number | null;
  pe: number | null;
  marketCapB: number;
}

interface Correlation {
  metric: string;
  correlation: number;
  direction: "positive" | "negative";
}

interface Catalyst {
  event: string;
  date: string;
  impact: "High" | "Medium" | "Low";
  description: string;
  sentiment?: "bullish" | "bearish" | "neutral";
  detail?: string;
}

interface PeriodReturns {
  "1D"?: number | null;
  "1M"?: number | null;
  YTD?: number | null;
  "1Y"?: number | null;
}

interface CompanyAnalyticsData {
  symbol: string;
  name: string;
  priceTrendPct: number;
  returns?: PeriodReturns;
  drivers: Driver[];
  peers: Peer[];
  correlations: Correlation[];
  catalysts: Catalyst[];
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

function fmt(n: number | null, suffix = "", decimals = 1): string {
  if (n === null || n === undefined) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(decimals)}${suffix}`;
}

function fmtPe(n: number | null): string {
  if (n === null || n === undefined) return "N/A";
  return n.toFixed(1) + "x";
}

function fmtCap(n: number): string {
  if (n >= 1000) return `$${(n / 1000).toFixed(1)}T`;
  return `$${n.toFixed(0)}B`;
}

function corrBar(corr: number): number {
  return Math.round(Math.abs(corr) * 100);
}

function ReturnStat({ label, value }: { label: string; value?: number | null }) {
  const has = value !== null && value !== undefined;
  const pos = has && value! >= 0;
  return (
    <div className="flex flex-col items-end gap-0.5 min-w-[3rem]">
      <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">{label}</span>
      <span className={`editorial-label text-[9px] nums-tabular ${!has ? "text-gray-600" : pos ? "text-white" : "text-muted-foreground"}`}>
        {!has ? "—" : `${value! > 0 ? "+" : ""}${value!.toFixed(label === "1D" ? 2 : 1)}%`}
      </span>
    </div>
  );
}

export function CompanyAnalyticsPanel({ data }: { data: CompanyAnalyticsData }) {
  const trend = data.priceTrendPct >= 0;
  const r = data.returns ?? { "1D": data.priceTrendPct };
  const [expandedDriver, setExpandedDriver] = useState<number | null>(null);
  const [expandedCatalyst, setExpandedCatalyst] = useState<number | null>(null);

  return (
    <ScrollArea className="h-full pr-1">
      <div className="flex flex-col gap-5 pb-2">

        {/* ── Performance by timeframe ── */}
        <section className="flex items-end justify-end gap-5 border-b border-border pb-3">
          <ReturnStat label="1D" value={r["1D"] ?? data.priceTrendPct} />
          <ReturnStat label="1M" value={r["1M"]} />
          <ReturnStat label="YTD" value={r.YTD} />
          <ReturnStat label="1Y" value={r["1Y"]} />
        </section>

        {/* ── 1. Price Drivers ── */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
            <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">Price Drivers</span>
            <span className={`editorial-label text-[8.5px] ml-auto nums-tabular ${trend ? "text-white" : "text-muted-foreground"}`}>
              {trend ? "+" : ""}{data.priceTrendPct.toFixed(2)}% 1D
            </span>
          </div>
          <div className="flex flex-col border-t border-border">
            {data.drivers.map((d, i) => {
              const open = expandedDriver === i;
              const hasDetail = !!(d.detail && d.detail.trim());
              return (
                <div key={i} className="border-b border-border last:border-b-0">
                  <button
                    type="button"
                    disabled={!hasDetail}
                    onClick={() => setExpandedDriver(open ? null : i)}
                    aria-expanded={open}
                    className={`w-full flex gap-3 py-2.5 text-left ${hasDetail ? "cursor-pointer hover:bg-white/[0.03]" : "cursor-default"} transition-colors`}
                  >
                    <span className="editorial-label text-[8px] text-muted-foreground mt-0.5 nums-tabular shrink-0 w-4">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start gap-2 mb-1">
                        <span className="font-serif text-sm text-white leading-tight">{d.title}</span>
                        <TagBadge tag={d.tag} />
                        {hasDetail && (
                          <ChevronDown
                            className={`w-3 h-3 text-muted-foreground ml-auto mt-0.5 shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
                            strokeWidth={1.5}
                          />
                        )}
                      </div>
                      <p className="editorial-label text-[8.5px] text-muted-foreground leading-relaxed">{d.explanation}</p>
                    </div>
                  </button>
                  <AnimatePresence initial={false}>
                    {open && hasDetail && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                        className="overflow-hidden"
                      >
                        <p className="editorial-label text-[8.5px] text-gray-400 leading-relaxed pl-7 pr-1 pb-3 border-l border-white/15 ml-1.5">
                          {d.detail}
                        </p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>
        </section>

        {/* ── 2. Competitive Landscape ── */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <GitBranch className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
            <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">Competitive Landscape</span>
          </div>
          <div className="border-t border-border">
            <Table>
              <TableHeader className="bg-black sticky top-0 z-10">
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="editorial-label text-[8px] text-muted-foreground py-2 w-16">Ticker</TableHead>
                  <TableHead className="editorial-label text-[8px] text-muted-foreground py-2 text-right">Rev Growth</TableHead>
                  <TableHead className="editorial-label text-[8px] text-muted-foreground py-2 text-right">Op Margin</TableHead>
                  <TableHead className="editorial-label text-[8px] text-muted-foreground py-2 text-right">P/E</TableHead>
                  <TableHead className="editorial-label text-[8px] text-muted-foreground py-2 text-right">Mkt Cap</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.peers.map((p) => (
                  <TableRow
                    key={p.symbol}
                    className={`border-border hover:bg-white/5 transition-colors ${p.isSubject ? "bg-white/5" : ""}`}
                  >
                    <TableCell className="py-2 font-serif text-sm">
                      <span className={p.isSubject ? "text-white" : "text-gray-400"}>{p.symbol}</span>
                      {p.isSubject && (
                        <span className="ml-1.5 editorial-label text-[7px] text-muted-foreground">subject</span>
                      )}
                    </TableCell>
                    <TableCell className={`py-2 text-right font-serif text-sm nums-tabular ${
                      p.revenueGrowth === null ? "text-muted-foreground"
                        : p.revenueGrowth > 0 ? "text-white" : "text-muted-foreground"
                    }`}>
                      {p.revenueGrowth !== null ? fmt(p.revenueGrowth, "%") : "—"}
                    </TableCell>
                    <TableCell className={`py-2 text-right font-serif text-sm nums-tabular ${
                      p.opMargin === null ? "text-muted-foreground"
                        : p.opMargin > 0 ? "text-white" : "text-muted-foreground"
                    }`}>
                      {p.opMargin !== null ? fmt(p.opMargin, "%") : "—"}
                    </TableCell>
                    <TableCell className="py-2 text-right font-serif text-sm nums-tabular text-white">
                      {fmtPe(p.pe)}
                    </TableCell>
                    <TableCell className="py-2 text-right font-serif text-sm nums-tabular text-white">
                      {fmtCap(p.marketCapB)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </section>

        {/* ── 3. Metric Correlations ── */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <BarChart2 className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
            <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">Metric Correlations</span>
            <span className="editorial-label text-[7.5px] text-muted-foreground ml-1">(vs 3M price returns)</span>
          </div>
          <div className="flex flex-col border-t border-border">
            {data.correlations.map((c, i) => (
              <div key={i} className="flex items-center gap-3 py-2.5 border-b border-border last:border-b-0">
                <span className="editorial-label text-[8px] text-muted-foreground nums-tabular shrink-0 w-4">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="font-serif text-xs text-gray-300 flex-1 min-w-0 leading-tight">{c.metric}</span>
                <div className="flex items-center gap-2 shrink-0">
                  <div className="w-16 h-1 bg-border rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${c.direction === "positive" ? "bg-white" : "bg-muted-foreground"}`}
                      style={{ width: `${corrBar(c.correlation)}%` }}
                    />
                  </div>
                  <span className={`editorial-label text-[8.5px] nums-tabular w-8 text-right ${
                    c.direction === "positive" ? "text-white" : "text-muted-foreground"
                  }`}>
                    {c.direction === "negative" ? "–" : "+"}{Math.abs(c.correlation).toFixed(2)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ── 4. Catalyst Watch ── */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Calendar className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
            <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">Catalyst Watch</span>
          </div>
          <div className="flex flex-col border-t border-border">
            {data.catalysts.map((cat, i) => {
              const open = expandedCatalyst === i;
              const hasDetail = !!(cat.detail && cat.detail.trim());
              return (
                <div key={i} className="border-b border-border last:border-b-0">
                  <button
                    type="button"
                    disabled={!hasDetail}
                    onClick={() => setExpandedCatalyst(open ? null : i)}
                    aria-expanded={open}
                    className={`w-full flex gap-3 py-2.5 text-left ${hasDetail ? "cursor-pointer hover:bg-white/[0.03]" : "cursor-default"} transition-colors`}
                  >
                    <div className="flex flex-col gap-0.5 shrink-0 w-16">
                      <span className="editorial-label text-[7.5px] text-muted-foreground nums-tabular">
                        {new Date(cat.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                      </span>
                      <ImpactBadge impact={cat.impact} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start gap-2 mb-1">
                        <span className="font-serif text-sm text-white leading-tight">{cat.event}</span>
                        {hasDetail && (
                          <ChevronDown
                            className={`w-3 h-3 text-muted-foreground ml-auto mt-0.5 shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
                            strokeWidth={1.5}
                          />
                        )}
                      </div>
                      <p className="editorial-label text-[8.5px] text-muted-foreground leading-relaxed">{cat.description}</p>
                    </div>
                  </button>
                  <AnimatePresence initial={false}>
                    {open && hasDetail && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                        className="overflow-hidden"
                      >
                        <div className="pl-[4.75rem] pr-1 pb-3">
                          <div className="border-l border-white/15 pl-3 flex flex-col gap-1.5">
                            {cat.sentiment && (
                              <div className="flex items-center gap-1.5">
                                <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">Sentiment Read</span>
                                <TagBadge tag={cat.sentiment} />
                              </div>
                            )}
                            <p className="editorial-label text-[8.5px] text-gray-400 leading-relaxed">{cat.detail}</p>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>
        </section>

      </div>
    </ScrollArea>
  );
}
