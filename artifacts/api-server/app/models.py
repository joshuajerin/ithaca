"""Pydantic models mirroring the OpenAPI contract (camelCase JSON fields)."""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Union

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
    yield_curve = "yield_curve"
    bond_rv = "bond_rv"
    cds_pricer = "cds_pricer"
    cashflow_duration = "cashflow_duration"
    portfolio_risk = "portfolio_risk"
    backtest = "backtest"
    correlation_matrix = "correlation_matrix"
    factor_analysis = "factor_analysis"
    risk_model = "risk_model"
    factor_exposures = "factor_exposures"
    portfolio_optimizer = "portfolio_optimizer"
    iv_surface = "iv_surface"
    options_strategy = "options_strategy"
    vol_term_structure = "vol_term_structure"
    structured_product = "structured_product"
    supply_chain = "supply_chain"
    dcf_model = "dcf_model"
    earnings_transcript = "earnings_transcript"
    ma_tracker = "ma_tracker"
    signal_research = "signal_research"
    signal_scorecard = "signal_scorecard"


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
    sentiment: str
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
    stance: str
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
    country: Optional[str] = None
    exchange: Optional[str] = None


# --- screener ---
class ScreenerRow(BaseModel):
    symbol: str
    name: str
    price: float
    changePct: float  # 1-day move
    retYTD: Optional[float] = None  # true year-to-date price return
    marketCap: float
    peRatio: Optional[float] = None
    volume: float
    sector: str
    country: Optional[str] = None
    exchange: Optional[str] = None


class ScreenerData(BaseModel):
    title: str
    rows: List[ScreenerRow]


# --- heatmap ---
class HeatmapCell(BaseModel):
    symbol: str
    name: str
    changePct: float  # 1-day move
    retYTD: Optional[float] = None  # true year-to-date price return
    marketCap: float
    sector: str
    country: Optional[str] = None
    exchange: Optional[str] = None


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
    label: str
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
    depth: float


class TapePrint(BaseModel):
    time: str
    price: float
    size: float
    side: str
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
    side: str
    venue: str
    isBlock: bool
    isDark: bool


class TradeFlowData(BaseModel):
    symbol: str
    name: str
    darkPoolPct: float
    buyImbalance: float
    totalVolume: float
    blockThreshold: float
    prints: List[FlowPrint]


# --- tca_report ---
class TCAAlgoFill(BaseModel):
    avgFill: float
    fillRate: float
    isBps: float
    vwapSlipBps: float


class TCAScheduleBucket(BaseModel):
    time: str
    price: float
    marketVolume: float
    childShares: float
    participation: float
    cumPct: float


class TCAOrder(BaseModel):
    symbol: str
    name: str
    side: str
    shares: float
    notional: float
    price: Optional[float] = None
    supported: bool
    reason: Optional[str] = None
    targetWeight: Optional[float] = None
    currentWeight: Optional[float] = None
    deltaWeight: Optional[float] = None
    arrivalPrice: Optional[float] = None
    intervalVwap: Optional[float] = None
    chosenAlgo: Optional[str] = None
    algos: Optional[Dict[str, TCAAlgoFill]] = None
    schedule: Optional[List[TCAScheduleBucket]] = None
    isBps: Optional[float] = None
    vwapSlipBps: Optional[float] = None
    impactBps: Optional[float] = None
    allInBps: Optional[float] = None
    costUsd: Optional[float] = None
    fillRate: Optional[float] = None
    adv: Optional[float] = None
    dailyVol: Optional[float] = None
    asOf: Optional[str] = None


class TCAModel(BaseModel):
    name: str
    formula: str
    coef: float
    assumptions: List[str]


class TCAAggregate(BaseModel):
    orderCount: int
    supportedCount: int
    unsupportedCount: int
    grossNotional: float
    buyNotional: float
    sellNotional: float
    isBps: float
    vwapSlipBps: float
    impactBps: float
    allInBps: float
    totalCostUsd: float


