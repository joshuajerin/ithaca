import React from "react";
import type { NewsData } from "@workspace/api-client-react/src/generated/api.schemas";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ExternalLink } from "lucide-react";

export function NewsPanel({ data }: { data: NewsData }) {
  return (
    <div className="flex flex-col h-full">
      <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-3 shrink-0">
        SCOPE: {data.scope}
      </div>
      
      <ScrollArea className="flex-1 pr-3">
        <div className="space-y-4">
          {data.items.map((item) => (
            <div key={item.id} className="border-b border-border/50 pb-4 last:border-0 last:pb-0">
              <div className="flex justify-between items-start gap-3 mb-1">
                <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  <span>{new Date(item.publishedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  <span className="w-1 h-1 bg-border rounded-full" />
                  <span>{item.source}</span>
                  {item.sentiment === 'positive' && <span className="text-white bg-white/20 px-1 rounded-sm">POS</span>}
                  {item.sentiment === 'negative' && <span className="text-destructive bg-destructive/20 px-1 rounded-sm">NEG</span>}
                </div>
                <div className="flex gap-1">
                  {item.tickers.map(t => (
                    <span key={t} className="text-[9px] border border-border px-1 py-0.5 uppercase tracking-widest">{t}</span>
                  ))}
                </div>
              </div>
              
              <h4 className="text-sm font-bold mb-1 leading-tight hover:underline cursor-pointer flex items-center gap-1 group">
                {item.url ? (
                  <a href={item.url} target="_blank" rel="noreferrer" className="flex items-start gap-1">
                    {item.headline}
                    <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-0.5" />
                  </a>
                ) : item.headline}
              </h4>
              
              <p className="text-xs text-muted-foreground line-clamp-2">
                {item.summary}
              </p>
            </div>
          ))}
          {data.items.length === 0 && (
            <div className="text-xs text-muted-foreground text-center py-4">No recent news found.</div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
