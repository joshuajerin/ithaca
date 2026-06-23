// @ts-nocheck
import React, { useMemo, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Building2, ArrowUpRight, ArrowDownRight, ExternalLink, ShieldAlert, Loader2 } from "lucide-react";

type ChangeKind = "new" | "added" | "trimmed" | "unchanged" | "exited";

interface InstHolderRow {
  institution: string;
  cik?: string | null;
  shares: number;
  value: number;
  pctOfPortfolio?: number | null;
  period?: string | null;
  priorShares?: number | null;
  priorValue?: number | null;
  deltaShares?: number | null;
  deltaValue?: number | null;
  changePct?: number | null;
  change: ChangeKind;
  url?: string | null;
}

interface InstHoldersSummary {
  totalValue: number;
  totalShares: number;
  holderCount: number;
  newCount: number;
  addedCount: number;
  trimmedCount: number;
  exitedCount: number;
  unchangedCount: number;
  netDeltaShares: number;
  netDeltaValue: number;
}

interface InstCoverage {
  managersConfigured: number;
  managersWithData: number;
  managersHolding: number;
  missing: string[];
}

interface InstitutionalHoldersData {
  title: string;
  symbol: string;
  name?: string | null;
  cusip?: string | null;
  reportPeriod?: string | null;
  holders: InstHolderRow[];
  summary: InstHoldersSummary;
  coverage: InstCoverage;
  feedSource?: string;
  source?: string;
  note?: string | null;
}

