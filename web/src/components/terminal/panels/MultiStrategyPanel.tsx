// @ts-nocheck
import React from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

interface SleeveRow {
  id: string;
  name: string;
  stage?: string | null;
  signalLabel?: string;
  capital: number;
  bookValue: number;
  pnl: number;
  pnlPct: number;
  points: number;
  eligible: boolean;
  weight?: number | null;
  vol?: number | null;
  riskContribPct?: number | null;
  current?: number | null;
  recommended?: number | null;
  delta?: number | null;
}
interface Exposure {
  symbol: string;
  marketValue: number;
  weight: number;
}
interface Combined {
  nav: number;
  capital: number;
  pnl: number;
  pnlPct: number;
  grossPct: number;
  exposures: Exposure[];
  exposureCount: number;
  sleeveCount: number;
}
interface Correlation {
  names: string[];
  matrix: number[][];
  days: number;
}
interface Risk {
  combinedVol: number;
  weightedAvgVol: number;
  diversificationBenefit: number;
  diversificationRatio: number;
  concentrationHHI: number;
  effectiveSleeves: number;
  window: number;
}
interface AllocRow {
  name: string;
  stage?: string | null;
  current: number;
  recommended: number;
  delta: number;
  vol?: number | null;
  recRiskContribPct: number;
}
interface Allocation {
  method: string;
  methodLabel: string;
  rows: AllocRow[];
  recommendedVol: number;
  currentVol: number;
  targetVol?: number | null;
  leverage?: number | null;
  investableSleeves: number;
}
interface Excluded {
  name: string;
  reason: string;
}
interface MethodMeta {
  id: string;
  label: string;
}
interface MultiStrategyData {
  sleeves: SleeveRow[];
  combined: Combined | null;
  correlation: Correlation | null;
  risk: Risk | null;
  allocation: Allocation | null;
  excluded: Excluded[];
  firmCurve: { t: string; nav: number }[];
  methods: MethodMeta[];
  method: string;
  methodLabel: string;
  count: number;
  note?: string | null;
  asOf?: string | null;
  source?: string;
}

const STAGE_STYLE: Record<string, string> = {
  paper: "border-amber-700 text-amber-400",
  live: "border-emerald-700 text-emerald-400",
};

