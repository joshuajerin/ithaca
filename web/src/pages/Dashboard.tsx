import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Dashboard as TerminalDashboard } from "../components/terminal/Dashboard";
import type { DashboardSpec, Panel, PanelLayout } from "../terminalCompat/api-client-react";

const DEFAULT_PROMPT = "what does nvda look like";
const PRESETS = [
  "what's the news",
  "show analyst ratings",
  "order book and trade flow",
  "macro dashboard",
  "retail analysis",
];

export function Dashboard() {
  const [command, setCommand] = useState(DEFAULT_PROMPT);
  const [activePrompt, setActivePrompt] = useState(DEFAULT_PROMPT);
  const [dashboard, setDashboard] = useState<DashboardSpec>(() => buildDashboard(DEFAULT_PROMPT));
  const [highlightedPanelId, setHighlightedPanelId] = useState<string | null>(dashboard.panels[0]?.id ?? null);

  useEffect(() => {
    if (!highlightedPanelId) return;
    const timer = window.setTimeout(() => setHighlightedPanelId(null), 1400);
    return () => window.clearTimeout(timer);
  }, [highlightedPanelId]);

  const panelSummary = useMemo(() => {
    const types = dashboard.panels.map((panel) => panel.type.replace(/_/g, " "));
    return types.join(" / ");
  }, [dashboard.panels]);

  const runCommand = (nextCommand: string) => {
    const trimmed = nextCommand.trim() || DEFAULT_PROMPT;
    const next = buildDashboard(trimmed);
    setActivePrompt(trimmed);
    setCommand(trimmed);
    setDashboard(next);
    setHighlightedPanelId(next.panels[0]?.id ?? null);
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    runCommand(command);
  };

  const handlePanelRefined = (updatedPanel: Panel) => {
    if (!updatedPanel || updatedPanel.type === "__noop_refine__") return;
    setDashboard((current) => ({
      ...current,
      panels: current.panels.map((panel) =>
        panel.id === updatedPanel.id
          ? { ...panel, ...updatedPanel, layout: updatedPanel.layout ?? panel.layout }
          : panel,
      ),
    }));
    setHighlightedPanelId(updatedPanel.id);
  };

  const handlePanelResized = (panelId: string, size: { w: number; h: number }) => {
    setDashboard((current) => ({
      ...current,
      panels: current.panels.map((panel) =>
        panel.id === panelId
          ? { ...panel, layout: { ...panel.layout, w: size.w, h: size.h } }
          : panel,
      ),
    }));
  };

  return (
    <div className="page terminal-page">
      <div className="terminal-workspace">
        <section className="terminal-commandbar">
          <div>
            <div className="terminal-command-meta">Doomberg terminal / prompt routes panels</div>
            <form className="terminal-command-form" onSubmit={handleSubmit}>
              <input
                className="terminal-command-input"
                value={command}
                onChange={(event) => setCommand(event.target.value)}
                placeholder="Ask for news, analysis, order book, macro, ratings..."
              />
              <button className="btn primary" type="submit">Run</button>
            </form>
          </div>
          <div className="terminal-command-side">
            {PRESETS.map((preset) => (
              <button
                className="terminal-example"
                key={preset}
                type="button"
                onClick={() => runCommand(preset)}
              >
                {preset}
              </button>
            ))}
          </div>
        </section>

        <section className="terminal-canvas-shell">
          <div className="terminal-canvas-head">
            <div>
              <div className="terminal-canvas-title">Doomberg Terminal</div>
              <div className="terminal-canvas-sub">{dashboard.title}</div>
            </div>
            <div className="terminal-canvas-stats">
              <span>{dashboard.panels.length} panels</span>
              <span>{panelSummary}</span>
            </div>
          </div>

          <TerminalDashboard
            dashboard={dashboard}
            highlightedPanelId={highlightedPanelId}
            onPanelRefined={handlePanelRefined}
            onPanelResized={handlePanelResized}
          />
        </section>

        <div className="terminal-prompt-strip">
          <span><strong>User:</strong> {activePrompt}</span>
          <span>{dashboard.sessionId}</span>
        </div>
      </div>
    </div>
  );
}

