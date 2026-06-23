// @ts-nocheck
import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { TrendingUp, ArrowUpRight, ArrowDownRight, ExternalLink, ShieldAlert, Loader2 } from "lucide-react";

type ChangeKind = "new" | "added" | "trimmed" | "unchanged" | "exited";

interface InstFlowRow {
  institution: string;
  cik?: string | null;
  change: ChangeKind;
  shares: number;
  value: number;
  deltaShares: number;
  deltaValue: number;
  tradeValue: number;
  period?: string | null;
  url?: string | null;
}

interface InstFlowsSummary {
  buyerCount: number;
  sellerCount: number;
  newCount: number;
  exitedCount: number;
  totalBought: number;
  totalSold: number;
  netValue: number;
}

interface InstCoverage {
  managersConfigured: number;
  managersWithData: number;
  managersHolding: number;
  missing: string[];
}

interface InstitutionalFlowsData {
  title: string;
  symbol: string;
  name?: string | null;
  cusip?: string | null;
  reportPeriod?: string | null;
  priorPeriod?: string | null;
  buyers: InstFlowRow[];
  sellers: InstFlowRow[];
  summary: InstFlowsSummary;
  coverage: InstCoverage;
  feedSource?: string;
  source?: string;
  note?: string | null;
}

function fmtShares(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1_000_000) return `${sign}${(a / 1_000_000).toFixed(2)}M`;
  if (a >= 1_000) return `${sign}${(a / 1_000).toFixed(1)}K`;
  return `${sign}${a.toLocaleString()}`;
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

function fmtPeriod(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  const q = Math.floor(d.getMonth() / 3) + 1;
  return `Q${q} ${d.getFullYear()}`;
}

const CHANGE_LABEL: Record<ChangeKind, string> = {
  new: "New",
  added: "Added",
  trimmed: "Trimmed",
  exited: "Exited",
  unchanged: "Held",
};

function FlowList({ rows, side }: { rows: InstFlowRow[]; side: "buy" | "sell" }) {
  const buy = side === "buy";
  return (
    <div className="flex flex-col">
      {rows.length === 0 && (
        <div className="text-[10px] text-muted-foreground px-2 py-3">
          No {buy ? "buyers" : "sellers"} this quarter.
        </div>
      )}
      {rows.map((r, i) => (
        <div
          key={`${r.cik}-${i}`}
          className="grid grid-cols-[1.6fr_0.7fr_0.9fr_0.4fr] gap-2 items-center px-2 py-1.5 border-b border-border/40 hover:bg-white/3"
        >
          <div className="min-w-0">
            <div className="text-[11px] font-medium text-gray-100 truncate">{r.institution}</div>
            <div className="text-[9px] text-muted-foreground truncate">
              {CHANGE_LABEL[r.change]} · {fmtShares(r.deltaShares)} sh
            </div>
          </div>
          <div
            className={`text-[9px] uppercase px-1 py-0.5 border justify-self-start ${
              buy ? "text-emerald-300 border-emerald-400/30 bg-emerald-400/5" : "text-rose-300 border-rose-400/30 bg-rose-400/5"
            }`}
          >
            {r.change === "new" ? "New" : r.change === "exited" ? "Exit" : buy ? "Buy" : "Sell"}
          </div>
          <div className={`text-right text-[10px] nums-tabular font-medium ${buy ? "text-emerald-300" : "text-rose-300"}`} title="Est. traded = Δshares × reported price">
            {fmtValue(r.tradeValue)}
          </div>
          <div className="text-right">
            {r.url ? (
              <a
                href={r.url}
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
      ))}
    </div>
  );
}

export function InstitutionalFlowsPanel({ data }: { data: InstitutionalFlowsData }) {
  const s = data.summary;
  const cov = data.coverage;
  const feed = data.feedSource ?? data.source;
  const pending = feed === "pending";
  const errored = feed === "error";
  const empty = (data.buyers?.length ?? 0) === 0 && (data.sellers?.length ?? 0) === 0;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <TrendingUp className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
          <span className="text-xs font-bold uppercase truncate">{data.title}</span>
        </div>
        <span className="text-[9px] text-muted-foreground uppercase tracking-wider shrink-0 ml-2">
          {data.reportPeriod ? fmtPeriod(data.reportPeriod) : "13F"} QoQ
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
      {!pending && !errored && empty && data.note && (
        <div className="mb-2 shrink-0 flex items-center gap-2 border border-border bg-white/3 px-2.5 py-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.8} />
          <span className="text-[10px] text-muted-foreground leading-tight">{data.note}</span>
        </div>
      )}

      {/* Summary */}
      {s && !pending && !empty && (
        <div className="mb-2 shrink-0 grid grid-cols-3 gap-1.5">
          <div className="border border-emerald-400/20 bg-emerald-400/5 px-2 py-1.5">
            <div className="text-[8px] uppercase tracking-wider text-emerald-300/70">Bought</div>
            <div className="text-[13px] font-bold nums-tabular text-emerald-300">{fmtValue(s.totalBought)}</div>
            <div className="text-[8px] text-muted-foreground">{s.buyerCount} buyers · {s.newCount} new</div>
          </div>
          <div className="border border-rose-400/20 bg-rose-400/5 px-2 py-1.5">
            <div className="text-[8px] uppercase tracking-wider text-rose-300/70">Sold</div>
            <div className="text-[13px] font-bold nums-tabular text-rose-300">{fmtValue(s.totalSold)}</div>
            <div className="text-[8px] text-muted-foreground">{s.sellerCount} sellers · {s.exitedCount} exit</div>
          </div>
          <div className="border border-border bg-white/3 px-2 py-1.5">
            <div className="text-[8px] uppercase tracking-wider text-muted-foreground">Net Flow</div>
            <div
              className={`text-[13px] font-bold nums-tabular flex items-center gap-0.5 ${
                s.netValue > 0 ? "text-emerald-300" : s.netValue < 0 ? "text-rose-300" : "text-gray-200"
              }`}
            >
              {s.netValue > 0 && <ArrowUpRight className="w-3 h-3" strokeWidth={2} />}
              {s.netValue < 0 && <ArrowDownRight className="w-3 h-3" strokeWidth={2} />}
              {fmtValue(s.netValue)}
            </div>
            <div className="text-[8px] text-muted-foreground">{s.netValue >= 0 ? "accumulation" : "distribution"}</div>
          </div>
        </div>
      )}

      {/* Buyers / Sellers */}
      {!pending && !empty && (
        <ScrollArea className="flex-1 min-h-0">
          <div className="flex flex-col gap-2">
            <div>
              <div className="text-[9px] uppercase tracking-wider text-emerald-300/70 px-2 pb-1 border-b border-border">
                Biggest Buyers
              </div>
              <FlowList rows={data.buyers || []} side="buy" />
            </div>
            <div>
              <div className="text-[9px] uppercase tracking-wider text-rose-300/70 px-2 pb-1 border-b border-border">
                Biggest Sellers
              </div>
              <FlowList rows={data.sellers || []} side="sell" />
            </div>
          </div>
        </ScrollArea>
      )}
      {(pending || empty) && <div className="flex-1 min-h-0" />}

      {/* Footer */}
      <div className="shrink-0 pt-1.5 text-[9px] text-muted-foreground flex items-center justify-between border-t border-border/40 mt-1">
        <span>
          {cov ? `${cov.managersWithData}/${cov.managersConfigured} managers` : ""}
          {cov && cov.missing?.length ? ` · ${cov.missing.length} pending` : ""}
        </span>
        <span>SEC 13F · EDGAR</span>
      </div>
    </div>
  );
}
