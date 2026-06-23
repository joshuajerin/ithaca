// @ts-nocheck
import React from "react";

import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

interface PolyTrade {
  time: string | null;
  side: string;
  price: number;
  size: number;
  usd: number;
  outcome: string | null;
  wallet: string | null;
}

interface PolyHistoryPoint {
  t: string | null;
  p: number;
  prob: number;
}

interface PolymarketMarketPanelProps {
  data: {
    title: string;
    question: string | null;
    label: string | null;
    slug: string | null;
    icon: string | null;
    endDate: string | null;
    outcomes: string[] | null;
    prices: (number | null)[] | null;
    yesProbability: number | null;
    bestBid: number | null;
    bestAsk: number | null;
    spreadPct: number | null;
    volume: number | null;
    volume24hr: number | null;
    liquidity: number | null;
    interval: string;
    history: PolyHistoryPoint[] | null;
    historyAvailable: boolean;
    trades: PolyTrade[];
    tradesAvailable: boolean;
  };
  onRefine?: (instruction: string) => void;
}

const fmtUsd = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
};

const pct = (p: number | null | undefined): string =>
  p === null || p === undefined ? "—" : `${(p * 100).toFixed(0)}%`;

const fmtTime = (t: string | null): string => {
  if (!t) return "—";
  const d = new Date(t);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

const INTERVALS: Array<{ key: string; label: string }> = [
  { key: "1h", label: "1H" },
  { key: "6h", label: "6H" },
  { key: "1d", label: "1D" },
  { key: "1w", label: "1W" },
  { key: "1m", label: "1M" },
  { key: "max", label: "ALL" },
];

const HistTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-black border border-white/20 p-2 shadow-xl text-xs">
        <p className="text-muted-foreground mb-1">
          {label ? new Date(label).toLocaleString() : ""}
        </p>
        <p className="font-mono text-cyan-300">{payload[0].value?.toFixed(1)}% implied</p>
      </div>
    );
  }
  return null;
};