function buildDashboard(prompt: string): DashboardSpec {
  const now = new Date().toISOString();
  const query = prompt.toLowerCase();
  const sessionId = `terminal-${slug(prompt)}`;

  if (/(news|headline|headlines|catalyst|catalysts)/.test(query)) {
    return {
      sessionId,
      title: "News-driven workspace",
      panels: [
        panel("news-main", "news", "Live News Tape", layout(0, 0, 5, 4), newsData(), now),
        panel("news-analysis", "analysis", "Catalyst Analysis", layout(5, 0, 4, 4), analysisData("news"), now),
        panel("news-sentiment", "sentiment", "Narrative Sentiment", layout(9, 0, 3, 4), sentimentData(), now),
        panel("news-price", "price_chart", "NVDA Price Reaction", layout(0, 4, 7, 3), priceData(), now),
        panel("news-macro", "macro_dashboard", "Macro Tape", layout(7, 4, 5, 3), macroData(), now),
      ],
    };
  }

  if (/(rating|ratings|analyst|target|upgrade|downgrade)/.test(query)) {
    return {
      sessionId,
      title: "Analyst ratings workspace",
      panels: [
        panel("ratings-panel", "analyst_ratings", "Consensus and Targets", layout(0, 0, 4, 4), analystRatingsData(), now),
        panel("ratings-analysis", "analysis", "Street Setup", layout(4, 0, 4, 4), analysisData("ratings"), now),
        panel("ratings-fundamentals", "fundamentals", "Fundamentals Snapshot", layout(8, 0, 4, 4), fundamentalsData(), now),
        panel("ratings-comparison", "comparison", "Peer Comparison", layout(0, 4, 6, 3), comparisonData(), now),
        panel("ratings-news", "news", "Recent Rating Notes", layout(6, 4, 6, 3), newsData(), now),
      ],
    };
  }

  if (/(order|book|flow|tape|dark|block|trade)/.test(query)) {
    return {
      sessionId,
      title: "Market microstructure workspace",
      panels: [
        panel("flow-book", "order_book", "Order Book Replay", layout(0, 0, 5, 4), orderBookData(), now),
        panel("flow-trades", "trade_flow", "Trade Flow", layout(5, 0, 4, 4), tradeFlowData(), now),
        panel("flow-price", "price_chart", "Intraday Price", layout(9, 0, 3, 4), priceData("NVDA", "1D"), now),
        panel("flow-news", "news", "Tape Catalysts", layout(0, 4, 6, 3), newsData(), now),
        panel("flow-analysis", "analysis", "Liquidity Read", layout(6, 4, 6, 3), analysisData("flow"), now),
      ],
    };
  }

  if (/(macro|rates|yield|dollar|oil|fx|regime)/.test(query)) {
    return {
      sessionId,
      title: "Macro terminal workspace",
      panels: [
        panel("macro-main", "macro_dashboard", "Cross-Asset Macro Dashboard", layout(0, 0, 8, 4), macroData(), now),
        panel("macro-analysis", "analysis", "Regime Read", layout(8, 0, 4, 4), analysisData("macro"), now),
        panel("macro-news", "news", "Macro Headlines", layout(0, 4, 4, 3), newsData(), now),
        panel("macro-sentiment", "sentiment", "Risk Sentiment", layout(4, 4, 4, 3), sentimentData("Macro"), now),
        panel("macro-screen", "screener", "Macro-Sensitive Movers", layout(8, 4, 4, 3), screenerData(), now),
      ],
    };
  }

  if (/(retail|consumer|store|shopping|ecommerce|demand)/.test(query)) {
    return {
      sessionId,
      title: "Retail analysis workspace",
      panels: [
        panel("retail-analysis", "analysis", "Retail Demand Analysis", layout(0, 0, 5, 4), analysisData("retail"), now),
        panel("retail-screen", "screener", "Retail Watchlist", layout(5, 0, 4, 4), screenerData("Retail watchlist"), now),
        panel("retail-sentiment", "sentiment", "Consumer Sentiment", layout(9, 0, 3, 4), sentimentData("Retail"), now),
        panel("retail-comparison", "comparison", "Peer Basket", layout(0, 4, 6, 3), comparisonData(), now),
        panel("retail-news", "news", "Retail Headlines", layout(6, 4, 6, 3), newsData(), now),
      ],
    };
  }

  return {
    sessionId,
    title: "General terminal workspace",
    panels: [
      panel("main-price", "price_chart", "NVDA Price Chart", layout(0, 0, 8, 3), priceData(), now),
      panel("main-ratings", "analyst_ratings", "Analyst Ratings", layout(8, 0, 4, 3), analystRatingsData(), now),
      panel("main-news", "news", "News", layout(0, 3, 4, 3), newsData(), now),
      panel("main-analysis", "analysis", "Analysis", layout(4, 3, 4, 3), analysisData("default"), now),
      panel("main-sentiment", "sentiment", "Sentiment", layout(8, 3, 4, 3), sentimentData(), now),
      panel("main-macro", "macro_dashboard", "Macro Dashboard", layout(0, 6, 8, 3), macroData(), now),
      panel("main-flow", "trade_flow", "Trade Flow", layout(8, 6, 4, 3), tradeFlowData(), now),
    ],
  };
}

