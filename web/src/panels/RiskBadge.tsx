import type { BacktestResult } from "../types";

// Honest risk surfacing: gate result + the v1 gross/net/maxName figures + violations.
export function RiskBadge({ risk, relaxed }: { risk?: BacktestResult["risk"]; relaxed?: boolean }) {
  if (!risk) return <span className="badge">no risk</span>;
  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <span className={`badge ${risk.ok ? "ok" : "bad"}`}>{risk.ok ? "risk ok" : "risk fail"}</span>
      <span className="badge">gross {pct(risk.gross)}</span>
      <span className="badge">net {pct(risk.net)}</span>
      <span className="badge">maxName {pct(risk.maxName)}</span>
      {relaxed && <span className="badge warn">relaxed</span>}
      {risk.violations?.length > 0 && (
        <span className="badge bad" title={risk.violations.join(", ")}>
          {risk.violations.length} violation{risk.violations.length > 1 ? "s" : ""}
        </span>
      )}
    </span>
  );
}

function pct(v: number | undefined): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(0)}%`;
}
