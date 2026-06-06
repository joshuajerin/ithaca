import React, { useState } from "react";
import type { Panel } from "@workspace/api-client-react";
import { useRefinePanel } from "@workspace/api-client-react";
import { Loader2, AlertTriangle, Settings2 } from "lucide-react";
import { PriceChartPanel } from "./panels/PriceChartPanel";
import { NewsPanel } from "./panels/NewsPanel";
import { AnalysisPanel } from "./panels/AnalysisPanel";
import { FundamentalsPanel } from "./panels/FundamentalsPanel";
import { ScreenerPanel } from "./panels/ScreenerPanel";
import { HeatmapPanel } from "./panels/HeatmapPanel";
import { SentimentPanel } from "./panels/SentimentPanel";
import { ComparisonPanel } from "./panels/ComparisonPanel";
import { OrderBookPanel } from "./panels/OrderBookPanel";
import { TradeFlowPanel } from "./panels/TradeFlowPanel";
import { TCAPanelReport } from "./panels/TCAPanelReport";
import { MacroDashboardPanel } from "./panels/MacroDashboardPanel";
import { YieldCurvePanel } from "./panels/YieldCurvePanel";
import { SovereignComparePanel } from "./panels/SovereignComparePanel";
import { BondRVPanel } from "./panels/BondRVPanel";
import { CDSPricerPanel } from "./panels/CDSPricerPanel";
import { CashFlowPanel } from "./panels/CashFlowPanel";
import { PortfolioRiskPanel } from "./panels/PortfolioRiskPanel";
import { BacktestPanel } from "./panels/BacktestPanel";
import { MonteCarloPanel } from "./panels/MonteCarloPanel";
import { CorrelationMatrixPanel } from "./panels/CorrelationMatrixPanel";
import { FactorAnalysisPanel } from "./panels/FactorAnalysisPanel";
import { RiskModelPanel } from "./panels/RiskModelPanel";
import { PortfolioOptimizerPanel } from "./panels/PortfolioOptimizerPanel";
import { FactorExposurePanel } from "./panels/FactorExposurePanel";
import { SignalResearchPanel } from "./panels/SignalResearchPanel";
import { SignalScorecardPanel } from "./panels/SignalScorecardPanel";
import { IVSurfacePanel } from "./panels/IVSurfacePanel";
import { OptionsStrategyPanel } from "./panels/OptionsStrategyPanel";
import { VolTermStructurePanel } from "./panels/VolTermStructurePanel";
import { StructuredProductPanel } from "./panels/StructuredProductPanel";
import { SupplyChainPanel } from "./panels/SupplyChainPanel";
import { DCFPanel } from "./panels/DCFPanel";
import { TranscriptPanel } from "./panels/TranscriptPanel";
import { EarningsCalendarPanel } from "./panels/EarningsCalendarPanel";
import { MACPanel } from "./panels/MACPanel";
import { CompanyAnalyticsPanel } from "./panels/CompanyAnalyticsPanel";
import { DataUniversePanel } from "./panels/DataUniversePanel";
import { IntradayChartPanel } from "./panels/IntradayChartPanel";
import { DataQualityPanel } from "./panels/DataQualityPanel";
import { AnalystReportPanel } from "./panels/AnalystReportPanel";
import { AnalystComparePanel } from "./panels/AnalystComparePanel";
import { ScenarioPanel } from "./panels/ScenarioPanel";
import { RiskMonitorPanel } from "./panels/RiskMonitorPanel";
import { PerformancePnlPanel } from "./panels/PerformancePnlPanel";
import { BrinsonPanel } from "./panels/BrinsonPanel";
import { FactorAttributionPanel } from "./panels/FactorAttributionPanel";
import { TearSheetPanel } from "./panels/TearSheetPanel";
import { StrategyDeskPanel } from "./panels/StrategyDeskPanel";
import { DynamicPanel } from "./panels/generated/DynamicPanel";

interface PanelContainerProps {
  panel: Panel;
  sessionId: string;
  onRefined: (updatedPanel: Panel) => void;
  highlighted?: boolean;
}

