// @ts-nocheck
import React from "react";
import { Loader2 } from "lucide-react";
import type { CorrelationMatrixData } from "@workspace/api-client-react";

function corrColor(v: number): string {
  const clamped = Math.max(-1, Math.min(1, v));
  if (clamped >= 0) {
    const t = clamped;
    const r = Math.round(255 * (1 - t));
    const g = Math.round(255 * (1 - t));
    const b = 255;
    return `rgb(${r},${g},${b})`;
  } else {
    const t = -clamped;
    const r = 255;
    const g = Math.round(255 * (1 - t));
    const b = Math.round(255 * (1 - t));
    return `rgb(${r},${g},${b})`;
  }
}

function textColor(v: number): string {
  return Math.abs(v) > 0.5 ? "#000" : "#fff";
}

interface Props {
  data: CorrelationMatrixData;
  onRefine?: (params: Record<string, unknown>) => void;
  pending?: boolean;
}

export function CorrelationMatrixPanel({ data, onRefine, pending }: Props) {
  const window = data.window as 30 | 90;
  const { symbols, matrix, betas } = data;

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="flex items-center justify-between shrink-0">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          Pairwise Correlations
        </div>
        <div className="flex items-center gap-1">
          {pending && <Loader2 className="w-3 h-3 animate-spin text-muted-foreground mr-1" strokeWidth={1.5} />}
          {([30, 90] as const).map((w) => (
            <button
              key={w}
              disabled={pending}
              onClick={() => {
                if (w !== window) onRefine?.({ symbols, window: w });
              }}
              className={`text-[9px] px-2 py-0.5 border uppercase tracking-widest transition-colors disabled:opacity-50 ${
                window === w
                  ? "border-white text-white bg-white/10"
                  : "border-border text-muted-foreground hover:border-white/40"
              }`}
            >
              {w}D
            </button>
          ))}
        </div>
      </div>

      <div className="relative flex-1 min-h-0 flex flex-col gap-2">
        {pending && (
          <div className="absolute inset-0 z-10 bg-black/50 flex items-center justify-center pointer-events-none">
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" strokeWidth={1.5} />
          </div>
        )}
        <div className="overflow-auto">
          <table className="text-[10px] font-mono border-collapse">
            <thead>
              <tr>
                <th className="w-12 text-left text-muted-foreground font-normal pb-1 pr-2"></th>
                {symbols.map((s) => (
                  <th key={s} className="text-center text-muted-foreground font-normal pb-1 px-0.5 min-w-[36px]">
                    {s}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {symbols.map((rowSym, i) => (
                <tr key={rowSym}>
                  <td className="text-muted-foreground pr-2 py-0.5 text-right">{rowSym}</td>
                  {symbols.map((colSym, j) => {
                    const v = matrix[i][j];
                    return (
                      <td
                        key={colSym}
                        className="text-center py-0.5 px-0.5"
                        style={{
                          backgroundColor: corrColor(v),
                          color: textColor(v),
                          width: 36,
                          height: 28,
                        }}
                      >
                        {i === j ? "1.00" : v.toFixed(2)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="shrink-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Beta & Hedge Ratio</div>
          <div className="overflow-auto">
            <table className="text-[10px] font-mono w-full border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-muted-foreground font-normal pb-1 pr-4">Symbol</th>
                  <th className="text-right text-muted-foreground font-normal pb-1 pr-4">Beta</th>
                  <th className="text-right text-muted-foreground font-normal pb-1">Hedge Ratio</th>
                </tr>
              </thead>
              <tbody>
                {betas.map((row) => (
                  <tr key={row.symbol} className="border-b border-border/30">
                    <td className="py-1 pr-4 text-white font-bold">{row.symbol}</td>
                    <td className="py-1 pr-4 text-right">
                      <span className={row.beta > 1.2 ? "text-white" : row.beta < 0.8 ? "text-muted-foreground" : "text-white/70"}>
                        {row.beta.toFixed(2)}
                      </span>
                    </td>
                    <td className="py-1 text-right text-white/70">{row.hedgeRatio.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
