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

  const statKeys = pickStats(stats);

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
  if (lk.includes("cagr") || lk.includes("dd") || lk.includes("rate") || lk.includes("vol")) {
    // these are commonly fractions or percents; show as %
    const asPct = Math.abs(v) <= 5 ? v * 100 : v;
    return `${asPct.toFixed(1)}%`;
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
