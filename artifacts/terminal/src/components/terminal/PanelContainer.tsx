import React, { useState } from "react";
import type { Panel } from "@workspace/api-client-react";
import { useRefinePanel } from "@workspace/api-client-react";
import { Loader2, Maximize2, Minimize2, MoreHorizontal, Settings2, AlertTriangle } from "lucide-react";
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
import { BondRVPanel } from "./panels/BondRVPanel";
import { CDSPricerPanel } from "./panels/CDSPricerPanel";
import { CashFlowPanel } from "./panels/CashFlowPanel";
import { PortfolioRiskPanel } from "./panels/PortfolioRiskPanel";
import { BacktestPanel } from "./panels/BacktestPanel";
import { CorrelationMatrixPanel } from "./panels/CorrelationMatrixPanel";
import { FactorAnalysisPanel } from "./panels/FactorAnalysisPanel";

interface PanelContainerProps {
  panel: Panel;
  sessionId: string;
  onRefined: (updatedPanel: Panel) => void;
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

export function PanelContainer({ panel, sessionId, onRefined }: PanelContainerProps) {
  const [isRefining, setIsRefining] = useState(false);
  const [refineText, setRefineText] = useState("");
  
  const refineMutation = useRefinePanel();

  const handleRefine = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!refineText.trim()) {
      setIsRefining(false);
      return;
    }
    
    try {
      const result = await refineMutation.mutateAsync({
        data: {
          sessionId,
          panelId: panel.id,
          instruction: refineText
        }
      });
      onRefined(result);
      setIsRefining(false);
      setRefineText("");
    } catch (e) {
      console.error("Failed to refine panel", e);
    }
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
      case "price_chart": return <PriceChartPanel data={panel.data as any} />;
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
      case "bond_rv": return <BondRVPanel data={panel.data as any} />;
      case "cds_pricer": return <CDSPricerPanel data={panel.data as any} />;
      case "cashflow_duration": return <CashFlowPanel data={panel.data as any} />;
      case "portfolio_risk": return <PortfolioRiskPanel data={panel.data as any} />;
      case "backtest": return <BacktestPanel data={panel.data as any} />;
      case "correlation_matrix": return <CorrelationMatrixPanel data={panel.data as any} />;
      case "factor_analysis": return <FactorAnalysisPanel data={panel.data as any} />;
      default: return <div className="p-4 text-xs">Unknown panel type: {panel.type}</div>;
    }
  };

  return (
    <div className="bg-black border border-border flex flex-col overflow-hidden relative group h-full">
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
              {panel.source === "live" ? formatAsOf(panel.asOf) : "mock"}
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
