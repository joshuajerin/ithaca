import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { StrategySpec as StrategySpecSchema } from "@ithaca/contracts";
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

const DEFAULT_BUILDER: BacktestBuilderState = {
  name: "Momentum research",
  symbols: "AAPL, MSFT, NVDA, AMZN",
  primitive: "momentum",
  scheme: "rank_weight",
  range: "1y",
  lookback: 90,
  fast: 20,
  slow: 50,
  threshold: 1,
  top: 3,
  gross: 1,
  maxName: 0.5,
  costBps: 5,
  slippageBps: 2,
  rebalance: "monthly@close",
  seed: 42,
};

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
  const [builderOpen, setBuilderOpen] = useState(false);
  const [builder, setBuilder] = useState(DEFAULT_BUILDER);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { data: strategies, loading: strategiesLoading, reload: reloadStrategies } = useAsync<StrategyRow[]>((s) => api.listStrategies(s), []);
  const { data: runs, loading: runsLoading, reload: reloadRuns } = useAsync<RunRow[]>((s) => api.listRuns("backtest", s), []);

  const cards = useMemo(() => buildBacktestCards(strategies ?? [], runs ?? []), [strategies, runs]);

  const filtered = cards.filter(({ displayName }) => {
    const needle = query.trim().toLowerCase();
    return !needle || displayName.toLowerCase().includes(needle);
  });

  const loading = strategiesLoading || runsLoading;

  async function submitBuilder() {
    setSubmitError(null);
    if (builder.primitive === "ma_cross" && builder.fast >= builder.slow) {
      setSubmitError("Fast moving average must be smaller than slow moving average.");
      return;
    }
    const parsed = StrategySpecSchema.safeParse(buildStrategySpec(builder));
    if (!parsed.success) {
      setSubmitError(parsed.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`).join(" · "));
      return;
    }
    setSubmitting(true);
    try {
      const strategy = await api.proposeStrategy(parsed.data as unknown as Record<string, unknown>);
      const run = await api.createRun(strategy.id, "backtest", builder.range, undefined, crypto.randomUUID());
      reloadStrategies();
      reloadRuns();
      setBuilderOpen(false);
      navigate(`/backtests/${strategy.id}?run=${encodeURIComponent(run.run_id ?? run.id)}`);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : String(error));
    } finally {
      setSubmitting(false);
    }
  }

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
          <div className="topbar-sub">Build, run, compare, and reproduce technical strategies.</div>
        </div>
        <div className="searchbar-wrap">
          <input className="searchbar" type="search" placeholder="Search strategies" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>
        <div className="topbar-right"><button className="btn primary" onClick={() => setBuilderOpen(true)}>New backtest</button></div>
      </div>

      {submitError && !builderOpen && <div className="banner" style={{ margin: "0 22px 12px" }}>{submitError}</div>}
      {loading && <div className="empty" style={{ margin: 22 }}>Loading backtests…</div>}
      {!loading && filtered.length === 0 && (
        <div className="backtest-empty">
          <strong>No backtests yet.</strong>
          <span>Create a technical strategy here or ask your connected agent to propose one.</span>
          <button className="btn primary" onClick={() => setBuilderOpen(true)}>Create first backtest</button>
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
                {strategy && <button className="btn primary" onClick={() => quickRun(strategy.id)}>Run again</button>}
              </div>
            </article>
          );
        })}
      </div>

      {builderOpen && (
        <div className="backtest-modal-backdrop" onMouseDown={() => !submitting && setBuilderOpen(false)}>
          <section className="backtest-modal" role="dialog" aria-modal="true" aria-label="Create backtest" onMouseDown={(event) => event.stopPropagation()}>
            <div className="backtest-modal-head">
              <div><h2>New backtest</h2><p>Price-only, deterministic, and no free-form code.</p></div>
              <button className="btn" onClick={() => setBuilderOpen(false)} disabled={submitting}>Close</button>
            </div>
            <div className="backtest-form-grid">
              <Field label="Name"><input value={builder.name} onChange={(e) => setBuilder({ ...builder, name: e.target.value })} /></Field>
              <Field label="Symbols"><input value={builder.symbols} onChange={(e) => setBuilder({ ...builder, symbols: e.target.value })} placeholder="AAPL, MSFT" /></Field>
              <Field label="Strategy"><select value={builder.primitive} onChange={(e) => setBuilder({ ...builder, primitive: e.target.value as Primitive })}><option value="momentum">Momentum</option><option value="ma_cross">MA crossover</option><option value="mean_reversion">Mean reversion</option><option value="rank_returns">Rank returns</option></select></Field>
              <Field label="History"><select value={builder.range} onChange={(e) => setBuilder({ ...builder, range: e.target.value })}><option value="3mo">3 months</option><option value="6mo">6 months</option><option value="1y">1 year</option><option value="2y">2 years</option><option value="5y">5 years</option></select></Field>
              {builder.primitive !== "ma_cross" && <NumberField label="Lookback" value={builder.lookback} min={2} max={252} set={(lookback) => setBuilder({ ...builder, lookback })} />}
              {builder.primitive === "ma_cross" && <><NumberField label="Fast MA" value={builder.fast} min={2} max={200} set={(fast) => setBuilder({ ...builder, fast })} /><NumberField label="Slow MA" value={builder.slow} min={3} max={400} set={(slow) => setBuilder({ ...builder, slow })} /></>}
              {builder.primitive === "mean_reversion" && <NumberField label="Z threshold" value={builder.threshold} min={0.1} max={4} step={0.1} set={(threshold) => setBuilder({ ...builder, threshold })} />}
              {builder.primitive === "rank_returns" && <NumberField label="Top names" value={builder.top} min={1} max={500} set={(top) => setBuilder({ ...builder, top })} />}
              <Field label="Weighting"><select value={builder.scheme} onChange={(e) => setBuilder({ ...builder, scheme: e.target.value as Scheme })}><option value="rank_weight">Rank weighted</option><option value="equal_weight">Equal weighted</option><option value="vol_weight">Volatility weighted</option></select></Field>
              <NumberField label="Gross exposure" value={builder.gross} min={0.1} max={4} step={0.1} set={(gross) => setBuilder({ ...builder, gross })} />
              <NumberField label="Max name" value={builder.maxName} min={0.01} max={1} step={0.01} set={(maxName) => setBuilder({ ...builder, maxName })} />
              <NumberField label="Commission (bps)" value={builder.costBps} min={0} max={1000} step={0.5} set={(costBps) => setBuilder({ ...builder, costBps })} />
              <NumberField label="Slippage (bps)" value={builder.slippageBps} min={0} max={1000} step={0.5} set={(slippageBps) => setBuilder({ ...builder, slippageBps })} />
              <Field label="Rebalance"><select value={builder.rebalance} onChange={(e) => setBuilder({ ...builder, rebalance: e.target.value as Rebalance })}><option value="daily@close">Daily close</option><option value="weekly@close">Weekly close</option><option value="monthly@close">Monthly close</option></select></Field>
              <NumberField label="Seed" value={builder.seed} min={0} max={2147483647} set={(seed) => setBuilder({ ...builder, seed })} />
            </div>
            {submitError && <div className="banner">{submitError}</div>}
            <div className="backtest-modal-actions"><span>{normalizeSymbols(builder.symbols).length} symbols</span><button className="btn primary" onClick={submitBuilder} disabled={submitting}>{submitting ? "Creating…" : "Create and run"}</button></div>
          </section>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="backtest-field"><span>{label}</span>{children}</label>;
}

function NumberField({ label, value, min, max, step = 1, set }: { label: string; value: number; min: number; max: number; step?: number; set: (value: number) => void }) {
  return <Field label={label}><input type="number" value={value} min={min} max={max} step={step} onChange={(event) => set(Number(event.target.value))} /></Field>;
}
