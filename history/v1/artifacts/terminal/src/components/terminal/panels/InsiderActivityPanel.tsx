import React, { useMemo, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Users, ArrowUpRight, ArrowDownRight, ExternalLink, ShieldAlert } from "lucide-react";

export interface InsiderTxn {
  symbol: string;
  insider: string | null;
  role: string | null;
  code: string | null;
  type: string | null;
  acquiredDisposed: string | null;
  security: string | null;
  isDerivative: boolean;
  shares: number | null;
  price: number | null;
  value: number | null;
  sharesOwnedAfter: number | null;
  transactionDate: string | null;
  filingDate: string | null;
  form: string | null;
  url: string | null;
  accession: string | null;
}

interface RankedInsider {
  insider: string;
  role: string | null;
  shares: number;
  value: number;
}

interface InsiderSummary {
  buyCount: number;
  sellCount: number;
  optionExerciseCount: number;
  otherCount: number;
  buyShares: number;
  sellShares: number;
  buyValue: number;
  sellValue: number;
  netShares: number;
  netValue: number;
  sentiment: string;
  uniqueInsiders: number;
}

interface InsiderActivityData {
  title: string;
  symbol: string;
  issuerName?: string | null;
  cik?: string | null;
  windowDays: number;
  rows: InsiderTxn[];
  count: number;
  shown: number;
  summary: InsiderSummary;
  topBuyers: RankedInsider[];
  topSellers: RankedInsider[];
  asOf?: string | null;
  source?: string;
  feedSource?: string;
}