class TCARportData(BaseModel):
    title: str
    interval: str
    intervalLabel: str
    range: str
    rangeLabel: str
    chosenAlgo: str
    povRate: float
    benchmarkNote: str
    model: TCAModel
    orders: List[TCAOrder]
    aggregate: TCAAggregate
    asOf: Optional[str] = None
    source: Optional[str] = None


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


# --- yield_curve ---
class YieldCurvePoint(BaseModel):
    tenor: str
    spot: float
    ago1y: float
    ago2y: float


class YieldCurveSpread(BaseModel):
    label: str
    value: float
    inverted: bool


class YieldCurveData(BaseModel):
    title: str
    points: List[YieldCurvePoint]
    spreads: List[YieldCurveSpread]
    inverted: bool


# --- bond_rv ---
class BondRVRow(BaseModel):
    issuer: str
    ticker: str
    coupon: float
    maturityYear: int
    yieldPct: float
    duration: float
    zSpread: float
    oas: float
    aswSpread: float
    rating: str


class BondRVData(BaseModel):
    title: str
    rows: List[BondRVRow]
    highlight: str


# --- cds_pricer ---
class CDSSurvivalPoint(BaseModel):
    tenor: str
    years: float
    survivalProb: float
    hazardRate: float
    defaultProb: float


class CDSPricerData(BaseModel):
    entity: str
    ticker: str
    rating: str
    recoveryRate: float
    runningSpread: float
    upfrontFee: float
    survivalCurve: List[CDSSurvivalPoint]
    impliedPd1y: float
    impliedPd5y: float


# --- cashflow_duration ---
class CashFlowPayment(BaseModel):
    date: str
    coupon: float
    principal: float
    total: float
    pv: float


class ScenarioRow(BaseModel):
    shiftBps: int
    newYield: float
    newPrice: float
    priceChange: float
    priceChangePct: float


class CashFlowDurationData(BaseModel):
    issuer: str
    coupon: float
    maturityDate: str
    faceValue: float
    price: float
    yieldPct: float
    modifiedDuration: float
    effectiveDuration: float
    convexity: float
    dv01: float
    payments: List[CashFlowPayment]
    scenarios: List[ScenarioRow]

# --- iv_surface ---
class IVSurfaceCell(BaseModel):
    strike: float
    expiry: str
    iv: float


class IVSkewPoint(BaseModel):
    strike: float
    iv: float
    moneyness: float


class IVSurfaceData(BaseModel):
    symbol: str
    underlyingPrice: float
    expiries: List[str]
    strikes: List[float]
    surface: List[IVSurfaceCell]
    atmIv: float
    skew: List[IVSkewPoint]


# --- options_strategy ---
class OptionsLeg(BaseModel):
    type: str        # call | put
    action: str      # long | short
    strike: float
    expiry: str
    premium: float
    delta: float
    gamma: float
    theta: float
    vega: float


class NetGreeks(BaseModel):
    delta: float
    gamma: float
    theta: float
    vega: float
    cost: float


class PayoffPoint(BaseModel):
    price: float
    pnl: float


class OptionsStrategyData(BaseModel):
    symbol: str
    underlyingPrice: float
    strategyName: str
    legs: List[OptionsLeg]
    netGreeks: NetGreeks
    payoff: List[PayoffPoint]
    maxProfit: Optional[float] = None
    maxLoss: Optional[float] = None
    breakevens: List[float]


# --- vol_term_structure ---
class VolExpiry(BaseModel):
    label: str
    daysToExpiry: int
    iv: float
    atmPremium: float
    isContango: bool


class VolTermStructureData(BaseModel):
    symbol: str
    spotVix: float
    atmIv: float
    regime: str   # contango | backwardation | flat
    expiries: List[VolExpiry]


# --- structured_product ---
class StructuredScenario(BaseModel):
    label: str
    spotMove: float
    finalSpot: float
    pnl: float
    returnPct: float
    probability: float


class StructuredProductData(BaseModel):
    symbol: str
    productType: str
    spotPrice: float
    barrier: float
    barrierPct: float
    tenor: float
    notional: float
    strike: float
    bsPrice: float
    fairValue: float
    delta: float
    gamma: float
    vega: float
    theta: float
    impliedVol: float
    scenarios: List[StructuredScenario]