function fmtUsd(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${n < 0 ? "-" : ""}$${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${n < 0 ? "-" : ""}$${(abs / 1_000).toFixed(1)}K`;
  return `${n < 0 ? "-" : ""}$${abs.toFixed(0)}`;
}
function pnlColor(n?: number | null): string {
  if (n == null) return "text-muted-foreground";
  return n > 0 ? "text-emerald-400" : n < 0 ? "text-red-400" : "text-white";
}
function deltaColor(n?: number | null): string {
  if (n == null || Math.abs(n) < 0.05) return "text-muted-foreground";
  return n > 0 ? "text-emerald-400" : "text-red-400";
}
function corrColor(v: number): string {
  const clamped = Math.max(-1, Math.min(1, v));
  if (clamped >= 0) {
    const t = clamped;
    const c = Math.round(255 * (1 - t));
    return `rgb(${c},${c},255)`;
  }
  const t = -clamped;
  const c = Math.round(255 * (1 - t));
  return `rgb(255,${c},${c})`;
}
function corrText(v: number): string {
  return Math.abs(v) > 0.5 ? "#000" : "#fff";
}

function StageTag({ stage }: { stage?: string | null }) {
  if (!stage) return null;
  return (
    <span className={`editorial-label text-[8px] border px-1.5 py-0.5 rounded-sm ${STAGE_STYLE[stage] || "border-zinc-600 text-zinc-400"}`}>
      {stage}
    </span>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col">
      <span className="editorial-label text-[7.5px] text-muted-foreground">{label}</span>
      <span className={`font-serif text-[15px] tabular-nums leading-tight ${tone || "text-white"}`}>{value}</span>
    </div>
  );
}

export function MultiStrategyPanel({
  data,
  onRefine,
}: {
  data: MultiStrategyData;
  onRefine?: (params: Record<string, unknown>) => void;
}) {
  const sleeves = data.sleeves || [];

  if (sleeves.length === 0) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center text-center gap-2 text-muted-foreground">
        <span className="font-serif text-base text-white">No sleeves to allocate</span>
        <span className="editorial-label text-[9px] max-w-[300px]">
          {data.note || "Create and paper-trade a few strategies, then allocate capital across them as sleeves."}
        </span>
      </div>
    );
  }

  const combined = data.combined;
  const risk = data.risk;
  const alloc = data.allocation;
  const corr = data.correlation;
  const curve = (data.firmCurve || []).map((p) => ({ t: p.t, nav: p.nav }));
  const curveUp = curve.length > 1 && curve[curve.length - 1].nav >= curve[0].nav;
  const stroke = curveUp ? "#34d399" : "#f87171";

  return (
    <div className="w-full h-full flex gap-4 overflow-hidden text-white">
      {/* Left: firm book + sleeves + allocation */}
      <div className="flex flex-col min-w-0 flex-1 overflow-hidden">
        <div className="flex items-center justify-between mb-2 shrink-0">
          <span className="editorial-label text-[8.5px] text-muted-foreground">
            Firm Book · {data.count} sleeve{data.count === 1 ? "" : "s"}
          </span>
          <div className="flex gap-1">
            {(data.methods || []).map((m) => (
              <button
                key={m.id}
                onClick={() => {
                  if (m.id !== data.method) onRefine?.({ method: m.id });
                }}
                className={`editorial-label text-[8px] px-2 py-0.5 border rounded-sm transition-colors ${
                  data.method === m.id
                    ? "border-white text-white bg-white/10"
                    : "border-border text-muted-foreground hover:border-white/40"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {combined && (
          <div className="grid grid-cols-4 gap-2 mb-3 shrink-0">
            <Metric label="Combined NAV" value={fmtUsd(combined.nav)} />
            <Metric label="P&L" value={`${combined.pnl > 0 ? "+" : ""}${combined.pnlPct.toFixed(2)}%`} tone={pnlColor(combined.pnlPct)} />
            <Metric label="Gross" value={`${combined.grossPct.toFixed(0)}%`} />
            <Metric label="Combined Vol" value={risk ? `${risk.combinedVol.toFixed(1)}%` : "—"} />
          </div>
        )}

        {curve.length > 1 && (
          <div className="h-[90px] mb-3 shrink-0">
            <div className="editorial-label text-[8px] text-muted-foreground mb-1">Combined NAV (real snapshots)</div>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={curve} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="firmGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                <XAxis dataKey="t" hide />
                <YAxis hide domain={["dataMin", "dataMax"]} />
                <Tooltip
                  contentStyle={{ background: "#0a0a0a", border: "1px solid #222", fontSize: 11 }}
                  labelStyle={{ color: "#888" }}
                  formatter={(v: number) => [fmtUsd(v), "NAV"]}
                />
                <Area type="monotone" dataKey="nav" stroke={stroke} strokeWidth={1.5} fill="url(#firmGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="overflow-y-auto flex-1 -mx-1 min-h-0">
          <div className="editorial-label text-[8px] text-muted-foreground mb-1 px-1">
            Capital Allocation{alloc ? ` · ${alloc.methodLabel}` : ""}
          </div>
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-muted-foreground editorial-label text-[8px] border-b border-border">
                <th className="text-left font-normal py-1.5 px-1">Sleeve</th>
                <th className="text-right font-normal py-1.5 px-1">Vol</th>
                <th className="text-right font-normal py-1.5 px-1">Risk%</th>
                <th className="text-right font-normal py-1.5 px-1">Current</th>
                <th className="text-right font-normal py-1.5 px-1">Target</th>
                <th className="text-right font-normal py-1.5 px-1">Δ</th>
              </tr>
            </thead>
            <tbody>
              {sleeves.map((r) => (
                <tr key={r.id} className={`border-b border-border/40 ${r.eligible ? "" : "opacity-50"}`}>
                  <td className="py-1.5 px-1">
                    <div className="flex items-center gap-1.5">
                      <span className="font-serif text-[13px] leading-tight truncate">{r.name}</span>
                      <StageTag stage={r.stage} />
                    </div>
                    <div className="editorial-label text-[7.5px] text-muted-foreground">
                      {r.eligible ? `${fmtUsd(r.bookValue)} · ${r.points}d` : `${r.points}d history — held out`}
                    </div>
                  </td>
                  <td className="py-1.5 px-1 text-right tabular-nums text-[11px] text-muted-foreground">
                    {r.vol != null ? `${r.vol.toFixed(1)}%` : "—"}
                  </td>
                  <td className="py-1.5 px-1 text-right tabular-nums text-[11px] text-muted-foreground">
                    {r.riskContribPct != null ? `${r.riskContribPct.toFixed(0)}%` : "—"}
                  </td>
                  <td className="py-1.5 px-1 text-right tabular-nums text-[11px]">
                    {r.current != null ? `${r.current.toFixed(1)}%` : "—"}
                  </td>
                  <td className="py-1.5 px-1 text-right tabular-nums text-[11px] text-white">
                    {r.recommended != null ? `${r.recommended.toFixed(1)}%` : "—"}
                  </td>
                  <td className={`py-1.5 px-1 text-right tabular-nums text-[11px] ${deltaColor(r.delta)}`}>
                    {r.delta != null ? `${r.delta > 0 ? "+" : ""}${r.delta.toFixed(1)}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {data.excluded && data.excluded.length > 0 && (
            <div className="mt-2 px-1">
              <div className="editorial-label text-[7.5px] text-muted-foreground mb-1">Held out (insufficient history)</div>
              {data.excluded.map((e, i) => (
                <div key={i} className="text-[9px] text-muted-foreground leading-snug">
                  <span className="text-amber-400/80">{e.name}</span> — {e.reason}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right: firm risk + correlation */}
      <div className="w-[44%] max-w-[400px] shrink-0 flex flex-col overflow-hidden border-l border-border pl-4">
        {risk ? (
          <>
            <div className="editorial-label text-[8px] text-muted-foreground mb-2 shrink-0">Firm-Level Risk</div>
            <div className="grid grid-cols-2 gap-2 mb-3 shrink-0">
              <Metric label="Combined Vol" value={`${risk.combinedVol.toFixed(2)}%`} />
              <Metric label="Σ Standalone Vol" value={`${risk.weightedAvgVol.toFixed(2)}%`} />
              <Metric
                label="Diversification Benefit"
                value={`${risk.diversificationBenefit > 0 ? "-" : ""}${Math.abs(risk.diversificationBenefit).toFixed(2)}%`}
                tone="text-emerald-400"
              />
              <Metric label="Diversification Ratio" value={`${risk.diversificationRatio.toFixed(2)}×`} />
              <Metric label="Concentration (HHI)" value={risk.concentrationHHI.toFixed(3)} />
              <Metric label="Effective Sleeves" value={`${risk.effectiveSleeves.toFixed(2)}`} />
            </div>

            {alloc && (
              <div className="mb-3 rounded-sm border border-border/60 bg-white/[0.02] px-2 py-1.5 shrink-0">
                <div className="flex items-center justify-between">
                  <span className="editorial-label text-[8px] text-muted-foreground">{alloc.methodLabel} → firm vol</span>
                  <span className="tabular-nums text-[11px]">
                    {alloc.currentVol.toFixed(1)}% <span className="text-muted-foreground">→</span>{" "}
                    <span className="text-white">{alloc.recommendedVol.toFixed(1)}%</span>
                  </span>
                </div>
                {alloc.targetVol != null && (
                  <div className="flex items-center justify-between mt-1">
                    <span className="editorial-label text-[8px] text-muted-foreground">Target vol budget</span>
                    <span className="tabular-nums text-[11px]">{alloc.targetVol.toFixed(1)}%</span>
                  </div>
                )}
                {alloc.leverage != null && (
                  <div className="flex items-center justify-between mt-1">
                    <span className="editorial-label text-[8px] text-muted-foreground">Implied gross leverage</span>
                    <span className="tabular-nums text-[11px]">{alloc.leverage.toFixed(2)}×</span>
                  </div>
                )}
              </div>
            )}

            {corr && corr.names.length >= 2 && (
              <div className="flex-1 overflow-auto min-h-0">
                <div className="editorial-label text-[8px] text-muted-foreground mb-1">
                  Cross-Strategy Correlation · {corr.days}d
                </div>
                <table className="text-[9px] font-mono border-collapse">
                  <thead>
                    <tr>
                      <th className="w-16"></th>
                      {corr.names.map((n, j) => (
                        <th key={j} className="text-center text-muted-foreground font-normal pb-1 px-0.5 min-w-[34px]">
                          {n.length > 5 ? n.slice(0, 5) : n}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {corr.names.map((rowName, i) => (
                      <tr key={i}>
                        <td className="text-muted-foreground pr-2 py-0.5 text-right truncate max-w-16">{rowName}</td>
                        {corr.names.map((_, j) => {
                          const v = corr.matrix[i][j];
                          return (
                            <td
                              key={j}
                              className="text-center py-0.5 px-0.5"
                              style={{ backgroundColor: corrColor(v), color: corrText(v), width: 34, height: 26 }}
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
            )}
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center gap-2 text-muted-foreground">
            <span className="font-serif text-sm text-white">Risk pending more history</span>
            <span className="editorial-label text-[8.5px] max-w-[240px]">
              {data.note || "Sleeves need more audited NAV snapshots before cross-strategy risk can be measured."}
            </span>
          </div>
        )}

        <div className="mt-3 pt-2 border-t border-border/40 shrink-0">
          <span className="editorial-label text-[7.5px] text-muted-foreground">
            Recommendation only — capital is not moved. Switch method above to re-allocate.
          </span>
        </div>
      </div>
    </div>
  );
}
