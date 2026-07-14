import { lazy, Suspense, useState } from "react";
import { useAsync } from "../hooks/useAsync";
import { api } from "../api";
import type {
  AdaptiveDashboardResponse,
  AdaptiveDashboardWidget,
  DashboardReadEnvelope,
  DashboardActivityData,
  DashboardMarketData,
  DashboardProviderStatusData,
  DashboardRunView,
  DashboardRiskData,
  DashboardSummaryData,
  RunRow,
} from "../types";
import { DotWaveCanvas } from "../components/adaptive/DotWaveCanvas";
import {
  performanceFromDashboard,
  riskFromDashboard,
} from "../dashboard/data";
import type { ReactNode } from "react";

const PerformancePnlPanel = lazy(() =>
  import("../dashboard/panels/PerformancePnlPanel").then((module) => ({
    default: module.PerformancePnlPanel,
  })),
);
const PortfolioRiskPanel = lazy(() =>
  import("../dashboard/panels/PortfolioRiskPanel").then((module) => ({
    default: module.PortfolioRiskPanel,
  })),
);

interface BandDef {
  id: string;
  label: string;
  panels: { id: string; title: string }[];
}

const BANDS: BandDef[] = [
  { id: "overview",  label: "Personal Overview", panels: [{ id: "perf", title: "Performance & P&L" }, { id: "risk", title: "Portfolio Risk" }] },
  { id: "activity",  label: "Recent Activity",   panels: [{ id: "flow", title: "Trade Flow" }, { id: "book", title: "Order Book" }, { id: "congress", title: "Congress Trades" }] },
  { id: "global",    label: "Global Analysis",   panels: [{ id: "yield", title: "Yield Curve" }, { id: "sentiment", title: "Sentiment" }] },
];

const ADAPTIVE_WIDGET_IDS = new Set([
  "performance_pnl",
  "portfolio_risk",
  "trade_flow",
  "order_book",
  "congress_trades",
  "yield_curve",
  "sentiment",
  "recent_sessions",
  "tool_usage",
  "warning_watch",
  "live_data_status",
]);

const INSTALL_COMMAND = "curl -fsSL https://app.tradeithaca.com/install.py | python3";

function SearchIcon() {
  return (
    <svg className="searchbar-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <circle cx="6.5" cy="6.5" r="4" /><line x1="10" y1="10" x2="14" y2="14" />
    </svg>
  );
}

function FCardPanel({ title, children, minHeight = 280 }: { title: string; children: ReactNode; minHeight?: number }) {
  return (
    <div className="fcard" style={{ display: "flex", flexDirection: "column", minHeight }}>
      <div style={{ fontSize: 13, color: "var(--fg)", fontWeight: 600, marginBottom: 14 }}>{title}</div>
      <div style={{ flex: 1, minHeight: 0 }}>{children}</div>
    </div>
  );
}

