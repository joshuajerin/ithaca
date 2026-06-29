import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { RunRow, StrategyRow } from "../types";
import type { BacktestResult } from "../types";
import { EquityCurve } from "../panels/EquityCurve";
import { RiskBadge } from "../panels/RiskBadge";
import { PerformancePnlPanel } from "../dashboard/panels/PerformancePnlPanel";
import { getPerformance } from "../dashboard/data";
import { fmtTime, shortId, stateClass } from "../lib/format";

function unwrapRun(run: RunRow): Partial<BacktestResult> {
  const result = (run.result ?? {}) as Partial<BacktestResult> & { data?: Partial<BacktestResult> };
  return (result.data ?? result) as Partial<BacktestResult>;
}

export function DeploymentDetail() {
  const { id } = useParams<{ id: string }>();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const { data: strategies } = useAsync<StrategyRow[]>((s) => api.listStrategies(s), []);
  const { data: allRuns, loading } = useAsync<RunRow[]>((s) => api.listRuns(undefined, s), []);

  const strategy = (strategies ?? []).find((s) => s.id === id) ?? null;
  const stratRuns = (allRuns ?? [])
    .filter((r) => r.strategy_id === id)
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));

  // Auto-select the latest run if none selected
  const activeRunId = selectedRunId ?? (stratRuns[0]?.id ?? null);
  const activeRun = stratRuns.find((r) => r.id === activeRunId) ?? stratRuns[0] ?? null;
  const bt = activeRun ? unwrapRun(activeRun) : null;
  const curve = Array.isArray(bt?.equityCurve) ? bt!.equityCurve : [];

  // Build performance panel data from the active run
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const perfData = getPerformance(activeRun ? [activeRun] : []) as any;

  const displayName = strategy?.name ?? `Strategy ${shortId(id ?? "")}`;

  return (
    <div className="page deploy-detail-screen" style={{ padding: 0, overflow: "auto" }}>
      {/* Topbar */}
      <div className="topbar">
        <div className="topbar-left">
          <div className="topbar-title">
            <Link to="/deployments" style={{ color: "var(--muted-dim)" }}>Deployments</Link>
            {" / "}
            {displayName}
          </div>
          <div className="topbar-sub">
            v{strategy?.version ?? "—"} · {shortId(id)} · {stratRuns.length} run{stratRuns.length !== 1 ? "s" : ""}
          </div>
        </div>
        <div className="topbar-right">
          {activeRun && (
            <span className={`badge ${stateClass(activeRun.state)}`} style={{ fontSize: 10 }}>{activeRun.state}</span>
          )}
        </div>
      </div>

      {/* Header summary card */}
      <div style={{ padding: "0 22px 16px" }}>
        <div className="fcard" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 12 }}>
          {bt?.stats && Object.entries(bt.stats).filter(([, v]) => typeof v === "number").slice(0, 6).map(([k, v]) => (
            <div key={k}>
              <div className="deploy-stat-label">{k}</div>
              <div className="deploy-stat-val">{(v as number).toFixed(2)}</div>
            </div>
          ))}
          {!bt?.stats && (
            <div className="empty">{loading ? "Loading…" : "No result data."}</div>
          )}
        </div>
      </div>

      {/* Detail body: run mini-list + charts */}
      <div className="deploy-detail-body">
        {/* Left: run list */}
        <div className="deploy-run-list">
          <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted-dim)", marginBottom: 8 }}>
            Runs ({stratRuns.length})
          </div>
          {stratRuns.length === 0 && <div className="empty">No runs.</div>}
          {stratRuns.map((run, idx) => (
            <div
              key={run.id}
              className={`deploy-run-item${(run.id === activeRunId) ? " sel" : ""}`}
              onClick={() => setSelectedRunId(run.id)}
            >
              <div style={{ fontWeight: 700, color: "var(--fg)", marginBottom: 2 }}>Run {stratRuns.length - idx}</div>
              <div className={`badge ${stateClass(run.state)}`} style={{ display: "inline-block", marginBottom: 3 }}>{run.state}</div>
              <div style={{ color: "var(--muted-dim)", fontSize: 9 }}>{shortId(run.id)}</div>
              <div style={{ color: "var(--muted-dim)", fontSize: 9, marginTop: 1 }}>{fmtTime(run.created_at)}</div>
            </div>
          ))}
        </div>

        {/* Right: charts */}
        <div className="deploy-charts">
          {/* Equity curve */}
          <div className="fcard">
            <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted-dim)", marginBottom: 10 }}>
              Equity Curve · {activeRun ? shortId(activeRun.id) : "—"}
            </div>
            {curve.length > 1 ? (
              <EquityCurve points={curve} height={160} />
            ) : (
              <div className="empty">{loading ? "Loading curve…" : "No equity data."}</div>
            )}
          </div>

          {/* Performance panel */}
          {curve.length > 2 && (
            <div className="fcard" style={{ minHeight: 320 }}>
              <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted-dim)", marginBottom: 10 }}>Performance & P&L</div>
              <div style={{ height: 280 }}>
                <PerformancePnlPanel data={perfData} />
              </div>
            </div>
          )}

          {/* Risk badge */}
          {bt && (
            <div className="fcard">
              <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted-dim)", marginBottom: 10 }}>Risk</div>
              <RiskBadge risk={bt.risk} relaxed={bt.relaxed} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