function panel(id: string, type: string, title: string, panelLayout: PanelLayout, data: unknown, asOf: string): Panel {
  return {
    id,
    type,
    title,
    layout: panelLayout,
    status: "ok",
    source: "sample",
    asOf,
    data,
  };
}

function layout(x: number, y: number, w: number, h: number): PanelLayout {
  return { x, y, w, h };
}

function priceData(symbol = "NVDA", range = "1M") {
  const base = range === "1D" ? 142.1 : 126.4;
  const points = Array.from({ length: range === "1D" ? 24 : 34 }, (_, index) => {
    const drift = index * 0.54;
    const wave = Math.sin(index / 2.4) * 2.2 + Math.cos(index / 4.1) * 1.4;
    const date = new Date(Date.now() - (33 - index) * 86400000);
    if (range === "1D") date.setHours(9 + Math.floor(index / 2), index % 2 ? 30 : 0, 0, 0);
    return { t: range === "1D" ? date.toISOString() : date.toISOString().slice(5, 10), c: base + drift + wave };
  });
  const first = points[0].c;
  const last = points[points.length - 1].c;

  return {
    symbol,
    name: "NVIDIA Corporation",
    currency: "USD",
    range,
    ranges: ["1D", "1W", "1M", "3M", "6M", "1Y"],
    last,
    change: last - first,
    changePct: ((last - first) / first) * 100,
    points,
  };
}

function newsData() {
  return {
    scope: "NVDA / AI infrastructure",
    items: [
      {
        id: "n1",
        source: "Doomberg Wire",
        sentiment: "positive",
        tickers: ["NVDA", "SMH"],
        headline: "AI server demand keeps accelerator backlog tight into next quarter",
        summary: "Channel checks point to stronger rack-level bookings and little evidence of pricing pressure across the newest accelerator stack.",
        publishedAt: new Date(Date.now() - 18 * 60000).toISOString(),
        url: null,
      },
      {
        id: "n2",
        source: "Market Desk",
        sentiment: "neutral",
        tickers: ["NVDA", "AMD"],
        headline: "Semiconductor tape pauses as rates and dollar strength pressure high multiple growth",
        summary: "Traders flagged a macro-led reset rather than a company-specific data point, with options flow still skewed toward upside call spreads.",
        publishedAt: new Date(Date.now() - 47 * 60000).toISOString(),
        url: null,
      },
      {
        id: "n3",
        source: "Supply Chain",
        sentiment: "positive",
        tickers: ["TSM", "NVDA"],
        headline: "Advanced packaging utilization remains the key constraint for hyperscaler GPU ramps",
        summary: "The bottleneck has shifted from chip allocation to full system integration, keeping lead times elevated for top cloud buyers.",
        publishedAt: new Date(Date.now() - 86 * 60000).toISOString(),
        url: null,
      },
      {
        id: "n4",
        source: "Policy Monitor",
        sentiment: "negative",
        tickers: ["NVDA"],
        headline: "Export-control headlines add another risk premium to forward China revenue assumptions",
        summary: "The market is treating the latest policy language as manageable, but desk commentary notes lower visibility around replacement SKUs.",
        publishedAt: new Date(Date.now() - 122 * 60000).toISOString(),
        url: null,
      },
    ],
  };
}

