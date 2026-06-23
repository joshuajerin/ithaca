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
  ReferenceLine,
} from "recharts";

interface RosterRow {
  id: string;
  name: string;
  signal?: string | null;
  signalLabel: string;
  stage: string;
  positions: number;
  grossPct: number;
  pnl: number;
  pnlPct: number;
  sharpe?: number | null;
  maxDD?: number | null;
  ageDays: number;
  bookValue: number;
}
interface Mark {
  symbol: string;
  shares: number;
  entryPrice: number;
  price: number;
  marketValue: number;
  costBasis?: number;
  pnl: number;
  pnlPct: number;
  priced?: boolean;
}
interface Exposure {
  symbol: string;
  weight: number;
}
interface NavPoint {
  t: string;
  nav: number;
  pnlPct: number;
}
interface Check {
  label: string;
  pass: boolean;
  detail: string;
}
interface Detail {
  id: string;
  name: string;
  signalLabel: string;
  stage: string;
  capital: number;
  cash: number;
  bookValue: number;
  pnl: number;
  pnlPct: number;
  grossPct: number;
  ageDays: number;
  inceptionDate?: string | null;
  universe?: string | null;
  marks: Mark[];
  exposures: Exposure[];
  navCurve: NavPoint[];
  stats: { sharpe?: number | null; maxDD?: number | null; annVolPct?: number | null; cagrPct?: number | null };
  promotionCriteria?: Record<string, number> | null;
  promotion?: { pass: boolean; checks: Check[] } | null;
  stageHistory?: { stage: string; at: string }[] | null;
  lastRebalance?: {
    at?: string | null;
    trades?: number | null;
    turnoverPct?: number | null;
    costUsd?: number | null;
    costBps?: number | null;
  } | null;
}
interface StrategyDeskData {
  strategies: RosterRow[];
  selected?: Detail | null;
  stages: string[];
  count: number;
  asOf?: string | null;
  source?: string;
}

