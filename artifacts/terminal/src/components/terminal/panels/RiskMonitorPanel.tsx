import React from "react";

interface Risk {
  var95Pct: number;
  cvar95Pct: number;
  annVolPct: number;
  predictedVolPct: number;
  var95Usd: number;
  cvar95Usd: number;
}
interface SectorExp {
  sector: string;
  label: string;
  netPct: number;
  grossPct: number;
  netUsd: number;
}
interface FactorExp {
  factor: string;
  exposure: number;
  pctOfRisk: number;
}
interface FactorBlock {
  available: boolean;
  exposures: FactorExp[];
  predictedVolPct?: number;
  factorVolPct?: number;
  specificVolPct?: number;
}
interface Limit {
  name: string;
  scope: string;
  current: number;
  limit: number;
  utilizationPct: number;
  status: "ok" | "warn" | "breach";
  format: "ratio" | "exp" | "pct";
  detail?: string;
}
interface MissingName {
  symbol: string;
  reason: string;
}
interface HistStress {
  id: string;
  label: string;
  period: string;
  available: boolean;
  bookPnlPct?: number;
  bookPnlUsd?: number;
  maxDrawdownPct?: number;
  covered: number;
  missing: MissingName[];
  worst: { symbol: string; weightPct: number; returnPct: number; pnlPct: number }[];
}
interface HypoStress {
  id: string;
  label: string;
  pnlPct: number;
  pnlUsd: number;
  breakdown?: string;
}
interface Coverage {
  included: number;
  excluded: number;
  excludedNames: MissingName[];
  days: number;
  source: string;
}
interface RiskMonitorData {
  bookName: string;
  nav: number;
  grossPct: number;
  netPct: number;
  grossUsd: number;
  netUsd: number;
  longCount: number;
  shortCount: number;
  risk: Risk;
  positions: { symbol: string; name: string; sector: string; weightPct: number; exposureUsd: number; side: string }[];
  sectors: SectorExp[];
  factor: FactorBlock;
  limits: Limit[];
  breaches: Limit[];
  inLimit: boolean;
  historicalStress: HistStress[];
  hypotheticalStress: HypoStress[];
  customStress?: HypoStress | null;
  coverage: Coverage;
  asOf?: string | null;
  source?: string;
}

