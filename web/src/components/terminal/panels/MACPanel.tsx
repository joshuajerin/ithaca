// @ts-nocheck
import React, { useState, useMemo } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, Tooltip, CartesianGrid, ZAxis } from "recharts";

interface MADeal {
  id: string;
  target: string;
  targetSymbol?: string | null;
  acquirer: string;
  acquirerSymbol?: string | null;
  dealValue: number;
  premium: number;
  status: string;
  announced: string;
  expectedClose?: string | null;
  arbSpread?: number | null;
  dealType: string;
  sector: string;
}

interface MAStats {
  totalDeals: number;
  totalValue: number;
  avgPremium: number;
  pendingDeals: number;
}

interface MAData {
  title: string;
  deals: MADeal[];
  stats: MAStats;
}

const STATUS_STYLES: Record<string, string> = {
  pending: "text-yellow-400 border-yellow-400/50 bg-yellow-400/5",
  completed: "text-emerald-400 border-emerald-400/50 bg-emerald-400/5",
  withdrawn: "text-red-400 border-red-400/50 bg-red-400/5",
};

const TYPE_OPTIONS = ["All", "acquisition", "merger", "LBO", "tender offer"];

function fmtDealVal(n: number): string {
  if (n >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toFixed(0)}`;
}

const SECTOR_LABELS: Record<string, string> = {
  ai_tech: "AI/Tech",
  semiconductors: "Semis",
  energy: "Energy",
};

export function MACPanel({ data }: { data: MAData }) {
  const [filterType, setFilterType] = useState("All");
  const [filterStatus, setFilterStatus] = useState("All");
  const [view, setView] = useState<"table" | "scatter">("table");

  const filtered = useMemo(() => {
    return data.deals.filter(d => {
      if (filterType !== "All" && d.dealType !== filterType) return false;
      if (filterStatus !== "All" && d.status !== filterStatus) return false;
      return true;
    });
  }, [data.deals, filterType, filterStatus]);

  const scatterData = useMemo(() =>
    data.deals.map(d => ({
      x: d.dealValue / 1e9,
      y: d.premium,
      z: d.status === "pending" ? 40 : 20,
      name: d.target,
      status: d.status,
    })), [data.deals]
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header stats */}
      <div className="flex gap-4 mb-3 shrink-0">
        <div>
          <div className="text-[9px] text-muted-foreground uppercase tracking-wider">Total Deals</div>
          <div className="text-lg font-bold font-mono">{data.stats.totalDeals}</div>
        </div>
        <div>
          <div className="text-[9px] text-muted-foreground uppercase tracking-wider">Total Value</div>
          <div className="text-lg font-bold font-mono">{fmtDealVal(data.stats.totalValue)}</div>
        </div>
        <div>
          <div className="text-[9px] text-muted-foreground uppercase tracking-wider">Avg Premium</div>
          <div className="text-lg font-bold font-mono text-white">{data.stats.avgPremium.toFixed(1)}%</div>
        </div>
        <div>
          <div className="text-[9px] text-muted-foreground uppercase tracking-wider">Pending</div>
          <div className="text-lg font-bold font-mono text-yellow-400">{data.stats.pendingDeals}</div>
        </div>
        <div className="ml-auto flex gap-1 items-start">
          {(["table", "scatter"] as const).map(v => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`text-[10px] uppercase tracking-widest px-2 py-0.5 border transition-colors ${
                view === v ? "border-white text-white bg-white/10" : "border-border text-muted-foreground hover:border-gray-500"
              }`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex gap-2 mb-2 shrink-0 flex-wrap">
        <div className="flex gap-1">
          {["All", "pending", "completed", "withdrawn"].map(s => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 border transition-colors ${
                filterStatus === s
                  ? s === "pending" ? "border-yellow-400 text-yellow-400 bg-yellow-400/5"
                    : s === "completed" ? "border-emerald-400 text-emerald-400 bg-emerald-400/5"
                    : s === "withdrawn" ? "border-red-400 text-red-400 bg-red-400/5"
                    : "border-white text-white bg-white/10"
                  : "border-border/50 text-muted-foreground hover:border-gray-500"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {TYPE_OPTIONS.map(t => (
            <button
              key={t}
              onClick={() => setFilterType(t)}
              className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 border transition-colors ${
                filterType === t ? "border-white text-white bg-white/10" : "border-border/50 text-muted-foreground hover:border-gray-500"
              }`}
            >
              {t === "All" ? "All Types" : t}
            </button>
          ))}
        </div>
      </div>

      {view === "scatter" ? (
        <div className="flex-1 min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1">Premium vs Deal Size</div>
          <ResponsiveContainer width="100%" height="90%">
            <ScatterChart margin={{ top: 5, right: 10, left: 0, bottom: 20 }}>
              <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" />
              <XAxis
                type="number"
                dataKey="x"
                name="Deal Value"
                unit="B"
                tick={{ fontSize: 9, fill: "#555" }}
                tickLine={false}
                axisLine={false}
                label={{ value: "Deal Value ($B)", position: "insideBottom", offset: -15, fontSize: 9, fill: "#555" }}
              />
              <YAxis
                type="number"
                dataKey="y"
                name="Premium"
                unit="%"
                tick={{ fontSize: 9, fill: "#555" }}
                tickLine={false}
                axisLine={false}
                label={{ value: "Premium %", angle: -90, position: "insideLeft", offset: 10, fontSize: 9, fill: "#555" }}
              />
              <ZAxis type="number" dataKey="z" range={[20, 60]} />
              <Tooltip
                contentStyle={{ backgroundColor: "#000", borderColor: "#333", fontSize: 10 }}
                content={({ payload }) => {
                  if (!payload?.length) return null;
                  const d = payload[0].payload;
                  return (
                    <div className="bg-black border border-border p-2 text-[10px]">
                      <div className="font-bold">{d.name}</div>
                      <div>Value: ${d.x.toFixed(1)}B</div>
                      <div>Premium: {d.y.toFixed(1)}%</div>
                      <div className={STATUS_STYLES[d.status]?.split(" ")[0] || "text-white"}>{d.status}</div>
                    </div>
                  );
                }}
              />
              {["pending", "completed", "withdrawn"].map(status => (
                <Scatter
                  key={status}
                  name={status}
                  data={scatterData.filter(d => d.status === status)}
                  fill={status === "pending" ? "#facc15" : status === "completed" ? "#34d399" : "#f87171"}
                  fillOpacity={0.7}
                />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <ScrollArea className="flex-1 min-h-0">
          <table className="w-full text-xs border-collapse">
            <thead className="sticky top-0 bg-black z-10">
              <tr className="border-b border-border">
                {["Target", "Acquirer", "Value", "Premium", "Type", "Announced", "Status", "Arb"].map(h => (
                  <th key={h} className="text-[9px] text-muted-foreground uppercase tracking-wider py-1.5 text-left pr-2 font-normal whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(deal => (
                <tr key={deal.id} className="border-b border-border/30 hover:bg-white/5 transition-colors">
                  <td className="py-1.5 pr-2 whitespace-nowrap">
                    <span className="font-bold">{deal.target}</span>
                    {deal.targetSymbol && <span className="text-muted-foreground ml-1 text-[9px]">{deal.targetSymbol}</span>}
                    <div className="text-[9px] text-muted-foreground">{SECTOR_LABELS[deal.sector] || deal.sector}</div>
                  </td>
                  <td className="py-1.5 pr-2 text-muted-foreground whitespace-nowrap">
                    {deal.acquirer}
                    {deal.acquirerSymbol && <span className="text-[9px] ml-1">{deal.acquirerSymbol}</span>}
                  </td>
                  <td className="py-1.5 pr-2 font-mono whitespace-nowrap">{fmtDealVal(deal.dealValue)}</td>
                  <td className="py-1.5 pr-2 font-mono text-white whitespace-nowrap">+{deal.premium.toFixed(1)}%</td>
                  <td className="py-1.5 pr-2 text-[9px] text-muted-foreground uppercase whitespace-nowrap">{deal.dealType}</td>
                  <td className="py-1.5 pr-2 text-[9px] text-muted-foreground whitespace-nowrap">{deal.announced}</td>
                  <td className="py-1.5 pr-2 whitespace-nowrap">
                    <span className={`text-[9px] uppercase font-bold border px-1 py-0.5 ${STATUS_STYLES[deal.status] || "text-muted-foreground border-border"}`}>
                      {deal.status}
                    </span>
                    {deal.expectedClose && deal.status === "pending" && (
                      <div className="text-[9px] text-muted-foreground mt-0.5">{deal.expectedClose}</div>
                    )}
                  </td>
                  <td className="py-1.5 font-mono whitespace-nowrap">
                    {deal.arbSpread != null ? (
                      <span className="text-yellow-400 font-bold">{deal.arbSpread.toFixed(1)}%</span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="text-xs text-muted-foreground p-4 text-center">No deals match the current filter.</div>
          )}
        </ScrollArea>
      )}
    </div>
  );
}
