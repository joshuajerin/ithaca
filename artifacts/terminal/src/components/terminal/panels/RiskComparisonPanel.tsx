import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
  Legend,
} from "recharts";

type RiskModel = {
  portfolioName: string;
  totalVol: number;
  factorVol: number;
  specificVol: number;
  factorVarPct: number;
  specificVarPct: number;
  diversificationRatio: number;
  rSquared: number;
  coverage: {
    included: number;
    excluded: number;
    days: number;
    source: string;
    excludedNames: { symbol: string; reason: string }[];
  };
};

type Metric = {
  label: string;
  key: string;
  a: number;
  b: number;
  diff: number;
  unit: string;
  better: "a" | "b" | "";
};

type FactorRow = {
  factor: string;
  exposureA: number | null;
  exposureB: number | null;
  exposureDiff: number;
  pctRiskA: number | null;
  pctRiskB: number | null;
};

type Tilt = { factor: string; exposure: number };

interface RiskComparisonData {
  a: RiskModel;
  b: RiskModel;
  metrics: Metric[];
  factors: FactorRow[];
  tiltsA: Tilt[];
  tiltsB: Tilt[];
  biggestDivergence: FactorRow[];
  summary: string;
}

const A_COLOR = "#ffffff";
const B_COLOR = "#f59e0b";