function analysisData(mode: string) {
  const copy: Record<string, { headline: string; summary: string; bullets: string[]; stance: "bullish" | "neutral" | "bearish"; scope: string }> = {
    news: {
      scope: "Catalyst",
      headline: "The tape is rewarding supply certainty, not just headline demand",
      summary: "The useful read is not that AI demand is high. The useful read is that the supply chain still cannot clear the highest-end configurations fast enough, which keeps gross-margin risk contained unless macro forces a broader multiple reset.",
      stance: "bullish",
      bullets: [
        "Backlog commentary is centered on full rack availability rather than single-chip inventory.",
        "Negative policy headlines are being absorbed as mix risk, not an immediate demand break.",
        "Options flow remains asymmetric but less crowded than the last earnings window.",
      ],
    },
    ratings: {
      scope: "Street",
      headline: "The analyst debate has shifted from TAM to cadence",
      summary: "Consensus is no longer arguing whether the accelerator cycle exists. The sharper question is how quickly product cadence and packaging capacity can defend the premium multiple.",
      stance: "neutral",
      bullets: [
        "Most upgrades are target-price revisions rather than fresh thesis changes.",
        "The downside case is multiple compression if growth decelerates before capex budgets reset.",
        "High target dispersion signals confidence in the cycle but disagreement on normalized margins.",
      ],
    },
    flow: {
      scope: "Tape",
      headline: "Block prints show buyers defending pullbacks",
      summary: "The order book is not one-way, but the larger prints cluster near bid support rather than chase strength. That usually points to accumulation, not a clean momentum breakout.",
      stance: "bullish",
      bullets: [
        "Dark-pool share is elevated but not extreme for a mega-cap semiconductor name.",
        "The bid stack rebuilds quickly after sweeps, suggesting real demand under the market.",
        "A break below the first volume shelf would turn the read neutral quickly.",
      ],
    },
    macro: {
      scope: "Macro",
      headline: "Growth leadership can hold while rates stay contained",
      summary: "The cross-asset board is consistent with a soft-landing tape: credit is calm, oil is firm but not disorderly, and the dollar is not yet strong enough to force a broad risk-off rotation.",
      stance: "neutral",
      bullets: [
        "Rates remain the main constraint on duration-sensitive equity leadership.",
        "Credit spreads are not confirming stress.",
        "Oil strength is inflationary at the margin but not yet a demand shock.",
      ],
    },
    retail: {
      scope: "Retail",
      headline: "Demand is becoming more selective, not uniformly weak",
      summary: "Retail analysis should split traffic, ticket, and margin. The broad consumer is slowing, but the winners are names with pricing discipline and inventory control rather than the highest same-store sales prints.",
      stance: "neutral",
      bullets: [
        "Promotion intensity matters more than headline revenue growth.",
        "Higher-income baskets continue to hold up better than discretionary value traffic.",
        "The cleanest panel mix is news, peer comparison, sentiment, and a live screener.",
      ],
    },
    default: {
      scope: "Equity",
      headline: "NVDA still screens as the market's cleanest AI infrastructure proxy",
      summary: "The dashboard is intentionally composed from the old terminal widgets: chart, ratings, news, analysis, sentiment, macro, and flow. Commands reshape the canvas by swapping in the subwidgets that match the requested workflow.",
      stance: "bullish",
      bullets: [
        "The visible UI is the copied old terminal panel system, not screenshots.",
        "Hover the panel chrome to see refine/export controls and border changes.",
        "Submit a prompt to repopulate the grid with the matching panel workflow.",
      ],
    },
  };

  const selected = copy[mode] ?? copy.default;
  return { confidence: 0.78, ...selected };
}

