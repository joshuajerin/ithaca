// @ts-nocheck
import React from "react";
import type { ComparisonData } from "@workspace/api-client-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";

export function ComparisonPanel({ data }: { data: ComparisonData }) {
  return (
    <div className="flex flex-col h-full">
      <div className="editorial-label text-[9px] text-muted-foreground mb-3 shrink-0">
        {data.title}
      </div>

      <div className="flex-1 min-h-0 border-t border-border">
        <ScrollArea className="h-full">
          <Table>
            <TableHeader className="bg-black sticky top-0 z-10">
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="editorial-label text-[8px] text-muted-foreground w-24 py-2.5">Metric</TableHead>
                {data.companies.map(c => (
                  <TableHead key={c.symbol} className="text-right py-2.5">
                    <span className="font-serif text-base text-white">{c.symbol}</span>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.metricLabels.map((label, idx) => (
                <TableRow key={label} className="border-border hover:bg-white/5 transition-colors">
                  <TableCell className="editorial-label text-[8.5px] text-muted-foreground py-2.5">
                    {label}
                  </TableCell>
                  {data.companies.map(c => {
                    const val = c.values[idx]?.value || '—';
                    // simple heuristic to see if it's positive/negative
                    const isNeg = val.startsWith('-') || val.includes('(-');
                    return (
                      <TableCell key={c.symbol} className={`py-2.5 text-right font-serif text-sm nums-tabular ${isNeg ? 'text-muted-foreground' : 'text-white'}`}>
                        {val}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollArea>
      </div>
    </div>
  );
}