function fmtShares(v: number | null): string {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  if (a >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (a >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toLocaleString();
}

function fmtValue(v: number | null): string {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1_000_000_000) return `${sign}$${(a / 1_000_000_000).toFixed(2)}B`;
  if (a >= 1_000_000) return `${sign}$${(a / 1_000_000).toFixed(2)}M`;
  if (a >= 1_000) return `${sign}$${(a / 1_000).toFixed(1)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

function fmtPrice(v: number | null): string {
  if (v === null || v === undefined || v === 0) return "—";
  return `$${v.toFixed(2)}`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" });
}

// Map an EDGAR transaction "type" to a compact label + colour family.
function typeBadge(t: InsiderTxn): { label: string; tone: "buy" | "sell" | "neutral" } {
  const type = (t.type || "").toLowerCase();
  if (type === "buy") return { label: "Buy", tone: "buy" };
  if (type === "sell") return { label: "Sell", tone: "sell" };
  if (type === "option-exercise") return { label: "Option Ex.", tone: "neutral" };
  if (type === "grant") return { label: "Grant", tone: "neutral" };
  if (type === "tax") return { label: "Tax", tone: "neutral" };
  if (type === "gift") return { label: "Gift", tone: "neutral" };
  // Fall back to the raw SEC code so nothing is silently hidden.
  const code = (t.code || "?").toUpperCase();
  return { label: code, tone: "neutral" };
}

const TONE_CLASS: Record<"buy" | "sell" | "neutral", string> = {
  buy: "text-emerald-300 border-emerald-400/30 bg-emerald-400/5",
  sell: "text-rose-300 border-rose-400/30 bg-rose-400/5",
  neutral: "text-muted-foreground border-border bg-white/3",
};

export function InsiderActivityPanel({ data }: { data: InsiderActivityData }) {
  const [filter, setFilter] = useState<"all" | "buy" | "sell">("all");
  const s = data.summary;

  const rows = useMemo(() => {
    if (filter === "buy") return data.rows.filter(r => (r.code || "").toUpperCase() === "P");
    if (filter === "sell") return data.rows.filter(r => (r.code || "").toUpperCase() === "S");
    return data.rows;
  }, [data.rows, filter]);

  const feed = data.feedSource ?? data.source;
  const unavailable = feed === "unavailable";
  const errored = feed === "error";
  const netPositive = s ? s.netValue > 0 || (s.netValue === 0 && s.netShares > 0) : false;
  const netNegative = s ? s.netValue < 0 || (s.netValue === 0 && s.netShares < 0) : false;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Users className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
          <span className="text-xs font-bold uppercase truncate">{data.title}</span>
        </div>
        <span className="text-[9px] text-muted-foreground uppercase tracking-wider shrink-0 ml-2">
          {data.count} txns · {data.windowDays}d
        </span>
      </div>

      {unavailable && (
        <div className="mb-2 shrink-0 flex items-center gap-2 border border-border bg-white/3 px-2.5 py-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.8} />
          <span className="text-[10px] text-muted-foreground leading-tight">
            No SEC filer found for {data.symbol} — insider data is only available for SEC-registered US issuers.
          </span>
        </div>
      )}
      {errored && (
        <div className="mb-2 shrink-0 flex items-center gap-2 border border-amber-400/40 bg-amber-400/5 px-2.5 py-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0" strokeWidth={1.8} />
          <span className="text-[10px] text-amber-300 leading-tight">
            Couldn't reach SEC EDGAR right now — no insider data to show.
          </span>
        </div>
      )}

      {/* Net flow summary */}
      {s && !unavailable && (
        <div className="mb-2 shrink-0 grid grid-cols-3 gap-1.5">
          <div className="border border-border bg-white/3 px-2 py-1.5">
            <div className="text-[8px] uppercase tracking-wider text-muted-foreground">Net Flow</div>
            <div
              className={`text-[13px] font-bold nums-tabular flex items-center gap-1 ${
                netPositive ? "text-emerald-300" : netNegative ? "text-rose-300" : "text-gray-200"
              }`}
            >
              {netPositive && <ArrowUpRight className="w-3 h-3" strokeWidth={2} />}
              {netNegative && <ArrowDownRight className="w-3 h-3" strokeWidth={2} />}
              {fmtValue(s.netValue)}
            </div>
            <div className="text-[8px] text-muted-foreground capitalize">{s.sentiment}</div>
          </div>
          <div className="border border-emerald-400/20 bg-emerald-400/5 px-2 py-1.5">
            <div className="text-[8px] uppercase tracking-wider text-emerald-300/70">Open-Mkt Buys</div>
            <div className="text-[13px] font-bold nums-tabular text-emerald-300">{s.buyCount}</div>
            <div className="text-[8px] text-muted-foreground">{fmtValue(s.buyValue)}</div>
          </div>
          <div className="border border-rose-400/20 bg-rose-400/5 px-2 py-1.5">
            <div className="text-[8px] uppercase tracking-wider text-rose-300/70">Open-Mkt Sells</div>
            <div className="text-[13px] font-bold nums-tabular text-rose-300">{s.sellCount}</div>
            <div className="text-[8px] text-muted-foreground">{fmtValue(s.sellValue)}</div>
          </div>
        </div>
      )}

      {/* Filter tabs */}
      {!unavailable && (
        <div className="flex gap-1 mb-2 shrink-0">
          {(["all", "buy", "sell"] as const).map(t => (
            <button
              key={t}
              onClick={() => setFilter(t)}
              disabled={(t === "buy" && (s?.buyCount ?? 0) === 0) || (t === "sell" && (s?.sellCount ?? 0) === 0)}
              className={`text-[10px] uppercase tracking-widest px-2 py-0.5 border transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
                filter === t ? "border-white text-white bg-white/10" : "border-border text-muted-foreground hover:border-gray-500"
              }`}
            >
              {t === "all" ? "All" : t === "buy" ? `Buys${s?.buyCount ? ` (${s.buyCount})` : ""}` : `Sells${s?.sellCount ? ` (${s.sellCount})` : ""}`}
            </button>
          ))}
          {(s?.optionExerciseCount ?? 0) + (s?.otherCount ?? 0) > 0 && (
            <span className="ml-auto self-center text-[9px] text-muted-foreground">
              +{(s?.optionExerciseCount ?? 0)} opt · {(s?.otherCount ?? 0)} other
            </span>
          )}
        </div>
      )}

      {/* Column header */}
      {!unavailable && (
        <div className="grid grid-cols-[1.8fr_0.9fr_0.7fr_0.8fr_0.9fr_0.5fr] gap-2 px-2 pb-1 shrink-0 text-[9px] text-muted-foreground uppercase tracking-wider border-b border-border">
          <span>Insider</span>
          <span>Type</span>
          <span className="text-right">Shares</span>
          <span className="text-right">Price</span>
          <span className="text-right">Value</span>
          <span className="text-right">Filing</span>
        </div>
      )}

      {/* Rows */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="flex flex-col">
          {rows.length === 0 && !unavailable && (
            <div className="text-xs text-muted-foreground px-2 py-4">
              {errored ? "No data available." : "No insider transactions in this window."}
            </div>
          )}
          {rows.map((r, i) => {
            const badge = typeBadge(r);
            return (
              <div
                key={`${r.accession}-${i}`}
                className="grid grid-cols-[1.8fr_0.9fr_0.7fr_0.8fr_0.9fr_0.5fr] gap-2 items-center px-2 py-1.5 border-b border-border/40 hover:bg-white/3"
              >
                <div className="min-w-0">
                  <div className="text-[11px] font-medium text-gray-100 truncate">{r.insider || "Unknown"}</div>
                  <div className="text-[9px] text-muted-foreground truncate">
                    {r.role || "Insider"}
                    {r.transactionDate ? ` · ${fmtDate(r.transactionDate)}` : ""}
                  </div>
                </div>
                <div>
                  <span className={`inline-block text-[9px] px-1 py-0.5 border uppercase ${TONE_CLASS[badge.tone]}`}>
                    {badge.label}
                  </span>
                  {r.isDerivative && (
                    <span className="ml-1 text-[8px] text-muted-foreground uppercase" title="Derivative security">der</span>
                  )}
                </div>
                <div className="text-right text-[10px] nums-tabular text-gray-200">{fmtShares(r.shares)}</div>
                <div className="text-right text-[10px] nums-tabular text-gray-300">{fmtPrice(r.price)}</div>
                <div
                  className={`text-right text-[10px] nums-tabular ${
                    badge.tone === "buy" ? "text-emerald-300" : badge.tone === "sell" ? "text-rose-300" : "text-gray-300"
                  }`}
                >
                  {fmtValue(r.value)}
                </div>
                <div className="text-right">
                  {r.url ? (
                    <a
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center justify-end text-muted-foreground hover:text-white"
                      title={`View Form ${r.form || "4"} on SEC EDGAR`}
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
          {s?.uniqueInsiders ?? 0} insider{(s?.uniqueInsiders ?? 0) === 1 ? "" : "s"}
          {data.shown < data.count ? ` · showing ${data.shown} of ${data.count}` : ""}
        </span>
        {!unavailable && <span>SEC Form 4/5 · EDGAR</span>}
      </div>
    </div>
  );
}
