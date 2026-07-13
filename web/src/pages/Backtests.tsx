import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { BacktestResult, RunRow, StrategyRow } from "../types";
import { EquityCurve } from "../panels/EquityCurve";
import { fmtTime, shortId, stateClass } from "../lib/format";

function unwrap(run: RunRow | null): Partial<BacktestResult> {
  const result = (run?.result ?? {}) as Partial<BacktestResult> & { data?: Partial<BacktestResult> };
  return result.data ?? result;
}

function MiniCurve({ run }: { run: RunRow | null }) {
  const curve = unwrap(run).equityCurve ?? [];
  if (curve.length < 2) return <div className="backtest-card-empty">No completed curve yet</div>;
  return <EquityCurve points={curve} height={72} />;
}

export function Backtests() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { data: strategies, loading: strategiesLoading } = useAsync<StrategyRow[]>((s) => api.listStrategies(s), []);
  const { data: runs, loading: runsLoading } = useAsync<RunRow[]>((s) => api.listRuns("backtest", s), []);

  const cards = useMemo(() => {
    return (strategies ?? []).map((strategy) => {
      const strategyRuns = (runs ?? [])
        .filter((run) => run.strategy_id === strategy.id)
        .sort((a, b) => String(b.updated_at ?? b.created_at ?? "").localeCompare(String(a.updated_at ?? a.created_at ?? "")));
      return { strategy, latestRun: strategyRuns[0] ?? null, runCount: strategyRuns.length };
    });
  }, [strategies, runs]);

  const filtered = cards.filter(({ strategy }) => {
    const needle = query.trim().toLowerCase();
    return !needle || String(strategy.name ?? strategy.id).toLowerCase().includes(needle);
  });

  const loading = strategiesLoading || runsLoading;

  async function quickRun(strategyId: string) {
    setSubmitError(null);
    try {
      const run = await api.createRun(strategyId, "backtest", "1y", undefined, crypto.randomUUID());
      navigate(`/backtests/${strategyId}?run=${encodeURIComponent(run.run_id ?? run.id)}`);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <div className="page deploy-screen" style={{ padding: 0, overflow: "auto" }}>
      <div className="topbar">
        <div className="topbar-left">
          <div className="topbar-title">Backtests</div>
          <div className="topbar-sub">Review, compare, and rerun MCP-deployed backtests.</div>
        </div>
        <div className="searchbar-wrap">
          <input className="searchbar" type="search" placeholder="Search strategies" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>
        <div className="topbar-right" />
      </div>

      {submitError && <div className="banner" style={{ margin: "0 22px 12px" }}>{submitError}</div>}
      {loading && <div className="empty" style={{ margin: 22 }}>Loading backtests…</div>}
      {!loading && filtered.length === 0 && (
        <div className="backtest-empty">
          <strong>No backtests yet.</strong>
          <span>Deploy a backtest through your connected Doomberg MCP client.</span>
        </div>
      )}

      <div className="deploy-grid">
        {filtered.map(({ strategy, latestRun, runCount }) => {
          const stats = unwrap(latestRun).stats ?? {};
          return (
            <article key={strategy.id} className="fcard backtest-card">
              <button className="backtest-card-main" onClick={() => navigate(`/backtests/${strategy.id}`)}>
                <div className="deploy-card-name">{strategy.name ?? `Strategy ${shortId(strategy.id)}`}</div>
                <div className="deploy-card-meta">
                  v{strategy.version} · {runCount} run{runCount === 1 ? "" : "s"}
                  {latestRun ? ` · ${fmtTime(latestRun.updated_at ?? latestRun.created_at)}` : ""}
                </div>
                {latestRun && <span className={`badge ${stateClass(latestRun.state)}`}>{latestRun.state}</span>}
                <MiniCurve run={latestRun} />
                <div className="deploy-card-stats">
                  {Object.entries(stats).filter(([, value]) => typeof value === "number").slice(0, 4).map(([key, value]) => (
                    <div key={key}><div className="deploy-stat-label">{key}</div><div className="deploy-stat-val">{Number(value).toFixed(2)}</div></div>
                  ))}
                </div>
              </button>
              <div className="backtest-card-actions">
                <button className="btn" onClick={() => navigate(`/backtests/${strategy.id}`)}>History</button>
                <button className="btn primary" onClick={() => quickRun(strategy.id)}>Run again</button>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