function fmtShares(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  if (a >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (a >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toLocaleString();
}

function fmtValue(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1_000_000_000) return `${sign}$${(a / 1_000_000_000).toFixed(2)}B`;
  if (a >= 1_000_000) return `${sign}$${(a / 1_000_000).toFixed(2)}M`;
  if (a >= 1_000) return `${sign}$${(a / 1_000).toFixed(1)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function fmtPeriod(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  const q = Math.floor(d.getMonth() / 3) + 1;
  return `Q${q} ${d.getFullYear()}`;
}

const CHANGE_TONE: Record<ChangeKind, { label: string; cls: string; tone: "buy" | "sell" | "neutral" }> = {
  new: { label: "New", cls: "text-emerald-200 border-emerald-400/40 bg-emerald-400/10", tone: "buy" },
  added: { label: "Added", cls: "text-emerald-300 border-emerald-400/30 bg-emerald-400/5", tone: "buy" },
  trimmed: { label: "Trimmed", cls: "text-rose-300 border-rose-400/30 bg-rose-400/5", tone: "sell" },
  exited: { label: "Exited", cls: "text-rose-200 border-rose-400/40 bg-rose-400/10", tone: "sell" },
  unchanged: { label: "Held", cls: "text-muted-foreground border-border bg-white/3", tone: "neutral" },
};

export function InstitutionalHoldersPanel({ data }: { data: InstitutionalHoldersData }) {
  const [filter, setFilter] = useState<"all" | "buy" | "sell">("all");
  const s = data.summary;
  const cov = data.coverage;
  const feed = data.feedSource ?? data.source;
  const pending = feed === "pending";
  const errored = feed === "error";

  const holders = useMemo(() => {
    const hs = data.holders || [];
    if (filter === "buy") return hs.filter(h => h.change === "new" || h.change === "added");
    if (filter === "sell") return hs.filter(h => h.change === "trimmed");
    return hs;
  }, [data.holders, filter]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Building2 className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
          <span className="text-xs font-bold uppercase truncate">{data.title}</span>
        </div>
        <span className="text-[9px] text-muted-foreground uppercase tracking-wider shrink-0 ml-2">
          {data.reportPeriod ? fmtPeriod(data.reportPeriod) : "13F"}
        </span>
      </div>

      {pending && (
        <div className="mb-2 shrink-0 flex items-center gap-2 border border-amber-400/40 bg-amber-400/5 px-2.5 py-1.5">
          <Loader2 className="w-3.5 h-3.5 text-amber-400 shrink-0 animate-spin" strokeWidth={1.8} />
          <span className="text-[10px] text-amber-300 leading-tight">
            {data.note || "Institutional 13F filings are still being ingested — refresh in a moment."}
          </span>
        </div>
      )}
      {errored && (
        <div className="mb-2 shrink-0 flex items-center gap-2 border border-amber-400/40 bg-amber-400/5 px-2.5 py-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0" strokeWidth={1.8} />
          <span className="text-[10px] text-amber-300 leading-tight">Couldn't load institutional data right now.</span>
        </div>
      )}
      {!pending && !errored && data.note && (data.holders?.length ?? 0) === 0 && (
        <div className="mb-2 shrink-0 flex items-center gap-2 border border-border bg-white/3 px-2.5 py-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.8} />
          <span className="text-[10px] text-muted-foreground leading-tight">{data.note}</span>
        </div>
      )}

      {/* Summary */}
      {s && !pending && (data.holders?.length ?? 0) > 0 && (
        <div className="mb-2 shrink-0 grid grid-cols-4 gap-1.5">
          <div className="border border-border bg-white/3 px-2 py-1.5">
            <div className="text-[8px] uppercase tracking-wider text-muted-foreground">Holders</div>
            <div className="text-[13px] font-bold nums-tabular text-gray-100">{s.holderCount}</div>
            <div className="text-[8px] text-muted-foreground">{fmtValue(s.totalValue)}</div>
          </div>
          <div className="border border-emerald-400/20 bg-emerald-400/5 px-2 py-1.5">
            <div className="text-[8px] uppercase tracking-wider text-emerald-300/70">New + Added</div>
            <div className="text-[13px] font-bold nums-tabular text-emerald-300">{s.newCount + s.addedCount}</div>
            <div className="text-[8px] text-muted-foreground">{s.newCount} new</div>
          </div>
          <div className="border border-rose-400/20 bg-rose-400/5 px-2 py-1.5">
            <div className="text-[8px] uppercase tracking-wider text-rose-300/70">Trimmed + Exit</div>
            <div className="text-[13px] font-bold nums-tabular text-rose-300">{s.trimmedCount + s.exitedCount}</div>
            <div className="text-[8px] text-muted-foreground">{s.exitedCount} exited</div>
          </div>
          <div className="border border-border bg-white/3 px-2 py-1.5">
            <div className="text-[8px] uppercase tracking-wider text-muted-foreground">Net QoQ</div>
            <div
              className={`text-[13px] font-bold nums-tabular flex items-center gap-0.5 ${
                s.netDeltaValue > 0 ? "text-emerald-300" : s.netDeltaValue < 0 ? "text-rose-300" : "text-gray-200"
              }`}
            >
              {s.netDeltaValue > 0 && <ArrowUpRight className="w-3 h-3" strokeWidth={2} />}
              {s.netDeltaValue < 0 && <ArrowDownRight className="w-3 h-3" strokeWidth={2} />}
              {fmtValue(s.netDeltaValue)}
            </div>
            <div className="text-[8px] text-muted-foreground">{fmtShares(s.netDeltaShares)} sh</div>
          </div>
        </div>
      )}

      {/* Filter tabs */}
      {!pending && (data.holders?.length ?? 0) > 0 && (
        <div className="flex gap-1 mb-2 shrink-0">
          {(["all", "buy", "sell"] as const).map(t => (
            <button
              key={t}
              onClick={() => setFilter(t)}
              className={`text-[10px] uppercase tracking-widest px-2 py-0.5 border transition-colors ${
                filter === t ? "border-white text-white bg-white/10" : "border-border text-muted-foreground hover:border-gray-500"
              }`}
            >
              {t === "all" ? "All" : t === "buy" ? "Buyers" : "Sellers"}
            </button>
          ))}
        </div>
      )}

      {/* Column header */}
      {!pending && (data.holders?.length ?? 0) > 0 && (
        <div className="grid grid-cols-[1.8fr_0.8fr_0.9fr_0.8fr_0.9fr_0.5fr] gap-2 px-2 pb-1 shrink-0 text-[9px] text-muted-foreground uppercase tracking-wider border-b border-border">
          <span>Institution</span>
          <span>Change</span>
          <span className="text-right">Shares</span>
          <span className="text-right">% Port.</span>
          <span className="text-right">Value</span>
          <span className="text-right">Filing</span>
        </div>
      )}

      {/* Rows */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="flex flex-col">
          {holders.length === 0 && !pending && (
            <div className="text-xs text-muted-foreground px-2 py-4">
              {data.note || "No institutional holders to show."}
            </div>
          )}
          {holders.map((h, i) => {
            const badge = CHANGE_TONE[h.change] || CHANGE_TONE.unchanged;
            return (
              <div
                key={`${h.cik}-${i}`}
                className="grid grid-cols-[1.8fr_0.8fr_0.9fr_0.8fr_0.9fr_0.5fr] gap-2 items-center px-2 py-1.5 border-b border-border/40 hover:bg-white/3"
              >
                <div className="min-w-0">
                  <div className="text-[11px] font-medium text-gray-100 truncate">{h.institution}</div>
                  <div className="text-[9px] text-muted-foreground truncate">
                    {h.changePct !== null && h.changePct !== undefined
                      ? `${h.changePct >= 0 ? "+" : ""}${h.changePct.toFixed(1)}% sh QoQ`
                      : "no prior quarter"}
                  </div>
                </div>
                <div>
                  <span className={`inline-block text-[9px] px-1 py-0.5 border uppercase ${badge.cls}`}>
                    {badge.label}
                  </span>
                </div>
                <div className="text-right text-[10px] nums-tabular text-gray-200">{fmtShares(h.shares)}</div>
                <div className="text-right text-[10px] nums-tabular text-gray-300">{fmtPct(h.pctOfPortfolio)}</div>
                <div
                  className={`text-right text-[10px] nums-tabular ${
                    badge.tone === "buy" ? "text-emerald-300" : badge.tone === "sell" ? "text-rose-300" : "text-gray-300"
                  }`}
                >
                  {fmtValue(h.value)}
                </div>
                <div className="text-right">
                  {h.url ? (
                    <a
                      href={h.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center justify-end text-muted-foreground hover:text-white"
                      title="View 13F filing on SEC EDGAR"
                    >
                      <ExternalLink className="w-3 h-3" strokeWidth={1.8} />
                    </a>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </ScrollArea>

      {/* Footer */}
      <div className="shrink-0 pt-1.5 text-[9px] text-muted-foreground flex items-center justify-between border-t border-border/40 mt-1">
        <span>
          {cov ? `${cov.managersHolding}/${cov.managersWithData} of ${cov.managersConfigured} managers` : ""}
          {cov && cov.missing?.length ? ` · ${cov.missing.length} pending` : ""}
        </span>
        <span>SEC 13F · EDGAR</span>
      </div>
    </div>
  );
}
