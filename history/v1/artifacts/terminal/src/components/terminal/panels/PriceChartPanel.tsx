import React from "react";
import type { PriceChartData } from "@workspace/api-client-react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine } from "recharts";
import { Sparkline } from "../Sparkline";

interface PriceChartPanelProps {
  data: PriceChartData;
  onSelectRange?: (range: string) => void;
}

const DEFAULT_RANGES = ["1D", "1W", "1M", "3M", "6M", "1Y"];
const INTRADAY_RANGES = new Set(["1D", "1W"]);

// Short ranges plot intraday bars whose `t` is a full ISO datetime; format the
// axis/tooltip as time-of-day (1D) or short date (1W) rather than a raw date.
function formatAxisLabel(value: string, range: string): string {
  if (!INTRADAY_RANGES.has(range)) return value;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  if (range === "1D") {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString([], { month: "numeric", day: "numeric" });
}

function formatTooltipLabel(value: string, range: string): string {
  if (!INTRADAY_RANGES.has(range)) return value;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString([], {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function PriceChartPanel({ data, onSelectRange }: PriceChartPanelProps) {
  const unavailable = data.available === false || data.last == null;
  const isPositive = (data.change ?? 0) >= 0;
  const spark = data.points.map((p) => p.c);
  const ranges = (data.ranges && data.ranges.length ? data.ranges : DEFAULT_RANGES);

  // Create a minimal tooltip
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-black border border-white px-3 py-2">
          <p className="editorial-label text-[8px] text-muted-foreground">{formatTooltipLabel(label, data.range)}</p>
          <p className="font-serif text-lg nums-tabular mt-0.5">
            {payload[0].value.toFixed(2)}
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex justify-between items-start mb-5 shrink-0">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <span className="font-serif text-4xl leading-none tracking-tight">{data.symbol}</span>
            {!unavailable && (
              <span className="text-muted-foreground mt-1">
                <Sparkline data={spark} width={56} height={22} />
              </span>
            )}
          </div>
          <div className="editorial-label text-[9px] text-muted-foreground mt-2 truncate">
            {data.name} · {data.range} Range
          </div>
        </div>
        <div className="text-right shrink-0 ml-4">
          {unavailable ? (
            <div className="font-serif text-3xl leading-none nums-oldstyle text-muted-foreground">—</div>
          ) : (
            <>
              <div className="font-serif text-3xl leading-none nums-oldstyle">
                {data.last!.toFixed(2)}
              </div>
              <div className="editorial-label text-[8px] text-muted-foreground mt-1.5 mb-1">{data.currency}</div>
              <div className={`font-serif text-base nums-oldstyle ${isPositive ? 'text-white' : 'text-muted-foreground'}`}>
                {isPositive ? '+' : ''}{(data.change ?? 0).toFixed(2)} ({isPositive ? '+' : ''}{(data.changePct ?? 0).toFixed(2)}%)
              </div>
              <div className="editorial-label text-[8px] text-muted-foreground mt-0.5">over {data.range}</div>
            </>
          )}
        </div>
      </div>

      {onSelectRange && (
        <div className="flex items-center gap-1.5 mb-3 shrink-0 flex-wrap">
          {ranges.map((r) => {
            const active = r === data.range;
            return (
              <button
                key={r}
                type="button"
                onClick={() => { if (!active) onSelectRange(r); }}
                aria-pressed={active}
                className={`editorial-label text-[9px] px-2 py-1 border transition-colors ${
                  active
                    ? "border-white text-white"
                    : "border-border text-muted-foreground hover:text-white hover:border-white"
                }`}
              >
                {r}
              </button>
            );
          })}
        </div>
      )}

      <div className="border-t border-border flex-1 w-full min-h-0 pt-3">
        {unavailable ? (
          <div className="w-full h-full flex flex-col items-center justify-center text-center gap-2 px-6">
            <span className="editorial-label text-[9px] text-muted-foreground">Intraday data unavailable</span>
            <span className="text-[10px] text-muted-foreground/70 max-w-[240px] leading-snug">
              {data.reason || `No intraday bars for ${data.symbol} over ${data.range}. Try a longer range.`}
            </span>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.points} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="1 3" stroke="#2a2a2a" vertical={false} />
              <XAxis
                dataKey="t"
                tick={{ fontSize: 9, fill: '#777', fontFamily: 'Inter', letterSpacing: '0.08em' }}
                tickLine={false}
                axisLine={false}
                minTickGap={30}
                tickFormatter={(val) => formatAxisLabel(val, data.range)}
              />
              <YAxis
                domain={['auto', 'auto']}
                tick={{ fontSize: 10, fill: '#777', fontFamily: 'Newsreader' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(val) => val.toFixed(1)}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ stroke: '#555', strokeWidth: 1 }} />
              {data.points.length > 0 && (
                <ReferenceLine y={data.points[0].c} stroke="#3a3a3a" strokeDasharray="2 4" />
              )}
              <Line
                type="monotone"
                dataKey="c"
                stroke="#fff"
                strokeWidth={1.25}
                dot={false}
                activeDot={{ r: 3, fill: '#000', stroke: '#fff', strokeWidth: 1.5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
