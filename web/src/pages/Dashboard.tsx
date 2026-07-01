import { useState } from "react";
import { useAsync } from "../hooks/useAsync";
import { api } from "../api";
import type { AdaptiveDashboardResponse, AdaptiveDashboardWidget, RunRow } from "../types";
import { DotWaveCanvas } from "../components/adaptive/DotWaveCanvas";
import { PerformancePnlPanel } from "../dashboard/panels/PerformancePnlPanel";
import { PortfolioRiskPanel } from "../dashboard/panels/PortfolioRiskPanel";
import { TradeFlowPanel } from "../dashboard/panels/TradeFlowPanel";
import { OrderBookPanel } from "../dashboard/panels/OrderBookPanel";
import { CongressTradesPanel } from "../dashboard/panels/CongressTradesPanel";
import { YieldCurvePanel } from "../dashboard/panels/YieldCurvePanel";
import { SentimentPanel } from "../dashboard/panels/SentimentPanel";
import {
  getPerformance,
  getPortfolioRisk,
  getTradeFlow,
  getOrderBook,
  getCongressTrades,
  getYieldCurve,
  getSentiment,
} from "../dashboard/data";
import type { ReactNode } from "react";

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

const INSTALL_COMMAND = "curl -fsSL https://app.doomberg.me/install.py | python3";

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
          Install the Doomberg MCP and start a research session to have a personalized dashboard.
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

export function shouldShowAdaptiveEmptyState({
  adaptive,
  adaptiveError,
}: {
  adaptive: AdaptiveDashboardResponse | null;
  adaptiveError: string | null;
}): boolean {
  if (adaptive?.status === "empty") return true;
  if (adaptive) return false;
  return Boolean(adaptiveError);
}

function UsageList({ rows }: { rows: RunRow[] }) {
  const recent = rows
    .filter((run) => run.kind === "research")
    .slice()
    .sort((a, b) => String(b.updated_at ?? b.created_at ?? "").localeCompare(String(a.updated_at ?? a.created_at ?? "")))
    .slice(0, 5);
  if (!recent.length) return <div className="empty">No recent sessions.</div>;
  return (
    <div className="adaptive-list">
      {recent.map((run) => (
        <div key={run.id} className="adaptive-list-row">
          <span>{run.state}</span>
          <strong>{run.id.slice(0, 8)}</strong>
          <small>{run.updated_at || run.created_at || ""}</small>
        </div>
      ))}
    </div>
  );
}

function ToolUsageSummary({ rows }: { rows: RunRow[] }) {
  const total = rows.filter((run) => run.kind === "research").length;
  return (
    <div className="adaptive-metric-stack">
      <div><strong>{total}</strong><span>Sessions</span></div>
      <div><strong>{rows.length}</strong><span>Total runs</span></div>
    </div>
  );
}

function WarningWatch({ rows }: { rows: RunRow[] }) {
  const failed = rows.filter((run) => /fail|timeout|cancel/i.test(run.state)).length;
  return (
    <div className="adaptive-metric-stack">
      <div><strong>{failed}</strong><span>Needs review</span></div>
      <div><strong>{rows.length - failed}</strong><span>Normal</span></div>
    </div>
  );
}

function LiveDataStatus() {
  return (
    <div className="adaptive-metric-stack">
      <div><strong>Live</strong><span>Data path</span></div>
      <div><strong>Server</strong><span>Credential boundary</span></div>
    </div>
  );
}

export function Dashboard() {
  const [query, setQuery] = useState("");
  const { data: runs } = useAsync<RunRow[]>((s) => api.listRuns(undefined, s), []);
  const { data: adaptive, error: adaptiveError } = useAsync<AdaptiveDashboardResponse>((s) => api.getAdaptiveDashboard(s), []);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const performanceData = getPerformance(runs ?? []) as any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const portfolioRiskData = getPortfolioRisk() as any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tradeFlowData = getTradeFlow() as any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const orderBookData = getOrderBook() as any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const congressData = getCongressTrades() as any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const yieldCurveData = getYieldCurve() as any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const sentimentData = getSentiment() as any;

  const q = query.toLowerCase().trim();
  const panelVisible = (title: string) => !q || title.toLowerCase().includes(q);
  const bandVisible = (band: BandDef) => !q || band.label.toLowerCase().includes(q) || band.panels.some((p) => panelVisible(p.title));
  const rows = runs ?? [];

  const renderAdaptiveWidget = (widget: AdaptiveDashboardWidget): ReactNode => {
    switch (widget.id) {
      case "performance_pnl":
        return <PerformancePnlPanel data={performanceData} />;
      case "portfolio_risk":
        return <PortfolioRiskPanel data={portfolioRiskData} />;
      case "trade_flow":
        return <TradeFlowPanel data={tradeFlowData} />;
      case "order_book":
        return <OrderBookPanel data={orderBookData} />;
      case "congress_trades":
        return <CongressTradesPanel data={congressData} />;
      case "yield_curve":
        return <YieldCurvePanel data={yieldCurveData} />;
      case "sentiment":
        return <SentimentPanel data={sentimentData} />;
      case "recent_sessions":
        return <UsageList rows={rows} />;
      case "tool_usage":
        return <ToolUsageSummary rows={rows} />;
      case "warning_watch":
        return <WarningWatch rows={rows} />;
      case "live_data_status":
        return <LiveDataStatus />;
      default:
        return null;
    }
  };

  const adaptiveWidgets = adaptive && adaptive.status !== "empty"
    ? visibleAdaptiveWidgets(adaptive.spec.widgets, query)
    : [];

  if (shouldShowAdaptiveEmptyState({ adaptive, adaptiveError })) {
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

  if (adaptive) {
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
                  <PerformancePnlPanel data={performanceData} />
                </FCardPanel>
              )}
              {panelVisible("Portfolio Risk") && (
                <FCardPanel title="Portfolio Risk" minHeight={340}>
                  <PortfolioRiskPanel data={portfolioRiskData} />
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
                  <TradeFlowPanel data={tradeFlowData} />
                </FCardPanel>
              )}
              {panelVisible("Order Book") && (
                <FCardPanel title="Order Book" minHeight={300}>
                  <OrderBookPanel data={orderBookData} />
                </FCardPanel>
              )}
              {panelVisible("Congress Trades") && (
                <FCardPanel title="Congress Trades" minHeight={300}>
                  <CongressTradesPanel data={congressData} />
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
                  <YieldCurvePanel data={yieldCurveData} />
                </FCardPanel>
              )}
              {panelVisible("Sentiment") && (
                <FCardPanel title="Sentiment" minHeight={300}>
                  <SentimentPanel data={sentimentData} />
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