export function PolymarketMarketPanel({ data, onRefine }: PolymarketMarketPanelProps) {
  const {
    question,
    yesProbability,
    bestBid,
    bestAsk,
    spreadPct,
    volume,
    volume24hr,
    liquidity,
    interval,
    history,
    historyAvailable,
    trades = [],
    tradesAvailable,
    endDate,
    icon,
  } = data;

  return (
    <div className="flex flex-col h-full w-full">
      {/* Header: probability + key stats */}
      <div className="shrink-0 flex items-start gap-3 mb-3">
        {icon && (
          <img
            src={icon}
            alt=""
            className="w-10 h-10 rounded object-cover shrink-0"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-[12px] text-white font-medium leading-snug line-clamp-2">
            {question}
          </div>
          <div className="flex items-center gap-2 mt-1 text-[9px] uppercase tracking-wider text-muted-foreground font-mono">
            <span>{fmtUsd(volume)} vol</span>
            <span>·</span>
            <span>{fmtUsd(volume24hr)} 24h</span>
            <span>·</span>
            <span>{fmtUsd(liquidity)} liq</span>
            {endDate && (
              <>
                <span>·</span>
                <span>ends {new Date(endDate).toLocaleDateString()}</span>
              </>
            )}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-3xl font-bold font-mono text-cyan-300 leading-none">
            {pct(yesProbability)}
          </div>
          <div className="text-[8px] uppercase tracking-widest text-muted-foreground mt-1">
            Yes · implied
          </div>
        </div>
      </div>

      {/* Bid/ask/spread strip */}
      <div className="shrink-0 grid grid-cols-3 gap-2 mb-3">
        <div className="border border-border bg-white/[0.015] px-2 py-1.5 text-center">
          <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Bid</div>
          <div className="text-sm font-mono text-emerald-400">{pct(bestBid)}</div>
        </div>
        <div className="border border-border bg-white/[0.015] px-2 py-1.5 text-center">
          <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Ask</div>
          <div className="text-sm font-mono text-red-400">{pct(bestAsk)}</div>
        </div>
        <div className="border border-border bg-white/[0.015] px-2 py-1.5 text-center">
          <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Spread</div>
          <div className="text-sm font-mono text-white">
            {spreadPct === null || spreadPct === undefined ? "—" : `${spreadPct.toFixed(1)}pt`}
          </div>
        </div>
      </div>

      {/* Interval selector */}
      <div className="shrink-0 flex items-center justify-between mb-1.5">
        <span className="text-[9px] uppercase tracking-widest text-muted-foreground">
          Implied probability
        </span>
        <div className="flex gap-1">
          {INTERVALS.map((iv) => (
            <button
              key={iv.key}
              disabled={!onRefine}
              onClick={() =>
                onRefine?.(
                  `Show the ${iv.label} probability history for the ${question} prediction market`
                )
              }
              className={`text-[8px] uppercase tracking-wider px-1.5 py-0.5 border transition-colors ${
                iv.key === interval
                  ? "border-white/70 text-white"
                  : "border-border text-muted-foreground hover:text-white hover:border-white/30"
              } ${onRefine ? "cursor-pointer" : "cursor-default"}`}
            >
              {iv.label}
            </button>
          ))}
        </div>
      </div>

      {/* Probability history chart */}
      <div className="h-[40%] min-h-[120px] w-full shrink-0">
        {historyAvailable && history && history.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={history} margin={{ top: 4, right: 6, left: -22, bottom: 0 }}>
              <defs>
                <linearGradient id="polyProb" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 2" stroke="#333" vertical={false} />
              <XAxis
                dataKey="t"
                tick={{ fontSize: 9, fill: "#666" }}
                tickLine={false}
                axisLine={false}
                minTickGap={50}
                tickFormatter={(v) => (v ? new Date(v).toLocaleDateString([], { month: "short", day: "numeric" }) : "")}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fontSize: 9, fill: "#666" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `${v}`}
              />
              <Tooltip content={<HistTooltip />} />
              <Area
                type="monotone"
                dataKey="prob"
                stroke="#22d3ee"
                strokeWidth={2}
                fill="url(#polyProb)"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center text-[10px] text-muted-foreground border border-dashed border-border">
            No probability history available for this market.
          </div>
        )}
      </div>

      {/* Recent trades tape */}
      <div className="flex-1 min-h-0 flex flex-col mt-3">
        <div className="shrink-0 text-[9px] uppercase tracking-widest text-muted-foreground mb-1">
          Recent trades
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto pr-1">
          {!tradesAvailable ? (
            <div className="text-[10px] text-muted-foreground py-4 text-center">
              Trade tape unavailable.
            </div>
          ) : trades.length === 0 ? (
            <div className="text-[10px] text-muted-foreground py-4 text-center">
              No recent trades.
            </div>
          ) : (
            <table className="w-full text-[10px] font-mono">
              <thead className="text-muted-foreground text-[8px] uppercase tracking-wider sticky top-0 bg-black">
                <tr>
                  <th className="text-left font-normal py-0.5">Time</th>
                  <th className="text-left font-normal">Side</th>
                  <th className="text-left font-normal">Outcome</th>
                  <th className="text-right font-normal">Price</th>
                  <th className="text-right font-normal">Size</th>
                  <th className="text-right font-normal">USD</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => (
                  <tr key={i} className="border-t border-white/[0.04]">
                    <td className="py-0.5 text-muted-foreground">{fmtTime(t.time)}</td>
                    <td className={t.side === "BUY" ? "text-emerald-400" : "text-red-400"}>
                      {t.side}
                    </td>
                    <td className="text-white/80 truncate max-w-[64px]">{t.outcome ?? "—"}</td>
                    <td className="text-right text-white">{(t.price * 100).toFixed(0)}%</td>
                    <td className="text-right text-muted-foreground">{t.size.toFixed(0)}</td>
                    <td className="text-right text-white">{fmtUsd(t.usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
