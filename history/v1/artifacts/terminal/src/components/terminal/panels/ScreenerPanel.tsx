import React from "react";
import type { ScreenerData } from "@workspace/api-client-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CompanyLogo } from "../CompanyLogo";

function formatNumber(num: number) {
  if (num >= 1e12) return (num / 1e12).toFixed(2) + 'T';
  if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
  if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
  return num.toLocaleString();
}

export function ScreenerPanel({ data }: { data: ScreenerData }) {
  return (
    <div className="flex flex-col h-full">
      <div className="editorial-label text-[9px] text-muted-foreground mb-3 shrink-0">
        {data.title} · <span className="nums-tabular">{data.rows.length}</span> Results
      </div>

      <div className="flex-1 min-h-0 border-t border-border">
        <ScrollArea className="h-full">
          <Table>
            <TableHeader className="bg-black sticky top-0 z-10">
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="editorial-label text-[8px] text-muted-foreground w-40 py-2.5 h-auto">Company</TableHead>
                <TableHead className="editorial-label text-[8px] text-muted-foreground py-2.5 h-auto text-right">Price</TableHead>
                <TableHead className="editorial-label text-[8px] text-muted-foreground py-2.5 h-auto text-right">1D %</TableHead>
                <TableHead className="editorial-label text-[8px] text-muted-foreground py-2.5 h-auto text-right">1Y %</TableHead>
                <TableHead className="editorial-label text-[8px] text-muted-foreground py-2.5 h-auto text-right">MCap</TableHead>
                <TableHead className="editorial-label text-[8px] text-muted-foreground py-2.5 h-auto text-right">Vol</TableHead>
                <TableHead className="editorial-label text-[8px] text-muted-foreground py-2.5 h-auto text-right hidden sm:table-cell">P/E</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((row) => (
                <TableRow key={row.symbol} className="border-border hover:bg-white/5 transition-colors">
                  <TableCell className="py-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <CompanyLogo symbol={row.symbol} logoUrl={row.logoUrl} />
                      <div className="flex flex-col min-w-0">
                        <span className="font-serif text-base leading-none">{row.symbol}</span>
                        {row.subIndustry && (
                          <span className="editorial-label text-[7.5px] text-muted-foreground truncate mt-0.5">
                            {row.subIndustry}
                          </span>
                        )}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="font-serif text-sm nums-tabular py-2 text-right">{row.price.toFixed(2)}</TableCell>
                  <TableCell className={`font-serif text-sm nums-tabular py-2 text-right ${row.changePct >= 0 ? 'text-white' : 'text-muted-foreground'}`}>
                    {row.changePct > 0 ? '+' : ''}{row.changePct.toFixed(2)}%
                  </TableCell>
                  <TableCell className={`font-serif text-sm nums-tabular py-2 text-right ${row.ret1Y == null ? 'text-gray-500' : row.ret1Y >= 0 ? 'text-white' : 'text-muted-foreground'}`}>
                    {row.ret1Y == null ? '—' : `${row.ret1Y > 0 ? '+' : ''}${row.ret1Y.toFixed(1)}%`}
                  </TableCell>
                  <TableCell className="font-serif text-sm nums-tabular py-2 text-right text-gray-400">{formatNumber(row.marketCap)}</TableCell>
                  <TableCell className="font-serif text-sm nums-tabular py-2 text-right text-gray-400">{formatNumber(row.volume)}</TableCell>
                  <TableCell className="font-serif text-sm nums-tabular py-2 text-right text-gray-400 hidden sm:table-cell">
                    {row.peRatio ? row.peRatio.toFixed(1) : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollArea>
      </div>
    </div>
  );
}
