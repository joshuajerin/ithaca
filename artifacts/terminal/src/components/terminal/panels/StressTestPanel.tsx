import React from "react";

interface MissingName {
  symbol: string;
  reason: string;
}
interface Holding {
  symbol: string;
  name: string;
  weightPct: number;
  beta: number;
  impactPct: number;
  impactUsd: number;
}
interface Scenario {
  id: string;
  label: string;
  factor: string;
  shock: string;
  narrative: string;
  available: boolean;
  portfolioImpactPct: number | null;
  portfolioImpactUsd: number | null;
  holdings: Holding[];
  missing: MissingName[];
}
interface ProxyMeta {
  factor: string;
  ticker: string;
  available: boolean;
}
interface Coverage {
  included: number;
  excluded: number;
  excludedNames: MissingName[];
  source: string;
}
interface StressTestData {
  bookName: string;
  nav: number;
  positionCount: number;
  longCount: number;
  shortCount: number;
  scenarios: Scenario[];
  worstImpactPct: number | null;
  proxies: ProxyMeta[];
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
const signed = (v: number, d = 1) => `${v >= 0 ? "+" : ""}${v.toFixed(d)}%`;

const FACTOR_LABEL: Record<string, string> = {
  market: "Equity",
  rate: "Rates",
  oil: "Oil",
};

export function StressTestPanel({ data }: { data: StressTestData }) {
  const {
    bookName,
    nav,
    positionCount,
    longCount,
    shortCount,
    scenarios,
    worstImpactPct,
    proxies,
    coverage,
  } = data;

  const [selected, setSelected] = React.useState<string>(() => {
    const firstAvail = scenarios.find((s) => s.available);
    return (firstAvail ?? scenarios[0])?.id ?? "";
  });
  const active = scenarios.find((s) => s.id === selected) ?? null;

  const maxImpact = Math.max(
    ...scenarios.map((s) => Math.abs(s.portfolioImpactPct ?? 0)),
    1,
  );

  return (
    <div className="flex flex-col h-full gap-3 text-xs">
      {/* Header */}
      <div className="shrink-0 flex items-baseline justify-between">
        <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
          {bookName} · Scenario Stress · {fmtUsd(nav)} NAV
        </div>
        {worstImpactPct != null && (
          <div
            className="text-[9px] uppercase tracking-widest font-mono px-1.5 py-0.5 border"
            style={{ color: "#ef4444", borderColor: "#ef444455" }}
          >
            Worst {signed(worstImpactPct)}
          </div>
        )}
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        {/* Left: scenario P&L table */}
        <div className="flex flex-col gap-2 flex-1 min-h-0 overflow-auto">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
            Scenario P&amp;L (portfolio impact)
          </div>
          <table className="text-[10px] font-mono w-full border-collapse">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="text-left font-normal pb-1 pr-2">Scenario</th>
                <th className="text-right font-normal pb-1 pr-2">Shock</th>
                <th className="text-right font-normal pb-1 pr-2">Impact</th>
                <th className="text-right font-normal pb-1">USD</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s) => {
                const isSel = s.id === selected;
                const v = s.portfolioImpactPct ?? 0;
                const neg = v < 0;
                return (
                  <tr
                    key={s.id}
                    onClick={() => s.available && setSelected(s.id)}
                    className={`border-b border-border/30 transition-colors ${
                      s.available ? "cursor-pointer hover:bg-white/5" : ""
                    } ${isSel ? "bg-white/5" : ""}`}
                  >
                    <td className="py-1 pr-2 text-white/80" title={s.narrative}>
                      <span
                        className="inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle"
                        style={{
                          backgroundColor: isSel ? "#fff" : "transparent",
                          border: isSel ? undefined : "1px solid rgba(255,255,255,0.25)",
                        }}
                      />
                      {s.label}
                    </td>
                    <td className="py-1 pr-2 text-right text-muted-foreground">{s.shock}</td>
                    {s.available ? (
                      <>
                        <td
                          className="py-1 pr-2 text-right"
                          style={{ color: neg ? "#ef4444" : "#22c55e" }}
                        >
                          {signed(v)}
                        </td>
                        <td
                          className="py-1 text-right"
                          style={{ color: neg ? "#ef4444" : "#22c55e" }}
                        >
                          {fmtUsd(s.portfolioImpactUsd ?? 0)}
                        </td>
                      </>
                    ) : (
                      <td colSpan={2} className="py-1 text-right text-muted-foreground/50 italic">
                        no coverage
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* Impact bars */}
          <div className="space-y-1.5 mt-1">
            {scenarios.filter((s) => s.available).map((s) => {
              const v = s.portfolioImpactPct ?? 0;
              const neg = v < 0;
              return (
                <div key={s.id} className="flex items-center gap-2">
                  <div className="w-32 shrink-0 text-[10px] text-white/70 truncate">{s.label}</div>
                  <div className="flex-1 h-2.5 relative">
                    <div className="absolute inset-y-0 left-1/2 w-px bg-white/20" />
                    <div
                      className="absolute inset-y-0"
                      style={{
                        backgroundColor: neg ? "#ef4444aa" : "#22c55eaa",
                        left: neg ? undefined : "50%",
                        right: neg ? "50%" : undefined,
                        width: `${(Math.abs(v) / maxImpact) * 50}%`,
                      }}
                    />
                  </div>
                  <div
                    className="w-12 shrink-0 text-right text-[10px] font-mono"
                    style={{ color: neg ? "#ef4444" : "#22c55e" }}
                  >
                    {signed(v)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: per-holding impacts for the selected scenario */}
        <div className="flex flex-col gap-2 flex-1 min-h-0 overflow-auto">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest">
            {active ? `${active.label} · per-holding` : "Per-holding"}
          </div>
          {active && (
            <div className="text-[9px] text-muted-foreground leading-snug">{active.narrative}</div>
          )}
          {active && active.holdings.length > 0 ? (
            <table className="text-[10px] font-mono w-full border-collapse">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="text-left font-normal pb-1 pr-2">Name</th>
                  <th className="text-right font-normal pb-1 pr-2">Wt</th>
                  <th className="text-right font-normal pb-1 pr-2">
                    β·{FACTOR_LABEL[active.factor] ?? active.factor}
                  </th>
                  <th className="text-right font-normal pb-1 pr-2">Impact</th>
                  <th className="text-right font-normal pb-1">USD</th>
                </tr>
              </thead>
              <tbody>
                {active.holdings.map((h) => {
                  const neg = h.impactPct < 0;
                  return (
                    <tr key={h.symbol} className="border-b border-border/30">
                      <td className="py-1 pr-2 text-white/80 truncate max-w-[110px]" title={h.name}>
                        {h.symbol}
                      </td>
                      <td className="py-1 pr-2 text-right text-muted-foreground">
                        {h.weightPct.toFixed(0)}%
                      </td>
                      <td className="py-1 pr-2 text-right text-muted-foreground">
                        {h.beta >= 0 ? "+" : ""}
                        {h.beta.toFixed(2)}
                      </td>
                      <td
                        className="py-1 pr-2 text-right"
                        style={{ color: neg ? "#ef4444" : "#22c55e" }}
                      >
                        {signed(h.impactPct)}
                      </td>
                      <td
                        className="py-1 text-right"
                        style={{ color: neg ? "#ef4444" : "#22c55e" }}
                      >
                        {fmtUsd(h.impactUsd)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div className="text-[10px] text-muted-foreground/60 italic py-2">
              No holding could be modeled for this scenario.
            </div>
          )}
          {active && active.missing.length > 0 && (
            <div
              className="text-[9px] text-red-400/70 font-mono"
              title={active.missing.map((m) => `${m.symbol}: ${m.reason}`).join("\n")}
            >
              {active.missing.length} excluded: {active.missing.map((m) => m.symbol).join(", ")}
            </div>
          )}
        </div>
      </div>

      {/* Footer: coverage + proxies */}
      <div className="shrink-0 flex items-center justify-between text-[9px] text-muted-foreground font-mono border-t border-border/50 pt-1.5">
        <span>
          {coverage.included} modeled · {longCount}L/{shortCount}S · {positionCount} names · {coverage.source}
        </span>
        <span className="flex items-center gap-2">
          {proxies.map((p) => (
            <span key={p.factor} className="flex items-center gap-1">
              <span
                className={`w-1.5 h-1.5 rounded-full ${p.available ? "bg-emerald-400" : "bg-red-400/60"}`}
              />
              {p.ticker}
            </span>
          ))}
          {coverage.excluded > 0 && (
            <span
              className="text-red-400/70"
              title={coverage.excludedNames.map((e) => `${e.symbol}: ${e.reason}`).join("\n")}
            >
              {coverage.excluded} excluded
            </span>
          )}
        </span>
      </div>
    </div>
  );
}
