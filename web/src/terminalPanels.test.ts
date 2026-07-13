import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const srcDir = path.dirname(fileURLToPath(import.meta.url));
const panelsDir = path.join(srcDir, "components", "terminal", "panels");
const panelContainer = path.join(srcDir, "components", "terminal", "PanelContainer.tsx");

const oldDashboardPanelFiles = [
  "AlertsPanel.tsx",
  "AnalysisPanel.tsx",
  "AnalystComparePanel.tsx",
  "AnalystRatingsPanel.tsx",
  "AnalystReportPanel.tsx",
  "BacktestPanel.tsx",
  "BondRVPanel.tsx",
  "BrinsonPanel.tsx",
  "CDSPricerPanel.tsx",
  "CashFlowPanel.tsx",
  "CombinedAlphaPanel.tsx",
  "CompanyAnalyticsComparePanel.tsx",
  "CompanyAnalyticsPanel.tsx",
  "ComparisonPanel.tsx",
  "CompliancePanel.tsx",
  "CongressTradesPanel.tsx",
  "CorrelationMatrixPanel.tsx",
  "CreditStressPanel.tsx",
  "DCFPanel.tsx",
  "DataQualityPanel.tsx",
  "DataUniversePanel.tsx",
  "ETFExposurePanel.tsx",
  "ETFHoldingsPanel.tsx",
  "EarningsCalendarPanel.tsx",
  "EconomicReleasesPanel.tsx",
  "FactorAnalysisPanel.tsx",
  "FactorAttributionPanel.tsx",
  "FactorExposurePanel.tsx",
  "FactorPerformancePanel.tsx",
  "FilingsBrowserPanel.tsx",
  "FundamentalsPanel.tsx",
  "HeatmapPanel.tsx",
  "IVSurfacePanel.tsx",
  "InsiderActivityPanel.tsx",
  "InstitutionalFlowsPanel.tsx",
  "InstitutionalHoldersPanel.tsx",
  "IntradayChartPanel.tsx",
  "MACPanel.tsx",
  "MacroDashboardPanel.tsx",
  "MonteCarloPanel.tsx",
  "MultiStrategyPanel.tsx",
  "NewsPanel.tsx",
  "OptionsChainPanel.tsx",
  "OptionsScreenerPanel.tsx",
  "OptionsStrategyPanel.tsx",
  "OrderBookPanel.tsx",
  "PerformancePnlPanel.tsx",
  "PolymarketMarketPanel.tsx",
  "PolymarketMarketsPanel.tsx",
  "PolymarketWalletPanel.tsx",
  "PortfolioOptimizerPanel.tsx",
  "PortfolioRiskPanel.tsx",
  "PriceChartPanel.tsx",
  "RebalancePlanPanel.tsx",
  "RiskComparisonPanel.tsx",
  "RiskModelPanel.tsx",
  "RiskMonitorPanel.tsx",
  "ScenarioPanel.tsx",
  "ScreenerPanel.tsx",
  "SentimentPanel.tsx",
  "SeriesRevisionsPanel.tsx",
  "ShortingDeskPanel.tsx",
  "SignalPortfolioPanel.tsx",
  "SignalResearchPanel.tsx",
  "SignalScorecardPanel.tsx",
  "SovereignComparePanel.tsx",
  "StrategyDeskPanel.tsx",
  "StrategyMarketplacePanel.tsx",
  "StressTestPanel.tsx",
  "StructuredProductPanel.tsx",
  "SupplyChainPanel.tsx",
  "TCAPanelReport.tsx",
  "TearSheetPanel.tsx",
  "TradeFlowPanel.tsx",
  "TranscriptPanel.tsx",
  "VolTermStructurePanel.tsx",
  "WalkForwardComparePanel.tsx",
  "WalkForwardPanel.tsx",
  "YieldCurvePanel.tsx",
  "generated/DynamicPanel.tsx",
  "generated/GeneratedPanel.tsx",
];

const oldDashboardPanelTypes = [
  "price_chart",
  "news",
  "analysis",
  "fundamentals",
  "screener",
  "heatmap",
  "sentiment",
  "comparison",
  "order_book",
  "trade_flow",
  "alerts",
  "tca_report",
  "macro_dashboard",
  "yield_curve",
  "sovereign_compare",
  "bond_rv",
  "cds_pricer",
  "credit_stress",
  "economic_releases",
  "series_revisions",
  "polymarket_markets",
  "polymarket_market",
  "polymarket_wallet",
  "cashflow_duration",
  "portfolio_risk",
  "backtest",
  "walk_forward",
  "walk_forward_compare",
  "monte_carlo",
  "correlation_matrix",
  "factor_analysis",
  "risk_model",
  "risk_comparison",
  "portfolio_optimizer",
  "factor_exposures",
  "signal_research",
  "signal_scorecard",
  "signal_portfolio",
  "combined_alpha",
  "iv_surface",
  "options_chain",
  "options_screener",
  "options_strategy",
  "vol_term_structure",
  "structured_product",
  "supply_chain",
  "dcf_model",
  "earnings_transcript",
  "earnings_calendar",
  "etf_holdings",
  "etf_exposure",
  "insider_activity",
  "congress_trades",
  "institutional_holders",
  "institutional_flows",
  "filings_browser",
  "ma_tracker",
  "company_analytics",
  "company_analytics_compare",
  "data_universe",
  "intraday_chart",
  "data_quality",
  "analyst_report",
  "analyst_compare",
  "analyst_ratings",
  "scenario",
  "risk_monitor",
  "stress_test",
  "performance_pnl",
  "brinson_attribution",
  "factor_attribution",
  "factor_performance",
  "tear_sheet",
  "strategy_desk",
  "compliance",
  "multi_strategy",
  "shorting_desk",
  "rebalance_plan",
  "strategy_marketplace",
];

describe("terminal dashboard panel renderers", () => {
  it("keeps the old dashboard sub-widget renderers in the active web app", () => {
    const missing = oldDashboardPanelFiles.filter((file) => !fs.existsSync(path.join(panelsDir, file)));

    expect(missing).toEqual([]);
  });

  it("keeps the old dashboard panel types wired into PanelContainer", () => {
    const source = fs.readFileSync(panelContainer, "utf8");
    const wiredTypes = new Set([...source.matchAll(/case "([^"]+)"/g)].map((match) => match[1]));
    const missing = oldDashboardPanelTypes.filter((type) => !wiredTypes.has(type));

    expect(missing).toEqual([]);
  });

  it("keeps the generated fallback as static data rendering only", () => {
    const generatedSources = [
      fs.readFileSync(path.join(panelsDir, "generated", "DynamicPanel.tsx"), "utf8"),
      fs.readFileSync(path.join(panelsDir, "generated", "GeneratedPanel.tsx"), "utf8"),
    ].join("\n");

    expect(generatedSources).not.toMatch(/new Function|eval\(|loadGeneratedComponent|sucrase|\/api\/generated-panels/);
  });

  it("guards compliance kill-switch writes with the tenant version", () => {
    const source = fs.readFileSync(path.join(panelsDir, "CompliancePanel.tsx"), "utf8");

    expect(source).toContain("expect_version: state.killVersion ?? 0");
    expect(source).toContain('state.killSource === "none" || state.killSource === "tenant"');
  });
});