function formatAsOf(asOf?: string | null): string {
  if (!asOf) return "live";
  const then = new Date(asOf).getTime();
  if (Number.isNaN(then)) return "live";
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function PanelContainer({ panel, sessionId, onRefined, highlighted }: PanelContainerProps) {
  const [isRefining, setIsRefining] = useState(false);
  const [refineText, setRefineText] = useState("");
  
  const refineMutation = useRefinePanel();

  const submitRefine = async (instruction: string) => {
    if (!instruction.trim()) return;
    try {
      const result = await refineMutation.mutateAsync({
        data: {
          sessionId,
          panelId: panel.id,
          instruction
        }
      });
      onRefined(result);
    } catch (e) {
      console.error("Failed to refine panel", e);
    }
  };

  const handleRefine = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!refineText.trim()) {
      setIsRefining(false);
      return;
    }
    await submitRefine(refineText);
    setIsRefining(false);
    setRefineText("");
  };

  // Switch the price chart window. Round-trips through the same refine path the
  // agent uses: instruction carries the current symbol + requested range so the
  // backend rebuilds the panel over the chosen window.
  const handleSelectRange = async (range: string) => {
    const symbol = (panel.data as any)?.symbol;
    const instruction = symbol ? `${symbol} ${range}` : range;
    await submitRefine(instruction);
  };

  const renderContent = () => {
    if (panel.status === "loading" || refineMutation.isPending) {
      return (
        <div className="w-full h-full flex flex-col items-center justify-center text-muted-foreground gap-3">
          <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.25} />
          <span className="editorial-label text-[9px] animate-pulse">Processing</span>
        </div>
      );
    }

    if (panel.status === "error" || !panel.data) {
      return (
        <div className="w-full h-full flex flex-col items-center justify-center text-muted-foreground gap-3 p-4 text-center">
          <AlertTriangle className="w-5 h-5" strokeWidth={1.25} />
          <span className="editorial-label text-[9px]">Data Acquisition Failed</span>
        </div>
      );
    }

    switch (panel.type) {
      case "price_chart": return <PriceChartPanel data={panel.data as any} onSelectRange={handleSelectRange} />;
      case "news": return <NewsPanel data={panel.data as any} />;
      case "analysis": return <AnalysisPanel data={panel.data as any} />;
      case "fundamentals": return <FundamentalsPanel data={panel.data as any} />;
      case "screener": return <ScreenerPanel data={panel.data as any} />;
      case "heatmap": return <HeatmapPanel data={panel.data as any} />;
      case "sentiment": return <SentimentPanel data={panel.data as any} />;
      case "comparison": return <ComparisonPanel data={panel.data as any} />;
      case "order_book": return <OrderBookPanel data={panel.data as any} />;
      case "trade_flow": return <TradeFlowPanel data={panel.data as any} />;
      case "tca_report": return <TCAPanelReport data={panel.data as any} />;
      case "macro_dashboard": return <MacroDashboardPanel data={panel.data as any} />;
      case "yield_curve": return <YieldCurvePanel data={panel.data as any} />;
      case "sovereign_compare": return <SovereignComparePanel data={panel.data as any} />;
      case "bond_rv": return <BondRVPanel data={panel.data as any} />;
      case "cds_pricer": return <CDSPricerPanel data={panel.data as any} />;
      case "cashflow_duration": return <CashFlowPanel data={panel.data as any} />;
      case "portfolio_risk": return <PortfolioRiskPanel data={panel.data as any} />;
      case "backtest": return <BacktestPanel data={panel.data as any} />;
      case "monte_carlo": return <MonteCarloPanel data={panel.data as any} />;
      case "correlation_matrix": return <CorrelationMatrixPanel data={panel.data as any} />;
      case "factor_analysis": return <FactorAnalysisPanel data={panel.data as any} />;
      case "risk_model": return <RiskModelPanel data={panel.data as any} />;
      case "portfolio_optimizer": return <PortfolioOptimizerPanel data={panel.data as any} />;
      case "factor_exposures": return <FactorExposurePanel data={panel.data as any} />;
      case "signal_research": return <SignalResearchPanel data={panel.data as any} />;
      case "signal_scorecard": return <SignalScorecardPanel data={panel.data as any} />;
      case "iv_surface": return <IVSurfacePanel data={panel.data as any} />;
      case "options_strategy": return <OptionsStrategyPanel data={panel.data as any} />;
      case "vol_term_structure": return <VolTermStructurePanel data={panel.data as any} />;
      case "structured_product": return <StructuredProductPanel data={panel.data as any} />;
      case "supply_chain": return <SupplyChainPanel data={panel.data as any} />;
      case "dcf_model": return <DCFPanel data={panel.data as any} />;
      case "earnings_transcript": return <TranscriptPanel data={panel.data as any} />;
      case "earnings_calendar": return <EarningsCalendarPanel data={panel.data as any} />;
      case "ma_tracker": return <MACPanel data={panel.data as any} />;
      case "company_analytics": return <CompanyAnalyticsPanel data={panel.data as any} />;
      case "data_universe": return <DataUniversePanel data={panel.data as any} />;
      case "intraday_chart": return <IntradayChartPanel data={panel.data as any} />;
      case "data_quality": return <DataQualityPanel data={panel.data as any} />;
      case "analyst_report": return <AnalystReportPanel data={panel.data as any} />;
      case "analyst_compare": return <AnalystComparePanel data={panel.data as any} />;
      case "scenario": return <ScenarioPanel data={panel.data as any} />;
      case "risk_monitor": return <RiskMonitorPanel data={panel.data as any} onShock={submitRefine} />;
      case "performance_pnl": return <PerformancePnlPanel data={panel.data as any} />;
      case "brinson_attribution": return <BrinsonPanel data={panel.data as any} />;
      case "factor_attribution": return <FactorAttributionPanel data={panel.data as any} />;
      case "tear_sheet": return <TearSheetPanel data={panel.data as any} />;
      case "strategy_desk": return <StrategyDeskPanel data={panel.data as any} />;
      default: return <DynamicPanel type={panel.type} data={panel.data as any} />;
    }
  };

  return (
    <div
      className={`bg-black border flex flex-col overflow-hidden relative group h-full transition-[box-shadow,border-color] duration-300 ${
        highlighted
          ? "border-white shadow-[0_0_0_1px_rgba(255,255,255,0.8),0_0_36px_rgba(255,255,255,0.45)] z-10"
          : "border-border"
      }`}
    >
      <div className="shrink-0 border-b border-border flex items-start justify-between px-4 pt-3 pb-2.5">
        <div className="flex flex-col gap-1 overflow-hidden min-w-0">
          <span className="editorial-label text-[8.5px] text-muted-foreground shrink-0">{panel.type.replace('_', ' ')}</span>
          <span className="font-serif text-base leading-none truncate">{panel.title}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0 mt-0.5">
          {panel.source && (
            <span
              title={panel.asOf ? `As of ${new Date(panel.asOf).toLocaleString()}` : undefined}
              className="flex items-center gap-1 text-[9px] uppercase tracking-widest text-muted-foreground"
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${panel.source === "live" ? "bg-emerald-400" : "bg-muted-foreground/50"}`}
              />
              {panel.source === "live" ? formatAsOf(panel.asOf) : panel.source}
            </span>
          )}
          <button 
            onClick={() => setIsRefining(!isRefining)}
            className="text-muted-foreground hover:text-white transition-colors opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <Settings2 className="w-3.5 h-3.5" strokeWidth={1.5} />
          </button>
        </div>
      </div>

      {isRefining && (
        <form onSubmit={handleRefine} className="px-4 py-2 border-b border-border">
          <input
            type="text"
            value={refineText}
            onChange={e => setRefineText(e.target.value)}
            placeholder="Refine this panel…"
            autoFocus
            className="w-full bg-transparent border-b border-border px-0 py-1 text-sm font-serif text-white placeholder:text-muted-foreground focus:outline-none focus:border-white transition-colors"
          />
        </form>
      )}

      {panel.note && (
        <div className="bg-[#111] text-muted-foreground px-4 py-1.5 editorial-label text-[8.5px] shrink-0 border-b border-border">
          {panel.note}
        </div>
      )}

      <div className="flex-1 overflow-hidden px-4 py-4 relative">
        {renderContent()}
      </div>
    </div>
  );
}
