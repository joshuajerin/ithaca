"""Curated mock market dataset for Phase 1.

Covers three sectors: semiconductors, energy, AI/tech. All numbers are
fabricated-but-plausible and generated deterministically so the terminal is
stable across requests.
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta
from typing import Dict, List, Optional

SECTORS = {
    "semiconductors": "Semiconductors",
    "energy": "Energy",
    "ai_tech": "AI / Tech",
}

# Aliases so natural-language scope resolution is forgiving.
SECTOR_ALIASES = {
    "semis": "semiconductors",
    "semiconductor": "semiconductors",
    "chips": "semiconductors",
    "chip": "semiconductors",
    "oil": "energy",
    "oil & gas": "energy",
    "clean energy": "energy",
    "renewables": "energy",
    "power": "energy",
    "ai": "ai_tech",
    "tech": "ai_tech",
    "technology": "ai_tech",
    "software": "ai_tech",
    "ai/tech": "ai_tech",
}

# symbol -> company record
COMPANIES: Dict[str, dict] = {}


def _c(symbol, name, sector, price, change_pct, market_cap, pe, volume,
       revenue, net_margin, eps, div_yield, beta, hi, lo, desc):
    COMPANIES[symbol] = {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "price": price,
        "changePct": change_pct,
        "marketCap": market_cap,  # absolute USD
        "peRatio": pe,
        "volume": volume,
        "revenue": revenue,  # absolute USD, trailing 12m
        "netMargin": net_margin,  # percent
        "eps": eps,
        "dividendYield": div_yield,  # percent
        "beta": beta,
        "week52High": hi,
        "week52Low": lo,
        "description": desc,
    }


B = 1_000_000_000
T = 1_000_000_000_000

# --- Semiconductors ---
_c("NVDA", "NVIDIA Corp.", "semiconductors", 121.40, 2.34, 2.98 * T, 54.2, 312_000_000,
   96.3 * B, 55.0, 2.24, 0.03, 1.68, 140.76, 75.61,
   "Dominant designer of GPUs and accelerated-computing platforms for AI training and inference.")
_c("AMD", "Advanced Micro Devices", "semiconductors", 162.05, 1.12, 262 * B, 46.8, 41_000_000,
   24.3 * B, 7.4, 3.46, 0.0, 1.71, 227.30, 116.37,
   "Designs CPUs, GPUs and data-center accelerators competing across PC and server markets.")
_c("INTC", "Intel Corp.", "semiconductors", 31.22, -0.86, 133 * B, 30.1, 38_000_000,
   54.2 * B, 3.1, 1.04, 1.6, 0.98, 51.28, 28.55,
   "Integrated device manufacturer pivoting to foundry services and AI-capable client chips.")
_c("TSM", "Taiwan Semiconductor", "semiconductors", 174.60, 1.87, 905 * B, 28.9, 12_500_000,
   76.0 * B, 40.2, 6.04, 1.3, 1.09, 193.47, 84.02,
   "World's largest dedicated chip foundry, manufacturing leading-edge nodes for fabless designers.")
_c("AVGO", "Broadcom Inc.", "semiconductors", 168.30, 0.94, 785 * B, 62.5, 22_000_000,
   51.6 * B, 28.5, 2.69, 1.2, 1.18, 185.16, 96.30,
   "Diversified semiconductor and infrastructure-software vendor with strong networking franchise.")
_c("ASML", "ASML Holding", "semiconductors", 712.40, -1.43, 281 * B, 40.7, 1_400_000,
   29.8 * B, 27.4, 17.50, 1.0, 1.05, 1110.09, 645.50,
   "Sole supplier of EUV lithography systems essential to advanced chip manufacturing.")
_c("MU", "Micron Technology", "semiconductors", 96.85, 3.05, 107 * B, 22.4, 28_000_000,
   25.1 * B, 9.8, 4.33, 0.5, 1.16, 157.54, 83.54,
   "Leading memory and storage maker leveraged to AI-driven HBM and DRAM demand.")
_c("QCOM", "Qualcomm Inc.", "semiconductors", 161.20, 0.41, 179 * B, 18.6, 9_500_000,
   38.9 * B, 21.0, 8.66, 2.0, 1.27, 230.63, 149.43,
   "Mobile-chipset and wireless-IP leader expanding into automotive and edge AI.")

# --- Energy ---
_c("XOM", "Exxon Mobil Corp.", "energy", 113.85, -0.52, 506 * B, 14.2, 14_000_000,
   339 * B, 9.8, 8.02, 3.3, 0.92, 126.34, 95.77,
   "Integrated supermajor across upstream, refining and chemicals with large buyback program.")
_c("CVX", "Chevron Corp.", "energy", 156.40, -0.31, 287 * B, 15.1, 7_800_000,
   196 * B, 8.9, 10.36, 4.2, 0.96, 167.11, 135.37,
   "Integrated oil major with Permian growth and disciplined capital returns.")
_c("COP", "ConocoPhillips", "energy", 104.20, 0.88, 122 * B, 12.7, 6_200_000,
   58.0 * B, 17.5, 8.21, 2.9, 1.18, 135.18, 99.45,
   "Large independent E&P with low-cost-of-supply portfolio and variable dividend.")
_c("SLB", "Schlumberger NV", "energy", 43.10, 1.24, 61 * B, 13.9, 11_000_000,
   35.6 * B, 12.6, 3.10, 2.5, 1.34, 63.04, 40.68,
   "Largest oilfield-services provider, leveraged to global upstream capex and digital.")
_c("NEE", "NextEra Energy", "energy", 76.55, 1.61, 157 * B, 23.4, 9_400_000,
   28.1 * B, 25.3, 3.27, 2.7, 0.55, 86.10, 56.62,
   "Regulated utility plus the world's largest renewables developer (wind, solar, storage).")
_c("ENPH", "Enphase Energy", "energy", 102.30, 4.21, 13.8 * B, 36.2, 5_100_000,
   1.9 * B, 8.5, 2.83, 0.0, 1.62, 141.63, 73.49,
   "Microinverter and home-energy systems maker levered to residential solar cycles.")
_c("FSLR", "First Solar", "energy", 189.70, 2.66, 20.3 * B, 17.8, 2_900_000,
   3.8 * B, 31.2, 10.66, 0.0, 1.41, 306.77, 152.28,
   "Thin-film solar manufacturer with large US backlog and IRA tax-credit tailwinds.")
_c("OXY", "Occidental Petroleum", "energy", 56.80, -1.05, 53 * B, 13.2, 12_300_000,
   27.0 * B, 12.0, 4.30, 1.6, 1.42, 71.18, 53.07,
   "Permian-weighted E&P with carbon-capture ambitions and Berkshire backing.")

# --- AI / Tech ---
_c("MSFT", "Microsoft Corp.", "ai_tech", 416.30, 0.74, 3.09 * T, 35.6, 18_000_000,
   245 * B, 36.3, 11.70, 0.7, 0.90, 468.35, 366.50,
   "Cloud, productivity and AI platform leader monetizing Copilot and Azure OpenAI.")
_c("GOOGL", "Alphabet Inc.", "ai_tech", 168.90, 1.02, 2.07 * T, 23.8, 22_000_000,
   328 * B, 27.7, 7.10, 0.5, 1.03, 191.75, 127.90,
   "Search, advertising and cloud giant with Gemini models and deep AI research.")
_c("META", "Meta Platforms", "ai_tech", 498.20, 1.58, 1.27 * T, 27.4, 14_500_000,
   149 * B, 33.9, 18.18, 0.4, 1.21, 542.81, 313.66,
   "Social-platform leader investing heavily in AI ranking, ads and open-source models.")
_c("AMZN", "Amazon.com Inc.", "ai_tech", 184.70, 0.66, 1.92 * T, 42.1, 33_000_000,
   590 * B, 7.3, 4.39, 0.0, 1.15, 201.20, 139.52,
   "E-commerce and AWS cloud leader scaling Bedrock and Trainium for AI workloads.")
_c("PLTR", "Palantir Technologies", "ai_tech", 31.05, 3.92, 70 * B, 78.3, 47_000_000,
   2.5 * B, 16.0, 0.40, 0.0, 2.61, 39.46, 13.68,
   "Data-analytics and AI-operations platform with fast-growing commercial AIP business.")
_c("SNOW", "Snowflake Inc.", "ai_tech", 138.40, -2.11, 46 * B, None, 6_700_000,
   3.0 * B, -22.0, -1.20, 0.0, 1.05, 237.72, 119.77,
   "Cloud data platform expanding into AI workloads and native apps; not yet GAAP-profitable.")
_c("CRM", "Salesforce Inc.", "ai_tech", 248.90, 0.49, 241 * B, 44.7, 5_900_000,
   37.9 * B, 16.4, 5.57, 0.6, 1.29, 318.71, 212.00,
   "Enterprise CRM leader embedding Einstein/Agentforce AI across its clouds.")
_c("NOW", "ServiceNow Inc.", "ai_tech", 742.10, 1.18, 152 * B, 78.9, 1_500_000,
   10.4 * B, 13.5, 9.41, 0.0, 1.07, 815.32, 605.96,
   "Enterprise workflow-automation platform monetizing Now Assist generative AI.")


def list_sectors() -> List[dict]:
    out = []
    for sid, name in SECTORS.items():
        count = sum(1 for c in COMPANIES.values() if c["sector"] == sid)
        out.append({"id": sid, "name": name, "tickerCount": count})
    return out


def sector_name(sid: str) -> str:
    return SECTORS.get(sid, sid)


def symbols_in_sector(sid: str) -> List[str]:
    return [s for s, c in COMPANIES.items() if c["sector"] == sid]


def all_symbols() -> List[str]:
    return list(COMPANIES.keys())


def get_company(symbol: str) -> Optional[dict]:
    return COMPANIES.get(symbol.upper())


def resolve_sector(text: str) -> Optional[str]:
    if not text:
        return None
    t = text.strip().lower()
    if t in SECTORS:
        return t
    if t in SECTOR_ALIASES:
        return SECTOR_ALIASES[t]
    for sid, name in SECTORS.items():
        if name.lower() in t or t in name.lower():
            return sid
    for alias, sid in SECTOR_ALIASES.items():
        if alias in t:
            return sid
    return None


def _seed(symbol: str) -> int:
    return int(hashlib.md5(symbol.encode()).hexdigest(), 16) % (2 ** 31)


def price_series(symbol: str, days: int = 90) -> List[dict]:
    """Deterministic OHLCV series ending at the company's current price."""
    company = get_company(symbol)
    if not company:
        return []
    last = company["price"]
    rng = _seed(symbol)
    # Reconstruct a plausible path backwards from `last` using a seeded walk.
    closes: List[float] = [last]
    price = last
    for i in range(days - 1):
        rng = (1103515245 * rng + 12345) & 0x7FFFFFFF
        # pseudo-random in [-1, 1)
        r = (rng / 0x7FFFFFFF) * 2 - 1
        drift = 0.0006
        vol = 0.018 + 0.012 * (abs(math.sin(i / 9.0)))
        prev = price / (1 + drift + r * vol)
        prev = max(prev, 1.0)
        closes.append(prev)
        price = prev
    closes.reverse()  # oldest -> newest

    points: List[dict] = []
    start = date.today() - timedelta(days=days - 1)
    for i, c in enumerate(closes):
        rng = (1103515245 * rng + 12345) & 0x7FFFFFFF
        r = (rng / 0x7FFFFFFF)
        o = closes[i - 1] if i > 0 else c * (1 - 0.004)
        hi = max(o, c) * (1 + 0.006 + 0.01 * r)
        lo = min(o, c) * (1 - 0.006 - 0.01 * r)
        base_vol = company["volume"]
        v = base_vol * (0.6 + 0.8 * r)
        d = start + timedelta(days=i)
        points.append({
            "t": d.isoformat(),
            "o": round(o, 2),
            "h": round(hi, 2),
            "l": round(lo, 2),
            "c": round(c, 2),
            "v": round(v, 0),
        })
    return points


