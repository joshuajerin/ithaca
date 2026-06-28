import { Link } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import { type FormEvent, type ReactNode, useState } from "react";
import type {
  ApprovalRow,
  ArtifactRow,
  DatasetSnapshotRow,
  JobRow,
  LiveDataSmokeStatus,
  OpsStatus,
  ProviderConnectionRow,
  RunRow,
  SessionRow,
  StrategyRow,
  TriggerDryRunResult,
  TriggerRow,
} from "../types";

interface DashboardData {
  runs: RunRow[];
  sessions: SessionRow[];
  strategies: StrategyRow[];
  jobs: JobRow[];
  ops: OpsStatus;
  artifacts: ArtifactRow[];
  approvals: ApprovalRow[];
  providers: ProviderConnectionRow[];
  snapshots: DatasetSnapshotRow[];
  triggers: TriggerRow[];
}

export function Dashboard() {
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [triggerSymbol, setTriggerSymbol] = useState("NVDA");
  const [triggerPrice, setTriggerPrice] = useState("");
  const [triggerOp, setTriggerOp] = useState<"gte" | "lte">("gte");
  const [triggerDryRun, setTriggerDryRun] = useState<TriggerDryRunResult | null>(null);
  const [liveDataSmokeSymbol, setLiveDataSmokeSymbol] = useState("AAPL");
  const [liveDataSmoke, setLiveDataSmoke] = useState<LiveDataSmokeStatus | null>(null);
  const { data, loading, error, reload } = useAsync<DashboardData>(
    async (signal) => {
      const [runs, sessions, strategies, jobs, ops, artifacts, approvals, providers, triggers] = await Promise.all([
        api.listRuns(undefined, signal),
        api.listSessions(signal),
        api.listStrategies(signal),
        api.listJobs(signal),
        api.getOpsStatus(signal),
        api.listArtifacts(signal),
        api.listApprovals(signal),
        api.listProviders(signal),
        api.listTriggers(signal),
      ]);
      return {
        runs,
        sessions,
        strategies,
        jobs,
        ops,
        artifacts,
        approvals,
        providers: providers.connections,
        snapshots: providers.snapshots,
        triggers,
      };
    },
    [],
  );

  const runs = data?.runs ?? [];
  const sessions = data?.sessions ?? [];
  const strategies = data?.strategies ?? [];
  const jobs = data?.jobs ?? [];
  const ops = data?.ops;
  const artifacts = data?.artifacts ?? [];
  const approvals = data?.approvals ?? [];
  const providers = data?.providers ?? [];
  const snapshots = data?.snapshots ?? [];
  const triggers = data?.triggers ?? [];
  const queued = runs.filter((run) => run.state === "queued").length;
  const running = runs.filter((run) => run.state === "running").length;
  const failed = runs.filter((run) => ["failed", "timeout", "timed_out", "cancelled"].includes(run.state)).length;
  const queuedJobs = jobs.filter((job) => job.state === "queued").length;
  const leasedJobs = jobs.filter((job) => job.state === "leased" || job.state === "running").length;
  const pendingApprovals = approvals.filter((approval) => approval.state === "pending").length;
  const connectedProviders = providers.filter((provider) => provider.state === "connected").length;
  const activeTriggers = triggers.filter((trigger) => trigger.state === "active").length;
  const latestRuns = [...runs].sort(byUpdatedDesc).slice(0, 6);
  const latestSessions = [...sessions].sort(byUpdatedDesc).slice(0, 5);
  const latestStrategies = [...strategies].sort(byCreatedDesc).slice(0, 8);
  const latestJobs = [...jobs].sort(byUpdatedDesc).slice(0, 5);
  const pendingApprovalRows = approvals.filter((approval) => approval.state === "pending").slice(0, 4);
  const readinessRows = ops?.readiness ?? [];
  const entitlementRecords = ops?.providers.entitlement_records
    ?? providers.reduce((sum, provider) => sum + provider.entitlements.length, 0);
  const archiveDataLabel = ops?.platform.archive_configured
    ? "archive configured"
    : `${snapshots.length} snapshot${snapshots.length === 1 ? "" : "s"}`;
  const executionGatewayDetail = "Trading is disabled. This workspace is data and backtest only.";

  async function runAction(label: string, fn: () => Promise<unknown>) {
    setBusy(label);
    setActionError(null);
    try {
      await fn();
      await reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  function connectLiveData() {
    return runAction("provider", () =>
      api.upsertProviderConnection({
        provider: "doomberg-live-data",
        connection_id: "live-market-data",
        capabilities: ["quotes", "market_data"],
        entitlements: [
          {
            dataset: "equities-options",
            entitlement_class: "doomberg_live",
            freshness: "real_time",
            permitted_use: "tenant_runtime",
          },
        ],
        state: "connected",
        retention_policy: "live-data",
      }),
    );
  }

  function smokeLiveData(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const symbol = liveDataSmokeSymbol.trim().toUpperCase();
    if (!symbol) {
      setActionError("Enter a symbol for the live data smoke.");
      return;
    }
    setLiveDataSmokeSymbol(symbol);
    return runAction("live-data-smoke", async () => {
      const result = await api.liveDataSmoke(symbol);
      setLiveDataSmoke(result);
    });
  }

  function currentPriceTrigger() {
    const symbol = triggerSymbol.trim().toUpperCase();
    const price = Number(triggerPrice);
    if (!symbol || !Number.isFinite(price) || price <= 0) {
      setActionError("Enter a symbol and positive trigger price.");
      return null;
    }
    const policy = {
      when: {
        event: "market.quote",
        universe: [symbol],
        market_session: "regular",
      },
      condition: {
        all: [
          { price: { [triggerOp]: price } },
          { data_freshness_seconds: { lte: 10 } },
        ],
      },
      controls: {
        dedupe_key: "${symbol}:price",
        cooldown: "20m",
        max_runs_per_day: 8,
        data_freshness_seconds: 10,
        require_connected_live_data: true,
      },
      action: {
        run_skill: "market.quote",
        mode: "analyze",
      },
      notify: {
        channels: ["dashboard"],
      },
    };
    return {
      name: `${symbol.toLowerCase()}-price-${triggerOp}-${price}`,
      policy,
      price,
      symbol,
    };
  }

  function dryRunPriceTrigger() {
    const prepared = currentPriceTrigger();
    if (!prepared) return undefined;
    return runAction("trigger-dry-run", async () => {
      const result = await api.dryRunTrigger(prepared.name, prepared.policy);
      setTriggerDryRun(result);
    });
  }

  function createPriceTrigger(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const prepared = currentPriceTrigger();
    if (!prepared) return undefined;
    setTriggerDryRun(null);
    return runAction("trigger", () =>
      api.createTrigger(prepared.name, prepared.policy, "active"),
    );
  }

  return (
    <div className="page live-dashboard-page">
      <div className="live-hero">
        <div>
          <div className="page-title">Control Plane</div>
          <div className="page-sub">tenant {api.tenantId} / api {api.apiBase}</div>
        </div>
        <div className="live-actions">
          <button className="btn" type="button" onClick={reload} disabled={loading}>
            Refresh
          </button>
          <Link className="btn primary" to="/new-session">New Session</Link>
        </div>
      </div>

      {error ? <div className="live-empty empty">{error}</div> : null}
      {actionError ? <div className="banner warn">{actionError}</div> : null}

      <section className="live-metrics" aria-label="Control-plane metrics">
        <Metric label="runs" value={runs.length} tone={runs.length ? "ok" : undefined} note="total" />
        <Metric label="queued" value={queued} tone={queued ? "warn" : undefined} note="awaiting worker" />
        <Metric label="running" value={running + leasedJobs} tone={running || leasedJobs ? "ok" : undefined} note="active compute" />
        <Metric label="data" value={ops?.live_data.engine_configured ? 1 : 0} tone={ops?.live_data.engine_configured ? "ok" : undefined} note="live market data" />
        <Metric label="approvals" value={pendingApprovals} tone={pendingApprovals ? "warn" : undefined} note="pending" />
        <Metric label="exceptions" value={failed} tone={failed ? "warn" : undefined} note="terminal failures" />
      </section>

      <section className="live-grid">
        <Panel title="Recent Runs" meta={loading ? "loading" : `${latestRuns.length} shown`} wide>
          {latestRuns.length ? (
            <div className="session-stack">
              {latestRuns.map((run) => (
                <Link className="live-row" to={`/runs/${run.run_id ?? run.id}`} key={run.run_id ?? run.id}>
                  <span className={`status-dot ${run.state}`} />
                  <span>
                    <strong>{run.kind} / {run.state}</strong>
                    <p>{run.strategy_id ?? "no strategy"} · {run.run_id ?? run.id}</p>
                  </span>
                  <time>{formatDate(run.updated_at ?? run.created_at)}</time>
                </Link>
              ))}
            </div>
          ) : (
            <Empty loading={loading} text="No runs recorded." />
          )}
        </Panel>

        <Panel title="Sessions" meta={loading ? "loading" : `${latestSessions.length} shown`}>
          {latestSessions.length ? (
            <div className="session-stack">
              {latestSessions.map((session) => (
                <Link className="live-row compact" to={`/sessions/${session.run_id ?? session.id}`} key={session.run_id ?? session.id}>
                  <span>
                    <strong>{session.title || session.prompt || "Untitled session"}</strong>
                    <p>{session.agent ?? "agent"} · calls {session.call_count ?? 0}</p>
                  </span>
                  <span>{session.warning_count ? `${session.warning_count} warn` : "clean"}</span>
                </Link>
              ))}
            </div>
          ) : (
            <Empty loading={loading} text="No research sessions recorded." />
          )}
        </Panel>

        <Panel title="Strategies" meta={loading ? "loading" : `${latestStrategies.length} active`}>
          {latestStrategies.length ? (
            <div className="strategy-cloud">
              {latestStrategies.map((strategy) => (
                <span key={`${strategy.id}:${strategy.version}`}>
                  {strategy.name || strategy.id} v{strategy.version}
                </span>
              ))}
            </div>
          ) : (
            <Empty loading={loading} text="No strategy drafts recorded." />
          )}
        </Panel>

        <Panel title="Worker Jobs" meta={`${jobs.length} durable`}>
          {latestJobs.length ? (
            <div className="warning-list">
              {latestJobs.map((job) => (
                <StatusRow
                  key={job.job_id}
                  state={job.state}
                  title={`${job.profile} / ${job.state}`}
                  detail={`${job.kind} run ${job.run_id} · attempt ${job.attempts}`}
                />
              ))}
            </div>
          ) : (
            <Empty loading={loading} text="No durable jobs recorded." />
          )}
        </Panel>

        <Panel title="Data And Providers" meta={`${connectedProviders}/${providers.length} connected`}>
          <div className="data-list">
            <div className="data-row">
              <strong>Community/archive data</strong>
              <span>{archiveDataLabel}</span>
            </div>
            <div className="data-row">
              <strong>Connected-account entitlements</strong>
              <span>{entitlementRecords} entitlement record{entitlementRecords === 1 ? "" : "s"}</span>
            </div>
            <div className="data-row">
              <strong>Live market data</strong>
              <span>{ops?.live_data.engine_configured ? "configured" : "unset"}</span>
            </div>
          </div>
          {liveDataSmoke ? (
            <div className="warning-list">
              <StatusRow
                state={liveDataSmoke.ok ? "succeeded" : "failed"}
                title={`Live data smoke / ${liveDataSmoke.status}`}
                detail={`${liveDataSmoke.symbol} ${formatOptionalNumber(liveDataSmoke.quote?.price)} · freshness ${formatOptionalNumber(liveDataSmoke.quote?.freshness_ms)}ms · latency ${formatOptionalNumber(liveDataSmoke.latency_ms)}ms`}
              />
            </div>
          ) : null}
          <div className="ops-actions">
            <button className="btn" type="button" onClick={connectLiveData} disabled={busy === "provider"}>
              Connect Live Data
            </button>
          </div>
          <form className="ops-form" onSubmit={smokeLiveData}>
            <input
              className="ops-input"
              value={liveDataSmokeSymbol}
              onChange={(e) => setLiveDataSmokeSymbol(e.target.value)}
              placeholder="symbol"
            />
            <button className="btn" type="submit" disabled={busy === "live-data-smoke"}>
              Smoke Live Data
            </button>
          </form>
          <div className="mini-list">
            {providers.slice(0, 4).map((provider) => (
              <div className="mini-row" key={provider.connection_id}>
                <span>
                  <strong>{provider.provider}</strong>
                  <p>{provider.state} · {provider.capabilities.join(", ") || "no capabilities"}</p>
                </span>
                <em>{provider.connection_id}</em>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Approvals And Controls" meta={`${pendingApprovals} pending`}>
          <div className="warning-list">
            <StatusRow state={pendingApprovals ? "pending" : "succeeded"} title="Approval queue" detail={`${pendingApprovals} pending approval${pendingApprovals === 1 ? "" : "s"}.`} />
            <StatusRow
              state="paused"
              title="Trading"
              detail={executionGatewayDetail}
            />
          </div>
          <div className="mini-list">
            {pendingApprovalRows.map((approval) => (
              <div className="mini-row" key={approval.approval_id}>
                <span>
                  <strong>{approval.kind}</strong>
                  <p>{approval.run_id}</p>
                </span>
                <div className="mini-actions">
                  <button className="btn" type="button" onClick={() => runAction("approval", () => api.decideApproval(approval.approval_id, "approved"))} disabled={busy === "approval"}>Approve</button>
                  <button className="btn" type="button" onClick={() => runAction("approval", () => api.decideApproval(approval.approval_id, "denied"))} disabled={busy === "approval"}>Deny</button>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Triggers And Artifacts" meta={`${activeTriggers} active`}>
          <div className="warning-list">
            <StatusRow state={activeTriggers ? "succeeded" : "paused"} title="Trigger policies" detail={`${activeTriggers} active of ${triggers.length} total.`} />
            <StatusRow state={artifacts.length ? "succeeded" : "paused"} title="Artifacts" detail={`${artifacts.length} run artifact${artifacts.length === 1 ? "" : "s"} indexed.`} />
            <StatusRow state={queuedJobs ? "pending" : "succeeded"} title="Queued jobs" detail={`${queuedJobs} queued worker job${queuedJobs === 1 ? "" : "s"}.`} />
            {triggerDryRun ? (
              <StatusRow
                state={triggerDryRun.would_fire ? "pending" : "paused"}
                title={`Trigger dry run / ${triggerDryRun.reason}`}
                detail={`${String(triggerDryRun.context?.symbol ?? triggerSymbol.toUpperCase())} ${String(triggerDryRun.context?.price ?? "no quote")} · ${triggerDryRun.would_create?.run ? "would create run" : "no run"} · ${triggerDryRun.quote_mode ?? "quote"}`}
              />
            ) : null}
          </div>
          <form className="ops-form" onSubmit={createPriceTrigger}>
            <input className="ops-input" value={triggerSymbol} onChange={(e) => setTriggerSymbol(e.target.value)} placeholder="symbol" />
            <select className="ops-input" value={triggerOp} onChange={(e) => setTriggerOp(e.target.value as "gte" | "lte")}>
              <option value="gte">at/above</option>
              <option value="lte">at/below</option>
            </select>
            <input className="ops-input" value={triggerPrice} onChange={(e) => setTriggerPrice(e.target.value)} placeholder="price" inputMode="decimal" />
            <button className="btn" type="button" onClick={dryRunPriceTrigger} disabled={busy === "trigger-dry-run"}>Test Trigger</button>
            <button className="btn" type="submit" disabled={busy === "trigger"}>Create Trigger</button>
          </form>
          <div className="mini-list">
            {triggers.slice(0, 4).map((trigger) => (
              <div className="mini-row" key={trigger.trigger_id}>
                <span>
                  <strong>{trigger.name}</strong>
                  <p>{trigger.state}</p>
                </span>
                <div className="mini-actions">
                  <button className="btn" type="button" onClick={() => runAction("trigger", () => api.setTriggerState(trigger.trigger_id, trigger.state === "active" ? "paused" : "active"))} disabled={busy === "trigger"}>
                    {trigger.state === "active" ? "Pause" : "Activate"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Operational Warnings" meta="launch gates">
          <div className="warning-list">
            {readinessRows.map((row) => (
              <StatusRow key={row.name} state={row.state} title={row.name} detail={row.detail} />
            ))}
            <StatusRow state={queued ? "pending" : "succeeded"} title="Queued backlog" detail={`${queued} queued run${queued === 1 ? "" : "s"}.`} />
            <StatusRow state={failed ? "failed" : "succeeded"} title="Terminal failures" detail={`${failed} failed, timed out, or cancelled run${failed === 1 ? "" : "s"}.`} />
            <StatusRow state={providers.length ? "succeeded" : "paused"} title="Provider registry" detail={`${providers.length} provider connection${providers.length === 1 ? "" : "s"} registered.`} />
          </div>
        </Panel>
      </section>
    </div>
  );
}

function Metric({ label, value, note, tone }: { label: string; value: number; note: string; tone?: "ok" | "warn" }) {
  return (
    <div className={`metric-tile ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{note}</em>
    </div>
  );
}

function Panel({ title, meta, wide = false, children }: { title: string; meta: string; wide?: boolean; children: ReactNode }) {
  return (
    <section className={`live-panel ${wide ? "span-wide" : ""}`}>
      <div className="live-panel-head">
        <span>{title}</span>
        <em>{meta}</em>
      </div>
      <div className="live-panel-body">{children}</div>
    </section>
  );
}

function StatusRow({ state, title, detail }: { state: string; title: string; detail: string }) {
  return (
    <div className="warning-row">
      <span className={`status-dot ${state}`} />
      <span>
        <strong>{title}</strong>
        <p>{detail}</p>
      </span>
    </div>
  );
}

function Empty({ loading, text }: { loading: boolean; text: string }) {
  return <div className="live-empty empty">{loading ? "Loading..." : text}</div>;
}

function byUpdatedDesc(
  a: { updated_at?: string | null; created_at?: string | null },
  b: { updated_at?: string | null; created_at?: string | null },
) {
  return dateMs(b.updated_at ?? b.created_at) - dateMs(a.updated_at ?? a.created_at);
}

function byCreatedDesc(a: { created_at?: string | null }, b: { created_at?: string | null }) {
  return dateMs(b.created_at) - dateMs(a.created_at);
}

function dateMs(value?: string | null) {
  return value ? Date.parse(value) || 0 : 0;
}

function formatDate(value?: string | null) {
  if (!value) return "unknown";
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(ms);
}

function formatOptionalNumber(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "n/a";
}