# --- portfolio_risk ---
class VarBin(BaseModel):
    bin: float
    count: float


class FactorExposure(BaseModel):
    factor: str
    exposure: float


class RiskSummary(BaseModel):
    var95: float
    trackingError: float
    beta: float
    portfolioName: str
    cvar95: Optional[float] = None


class PortfolioRiskData(BaseModel):
    portfolioName: str
    symbols: List[str]
    varHistogram: List[VarBin]
    factorExposures: List[FactorExposure]
    summary: RiskSummary


# --- backtest ---
class BacktestPoint(BaseModel):
    t: str
    strategy: float
    benchmark: float


class DrawdownPoint(BaseModel):
    t: str
    dd: float


class BacktestStats(BaseModel):
    sharpe: float
    sortino: float
    cagr: float
    maxDD: float
    winRate: float
    totalReturn: Optional[float] = None
    vol: Optional[float] = None
    turnover: Optional[float] = None
    var95: Optional[float] = None
    cvar95: Optional[float] = None


class TradeLogEntry(BaseModel):
    t: str
    action: str
    price: float
    fromPos: float
    toPos: float
    pnl: Optional[float] = None
    pnlPct: Optional[float] = None


class BacktestData(BaseModel):
    symbol: str
    strategy: str
    curve: List[BacktestPoint]
    drawdown: List[DrawdownPoint]
    stats: BacktestStats
    tradeLog: Optional[List[TradeLogEntry]] = None


# --- correlation_matrix ---
class BetaRow(BaseModel):
    symbol: str
    beta: float
    hedgeRatio: float


class CorrelationMatrixData(BaseModel):
    symbols: List[str]
    matrix: List[List[float]]
    window: int
    betas: List[BetaRow]


# --- factor_analysis ---
class MonthlyAttribution(BaseModel):
    month: str
    momentum: float
    value: float
    size: float
    quality: float
    residual: float


class FactorLoading(BaseModel):
    factor: str
    loading: float
    tStat: float
    contribution: float


class FactorAnalysisData(BaseModel):
    symbol: str
    name: str
    monthlyAttribution: List[MonthlyAttribution]
    loadings: List[FactorLoading]


# --- risk_model ---
# --- signal_research ---
class ICStat(BaseModel):
    mean: float
    std: float
    ir: float
    tStat: float
    hitRate: float
    n: int


class ICDecayPoint(BaseModel):
    horizon: int
    ic: float


class QuantileReturn(BaseModel):
    quantile: int
    ret: float


class SpreadPoint(BaseModel):
    t: str
    value: float
    long: float
    short: float


class SpreadStats(BaseModel):
    totalReturn: float
    sharpe: float
    cagr: float


class ExcludedName(BaseModel):
    symbol: str
    reason: str


class RiskCoverage(BaseModel):
    included: int
    excluded: int
    excludedNames: List[ExcludedName]
    days: int
    source: str
    pcaVarExplained: List[float]


class FactorContribution(BaseModel):
    factor: str
    exposure: float
    volContribution: float
    pctOfRisk: float


class RiskHolding(BaseModel):
    symbol: str
    name: str
    weight: float
    mctr: float
    pctOfRisk: float
    specificVol: float


class RiskModelData(BaseModel):
    portfolioName: str
    totalVol: float
    factorVol: float
    specificVol: float
    factorVarPct: float
    specificVarPct: float
    diversificationRatio: float
    rSquared: float
    factorContributions: List[FactorContribution]
    holdings: List[RiskHolding]
    coverage: RiskCoverage


# --- factor_exposures ---
class FactorPremium(BaseModel):
    factor: str
    exposure: float
    factorReturn: float
    tStat: float


class HoldingExposure(BaseModel):
    symbol: str
    name: str
    weight: float
    market: float
    size: float
    value: float
    momentum: float
    volatility: float
    quality: float


