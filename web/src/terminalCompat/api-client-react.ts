import { useCallback, useState } from "react";

export type PanelType = string;
export type PanelStatus = "loading" | "ready" | "ok" | "error";

export interface PanelLayout {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Panel {
  id: string;
  type: PanelType;
  title: string;
  layout: PanelLayout;
  status: PanelStatus;
  data?: unknown;
  note?: string | null;
  source?: "live" | "cache" | "derived" | "sample" | string | null;
  asOf?: string | null;
}

export interface DashboardSpec {
  sessionId: string;
  title?: string;
  panels: Panel[];
}

export interface SavedDashboardMeta {
  id: string;
  title: string;
  updatedAt?: string | null;
  createdAt?: string | null;
}

export interface NavigationStop {
  panelId: string;
  label?: string;
  instruction?: string;
}

export interface NavigationTour {
  id: string;
  title: string;
  stops: NavigationStop[];
}

export interface NarrationSegment {
  id: string;
  text: string;
  panelId?: string | null;
}

export type PriceChartData = any;
export type NewsData = any;
export type AnalysisData = any;
export type FundamentalsData = any;
export type ScreenerData = any;
export type HeatmapData = any;
export type SentimentData = any;
export type ComparisonData = any;
export type PortfolioRiskData = any;
export type BacktestData = any;
export type MonteCarloData = any;
export type CorrelationMatrixData = any;
export type FactorAnalysisData = any;
export type RiskModelData = any;
export type FactorExposureData = any;
export type SignalResearchData = any;
export type SignalScoreRow = any;
export type SignalScorecardData = any;

type MutationArgs = {
  data?: {
    sessionId?: string;
    panelId?: string;
    instruction?: string;
    params?: Record<string, unknown>;
  };
};

export function useRefinePanel() {
  const [isPending, setIsPending] = useState(false);

  const mutateAsync = useCallback(async (args: MutationArgs = {}) => {
    setIsPending(true);
    try {
      await new Promise((resolve) => window.setTimeout(resolve, 180));
      const panelId = args.data?.panelId ?? "panel";
      const instruction = args.data?.instruction ?? "";
      const params = args.data?.params ?? {};
      const requestedRange = typeof params.range === "string"
        ? params.range
        : instruction.match(/\b(1D|1W|1M|3M|6M|1Y)\b/i)?.[1]?.toUpperCase();
      const requestedSymbol = typeof params.symbol === "string"
        ? params.symbol
        : instruction.match(/\b[A-Z]{1,5}\b/)?.[0] ?? "NVDA";

      if (requestedRange) {
        return {
          id: panelId,
          type: "price_chart",
          title: `${requestedSymbol} Price Chart`,
          status: "ok",
          source: "sample",
          asOf: new Date().toISOString(),
          data: makePriceData(requestedSymbol, requestedRange),
        } as Panel;
      }

      return {
        id: panelId,
        type: "__noop_refine__",
        title: "Refine request captured",
        status: "ok",
        data: {
          instruction: args.data?.instruction ?? null,
          params: args.data?.params ?? null,
          pending: false,
        },
      } as Panel;
    } finally {
      setIsPending(false);
    }
  }, []);

  return { isPending, mutateAsync };
}

export async function recomputeScenario(input: {
  symbols?: string[];
  horizonDays?: number;
  driftPct?: number;
  amount?: number;
}, _init?: RequestInit) {
  const horizon = Math.max(1, input.horizonDays ?? 30);
  const drift = input.driftPct ?? 0;
  const startValue = input.amount && input.amount > 0 ? input.amount : 100;
  const baselineEnd = startValue * 1.03;
  const scenarioEnd = startValue * (1 + drift / 100);
  const path = Array.from({ length: 8 }, (_, idx) => {
    const step = Math.round((idx / 7) * horizon);
    const t = idx / 7;
    return {
      step,
      baselineP50: startValue + (baselineEnd - startValue) * t,
      scenarioP50: startValue + (scenarioEnd - startValue) * t,
      baselineP5: startValue + (baselineEnd * 0.92 - startValue) * t,
      baselineP95: startValue + (baselineEnd * 1.08 - startValue) * t,
      scenarioP5: startValue + (scenarioEnd * 0.9 - startValue) * t,
      scenarioP95: startValue + (scenarioEnd * 1.1 - startValue) * t,
    };
  });

  return {
    projection: {
      horizon,
      method: "local dashboard projection",
      startValue,
      path,
      baseline: {
        expectedReturnPct: 3,
        endValue: baselineEnd,
        deltaPct: 3,
        probLossPct: 28,
      },
      scenario: {
        expectedReturnPct: drift,
        endValue: scenarioEnd,
        deltaPct: drift,
        probLossPct: drift < 0 ? 62 : 22,
      },
    },
  };
}

export function setBaseUrl() {
  return undefined;
}

export function setAuthTokenGetter() {
  return undefined;
}

function makePriceData(symbol: string, range: string) {
  const length = range === "1D" ? 24 : range === "1W" ? 20 : 34;
  const base = range === "1D" ? 142.1 : 126.4;
  const points = Array.from({ length }, (_, index) => {
    const drift = index * (range === "1D" ? 0.16 : 0.54);
    const wave = Math.sin(index / 2.4) * 2.2 + Math.cos(index / 4.1) * 1.4;
    const date = new Date(Date.now() - (length - index - 1) * 86400000);
    if (range === "1D") date.setHours(9 + Math.floor(index / 2), index % 2 ? 30 : 0, 0, 0);
    return {
      t: range === "1D" ? date.toISOString() : date.toISOString().slice(5, 10),
      c: base + drift + wave,
    };
  });
  const first = points[0].c;
  const last = points[points.length - 1].c;

  return {
    symbol,
    name: symbol === "NVDA" ? "NVIDIA Corporation" : `${symbol} instrument`,
    currency: "USD",
    range,
    ranges: ["1D", "1W", "1M", "3M", "6M", "1Y"],
    last,
    change: last - first,
    changePct: ((last - first) / first) * 100,
    points,
  };
}
