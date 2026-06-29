import { useState } from "react";
import { useAsync } from "../hooks/useAsync";
import { api } from "../api";
import type { RunRow } from "../types";
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

export function Dashboard() {
  const [query, setQuery] = useState("");
  const { data: runs } = useAsync<RunRow[]>((s) => api.listRuns(undefined, s), []);

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