function analystRatingsData() {
  return {
    symbol: "NVDA",
    name: "NVIDIA Corporation",
    covered: true,
    consensus: {
      label: "Strong Buy",
      mean: 4.74,
      numAnalysts: 48,
      distribution: { strongBuy: 31, buy: 12, hold: 5, sell: 0, strongSell: 0 },
    },
    priceTarget: {
      current: 147.62,
      mean: 176.25,
      high: 210,
      low: 125,
      median: 178,
      impliedUpsidePct: 19.4,
    },
    changes: [
      { date: "Jun 21", firm: "Morgan Stanley", action: "upgrade", fromGrade: "Equal Weight", toGrade: "Overweight" },
      { date: "Jun 18", firm: "BofA", action: "reiterate", fromGrade: "Buy", toGrade: "Buy" },
      { date: "Jun 12", firm: "UBS", action: "upgrade", fromGrade: "Neutral", toGrade: "Buy" },
    ],
  };
}

function sentimentData(scope = "NVDA") {
  return {
    scope,
    label: "constructive",
    overall: 0.42,
    sources: [
      { channel: "News", score: 0.58 },
      { channel: "Options", score: 0.34 },
      { channel: "Social", score: 0.22 },
      { channel: "Analyst", score: 0.61 },
    ],
    trend: Array.from({ length: 18 }, (_, index) => ({
      t: `${index + 1}`,
      score: 0.12 + Math.sin(index / 2.2) * 0.16 + index * 0.018,
    })),
  };
}

function macroData() {
  const tiles = (symbols: string[], base: number) =>
    symbols.map((symbol, index) => ({
      symbol,
      name: ["10Y Treasury", "Dollar Index", "WTI Crude", "Nasdaq 100", "Gold"][index] ?? symbol,
      price: base + index * 17.8,
      changePct: [0.06, -0.18, 1.14, 0.72, -0.22][index] ?? 0,
      unit: index === 0 ? "%" : index === 1 ? "FX" : "",
      isLive: index % 2 === 0,
      sparkline: Array.from({ length: 18 }, (_, i) => base + Math.sin(i / 2 + index) * 2 + i * 0.25),
    }));

  return {
    regime: {
      label: "soft_landing",
      headline: "Soft landing",
      rationale: "Rates contained, credit calm, growth leadership intact.",
    },
    groups: [
      { label: "Rates", tiles: tiles(["US10Y", "US02Y", "MOVE"], 4.2) },
      { label: "FX", tiles: tiles(["DXY", "EURUSD", "USDJPY"], 101.4) },
      { label: "Commodities", tiles: tiles(["WTI", "GOLD", "COPPER"], 76.2) },
      { label: "Equities", tiles: tiles(["NDX", "SPX", "RUT"], 5200) },
    ],
  };
}

function tradeFlowData() {
  const prints = Array.from({ length: 34 }, (_, index) => ({
    time: `${9 + Math.floor(index / 6)}:${String((index * 7) % 60).padStart(2, "0")}`,
    price: 144 + Math.sin(index / 2.8) * 1.8 + index * 0.08,
    size: 8000 + index * 2400,
    side: index % 3 === 0 ? "sell" : "buy",
    isBlock: index % 8 === 0,
    isDark: index % 5 === 0,
    venue: index % 5 === 0 ? "DARK" : "NASDAQ",
  }));
  return {
    symbol: "NVDA",
    buyImbalance: 0.64,
    totalVolume: 48300000,
    darkPoolPct: 42.6,
    blockThreshold: 100000,
    prints,
  };
}

