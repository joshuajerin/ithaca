// @ts-nocheck
import React from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
  Legend,
} from "recharts";

interface FactorSummary {
  factor: string;
  cumReturn: number;
  annReturn: number;
  annVol: number;
  sharpe: number;
  tStat: number;
}

interface ExcludedName {
  symbol: string;
  reason: string;
}

interface Coverage {
  included: number;
  excluded: number;
  excludedNames: ExcludedName[];
  days: number;
  source: string;
  pcaVarExplained: number[];
}

interface FactorPerformanceData {
  portfolioName: string;
  factorNames: string[];
  series: Array<Record<string, number | string>>;
  factors: FactorSummary[];
  windowDays: number;
  coverage: Coverage;
}

const FACTOR_COLORS: Record<string, string> = {
  Market: "#9ca3af",
  Size: "#38bdf8",
  Value: "#4ade80",
  Momentum: "#f59e0b",
  Volatility: "#f472b6",
  Quality: "#a78bfa",
};

function colorFor(factor: string, i: number): string {
  return FACTOR_COLORS[factor] ?? ["#60a5fa", "#34d399", "#fbbf24", "#f87171", "#c084fc", "#94a3b8"][i % 6];
}

export function FactorPerformancePanel({ data }: { data: FactorPerformanceData }) {
  const { portfolioName, factorNames, series, factors, windowDays, coverage } = data;

  const fmtDate = (d: string) => (typeof d === "string" && d.length >= 10 ? d.slice(5) : d);

  const PerfTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      const rows = [...payload].sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
      return (
        <div className="bg-black border border-white/20 p-2 text-xs space-y-0.5 min-w-[150px]">
          <p className="text-white mb-1 font-mono">{label}</p>
          {rows.map((p: any) => (
            <p key={p.dataKey} className="flex justify-between gap-3">
              <span style={{ color: p.color }}>{p.dataKey}</span>
              <span className="font-mono" style={{ color: p.color }}>
                {p.value > 0 ? "+" : ""}
                {Number(p.value).toFixed(1)}%
              </span>
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="shrink-0">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          Factor Performance · cumulative return over the estimation window
        </div>
      </div>

      {/* Cumulative factor-return lines */}
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="#1d1d1d" />
            <XAxis
              dataKey="date"
              tickFormatter={fmtDate}
              tick={{ fontSize: 9, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              minTickGap={32}
            />
            <YAxis
              tick={{ fontSize: 9, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              width={36}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip content={<PerfTooltip />} cursor={{ stroke: "#ffffff22" }} />
            <ReferenceLine y={0} stroke="#444" strokeWidth={1} />
            <Legend
              wrapperStyle={{ fontSize: 9 }}
              iconType="plainline"
              iconSize={10}
            />
            {factorNames.map((fn, i) => (
              <Line
                key={fn}
                type="monotone"
                dataKey={fn}
                stroke={colorFor(fn, i)}
                strokeWidth={fn === "Market" ? 1 : 1.5}
                strokeDasharray={fn === "Market" ? "4 3" : undefined}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Per-factor summary table */}
      <div className="shrink-0">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
          Factor Premia ({windowDays}d)
        </div>
        <div className="overflow-auto" style={{ maxHeight: "42%" }}>
          <table className="text-[10px] font-mono w-full border-collapse">
            <thead>
              <tr className="border-b border-border sticky top-0 bg-background">
                <th className="text-left text-muted-foreground font-normal pb-1 pr-2">Factor</th>
                <th className="text-right text-muted-foreground font-normal pb-1 pr-2">Cum</th>
                <th className="text-right text-muted-foreground font-normal pb-1 pr-2">Ann</th>
                <th className="text-right text-muted-foreground font-normal pb-1 pr-2">Vol</th>
                <th className="text-right text-muted-foreground font-normal pb-1 pr-2">Sharpe</th>
                <th className="text-right text-muted-foreground font-normal pb-1">t</th>
              </tr>
            </thead>
            <tbody>
              {factors.map((f, i) => {
                const sig = Math.abs(f.tStat) > 2;
                return (
                  <tr key={f.factor} className="border-b border-border/30">
                    <td className="py-1 pr-2">
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className="inline-block w-2 h-2 rounded-full"
                          style={{ backgroundColor: colorFor(f.factor, i) }}
                        />
                        <span className="text-muted-foreground">{f.factor}</span>
                      </span>
                    </td>
                    <td className={`py-1 pr-2 text-right ${f.cumReturn >= 0 ? "text-white" : "text-red-400"}`}>
                      {f.cumReturn > 0 ? "+" : ""}
                      {f.cumReturn.toFixed(1)}%
                    </td>
                    <td className={`py-1 pr-2 text-right ${f.annReturn >= 0 ? "text-white/80" : "text-red-400/80"}`}>
                      {f.annReturn > 0 ? "+" : ""}
                      {f.annReturn.toFixed(1)}%
                    </td>
                    <td className="py-1 pr-2 text-right text-muted-foreground">{f.annVol.toFixed(1)}%</td>
                    <td className={`py-1 pr-2 text-right ${f.sharpe >= 0 ? "text-white/80" : "text-red-400/80"}`}>
                      {f.sharpe.toFixed(2)}
                    </td>
                    <td className={`py-1 text-right ${sig ? "text-white" : "text-muted-foreground"}`}>
                      {f.tStat.toFixed(1)}
                      {sig ? " ✓" : ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="shrink-0 flex items-center justify-between text-[9px] text-muted-foreground font-mono border-t border-border/50 pt-1.5">
        <span>
          {coverage.included} names · {coverage.days}d window · {coverage.source}
        </span>
        {coverage.excluded > 0 && (
          <span
            className="text-red-400/70"
            title={coverage.excludedNames.map((e) => `${e.symbol}: ${e.reason}`).join("\n")}
          >
            {coverage.excluded} excluded
          </span>
        )}
      </div>
    </div>
  );
}
