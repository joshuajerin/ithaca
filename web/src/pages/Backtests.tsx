import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { RunRow, StrategyRow } from "../types";
import { EquityCurve } from "../panels/EquityCurve";
import { fmtTime, shortId, stateClass } from "../lib/format";
import { unwrapBacktestResult } from "../lib/backtest";

export function buildBacktestCards(strategies: StrategyRow[], runs: RunRow[]) {
  const runsByStrategy = new Map<string, { latestRun: RunRow; runCount: number }>();
  for (const run of runs) {
    if (!run.strategy_id) continue;
    const current = runsByStrategy.get(run.strategy_id);
    const runTime = String(run.updated_at ?? run.created_at ?? "");
    const currentTime = String(current?.latestRun.updated_at ?? current?.latestRun.created_at ?? "");
    runsByStrategy.set(run.strategy_id, {
      latestRun: !current || runTime > currentTime ? run : current.latestRun,
      runCount: (current?.runCount ?? 0) + 1,
    });
  }
  return strategies.map((strategy) => {
    const strategyRuns = runsByStrategy.get(strategy.id);
    return {
      strategy,
      latestRun: strategyRuns?.latestRun ?? null,
      runCount: strategyRuns?.runCount ?? 0,
    };
  });
}

export function filterBacktestCards(cards: ReturnType<typeof buildBacktestCards>, query: string) {
  const needle = query.trim().toLowerCase();
  return cards.filter(({ strategy }) => (
    !needle || String(strategy.name ?? strategy.id).toLowerCase().includes(needle)
  ));
}

function MiniCurve({ run }: { run: RunRow | null }) {
  const curve = unwrapBacktestResult(run).equityCurve ?? [];
  if (curve.length < 2) return <div className="backtest-card-empty">No completed curve yet</div>;
  return <EquityCurve points={curve} height={72} />;
}

export function Backtests() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const { data: strategies, loading: strategiesLoading } = useAsync<StrategyRow[]>((s) => api.listStrategies(s), []);
  const { data: runs, loading: runsLoading } = useAsync<RunRow[]>((s) => api.listRuns("backtest", s), []);

  const cards = useMemo(() => buildBacktestCards(strategies ?? [], runs ?? []), [strategies, runs]);
  const filtered = filterBacktestCards(cards, query);

  const loading = strategiesLoading || runsLoading;

  return (
    <div className="page deploy-screen" style={{ padding: 0, overflow: "auto" }}>
      <div className="topbar">
        <div className="topbar-left">
          <div className="topbar-title">Backtests</div>
          <div className="topbar-sub">Observe and compare backtests created by your connected agent.</div>
        </div>
        <div className="searchbar-wrap">
          <input className="searchbar" type="search" placeholder="Search strategies" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>
        <div className="topbar-right" />
      </div>

      {loading && <div className="empty" style={{ margin: 22 }}>Loading backtests…</div>}
      {!loading && filtered.length === 0 && (
        <div className="backtest-empty">
          <strong>No backtests yet.</strong>
          <span>Ask your connected agent to create and run a backtest through Doomberg MCP.</span>
        </div>
      )}

      <div className="deploy-grid">
        {filtered.map(({ strategy, latestRun, runCount }) => {
          const stats = unwrapBacktestResult(latestRun).stats ?? {};
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
            </article>
          );
        })}
      </div>
    </div>
  );
}
