import React from "react";
import type { StructuredProductData } from "@workspace/api-client-react";

interface StructuredProductPanelProps {
  data: StructuredProductData;
}

function MetricRow({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex justify-between items-baseline py-1 border-b border-border/40">
      <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</span>
      <div className="text-right">
        <span className="text-xs font-bold font-mono">{value}</span>
        {sub && <span className="text-[10px] text-muted-foreground ml-1">{sub}</span>}
      </div>
    </div>
  );
}

export function StructuredProductPanel({ data }: StructuredProductPanelProps) {
  const barrierBreached = (move: number) => {
    if (data.productType.toLowerCase().includes("down")) {
      return data.spotPrice * (1 + move / 100) <= data.barrier;
    }
    if (data.productType.toLowerCase().includes("up")) {
      return data.spotPrice * (1 + move / 100) >= data.barrier;
    }
    return false;
  };

  const fmt = (n: number) =>
    n >= 0
      ? `+${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
      : n.toLocaleString("en-US", { maximumFractionDigits: 0 });

  return (
    <div className="flex flex-col h-full w-full gap-2">
      {/* Header */}
      <div className="flex justify-between items-baseline shrink-0">
        <div className="flex items-baseline gap-2">
          <span className="text-xl font-bold">{data.symbol}</span>
          <span className="text-xs text-muted-foreground uppercase tracking-wider">
            {data.productType}
          </span>
        </div>
        <div className="text-right">
          <span className="text-xs text-muted-foreground mr-1">Fair Value</span>
          <span className="text-sm font-bold font-mono">
            ${data.fairValue.toLocaleString("en-US", { maximumFractionDigits: 0 })}
          </span>
        </div>
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        {/* Left: pricer inputs + greeks */}
        <div className="w-36 shrink-0 flex flex-col gap-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
            Inputs
          </div>
          <MetricRow label="Spot" value={`$${data.spotPrice.toFixed(2)}`} />
          <MetricRow label="Strike" value={`$${data.strike.toFixed(2)}`} />
          <MetricRow
            label="Barrier"
            value={`$${data.barrier.toFixed(2)}`}
            sub={`${data.barrierPct.toFixed(0)}%`}
          />
          <MetricRow
            label="Tenor"
            value={`${data.tenor >= 1 ? `${data.tenor.toFixed(0)}Y` : `${Math.round(data.tenor * 12)}M`}`}
          />
          <MetricRow
            label="Notional"
            value={`$${(data.notional / 1000).toFixed(0)}K`}
          />
          <MetricRow label="IV" value={`${data.impliedVol.toFixed(1)}%`} />

          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mt-2 mb-1">
            Greeks
          </div>
          <MetricRow
            label="Delta"
            value={`${data.delta >= 0 ? "+" : ""}${data.delta.toFixed(3)}`}
          />
          <MetricRow
            label="Gamma"
            value={data.gamma.toFixed(5)}
          />
          <MetricRow
            label="Vega"
            value={`${data.vega >= 0 ? "+" : ""}${data.vega.toFixed(3)}`}
          />
          <MetricRow
            label="Theta"
            value={`${data.theta >= 0 ? "+" : ""}${data.theta.toFixed(3)}`}
          />
          <MetricRow label="BS Vanilla" value={`$${data.bsPrice.toFixed(2)}`} />
        </div>

        {/* Right: scenario table */}
        <div className="flex-1 overflow-auto min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
            Scenario Analysis
          </div>
          <table className="w-full text-[10px]">
            <thead>
              <tr className="text-muted-foreground uppercase">
                <th className="text-left font-normal pb-1">Move</th>
                <th className="text-right font-normal pb-1">Spot</th>
                <th className="text-right font-normal pb-1">P&L ($)</th>
                <th className="text-right font-normal pb-1">Ret%</th>
                <th className="text-right font-normal pb-1">p̃</th>
              </tr>
            </thead>
            <tbody>
              {data.scenarios.map((s, i) => {
                const knocked = barrierBreached(s.spotMove);
                const positive = s.pnl > 0;
                return (
                  <tr
                    key={i}
                    className={`border-t border-border/40 ${knocked ? "opacity-50" : ""}`}
                  >
                    <td className={`py-0.5 font-bold font-mono ${s.spotMove < 0 ? "text-gray-400" : "text-white"}`}>
                      {s.label}
                    </td>
                    <td className="text-right font-mono text-muted-foreground">
                      ${s.finalSpot.toFixed(1)}
                      {knocked && (
                        <span className="ml-1 text-[8px] text-gray-600 uppercase">KO</span>
                      )}
                    </td>
                    <td
                      className={`text-right font-bold font-mono ${positive ? "text-white" : "text-gray-500"}`}
                    >
                      {fmt(s.pnl)}
                    </td>
                    <td
                      className={`text-right font-mono ${positive ? "text-white" : "text-gray-500"}`}
                    >
                      {s.returnPct >= 0 ? "+" : ""}{s.returnPct.toFixed(1)}%
                    </td>
                    <td className="text-right font-mono text-muted-foreground">
                      {(s.probability * 100).toFixed(0)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* Legend */}
          <div className="mt-2 text-[9px] text-muted-foreground">
            <span className="mr-3">KO = Barrier knocked out (intrinsic → 0)</span>
            <span>p̃ = approx path probability</span>
          </div>
        </div>
      </div>
    </div>
  );
}
