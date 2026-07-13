import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import { useRunEvents } from "../hooks/useRunEvents";
import type { RunRow, StrategyRow } from "../types";
import type { BacktestResult } from "../types";
import { EquityCurve } from "../panels/EquityCurve";
import { RiskBadge } from "../panels/RiskBadge";
import { PerformancePnlPanel } from "../dashboard/panels/PerformancePnlPanel";
import { performanceFromRuns } from "../dashboard/data";
import { fmtTime, shortId, stateClass } from "../lib/format";

function unwrapRun(run: RunRow): Partial<BacktestResult> {
  const result = (run.result ?? {}) as Partial<BacktestResult> & { data?: Partial<BacktestResult> };
  return (result.data ?? result) as Partial<BacktestResult>;
}

export function DeploymentDetail() {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [compareRunId, setCompareRunId] = useState<string>("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);

  const { data: strategies } = useAsync<StrategyRow[]>((s) => api.listStrategies(s), []);
  const { data: allRuns, loading, reload } = useAsync<RunRow[]>((s) => api.listRuns("backtest", s), []);

  const strategy = (strategies ?? []).find((s) => s.id === id) ?? null;
  const stratRuns = (allRuns ?? [])
    .filter((r) => r.strategy_id === id)
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));

  // Auto-select the latest run if none selected
  const requestedRun = searchParams.get("run");
  const activeRunId = selectedRunId ?? requestedRun ?? (stratRuns[0]?.id ?? null);
  const activeRunSummary = stratRuns.find((r) => r.id === activeRunId) ?? stratRuns[0] ?? null;
  const { data: detailedRun, reload: reloadDetail } = useAsync<RunRow>(
    (signal) => activeRunId ? api.getRun(activeRunId, signal) : Promise.resolve(null as unknown as RunRow),
    [activeRunId],
  );
  const activeRun = detailedRun?.id === activeRunId ? detailedRun : activeRunSummary;
  const { events: liveEvents, conn: eventConnection } = useRunEvents(activeRunId ?? undefined);
  const bt = activeRun ? unwrapRun(activeRun) : null;
  const curve = Array.isArray(bt?.equityCurve) ? bt!.equityCurve : [];
  const comparisonRun = stratRuns.find((run) => run.id === compareRunId) ?? null;
  const comparisonCurve = comparisonRun ? unwrapRun(comparisonRun).equityCurve ?? [] : [];
  const job = activeRun?.jobs?.[0] as Record<string, unknown> | undefined;
  const terminal = activeRun ? ["succeeded", "failed", "timeout", "cancelled", "retired"].includes(activeRun.state) : true;
  const latestProgress = [...liveEvents].reverse().find((event) => event.type === "run_progress");
  const stalled = activeRun?.state === "queued"
    ? ageSeconds(activeRun.created_at) > 120
    : activeRun?.state === "running" && ageSeconds(String(job?.heartbeat_at ?? "")) > 90;

  useEffect(() => {
    if (terminal) return;
    const timer = window.setInterval(() => { reload(); reloadDetail(); }, 2000);
    return () => window.clearInterval(timer);
  }, [terminal, reload, reloadDetail]);

  useEffect(() => {
    if (!liveEvents.length) return;
    reloadDetail();
  }, [liveEvents.length, reloadDetail]);

  const perfData = performanceFromRuns(activeRun ? [activeRun] : []);

  const displayName = strategy?.name ?? `Strategy ${shortId(id ?? "")}`;

  async function runAgain() {
    if (!id) return;
    setActing(true);
    setActionError(null);
    try {
      const created = await api.createRun(id, "backtest", "1y", undefined, crypto.randomUUID());
      const runId = created.run_id ?? created.id;
      setSelectedRunId(runId);
      setSearchParams({ run: runId });
      reload();
      reloadDetail();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setActing(false);
    }
  }

  async function cancelActive() {
    if (!activeRun) return;
    setActing(true);
    setActionError(null);
    try {
      await api.runAction(activeRun.id, "cancel", { reason: "Cancelled from Backtests UI" });
      reload();
      reloadDetail();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setActing(false);
    }
  }

  function exportCsv() {
    if (!bt || !activeRun) return;
    const rows = [["metric", "value"], ...Object.entries(bt.stats ?? {}).map(([key, value]) => [key, String(value)])];
    const csv = rows.map((row) => row.map((cell) => JSON.stringify(cell)).join(",")).join("\n");
    downloadBlob(new Blob([csv], { type: "text/csv" }), `backtest-${activeRun.id}.csv`);
  }

  async function downloadArtifact(artifact: Record<string, unknown>) {
    try {
      const blob = await api.downloadArtifact(String(artifact.artifact_id));
      const metadata = (artifact.metadata ?? {}) as Record<string, unknown>;
      downloadBlob(blob, String(metadata.filename ?? `${artifact.kind ?? "artifact"}.bin`));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <div className="page deploy-detail-screen" style={{ padding: 0, overflow: "auto" }}>
      {/* Topbar */}
      <div className="topbar">
        <div className="topbar-left">
          <div className="topbar-title">
            <Link to="/backtests" style={{ color: "var(--muted-dim)" }}>Backtests</Link>
            {" / "}
            {displayName}
          </div>
          <div className="topbar-sub">
            v{strategy?.version ?? "—"} · {shortId(id)} · {stratRuns.length} run{stratRuns.length !== 1 ? "s" : ""}
          </div>
        </div>
        <div aria-hidden="true" />
        <div className="topbar-right">
          {!terminal && <button className="btn" onClick={cancelActive} disabled={acting}>Cancel</button>}
          <button className="btn primary" onClick={runAgain} disabled={acting || !strategy}>Run again</button>
          {activeRun && (
            <span className={`badge ${stateClass(activeRun.state)}`} style={{ fontSize: 10 }}>{activeRun.state}</span>
          )}
        </div>
      </div>

      {actionError && <div className="banner" style={{ margin: "0 22px 12px" }}>{actionError}</div>}

      {activeRun && !terminal && (
        <div className="backtest-progress" style={{ margin: "0 22px 16px" }}>
          <div><strong>{activeRun.state === "queued" ? "Waiting for a backtest worker" : `Backtest ${String(latestProgress?.data.phase ?? "running")}`}</strong><span>{String(job?.worker_id ?? "Worker not leased yet")} · events {eventConnection}</span></div>
          <div><span>Attempt {String(job?.attempts ?? 0)} / {String(job?.max_attempts ?? 3)} · {String(latestProgress?.data.pct ?? 0)}%</span><span>Heartbeat {fmtTime(String(job?.heartbeat_at ?? ""))}</span></div>
        </div>
      )}
      {stalled && <div className="banner" style={{ margin: "0 22px 12px" }}>This job is not receiving worker progress. It remains durable in Postgres and will be reclaimed when a worker is available.</div>}

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
              onClick={() => { setSelectedRunId(run.id); setSearchParams({ run: run.id }); }}
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
            <div className="backtest-chart-head">
              <span>Equity Curve · {activeRun ? shortId(activeRun.id) : "—"}</span>
              <select value={compareRunId} onChange={(event) => setCompareRunId(event.target.value)}>
                <option value="">Compare with…</option>
                {stratRuns.filter((run) => run.id !== activeRun?.id && run.state === "succeeded").map((run) => <option key={run.id} value={run.id}>{shortId(run.id)} · {fmtTime(run.created_at)}</option>)}
              </select>
            </div>
            {curve.length > 1 ? (
              <EquityCurve points={curve} height={160} />
            ) : (
              <div className="empty">{loading ? "Loading curve…" : "No equity data."}</div>
            )}
            {comparisonCurve.length > 1 && <div style={{ marginTop: 12 }}><div className="deploy-stat-label">Comparison · {shortId(compareRunId)}</div><EquityCurve points={comparisonCurve} height={100} /></div>}
          </div>

          {/* Performance panel */}
          {perfData && (
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

          {activeRun?.result && (
            <div className="fcard">
              <div className="backtest-chart-head"><span>Reproducibility</span><button className="btn" onClick={exportCsv}>Export CSV</button></div>
              <div className="backtest-repro-grid">
                <div><span>Seed</span><strong>{String((activeRun.spec as Record<string, unknown> | null)?.seed ?? "—")}</strong></div>
                <div><span>Result hash</span><strong>{String((activeRun.result as Record<string, unknown>).result_hash ?? "—")}</strong></div>
              </div>
              {!!activeRun.artifacts?.length && <div className="backtest-artifacts">{activeRun.artifacts.map((artifact, index) => <button className="btn" key={String((artifact as Record<string, unknown>).artifact_id ?? index)} onClick={() => downloadArtifact(artifact as Record<string, unknown>)}>{String((artifact as Record<string, unknown>).kind ?? "artifact")}</button>)}</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function ageSeconds(value?: string | null): number {
  if (!value) return 0;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? Math.max(0, (Date.now() - timestamp) / 1000) : 0;
}
