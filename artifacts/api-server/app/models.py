"""Pydantic models mirroring the OpenAPI contract (camelCase JSON fields)."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel


class PanelType(str, Enum):
    price_chart = "price_chart"
    news = "news"
    analysis = "analysis"
    fundamentals = "fundamentals"
    screener = "screener"
    heatmap = "heatmap"
    sentiment = "sentiment"
    comparison = "comparison"
    order_book = "order_book"
    trade_flow = "trade_flow"
    tca_report = "tca_report"
    macro_dashboard = "macro_dashboard"


class PanelStatus(str, Enum):
    ok = "ok"
    loading = "loading"
    error = "error"


class PanelLayout(BaseModel):
    x: int
    y: int
    w: int
    h: int


# --- price_chart ---
class PricePoint(BaseModel):
    t: str
    o: float
    h: float
    l: float
    c: float
    v: float


class PriceChartData(BaseModel):
    symbol: str
    name: str
    currency: str
    last: float
    change: float
    changePct: float
    range: str
    points: List[PricePoint]


# --- news ---
class NewsItem(BaseModel):
    id: str
    headline: str
    source: str
    summary: str
    url: Optional[str] = None
    publishedAt: str
    sentiment: str  # positive | neutral | negative
    tickers: List[str]


class NewsData(BaseModel):
    scope: str
    items: List[NewsItem]


# --- analysis ---
class AnalysisData(BaseModel):
    scope: str
    headline: str
    summary: str
    bullets: List[str]
    stance: str  # bullish | neutral | bearish
    confidence: float


# --- fundamentals ---
class FundamentalMetric(BaseModel):
    label: str
    value: str
    change: Optional[float] = None
    hint: Optional[str] = None


class FundamentalsData(BaseModel):
    symbol: str
    name: str
    metrics: List[FundamentalMetric]


# --- screener ---
class ScreenerRow(BaseModel):
    symbol: str
    name: str
    price: float
    changePct: float
    marketCap: float
    peRatio: Optional[float] = None
    volume: float
    sector: str


class ScreenerData(BaseModel):
    title: str
    rows: List[ScreenerRow]


# --- heatmap ---
class HeatmapCell(BaseModel):
    symbol: str
    name: str
    changePct: float
    marketCap: float
    sector: str


class HeatmapData(BaseModel):
    title: str
    cells: List[HeatmapCell]


# --- sentiment ---
class SentimentSource(BaseModel):
    channel: str
    score: float
    volume: int
    change: float


class SentimentTrendPoint(BaseModel):
    t: str
    score: float


class SentimentData(BaseModel):
    scope: str
    overall: float
    label: str  # very_bearish | bearish | neutral | bullish | very_bullish
    sources: List[SentimentSource]
    trend: List[SentimentTrendPoint]


# --- comparison ---
class ComparisonValue(BaseModel):
    label: str
    value: str


class ComparisonCompany(BaseModel):
    symbol: str
    name: str
    values: List[ComparisonValue]


class ComparisonData(BaseModel):
    title: str
    metricLabels: List[str]
    companies: List[ComparisonCompany]


# --- order_book ---
class OrderBookLevel(BaseModel):
    price: float
    size: float
    depth: float  # 0-1, proportion of max size at this side


class TapePrint(BaseModel):
    time: str
    price: float
    size: float
    side: str  # buy | sell
    venue: str


class OrderBookData(BaseModel):
    symbol: str
    name: str
    lastPrice: float
    spread: float
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    tape: List[TapePrint]


# --- trade_flow ---
class FlowPrint(BaseModel):
    time: str
    price: float
    size: float
    side: str  # buy | sell
    venue: str
    isBlock: bool
    isDark: bool


class TradeFlowData(BaseModel):
    symbol: str
    name: str
    darkPoolPct: float
    buyImbalance: float  # 0-1; > 0.5 = net buy pressure
    totalVolume: float
    blockThreshold: float
    prints: List[FlowPrint]


# --- tca_report ---
class TCABucket(BaseModel):
    time: str
    execPrice: float
    vwap: float
    twap: float
    participationRate: float
    volume: float


class TCARportData(BaseModel):
    symbol: str
    name: str
    arrivalPrice: float
    avgExecPrice: float
    vwap: float
    twap: float
    implementationShortfall: float  # bps
    vwapSlippage: float  # bps
    twapSlippage: float  # bps
    buckets: List[TCABucket]


# --- macro_dashboard ---
class MacroTile(BaseModel):
    symbol: str
    name: str
    price: float
    changePct: float
    unit: str
    sparkline: List[float]


class MacroGroup(BaseModel):
    label: str
    tiles: List[MacroTile]


class MacroDashboardData(BaseModel):
    theme: str
    title: str
    groups: List[MacroGroup]


PanelData = Union[
    PriceChartData,
    NewsData,
    AnalysisData,
    FundamentalsData,
    ScreenerData,
    HeatmapData,
    SentimentData,
    ComparisonData,
    OrderBookData,
    TradeFlowData,
    TCARportData,
    MacroDashboardData,
]


class Panel(BaseModel):
    id: str
    type: PanelType
    title: str
    layout: PanelLayout
    status: PanelStatus
    note: Optional[str] = None
    data: Optional[PanelData] = None


class DashboardSpec(BaseModel):
    sessionId: str
    summary: str
    panels: List[Panel]


class OrchestrationRequest(BaseModel):
    query: str
    sessionId: Optional[str] = None


class RefineRequest(BaseModel):
    sessionId: str
    panelId: str
    instruction: str


# --- skills ---
class Subskill(BaseModel):
    name: str
    description: str
    expectedOutput: str


class Skill(BaseModel):
    id: str
    name: str
    panelType: PanelType
    description: str
    subskills: List[Subskill]


class SkillCatalog(BaseModel):
    skills: List[Skill]


# --- sectors ---
class Sector(BaseModel):
    id: str
    name: str
    tickerCount: int


class SectorList(BaseModel):
    sectors: List[Sector]


class SuggestionList(BaseModel):
    prompts: List[str]


# --- watchlist ---
class WatchlistItem(BaseModel):
    symbol: str
    name: str
    price: float
    changePct: float


class Watchlist(BaseModel):
    items: List[WatchlistItem]


class WatchlistInput(BaseModel):
    symbol: str