class FactorExposureData(BaseModel):
    portfolioName: str
    exposures: List[FactorPremium]
    holdings: List[HoldingExposure]
    coverage: RiskCoverage


# --- portfolio_optimizer ---
class OptObjective(BaseModel):
    expReturn: float
    vol: float
    sharpe: float
    gross: float
    net: float
    nHoldings: int


class OptConstraints(BaseModel):
    maxPosition: float
    requestedMaxPosition: Optional[float] = None
    longOnly: bool
    net: float
    gross: float
    sectorCaps: Dict[str, float]
    turnoverPenalty: float
    binding: List[str]


class OptHolding(BaseModel):
    symbol: str
    name: str
    sector: str
    weight: float
    benchWeight: float
    activeWeight: float
    expReturn: float
    riskContribPct: float
    currentWeight: Optional[float] = None
    trade: Optional[float] = None
    priorReturn: Optional[float] = None


class OptFactorTilt(BaseModel):
    factor: str
    tilt: float
    factorReturn: float


class OptSectorAllocation(BaseModel):
    sector: str
    weight: float


class PortfolioOptimizerData(BaseModel):
    method: str
    methodLabel: str
    universeLabel: str
    longOnly: bool
    status: str
    notes: List[str]
    objective: OptObjective
    constraints: OptConstraints
    holdings: List[OptHolding]
    factorTilts: List[OptFactorTilt]
    sectorAllocation: List[OptSectorAllocation]
    turnover: Optional[float] = None
    blDelta: Optional[float] = None
    coverage: RiskCoverage


class SignalResearchData(BaseModel):
    signal: str
    label: str
    description: str
    universe: str
    universeSize: int
    included: int
    excluded: int
    excludedNames: List[ExcludedName]
    horizons: List[int]
    primaryHorizon: int
    holding: int
    quantiles: int
    ic: ICStat
    decay: List[ICDecayPoint]
    turnover: float
    turnoverAnnual: float
    rebalances: int
    quantileReturns: List[QuantileReturn]
    spread: List[SpreadPoint]
    spreadStats: SpreadStats


# --- signal_scorecard ---
class SignalScoreRow(BaseModel):
    signal: str
    label: str
    meanIC: float
    icIR: float
    tStat: float
    hitRate: float
    turnover: float
    spreadReturn: float
    spreadSharpe: float
    included: int
    rank: int
    spark: List[float]


class SignalScorecardData(BaseModel):
    universe: str
    universeSize: int
    primaryHorizon: int
    holding: int
    quantiles: int
    rows: List[SignalScoreRow]


# --- supply_chain ---
class SupplyChainNode(BaseModel):
    id: str
    name: str
    symbol: Optional[str] = None
    role: str
    exposure: float
    country: str


class SupplyChainEdge(BaseModel):
    source: str
    target: str
    weight: float


class SupplyChainTableRow(BaseModel):
    name: str
    symbol: Optional[str] = None
    role: str
    exposure: float
    country: str
    category: str


class SupplyChainData(BaseModel):
    symbol: str
    name: str
    nodes: List[SupplyChainNode]
    edges: List[SupplyChainEdge]
    table: List[SupplyChainTableRow]


# --- dcf_model ---
class DCFAssumptions(BaseModel):
    revenueGrowth: float
    ebitdaMargin: float
    wacc: float
    exitMultiple: float
    taxRate: float
    capexPct: float


class DCFProjectionYear(BaseModel):
    year: int
    revenue: float
    fcf: float
    pvFcf: float


class DCFSensCell(BaseModel):
    wacc: float
    exitMultiple: float
    impliedPrice: float


class DCFData(BaseModel):
    symbol: str
    name: str
    currentPrice: float
    baseRevenue: float
    sharesOut: float
    netDebt: float
    assumptions: DCFAssumptions
    projections: List[DCFProjectionYear]
    impliedPriceLow: float
    impliedPriceMid: float
    impliedPriceHigh: float
    sensitivity: List[DCFSensCell]


