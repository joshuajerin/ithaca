import React from "react";
import {
  priceStructuredProduct,
  productTypeFromLabel,
  type PricerInputs,
} from "@/lib/structuredProductPricer";

interface StructuredProductPanelProps {
  data: any;
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

function InputRow({
  label,
  value,
  suffix,
  step,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  suffix?: string;
  step?: number;
  min?: number;
  max?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex justify-between items-center py-1 border-b border-border/40">
      <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</span>
      <div className="flex items-baseline gap-0.5">
        <input
          type="number"
          value={Number.isFinite(value) ? value : ""}
          step={step}
          min={min}
          max={max}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="w-16 bg-transparent border border-border/60 rounded px-1 py-0.5 text-right text-xs font-bold font-mono focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
        {suffix && <span className="text-[10px] text-muted-foreground w-3">{suffix}</span>}
      </div>
    </div>
  );
}

export function StructuredProductPanel({ data }: StructuredProductPanelProps) {
  const S: number = data.spotPrice;
  const baseIv: number = data.impliedVol / 100;
  const productType = productTypeFromLabel(data.productType);

  const defaults: PricerInputs = React.useMemo(
    () => ({
      barrierPct: data.barrierPct,
      tenorMonths: Math.round(data.tenor * 12),
      notional: data.notional,
      strikePct: Math.round((data.strike / S) * 100),
    }),
    [data.barrierPct, data.tenor, data.notional, data.strike, S],
  );

  const [inputs, setInputs] = React.useState<PricerInputs>(defaults);

  React.useEffect(() => {
    setInputs(defaults);
  }, [defaults]);

  const setField = (field: keyof PricerInputs) => (v: number) =>
    setInputs((prev) => ({ ...prev, [field]: v }));

  const dirty =
    inputs.barrierPct !== defaults.barrierPct ||
    inputs.tenorMonths !== defaults.tenorMonths ||
    inputs.notional !== defaults.notional ||
    inputs.strikePct !== defaults.strikePct;

  const valid =
    Number.isFinite(inputs.barrierPct) &&
    Number.isFinite(inputs.tenorMonths) &&
    inputs.tenorMonths > 0 &&
    Number.isFinite(inputs.notional) &&
    inputs.notional > 0 &&
    Number.isFinite(inputs.strikePct) &&
    inputs.strikePct > 0 &&
    inputs.barrierPct > 0;

  const priced = React.useMemo(() => {
    if (!valid) return null;
    return priceStructuredProduct(S, baseIv, productType, inputs);
  }, [S, baseIv, productType, inputs, valid]);

  // Use freshly computed values when valid; otherwise fall back to server data.
  const view = priced ?? {
    barrier: data.barrier,
    barrierPct: data.barrierPct,
    tenor: data.tenor,
    notional: data.notional,
    strike: data.strike,
    bsPrice: data.bsPrice,
    fairValue: data.fairValue,
    delta: data.delta,
    gamma: data.gamma,
    vega: data.vega,
    theta: data.theta,
    scenarios: data.scenarios,
  };

  const barrierBreached = (move: number) => {
    if (productType.includes("down")) {
      return S * (1 + move / 100) <= view.barrier;
    }
    if (productType.includes("up")) {
      return S * (1 + move / 100) >= view.barrier;
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
        <div className="flex items-baseline gap-3">
          {dirty && (
            <button
              type="button"
              onClick={() => setInputs(defaults)}
              className="text-[9px] text-muted-foreground uppercase tracking-wider border border-border/60 rounded px-1.5 py-0.5 hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              Reset
            </button>
          )}
          <div className="text-right">
            <span className="text-xs text-muted-foreground mr-1">Fair Value</span>
            <span className="text-sm font-bold font-mono">
              ${view.fairValue.toLocaleString("en-US", { maximumFractionDigits: 0 })}
            </span>
          </div>
        </div>
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        {/* Left: pricer inputs + greeks */}
        <div className="w-40 shrink-0 flex flex-col gap-0 overflow-auto min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
            Inputs
          </div>
          <MetricRow label="Spot" value={`$${S.toFixed(2)}`} />
          <InputRow
            label="Strike"
            value={inputs.strikePct}
            suffix="%"
            step={1}
            min={1}
            onChange={setField("strikePct")}
          />
          <InputRow
            label="Barrier"
            value={inputs.barrierPct}
            suffix="%"
            step={1}
            min={1}
            onChange={setField("barrierPct")}
          />
          <InputRow
            label="Tenor"
            value={inputs.tenorMonths}
            suffix="M"
            step={1}
            min={1}
            onChange={setField("tenorMonths")}
          />
          <InputRow
            label="Notional"
            value={inputs.notional}
            step={10000}
            min={0}
            onChange={setField("notional")}
          />
          <MetricRow label="IV" value={`${data.impliedVol.toFixed(1)}%`} />
          <MetricRow label="Strike $" value={`$${view.strike.toFixed(2)}`} />
          <MetricRow label="Barrier $" value={`$${view.barrier.toFixed(2)}`} />

          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mt-2 mb-1">
            Greeks
          </div>
          <MetricRow
            label="Delta"
            value={`${view.delta >= 0 ? "+" : ""}${view.delta.toFixed(3)}`}
          />
          <MetricRow label="Gamma" value={view.gamma.toFixed(5)} />
          <MetricRow
            label="Vega"
            value={`${view.vega >= 0 ? "+" : ""}${view.vega.toFixed(3)}`}
          />
          <MetricRow
            label="Theta"
            value={`${view.theta >= 0 ? "+" : ""}${view.theta.toFixed(3)}`}
          />
          <MetricRow label="BS Vanilla" value={`$${view.bsPrice.toFixed(2)}`} />
        </div>

        {/* Right: scenario table */}
        <div className="flex-1 overflow-auto min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
            Scenario Analysis
          </div>
          {!valid && (
            <div className="text-[10px] text-amber-500 mb-1">
              Enter positive values for barrier, tenor, notional and strike to re-price.
            </div>
          )}
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
              {view.scenarios.map((s: any, i: number) => {
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
