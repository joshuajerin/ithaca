import React from "react";

interface PolyPosition {
  title: string | null;
  outcome: string | null;
  slug: string | null;
  icon: string | null;
  size: number | null;
  avgPrice: number | null;
  curPrice: number | null;
  initialValue: number | null;
  currentValue: number | null;
  cashPnl: number | null;
  percentPnl: number | null;
  realizedPnl: number | null;
  redeemable: boolean;
  endDate: string | null;
}

interface PolymarketWalletPanelProps {
  data: {
    title: string;
    address: string;
    value: number | null;
    positions: PolyPosition[];
    positionCount: number;
    summary: {
      currentValue: number;
      costBasis: number;
      unrealizedPnl: number;
      realizedPnl: number;
      totalPnlPct: number | null;
    };
  };
}

const fmtUsd = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(2)}`;
};

const pnlColor = (v: number | null | undefined): string =>
  v === null || v === undefined ? "text-muted-foreground" : v >= 0 ? "text-emerald-400" : "text-red-400";

export function PolymarketWalletPanel({ data }: PolymarketWalletPanelProps) {
  const { address, value, positions = [], summary } = data;

  return (
    <div className="flex flex-col h-full w-full">
      {/* Summary tiles */}
      <div className="shrink-0 grid grid-cols-2 gap-2 mb-3">
        <div className="border border-border bg-white/[0.015] px-3 py-2">
          <div className="text-[8px] uppercase tracking-widest text-muted-foreground">
            Portfolio value
          </div>
          <div className="text-xl font-bold font-mono text-white mt-0.5">
            {fmtUsd(value ?? summary?.currentValue)}
          </div>
        </div>
        <div className="border border-border bg-white/[0.015] px-3 py-2">
          <div className="text-[8px] uppercase tracking-widest text-muted-foreground">
            Unrealized PnL
          </div>
          <div className={`text-xl font-bold font-mono mt-0.5 ${pnlColor(summary?.unrealizedPnl)}`}>
            {fmtUsd(summary?.unrealizedPnl)}
            {summary?.totalPnlPct !== null && summary?.totalPnlPct !== undefined && (
              <span className="text-[11px] ml-1">
                {summary.totalPnlPct >= 0 ? "+" : ""}
                {summary.totalPnlPct.toFixed(1)}%
              </span>
            )}
          </div>
        </div>
        <div className="border border-border bg-white/[0.015] px-3 py-2">
          <div className="text-[8px] uppercase tracking-widest text-muted-foreground">
            Cost basis
          </div>
          <div className="text-sm font-mono text-white mt-0.5">{fmtUsd(summary?.costBasis)}</div>
        </div>
        <div className="border border-border bg-white/[0.015] px-3 py-2">
          <div className="text-[8px] uppercase tracking-widest text-muted-foreground">
            Realized PnL
          </div>
          <div className={`text-sm font-mono mt-0.5 ${pnlColor(summary?.realizedPnl)}`}>
            {fmtUsd(summary?.realizedPnl)}
          </div>
        </div>
      </div>

      {/* Positions */}
      <div className="shrink-0 text-[9px] uppercase tracking-widest text-muted-foreground mb-1">
        Open positions ({positions.length})
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-1.5">
        {positions.length === 0 ? (
          <div className="text-[10px] text-muted-foreground py-6 text-center">
            No open positions for this wallet.
          </div>
        ) : (
          positions.map((p, i) => (
            <div
              key={i}
              className="border border-border bg-white/[0.015] px-3 py-2 flex items-start gap-2.5"
            >
              {p.icon && (
                <img
                  src={p.icon}
                  alt=""
                  className="w-7 h-7 rounded object-cover shrink-0 mt-0.5"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-[11px] text-white leading-snug line-clamp-2">
                    {p.title}
                  </span>
                  <span className={`text-[12px] font-bold font-mono shrink-0 ${pnlColor(p.cashPnl)}`}>
                    {fmtUsd(p.cashPnl)}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-1 text-[9px] uppercase tracking-wider text-muted-foreground font-mono">
                  <span
                    className={`px-1 py-px border ${
                      (p.outcome ?? "").toLowerCase() === "yes"
                        ? "border-emerald-500/40 text-emerald-300"
                        : "border-red-500/40 text-red-300"
                    }`}
                  >
                    {p.outcome ?? "—"}
                  </span>
                  <span>{p.size?.toFixed(0) ?? "—"} sh</span>
                  <span>·</span>
                  <span>
                    {p.avgPrice !== null && p.avgPrice !== undefined
                      ? `${(p.avgPrice * 100).toFixed(0)}%`
                      : "—"}{" "}
                    →{" "}
                    {p.curPrice !== null && p.curPrice !== undefined
                      ? `${(p.curPrice * 100).toFixed(0)}%`
                      : "—"}
                  </span>
                  {p.percentPnl !== null && p.percentPnl !== undefined && (
                    <span className={pnlColor(p.cashPnl)}>
                      {p.percentPnl >= 0 ? "+" : ""}
                      {p.percentPnl.toFixed(1)}%
                    </span>
                  )}
                  {p.redeemable && (
                    <span className="text-cyan-300 border border-cyan-500/40 px-1 py-px">
                      Redeemable
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="shrink-0 text-[8px] text-muted-foreground mt-2 uppercase tracking-widest font-mono truncate">
        {address}
      </div>
    </div>
  );
}
