import { Link } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { ReactNode } from "react";
import type {
  ApprovalRow,
  ArtifactRow,
  DatasetSnapshotRow,
  JobRow,
  OrderIntentRow,
  ProviderConnectionRow,
  RunRow,
  SessionRow,
  StrategyRow,
  TriggerRow,
} from "../types";

interface DashboardData {
  runs: RunRow[];
  sessions: SessionRow[];
  strategies: StrategyRow[];
  jobs: JobRow[];
  artifacts: ArtifactRow[];
  approvals: ApprovalRow[];
  providers: ProviderConnectionRow[];
  snapshots: DatasetSnapshotRow[];
  orderIntents: OrderIntentRow[];
  triggers: TriggerRow[];
}

export function Dashboard() {
  const { data, loading, error, reload } = useAsync<DashboardData>(
    async (signal) => {
      const [runs, sessions, strategies, jobs, artifacts, approvals, providers, orderIntents, triggers] = await Promise.all([
        api.listRuns(undefined, signal),
        api.listSessions(signal),
        api.listStrategies(signal),
        api.listJobs(signal),
        api.listArtifacts(signal),
        api.listApprovals(signal),
        api.listProviders(signal),
        api.listOrderIntents(signal),
        api.listTriggers(signal),
      ]);
      return {
        runs,
        sessions,
        strategies,
        jobs,
        artifacts,
        approvals,
        providers: providers.connections,
        snapshots: providers.snapshots,
        orderIntents,
        triggers,
      };
    },
    [],
  );

  const runs = data?.runs ?? [];
  const sessions = data?.sessions ?? [];
  const strategies = data?.strategies ?? [];
  const jobs = data?.jobs ?? [];
  const artifacts = data?.artifacts ?? [];
  const approvals = data?.approvals ?? [];
  const providers = data?.providers ?? [];
  const snapshots = data?.snapshots ?? [];
  const orderIntents = data?.orderIntents ?? [];
  const triggers = data?.triggers ?? [];
  const queued = runs.filter((run) => run.state === "queued").length;
  const running = runs.filter((run) => run.state === "running").length;
  const live = runs.filter((run) => run.state === "live").length;
  const failed = runs.filter((run) => ["failed", "timeout", "timed_out", "cancelled"].includes(run.state)).length;
  const queuedJobs = jobs.filter((job) => job.state === "queued").length;
  const leasedJobs = jobs.filter((job) => job.state === "leased" || job.state === "running").length;
  const pendingApprovals = approvals.filter((approval) => approval.state === "pending").length;
  const connectedProviders = providers.filter((provider) => provider.state === "connected").length;
  const activeTriggers = triggers.filter((trigger) => trigger.state === "active").length;
  const proposedIntents = orderIntents.filter((intent) => intent.state === "proposed").length;
  const latestRuns = [...runs].sort(byUpdatedDesc).slice(0, 6);
  const latestSessions = [...sessions].sort(byUpdatedDesc).slice(0, 5);
  const latestStrategies = [...strategies].sort(byCreatedDesc).slice(0, 8);
  const latestJobs = [...jobs].sort(byUpdatedDesc).slice(0, 5);

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

      <section className="live-metrics" aria-label="Control-plane metrics">
        <Metric label="runs" value={runs.length} tone={runs.length ? "ok" : undefined} note="total" />
        <Metric label="queued" value={queued} tone={queued ? "warn" : undefined} note="awaiting worker" />
        <Metric label="running" value={running + leasedJobs} tone={running || leasedJobs ? "ok" : undefined} note="active compute" />
        <Metric label="live" value={live} tone={live ? "ok" : undefined} note="paper deployments" />
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
              <span>{snapshots.length} dataset snapshot{snapshots.length === 1 ? "" : "s"}</span>
            </div>
            <div className="data-row">
              <strong>Connected-account entitlements</strong>
              <span>{providers.reduce((sum, p) => sum + p.entitlements.length, 0)} entitlement record{providers.reduce((sum, p) => sum + p.entitlements.length, 0) === 1 ? "" : "s"}</span>
            </div>
            <div className="data-row">
              <strong>Provider capabilities</strong>
              <span>{providers.reduce((sum, p) => sum + p.capabilities.length, 0)} declared</span>
            </div>
          </div>
        </Panel>

        <Panel title="Approvals And Execution" meta={`${pendingApprovals} pending`}>
          <div className="warning-list">
            <StatusRow state={pendingApprovals ? "pending" : "succeeded"} title="Approval queue" detail={`${pendingApprovals} pending approval${pendingApprovals === 1 ? "" : "s"}.`} />
            <StatusRow state={proposedIntents ? "pending" : "succeeded"} title="Order intents" detail={`${proposedIntents} proposed intent${proposedIntents === 1 ? "" : "s"} awaiting policy or approval.`} />
            <StatusRow state="paused" title="Execution gateway" detail="Live broker submission remains disabled behind the gateway boundary." />
          </div>
        </Panel>

        <Panel title="Triggers And Artifacts" meta={`${activeTriggers} active`}>
          <div className="warning-list">
            <StatusRow state={activeTriggers ? "succeeded" : "paused"} title="Trigger policies" detail={`${activeTriggers} active of ${triggers.length} total.`} />
            <StatusRow state={artifacts.length ? "succeeded" : "paused"} title="Artifacts" detail={`${artifacts.length} run artifact${artifacts.length === 1 ? "" : "s"} indexed.`} />
            <StatusRow state={queuedJobs ? "pending" : "succeeded"} title="Queued jobs" detail={`${queuedJobs} queued worker job${queuedJobs === 1 ? "" : "s"}.`} />
          </div>
        </Panel>

        <Panel title="Operational Warnings" meta="launch gates">
          <div className="warning-list">
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