function orderBookData() {
  const makeFrame = (index: number) => {
    const mid = 146.2 + index * 0.09;
    return {
      time: `10:${String(12 + index * 3).padStart(2, "0")}`,
      lastPrice: mid,
      spread: 0.08 + (index % 3) * 0.01,
      bids: Array.from({ length: 8 }, (_, level) => ({
        price: mid - 0.04 - level * 0.06,
        size: 14000 + level * 5200 + index * 300,
        depth: 0.95 - level * 0.09,
      })),
      asks: Array.from({ length: 8 }, (_, level) => ({
        price: mid + 0.04 + level * 0.06,
        size: 12000 + level * 4700 + index * 260,
        depth: 0.88 - level * 0.08,
      })),
      tape: Array.from({ length: 12 }, (_, trade) => ({
        time: `10:${String(12 + index * 3).padStart(2, "0")}:${String(trade * 5).padStart(2, "0")}`,
        price: mid + Math.sin(trade / 2) * 0.16,
        size: 900 + trade * 850,
        side: trade % 3 === 0 ? "sell" : "buy",
        venue: trade % 4 === 0 ? "IEX" : "NSDQ",
        isBlock: trade === 4,
        isSweep: trade === 7,
      })),
    };
  };

  return {
    symbol: "NVDA",
    replayReal: false,
    coverage: "Simulated depth seeded from terminal sample data",
    frames: Array.from({ length: 7 }, (_, index) => makeFrame(index)),
    events: [
      { pos: 0.22, type: "block", time: "10:18", side: "buy", size: 126000, price: 146.4 },
      { pos: 0.62, type: "sweep", time: "10:28", side: "buy", size: 82000, price: 147.1 },
    ],
    sessionStart: "10:12",
    sessionEnd: "10:30",
  };
}

function screenerData(title = "AI infrastructure watchlist") {
  return {
    title,
    rows: [
      { symbol: "NVDA", subIndustry: "GPUs", price: 147.62, changePct: 1.84, ret1Y: 178.2, marketCap: 3620000000000, volume: 48300000, peRatio: 48.5 },
      { symbol: "AMD", subIndustry: "Accelerators", price: 168.2, changePct: 0.92, ret1Y: 64.8, marketCap: 272000000000, volume: 28600000, peRatio: 41.1 },
      { symbol: "AVGO", subIndustry: "ASICs", price: 1846.4, changePct: 1.21, ret1Y: 88.4, marketCap: 858000000000, volume: 4200000, peRatio: 37.8 },
      { symbol: "TSM", subIndustry: "Foundry", price: 188.7, changePct: -0.36, ret1Y: 52.5, marketCap: 978000000000, volume: 9800000, peRatio: 29.2 },
      { symbol: "SMCI", subIndustry: "Servers", price: 51.18, changePct: 2.42, ret1Y: -38.7, marketCap: 30000000000, volume: 17100000, peRatio: 18.4 },
    ],
  };
}

function comparisonData() {
  return {
    title: "AI peer comparison",
    metricLabels: ["1D", "1Y", "Gross Margin", "Fwd P/E", "Revenue Growth", "FCF Yield"],
    companies: [
      { symbol: "NVDA", values: [{ value: "+1.8%" }, { value: "+178%" }, { value: "76.0%" }, { value: "48.5x" }, { value: "+126%" }, { value: "2.8%" }] },
      { symbol: "AMD", values: [{ value: "+0.9%" }, { value: "+65%" }, { value: "51.0%" }, { value: "41.1x" }, { value: "+22%" }, { value: "1.4%" }] },
      { symbol: "AVGO", values: [{ value: "+1.2%" }, { value: "+88%" }, { value: "74.2%" }, { value: "37.8x" }, { value: "+44%" }, { value: "3.6%" }] },
      { symbol: "TSM", values: [{ value: "-0.4%" }, { value: "+53%" }, { value: "54.0%" }, { value: "29.2x" }, { value: "+31%" }, { value: "3.1%" }] },
    ],
  };
}

function fundamentalsData() {
  return {
    symbol: "NVDA",
    name: "NVIDIA Corporation",
    metrics: [
      { label: "Revenue TTM", value: "$130.5B", change: 114.2, hint: "Trailing twelve month revenue" },
      { label: "Gross Margin", value: "76.0%", change: 4.1 },
      { label: "FCF Margin", value: "43.8%", change: 8.3 },
      { label: "Forward P/E", value: "48.5x", change: -6.2 },
      { label: "Net Cash", value: "$24.7B" },
      { label: "Data Center Mix", value: "87%", change: 12.8 },
      { label: "Capex Beta", value: "High" },
      { label: "Revision Trend", value: "Positive", change: 9.4 },
    ],
  };
}

function slug(input: string) {
  const value = input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 42);
  return value || "dashboard";
}
