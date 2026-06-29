import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { RunRow, StrategyRow } from "../types";
import { EquityCurve } from "../panels/EquityCurve";
import { fmtTime, shortId, stateClass } from "../lib/format";
import type { BacktestResult } from "../types";

interface StrategyCard {
  strategy: StrategyRow;
  latestRun: RunRow | null;
}

function SearchIcon() {
  return (
    <svg className="searchbar-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <circle cx="6.5" cy="6.5" r="4" /><line x1="10" y1="10" x2="14" y2="14" />
    </svg>
  );
}

function MiniSparkline({ run }: { run: RunRow | null }) {
  if (!run?.result) return <div style={{ height: 56, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "var(--muted-dim)" }}>No data</div>;
  const result = run.result as Partial<BacktestResult> & { data?: Partial<BacktestResult> };
  const bt = (result.data ?? result) as Partial<BacktestResult>;
  const curve = Array.isArray(bt.equityCurve) ? bt.equityCurve : [];
  if (curve.length < 2) return <div style={{ height: 56, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "var(--muted-dim)" }}>No curve</div>;
  return <EquityCurve points={curve} height={56} />;
}

function keyStats(run: RunRow | null) {
  if (!run?.result) return null;
  const result = run.result as Partial<BacktestResult> & { data?: Partial<BacktestResult> };
  const bt = (result.data ?? result) as Partial<BacktestResult>;
  const stats = bt.stats ?? {};
  return stats;
}

export function Deployments() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  const { data: strategies, loading: stratLoading } = useAsync<StrategyRow[]>((s) => api.listStrategies(s), []);
  const { data: allRuns, loading: runsLoading } = useAsync<RunRow[]>((s) => api.listRuns(undefined, s), []);

  const loading = stratLoading || runsLoading;

  const cards: StrategyCard[] = (strategies ?? []).map((strategy) => {
    const runs = (allRuns ?? [])
      .filter((r) => r.strategy_id === strategy.id)
      .sort((a, b) => (b.updated_at ?? b.created_at ?? "").localeCompare(a.updated_at ?? a.created_at ?? ""));
    return { strategy, latestRun: runs[0] ?? null };
  });

  const q = query.toLowerCase().trim();
  const filtered = cards.filter((c) =>
    !q ||
    (c.strategy.name ?? c.strategy.id).toLowerCase().includes(q) ||
    c.strategy.id.toLowerCase().includes(q),
  );

  return (
    <div className="page deploy-screen" style={{ padding: 0, overflow: "auto" }}>
      <div className="topbar">
        <div className="topbar-left">
          <div className="topbar-title">Deployments</div>
        </div>
        <div className="searchbar-wrap">
          <SearchIcon />
          <input className="searchbar" type="search" placeholder="Search something..." value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="topbar-right" />
      </div>

      {loading && <div className="empty" style={{ margin: "24px 22px" }}>Loading deployments…</div>}
      {!loading && filtered.length === 0 && (
        <div className="empty" style={{ margin: "24px 22px" }}>
          {q ? `No strategies match "${query}"` : "No strategies deployed yet."}
        </div>
      )}

      <div className="deploy-grid">
        {filtered.map(({ strategy, latestRun }) => {
          const stats = keyStats(latestRun);
          const displayName = strategy.name ?? `Strategy ${shortId(strategy.id)}`;
          return (
            <div
              key={strategy.id}
              className="fcard clickable"
              onClick={() => navigate(`/deployments/${strategy.id}`)}
              style={{ cursor: "pointer" }}
            >
              <div className="deploy-card-name">{displayName}</div>
              <div className="deploy-card-meta">
                {latestRun ? (
                  <>
                    <span className={`badge ${stateClass(latestRun.state)}`} style={{ marginRight: 6 }}>{latestRun.state}</span>
                    v{strategy.version} · {shortId(strategy.id)} · {fmtTime(latestRun.updated_at ?? latestRun.created_at)}
                  </>
                ) : (
                  <>v{strategy.version} · {shortId(strategy.id)} · no runs</>
                )}
              </div>

              <MiniSparkline run={latestRun} />

              {stats && (
                <div className="deploy-card-stats">
                  {Object.entries(stats)
                    .filter(([, v]) => typeof v === "number")
                    .slice(0, 4)
                    .map(([k, v]) => (
                      <div key={k}>
                        <div className="deploy-stat-label">{k}</div>
                        <div className="deploy-stat-val">{(v as number).toFixed(2)}</div>
                      </div>
                    ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
