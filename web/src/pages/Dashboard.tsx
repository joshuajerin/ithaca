import { Link } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import { type FormEvent, type ReactNode, useState } from "react";
import type {
  ApprovalRow,
  ArtifactRow,
  DatasetSnapshotRow,
  JobRow,
  OrderIntentRow,
  OpsStatus,
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
  ops: OpsStatus;
  artifacts: ArtifactRow[];
  approvals: ApprovalRow[];
  providers: ProviderConnectionRow[];
  snapshots: DatasetSnapshotRow[];
  orderIntents: OrderIntentRow[];
  triggers: TriggerRow[];
}

export function Dashboard() {
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [triggerSymbol, setTriggerSymbol] = useState("NVDA");
  const [triggerPrice, setTriggerPrice] = useState("");
  const [triggerOp, setTriggerOp] = useState<"gte" | "lte">("gte");
  const [orderRunId, setOrderRunId] = useState("");
  const [orderSymbol, setOrderSymbol] = useState("AAPL");
  const [orderQuantity, setOrderQuantity] = useState("1");
  const [orderLimit, setOrderLimit] = useState("");
  const { data, loading, error, reload } = useAsync<DashboardData>(
    async (signal) => {
      const [runs, sessions, strategies, jobs, ops, artifacts, approvals, providers, orderIntents, triggers] = await Promise.all([
        api.listRuns(undefined, signal),
        api.listSessions(signal),
        api.listStrategies(signal),
        api.listJobs(signal),
        api.getOpsStatus(signal),
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
        ops,
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
  const ops = data?.ops;
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
  const pendingApprovalRows = approvals.filter((approval) => approval.state === "pending").slice(0, 4);
  const latestIntents = [...orderIntents].sort(byUpdatedDesc).slice(0, 4);
  const readinessRows = ops?.readiness ?? [];
  const entitlementRecords = ops?.providers.entitlement_records
    ?? providers.reduce((sum, provider) => sum + provider.entitlements.length, 0);
  const archiveDataLabel = ops?.platform.archive_configured
    ? "archive configured"
    : `${snapshots.length} snapshot${snapshots.length === 1 ? "" : "s"}`;
  const executionGatewayDetail = ops?.execution.live_enabled
    ? "Live submission enabled behind policy checks."
    : "Paper execution only.";

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

  function connectIbkr() {
    return runAction("provider", () =>
      api.upsertProviderConnection({
        provider: "ibkr",
        connection_id: "ibkr-vps",
        account_ref: "ibkr-vps",
        credential_ref: "env:DOOMBERG_IBKR_ENGINE_TOKEN",
        capabilities: ["quotes", "orders", "trading", "execution"],
        entitlements: [
          {
            dataset: "equities-options",
            entitlement_class: "connected_account",
            source_account: "ibkr-vps",
            freshness: "real_time",
            permitted_use: "tenant_runtime",
          },
        ],
        state: "connected",
        retention_policy: "connected-account",
      }),
    );
  }

  function createPriceTrigger(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const symbol = triggerSymbol.trim().toUpperCase();
    const price = Number(triggerPrice);
    if (!symbol || !Number.isFinite(price) || price <= 0) {
      setActionError("Enter a symbol and positive trigger price.");
      return;
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
    return runAction("trigger", () =>
      api.createTrigger(`${symbol.toLowerCase()}-price-${triggerOp}-${price}`, policy, "active"),
    );
  }

  function createPaperIntent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const runId = orderRunId.trim() || latestRuns[0]?.run_id || latestRuns[0]?.id;
    const symbol = orderSymbol.trim().toUpperCase();
    const quantity = Number(orderQuantity);
    const limitPrice = Number(orderLimit);
    if (!runId || !symbol || !Number.isFinite(quantity) || quantity <= 0) {
      setActionError("Enter a run, symbol, and positive quantity.");
      return;
    }
    if (!Number.isFinite(limitPrice) || limitPrice <= 0) {
      setActionError("Enter a positive limit price for paper fill preview.");
      return;
    }
    return runAction("intent", () =>
      api.createOrderIntent({
        run_id: runId,
        payload: {
          broker: "paper",
          symbol,
          side: "buy",
          quantity,
          order_type: "limit",
          limit_price: limitPrice,
          freshness_ms: 0,
        },
        idempotency_key: `ui:${runId}:${symbol}:${Date.now()}`,
      }),
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
              <span>{archiveDataLabel}</span>
            </div>
            <div className="data-row">
              <strong>Connected-account entitlements</strong>
              <span>{entitlementRecords} entitlement record{entitlementRecords === 1 ? "" : "s"}</span>
            </div>
            <div className="data-row">
              <strong>IBKR engine</strong>
              <span>{ops?.ibkr.engine_configured ? ops.ibkr.engine_host ?? "configured" : "unset"}</span>
            </div>
          </div>
          <div className="ops-actions">
            <button className="btn" type="button" onClick={connectIbkr} disabled={busy === "provider"}>
              Connect IBKR VPS
            </button>
          </div>
          <div className="mini-list">
            {providers.slice(0, 4).map((provider) => (
              <div className="mini-row" key={provider.connection_id}>
                <span>
                  <strong>{provider.provider}</strong>
                  <p>{provider.state} · {provider.capabilities.join(", ") || "no capabilities"}</p>
                </span>
                <em>{provider.account_ref ?? provider.connection_id}</em>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Approvals And Execution" meta={`${pendingApprovals} pending`}>
          <div className="warning-list">
            <StatusRow state={pendingApprovals ? "pending" : "succeeded"} title="Approval queue" detail={`${pendingApprovals} pending approval${pendingApprovals === 1 ? "" : "s"}.`} />
            <StatusRow state={proposedIntents ? "pending" : "succeeded"} title="Order intents" detail={`${proposedIntents} proposed intent${proposedIntents === 1 ? "" : "s"} awaiting policy or approval.`} />
            <StatusRow
              state={ops?.execution.live_enabled ? "succeeded" : "paused"}
              title="Execution gateway"
              detail={executionGatewayDetail}
            />
          </div>
          <form className="ops-form" onSubmit={createPaperIntent}>
            <input className="ops-input wide" value={orderRunId} onChange={(e) => setOrderRunId(e.target.value)} placeholder="run id" />
            <input className="ops-input" value={orderSymbol} onChange={(e) => setOrderSymbol(e.target.value)} placeholder="symbol" />
            <input className="ops-input" value={orderQuantity} onChange={(e) => setOrderQuantity(e.target.value)} placeholder="qty" inputMode="decimal" />
            <input className="ops-input" value={orderLimit} onChange={(e) => setOrderLimit(e.target.value)} placeholder="limit" inputMode="decimal" />
            <button className="btn" type="submit" disabled={busy === "intent"}>Create Intent</button>
          </form>
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
            {latestIntents.map((intent) => (
              <div className="mini-row" key={intent.intent_id}>
                <span>
                  <strong>{String(intent.payload.symbol ?? "intent")} / {intent.state}</strong>
                  <p>{intent.intent_id}</p>
                </span>
                <div className="mini-actions">
                  <button className="btn" type="button" onClick={() => runAction("intent", () => api.previewOrderIntent(intent.intent_id))} disabled={busy === "intent"}>Preview</button>
                  <button className="btn" type="button" onClick={() => runAction("intent", () => api.submitOrderIntent(intent.intent_id))} disabled={busy === "intent"}>Submit</button>
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
          </div>
          <form className="ops-form" onSubmit={createPriceTrigger}>
            <input className="ops-input" value={triggerSymbol} onChange={(e) => setTriggerSymbol(e.target.value)} placeholder="symbol" />
            <select className="ops-input" value={triggerOp} onChange={(e) => setTriggerOp(e.target.value as "gte" | "lte")}>
              <option value="gte">at/above</option>
              <option value="lte">at/below</option>
            </select>
            <input className="ops-input" value={triggerPrice} onChange={(e) => setTriggerPrice(e.target.value)} placeholder="price" inputMode="decimal" />
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
