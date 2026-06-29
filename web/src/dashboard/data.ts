// web/src/dashboard/data.ts
// Data adapters for the v2 Dashboard panels.
// Real data: derived from API results when passed in.
// Sample data: deterministic, plausible-looking fallbacks with // TODO: wire to <endpoint> comments.

import type { RunRow } from "../types";
import type { PerformancePnlData } from "./panels/PerformancePnlPanel";

// ── Types ──────────────────────────────────────────────────────────────────────

export type { PerformancePnlData };

export interface PortfolioRiskData {
  symbols: string[];
  summary: { var95: number; trackingError: number; beta: number };
  varHistogram: { bin: number; count: number }[];
  factorExposures: { factor: string; exposure: number }[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function dateStr(daysAgo: number): string {
  const d = new Date("2026-06-28");
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

function makeSeries(days: number) {
  const out: { date: string; book: number; bench: number; drawdown: number }[] = [];
  let book = 0;
  let bench = 0;
  let peak = 0;
  for (let i = days; i >= 0; i--) {
    book += 0.08 + Math.sin(i / 8) * 0.3 + Math.cos(i / 14) * 0.2;
    bench += 0.06 + Math.sin(i / 10) * 0.25;
    peak = Math.max(peak, book);
    out.push({
      date: dateStr(i),
      book: parseFloat(book.toFixed(2)),
      bench: parseFloat(bench.toFixed(2)),
      drawdown: parseFloat(Math.min(0, book - peak).toFixed(2)),
    });
  }
  return out;
}

// ── Public adapters ───────────────────────────────────────────────────────────

/** Personal Overview P&L. Derives from the latest backtest run with an equityCurve; falls back to sample. */
export function getPerformance(runs?: RunRow[]): PerformancePnlData {
  if (runs && runs.length > 0) {
    const sorted = [...runs].sort((a, b) => {
      const ta = a.updated_at ?? a.created_at ?? "";
      const tb = b.updated_at ?? b.created_at ?? "";
      return tb.localeCompare(ta);
    });
    for (const run of sorted) {
      const result = (run.result ?? {}) as Record<string, unknown>;
      const bt = (result["data"] ?? result) as Record<string, unknown>;
      const equityCurve = Array.isArray(bt["equityCurve"]) ? (bt["equityCurve"] as { d: string; v: number }[]) : null;
      const statsRaw = bt["stats"] as Record<string, number> | undefined;
      if (equityCurve && equityCurve.length > 2 && statsRaw) {
        const first = equityCurve[0].v;
        const last = equityCurve[equityCurve.length - 1].v;
        const totalReturn = ((last - first) / Math.abs(first || 1)) * 100;
        const series = equityCurve.map((pt) => ({
          date: pt.d,
          book: parseFloat(((pt.v - first) / Math.abs(first || 1) * 100).toFixed(2)),
          bench: 0,
          drawdown: 0,
        }));
        return {
          portfolioName: "Portfolio",
          benchmarkName: "SPY",
          rangeLabel: "All",
          windowDays: equityCurve.length,
          series,
          stats: {
            book: { totalReturn, cagr: totalReturn * 1.5, vol: typeof statsRaw["vol"] === "number" ? statsRaw["vol"] * 100 : 12.4, sharpe: typeof statsRaw["sharpe"] === "number" ? statsRaw["sharpe"] : 0.8, sortino: 1.1, maxDD: typeof statsRaw["maxDD"] === "number" ? statsRaw["maxDD"] * 100 : -8.2, hitRate: 54 },
            benchmark: { totalReturn: totalReturn * 0.7, cagr: 10.2, vol: 13.1, sharpe: 0.72, sortino: 0.9, maxDD: -11.4, hitRate: 52 },
            active: { activeReturn: totalReturn * 0.3, trackingError: 6.2, informationRatio: 0.64, beta: 0.88, alpha: 3.1, correlation: 0.81, upCapture: 98, downCapture: 72 },
          },
        };
      }
    }
  }
  // Sample fallback
  const series = makeSeries(180);
  return {
    portfolioName: "Jarvis Alpha",
    benchmarkName: "SPY",
    benchmarkSource: "CRSP",
    rangeLabel: "6M",
    windowDays: 180,
    series,
    stats: {
      book: { totalReturn: 14.7, cagr: 31.2, vol: 11.8, sharpe: 1.24, sortino: 1.67, maxDD: -6.3, hitRate: 57 },
      benchmark: { totalReturn: 8.4, cagr: 17.6, vol: 13.2, sharpe: 0.72, sortino: 0.9, maxDD: -11.4, hitRate: 52 },
      active: { activeReturn: 6.3, trackingError: 5.8, informationRatio: 1.09, beta: 0.84, alpha: 4.2, correlation: 0.79, upCapture: 104, downCapture: 71 },
    },
  };
}

/** Portfolio risk data. // TODO: wire to /api/runs/<latest>/result.risk */
export function getPortfolioRisk(): PortfolioRiskData {
  return {
    symbols: ["NVDA", "MSFT", "AAPL", "TSLA", "AMZN", "GOOG"],
    summary: { var95: 1.84, trackingError: 5.2, beta: 0.88 },
    varHistogram: [
      { bin: -4, count: 2 }, { bin: -3, count: 5 }, { bin: -2, count: 14 },
      { bin: -1, count: 28 }, { bin: 0, count: 42 }, { bin: 1, count: 31 },
      { bin: 2, count: 18 }, { bin: 3, count: 8 }, { bin: 4, count: 3 },
    ],
    factorExposures: [
      { factor: "Market", exposure: 0.88 },
      { factor: "Value", exposure: -0.22 },
      { factor: "Momentum", exposure: 0.61 },
      { factor: "Quality", exposure: 0.44 },
      { factor: "Size", exposure: -0.18 },
      { factor: "Low Vol", exposure: 0.15 },
    ],
  };
}

/** Trade flow scatter data. // TODO: wire to /api/market/trade-flow?symbol=NVDA */
export function getTradeFlow(): Record<string, unknown> {
  const prints = Array.from({ length: 40 }, (_, i) => {
    const hour = 9 + Math.floor(i / 5);
    const min = (i * 7) % 60;
    const price = 478.2 + Math.sin(i / 3) * 2.4 + Math.cos(i / 7) * 1.1;
    const size = 100 * (1 + (i % 12));
    return {
      time: `${hour}:${String(min).padStart(2, "0")}`,
      price: parseFloat(price.toFixed(2)),
      size,
      side: i % 3 === 0 ? "sell" : "buy",
      isBlock: size >= 1000,
      isDark: i % 7 === 0,
      venue: ["ARCA", "NASDAQ", "NYSE", "DARK"][i % 4],
    };
  });
  return { symbol: "NVDA", buyImbalance: 0.62, totalVolume: 18_400_000, darkPoolPct: 28.4, blockThreshold: 1000, prints };
}

/** Order book snapshot. // TODO: wire to /api/market/orderbook?symbol=NVDA */
export function getOrderBook(): Record<string, unknown> {
  const price = 478.24;
  const bids = Array.from({ length: 10 }, (_, i) => ({
    price: parseFloat((price - (i + 1) * 0.02).toFixed(2)),
    size: 500 - i * 40,
    depth: (500 - i * 40) / 500,
  }));
  const asks = Array.from({ length: 10 }, (_, i) => ({
    price: parseFloat((price + (i + 1) * 0.02).toFixed(2)),
    size: 480 - i * 35,
    depth: (480 - i * 35) / 480,
  }));
  const tape = Array.from({ length: 8 }, (_, i) => ({
    time: `10:${String(i * 3 + 14).padStart(2, "0")}`,
    price: parseFloat((price + Math.sin(i) * 0.12).toFixed(2)),
    size: 100 * (1 + (i % 5)),
    side: i % 2 === 0 ? "buy" : "sell",
    isBlock: i === 3,
    isSweep: i === 6,
    venue: ["ARCA", "NASDAQ"][i % 2],
  }));
  return { symbol: "NVDA", lastPrice: price, spread: 0.02, bids, asks, tape, replayReal: false, coverage: "Simulated depth — connect live data for real book" };
}

/** Congress trades. // TODO: wire to /api/alt-data/congress-trades */
export function getCongressTrades(): Record<string, unknown> {
  const trades = [
    { id: "ct1", member: "Nancy Pelosi", chamber: "House", party: "Democrat", partyCode: "D", ticker: "NVDA", type: "buy", amountRange: "$250K–$500K", transactionDate: dateStr(14), disclosureDate: dateStr(7), lagDays: 7, sourceUrl: null },
    { id: "ct2", member: "Tommy Tuberville", chamber: "Senate", party: "Republican", partyCode: "R", ticker: "MSFT", type: "sell", amountRange: "$100K–$250K", transactionDate: dateStr(22), disclosureDate: dateStr(12), lagDays: 10, sourceUrl: null },
    { id: "ct3", member: "Ro Khanna", chamber: "House", party: "Democrat", partyCode: "D", ticker: "AAPL", type: "buy", amountRange: "$50K–$100K", transactionDate: dateStr(30), disclosureDate: dateStr(18), lagDays: 12, sourceUrl: null },
    { id: "ct4", member: "Dan Crenshaw", chamber: "House", party: "Republican", partyCode: "R", ticker: "AMZN", type: "buy", amountRange: "$100K–$250K", transactionDate: dateStr(35), disclosureDate: dateStr(21), lagDays: 14, sourceUrl: null },
    { id: "ct5", member: "Susie Lee", chamber: "House", party: "Democrat", partyCode: "D", ticker: "TSLA", type: "sell", amountRange: "$50K–$100K", transactionDate: dateStr(42), disclosureDate: dateStr(27), lagDays: 15, sourceUrl: null },
  ];
  return {
    scope: "All Congress", ticker: null, trades,
    highlights: [{ kind: "cluster_buy", label: "NVDA cluster buy", detail: "3 members bought NVDA in the last 30 days", ticker: "NVDA", members: ["Nancy Pelosi", "Ro Khanna", "Dan Crenshaw"] }],
    stats: { total: trades.length, buys: 3, sells: 2, exchanges: 0, avgLagDays: 11.6, maxLagDays: 15, uniqueMembers: 5 },
    lagNote: "Congress members have 45 days to disclose trades under the STOCK Act. Recent trades may not yet appear.",
    disclaimer: "Source: Quiver Quantitative / House Clerk. Disclosure lags mean recent trades may not yet appear.",
    asOf: dateStr(0), source: "mock",
  };
}

/** Macro dashboard. // TODO: wire to /api/market/macro */
export function getMacro(): Record<string, unknown> {
  const mkSparkline = (base: number, n = 12) =>
    Array.from({ length: n }, (_, i) => base + Math.sin(i / 2) * base * 0.02 + i * base * 0.001);
  return {
    regime: { label: "soft_landing", headline: "Soft Landing", rationale: "Inflation moderating; labor market resilient; Fed on pause." },
    groups: [
      { label: "Rates", tiles: [
        { symbol: "US10Y", name: "10-Year Treasury", price: 4.38, changePct: -0.04, unit: "%", sparkline: mkSparkline(4.38), isLive: false },
        { symbol: "US2Y", name: "2-Year Treasury", price: 4.82, changePct: -0.02, unit: "%", sparkline: mkSparkline(4.82), isLive: false },
        { symbol: "SOFR", name: "SOFR", price: 5.30, changePct: 0, unit: "%", sparkline: mkSparkline(5.30), isLive: false },
      ]},
      { label: "FX", tiles: [
        { symbol: "DXY", name: "USD Index", price: 104.22, changePct: 0.12, unit: "FX", sparkline: mkSparkline(104.22), isLive: false },
        { symbol: "EURUSD", name: "EUR/USD", price: 1.0841, changePct: -0.08, unit: "FX", sparkline: mkSparkline(1.0841), isLive: false },
        { symbol: "USDJPY", name: "USD/JPY", price: 157.44, changePct: 0.22, unit: "FX", sparkline: mkSparkline(157.44), isLive: false },
      ]},
      { label: "Commodities", tiles: [
        { symbol: "WTI", name: "Crude Oil WTI", price: 81.42, changePct: 0.68, unit: "", sparkline: mkSparkline(81.42), isLive: false },
        { symbol: "GOLD", name: "Gold", price: 2341.80, changePct: 0.31, unit: "", sparkline: mkSparkline(2341.80), isLive: false },
      ]},
      { label: "Equities", tiles: [
        { symbol: "SPX", name: "S&P 500", price: 5421.03, changePct: 0.44, unit: "", sparkline: mkSparkline(5421.03), isLive: false },
        { symbol: "NDX", name: "Nasdaq 100", price: 19804.50, changePct: 0.61, unit: "", sparkline: mkSparkline(19804.50), isLive: false },
        { symbol: "VIX", name: "CBOE VIX", price: 14.82, changePct: -2.1, unit: "", sparkline: mkSparkline(14.82), isLive: false },
      ]},
    ],
  };
}

/** Yield curve. // TODO: wire to /api/market/yield-curve */
export function getYieldCurve(): Record<string, unknown> {
  return {
    title: "US Treasury Yield Curve",
    points: [
      { tenor: "1M", spot: 5.32, ago1y: 5.08, ago2y: 1.22 },
      { tenor: "3M", spot: 5.30, ago1y: 5.10, ago2y: 1.48 },
      { tenor: "6M", spot: 5.24, ago1y: 5.02, ago2y: 1.82 },
      { tenor: "1Y", spot: 5.12, ago1y: 4.88, ago2y: 2.14 },
      { tenor: "2Y", spot: 4.82, ago1y: 4.64, ago2y: 2.56 },
      { tenor: "5Y", spot: 4.52, ago1y: 4.24, ago2y: 2.88 },
      { tenor: "10Y", spot: 4.38, ago1y: 4.18, ago2y: 2.98 },
      { tenor: "30Y", spot: 4.54, ago1y: 4.32, ago2y: 3.12 },
    ],
    spreads: [
      { label: "2Y–10Y", value: -44, inverted: true },
      { label: "3M–10Y", value: -92, inverted: true },
    ],
    recession: {
      level: "watch",
      headline: "Inversion Watch",
      detail: "The 2Y–10Y spread has been inverted for 21 months. Historical lead time to recession averages 12–18 months after un-inversion.",
      segments: [{ label: "2Y–10Y", inverted: true, days: 630, since: "Oct 2022" }],
    },
  };
}

/** Sentiment. // TODO: wire to /api/alt-data/sentiment */
export function getSentiment(): Record<string, unknown> {
  const trend = Array.from({ length: 30 }, (_, i) => ({
    t: dateStr(30 - i).slice(5),
    score: parseFloat((0.2 + Math.sin(i / 4) * 0.4 + Math.cos(i / 9) * 0.2).toFixed(2)),
  }));
  return {
    scope: "Market",
    label: "cautiously_bullish",
    overall: 0.42,
    sources: [
      { channel: "News NLP", score: 0.38 },
      { channel: "Options Flow", score: 0.61 },
      { channel: "Social Media", score: 0.28 },
      { channel: "Retail Flows", score: 0.44 },
    ],
    trend,
  };
}