# --- Curated news ---
# Each item: headline, source, summary, sentiment, tickers, sector, days_ago
_NEWS: List[dict] = [
    # Semiconductors
    {"headline": "NVIDIA's next-gen accelerators sell out through next year on hyperscaler demand",
     "source": "Reuters", "sentiment": "positive", "tickers": ["NVDA"], "sector": "semiconductors",
     "days_ago": 0, "summary": "Cloud providers have reportedly pre-committed the bulk of upcoming GPU supply, extending the data-center upgrade cycle."},
    {"headline": "TSMC raises capex guidance as advanced-node utilization stays near full",
     "source": "Bloomberg", "sentiment": "positive", "tickers": ["TSM", "NVDA", "AMD"], "sector": "semiconductors",
     "days_ago": 1, "summary": "The foundry cited sustained AI accelerator orders and resilient high-performance-computing demand."},
    {"headline": "Intel foundry roadmap slips, pressuring turnaround timeline",
     "source": "The Information", "sentiment": "negative", "tickers": ["INTC"], "sector": "semiconductors",
     "days_ago": 2, "summary": "Analysts trimmed estimates after reports of delays in ramping the company's leading-edge process."},
    {"headline": "Micron HBM capacity sold out for the year as AI memory demand surges",
     "source": "CNBC", "sentiment": "positive", "tickers": ["MU"], "sector": "semiconductors",
     "days_ago": 1, "summary": "High-bandwidth memory pricing remains firm, lifting margin expectations for the memory cycle."},
    {"headline": "ASML bookings cool on China export curbs, shares slip",
     "source": "Financial Times", "sentiment": "negative", "tickers": ["ASML"], "sector": "semiconductors",
     "days_ago": 3, "summary": "New-order intake came in below consensus as restrictions weigh on near-term shipments."},
    # Energy
    {"headline": "Crude steadies as OPEC+ signals patience on supply additions",
     "source": "Reuters", "sentiment": "neutral", "tickers": ["XOM", "CVX", "COP", "OXY"], "sector": "energy",
     "days_ago": 0, "summary": "Benchmark prices held a tight range as the group reiterated a gradual approach to restoring barrels."},
    {"headline": "First Solar backlog hits record on US manufacturing incentives",
     "source": "Bloomberg", "sentiment": "positive", "tickers": ["FSLR"], "sector": "energy",
     "days_ago": 1, "summary": "Domestic-content tax credits continue to pull forward utility-scale solar bookings."},
    {"headline": "NextEra accelerates storage pipeline, reaffirms growth targets",
     "source": "S&P Global", "sentiment": "positive", "tickers": ["NEE"], "sector": "energy",
     "days_ago": 2, "summary": "The utility highlighted battery-storage additions as a key driver of its renewables build-out."},
    {"headline": "Enphase guides cautiously as European residential solar demand softens",
     "source": "CNBC", "sentiment": "negative", "tickers": ["ENPH"], "sector": "energy",
     "days_ago": 2, "summary": "Channel inventory normalization is taking longer than expected in several EU markets."},
    {"headline": "Exxon expands buyback as Permian output beats plan",
     "source": "WSJ", "sentiment": "positive", "tickers": ["XOM"], "sector": "energy",
     "days_ago": 3, "summary": "Strong upstream volumes and cost control support an enlarged shareholder-return program."},
    # AI / Tech
    {"headline": "Microsoft Copilot adoption accelerates across enterprise seats",
     "source": "Bloomberg", "sentiment": "positive", "tickers": ["MSFT"], "sector": "ai_tech",
     "days_ago": 0, "summary": "Management pointed to rising paid-seat conversion and Azure AI consumption growth."},
    {"headline": "Alphabet's Gemini gains share in developer benchmarks",
     "source": "The Verge", "sentiment": "positive", "tickers": ["GOOGL"], "sector": "ai_tech",
     "days_ago": 1, "summary": "New model variants narrowed the gap with rivals on reasoning and coding evaluations."},
    {"headline": "Palantir's commercial AI platform drives another quarter of acceleration",
     "source": "Reuters", "sentiment": "positive", "tickers": ["PLTR"], "sector": "ai_tech",
     "days_ago": 1, "summary": "AIP-led deal velocity continues to expand the US commercial customer base."},
    {"headline": "Snowflake guidance disappoints as consumption growth decelerates",
     "source": "CNBC", "sentiment": "negative", "tickers": ["SNOW"], "sector": "ai_tech",
     "days_ago": 2, "summary": "Investors focused on slowing net-revenue retention despite new AI product momentum."},
    {"headline": "Meta lifts AI infrastructure spend, eyes efficiency gains in ads",
     "source": "Bloomberg", "sentiment": "neutral", "tickers": ["META"], "sector": "ai_tech",
     "days_ago": 3, "summary": "Heavier capex is framed as supporting both ranking improvements and long-term compute needs."},
    {"headline": "Amazon touts custom AI silicon to cut inference costs on AWS",
     "source": "WSJ", "sentiment": "positive", "tickers": ["AMZN", "NVDA"], "sector": "ai_tech",
     "days_ago": 2, "summary": "Trainium and Inferentia adoption is pitched as a margin lever for cloud AI workloads."},
]


