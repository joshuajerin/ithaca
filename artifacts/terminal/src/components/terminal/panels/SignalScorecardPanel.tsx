import React from "react";
import type { SignalScorecardData, SignalScoreRow } from "@workspace/api-client-react";

interface Props {
  data: SignalScorecardData;
}

function Spark({ values, positive }: { values: number[]; positive: boolean }) {
  if (!values || values.length < 2) {
    return <div className="h-5 w-full" />;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const w = 100;
  const h = 20;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const stroke = positive ? "#4ade80" : "#f87171";
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-5 w-full">
      <polyline points={pts} fill="none" stroke={stroke} strokeWidth={1.25} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function SignalScorecardPanel({ data }: Props) {
  const { universe, universeSize, holding, quantiles, rows } = data;

  const fmtSigned = (v: number, digits = 2) => `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;

  return (
    <div className="flex flex-col h-full gap-2">
      <div className="shrink-0">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          Alpha Signal Scorecard · ranked by IC information ratio
        </div>
        <div className="text-[9px] text-muted-foreground/70 mt-0.5">
          {universe} · {universeSize} names · {holding}d holding · {quantiles} quantiles
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        <table className="text-[10px] font-mono w-full border-collapse">
          <thead className="sticky top-0 bg-black z-10">
            <tr className="border-b border-border">
              <th className="text-left text-muted-foreground font-normal pb-1 pr-2">#</th>
              <th className="text-left text-muted-foreground font-normal pb-1 pr-3">Signal</th>
              <th className="text-right text-muted-foreground font-normal pb-1 pr-3">Mean IC</th>
              <th className="text-right text-muted-foreground font-normal pb-1 pr-3">IC IR</th>
              <th className="text-right text-muted-foreground font-normal pb-1 pr-3">t-Stat</th>
              <th className="text-right text-muted-foreground font-normal pb-1 pr-3">Hit</th>
              <th className="text-right text-muted-foreground font-normal pb-1 pr-3">L/S Ret</th>
              <th className="text-right text-muted-foreground font-normal pb-1 pr-3">Sharpe</th>
              <th className="text-right text-muted-foreground font-normal pb-1 pr-3">Turn</th>
              <th className="text-right text-muted-foreground font-normal pb-1 pr-3">N</th>
              <th className="text-left text-muted-foreground font-normal pb-1 pl-1 w-[80px]">Spread</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row: SignalScoreRow) => {
              const icTone = row.meanIC > 0 ? "text-emerald-400" : row.meanIC < 0 ? "text-red-400" : "text-muted-foreground";
              const retTone = row.spreadReturn > 0 ? "text-emerald-400" : row.spreadReturn < 0 ? "text-red-400" : "text-muted-foreground";
              const tTone = Math.abs(row.tStat) > 2 ? "text-white" : "text-muted-foreground";
              return (
                <tr key={row.signal} className={`border-b border-border/30 ${row.rank === 1 ? "bg-white/[0.04]" : ""}`}>
                  <td className="py-1.5 pr-2 text-muted-foreground">{row.rank}</td>
                  <td className="py-1.5 pr-3 text-white whitespace-nowrap">{row.label}</td>
                  <td className={`py-1.5 pr-3 text-right ${icTone}`}>{row.meanIC.toFixed(3)}</td>
                  <td className="py-1.5 pr-3 text-right text-white">{fmtSigned(row.icIR)}</td>
                  <td className={`py-1.5 pr-3 text-right ${tTone}`}>{fmtSigned(row.tStat)}</td>
                  <td className="py-1.5 pr-3 text-right text-muted-foreground">{row.hitRate.toFixed(0)}%</td>
                  <td className={`py-1.5 pr-3 text-right ${retTone}`}>{fmtSigned(row.spreadReturn, 1)}%</td>
                  <td className="py-1.5 pr-3 text-right text-muted-foreground">{row.spreadSharpe.toFixed(2)}</td>
                  <td className="py-1.5 pr-3 text-right text-muted-foreground">{row.turnover.toFixed(0)}%</td>
                  <td className="py-1.5 pr-3 text-right text-muted-foreground">{row.included}</td>
                  <td className="py-1.5 pl-1">
                    <Spark values={row.spark} positive={row.spreadReturn >= 0} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="shrink-0 border-t border-border/40 pt-1.5 text-[8px] text-muted-foreground uppercase tracking-widest">
        IC IR = mean rank IC / IC volatility · higher is a more consistent signal · |t| &gt; 2 ≈ significant
      </div>
    </div>
  );
}