const STAGE_STYLE: Record<string, string> = {
  research: "border-zinc-600 text-zinc-400",
  backtest: "border-sky-700 text-sky-400",
  paper: "border-amber-700 text-amber-400",
  live: "border-emerald-700 text-emerald-400",
  retired: "border-zinc-800 text-zinc-600",
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
function weightFor(detail: Detail, symbol: string): number | null {
  const e = (detail.exposures || []).find((x) => x.symbol === symbol);
  return e ? e.weight : null;
}
function StageTag({ stage }: { stage: string }) {
  return (
    <span className={`editorial-label text-[8px] border px-1.5 py-0.5 rounded-sm ${STAGE_STYLE[stage] || STAGE_STYLE.research}`}>
      {stage}
    </span>
  );
}

export function StrategyDeskPanel({ data }: { data: StrategyDeskData }) {
  const rows = data.strategies || [];
  const detail = data.selected ?? null;

  if (rows.length === 0) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center text-center gap-2 text-muted-foreground">
        <span className="font-serif text-base text-white">No strategies yet</span>
        <span className="editorial-label text-[9px] max-w-[260px]">
          Say "create a momentum strategy" or "paper-trade the value strategy" to populate the desk.
        </span>
      </div>
    );
  }

  const selId = detail?.id;
  const curve = (detail?.navCurve || []).map((p) => ({ t: p.t, pnlPct: p.pnlPct, nav: p.nav }));
  const curveUp = curve.length > 0 && curve[curve.length - 1].pnlPct >= 0;
  const stroke = curveUp ? "#34d399" : "#f87171";

  return (
    <div className="w-full h-full flex gap-4 overflow-hidden text-white">
      {/* Roster */}
      <div className="flex flex-col min-w-0 flex-1 overflow-hidden">
        <div className="flex items-baseline justify-between mb-2 shrink-0">
          <span className="editorial-label text-[8.5px] text-muted-foreground">Lifecycle Roster · {data.count}</span>
        </div>
        <div className="overflow-y-auto flex-1 -mx-1">
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-muted-foreground editorial-label text-[8px] border-b border-border">
                <th className="text-left font-normal py-1.5 px-1">Strategy</th>
                <th className="text-left font-normal py-1.5 px-1">Stage</th>
                <th className="text-right font-normal py-1.5 px-1">Pos</th>
                <th className="text-right font-normal py-1.5 px-1">Gross</th>
                <th className="text-right font-normal py-1.5 px-1">P&L</th>
                <th className="text-right font-normal py-1.5 px-1">Sharpe</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const active = r.id === selId;
                return (
                  <tr
                    key={r.id}
                    className={`border-b border-border/40 transition-colors ${
                      active ? "bg-white/5" : ""
                    }`}
                  >
                    <td className="py-1.5 px-1">
                      <div className="font-serif text-[13px] leading-tight truncate">{r.name}</div>
                      <div className="editorial-label text-[7.5px] text-muted-foreground">{r.signalLabel}</div>
                    </td>
                    <td className="py-1.5 px-1"><StageTag stage={r.stage} /></td>
                    <td className="py-1.5 px-1 text-right tabular-nums text-[11px]">{r.positions || "—"}</td>
                    <td className="py-1.5 px-1 text-right tabular-nums text-[11px]">{r.grossPct ? `${r.grossPct.toFixed(0)}%` : "—"}</td>
                    <td className={`py-1.5 px-1 text-right tabular-nums text-[11px] ${pnlColor(r.pnlPct)}`}>
                      {r.positions ? `${r.pnlPct > 0 ? "+" : ""}${r.pnlPct.toFixed(2)}%` : "—"}
                    </td>
                    <td className="py-1.5 px-1 text-right tabular-nums text-[11px] text-muted-foreground">
                      {r.sharpe != null ? r.sharpe.toFixed(2) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail */}
      {detail && (
        <div className="w-[46%] max-w-[420px] shrink-0 flex flex-col overflow-hidden border-l border-border pl-4">
          <div className="flex items-start justify-between gap-2 shrink-0">
            <div className="min-w-0">
              <div className="font-serif text-lg leading-tight truncate">{detail.name}</div>
              <div className="editorial-label text-[8px] text-muted-foreground truncate">
                {detail.signalLabel}{detail.universe ? ` · ${detail.universe}` : ""}
              </div>
            </div>
            <StageTag stage={detail.stage} />
          </div>

          <div className="grid grid-cols-3 gap-2 my-3 shrink-0">
            <Metric label="Book Value" value={fmtUsd(detail.bookValue)} />
            <Metric label="P&L" value={`${detail.pnl > 0 ? "+" : ""}${detail.pnlPct.toFixed(2)}%`} tone={pnlColor(detail.pnlPct)} />
            <Metric label="Sharpe" value={detail.stats?.sharpe != null ? detail.stats.sharpe.toFixed(2) : "—"} />
            <Metric label="Max DD" value={detail.stats?.maxDD != null ? `${detail.stats.maxDD.toFixed(1)}%` : "—"} />
            <Metric label="Gross" value={`${detail.grossPct.toFixed(0)}%`} />
            <Metric label="Age" value={`${detail.ageDays}d`} />
          </div>

          <div className="flex-1 overflow-y-auto pr-1 min-h-0">
            {detail.lastRebalance && detail.lastRebalance.at && (
              <div className="mb-3 rounded-sm border border-border/60 bg-white/[0.02] px-2 py-1.5">
                <div className="flex items-center justify-between">
                  <span className="editorial-label text-[8px] text-muted-foreground">
                    Last Rebalance · {detail.lastRebalance.at}
                  </span>
                  {detail.lastRebalance.costBps != null && (
                    <span className="editorial-label text-[7.5px] text-muted-foreground">
                      {detail.lastRebalance.costBps}bps model
                    </span>
                  )}
                </div>
                <div className="flex items-baseline gap-4 mt-1">
                  <span className="tabular-nums text-[11px]">
                    {detail.lastRebalance.trades ?? 0}{" "}
                    <span className="text-muted-foreground text-[9px]">trades</span>
                  </span>
                  <span className="tabular-nums text-[11px]">
                    {(detail.lastRebalance.turnoverPct ?? 0).toFixed(1)}%{" "}
                    <span className="text-muted-foreground text-[9px]">turnover</span>
                  </span>
                  <span className="tabular-nums text-[11px]">
                    {fmtUsd(detail.lastRebalance.costUsd ?? 0)}{" "}
                    <span className="text-muted-foreground text-[9px]">cost</span>
                  </span>
                </div>
              </div>
            )}
            {curve.length > 1 && (
              <div className="h-[110px] mb-3">
                <div className="editorial-label text-[8px] text-muted-foreground mb-1">P&L Since Inception (real closes)</div>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={curve} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id={`navGrad-${detail.id}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
                        <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                    <XAxis dataKey="t" hide />
                    <YAxis hide domain={["dataMin", "dataMax"]} />
                    <ReferenceLine y={0} stroke="#333" strokeDasharray="2 2" />
                    <Tooltip
                      contentStyle={{ background: "#0a0a0a", border: "1px solid #222", fontSize: 11 }}
                      labelStyle={{ color: "#888" }}
                      formatter={(v: number) => [`${v > 0 ? "+" : ""}${v.toFixed(2)}%`, "P&L"]}
                    />
                    <Area type="monotone" dataKey="pnlPct" stroke={stroke} strokeWidth={1.5} fill={`url(#navGrad-${detail.id})`} dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}

            {detail.promotion && (
              <div className="mb-3">
                <div className="editorial-label text-[8px] text-muted-foreground mb-1">
                  Promotion Check · {detail.promotion.pass ? "ready" : "not ready"}
                </div>
                <div className="flex flex-col gap-1">
                  {detail.promotion.checks.map((c) => (
                    <div key={c.label} className="flex items-center justify-between text-[10.5px]">
                      <span className="flex items-center gap-1.5">
                        <span className={c.pass ? "text-emerald-400" : "text-red-400"}>{c.pass ? "✓" : "✕"}</span>
                        <span className="text-muted-foreground">{c.label}</span>
                      </span>
                      <span className="tabular-nums">{c.detail}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {detail.marks && detail.marks.length > 0 && (
              <div>
                <div className="editorial-label text-[8px] text-muted-foreground mb-1">Marked Positions</div>
                <table className="w-full border-collapse">
                  <tbody>
                    {detail.marks.map((m) => {
                      const w = weightFor(detail, m.symbol);
                      return (
                        <tr key={m.symbol} className="border-b border-border/30">
                          <td className="py-1 text-[11px] font-medium">{m.symbol}</td>
                          <td className="py-1 text-right tabular-nums text-[10px] text-muted-foreground">{w != null ? `${w.toFixed(1)}%` : "—"}</td>
                          <td className="py-1 text-right tabular-nums text-[10px] text-muted-foreground">{fmtUsd(m.marketValue)}</td>
                          <td className={`py-1 text-right tabular-nums text-[10.5px] ${pnlColor(m.pnlPct)}`}>
                            {m.pnlPct > 0 ? "+" : ""}{m.pnlPct.toFixed(2)}%
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            <div className="mt-3 pt-2 border-t border-border/40">
              <span className="editorial-label text-[7.5px] text-muted-foreground">
                Ask "show risk for {detail.name}" or "attribution for {detail.name}" to drill in.
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
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