# ---------------------------------------------------------------------------
# Macro / cross-asset data
# ---------------------------------------------------------------------------
MACRO_ASSETS: Dict[str, dict] = {
    # --- Rates ---
    "US10Y":   {"name": "US 10Y Yield",       "group": "rates",       "price": 4.42,    "changePct":  1.15, "unit": "%"},
    "US2Y10Y": {"name": "2Y-10Y Spread",      "group": "rates",       "price": -0.18,   "changePct": -5.20, "unit": "bps"},
    "US2Y":    {"name": "US 2Y Yield",         "group": "rates",       "price": 4.85,    "changePct":  0.62, "unit": "%"},
    "TIPS10Y": {"name": "10Y Breakeven",       "group": "rates",       "price": 2.31,    "changePct":  0.43, "unit": "%"},
    # --- FX ---
    "DXY":     {"name": "US Dollar Index",     "group": "fx",          "price": 104.32,  "changePct": -0.21, "unit": "index"},
    "EURUSD":  {"name": "EUR/USD",             "group": "fx",          "price": 1.0842,  "changePct":  0.18, "unit": "FX"},
    "USDJPY":  {"name": "USD/JPY",             "group": "fx",          "price": 153.47,  "changePct":  0.32, "unit": "FX"},
    "USDCNH":  {"name": "USD/CNH",             "group": "fx",          "price": 7.2441,  "changePct":  0.08, "unit": "FX"},
    # --- Commodities ---
    "WTI":     {"name": "WTI Crude Oil",       "group": "commodities", "price": 77.84,   "changePct": -0.94, "unit": "USD"},
    "GOLD":    {"name": "Gold",                "group": "commodities", "price": 2318.50, "changePct":  0.41, "unit": "USD"},
    "COPPER":  {"name": "Copper",              "group": "commodities", "price": 4.42,    "changePct":  1.05, "unit": "USD"},
    "IRON":    {"name": "Iron Ore",            "group": "commodities", "price": 104.20,  "changePct": -1.30, "unit": "USD"},
    # --- Equities ---
    "SPX":     {"name": "S&P 500",             "group": "equities",    "price": 5248.49, "changePct":  0.57, "unit": "index"},
    "NDX":     {"name": "Nasdaq 100",          "group": "equities",    "price": 18339.44,"changePct":  0.82, "unit": "index"},
    "EEM":     {"name": "EM Equities (EEM)",   "group": "equities",    "price": 40.35,   "changePct": -0.31, "unit": "index"},
    "HSCEI":   {"name": "HK China Ent.",       "group": "equities",    "price": 6742.18, "changePct": -0.84, "unit": "index"},
    "CSI300":  {"name": "CSI 300",             "group": "equities",    "price": 3521.40, "changePct":  0.23, "unit": "index"},
    "VIX":     {"name": "VIX",                 "group": "equities",    "price": 14.82,   "changePct": -3.21, "unit": "index"},
}

