import React, { useState } from "react";
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";
import { ScrollArea } from "@/components/ui/scroll-area";

interface BondRVPanelProps {
  data: any;
}

type SortKey = "yieldPct" | "duration" | "zSpread" | "oas" | "aswSpread";

const SCATTER_COLORS: Record<string, string> = {
  AAPL: "#ffffff",
  MSFT: "#9ca3af",
  AMZN: "#6b7280",
  GOOGL: "#4b5563",
  META: "#d1d5db",
  NVDA: "#f9fafb",
  INTC: "#6b7280",
  F: "#ef4444",
  XOM: "#f59e0b",
  CVX: "#fbbf24",
};

const CustomScatterTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const row: any = payload[0].payload;
    return (
      <div className="bg-black border border-white/20 p-2 shadow-xl text-xs">
        <p className="font-bold text-white mb-1">{row.issuer}</p>
        <p className="text-muted-foreground">{row.coupon}% {row.maturityYear}</p>
        <p className="font-mono">Yield: {row.yieldPct.toFixed(2)}%</p>
        <p className="font-mono">Dur: {row.duration.toFixed(1)}yr</p>
        <p className="font-mono">Z: {row.zSpread}bp</p>
      </div>
    );
  }
  return null;
};

export function BondRVPanel({ data }: BondRVPanelProps) {
  const [sortKey, setSortKey] = useState<SortKey>("zSpread");
  const [sortAsc, setSortAsc] = useState(false);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  const sorted = [...data.rows].sort((a, b) => {
    const diff = a[sortKey] - b[sortKey];
    return sortAsc ? diff : -diff;
  });

  const SortHeader = ({ k, label }: { k: SortKey; label: string }) => (
    <th
      className="text-right py-1.5 px-2 text-[9px] uppercase tracking-wider cursor-pointer select-none hover:text-white transition-colors"
      onClick={() => handleSort(k)}
    >
      {label}{sortKey === k ? (sortAsc ? " ↑" : " ↓") : ""}
    </th>
  );

  return (
    <div className="flex flex-col h-full w-full">
      <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-2 shrink-0">
        {data.title}
      </div>

      <div className="h-28 w-full shrink-0 mb-2">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="#222" />
            <XAxis
              dataKey="duration"
              name="Duration"
              type="number"
              domain={["auto", "auto"]}
              tick={{ fontSize: 9, fill: "#666" }}
              tickLine={false}
              axisLine={false}
              label={{ value: "Duration (yr)", position: "insideBottomRight", offset: -4, fontSize: 8, fill: "#555" }}
            />
            <YAxis
              dataKey="yieldPct"
              name="Yield"
              type="number"
              domain={["auto", "auto"]}
              tick={{ fontSize: 9, fill: "#666" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v.toFixed(1)}%`}
            />
            <Tooltip content={<CustomScatterTooltip />} />
            <Scatter data={data.rows} name="Bonds">
              {data.rows.map((row: any, i: any) => (
                <Cell
                  key={i}
                  fill={row.ticker === data.highlight ? "#ffffff" : "#4b5563"}
                  r={row.ticker === data.highlight ? 5 : 3}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <div className="flex-1 min-h-0 border border-border">
        <ScrollArea className="h-full">
          <table className="w-full text-xs">
            <thead className="bg-black sticky top-0 z-10">
              <tr className="border-b border-border text-muted-foreground">
                <th className="text-left py-1.5 px-2 text-[9px] uppercase tracking-wider">Issuer</th>
                <th className="text-right py-1.5 px-2 text-[9px] uppercase tracking-wider">Cpn/Mat</th>
                <SortHeader k="yieldPct" label="Yield" />
                <SortHeader k="duration" label="Dur" />
                <SortHeader k="zSpread" label="Z-Spd" />
                <SortHeader k="oas" label="OAS" />
                <SortHeader k="aswSpread" label="ASW" />
                <th className="text-right py-1.5 px-2 text-[9px] uppercase tracking-wider">Rtg</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => {
                const isHighlight = row.ticker === data.highlight;
                return (
                  <tr
                    key={i}
                    className={`border-b border-border/40 hover:bg-white/5 transition-colors ${isHighlight ? "bg-white/5" : ""}`}
                  >
                    <td className={`py-1.5 px-2 font-bold ${isHighlight ? "text-white" : "text-muted-foreground"}`}>
                      {row.ticker}
                    </td>
                    <td className="py-1.5 px-2 text-right font-mono text-muted-foreground text-[10px]">
                      {row.coupon}%/{row.maturityYear}
                    </td>
                    <td className="py-1.5 px-2 text-right font-mono">{row.yieldPct.toFixed(2)}%</td>
                    <td className="py-1.5 px-2 text-right font-mono">{row.duration.toFixed(1)}</td>
                    <td className="py-1.5 px-2 text-right font-mono font-bold">{row.zSpread}</td>
                    <td className="py-1.5 px-2 text-right font-mono">{row.oas}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-muted-foreground">{row.aswSpread}</td>
                    <td className="py-1.5 px-2 text-right text-muted-foreground text-[9px]">{row.rating}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </ScrollArea>
      </div>
    </div>
  );
}