# --- earnings_transcript ---
class TranscriptSegment(BaseModel):
    index: int
    speaker: str
    role: str
    text: str
    sentiment: float
    sentimentLabel: str
    isKeyQuote: bool


class TranscriptKeyQuote(BaseModel):
    speaker: str
    role: str
    text: str
    topic: str


class TranscriptSentPoint(BaseModel):
    index: int
    score: float
    label: str


class TranscriptData(BaseModel):
    symbol: str
    name: str
    callDate: str
    quarter: str
    overallSentiment: float
    segments: List[TranscriptSegment]
    keyQuotes: List[TranscriptKeyQuote]
    sentimentTimeline: List[TranscriptSentPoint]


# --- ma_tracker ---
class MADeal(BaseModel):
    id: str
    target: str
    targetSymbol: Optional[str] = None
    acquirer: str
    acquirerSymbol: Optional[str] = None
    dealValue: float
    premium: float
    status: str
    announced: str
    expectedClose: Optional[str] = None
    arbSpread: Optional[float] = None
    dealType: str
    sector: str


class MAStats(BaseModel):
    totalDeals: int
    totalValue: float
    avgPremium: float
    pendingDeals: int


class MAData(BaseModel):
    title: str
    deals: List[MADeal]
    stats: MAStats


# --- monte_carlo ---
class MonteCarloFanPoint(BaseModel):
    step: int
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float


class MonteCarloPath(BaseModel):
    id: int
    values: List[float]


class MonteCarloSummary(BaseModel):
    method: str
    startValue: float
    horizon: int
    paths: int
    expectedTerminal: float
    medianTerminal: float
    p5Terminal: float
    p95Terminal: float
    expectedReturn: float
    probLoss: float
    var95: float
    cvar95: float


class MonteCarloData(BaseModel):
    symbol: str
    method: str
    horizon: int
    startValue: float
    fan: List[MonteCarloFanPoint]
    samplePaths: List[MonteCarloPath]
    summary: MonteCarloSummary


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
    YieldCurveData,
    BondRVData,
    CDSPricerData,
    CashFlowDurationData,
    PortfolioRiskData,
    BacktestData,
    CorrelationMatrixData,
    FactorAnalysisData,
    RiskModelData,
    FactorExposureData,
    IVSurfaceData,
    OptionsStrategyData,
    VolTermStructureData,
    StructuredProductData,
    SupplyChainData,
    DCFData,
    TranscriptData,
    MAData,
    MonteCarloData,
]


class Panel(BaseModel):
    # `type` is a plain string (not the PanelType enum) so AI-generated dynamic
    # panel types serialize without being rejected. `data` is a free-form dict
    # for the same reason — built-in panels still produce their validated shape.
    id: str
    type: str
    title: str
    layout: PanelLayout
    status: PanelStatus
    note: Optional[str] = None
    asOf: Optional[str] = None
    source: Optional[str] = None
    data: Optional[dict] = None


class NarrationSegment(BaseModel):
    text: str
    panelId: Optional[str] = None


class DashboardSpec(BaseModel):
    sessionId: str
    summary: str
    panels: List[Panel]
    narration: Optional[List[NarrationSegment]] = None
    # "question" when the message was answered conversationally (panels unchanged)
    # or "build" when the dashboard was composed/modified.
    intent: Optional[str] = None
    # Conversational answer text for a question intent; null for a build.
    answer: Optional[str] = None


class OrchestrationRequest(BaseModel):
    query: str
    sessionId: Optional[str] = None
    voice: Optional[bool] = None


# --- navigator (AI cursor tour) ---
class NavigationStop(BaseModel):
    panelId: str
    caption: str


class NavigationTour(BaseModel):
    sessionId: str
    title: str
    stops: List[NavigationStop]


class NavigateRequest(BaseModel):
    sessionId: str
    query: Optional[str] = None


class SpeakRequest(BaseModel):
    text: str
    voice: Optional[str] = None


class SpeechAudio(BaseModel):
    audio: str
    format: str


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
    panelType: str  # plain string so AI-generated dynamic skills are accepted
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
