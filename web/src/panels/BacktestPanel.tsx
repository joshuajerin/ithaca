import type { BacktestResult } from "../types";
import { EquityCurve } from "./EquityCurve";
import { RiskBadge } from "./RiskBadge";

// Display-only renderer for a backtest result payload (doomberg_core backtest.run `data`).
// Tolerant of partial data — it renders whatever subset of the shape is present.
export function BacktestPanel({ data }: { data: unknown }) {
  const d = (data ?? {}) as Partial<BacktestResult>;
  const stats = d.stats ?? {};
  const curve = Array.isArray(d.equityCurve) ? d.equityCurve : [];
  const weights = d.finalWeights ?? {};
  const benchmark = d.benchmark;
  const comparison = d.comparison;
  const execution = d.execution;
  const integrity = d.integrity;
  const quality = d.dataQuality;

  const statKeys = pickStats(stats);
  const benchmarkStats = benchmark?.stats ? pickStats(benchmark.stats).slice(0, 4) : [];

  return (
    <div>
      <div style={{ marginBottom: 10 }}>
        <RiskBadge risk={d.risk} relaxed={d.relaxed} />
      </div>

      {statKeys.length > 0 && (
        <div className="stat-grid">
          {statKeys.map(([k, v]) => (
            <div className="stat" key={k}>
              <div className="stat-label">{k}</div>
              <div className={`stat-val ${signClass(k, v)}`}>{fmtStat(k, v)}</div>
            </div>
          ))}
        </div>
      )}

      <div className="col-head" style={{ position: "static", padding: "4px 0", border: "none" }}>
        Equity Curve {d.bars ? `· ${d.bars} bars` : ""}{" "}
        {Array.isArray(d.symbols) && d.symbols.length ? `· ${d.symbols.join(", ")}` : ""}
      </div>
      <EquityCurve points={curve} />

      {(comparison || benchmarkStats.length > 0) && (
        <>
          <div className="col-head" style={{ position: "static", padding: "10px 0 4px", border: "none" }}>
            Benchmark Comparison {benchmark?.label ? `· ${benchmark.label}` : ""}
          </div>
          <div className="stat-grid">
            {comparison && (
              <>
                <div className="stat">
                  <div className="stat-label">active return</div>
                  <div className={`stat-val ${comparison.activeTotalReturnPct >= 0 ? "pos" : "neg"}`}>
                    {comparison.activeTotalReturnPct.toFixed(1)}%
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-label">tracking error</div>
                  <div className="stat-val">{comparison.trackingErrorPct.toFixed(1)}%</div>
                </div>
                <div className="stat">
                  <div className="stat-label">info ratio</div>
                  <div className={`stat-val ${comparison.informationRatio >= 0 ? "pos" : "neg"}`}>
                    {comparison.informationRatio.toFixed(2)}
                  </div>
                </div>
              </>
            )}
            {benchmarkStats.map(([k, v]) => (
              <div className="stat" key={`bench-${k}`}>
                <div className="stat-label">bench {k}</div>
                <div className={`stat-val ${signClass(k, v)}`}>{fmtStat(k, v)}</div>
              </div>
            ))}
          </div>
        </>
      )}

      {(execution || integrity || quality) && (
        <>
          <div className="col-head" style={{ position: "static", padding: "10px 0 4px", border: "none" }}>
            Run Integrity
          </div>
          <table className="tbl">
            <tbody>
              {execution && (
                <>
                  <tr>
                    <td>Trading cost</td>
                    <td>{execution.cost_bps.toFixed(1)} bps + {execution.slippage_bps.toFixed(1)} bps slippage</td>
                  </tr>
                  <tr>
                    <td>Turnover cost</td>
                    <td>{execution.total_cost_pct.toFixed(2)}% total · {execution.avg_daily_turnover.toFixed(3)} avg daily turnover</td>
                  </tr>
                </>
              )}
              {integrity && (
                <tr>
                  <td>No-lookahead</td>
                  <td>{integrity.noLookahead ? `${integrity.decisionLagBars} bar decision lag` : "not attested"}</td>
                </tr>
              )}
              {quality && (
                <tr>
                  <td>OHLCV panel</td>
                  <td>cleaned cache · PIT {quality.pointInTime ? "yes" : "no"}</td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}

      {Object.keys(weights).length > 0 && (
        <>
          <div className="col-head" style={{ position: "static", padding: "10px 0 4px", border: "none" }}>
            Final Weights
          </div>
          <table className="tbl">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Weight</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(weights)
                .sort((a, b) => Math.abs(b[1] as number) - Math.abs(a[1] as number))
                .map(([sym, w]) => (
                  <tr key={sym}>
                    <td>{sym}</td>
                    <td className={(w as number) >= 0 ? "" : "mono"} style={{ color: (w as number) >= 0 ? "var(--pos)" : "var(--neg)" }}>
                      {((w as number) * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function pickStats(stats: Record<string, number>): [string, number][] {
  const order = ["sharpe", "cagr", "maxDD", "vol", "winRate", "sortino", "calmar"];
  const entries = Object.entries(stats).filter(([, v]) => typeof v === "number");
  entries.sort((a, b) => {
    const ia = order.indexOf(a[0]);
    const ib = order.indexOf(b[0]);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
  return entries.slice(0, 8) as [string, number][];
}

function fmtStat(k: string, v: number): string {
  const lk = k.toLowerCase();
  if (lk.includes("cagr") || lk.includes("dd") || lk.includes("rate") || lk.includes("return") || lk.includes("vol")) {
    return `${v.toFixed(1)}%`;
  }
  return v.toFixed(2);
}

function signClass(k: string, v: number): string {
  const lk = k.toLowerCase();
  if (lk.includes("dd")) return "neg";
  if (lk.includes("sharpe") || lk.includes("cagr") || lk.includes("sortino") || lk.includes("calmar")) {
    return v >= 0 ? "pos" : "neg";
  }
  return "";
}
