import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { BacktestResult, RunRow, StrategyRow } from "../types";
import { EquityCurve } from "../panels/EquityCurve";
import { fmtTime, shortId, stateClass } from "../lib/format";

type Primitive = "momentum" | "ma_cross" | "mean_reversion" | "rank_returns";
type Scheme = "equal_weight" | "rank_weight" | "vol_weight";
type Rebalance = "daily@close" | "weekly@close" | "monthly@close";

export interface BacktestBuilderState {
  name: string;
  symbols: string;
  primitive: Primitive;
  scheme: Scheme;
  range: string;
  lookback: number;
  fast: number;
  slow: number;
  threshold: number;
  top: number;
  gross: number;
  maxName: number;
  costBps: number;
  slippageBps: number;
  rebalance: Rebalance;
  seed: number;
}

export function normalizeSymbols(raw: string): string[] {
  return Array.from(
    new Set(raw.split(/[\s,]+/).map((symbol) => symbol.trim().toUpperCase()).filter(Boolean)),
  );
}

export function buildStrategySpec(state: BacktestBuilderState): Record<string, unknown> {
  const params: Record<string, number> = {};
  if (state.primitive === "momentum") params.lookback = state.lookback;
  if (state.primitive === "ma_cross") Object.assign(params, { fast: state.fast, slow: state.slow });
  if (state.primitive === "mean_reversion") Object.assign(params, { lookback: state.lookback, threshold: state.threshold });
  if (state.primitive === "rank_returns") Object.assign(params, { lookback: state.lookback, top: state.top });
  return {
    spec_version: "1.0",
    name: state.name.trim(),
    universe: { symbols: normalizeSymbols(state.symbols), source: "prices" },
    strategy: { id: state.primitive, params },
    construction: { scheme: state.scheme, long_only: true, gross: state.gross },
    risk: { max_gross: state.gross, max_net: state.gross, max_name_pct: state.maxName },
    execution: {
      cost_bps: state.costBps,
      slippage_bps: state.slippageBps,
      algo: "vwap",
      rebalance: state.rebalance,
    },
    resources: { tier: "standard" },
    seed: state.seed,
  };
}

function unwrap(run: RunRow | null): Partial<BacktestResult> {
  const result = (run?.result ?? {}) as Partial<BacktestResult> & { data?: Partial<BacktestResult> };
  return result.data ?? result;
}

function MiniCurve({ run }: { run: RunRow | null }) {
  const curve = unwrap(run).equityCurve ?? [];
  if (curve.length < 2) return <div className="backtest-card-empty">No completed curve yet</div>;
  return <EquityCurve points={curve} height={72} />;
}

export interface BacktestCard {
  strategy: StrategyRow | null;
  latestRun: RunRow | null;
  runCount: number;
  displayName: string;
}

function runName(run: RunRow): string {
  const name = run.spec?.name;
  return typeof name === "string" && name.trim() ? name : `Agent backtest ${shortId(run.id)}`;
}

export function buildBacktestCards(strategies: StrategyRow[], runs: RunRow[]): BacktestCard[] {
  const strategyIds = new Set(strategies.map((strategy) => strategy.id));
  const byUpdatedAt = (a: RunRow, b: RunRow) =>
    String(b.updated_at ?? b.created_at ?? "").localeCompare(String(a.updated_at ?? a.created_at ?? ""));
  const linked = strategies.map((strategy) => {
    const strategyRuns = runs.filter((run) => run.strategy_id === strategy.id).sort(byUpdatedAt);
    return { strategy, latestRun: strategyRuns[0] ?? null, runCount: strategyRuns.length, displayName: strategy.name ?? `Strategy ${shortId(strategy.id)}` };
  });
  const unlinked = runs
    .filter((run) => !run.strategy_id || !strategyIds.has(run.strategy_id))
    .sort(byUpdatedAt)
    .map((run) => ({ strategy: null, latestRun: run, runCount: 1, displayName: runName(run) }));
  return [...linked, ...unlinked];
}

export function Backtests() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const { data: strategies, loading: strategiesLoading } = useAsync<StrategyRow[]>((s) => api.listStrategies(s), []);
  const { data: runs, loading: runsLoading } = useAsync<RunRow[]>((s) => api.listRuns("backtest", s), []);

  const cards = useMemo(() => buildBacktestCards(strategies ?? [], runs ?? []), [strategies, runs]);

  const filtered = cards.filter(({ displayName }) => {
    const needle = query.trim().toLowerCase();
    return !needle || displayName.toLowerCase().includes(needle);
  });

  const loading = strategiesLoading || runsLoading;

  return (
    <div className="page deploy-screen" style={{ padding: 0, overflow: "auto" }}>
      <div className="topbar">
        <div className="topbar-left">
          <div className="topbar-title">Backtests</div>
          <div className="topbar-sub">Build, run, compare, and reproduce technical strategies.</div>
        </div>
        <div className="searchbar-wrap">
          <input className="searchbar" type="search" placeholder="Search strategies" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>
      </div>

      {loading && <div className="empty" style={{ margin: 22 }}>Loading backtests…</div>}
      {!loading && filtered.length === 0 && (
        <div className="backtest-empty">
          <strong>No backtests yet.</strong>
          <span>Ask your connected agent to propose and deploy a strategy.</span>
        </div>
      )}

      <div className="deploy-grid">
        {filtered.map(({ strategy, latestRun, runCount, displayName }) => {
          const stats = unwrap(latestRun).stats ?? {};
          const href = strategy ? `/backtests/${strategy.id}` : `/backtests/agent?run=${encodeURIComponent(latestRun?.id ?? "")}`;
          return (
            <article key={strategy?.id ?? latestRun?.id} className="fcard backtest-card">
              <button className="backtest-card-main" onClick={() => navigate(href)}>
                <div className="deploy-card-name">{displayName}</div>
                <div className="deploy-card-meta">
                  {strategy ? `v${strategy.version} · ` : "Agent run · "}{runCount} run{runCount === 1 ? "" : "s"}
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
                <button className="btn" onClick={() => navigate(href)}>History</button>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
