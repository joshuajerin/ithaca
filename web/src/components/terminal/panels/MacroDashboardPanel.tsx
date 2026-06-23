// @ts-nocheck
import React from "react";
import { LineChart, Line, ResponsiveContainer } from "recharts";

const GROUP_COLORS: Record<string, string> = {
  Rates: "#8b8b8b",
  FX: "#a0a0a0",
  Commodities: "#909090",
  Equities: "#b0b0b0",
};

function formatPrice(price: number, unit: string): string {
  if (unit === "%") return `${price >= 0 ? "" : ""}${price.toFixed(2)}%`;
  if (unit === "bps") return `${price >= 0 ? "+" : ""}${price.toFixed(0)} bps`;
  if (unit === "FX") return price.toFixed(4);
  if (price >= 10000) return price.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (price >= 100) return price.toFixed(2);
  return price.toFixed(4);
}

function Sparkline({ data, positive }: { data: number[]; positive: boolean }) {
  const points = data.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={32}>
      <LineChart data={points} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={positive ? "#ffffff" : "#555555"}
          strokeWidth={1}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

const REGIME_STYLES: Record<
  string,
  { border: string; bg: string; dot: string; text: string }
> = {
  risk_on: {
    border: "border-emerald-400/40",
    bg: "bg-emerald-400/10",
    dot: "#34d399",
    text: "text-emerald-300",
  },
  risk_off: {
    border: "border-red-400/40",
    bg: "bg-red-400/10",
    dot: "#f87171",
    text: "text-red-300",
  },
  stagflation: {
    border: "border-amber-400/40",
    bg: "bg-amber-400/10",
    dot: "#fbbf24",
    text: "text-amber-300",
  },
  soft_landing: {
    border: "border-sky-400/40",
    bg: "bg-sky-400/10",
    dot: "#38bdf8",
    text: "text-sky-300",
  },
  neutral: {
    border: "border-white/20",
    bg: "bg-white/5",
    dot: "#9ca3af",
    text: "text-muted-foreground",
  },
};

function RegimeBanner({ regime }: { regime: any }) {
  const style = REGIME_STYLES[regime.label] ?? REGIME_STYLES.neutral;
  const headline =
    regime.headline ??
    String(regime.label ?? "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c: string) => c.toUpperCase());

  return (
    <div
      className={`flex items-center gap-2 px-2.5 py-1.5 border ${style.border} ${style.bg} shrink-0`}
    >
      <span
        className="inline-block h-2 w-2 rounded-full shrink-0"
        style={{ backgroundColor: style.dot }}
      />
      <span
        className={`text-[10px] font-bold uppercase tracking-[0.18em] shrink-0 ${style.text}`}
      >
        {headline}
      </span>
      <span className="text-[9px] text-muted-foreground/50 shrink-0">·</span>
      <span className="text-[10px] text-muted-foreground truncate min-w-0">
        {regime.rationale}
      </span>
    </div>
  );
}

function AssetTile({ tile }: { tile: any }) {
  const isPositive = tile.changePct >= 0;
  const isLive = tile.isLive === true;

  return (
    <div
      className={`flex flex-col justify-between p-2 border transition-colors hover:border-white/40 ${
        isPositive
          ? "border-white/20 bg-white/5"
          : "border-white/10 bg-black"
      }`}
      style={{ minWidth: 0 }}
    >
      <div className="flex items-start justify-between gap-1 min-w-0">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1">
            <span
              title={isLive ? "Live quote" : "Curated reference value (no live source)"}
              className={`w-1 h-1 rounded-full shrink-0 ${
                isLive ? "bg-emerald-400" : "bg-muted-foreground/40"
              }`}
            />
            <div className="text-[10px] font-bold uppercase tracking-wider text-white truncate">
              {tile.symbol}
            </div>
          </div>
          <div className="text-[9px] text-muted-foreground truncate leading-tight">
            {tile.name}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div
            className={`text-[10px] font-bold tabular-nums ${
              isPositive ? "text-white" : "text-muted-foreground"
            }`}
          >
            {isPositive ? "+" : ""}
            {tile.changePct.toFixed(2)}%
          </div>
        </div>
      </div>

      <div className="my-1">
        <Sparkline data={tile.sparkline} positive={isPositive} />
      </div>

      <div className="text-[11px] font-bold tabular-nums text-white/90 leading-none">
        {formatPrice(tile.price, tile.unit)}
      </div>
    </div>
  );
}

export function MacroDashboardPanel({ data }: { data: any }) {
  return (
    <div className="flex flex-col h-full gap-3 overflow-y-auto">
      {data.regime && <RegimeBanner regime={data.regime} />}
      <div className="flex items-center justify-end gap-2.5 text-[8px] text-muted-foreground/70 shrink-0 -mb-1">
        <span className="flex items-center gap-1">
          <span className="w-1 h-1 rounded-full bg-emerald-400" /> live
        </span>
        <span className="flex items-center gap-1">
          <span className="w-1 h-1 rounded-full bg-muted-foreground/40" /> reference
        </span>
        <span className="editorial-label">% = 1D change</span>
      </div>
      {data.groups.map((group: any) => (
        <div key={group.label} className="shrink-0">
          <div
            className="text-[9px] font-bold uppercase tracking-[0.2em] mb-1.5 pb-1 border-b"
            style={{
              color: GROUP_COLORS[group.label] ?? "#888",
              borderColor: GROUP_COLORS[group.label]
                ? `${GROUP_COLORS[group.label]}40`
                : "#333",
            }}
          >
            {group.label}
          </div>
          <div
            className="grid gap-1.5"
            style={{
              gridTemplateColumns: `repeat(${Math.min(group.tiles.length, 5)}, minmax(0, 1fr))`,
            }}
          >
            {group.tiles.map((tile: any) => (
              <AssetTile key={tile.symbol} tile={tile} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