MACRO_THEMES: Dict[str, dict] = {
    "global": {
        "title": "Global Macro Dashboard",
        "groups": {
            "Rates":       ["US10Y", "US2Y10Y"],
            "FX":          ["DXY", "EURUSD", "USDJPY"],
            "Commodities": ["WTI", "GOLD"],
            "Equities":    ["SPX", "NDX", "EEM"],
        },
    },
    "inflation": {
        "title": "Inflation Dashboard",
        "groups": {
            "Rates":       ["US10Y", "US2Y", "TIPS10Y"],
            "FX":          ["DXY"],
            "Commodities": ["WTI", "GOLD", "COPPER"],
            "Equities":    ["SPX"],
        },
    },
    "china": {
        "title": "China Macro Dashboard",
        "groups": {
            "Equities":    ["CSI300", "HSCEI", "EEM"],
            "FX":          ["USDCNH", "USDJPY"],
            "Commodities": ["IRON", "COPPER"],
            "Rates":       ["US10Y"],
        },
    },
    "risk": {
        "title": "Risk-On / Risk-Off Dashboard",
        "groups": {
            "Equities":    ["SPX", "NDX", "VIX"],
            "Rates":       ["US10Y", "US2Y10Y"],
            "FX":          ["DXY", "USDJPY"],
            "Commodities": ["GOLD", "WTI"],
        },
    },
}

