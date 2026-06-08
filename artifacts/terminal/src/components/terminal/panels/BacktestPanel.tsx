import React, { useEffect, useState } from "react";
import type { BacktestData } from "@workspace/api-client-react";
import { CoverageBadge, type DataCoverage } from "./CoverageBadge";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

const STRATEGIES: { value: string; label: string }[] = [
  { value: "momentum", label: "Momentum" },
  { value: "mean_reversion", label: "Mean Reversion" },
  { value: "buy_and_hold", label: "Buy & Hold" },
];
const RANGES = ["1M", "3M", "6M", "1Y"] as const;

interface Props {
  data: BacktestData;
  onRefine?: (params: Record<string, unknown>) => void;
}

function fmtUsd(v?: number | null, compact = false): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  return v.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    notation: compact && abs >= 10000 ? "compact" : "standard",
    maximumFractionDigits: abs >= 1000 || compact ? 0 : 2,
  });
}

export function BacktestPanel({ data, onRefine }: Props) {
  const { stats, curve, drawdown } = data;
  const range = (data.range ?? "1Y").toUpperCase();
  const invested = data.investment ?? 0;
  const entryMode = data.entry?.mode ?? "preset";
  const gain = data.gain ?? 0;
  const gainUp = gain >= 0;

  // Local amount field so typing doesn't fire a refine per keystroke; commit on
  // Enter or blur. Reset whenever the panel's investment changes (new result).
  const [amountInput, setAmountInput] = useState<string>(
    invested ? String(Math.round(invested)) : "",
  );
  const [dateInput, setDateInput] = useState<string>(data.entry?.date ?? "");
  useEffect(() => {
    setAmountInput(invested ? String(Math.round(invested)) : "");
  }, [invested]);
  useEffect(() => {
    if (entryMode === "date" && data.entry?.date) setDateInput(data.entry.date);
  }, [entryMode, data.entry?.date]);

  const refine = (patch: Record<string, unknown>) => {
    if (!onRefine) return;
    onRefine({
      symbol: data.symbol,
      strategy: data.strategy,
      range,
      amount: invested || undefined,
      entry: entryMode,
      date: data.entry?.date,
      ...patch,
    });
  };

  const commitAmount = () => {
    const parsed = Number(amountInput.replace(/[^0-9.]/g, ""));
    if (Number.isFinite(parsed) && parsed > 0 && Math.round(parsed) !== Math.round(invested)) {
      refine({ amount: parsed });
    } else {
      setAmountInput(invested ? String(Math.round(invested)) : "");
    }
  };

  const commitDate = (d: string) => {
    setDateInput(d);
    if (d) refine({ entry: "date", date: d });
  };

  const closedTrades = (data.tradeLog ?? []).filter(
    (t) => typeof t.pnl === "number" && t.pnl !== 0,
  );
  const bestTrade = closedTrades.length
    ? closedTrades.reduce((a, b) => ((b.pnl ?? 0) > (a.pnl ?? 0) ? b : a))
    : null;
  const worstTrade = closedTrades.length
    ? closedTrades.reduce((a, b) => ((b.pnl ?? 0) < (a.pnl ?? 0) ? b : a))
    : null;

  const fmtUsdSigned = (v?: number) =>
    `${(v ?? 0) >= 0 ? "+" : "-"}${fmtUsd(Math.abs(v ?? 0))}`;

  const CurveTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div className="bg-black border border-white/20 p-2 text-xs space-y-1">
          <p className="text-muted-foreground">{label}</p>
          {payload.map((p: any) => (
            <p key={p.name} style={{ color: p.color }} className="font-mono">
              {p.name}: {fmtUsd(p.value)}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  const DDTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div className="bg-black border border-white/20 p-2 text-xs">
          <p className="text-muted-foreground">{label}</p>
          <p className="text-red-400 font-mono">DD: {payload[0].value.toFixed(2)}%</p>
        </div>
      );
    }
    return null;
  };

  const statItems = [
    { label: "Sharpe", value: stats.sharpe.toFixed(2), positive: stats.sharpe > 1 },
    { label: "CAGR", value: `${stats.cagr.toFixed(1)}%`, positive: stats.cagr > 0 },
    { label: "Max DD", value: `${stats.maxDD.toFixed(1)}%`, positive: false, alwaysRed: true },
    { label: "Win Rate", value: `${stats.winRate.toFixed(1)}%`, positive: stats.winRate > 50 },
  ];

  const downsampledCurve = curve.filter((_, i) => i % Math.max(1, Math.floor(curve.length / 120)) === 0);
  const downsampledDD = drawdown.filter((_, i) => i % Math.max(1, Math.floor(drawdown.length / 120)) === 0);

  const coverage = (data as unknown as { coverage?: DataCoverage }).coverage;

  return (
    <div className="flex flex-col h-full gap-3">
      <CoverageBadge coverage={coverage} />
      {onRefine && (
        <div className="flex flex-col gap-2 shrink-0">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-1.5">
              <span className="text-[9px] text-muted-foreground uppercase tracking-widest">Invest</span>
              <div className="flex items-center border border-border focus-within:border-white/60 transition-colors">
                <span className="text-[10px] text-muted-foreground pl-1.5">$</span>
                <input
                  type="text"
                  inputMode="numeric"
                  value={amountInput}
                  onChange={(e) => setAmountInput(e.target.value)}
                  onBlur={commitAmount}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                  }}
                  className="w-24 text-[10px] bg-black px-1 py-0.5 font-mono text-white focus:outline-none"
                  placeholder="10,000"
                />
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[9px] text-muted-foreground uppercase tracking-widest">Strategy</span>
              <select
                value={data.strategy}
                onChange={(e) => refine({ strategy: e.target.value })}
                className="text-[10px] bg-black border border-border px-1.5 py-0.5 font-mono text-white focus:outline-none focus:border-white/60 transition-colors"
              >
                {STRATEGIES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[9px] text-muted-foreground uppercase tracking-widest">Entry</span>
            <div className="flex gap-1 flex-wrap">
              <button
                onClick={() => refine({ entry: "peak" })}
                className={`text-[9px] px-2 py-0.5 border uppercase tracking-widest transition-colors ${
                  entryMode === "peak"
                    ? "border-white text-white bg-white/10"
                    : "border-border text-muted-foreground hover:border-white/40"
                }`}
              >
                Peak
              </button>
              <button
                onClick={() => entryMode !== "date" && commitDate(dateInput || data.entry?.date || "")}
                className={`text-[9px] px-2 py-0.5 border uppercase tracking-widest transition-colors ${
                  entryMode === "date"
                    ? "border-white text-white bg-white/10"
                    : "border-border text-muted-foreground hover:border-white/40"
                }`}
              >
                Date
              </button>
              {RANGES.map((r) => (
                <button
                  key={r}
                  onClick={() => refine({ entry: "preset", range: r })}
                  className={`text-[9px] px-2 py-0.5 border uppercase tracking-widest transition-colors ${
                    entryMode === "preset" && range === r
                      ? "border-white text-white bg-white/10"
                      : "border-border text-muted-foreground hover:border-white/40"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
            {entryMode === "date" && (
              <input
                type="date"
                value={dateInput}
                onChange={(e) => commitDate(e.target.value)}
                className="text-[10px] bg-black border border-border px-1.5 py-0.5 font-mono text-white focus:outline-none focus:border-white/60 transition-colors"
              />
            )}
          </div>
        </div>
      )}

      {/* Dollar outcome summary */}
      {invested > 0 && (
        <div className="grid grid-cols-4 gap-2 shrink-0">
          <div className="border border-border p-2">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">Invested</div>
            <div className="text-sm font-bold font-mono text-white">{fmtUsd(invested)}</div>
            <div className="text-[8px] text-muted-foreground mt-0.5 truncate">
              {data.entry?.label ?? "Entry"}
              {data.entry?.date ? ` · ${data.entry.date}` : ""}
              {data.entry?.price ? ` @ ${fmtUsd(data.entry.price)}` : ""}
            </div>
          </div>
          <div className="border border-border p-2">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">Now Worth</div>
            <div className="text-sm font-bold font-mono text-white">{fmtUsd(data.endValue)}</div>
            <div className="text-[8px] text-muted-foreground mt-0.5">
              vs hold {fmtUsd(data.benchmarkEndValue, true)}
            </div>
          </div>
          <div className="border border-border p-2">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">Gain / Loss</div>
            <div className={`text-sm font-bold font-mono ${gainUp ? "text-emerald-400" : "text-red-400"}`}>
              {fmtUsdSigned(gain)}
            </div>
            <div className={`text-[8px] mt-0.5 ${gainUp ? "text-emerald-400/70" : "text-red-400/70"}`}>
              {(data.gainPct ?? 0) >= 0 ? "+" : ""}{(data.gainPct ?? 0).toFixed(1)}%
            </div>
          </div>
          <div className="border border-border p-2">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">Multiple</div>
            <div className={`text-sm font-bold font-mono ${gainUp ? "text-emerald-400" : "text-red-400"}`}>
              {(data.multiple ?? 1).toFixed(2)}×
            </div>
            <div className="text-[8px] text-muted-foreground mt-0.5">on invested</div>
          </div>
        </div>
      )}

      {data.entryNote && (
        <div className="shrink-0 text-[8.5px] text-amber-300/80 border border-amber-500/20 bg-amber-500/[0.04] px-2 py-1 leading-relaxed">
          {data.entryNote}
        </div>
      )}

      <div className="grid grid-cols-4 gap-2 shrink-0">
        {statItems.map((item) => (
          <div key={item.label} className="border border-border p-2">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">{item.label}</div>
            <div
              className={`text-sm font-bold font-mono ${
                item.alwaysRed ? "text-red-400" : item.positive ? "text-white" : "text-muted-foreground"
              }`}
            >
              {item.value}
            </div>
          </div>
        ))}
      </div>

      {(bestTrade || worstTrade) && (
        <div className="grid grid-cols-2 gap-2 shrink-0">
          {[
            { label: "Best Trade", trade: bestTrade, color: "text-emerald-400" },
            { label: "Worst Trade", trade: worstTrade, color: "text-red-400" },
          ].map(({ label, trade, color }) => (
            <div key={label} className="border border-border p-2">
              <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">{label}</div>
              {trade ? (
                <div className="flex items-baseline justify-between gap-2">
                  <span className={`text-sm font-bold font-mono ${color}`}>
                    {fmtUsdSigned(trade.pnl)}
                  </span>
                  <span className="text-[10px] font-mono text-muted-foreground">
                    {(trade.pnlPct ?? 0) >= 0 ? "+" : ""}{(trade.pnlPct ?? 0).toFixed(1)}% · {trade.action} @ {trade.price} · {trade.t}
                  </span>
                </div>
              ) : (
                <div className="text-sm font-mono text-muted-foreground">—</div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex-1 min-h-0 flex flex-col gap-2">
        <div className="flex-[2] min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
            {data.strategy.replace(/_/g, " ").toUpperCase()} · {data.symbol} vs Buy &amp; Hold (in $)
          </div>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={downsampledCurve} margin={{ top: 2, right: 0, left: -8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
              <XAxis dataKey="t" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} minTickGap={40} />
              <YAxis
                tick={{ fontSize: 9, fill: "#555" }}
                tickLine={false}
                axisLine={false}
                domain={["auto", "auto"]}
                width={52}
                tickFormatter={(v) => fmtUsd(v, true)}
              />
              <Tooltip content={<CurveTooltip />} />
              <Line type="monotone" dataKey="strategy" stroke="#ffffff" strokeWidth={1.5} dot={false} name="Strategy" />
              <Line type="monotone" dataKey="benchmark" stroke="#555555" strokeWidth={1} dot={false} name="Buy & Hold" strokeDasharray="4 2" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="flex-1 min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Drawdown</div>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={downsampledDD} margin={{ top: 2, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
              <XAxis dataKey="t" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} minTickGap={40} />
              <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
              <Tooltip content={<DDTooltip />} />
              <defs>
                <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ef4444" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#ef4444" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <Area type="monotone" dataKey="dd" stroke="#ef4444" strokeWidth={1} fill="url(#ddGrad)" name="Drawdown" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
