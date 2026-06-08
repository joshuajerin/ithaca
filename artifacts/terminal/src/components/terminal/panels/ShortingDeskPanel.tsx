import React from "react";

interface Holding {
  symbol: string;
  name?: string;
  side: "long" | "short";
  weight: number;
  marketValue: number;
  tier?: string;
  tierLabel?: string;
  feeBps?: number;
  shortable: boolean;
  borrowCostAnnual: number;
  dollarAdv?: number;
  note?: string;
}

interface Carry {
  gcRatePct: number;
  financingRatePct: number;
  rebateRatePct: number;
  cash: number;
  borrowedCash: number;
  idleCash: number;
  borrowCostAnnual: number;
  financingCostAnnual: number;
  cashRebateAnnual: number;
  netCarryAnnual: number;
  dailyCarry: number;
  dragBpsAnnual: number;
}

interface Margin {
  equity: number;
  longMv: number;
  shortMv: number;
  grossMv: number;
  netMv: number;
  grossLeverage: number;
  netLeverage: number;
  initialMargin: number;
  maintenanceMargin: number;
  excessLiquidity: number;
  initialExcess: number;
  marginUtilizationPct: number;
  breach: boolean;
  warnings: string[];
}

interface ShortingDeskData {
  label: string;
  capital: number;
  holdings: Holding[];
  longCount: number;
  shortCount: number;
  carry: Carry;
  margin: Margin;
  financing: { gcRatePct: number; anchor: string; source: string; asOf?: string | null };
  blocked: string[];
  notes: string[];
  assumptions: string;
  source: string;
}

const TIER_TONE: Record<string, string> = {
  gc: "text-emerald-400",
  easy: "text-emerald-300",
  moderate: "text-amber-300",
  htb: "text-orange-400",
  locate: "text-red-400",
};

function usd(n: number | undefined): string {
  const v = Number(n ?? 0);
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[8px] text-muted-foreground uppercase tracking-widest">{label}</span>
      <span className={`font-mono text-[13px] leading-tight ${tone ?? "text-white"}`}>{value}</span>
    </div>
  );
}