export function RiskComparisonPanel({ data }: { data: RiskComparisonData }) {
  const { a, b, metrics, factors, tiltsA, tiltsB, summary } = data;

  const factorData = factors.map((f) => ({
    factor: f.factor,
    [a.portfolioName]: f.exposureA ?? 0,
    [b.portfolioName]: f.exposureB ?? 0,
  }));

  const fmt = (v: number, unit: string) =>
    unit === "x" ? v.toFixed(2) : `${v.toFixed(1)}%`;

  const ExposureTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div className="bg-black border border-white/20 p-2 text-xs space-y-0.5 min-w-[150px]">
          <p className="text-white mb-1">{label}</p>
          {payload.map((p: any) => (
            <p key={p.name} className="flex justify-between gap-3" style={{ color: p.color }}>
              <span className="truncate max-w-[110px]">{p.name}</span>
              <span className="font-mono">{Number(p.value).toFixed(2)}</span>
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Header */}
      <div className="shrink-0 flex items-baseline justify-between">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          Risk Comparison · A vs B
        </div>
        <div className="text-[9px] uppercase tracking-widest font-mono flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2" style={{ background: A_COLOR }} />
            <span className="text-white/80 truncate max-w-[120px]">{a.portfolioName}</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2" style={{ background: B_COLOR }} />
            <span className="text-white/80 truncate max-w-[120px]">{b.portfolioName}</span>
          </span>
        </div>
      </div>

      {/* Summary */}
      <div className="shrink-0 text-[11px] text-white/70 leading-snug border-l-2 border-white/20 pl-2">
        {summary}
      </div>

      {/* Metric comparison cards */}
      <div className="grid grid-cols-3 gap-2 shrink-0">
        {metrics.map((m) => {
          const aWins = m.better === "a";
          const bWins = m.better === "b";
          return (
            <div key={m.key} className="border border-border p-2">
              <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 truncate">
                {m.label}
              </div>
              <div className="flex items-baseline justify-between font-mono">
                <span className={`text-sm font-bold ${aWins ? "text-emerald-400" : "text-white/90"}`}>
                  {fmt(m.a, m.unit)}
                </span>
                <span className="text-[9px] text-muted-foreground mx-1">vs</span>
                <span className={`text-sm font-bold ${bWins ? "text-emerald-400" : "text-amber-400/90"}`}>
                  {fmt(m.b, m.unit)}
                </span>
              </div>
              <div className="text-[9px] font-mono text-muted-foreground mt-0.5">
                Δ {m.diff > 0 ? "+" : ""}
                {m.unit === "x" ? m.diff.toFixed(2) : `${m.diff.toFixed(1)}%`}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        {/* Factor exposure comparison */}
        <div className="flex-[3] flex flex-col min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1 shrink-0">
            Factor Exposures (standardized)
          </div>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={factorData} layout="vertical" margin={{ top: 2, right: 12, left: 8, bottom: 2 }}>
                <CartesianGrid strokeDasharray="2 2" stroke="#222" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="factor" tick={{ fontSize: 9, fill: "#888" }} tickLine={false} axisLine={false} width={64} />
                <Tooltip content={<ExposureTooltip />} cursor={{ fill: "#ffffff08" }} />
                <ReferenceLine x={0} stroke="#444" strokeWidth={1} />
                <Legend wrapperStyle={{ fontSize: 9 }} iconSize={8} />
                <Bar dataKey={a.portfolioName} fill={A_COLOR} fillOpacity={0.8} radius={[0, 2, 2, 0]} />
                <Bar dataKey={b.portfolioName} fill={B_COLOR} fillOpacity={0.8} radius={[0, 2, 2, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Factor vs specific split + dominant tilts */}
        <div className="flex-[2] flex flex-col min-h-0 gap-3">
          <div className="shrink-0">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
              Factor vs Specific Risk
            </div>
            {[a, b].map((p, i) => (
              <div key={i} className="mb-2">
                <div className="flex justify-between text-[9px] text-muted-foreground font-mono mb-0.5">
                  <span className="truncate max-w-[120px]" style={{ color: i === 0 ? A_COLOR : B_COLOR }}>
                    {p.portfolioName}
                  </span>
                  <span>{p.totalVol.toFixed(1)}% vol</span>
                </div>
                <div className="flex h-3 w-full overflow-hidden border border-border">
                  <div
                    className="h-full"
                    style={{ width: `${p.factorVarPct}%`, background: i === 0 ? A_COLOR : B_COLOR, opacity: 0.7 }}
                    title={`Factor ${p.factorVarPct.toFixed(0)}%`}
                  />
                  <div
                    className="h-full"
                    style={{ width: `${p.specificVarPct}%`, background: i === 0 ? A_COLOR : B_COLOR, opacity: 0.2 }}
                    title={`Specific ${p.specificVarPct.toFixed(0)}%`}
                  />
                </div>
                <div className="flex justify-between text-[8px] text-muted-foreground mt-0.5 font-mono">
                  <span>Factor {p.factorVarPct.toFixed(0)}%</span>
                  <span>Specific {p.specificVarPct.toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>

          <div className="flex-1 min-h-0 overflow-auto">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">
              Dominant Tilts
            </div>
            <div className="grid grid-cols-2 gap-2">
              {[
                { name: a.portfolioName, tilts: tiltsA, color: A_COLOR },
                { name: b.portfolioName, tilts: tiltsB, color: B_COLOR },
              ].map((g, gi) => (
                <div key={gi}>
                  <div className="text-[9px] font-mono mb-1 truncate" style={{ color: g.color }}>
                    {g.name}
                  </div>
                  <div className="space-y-1">
                    {g.tilts.map((t) => (
                      <div key={t.factor} className="flex justify-between text-[10px] font-mono">
                        <span className="text-white/70">{t.factor}</span>
                        <span className={t.exposure >= 0 ? "text-white" : "text-red-400"}>
                          {t.exposure >= 0 ? "+" : ""}
                          {t.exposure.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Coverage footer */}
      <div className="shrink-0 flex items-center justify-between text-[9px] text-muted-foreground font-mono border-t border-border/50 pt-1.5">
        <span style={{ color: A_COLOR }}>
          {a.portfolioName}: {a.coverage.included} modeled · {a.coverage.days}d
          {a.coverage.excluded > 0 && (
            <span className="text-red-400/70" title={a.coverage.excludedNames.map((e) => `${e.symbol}: ${e.reason}`).join("\n")}>
              {" "}· {a.coverage.excluded} excl
            </span>
          )}
        </span>
        <span style={{ color: B_COLOR }}>
          {b.portfolioName}: {b.coverage.included} modeled · {b.coverage.days}d
          {b.coverage.excluded > 0 && (
            <span className="text-red-400/70" title={b.coverage.excludedNames.map((e) => `${e.symbol}: ${e.reason}`).join("\n")}>
              {" "}· {b.coverage.excluded} excl
            </span>
          )}
        </span>
      </div>
    </div>
  );
}
