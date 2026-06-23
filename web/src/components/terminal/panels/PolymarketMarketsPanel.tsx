// @ts-nocheck
import React from "react";

interface PolyOutcome {
  label: string;
  probability: number | null;
  marketId: string | null;
  slug: string | null;
}

interface PolyEvent {
  id: string;
  slug: string | null;
  title: string;
  category: string;
  icon: string | null;
  volume: number | null;
  volume24hr: number | null;
  liquidity: number | null;
  marketCount: number;
  topOutcomes: PolyOutcome[];
}

interface PolyCategory {
  slug: string | null;
  label: string;
}

interface PolymarketMarketsPanelProps {
  data: {
    title: string;
    category: string | null;
    categoryLabel?: string;
    categories?: PolyCategory[];
    events: PolyEvent[];
  };
  onRefine?: (instruction: string) => void;
}

const fmtUsd = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
};

const pct = (p: number | null): string =>
  p === null || p === undefined ? "—" : `${(p * 100).toFixed(0)}%`;

const probColor = (p: number | null): string => {
  if (p === null || p === undefined) return "#666";
  if (p >= 0.66) return "#34d399";
  if (p >= 0.33) return "#fbbf24";
  return "#f87171";
};

export function PolymarketMarketsPanel({ data, onRefine }: PolymarketMarketsPanelProps) {
  const { events = [], categories = [], category, categoryLabel } = data;

  return (
    <div className="flex flex-col h-full w-full">
      {/* Category chips */}
      {categories.length > 0 && (
        <div className="shrink-0 flex flex-wrap gap-1.5 mb-3">
          {categories.map((c) => {
            const active = (c.slug ?? null) === (category ?? null);
            return (
              <button
                key={c.label}
                disabled={!onRefine}
                onClick={() =>
                  onRefine?.(
                    c.slug
                      ? `Show ${c.label} prediction markets`
                      : "Show trending prediction markets"
                  )
                }
                className={`text-[10px] uppercase tracking-wider px-2 py-1 border transition-colors ${
                  active
                    ? "border-white/70 text-white bg-white/[0.06]"
                    : "border-border text-muted-foreground hover:text-white hover:border-white/30"
                } ${onRefine ? "cursor-pointer" : "cursor-default"}`}
              >
                {c.label}
              </button>
            );
          })}
        </div>
      )}

      {/* Event list */}
      <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-2">
        {events.map((ev) => {
          const binary = ev.marketCount <= 1 && ev.topOutcomes.length <= 1;
          const lead = ev.topOutcomes[0];
          return (
            <button
              key={ev.id}
              disabled={!onRefine}
              onClick={() =>
                onRefine?.(`Show the Polymarket market detail for ${ev.title}`)
              }
              className={`w-full text-left border border-border bg-white/[0.015] px-3 py-2.5 transition-colors ${
                onRefine ? "hover:border-white/30 cursor-pointer" : "cursor-default"
              }`}
            >
              <div className="flex items-start gap-2.5">
                {ev.icon && (
                  <img
                    src={ev.icon}
                    alt=""
                    className="w-8 h-8 rounded object-cover shrink-0 mt-0.5"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = "none";
                    }}
                  />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-[12px] text-white font-medium leading-snug line-clamp-2">
                      {ev.title}
                    </span>
                    {binary && lead && (
                      <span
                        className="text-lg font-bold font-mono shrink-0"
                        style={{ color: probColor(lead.probability) }}
                      >
                        {pct(lead.probability)}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2 mt-1 text-[9px] uppercase tracking-wider text-muted-foreground">
                    <span className="text-cyan-300/80">{ev.category}</span>
                    <span>·</span>
                    <span>{fmtUsd(ev.volume24hr)} 24h</span>
                    <span>·</span>
                    <span>{fmtUsd(ev.liquidity)} liq</span>
                    {!binary && (
                      <>
                        <span>·</span>
                        <span>{ev.marketCount} outcomes</span>
                      </>
                    )}
                  </div>

                  {/* Multi-outcome leaders */}
                  {!binary && ev.topOutcomes.length > 0 && (
                    <div className="mt-1.5 space-y-1">
                      {ev.topOutcomes.slice(0, 4).map((o) => (
                        <div key={o.marketId ?? o.label} className="flex items-center gap-2">
                          <span className="text-[10px] text-muted-foreground w-28 truncate shrink-0">
                            {o.label}
                          </span>
                          <div className="flex-1 h-1.5 bg-white/[0.06] rounded-sm overflow-hidden">
                            <div
                              className="h-full rounded-sm"
                              style={{
                                width: `${Math.max(2, (o.probability ?? 0) * 100)}%`,
                                backgroundColor: probColor(o.probability),
                              }}
                            />
                          </div>
                          <span
                            className="text-[10px] font-mono w-9 text-right shrink-0"
                            style={{ color: probColor(o.probability) }}
                          >
                            {pct(o.probability)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </button>
          );
        })}
        {events.length === 0 && (
          <div className="text-[11px] text-muted-foreground py-8 text-center">
            No active markets returned.
          </div>
        )}
      </div>

      <div className="shrink-0 text-[8px] text-muted-foreground mt-2 uppercase tracking-widest">
        {categoryLabel ?? "Trending"} · {events.length} events · click an event for detail
      </div>
    </div>
  );
}