function AdaptiveDashboardEmptyState() {
  const [copied, setCopied] = useState(false);

  async function copyInstallCommand() {
    try {
      await navigator.clipboard.writeText(INSTALL_COMMAND);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = INSTALL_COMMAND;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }

    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <div className="adaptive-empty-state" aria-label="No adaptive dashboard history">
      <DotWaveCanvas />
      <div className="adaptive-empty-card">
        <p className="adaptive-empty-message">
          Install the Ithaca MCP and start a research session to have a personalized dashboard.
        </p>
        <div className="adaptive-install-command">
          <span className="adaptive-install-prompt">$</span>
          <code>{INSTALL_COMMAND}</code>
          <button
            type="button"
            className="adaptive-install-copy"
            onClick={copyInstallCommand}
            aria-label="Copy install command"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function visibleAdaptiveWidgets(
  widgets: AdaptiveDashboardWidget[] | undefined,
  query: string,
): AdaptiveDashboardWidget[] {
  const q = query.toLowerCase().trim();
  return (widgets ?? [])
    .filter((widget) => ADAPTIVE_WIDGET_IDS.has(widget.id))
    .filter((widget) => !q || widget.title.toLowerCase().includes(q) || widget.id.toLowerCase().includes(q))
    .sort((a, b) => a.priority - b.priority || a.layout.y - b.layout.y || a.layout.x - b.layout.x);
}

export type AdaptiveDashboardView = "loading" | "empty" | "adaptive" | "fallback";

export function resolveAdaptiveDashboardState({
  adaptive,
  adaptiveError,
  adaptiveLoading,
  runs,
  runsError,
  runsLoading,
}: {
  adaptive: AdaptiveDashboardResponse | null;
  adaptiveError: string | null;
  adaptiveLoading: boolean;
  runs: RunRow[] | null;
  runsError: string | null;
  runsLoading: boolean;
}): AdaptiveDashboardView {
  if (adaptiveLoading || runsLoading) return "loading";
  if (adaptive && adaptive.status !== "empty") return "adaptive";
  if (runs?.some((run) => run.kind === "research")) return "fallback";
  if (adaptive?.status === "empty") return "empty";
  if (adaptiveError && !runsError && runs !== null) return "empty";
  return "fallback";
}

export function recentResearchSessions(rows: DashboardRunView[]): DashboardRunView[] {
  return rows.filter((run) => run.kind === "research").slice(0, 5);
}

export function warningCounts(activity: DashboardActivityData | null): {
  failed: number;
  alerts: number;
} {
  return {
    failed: activity?.runs.filter((run) => /fail|timeout|cancel/i.test(run.state ?? "")).length ?? 0,
    alerts: activity?.alerts.length ?? 0,
  };
}

function UsageList({ rows }: { rows: DashboardRunView[] }) {
  const recent = recentResearchSessions(rows);
  if (!recent.length) return <div className="empty">No recent sessions.</div>;
  return (
    <div className="adaptive-list">
      {recent.map((run) => (
        <div key={run.run_id} className="adaptive-list-row">
          <span>{run.state}</span>
          <strong>{run.run_id?.slice(0, 8) ?? "—"}</strong>
          <small>{run.updated_at || run.created_at || ""}</small>
        </div>
      ))}
    </div>
  );
}

function ToolUsageSummary({ adaptive }: { adaptive: Exclude<AdaptiveDashboardResponse, { status: "empty" }> }) {
  return (
    <div className="adaptive-metric-stack">
      <div><strong>{adaptive.source_session_count}</strong><span>Your research sessions</span></div>
      <div><strong>{adaptive.source_event_count}</strong><span>Your recorded events</span></div>
    </div>
  );
}

function WarningWatch({ activity }: { activity: DashboardActivityData | null }) {
  const counts = warningCounts(activity);
  return (
    <div className="adaptive-metric-stack">
      <div><strong>{counts.alerts}</strong><span>Open alerts</span></div>
      <div><strong>{counts.failed}</strong><span>Recent failed runs</span></div>
    </div>
  );
}

function LiveDataStatus({
  providers,
  market,
  marketLoading,
  marketError,
}: {
  providers: DashboardReadEnvelope<DashboardProviderStatusData> | null;
  market: DashboardReadEnvelope<DashboardMarketData> | null;
  marketLoading: boolean;
  marketError: string | null;
}) {
  if (!providers || providers.status === "empty" || providers.status === "unavailable") {
    return <DataStatePanel response={providers} emptyMessage="No tenant data provider is connected." />;
  }
  return (
    <div className="adaptive-metric-stack">
      <div><strong>{providers.data.counts.connected}</strong><span>Connected providers</span></div>
      <div><strong>{marketLoading ? "loading" : marketError ? "unavailable" : market?.status ?? "empty"}</strong><span>Market observations</span></div>
      <div><strong>{market?.freshness_ms != null ? `${Math.round(market.freshness_ms / 1000)}s` : "—"}</strong><span>Observation age</span></div>
    </div>
  );
}

function DataStatePanel({
  loading,
  error,
  response,
  emptyMessage,
}: {
  loading?: boolean;
  error?: string | null;
  response?: DashboardReadEnvelope<unknown> | null;
  emptyMessage: string;
}) {
  const message = loading
    ? "Loading your data…"
    : error
      ? "This data could not be loaded."
      : response?.status === "unavailable"
        ? response.error?.message ?? "This data source is unavailable."
        : response?.status === "stale"
          ? "The latest recorded data is stale."
          : emptyMessage;
  return (
    <div className="empty" style={{ minHeight: 160, display: "grid", placeItems: "center", padding: 24, textAlign: "center" }}>
      <span>{message}</span>
    </div>
  );
}

function UnsupportedPanel({ label }: { label: string }) {
  return (
    <DataStatePanel
      emptyMessage={`${label} is not available from a connected tenant data source yet.`}
    />
  );
}

function PanelLoading() {
  return <DataStatePanel loading emptyMessage="Loading panel…" />;
}

export function Dashboard() {
  const [query, setQuery] = useState("");
  const {
    data: runs,
    loading: runsLoading,
    error: runsError,
  } = useAsync<RunRow[]>((s) => api.listRuns(undefined, s), []);
  const {
    data: adaptive,
    loading: adaptiveLoading,
    error: adaptiveError,
  } = useAsync<AdaptiveDashboardResponse>((s) => api.getAdaptiveDashboard(s), []);
  const { data: summary, loading: summaryLoading, error: summaryError } =
    useAsync<DashboardReadEnvelope<DashboardSummaryData>>((s) => api.getDashboardSummary(s), []);
  const { data: risk, loading: riskLoading, error: riskError } =
    useAsync<DashboardReadEnvelope<DashboardRiskData>>((s) => api.getDashboardRisk(s), []);
  const { data: activity, loading: activityLoading, error: activityError } =
    useAsync<DashboardReadEnvelope<DashboardActivityData>>((s) => api.getDashboardActivity(s), []);
  const { data: providers, loading: providersLoading, error: providersError } =
    useAsync<DashboardReadEnvelope<DashboardProviderStatusData>>((s) => api.getDashboardProviderStatus(s), []);
  const { data: market, loading: marketLoading, error: marketError } =
    useAsync<DashboardReadEnvelope<DashboardMarketData>>((s) => api.getDashboardMarket(s), []);
  const performanceData = performanceFromDashboard(summary);
  const portfolioRiskData = riskFromDashboard(risk);

  const q = query.toLowerCase().trim();
  const panelVisible = (title: string) => !q || title.toLowerCase().includes(q);
  const bandVisible = (band: BandDef) => !q || band.label.toLowerCase().includes(q) || band.panels.some((p) => panelVisible(p.title));

  const renderAdaptiveWidget = (widget: AdaptiveDashboardWidget): ReactNode => {
    switch (widget.id) {
      case "performance_pnl":
        return performanceData
          ? <Suspense fallback={<PanelLoading />}><PerformancePnlPanel data={performanceData} /></Suspense>
          : <DataStatePanel loading={summaryLoading} error={summaryError} response={summary} emptyMessage="Run a completed backtest to see performance." />;
      case "portfolio_risk":
        return portfolioRiskData
          ? <Suspense fallback={<PanelLoading />}><PortfolioRiskPanel data={portfolioRiskData} /></Suspense>
          : <DataStatePanel loading={riskLoading} error={riskError} response={risk} emptyMessage="No recorded risk metrics or paper positions yet." />;
      case "trade_flow":
        return <UnsupportedPanel label="Trade flow" />;
      case "order_book":
        return <UnsupportedPanel label="Order book depth" />;
      case "congress_trades":
        return <UnsupportedPanel label="Congress trades" />;
      case "yield_curve":
        return <UnsupportedPanel label="Yield curve" />;
      case "sentiment":
        return <UnsupportedPanel label="Sentiment" />;
      case "recent_sessions":
        return activity?.data
          ? <UsageList rows={activity.data.runs} />
          : <DataStatePanel loading={activityLoading} error={activityError} response={activity} emptyMessage="No recent research sessions." />;
      case "tool_usage":
        return adaptive && adaptive.status !== "empty"
          ? <ToolUsageSummary adaptive={adaptive} />
          : <DataStatePanel emptyMessage="No personal usage history yet." />;
      case "warning_watch":
        return activity?.data
          ? <WarningWatch activity={activity.data} />
          : <DataStatePanel loading={activityLoading} error={activityError} response={activity} emptyMessage="No warnings recorded." />;
      case "live_data_status":
        return providers
          ? <LiveDataStatus providers={providers} market={market} marketLoading={marketLoading} marketError={marketError} />
          : <DataStatePanel loading={providersLoading || marketLoading} error={providersError || marketError} response={providers} emptyMessage="No tenant data provider is connected." />;
      default:
        return null;
    }
  };

  const adaptiveWidgets = adaptive && adaptive.status !== "empty"
    ? visibleAdaptiveWidgets(adaptive.spec.widgets, query)
    : [];

  const dashboardState = resolveAdaptiveDashboardState({
    adaptive,
    adaptiveError,
    adaptiveLoading,
    runs,
    runsError,
    runsLoading,
  });

  if (dashboardState === "loading") {
    return (
      <div className="page" style={{ padding: 0, overflow: "hidden" }}>
        <div className="topbar">
          <div className="topbar-left">
            <div className="topbar-title">Dashboard</div>
          </div>
          <div className="topbar-right" />
        </div>
        <div className="empty" style={{ padding: 40 }}>Loading dashboard…</div>
      </div>
    );
  }

  if (dashboardState === "empty") {
    return (
      <div className="page" style={{ padding: 0, overflow: "hidden" }}>
        <div className="topbar">
          <div className="topbar-left">
            <div className="topbar-title">Dashboard</div>
          </div>
          <div className="topbar-right" />
        </div>
        <AdaptiveDashboardEmptyState />
      </div>
    );
  }

  if (dashboardState === "adaptive" && adaptive && adaptive.status !== "empty") {
    return (
      <div className="page" style={{ padding: 0, overflow: "auto" }}>
        <div className="topbar">
          <div className="topbar-left">
            <div className="topbar-title">Dashboard</div>
          </div>
          <div className="searchbar-wrap">
            <SearchIcon />
            <input className="searchbar" type="search" placeholder="Search something..." value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <div className="topbar-right" />
        </div>

        <div className="adaptive-grid-wrap">
          <div className="adaptive-grid">
            {adaptiveWidgets.map((widget) => {
              const content = renderAdaptiveWidget(widget);
              if (!content) return null;
              return (
                <div
                  key={widget.id}
                  className="fcard adaptive-widget"
                  style={{
                    gridColumn: `${widget.layout.x + 1} / span ${widget.layout.w}`,
                    minHeight: Math.max(220, widget.layout.h * 92),
                  }}
                >
                  <div className="adaptive-widget-title">{widget.title}</div>
                  <div className="adaptive-widget-body">{content}</div>
                </div>
              );
            })}
          </div>
          {adaptiveWidgets.length === 0 && (
            <div className="empty" style={{ paddingTop: 40 }}>No panels match &ldquo;{query}&rdquo;</div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="page" style={{ padding: 0, overflow: "auto" }}>
      <div className="topbar">
        <div className="topbar-left">
          <div className="topbar-title">Dashboard</div>
        </div>
        <div className="searchbar-wrap">
          <SearchIcon />
          <input className="searchbar" type="search" placeholder="Search something..." value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="topbar-right" />
      </div>

      <div style={{ padding: "4px 22px 32px" }}>
        {/* Personal Overview */}
        {bandVisible(BANDS[0]) && (
          <div className="band">
            <div className="band-grid-2">
              {panelVisible("Performance & P&L") && (
                <FCardPanel title="Performance & P&L" minHeight={340}>
                  {performanceData
                    ? <Suspense fallback={<PanelLoading />}><PerformancePnlPanel data={performanceData} /></Suspense>
                    : <DataStatePanel loading={summaryLoading} error={summaryError} response={summary} emptyMessage="Run a completed backtest to see performance." />}
                </FCardPanel>
              )}
              {panelVisible("Portfolio Risk") && (
                <FCardPanel title="Portfolio Risk" minHeight={340}>
                  {portfolioRiskData
                    ? <Suspense fallback={<PanelLoading />}><PortfolioRiskPanel data={portfolioRiskData} /></Suspense>
                    : <DataStatePanel loading={riskLoading} error={riskError} response={risk} emptyMessage="No recorded risk metrics or paper positions yet." />}
                </FCardPanel>
              )}
            </div>
          </div>
        )}

        {/* Recent Activity */}
        {bandVisible(BANDS[1]) && (
          <div className="band">
            <div className="band-grid-3">
              {panelVisible("Trade Flow") && (
                <FCardPanel title="Trade Flow" minHeight={300}>
                  <UnsupportedPanel label="Trade flow" />
                </FCardPanel>
              )}
              {panelVisible("Order Book") && (
                <FCardPanel title="Order Book" minHeight={300}>
                  <UnsupportedPanel label="Order book depth" />
                </FCardPanel>
              )}
              {panelVisible("Congress Trades") && (
                <FCardPanel title="Congress Trades" minHeight={300}>
                  <UnsupportedPanel label="Congress trades" />
                </FCardPanel>
              )}
            </div>
          </div>
        )}

        {/* Global Analysis */}
        {bandVisible(BANDS[2]) && (
          <div className="band">
            <div className="band-grid-2">
              {panelVisible("Yield Curve") && (
                <FCardPanel title="Yield Curve" minHeight={300}>
                  <UnsupportedPanel label="Yield curve" />
                </FCardPanel>
              )}
              {panelVisible("Sentiment") && (
                <FCardPanel title="Sentiment" minHeight={300}>
                  <UnsupportedPanel label="Sentiment" />
                </FCardPanel>
              )}
            </div>
          </div>
        )}

        {q && !BANDS.some(bandVisible) && (
          <div className="empty" style={{ paddingTop: 40 }}>No panels match &ldquo;{query}&rdquo;</div>
        )}
      </div>
    </div>
  );
}