const fmtUsd = (v: number) => {
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(0)}K`;
  return `${sign}$${a.toFixed(0)}`;
};
const pct = (v: number, d = 1) => `${v >= 0 ? "" : ""}${v.toFixed(d)}%`;
const signed = (v: number, d = 1) => `${v >= 0 ? "+" : ""}${v.toFixed(d)}%`;

const statusColor = (s: Limit["status"]) =>
  s === "breach" ? "#ef4444" : s === "warn" ? "#f59e0b" : "#22c55e";

function fmtLimitVal(v: number, format: Limit["format"]): string {
  if (format === "ratio") return `${v.toFixed(2)}x`;
  if (format === "exp") return `${(v * 100).toFixed(0)}%`;
  return `${(v * 100).toFixed(2)}%`;
}

export function RiskMonitorPanel({ data }: { data: RiskMonitorData }) {
  const {
    bookName,
    nav,
    grossPct,
    netPct,
    grossUsd,
    netUsd,
    longCount,
    shortCount,
    risk,
    sectors,
    factor,
    limits,
    breaches,
    inLimit,
    historicalStress,
    hypotheticalStress,
    coverage,
  } = data;

  const maxSector = Math.max(...sectors.map((s) => Math.abs(s.netPct)), 1);
  const maxFactor = Math.max(...(factor.exposures || []).map((f) => Math.abs(f.exposure)), 0.5);
  const histAvail = historicalStress.filter((h) => h.available);
  const worstHist = histAvail.reduce(
    (acc, h) => (h.bookPnlPct != null && h.bookPnlPct < acc ? h.bookPnlPct : acc),
    0,
  );

  return (
    <div className="flex flex-col h-full gap-3 text-xs">
      {/* Header */}
      <div className="shrink-0 flex items-baseline justify-between">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          {bookName} · Risk Monitor · {fmtUsd(nav)} NAV
        </div>
        <div
          className="text-[9px] uppercase tracking-widest font-mono px-1.5 py-0.5 border"
          style={{
            color: inLimit ? "#22c55e" : "#ef4444",
            borderColor: inLimit ? "#22c55e55" : "#ef444455",
          }}
        >
          {inLimit ? "Within Limits" : `${breaches.length} Breach${breaches.length === 1 ? "" : "es"}`}
        </div>
      </div>

      {/* Exposure summary cards */}
      <div className="grid grid-cols-4 gap-2 shrink-0">
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Gross</div>
          <div className="text-base font-bold font-mono">{grossPct.toFixed(0)}%</div>
          <div className="text-[9px] text-muted-foreground font-mono">{fmtUsd(grossUsd)}</div>
        </div>
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Net</div>
          <div className="text-base font-bold font-mono">{netPct.toFixed(0)}%</div>
          <div className="text-[9px] text-muted-foreground font-mono">{fmtUsd(netUsd)}</div>
        </div>
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">VaR 95%</div>
          <div className="text-base font-bold font-mono text-amber-400">{risk.var95Pct.toFixed(2)}%</div>
          <div className="text-[9px] text-muted-foreground font-mono">{fmtUsd(risk.var95Usd)}</div>
        </div>
        <div className="border border-border p-2">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">CVaR 95%</div>
          <div className="text-base font-bold font-mono text-red-400">{risk.cvar95Pct.toFixed(2)}%</div>
          <div className="text-[9px] text-muted-foreground font-mono">{fmtUsd(risk.cvar95Usd)}</div>
        </div>
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        {/* Left column: limits + exposures */}
        <div className="flex flex-col gap-3 flex-1 min-h-0 overflow-auto">
          {/* Limits framework */}
          <div className="shrink-0">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1.5">
              Limits Framework
            </div>
            <div className="space-y-1.5">
              {limits.map((l) => (
                <div key={l.name} className="flex items-center gap-2">
                  <div className="w-28 shrink-0 text-[10px] text-white/80 truncate" title={l.detail}>
                    {l.name}
                  </div>
                  <div className="flex-1 h-2.5 bg-white/5 relative overflow-hidden">
                    <div
                      className="absolute inset-y-0 left-0"
                      style={{
                        width: `${Math.min(100, l.utilizationPct)}%`,
                        backgroundColor: statusColor(l.status),
                        opacity: 0.7,
                      }}
                    />
                  </div>
                  <div className="w-28 shrink-0 text-right text-[10px] font-mono text-muted-foreground">
                    {fmtLimitVal(l.current, l.format)} / {fmtLimitVal(l.limit, l.format)}
                  </div>
                  <div
                    className="w-10 shrink-0 text-right text-[10px] font-mono"
                    style={{ color: statusColor(l.status) }}
                  >
                    {l.utilizationPct.toFixed(0)}%
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Sector exposures */}
          <div className="shrink-0">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1.5">
              Sector Exposure (net)
            </div>
            <div className="space-y-1">
              {sectors.slice(0, 8).map((s) => (
                <div key={s.sector} className="flex items-center gap-2">
                  <div className="w-28 shrink-0 text-[10px] text-white/70 truncate">{s.label}</div>
                  <div className="flex-1 h-2 relative">
                    <div className="absolute inset-y-0 left-1/2 w-px bg-white/20" />
                    <div
                      className="absolute inset-y-0"
                      style={{
                        backgroundColor: s.netPct >= 0 ? "#ffffffaa" : "#ef4444aa",
                        left: s.netPct >= 0 ? "50%" : undefined,
                        right: s.netPct < 0 ? "50%" : undefined,
                        width: `${(Math.abs(s.netPct) / maxSector) * 50}%`,
                      }}
                    />
                  </div>
                  <div className="w-12 shrink-0 text-right text-[10px] font-mono text-white">
                    {signed(s.netPct, 0)}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Factor exposures */}
          {factor.available && factor.exposures.length > 0 && (
            <div className="shrink-0">
              <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1.5">
                Factor Exposure
              </div>
              <div className="space-y-1">
                {factor.exposures.map((f) => (
                  <div key={f.factor} className="flex items-center gap-2">
                    <div className="w-20 shrink-0 text-[10px] text-white/70">{f.factor}</div>
                    <div className="flex-1 h-2 relative">
                      <div className="absolute inset-y-0 left-1/2 w-px bg-white/20" />
                      <div
                        className="absolute inset-y-0"
                        style={{
                          backgroundColor: f.exposure >= 0 ? "#60a5faaa" : "#ef4444aa",
                          left: f.exposure >= 0 ? "50%" : undefined,
                          right: f.exposure < 0 ? "50%" : undefined,
                          width: `${(Math.abs(f.exposure) / maxFactor) * 50}%`,
                        }}
                      />
                    </div>
                    <div className="w-12 shrink-0 text-right text-[10px] font-mono text-white">
                      {f.exposure >= 0 ? "+" : ""}
                      {f.exposure.toFixed(2)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right column: stress */}
        <div className="flex flex-col gap-3 flex-1 min-h-0 overflow-auto">
          {/* Historical stress */}
          <div className="shrink-0">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1.5">
              Historical Stress (replayed)
            </div>
            <table className="text-[10px] font-mono w-full border-collapse">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="text-left font-normal pb-1 pr-2">Crisis</th>
                  <th className="text-right font-normal pb-1 pr-2">Book P&L</th>
                  <th className="text-right font-normal pb-1 pr-2">Max DD</th>
                  <th className="text-right font-normal pb-1">Cov.</th>
                </tr>
              </thead>
              <tbody>
                {historicalStress.map((h) => (
                  <tr key={h.id} className="border-b border-border/30">
                    <td className="py-1 pr-2 text-white/80" title={h.period}>
                      {h.label}
                    </td>
                    {h.available ? (
                      <>
                        <td
                          className="py-1 pr-2 text-right"
                          style={{ color: (h.bookPnlPct ?? 0) < 0 ? "#ef4444" : "#22c55e" }}
                        >
                          {signed(h.bookPnlPct ?? 0)}
                        </td>
                        <td className="py-1 pr-2 text-right text-amber-400/80">
                          {(h.maxDrawdownPct ?? 0).toFixed(1)}%
                        </td>
                        <td
                          className="py-1 text-right text-muted-foreground"
                          title={
                            h.missing.length
                              ? `Missing: ${h.missing.map((m) => m.symbol).join(", ")}`
                              : undefined
                          }
                        >
                          {h.covered}
                          {h.missing.length > 0 && (
                            <span className="text-red-400/70"> −{h.missing.length}</span>
                          )}
                        </td>
                      </>
                    ) : (
                      <td colSpan={3} className="py-1 text-right text-muted-foreground/50 italic">
                        no coverage
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {worstHist < 0 && (
              <div className="text-[9px] text-muted-foreground mt-1 font-mono">
                Worst crisis drawdown: <span className="text-red-400">{signed(worstHist)}</span>
              </div>
            )}
          </div>

          {/* Hypothetical stress */}
          <div className="shrink-0">
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1.5">
              Hypothetical Stress (shocks)
            </div>
            <div className="space-y-1.5">
              {hypotheticalStress.map((h) => {
                const neg = h.pnlPct < 0;
                const mag = Math.min(100, Math.abs(h.pnlPct) * 6);
                return (
                  <div key={h.id} className="flex items-center gap-2">
                    <div className="w-32 shrink-0 text-[10px] text-white/70 truncate" title={h.breakdown}>
                      {h.label}
                    </div>
                    <div className="flex-1 h-2.5 relative">
                      <div className="absolute inset-y-0 left-1/2 w-px bg-white/20" />
                      <div
                        className="absolute inset-y-0"
                        style={{
                          backgroundColor: neg ? "#ef4444aa" : "#22c55eaa",
                          left: neg ? undefined : "50%",
                          right: neg ? "50%" : undefined,
                          width: `${mag / 2}%`,
                        }}
                      />
                    </div>
                    <div
                      className="w-20 shrink-0 text-right text-[10px] font-mono"
                      style={{ color: neg ? "#ef4444" : "#22c55e" }}
                    >
                      {signed(h.pnlPct)} · {fmtUsd(h.pnlUsd)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Coverage footer */}
      <div className="shrink-0 flex items-center justify-between text-[9px] text-muted-foreground font-mono border-t border-border/50 pt-1.5">
        <span>
          {coverage.included} modeled · {longCount}L/{shortCount}S · {coverage.days}d · {coverage.source}
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
