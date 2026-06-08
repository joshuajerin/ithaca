import React from "react";

interface OrderRow {
  symbol: string;
  side: string;
  shares: number;
  notional: number;
  price: number;
  currentWeight?: number | null;
  targetWeight?: number | null;
  deltaWeight?: number | null;
  expectedCostSupported: boolean;
  expectedImpactBps: number;
  expectedCostUsd: number;
  realizedSupported: boolean;
  realizedAllInBps?: number | null;
  realizedCostUsd?: number | null;
  realizedReason?: string | null;
}
interface CostBlock {
  costUsd?: number | null;
  costBps?: number | null;
  supportedCount?: number;
  unsupportedCount?: number;
  asOf?: string | null;
  interval?: string;
  intervalLabel?: string;
  chosenAlgo?: string;
}
interface RebalancePlanData {
  status: string;
  applied: boolean;
  message?: string;
  strategyName?: string;
  stage?: string;
  signalLabel?: string;
  established?: boolean;
  hasTrades?: boolean;
  tradeCount?: number;
  bookValue?: number | null;
  navBefore?: number | null;
  navAfter?: number | null;
  cash?: number | null;
  turnoverPct?: number | null;
  tradedNotional?: number | null;
  expected?: CostBlock;
  realized?: CostBlock;
  orders?: OrderRow[];
  excluded?: { symbol: string; reason: string }[] | null;
  universeLabel?: string | null;
  model?: { name?: string; formula?: string; coef?: number; note?: string } | null;
}

