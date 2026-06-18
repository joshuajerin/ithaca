import React, { useEffect, useMemo, useState } from "react";
import { Pencil, Check, X, Loader2 } from "lucide-react";

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
  key?: string | null;
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
interface CustomStress {
  label: string;
  pnlPct: number;
  pnlUsd: number;
  factorBreakdown: { factor: string; exposure: number; shockPct: number; pnlPct: number }[];
  assetBreakdown: { symbol: string; weightPct: number; shockPct: number; pnlPct: number }[];
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
  customStress?: CustomStress | null;
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

// The config value is stored as a multiple (ratio) or a fraction (exp/pct). The
// editor shows the human-readable number: a multiple for "ratio", a percent for
// "exp"/"pct".
function limitToInput(v: number, format: Limit["format"]): number {
  return format === "ratio" ? v : v * 100;
}
function inputToLimit(n: number, format: Limit["format"]): number {
  return format === "ratio" ? n : n / 100;
}
const limitUnit = (format: Limit["format"]) => (format === "ratio" ? "x" : "%");

export function RiskMonitorPanel({
  data,
  onShock,
  onEditLimits,
}: {
  data: RiskMonitorData;
  onShock?: (instruction: string) => void;
  onEditLimits?: (instruction: string) => Promise<unknown>;
}) {
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
    positions,
    sectors,
    factor,
    limits,
    breaches,
    inLimit,
    historicalStress,
    hypotheticalStress,
    customStress,
    coverage,
  } = data;

  const factorNames = (factor.exposures || []).map((f) => f.factor);
  const assetSymbols = (positions || []).map((p) => p.symbol);

  type ShockKind = "factor" | "asset" | "market";
  const [kind, setKind] = React.useState<ShockKind>(
    factorNames.length ? "factor" : assetSymbols.length ? "asset" : "market",
  );
  const [factorTarget, setFactorTarget] = React.useState(factorNames[0] || "");
  const [assetTarget, setAssetTarget] = React.useState(assetSymbols[0] || "");
  const [magnitude, setMagnitude] = React.useState(-10);

  const submitShock = () => {
    if (!onShock) return;
    let instruction = "";
    if (kind === "factor") {
      if (!factorTarget) return;
      instruction = `Custom shock: factor ${factorTarget} ${magnitude}%`;
    } else if (kind === "asset") {
      if (!assetTarget) return;
      instruction = `Custom shock: asset ${assetTarget} ${magnitude}%`;
    } else {
      instruction = `Custom shock: market ${magnitude}%`;
    }
    onShock(instruction);
  };

