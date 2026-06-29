// @ts-nocheck
import React, { useMemo, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Landmark, TrendingUp, TrendingDown, Repeat, Flame, Users, Clock, ExternalLink, Info } from "lucide-react";

interface CongressTrade {
  id: string;
  member: string;
  chamber?: string | null;
  party?: string | null;
  partyCode?: string | null;
  ticker?: string | null;
  type: string;
  rawType?: string | null;
  amountRange?: string | null;
  amountLow?: number | null;
  amountHigh?: number | null;
  transactionDate?: string | null;
  disclosureDate?: string | null;
  lagDays?: number | null;
  sourceUrl?: string | null;
  description?: string | null;
}

interface CongressHighlight {
  kind: string;
  label: string;
  detail: string;
  ticker?: string | null;
  members: string[];
}

interface CongressStats {
  total: number;
  buys: number;
  sells: number;
  exchanges: number;
  avgLagDays?: number | null;
  maxLagDays?: number | null;
  uniqueMembers: number;
}

interface CongressTradesData {
  scope: string;
  ticker?: string | null;
  trades: CongressTrade[];
  highlights: CongressHighlight[];
  stats: CongressStats;
  lagNote: string;
  disclaimer: string;
  asOf?: string | null;
  source?: string | null;
}

function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" });
}

function partyColor(code?: string | null, party?: string | null): string {
  const p = (code || party || "").toLowerCase();
  if (p === "d" || p === "democrat") return "text-sky-300 border-sky-400/30 bg-sky-400/5";
  if (p === "r" || p === "republican") return "text-rose-300 border-rose-400/30 bg-rose-400/5";
  return "text-violet-300 border-violet-400/30 bg-violet-400/5";
}

type SideFilter = "all" | "buy" | "sell";