export function ShortingDeskPanel({ data }: { data: ShortingDeskData }) {
  const { label, capital, holdings, longCount, shortCount, carry, margin, financing, notes } = data;

  const longs = holdings.filter((h) => h.side === "long");
  const shorts = holdings.filter((h) => h.side === "short");

  const dragTone = carry.dragBpsAnnual > 0 ? "text-red-400" : "text-emerald-400";
  const levTone =
    margin.grossLeverage > 4 ? "text-red-400" : margin.grossLeverage > 2 ? "text-amber-300" : "text-white";
  const liqTone = margin.excessLiquidity < 0 ? "text-red-400" : "text-emerald-400";

  return (
    <div className="flex flex-col h-full gap-2">
      <div className="shrink-0 flex items-start justify-between gap-3">
        <div>
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
            Shorting Desk · {label}
          </div>
          <div className="text-[9px] text-muted-foreground/70 mt-0.5">
            {usd(capital)} equity · {longCount} long / {shortCount} short
          </div>
        </div>
        <div className="text-[8px] uppercase tracking-widest text-right shrink-0">
          {margin.breach ? (
            <span className="text-red-400 font-mono">⚠ MARGIN BREACH</span>
          ) : (
            <span className="text-emerald-400/70">within margin</span>
          )}
          <br />
          <span className="text-muted-foreground">
            GC {financing.gcRatePct.toFixed(2)}% ({financing.source})
          </span>
        </div>
      </div>

      {/* Headline */}
      <div className="grid grid-cols-4 gap-2 shrink-0 border-y border-border/40 py-2">
        <Stat label="Gross Leverage" value={`${margin.grossLeverage.toFixed(2)}×`} tone={levTone} />
        <Stat label="Net Exposure" value={usd(margin.netMv)} />
        <Stat
          label="Carry Drag"
          value={`${carry.dragBpsAnnual > 0 ? "+" : ""}${carry.dragBpsAnnual.toFixed(0)} bps/yr`}
          tone={dragTone}
        />
        <Stat label="Daily Carry" value={usd(carry.dailyCarry)} tone={dragTone} />
        <Stat label="Maint. Margin" value={usd(margin.maintenanceMargin)} />
        <Stat label="Excess Liquidity" value={usd(margin.excessLiquidity)} tone={liqTone} />
        <Stat label="Margin Util." value={`${margin.marginUtilizationPct.toFixed(0)}%`} />
        <Stat label="Borrow Fees" value={`${usd(carry.borrowCostAnnual)}/yr`} tone="text-orange-300" />
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        {/* Borrow book */}
        <div className="flex-[3] min-h-0 flex flex-col">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
            Borrow Book · per-name stock-loan
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto pr-1">
            <table className="w-full text-[10px] font-mono">
              <thead className="text-[8px] text-muted-foreground uppercase tracking-widest sticky top-0 bg-black">
                <tr className="border-b border-border/40">
                  <th className="text-left font-normal py-1">Name</th>
                  <th className="text-right font-normal">Wt</th>
                  <th className="text-right font-normal">MV</th>
                  <th className="text-left font-normal pl-2">Tier</th>
                  <th className="text-right font-normal">Fee</th>
                  <th className="text-right font-normal">$/yr</th>
                </tr>
              </thead>
              <tbody>
                {shorts.map((h) => (
                  <tr key={`s-${h.symbol}`} className="border-b border-border/10">
                    <td className="py-0.5 text-white truncate max-w-[80px]" title={h.name || h.symbol}>
                      {h.symbol}
                    </td>
                    <td className="text-right text-red-400 tabular-nums">{(h.weight * 100).toFixed(1)}%</td>
                    <td className="text-right text-muted-foreground tabular-nums">{usd(h.marketValue)}</td>
                    <td className={`pl-2 ${TIER_TONE[h.tier ?? ""] ?? "text-white"}`}>
                      {h.tierLabel}
                      {!h.shortable && <span className="text-red-400"> ✕</span>}
                    </td>
                    <td className="text-right tabular-nums text-orange-300">
                      {h.feeBps != null ? `${h.feeBps.toFixed(0)}bp` : "—"}
                    </td>
                    <td className="text-right tabular-nums text-orange-300">{usd(h.borrowCostAnnual)}</td>
                  </tr>
                ))}
                {longs.map((h) => (
                  <tr key={`l-${h.symbol}`} className="border-b border-border/10 opacity-70">
                    <td className="py-0.5 text-white truncate max-w-[80px]" title={h.name || h.symbol}>
                      {h.symbol}
                    </td>
                    <td className="text-right text-emerald-400 tabular-nums">+{(h.weight * 100).toFixed(1)}%</td>
                    <td className="text-right text-muted-foreground tabular-nums">{usd(h.marketValue)}</td>
                    <td className="pl-2 text-muted-foreground/60">long</td>
                    <td className="text-right text-muted-foreground/40">—</td>
                    <td className="text-right text-muted-foreground/40">—</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Carry + margin breakdown */}
        <div className="flex-[2] min-h-0 flex flex-col gap-2 overflow-y-auto pr-1">
          <div>
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
              Carrying Cost (annual)
            </div>
            <div className="space-y-0.5 text-[10px] font-mono">
              <Row label="Borrow fees" value={usd(carry.borrowCostAnnual)} tone="text-orange-300" />
              <Row label={`Financing @ ${carry.financingRatePct.toFixed(2)}%`} value={usd(carry.financingCostAnnual)} tone="text-orange-300" />
              <Row label={`Cash rebate @ ${carry.rebateRatePct.toFixed(2)}%`} value={`(${usd(carry.cashRebateAnnual)})`} tone="text-emerald-400" />
              <div className="border-t border-border/40 my-1" />
              <Row label="Net carry" value={usd(carry.netCarryAnnual)} tone={dragTone} bold />
              <Row label="Cash balance" value={usd(carry.cash)} tone={carry.cash < 0 ? "text-amber-300" : "text-muted-foreground"} />
            </div>
          </div>

          <div>
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
              Reg-T Margin
            </div>
            <div className="space-y-0.5 text-[10px] font-mono">
              <Row label="Gross MV" value={usd(margin.grossMv)} />
              <Row label="Initial margin" value={usd(margin.initialMargin)} />
              <Row label="Maintenance margin" value={usd(margin.maintenanceMargin)} />
              <Row label="Excess liquidity" value={usd(margin.excessLiquidity)} tone={liqTone} bold />
            </div>
          </div>
        </div>
      </div>

      {/* Notes / assumptions footer */}
      {(notes.length > 0 || margin.warnings.length > 0) && (
        <div className="shrink-0 border-t border-border/40 pt-1.5 space-y-0.5">
          {[...notes, ...margin.warnings.filter((w) => !notes.includes(w))].slice(0, 3).map((n, i) => (
            <div key={i} className="text-[8px] text-amber-400/80 font-mono leading-tight">
              · {n}
            </div>
          ))}
        </div>
      )}
      <div className="shrink-0 text-[7px] text-muted-foreground/50 leading-tight">{data.assumptions}</div>
    </div>
  );
}

function Row({ label, value, tone, bold }: { label: string; value: string; tone?: string; bold?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground/80">{label}</span>
      <span className={`tabular-nums ${tone ?? "text-white"} ${bold ? "font-semibold" : ""}`}>{value}</span>
    </div>
  );
}
