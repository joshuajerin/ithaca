import type { DashboardSpec } from "@workspace/api-client-react";

const now = new Date().toISOString();

const pricePoints = Array.from({ length: 28 }, (_, index) => {
  const date = new Date(Date.now() - (27 - index) * 60 * 60 * 1000);
  const drift = index * 0.44;
  const wave = Math.sin(index / 2.3) * 2.7 + Math.cos(index / 5) * 1.3;
  return { t: date.toISOString(), c: 124.6 + drift + wave };
});

const first = pricePoints[0].c;
const last = pricePoints[pricePoints.length - 1].c;

export const sampleDashboard: DashboardSpec = {
  sessionId: "dashboard",
  title: "Doomberg",
  panels: [
    {
      id: "price",
      type: "price_chart",
      title: "NVDA Price",
      status: "ok",
      source: "sample",
      asOf: now,
      layout: { x: 0, y: 0, w: 5, h: 3 },
      data: {
        symbol: "NVDA",
        name: "NVIDIA Corporation",
        currency: "USD",
        range: "1D",
        ranges: ["1D", "1W", "1M", "3M", "6M", "1Y"],
        last,
        change: last - first,
        changePct: ((last - first) / first) * 100,
        points: pricePoints,
      },
    },
    {
      id: "analysis",
      type: "analysis",
      title: "Thesis",
      status: "ok",
      source: "sample",
      asOf: now,
      layout: { x: 5, y: 0, w: 4, h: 3 },
      data: {
        scope: "NVDA",
        stance: "bullish",
        confidence: 0.74,
        headline: "Momentum remains intact",
        summary:
          "Revenue revisions, datacenter demand, and margin resilience keep the near-term setup constructive while valuation risk remains the main constraint.",
        bullets: [
          "Forward estimates are still moving higher after the latest datacenter checks.",
          "Gross margin pressure is contained by mix and supply discipline.",
          "Position sizing should account for crowded ownership and event risk.",
        ],
      },
    },
    {
      id: "sentiment",
      type: "sentiment",
      title: "Sentiment",
      status: "ok",
      source: "sample",
      asOf: now,
      layout: { x: 9, y: 0, w: 3, h: 3 },
      data: {
        scope: "NVDA",
        label: "positive",
        overall: 0.62,
        sources: [
          { channel: "News", score: 0.7 },
          { channel: "Social", score: 0.48 },
          { channel: "Analysts", score: 0.74 },
          { channel: "Options", score: 0.42 },
        ],
        trend: Array.from({ length: 18 }, (_, index) => ({
          t: `${index + 1}`,
          score: 0.25 + Math.sin(index / 2.2) * 0.18 + index * 0.022,
        })),
      },
    },
    {
      id: "news",
      type: "news",
      title: "News",
      status: "ok",
      source: "sample",
      asOf: now,
      layout: { x: 0, y: 3, w: 4, h: 3 },
      data: {
        scope: "NVDA",
        items: [
          {
            id: "n1",
            publishedAt: now,
            source: "MarketWatch",
            headline: "AI server checks point to resilient datacenter demand",
            summary: "Channel commentary continues to flag firm accelerator demand into the next quarter.",
            tickers: ["NVDA", "AMD"],
            sentiment: "positive",
          },
          {
            id: "n2",
            publishedAt: new Date(Date.now() - 80 * 60 * 1000).toISOString(),
            source: "Reuters",
            headline: "Chip suppliers weigh tighter export compliance",
            summary: "Policy uncertainty remains a watch item for high-end accelerator shipments.",
            tickers: ["NVDA"],
            sentiment: "neutral",
          },
          {
            id: "n3",
            publishedAt: new Date(Date.now() - 150 * 60 * 1000).toISOString(),
            source: "Bloomberg",
            headline: "Hyperscaler capex plans keep AI infrastructure bid",
            summary: "Large cloud buyers are still guiding to elevated infrastructure spending.",
            tickers: ["NVDA", "MSFT", "GOOGL"],
            sentiment: "positive",
          },
        ],
      },
    },
    {
      id: "heatmap",
      type: "heatmap",
      title: "Memory Map",
      status: "ok",
      source: "sample",
      asOf: now,
      layout: { x: 4, y: 3, w: 4, h: 3 },
      data: {
        title: "AI Infrastructure",
        cells: [
          { symbol: "NVDA", name: "NVIDIA", sector: "Semis", marketCap: 3150000000000, changePct: 2.1, ret1Y: 178 },
          { symbol: "AMD", name: "AMD", sector: "Semis", marketCap: 265000000000, changePct: 0.8, ret1Y: 54 },
          { symbol: "AVGO", name: "Broadcom", sector: "Semis", marketCap: 760000000000, changePct: 1.4, ret1Y: 82 },
          { symbol: "MSFT", name: "Microsoft", sector: "Cloud", marketCap: 3400000000000, changePct: 0.5, ret1Y: 31 },
          { symbol: "GOOGL", name: "Alphabet", sector: "Cloud", marketCap: 2250000000000, changePct: -0.2, ret1Y: 26 },
          { symbol: "TSM", name: "TSMC", sector: "Foundry", marketCap: 910000000000, changePct: 1.2, ret1Y: 64 },
        ],
      },
    },
    {
      id: "signals",
      type: "signal_scorecard",
      title: "Signals",
      status: "ok",
      source: "sample",
      asOf: now,
      layout: { x: 8, y: 3, w: 4, h: 3 },
      data: {
        universe: "US mega-cap tech",
        universeSize: 64,
        holding: 20,
        quantiles: 5,
        rows: [
          { rank: 1, signal: "rev_mom", label: "Revision Momentum", meanIC: 0.083, icIR: 1.42, tStat: 2.8, hitRate: 61, spreadReturn: 4.9, spreadSharpe: 1.6, turnover: 31, included: 64, spark: [1, 2, 3, 2.7, 4.1, 5.2] },
          { rank: 2, signal: "gross_margin", label: "Margin Surprise", meanIC: 0.051, icIR: 1.03, tStat: 2.1, hitRate: 57, spreadReturn: 2.8, spreadSharpe: 1.1, turnover: 24, included: 58, spark: [1, 1.5, 2.4, 2.2, 2.9, 3.3] },
          { rank: 3, signal: "quality", label: "Quality Carry", meanIC: 0.037, icIR: 0.82, tStat: 1.7, hitRate: 54, spreadReturn: 1.9, spreadSharpe: 0.8, turnover: 18, included: 64, spark: [1, 1.2, 1.1, 1.6, 1.8, 2.1] },
        ],
      },
    },
  ],
};
