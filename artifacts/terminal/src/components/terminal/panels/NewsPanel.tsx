import React from "react";
import type { NewsData } from "@workspace/api-client-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ExternalLink } from "lucide-react";

export function NewsPanel({ data }: { data: NewsData }) {
  return (
    <div className="flex flex-col h-full">
      <div className="editorial-label text-[9px] text-muted-foreground mb-3 shrink-0">
        Scope · {data.scope}
      </div>
      
      <ScrollArea className="flex-1 pr-3">
        <div className="flex flex-col">
          {data.items.map((item) => (
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
                  {item.tickers.map(t => (
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
          {data.items.length === 0 && (
            <div className="font-serif text-sm text-muted-foreground text-center py-6 italic">No recent news found.</div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