# Also allow the theme key "default" and "global risk" / etc.
MACRO_THEME_ALIASES: Dict[str, str] = {
    "default": "global",
    "global risk": "global",
    "global risk-on/risk-off": "risk",
    "risk-on": "risk",
    "risk off": "risk",
    "risk on": "risk",
    "risk-off": "risk",
    "roro": "risk",
}


def resolve_macro_theme(text: str) -> str:
    """Return a canonical MACRO_THEMES key for a natural-language theme string."""
    if not text:
        return "global"
    t = text.strip().lower()
    if t in MACRO_THEMES:
        return t
    if t in MACRO_THEME_ALIASES:
        return MACRO_THEME_ALIASES[t]
    for key in MACRO_THEMES:
        if key in t or t in key:
            return key
    return "global"


def macro_sparkline(symbol: str, points: int = 14) -> List[float]:
    """Deterministic short price series for a macro asset tile."""
    asset = MACRO_ASSETS.get(symbol)
    if not asset:
        return [0.0] * points
    last = float(asset["price"])
    seed = _seed(symbol)
    vals: List[float] = [last]
    p = last
    for i in range(points - 1):
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        r = (seed / 0x7FFFFFFF) * 2 - 1
        vol = 0.006 + 0.004 * abs(math.sin(i / 2.5))
        prev = max(p / (1.0 + r * vol), 0.0001)
        vals.append(round(prev, 6))
        p = prev
    vals.reverse()
    return [round(v, 6) for v in vals]


def news_for(scope_type: str, scope: str, limit: int = 8) -> List[dict]:
    """scope_type: 'symbol' or 'sector'. Returns curated news items."""
    items: List[dict] = []
    if scope_type == "symbol":
        sym = scope.upper()
        for n in _NEWS:
            if sym in n["tickers"]:
                items.append(n)
        if not items:
            company = get_company(sym)
            sid = company["sector"] if company else None
            if sid:
                items = [n for n in _NEWS if n["sector"] == sid]
    else:
        sid = resolve_sector(scope) or scope
        items = [n for n in _NEWS if n["sector"] == sid]
        if not items:
            items = list(_NEWS)
    items = sorted(items, key=lambda n: n["days_ago"])[:limit]
    out = []
    today = date.today()
    for i, n in enumerate(items):
        d = today - timedelta(days=n["days_ago"])
        out.append({
            "id": f"news-{abs(hash(n['headline'])) % 100000}",
            "headline": n["headline"],
            "source": n["source"],
            "summary": n["summary"],
            "url": None,
            "publishedAt": d.isoformat(),
            "sentiment": n["sentiment"],
            "tickers": n["tickers"],
        })
    return out
