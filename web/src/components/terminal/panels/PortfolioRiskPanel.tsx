// @ts-nocheck
import React, { useState } from "react";
import type { PortfolioRiskData } from "@workspace/api-client-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  ReferenceLine,
} from "recharts";
import { X, Loader2 } from "lucide-react";

interface Props {
  data: PortfolioRiskData;
  onRefine?: (params: Record<string, unknown>) => void;
  pending?: boolean;
}

export function PortfolioRiskPanel({ data, onRefine, pending }: Props) {
  const { summary, varHistogram, factorExposures } = data;
  const [draft, setDraft] = useState("");

  const symbols = data.symbols;

  const removeSymbol = (s: string) => {
    if (symbols.length <= 1) return;
    onRefine?.({ symbols: symbols.filter((x) => x !== s) });
  };

  const addSymbol = (e: React.FormEvent) => {
    e.preventDefault();
    const t = draft.trim().toUpperCase();
    setDraft("");
    if (!t || symbols.includes(t)) return;
    onRefine?.({ symbols: [...symbols, t] });
  };

  const var95Bin = -summary.var95;
  const maxCount = Math.max(...varHistogram.map((b) => b.count));

  const VarTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div className="bg-black border border-white/20 p-2 text-xs">
          <p className="text-muted-foreground">P&L: {label}%</p>
          <p className="text-white font-bold">Count: {payload[0].value}</p>
        </div>
      );
    }
    return null;
  };

  const FactorTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div className="bg-black border border-white/20 p-2 text-xs">
          <p className="text-muted-foreground">{label}</p>
          <p className="text-white font-bold">Exposure: {payload[0].value.toFixed(2)}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="relative flex-1 flex flex-col gap-3 min-h-0">
        {pending && (
          <div className="absolute inset-0 z-10 bg-black/50 flex items-center justify-center pointer-events-none">
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" strokeWidth={1.5} />
          </div>
        )}
      <div className="grid grid-cols-3 gap-3 shrink-0">
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">1-Day 95% VaR</div>
          <div className="text-lg font-bold font-mono text-red-400">-{summary.var95.toFixed(2)}%</div>
        </div>
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Tracking Error</div>
          <div className="text-lg font-bold font-mono">{summary.trackingError.toFixed(2)}%</div>
        </div>
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Portfolio Beta</div>
          <div className="text-lg font-bold font-mono">{summary.beta.toFixed(2)}</div>
        </div>
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        <div className="flex-1 flex flex-col min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">P&L Distribution (VaR)</div>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={varHistogram} margin={{ top: 2, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 2" stroke="#222" vertical={false} />
                <XAxis
                  dataKey="bin"
                  tick={{ fontSize: 9, fill: "#555" }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={20}
                  tickFormatter={(v) => `${v}%`}
                />
                <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} />
                <Tooltip content={<VarTooltip />} />
                <ReferenceLine x={-summary.var95} stroke="#ef4444" strokeDasharray="3 3" strokeWidth={1.5} />
                <Bar dataKey="count" radius={[1, 1, 0, 0]}>
                  {varHistogram.map((entry, idx) => (
                    <Cell
                      key={idx}
                      fill={entry.bin <= -summary.var95 ? "#ef4444" : "#ffffff"}
                      fillOpacity={entry.bin <= -summary.var95 ? 0.7 : 0.3 + 0.5 * (entry.count / maxCount)}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="w-36 flex flex-col min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">Factor Exposures</div>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={factorExposures}
                layout="vertical"
                margin={{ top: 2, right: 8, left: 8, bottom: 2 }}
              >
                <CartesianGrid strokeDasharray="2 2" stroke="#222" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} domain={[-1, 2]} />
                <YAxis
                  type="category"
                  dataKey="factor"
                  tick={{ fontSize: 9, fill: "#888" }}
                  tickLine={false}
                  axisLine={false}
                  width={52}
                />
                <Tooltip content={<FactorTooltip />} />
                <ReferenceLine x={0} stroke="#444" strokeWidth={1} />
                <Bar dataKey="exposure" radius={[0, 2, 2, 0]}>
                  {factorExposures.map((entry, idx) => (
                    <Cell key={idx} fill={entry.exposure >= 0 ? "#ffffff" : "#888888"} fillOpacity={0.7} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      </div>

      <div className="shrink-0">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Holdings</div>
        <div className="flex flex-wrap items-center gap-1.5">
          {symbols.map((s) => (
            <span
              key={s}
              className="group/chip flex items-center gap-1 text-[10px] border border-border px-1.5 py-0.5 font-mono text-white/70"
            >
              {s}
              {onRefine && symbols.length > 1 && (
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => removeSymbol(s)}
                  className="text-muted-foreground hover:text-red-400 transition-colors disabled:opacity-50"
                  aria-label={`Remove ${s}`}
                >
                  <X className="w-2.5 h-2.5" strokeWidth={2} />
                </button>
              )}
            </span>
          ))}
          {onRefine && (
            <form onSubmit={addSymbol}>
              <input
                value={draft}
                disabled={pending}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="+ ticker"
                aria-label="Add ticker"
                spellCheck={false}
                className="w-16 bg-transparent border border-dashed border-border px-1.5 py-0.5 text-[10px] font-mono uppercase text-white placeholder:text-muted-foreground focus:outline-none focus:border-white/60 transition-colors disabled:opacity-50"
              />
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
