// @ts-nocheck
import React from "react";
import type { NewsData } from "@workspace/api-client-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ExternalLink, Search, X } from "lucide-react";

type SentimentFilter = "all" | "positive" | "negative" | "neutral";

export function NewsPanel({ data }: { data: NewsData | null | undefined }) {
  const [keyword, setKeyword] = React.useState("");
  const [source, setSource] = React.useState<string>("all");
  const [sentiment, setSentiment] = React.useState<SentimentFilter>("all");
  const items = React.useMemo(() => (
    Array.isArray(data?.items) ? data.items : []
  ), [data?.items]);

  const sources = React.useMemo(() => {
    const seen = new Set<string>();
    for (const item of items) {
      if (item.source) seen.add(item.source);
    }
    return Array.from(seen).sort((a, b) => a.localeCompare(b));
  }, [items]);

  const filtered = React.useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return items.filter((item) => {
      if (source !== "all" && item.source !== source) return false;
      if (sentiment !== "all" && (item.sentiment || "neutral") !== sentiment) return false;
      if (kw) {
        const tickers = Array.isArray(item.tickers) ? item.tickers : [];
        const hay = `${item.headline} ${item.summary} ${tickers.join(" ")}`.toLowerCase();
        if (!hay.includes(kw)) return false;
      }
      return true;
    });
  }, [items, keyword, source, sentiment]);

  const hasActiveFilters = keyword.trim() !== "" || source !== "all" || sentiment !== "all";

  const clearFilters = () => {
    setKeyword("");
    setSource("all");
    setSentiment("all");
  };

  const sentiments: SentimentFilter[] = ["all", "positive", "negative", "neutral"];
  const sentimentLabels: Record<SentimentFilter, string> = {
    all: "All",
    positive: "Pos",
    negative: "Neg",
    neutral: "Neutral",
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between gap-2 mb-3 shrink-0">
        <div className="editorial-label text-[9px] text-muted-foreground nums-tabular">
          {filtered.length}
          {filtered.length !== items.length ? ` / ${items.length}` : ""}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-3 shrink-0">
        <div className="relative flex-1 min-w-[140px]">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" strokeWidth={1.5} />
          <input
            type="text"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="Filter headlines…"
            className="w-full bg-transparent border border-border pl-7 pr-2 py-1 text-xs font-serif outline-none focus:border-foreground transition-colors"
          />
        </div>

        {sources.length > 1 && (
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="bg-transparent border border-border px-2 py-1 editorial-label text-[9px] text-muted-foreground outline-none focus:border-foreground transition-colors cursor-pointer max-w-[120px]"
          >
            <option value="all">All sources</option>
            {sources.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        )}

        <div className="flex border border-border">
          {sentiments.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSentiment(s)}
              className={`editorial-label text-[8.5px] px-1.5 py-1 transition-colors border-r border-border last:border-r-0 ${
                sentiment === s
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {sentimentLabels[s]}
            </button>
          ))}
        </div>

        {hasActiveFilters && (
          <button
            type="button"
            onClick={clearFilters}
            className="flex items-center gap-1 editorial-label text-[8.5px] text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="w-3 h-3" strokeWidth={1.5} />
            Clear
          </button>
        )}
      </div>

      <ScrollArea className="flex-1 pr-3">
        <div className="flex flex-col">
          {filtered.map((item) => (
            <div key={item.id} className="border-t border-border py-4 first:border-t-0 first:pt-0">
              <div className="flex justify-between items-start gap-3 mb-2">
                <div className="flex items-center gap-2 editorial-label text-[8.5px] text-muted-foreground">
                  <span className="nums-tabular">{new Date(item.publishedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  <span className="w-0.5 h-0.5 bg-muted-foreground rounded-full" />
                  <span>{item.source}</span>
                  {item.sentiment === 'positive' && <span className="text-black bg-white px-1">Pos</span>}
                  {item.sentiment === 'negative' && <span className="border border-muted-foreground px-1">Neg</span>}
                </div>
                <div className="flex gap-1 shrink-0">
                  {(Array.isArray(item.tickers) ? item.tickers : []).map(t => (
                    <span key={t} className="editorial-label text-[8px] border border-border px-1 py-0.5">{t}</span>
                  ))}
                </div>
              </div>
              
              <h4 className="font-serif text-lg leading-tight mb-1.5 cursor-pointer group">
                {item.url ? (
                  <a href={item.url} target="_blank" rel="noreferrer" className="flex items-start gap-1 hover:underline decoration-1 underline-offset-2">
                    {item.headline}
                    <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-1.5" strokeWidth={1.5} />
                  </a>
                ) : item.headline}
              </h4>
              
              <p className="font-serif text-sm text-muted-foreground leading-snug line-clamp-2">
                {item.summary}
              </p>
            </div>
          ))}
          {items.length === 0 && (
            <div className="font-serif text-sm text-muted-foreground text-center py-6 italic">No recent IBKR headlines available.</div>
          )}
          {items.length > 0 && filtered.length === 0 && (
            <div className="font-serif text-sm text-muted-foreground text-center py-6 italic">No headlines match your filters.</div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
