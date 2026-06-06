import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ArrowUpRight, ArrowDownRight, ArrowRight, AlertTriangle } from "lucide-react";

type Stance = "bullish" | "bearish" | "neutral";

interface Figure {
  label: string;
  value: string;
}

interface Card {
  symbol: string;
  name: string;
  stance: Stance;
  conviction?: number | null;
  headline?: string | null;
  call?: string | null;
  figures?: Figure[];
}

interface Failed {
  symbol: string;
  reason?: string;
}

interface AnalystCompareData {
  title: string;
  cards: Card[];
  failed?: Failed[];
}

const STANCE_RANK: Record<Stance, number> = { bullish: 0, neutral: 1, bearish: 2 };

function StanceBadge({ stance }: { stance: Stance }) {
  const styles: Record<Stance, string> = {
    bullish: "border-white/50 text-white bg-white/8",
    bearish: "border-muted-foreground/50 text-muted-foreground bg-muted/10",
    neutral: "border-border text-gray-400 bg-transparent",
  };
  const icons: Record<Stance, React.ReactNode> = {
    bullish: <ArrowUpRight className="w-3 h-3" strokeWidth={2} />,
    bearish: <ArrowDownRight className="w-3 h-3" strokeWidth={2} />,
    neutral: <ArrowRight className="w-3 h-3" strokeWidth={2} />,
  };
  return (
    <span className={`flex items-center gap-1 px-2 py-0.5 border editorial-label text-[9px] shrink-0 uppercase tracking-widest ${styles[stance]}`}>
      {icons[stance]}
      {stance}
    </span>
  );
}

export function AnalystComparePanel({ data }: { data: AnalystCompareData }) {
  const cards = [...(data.cards || [])].sort(
    (a, b) => STANCE_RANK[a.stance] - STANCE_RANK[b.stance]
  );

  return (
    <ScrollArea className="h-full pr-1">
      <div className="flex flex-col gap-3 pb-2">
        <div className="editorial-label text-[9px] text-muted-foreground shrink-0">
          {data.title}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {cards.map((c) => {
            const conviction = Math.max(0, Math.min(1, c.conviction ?? 0.5));
            const convPct = Math.round(conviction * 100);
            return (
              <div
                key={c.symbol}
                className="flex flex-col gap-3 border border-border bg-white/[0.02] p-3"
              >
                {/* Header: ticker + stance */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex flex-col min-w-0">
                    <span className="font-serif text-base text-white leading-none">{c.symbol}</span>
                    <span className="editorial-label text-[8px] text-muted-foreground truncate mt-1">
                      {c.name}
                    </span>
                  </div>
                  <StanceBadge stance={c.stance} />
                </div>

                {/* Conviction */}
                <div className="flex items-center gap-2">
                  <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">Conv</span>
                  <div className="flex-1 h-1 bg-border rounded-full overflow-hidden">
                    <div className="h-full rounded-full bg-white" style={{ width: `${convPct}%` }} />
                  </div>
                  <span className="editorial-label text-[8.5px] text-white nums-tabular w-7 text-right">{convPct}%</span>
                </div>

                {/* Key figures */}
                {c.figures && c.figures.length > 0 && (
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 border-t border-border pt-2.5">
                    {c.figures.map((f, i) => (
                      <div key={i} className="flex flex-col gap-0.5">
                        <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">{f.label}</span>
                        <span className="font-serif text-xs text-white nums-tabular">{f.value}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* The call */}
                {c.call && (
                  <div className="border-t border-border pt-2.5 mt-auto">
                    <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">The Call</span>
                    <p className="font-serif text-[11px] text-gray-200 leading-relaxed mt-1">{c.call}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Names that couldn't be built */}
        {data.failed && data.failed.length > 0 && (
          <div className="flex items-start gap-2 border-t border-border pt-2.5">
            <AlertTriangle className="w-3 h-3 text-muted-foreground mt-0.5 shrink-0" strokeWidth={1.5} />
            <p className="editorial-label text-[8px] text-muted-foreground leading-relaxed">
              No analyst view for {data.failed.map((f) => f.symbol).join(", ")} — skipped.
            </p>
          </div>
        )}
      </div>
    </ScrollArea>
  );
}