function fmtUsd(n?: number | null): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${n < 0 ? "-" : ""}$${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${n < 0 ? "-" : ""}$${(abs / 1_000).toFixed(1)}K`;
  return `${n < 0 ? "-" : ""}$${abs.toFixed(0)}`;
}
function fmtPct(n?: number | null, digits = 1): string {
  if (n == null) return "—";
  return `${n.toFixed(digits)}%`;
}
function sideColor(side: string): string {
  return side === "buy" ? "text-emerald-400" : "text-red-400";
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col">
      <span className="editorial-label text-[7.5px] text-muted-foreground">{label}</span>
      <span className={`font-serif text-[15px] tabular-nums leading-tight ${tone || "text-white"}`}>{value}</span>
    </div>
  );
}

export function RebalancePlanPanel({ data }: { data: RebalancePlanData }) {
  if (!data || data.status === "empty") {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center text-center gap-2 text-muted-foreground">
        <span className="font-serif text-base text-white">No strategy to rebalance</span>
        <span className="editorial-label text-[9px] max-w-[280px]">
          {data?.message || 'Create a strategy first (e.g. "create a momentum strategy"), then ask to rebalance it.'}
        </span>
      </div>
    );
  }

  const orders = data.orders || [];
  const exp = data.expected || {};
  const real = data.realized || {};

  if (!data.hasTrades) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center text-center gap-2 text-muted-foreground">
        <span className="font-serif text-base text-white">{data.strategyName} is on target</span>
        <span className="editorial-label text-[9px] max-w-[280px]">
          The book already matches its latest {data.signalLabel || "signal"} targets — no trades needed.
        </span>
      </div>
    );
  }

  return (
    <div className="w-full h-full flex flex-col gap-3 overflow-hidden text-white">
      {/* Header */}
      <div className="flex items-start justify-between gap-2 shrink-0">
        <div className="min-w-0">
          <div className="font-serif text-lg leading-tight truncate">{data.strategyName}</div>
          <div className="editorial-label text-[8px] text-muted-foreground truncate">
            {data.signalLabel}
            {data.universeLabel ? ` · ${data.universeLabel}` : ""}
            {data.established ? " · initial build" : ""}
          </div>
        </div>
        <span
          className={`editorial-label text-[8px] border px-1.5 py-0.5 rounded-sm ${
            data.applied
              ? "border-emerald-700 text-emerald-400"
              : "border-amber-700 text-amber-400"
          }`}
        >
          {data.applied ? "applied" : "preview"}
        </span>
      </div>

      {/* Summary metrics */}
      <div className="grid grid-cols-4 gap-2 shrink-0">
        <Metric label="Trades" value={`${data.tradeCount ?? orders.length}`} />
        <Metric label="Turnover" value={fmtPct(data.turnoverPct)} />
        <Metric label="Est. Cost" value={fmtUsd(exp.costUsd)} tone="text-amber-400" />
        <Metric label="Cost (bps)" value={exp.costBps != null ? exp.costBps.toFixed(1) : "—"} />
        <Metric label="NAV Before" value={fmtUsd(data.navBefore)} />
        <Metric
          label="NAV After"
          value={fmtUsd(data.navAfter)}
          tone={data.applied ? "text-white" : "text-muted-foreground"}
        />
        <Metric label="Traded" value={fmtUsd(data.tradedNotional)} />
        <Metric
          label="Realized Cost"
          value={fmtUsd(real.costUsd)}
          tone={real.supportedCount ? "text-amber-400" : "text-muted-foreground"}
        />
      </div>

      {/* Cost-coverage note */}
      <div className="shrink-0 rounded-sm border border-border/60 bg-white/[0.02] px-2 py-1.5">
        <span className="editorial-label text-[7.5px] text-muted-foreground leading-snug">
          Expected cost = modeled square-root impact (ADV + daily vol).
          {real.supportedCount
            ? ` Realized = intraday execution sim on ${real.supportedCount}/${orders.length} names${
                real.intervalLabel ? ` (${real.intervalLabel}` : ""
              }${real.chosenAlgo ? `, ${real.chosenAlgo.toUpperCase()})` : real.intervalLabel ? ")" : ""}.`
            : " No real intraday data for these names — realized cost is flagged, not faked."}
          {exp.unsupportedCount
            ? ` ${exp.unsupportedCount} name${exp.unsupportedCount > 1 ? "s" : ""} lack real ADV/vol (flagged).`
            : ""}
        </span>
      </div>

      {/* Trade list */}
      <div className="flex-1 overflow-y-auto -mx-1 min-h-0">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 bg-background">
            <tr className="text-muted-foreground editorial-label text-[8px] border-b border-border">
              <th className="text-left font-normal py-1.5 px-1">Trade</th>
              <th className="text-right font-normal py-1.5 px-1">Shares</th>
              <th className="text-right font-normal py-1.5 px-1">Notional</th>
              <th className="text-right font-normal py-1.5 px-1">Cur→Tgt</th>
              <th className="text-right font-normal py-1.5 px-1">Exp bps</th>
              <th className="text-right font-normal py-1.5 px-1">Exp $</th>
              <th className="text-right font-normal py-1.5 px-1">Real $</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.symbol} className="border-b border-border/40">
                <td className="py-1.5 px-1">
                  <div className="flex items-center gap-1.5">
                    <span className={`editorial-label text-[8px] uppercase ${sideColor(o.side)}`}>{o.side}</span>
                    <span className="font-serif text-[12px] leading-tight">{o.symbol}</span>
                  </div>
                  <div className="editorial-label text-[7px] text-muted-foreground">@ {fmtUsd(o.price)}</div>
                </td>
                <td className="py-1.5 px-1 text-right tabular-nums text-[11px]">
                  {Math.round(o.shares).toLocaleString()}
                </td>
                <td className="py-1.5 px-1 text-right tabular-nums text-[11px]">{fmtUsd(o.notional)}</td>
                <td className="py-1.5 px-1 text-right tabular-nums text-[10px] text-muted-foreground">
                  {o.currentWeight != null ? `${o.currentWeight.toFixed(1)}` : "0"}→
                  {o.targetWeight != null ? `${o.targetWeight.toFixed(1)}%` : "0%"}
                </td>
                <td className="py-1.5 px-1 text-right tabular-nums text-[11px]">
                  {o.expectedCostSupported ? o.expectedImpactBps.toFixed(1) : <span className="text-muted-foreground">n/a</span>}
                </td>
                <td className="py-1.5 px-1 text-right tabular-nums text-[11px] text-amber-400">
                  {o.expectedCostSupported ? fmtUsd(o.expectedCostUsd) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="py-1.5 px-1 text-right tabular-nums text-[11px]">
                  {o.realizedSupported ? (
                    <span className="text-amber-400">{fmtUsd(o.realizedCostUsd)}</span>
                  ) : (
                    <span className="editorial-label text-[7px] text-muted-foreground" title={o.realizedReason || ""}>
                      no data
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer hint */}
      <div className="shrink-0 pt-1 border-t border-border/40">
        <span className="editorial-label text-[7.5px] text-muted-foreground">
          {data.applied
            ? `Applied to ${data.strategyName}'s paper book — modeled cost debited from cash.`
            : `Preview only. Say "apply" or "rebalance ${data.strategyName}" to execute these trades.`}
        </span>
      </div>
    </div>
  );
}
