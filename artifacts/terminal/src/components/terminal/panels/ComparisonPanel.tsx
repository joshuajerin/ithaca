import React from "react";
import type { ComparisonData } from "@workspace/api-client-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";

export function ComparisonPanel({ data }: { data: ComparisonData }) {
  return (
    <div className="flex flex-col h-full">
      <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-2 shrink-0">
        {data.title}
      </div>

      <div className="flex-1 min-h-0 border border-border">
        <ScrollArea className="h-full">
          <Table className="text-xs">
            <TableHeader className="bg-black sticky top-0 z-10">
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-muted-foreground w-24 py-2">METRIC</TableHead>
                {data.companies.map(c => (
                  <TableHead key={c.symbol} className="text-right py-2 text-white font-bold">
                    {c.symbol}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.metricLabels.map((label, idx) => (
                <TableRow key={label} className="border-border/50 hover:bg-white/5 transition-colors">
                  <TableCell className="font-bold text-muted-foreground py-2 uppercase text-[10px] tracking-wider">
                    {label}
                  </TableCell>
                  {data.companies.map(c => {
                    const val = c.values[idx]?.value || '-';
                    // simple heuristic to see if it's positive/negative
                    const isNeg = val.startsWith('-') || val.includes('(-');
                    return (
                      <TableCell key={c.symbol} className={`py-2 text-right font-mono ${isNeg ? 'text-muted-foreground' : 'text-white'}`}>
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