  const editableLimits = useMemo(() => limits.filter((l) => !!l.key), [limits]);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) {
      setDraft(
        Object.fromEntries(
          editableLimits.map((l) => [l.key as string, String(limitToInput(l.limit, l.format))]),
        ),
      );
    }
  }, [editing, editableLimits]);

  const startEditing = () => {
    setError(null);
    setDraft(
      Object.fromEntries(
        editableLimits.map((l) => [l.key as string, String(limitToInput(l.limit, l.format))]),
      ),
    );
    setEditing(true);
  };

  const cancelEditing = () => {
    setEditing(false);
    setError(null);
  };

  const saveLimits = async () => {
    if (!onEditLimits) return;
    const next: Record<string, number> = {};
    for (const l of editableLimits) {
      const key = l.key as string;
      const raw = draft[key];
      const num = Number(raw);
      if (raw === undefined || raw.trim() === "" || !Number.isFinite(num) || num <= 0) {
        setError(`Enter a positive value for ${l.name}`);
        return;
      }
      next[key] = inputToLimit(num, l.format);
    }
    setSaving(true);
    setError(null);
    try {
      await onEditLimits(JSON.stringify({ limits: next }));
      setEditing(false);
    } catch {
      setError("Could not update limits");
    } finally {
      setSaving(false);
    }
  };

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
            <div className="flex items-center justify-between mb-1.5">
              <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
                Limits Framework
              </div>
              {onEditLimits && editableLimits.length > 0 && (
                editing ? (
                  <div className="flex items-center gap-2">
                    {saving && <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />}
                    <button
                      onClick={saveLimits}
                      disabled={saving}
                      className="flex items-center gap-1 text-[9px] uppercase tracking-widest text-emerald-400 hover:text-emerald-300 disabled:opacity-50"
                      title="Save limits"
                    >
                      <Check className="w-3 h-3" strokeWidth={2} /> Save
                    </button>
                    <button
                      onClick={cancelEditing}
                      disabled={saving}
                      className="flex items-center gap-1 text-[9px] uppercase tracking-widest text-muted-foreground hover:text-white disabled:opacity-50"
                      title="Cancel"
                    >
                      <X className="w-3 h-3" strokeWidth={2} /> Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={startEditing}
                    className="flex items-center gap-1 text-[9px] uppercase tracking-widest text-muted-foreground hover:text-white"
                    title="Edit limits"
                  >
                    <Pencil className="w-2.5 h-2.5" strokeWidth={2} /> Edit
                  </button>
                )
              )}
            </div>
            <div className="space-y-1.5">
              {limits.map((l) => (
                <div key={l.name} className="flex items-center gap-2">
                  <div className="w-28 shrink-0 text-[10px] text-white/80 truncate" title={l.detail}>
                    {l.name}
                  </div>
                  {editing && l.key ? (
                    <>
                      <div className="flex-1 text-[10px] text-muted-foreground font-mono">
                        now {fmtLimitVal(l.current, l.format)}
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <input
                          type="number"
                          step="any"
                          min="0"
                          value={draft[l.key] ?? ""}
                          onChange={(e) =>
                            setDraft((d) => ({ ...d, [l.key as string]: e.target.value }))
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter") saveLimits();
                            if (e.key === "Escape") cancelEditing();
                          }}
                          className="w-16 bg-white/5 border border-border px-1.5 py-0.5 text-right text-[10px] font-mono text-white focus:outline-none focus:border-white"
                        />
                        <span className="w-3 text-[10px] text-muted-foreground font-mono">
                          {limitUnit(l.format)}
                        </span>
                      </div>
                    </>
                  ) : (
                    <>
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
                    </>
                  )}
                </div>
              ))}
            </div>
            {editing && error && (
              <div className="text-[9px] text-red-400 mt-1.5 font-mono">{error}</div>
            )}
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

          {/* Custom shock builder */}
          {onShock && (
            <div className="shrink-0">
              <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1.5">
                Custom Shock Builder
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <select
                  value={kind}
                  onChange={(e) => setKind(e.target.value as ShockKind)}
                  className="bg-transparent border border-border text-[10px] text-white py-1 px-1.5 focus:outline-none focus:border-white"
                >
                  {factorNames.length > 0 && <option value="factor">Factor</option>}
                  {assetSymbols.length > 0 && <option value="asset">Asset</option>}
                  <option value="market">Market</option>
                </select>
                {kind === "factor" && (
                  <select
                    value={factorTarget}
                    onChange={(e) => setFactorTarget(e.target.value)}
                    className="bg-transparent border border-border text-[10px] text-white py-1 px-1.5 focus:outline-none focus:border-white"
                  >
                    {factorNames.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>
                )}
                {kind === "asset" && (
                  <select
                    value={assetTarget}
                    onChange={(e) => setAssetTarget(e.target.value)}
                    className="bg-transparent border border-border text-[10px] text-white py-1 px-1.5 focus:outline-none focus:border-white"
                  >
                    {assetSymbols.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                )}
                <div className="flex items-center gap-1.5 flex-1 min-w-[120px]">
                  <input
                    type="range"
                    min={-50}
                    max={50}
                    step={1}
                    value={magnitude}
                    onChange={(e) => setMagnitude(Number(e.target.value))}
                    className="flex-1 accent-white h-1"
                  />
                  <span
                    className="w-12 shrink-0 text-right text-[10px] font-mono"
                    style={{ color: magnitude < 0 ? "#ef4444" : "#22c55e" }}
                  >
                    {signed(magnitude, 0)}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={submitShock}
                  className="text-[10px] uppercase tracking-widest border border-border px-2 py-1 text-white hover:bg-white hover:text-black transition-colors"
                >
                  Apply
                </button>
              </div>

              {customStress && (
                <div className="mt-2 border border-amber-400/40 bg-amber-400/5 p-2">
                  <div className="flex items-baseline justify-between">
                    <div className="text-[9px] uppercase tracking-widest text-amber-300/90">
                      {customStress.label}
                    </div>
                    <div
                      className="text-[11px] font-mono font-bold"
                      style={{ color: customStress.pnlPct < 0 ? "#ef4444" : "#22c55e" }}
                    >
                      {signed(customStress.pnlPct, 2)} · {fmtUsd(customStress.pnlUsd)}
                    </div>
                  </div>
                  {(customStress.factorBreakdown.length > 0 ||
                    customStress.assetBreakdown.length > 0) && (
                    <div className="mt-1.5 space-y-0.5">
                      {customStress.factorBreakdown.map((b) => (
                        <div
                          key={`f-${b.factor}`}
                          className="flex items-center justify-between text-[9px] font-mono text-muted-foreground"
                        >
                          <span className="text-white/70">
                            {b.factor} <span className="text-muted-foreground">· β {b.exposure.toFixed(2)} · {signed(b.shockPct, 0)}</span>
                          </span>
                          <span style={{ color: b.pnlPct < 0 ? "#ef4444" : "#22c55e" }}>
                            {signed(b.pnlPct, 2)}
                          </span>
                        </div>
                      ))}
                      {customStress.assetBreakdown.map((b) => (
                        <div
                          key={`a-${b.symbol}`}
                          className="flex items-center justify-between text-[9px] font-mono text-muted-foreground"
                        >
                          <span className="text-white/70">
                            {b.symbol} <span className="text-muted-foreground">· w {b.weightPct.toFixed(0)}% · {signed(b.shockPct, 0)}</span>
                          </span>
                          <span style={{ color: b.pnlPct < 0 ? "#ef4444" : "#22c55e" }}>
                            {signed(b.pnlPct, 2)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
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