export function CongressTradesPanel({ data }: { data: CongressTradesData }) {
  const [side, setSide] = useState<SideFilter>("all");
  const isLive = data.source === "live";

  const trades = useMemo(
    () => (side === "all" ? data.trades : data.trades.filter(t => t.type === side)),
    [data.trades, side],
  );

  const s = data.stats;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Landmark className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
          <span className="text-xs font-bold uppercase truncate">
            Congress · {data.scope}
          </span>
        </div>
        <span className="text-[9px] text-muted-foreground uppercase tracking-wider shrink-0 ml-2 flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${isLive ? "bg-emerald-400" : "bg-gray-500"}`} />
          {isLive ? "live" : "reference"}
        </span>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-4 gap-1.5 mb-2 shrink-0 text-center">
        <div className="border border-border bg-white/3 px-1 py-1">
          <div className="text-[13px] font-bold nums-tabular">{s.total}</div>
          <div className="text-[8px] text-muted-foreground uppercase tracking-wider">Trades</div>
        </div>
        <div className="border border-emerald-400/20 bg-emerald-400/5 px-1 py-1">
          <div className="text-[13px] font-bold nums-tabular text-emerald-300">{s.buys}</div>
          <div className="text-[8px] text-muted-foreground uppercase tracking-wider">Buys</div>
        </div>
        <div className="border border-rose-400/20 bg-rose-400/5 px-1 py-1">
          <div className="text-[13px] font-bold nums-tabular text-rose-300">{s.sells}</div>
          <div className="text-[8px] text-muted-foreground uppercase tracking-wider">Sells</div>
        </div>
        <div className="border border-border bg-white/3 px-1 py-1">
          <div className="text-[13px] font-bold nums-tabular">{s.uniqueMembers}</div>
          <div className="text-[8px] text-muted-foreground uppercase tracking-wider">Members</div>
        </div>
      </div>

      {/* Notable activity */}
      {data.highlights.length > 0 && (
        <div className="mb-2 shrink-0 flex flex-col gap-1">
          {data.highlights.slice(0, 3).map((h, i) => {
            const cluster = h.kind === "cluster_buy";
            const sale = h.kind === "large_sale";
            return (
              <div
                key={i}
                className={`flex items-center gap-2 border px-2 py-1 ${
                  cluster
                    ? "border-amber-400/40 bg-amber-400/10"
                    : sale
                      ? "border-rose-400/30 bg-rose-400/5"
                      : "border-emerald-400/30 bg-emerald-400/5"
                }`}
              >
                {cluster ? (
                  <Users className="w-3 h-3 text-amber-300 shrink-0" strokeWidth={1.8} />
                ) : (
                  <Flame className={`w-3 h-3 shrink-0 ${sale ? "text-rose-300" : "text-emerald-300"}`} strokeWidth={1.8} />
                )}
                <span className="text-[10px] leading-tight min-w-0 truncate">
                  <span className={`font-bold ${cluster ? "text-amber-200" : sale ? "text-rose-200" : "text-emerald-200"}`}>
                    {h.label}
                  </span>
                  <span className="text-muted-foreground"> — {h.detail}</span>
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Reporting-lag note */}
      <div className="mb-2 shrink-0 flex items-start gap-1.5 text-[9px] text-muted-foreground border border-border/60 bg-white/2 px-2 py-1">
        <Clock className="w-2.5 h-2.5 shrink-0 mt-0.5" strokeWidth={1.8} />
        <span className="leading-tight">{data.lagNote}</span>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 mb-2 shrink-0">
        {(["all", "buy", "sell"] as const).map(t => (
          <button
            key={t}
            onClick={() => setSide(t)}
            className={`text-[10px] uppercase tracking-widest px-2 py-0.5 border transition-colors ${
              side === t ? "border-white text-white bg-white/10" : "border-border text-muted-foreground hover:border-gray-500"
            }`}
          >
            {t === "all" ? "All" : t === "buy" ? "Buys" : "Sells"}
          </button>
        ))}
      </div>

      {/* Column header */}
      <div className="grid grid-cols-[1.5fr_0.6fr_0.55fr_1fr_1.25fr] gap-2 px-2 pb-1 shrink-0 text-[9px] text-muted-foreground uppercase tracking-wider border-b border-border">
        <span>Member</span>
        <span>Ticker</span>
        <span className="text-center">Side</span>
        <span className="text-right">Amount</span>
        <span className="text-right">Traded → Disclosed</span>
      </div>

      {/* Rows */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="flex flex-col">
          {trades.length === 0 && (
            <div className="text-xs text-muted-foreground px-2 py-4">
              No disclosed trades match this filter.
            </div>
          )}
          {trades.map(t => {
            const buy = t.type === "buy";
            const sell = t.type === "sell";
            return (
              <div
                key={t.id}
                className="grid grid-cols-[1.5fr_0.6fr_0.55fr_1fr_1.25fr] gap-2 items-center px-2 py-1.5 border-b border-border/40 hover:bg-white/3"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[11px] font-bold truncate">{t.member}</span>
                    {t.sourceUrl && (
                      <a
                        href={t.sourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="shrink-0 text-muted-foreground hover:text-white"
                        title="Member disclosure page"
                      >
                        <ExternalLink className="w-2.5 h-2.5" strokeWidth={1.8} />
                      </a>
                    )}
                  </div>
                  <div className="flex items-center gap-1 mt-0.5">
                    <span className={`text-[8px] px-1 border uppercase ${partyColor(t.partyCode, t.party)}`}>
                      {t.partyCode || (t.party ? t.party[0] : "?")}
                    </span>
                    <span className="text-[9px] text-muted-foreground">{t.chamber || "—"}</span>
                  </div>
                </div>
                <div className="text-[11px] font-bold uppercase truncate">{t.ticker || "—"}</div>
                <div className="flex justify-center">
                  {buy ? (
                    <span className="flex items-center gap-1 text-[9px] text-emerald-300 border border-emerald-400/30 bg-emerald-400/5 px-1 py-0.5 uppercase">
                      <TrendingUp className="w-2.5 h-2.5" strokeWidth={1.8} /> Buy
                    </span>
                  ) : sell ? (
                    <span className="flex items-center gap-1 text-[9px] text-rose-300 border border-rose-400/30 bg-rose-400/5 px-1 py-0.5 uppercase">
                      <TrendingDown className="w-2.5 h-2.5" strokeWidth={1.8} /> Sell
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-[9px] text-muted-foreground border border-border bg-white/3 px-1 py-0.5 uppercase">
                      <Repeat className="w-2.5 h-2.5" strokeWidth={1.8} /> Exch
                    </span>
                  )}
                </div>
                <div className="text-right text-[10px] nums-tabular text-gray-200 truncate" title={t.amountRange || ""}>
                  {t.amountRange || "—"}
                </div>
                <div className="text-right">
                  <div className="text-[10px] nums-tabular text-gray-300" title="Transaction date">
                    {fmtDate(t.transactionDate)}
                  </div>
                  <div className="text-[9px] nums-tabular text-muted-foreground" title="Disclosure date">
                    <span className="text-gray-500">disc </span>
                    {fmtDate(t.disclosureDate)}
                    {t.lagDays != null && <span className="text-gray-500"> · {t.lagDays}d</span>}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </ScrollArea>

      {/* Source / disclaimer footer */}
      <div className="shrink-0 mt-1.5 flex items-start gap-1.5 text-[9px] text-muted-foreground border-t border-border/40 pt-1.5">
        <Info className="w-2.5 h-2.5 shrink-0 mt-0.5" strokeWidth={1.8} />
        <span className="leading-tight">{data.disclaimer}</span>
      </div>
    </div>
  );
}
