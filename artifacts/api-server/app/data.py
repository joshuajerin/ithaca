"""Curated mock market dataset for Phase 1.

Covers a broad set of thematic sectors (semiconductors, energy, AI/tech,
robotics, EVs, cybersecurity, biotech, fintech, cloud/software, clean energy,
defense, banks/financials, healthcare, consumer/retail, communications/media
and industrials). All numbers are fabricated-but-plausible and generated
deterministically so the terminal is stable across requests.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

SECTORS = {
    "semiconductors": "Semiconductors",
    "energy": "Energy",
    "ai_tech": "AI / Tech",
    "robotics": "Robotics & Automation",
    "ev_auto": "EVs & Automotive",
    "cybersecurity": "Cybersecurity",
    "biotech": "Biotech & Pharma",
    "fintech": "Fintech",
    "cloud": "Cloud & Software",
    "clean_energy": "Clean & Renewable Energy",
    "defense": "Defense & Aerospace",
    "financials": "Banks & Financials",
    "healthcare": "Healthcare",
    "consumer": "Consumer Discretionary",
    "comms": "Communications & Media",
    "industrials": "Industrials",
    # --- Expanded taxonomy (Task: deep curated universe) ---
    "staples": "Consumer Staples",
    "real_estate": "Real Estate & REITs",
    "materials": "Materials & Chemicals",
    "metals_mining": "Metals & Mining",
    "utilities": "Utilities",
    "transportation": "Transportation & Logistics",
    "insurance": "Insurance",
    "telecom": "Telecom",
    "crypto": "Crypto & Blockchain",
    "space": "Space",
    "quantum": "Quantum Computing",
}

# Aliases so natural-language scope resolution is forgiving.
SECTOR_ALIASES = {
    # Semiconductors
    "semis": "semiconductors",
    "semiconductor": "semiconductors",
    "chips": "semiconductors",
    "chip": "semiconductors",
    # Energy (oil & gas)
    "oil": "energy",
    "oil & gas": "energy",
    "oil and gas": "energy",
    "gas": "energy",
    "crude": "energy",
    "fossil fuels": "energy",
    "upstream": "energy",
    "midstream": "energy",
    "refiners": "energy",
    # AI / Tech
    "ai": "ai_tech",
    "tech": "ai_tech",
    "technology": "ai_tech",
    "ai/tech": "ai_tech",
    "artificial intelligence": "ai_tech",
    # Robotics & automation
    "robotics": "robotics",
    "robot": "robotics",
    "robots": "robotics",
    "bots": "robotics",
    "automation": "robotics",
    "industrial automation": "robotics",
    "cobots": "robotics",
    # EVs & automotive
    "ev": "ev_auto",
    "evs": "ev_auto",
    "electric vehicle": "ev_auto",
    "electric vehicles": "ev_auto",
    "auto": "ev_auto",
    "autos": "ev_auto",
    "automotive": "ev_auto",
    "automakers": "ev_auto",
    "carmakers": "ev_auto",
    "cars": "ev_auto",
    # Cybersecurity
    "cyber": "cybersecurity",
    "cybersecurity": "cybersecurity",
    "cyber security": "cybersecurity",
    "security": "cybersecurity",
    "infosec": "cybersecurity",
    "network security": "cybersecurity",
    # Biotech & pharma
    "biotech": "biotech",
    "biotechnology": "biotech",
    "biopharma": "biotech",
    "pharma": "biotech",
    "pharmaceutical": "biotech",
    "pharmaceuticals": "biotech",
    "drugs": "biotech",
    "drugmakers": "biotech",
    # Fintech
    "fintech": "fintech",
    "financial technology": "fintech",
    "payments": "fintech",
    "digital payments": "fintech",
    "crypto stocks": "fintech",
    # Cloud & software
    "cloud": "cloud",
    "saas": "cloud",
    "software": "cloud",
    "enterprise software": "cloud",
    "cloud software": "cloud",
    "cloud computing": "cloud",
    # Clean & renewable energy
    "clean energy": "clean_energy",
    "clean": "clean_energy",
    "renewables": "clean_energy",
    "renewable": "clean_energy",
    "renewable energy": "clean_energy",
    "solar": "clean_energy",
    "wind": "clean_energy",
    "green energy": "clean_energy",
    "hydrogen": "clean_energy",
    # Defense & aerospace
    "defense": "defense",
    "defence": "defense",
    "aerospace": "defense",
    "military": "defense",
    "weapons": "defense",
    "defense contractors": "defense",
    # Banks & financials
    "financials": "financials",
    "banks": "financials",
    "bank": "financials",
    "banking": "financials",
    "wall street": "financials",
    "lenders": "financials",
    "brokers": "financials",
    # Healthcare
    "healthcare": "healthcare",
    "health care": "healthcare",
    "health": "healthcare",
    "medical": "healthcare",
    "medtech": "healthcare",
    "med tech": "healthcare",
    "medical devices": "healthcare",
    "health insurers": "healthcare",
    "hospitals": "healthcare",
    # Consumer discretionary
    "consumer": "consumer",
    "retail": "consumer",
    "retailers": "consumer",
    "consumer discretionary": "consumer",
    "discretionary": "consumer",
    "shopping": "consumer",
    "restaurants": "consumer",
    "apparel": "consumer",
    "travel": "consumer",
    "leisure": "consumer",
    "gaming": "consumer",
    # Communications & media
    "comms": "comms",
    "communications": "comms",
    "media": "comms",
    "streaming": "comms",
    "entertainment": "comms",
    "social media": "comms",
    "advertising": "comms",
    # Industrials
    "industrials": "industrials",
    "industrial": "industrials",
    "machinery": "industrials",
    "manufacturing": "industrials",
    # Consumer staples
    "staples": "staples",
    "consumer staples": "staples",
    "food": "staples",
    "food & beverage": "staples",
    "beverages": "staples",
    "groceries": "staples",
    "household products": "staples",
    "tobacco": "staples",
    # Real estate & REITs
    "real estate": "real_estate",
    "reit": "real_estate",
    "reits": "real_estate",
    "property": "real_estate",
    "properties": "real_estate",
    "realty": "real_estate",
    # Materials & chemicals
    "materials": "materials",
    "chemicals": "materials",
    "chemical": "materials",
    "commodities": "materials",
    "industrial materials": "materials",
    # Metals & mining
    "metals": "metals_mining",
    "metals & mining": "metals_mining",
    "mining": "metals_mining",
    "miners": "metals_mining",
    "gold": "metals_mining",
    "gold miners": "metals_mining",
    "silver": "metals_mining",
    "copper": "metals_mining",
    "steel": "metals_mining",
    # Utilities
    "utilities": "utilities",
    "utility": "utilities",
    "power": "utilities",
    "electric": "utilities",
    "electricity": "utilities",
    "water utilities": "utilities",
    # Transportation & logistics
    "transportation": "transportation",
    "transports": "transportation",
    "transport": "transportation",
    "logistics": "transportation",
    "shipping": "transportation",
    "airlines": "transportation",
    "railroads": "transportation",
    "trucking": "transportation",
    "freight": "transportation",
    # Insurance
    "insurance": "insurance",
    "insurers": "insurance",
    "insurer": "insurance",
    "reinsurance": "insurance",
    "p&c insurance": "insurance",
    "life insurance": "insurance",
    # Telecom
    "telecom": "telecom",
    "telecoms": "telecom",
    "telecommunications": "telecom",
    "carriers": "telecom",
    "wireless": "telecom",
    "cell towers": "telecom",
    "towers": "telecom",
    # Crypto & blockchain
    "crypto": "crypto",
    "cryptocurrency": "crypto",
    "blockchain": "crypto",
    "bitcoin": "crypto",
    "bitcoin miners": "crypto",
    "digital assets": "crypto",
    "web3": "crypto",
    # Space
    "space": "space",
    "space stocks": "space",
    "satellite": "space",
    "satellites": "space",
    "rockets": "space",
    "launch": "space",
    # Quantum computing
    "quantum": "quantum",
    "quantum computing": "quantum",
    "quantum stocks": "quantum",
}

# symbol -> company record
COMPANIES: Dict[str, dict] = {}


def _c(symbol, name, sector, price, change_pct, market_cap, pe, volume,
       revenue, net_margin, eps, div_yield, beta, hi, lo, desc,
       country="United States", exchange="NASDAQ"):
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
        "country": country,
        "exchange": exchange,
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

# --- Robotics & Automation ---
_c("ABB", "ABB Ltd", "robotics", 52.10, 0.82, 96 * B, 24.5, 3_000_000,
   32.2 * B, 13.5, 1.95, 1.9, 1.05, 56.40, 41.20,
   "Swiss-Swedish industrial-automation and robotics leader in electrification and motion.")
_c("ROK", "Rockwell Automation", "robotics", 270.50, 1.11, 30.5 * B, 24.0, 700_000,
   8.3 * B, 11.0, 9.20, 1.9, 1.30, 309.00, 215.00,
   "US industrial-automation pure-play providing control systems and software for factories.")
_c("TER", "Teradyne Inc.", "robotics", 112.30, 1.62, 18.2 * B, 33.0, 1_500_000,
   2.8 * B, 18.0, 3.20, 0.4, 1.45, 163.00, 86.00,
   "Maker of semiconductor and electronics test equipment plus industrial-automation robots.")
_c("ZBRA", "Zebra Technologies", "robotics", 312.70, 0.91, 16.0 * B, 31.5, 400_000,
   4.9 * B, 9.5, 8.40, 0.0, 1.40, 345.00, 218.00,
   "Enterprise asset-intelligence firm in barcode, RFID and warehouse-automation robotics.")
_c("SYM", "Symbotic Inc.", "robotics", 28.40, 3.21, 16.5 * B, None, 2_200_000,
   1.8 * B, -3.0, -0.20, 0.0, 2.10, 64.00, 18.00,
   "Warehouse-automation company deploying AI-powered robotic systems for retailers.")
_c("PATH", "UiPath Inc.", "robotics", 12.85, 2.14, 7.2 * B, None, 9_000_000,
   1.4 * B, 5.0, 0.10, 0.0, 1.55, 25.00, 10.40,
   "Robotic process automation (RPA) software platform automating enterprise workflows.")
_c("IRBT", "iRobot Corp.", "robotics", 9.60, 1.41, 0.3 * B, None, 1_100_000,
   0.9 * B, -15.0, -1.80, 0.0, 1.70, 24.00, 6.50,
   "Consumer-robotics maker of the Roomba line of autonomous home-cleaning devices.")

# --- EVs & Automotive ---
_c("TSLA", "Tesla Inc.", "ev_auto", 248.50, 2.04, 790 * B, 65.0, 95_000_000,
   97 * B, 13.0, 3.65, 0.0, 2.30, 299.00, 138.00,
   "Electric-vehicle and energy-storage leader expanding into autonomy and robotics.")
_c("RIVN", "Rivian Automotive", "ev_auto", 13.20, 3.52, 13.0 * B, None, 40_000_000,
   4.9 * B, -80.0, -4.50, 0.0, 2.10, 28.00, 8.50,
   "EV startup building electric trucks, SUVs and commercial delivery vans.")
_c("LCID", "Lucid Group", "ev_auto", 3.10, 4.03, 7.1 * B, None, 60_000_000,
   0.8 * B, -300.0, -1.20, 0.0, 1.95, 5.30, 2.20,
   "Luxury EV maker producing the long-range Air sedan and Gravity SUV.")
_c("GM", "General Motors", "ev_auto", 47.80, 0.63, 53 * B, 6.0, 12_000_000,
   172 * B, 5.5, 8.10, 1.0, 1.30, 52.00, 30.00,
   "Legacy automaker scaling its Ultium EV platform alongside ICE trucks and SUVs.")
_c("F", "Ford Motor Co.", "ev_auto", 11.40, 0.44, 45 * B, 11.0, 55_000_000,
   176 * B, 2.5, 1.05, 5.2, 1.45, 14.85, 9.50,
   "Global automaker investing in electric trucks and vans through its Model e unit.")
_c("NIO", "NIO Inc.", "ev_auto", 4.80, 5.12, 9.5 * B, None, 50_000_000,
   9.0 * B, -30.0, -1.10, 0.0, 1.85, 9.60, 3.60,
   "Chinese premium EV maker known for battery-swap stations and smart EVs.")
_c("LI", "Li Auto Inc.", "ev_auto", 24.30, 2.81, 25 * B, 18.0, 8_000_000,
   18.0 * B, 9.0, 1.35, 0.0, 1.40, 46.00, 18.00,
   "Chinese EV maker specializing in extended-range electric SUVs.")

# --- Cybersecurity ---
_c("CRWD", "CrowdStrike Holdings", "cybersecurity", 360.20, 1.83, 88 * B, 90.0, 3_500_000,
   3.7 * B, 6.0, 1.20, 0.0, 1.15, 398.00, 200.00,
   "Cloud-native endpoint and threat-intelligence platform built on the Falcon architecture.")
_c("PANW", "Palo Alto Networks", "cybersecurity", 178.40, 1.21, 115 * B, 47.0, 6_000_000,
   8.0 * B, 25.0, 3.30, 0.0, 1.10, 207.00, 135.00,
   "Broad cybersecurity platform spanning network, cloud and AI-driven security operations.")
_c("ZS", "Zscaler Inc.", "cybersecurity", 195.60, 1.54, 29 * B, None, 2_000_000,
   2.2 * B, 2.0, 0.30, 0.0, 1.20, 259.00, 165.00,
   "Zero-trust cloud-security platform securing user-to-app traffic at scale.")
_c("FTNT", "Fortinet Inc.", "cybersecurity", 78.30, 0.92, 60 * B, 42.0, 5_000_000,
   5.7 * B, 28.0, 1.85, 0.0, 1.05, 97.00, 54.00,
   "Network-security vendor known for firewalls and a broad integrated security fabric.")
_c("S", "SentinelOne Inc.", "cybersecurity", 22.10, 2.41, 7.0 * B, None, 6_000_000,
   0.8 * B, -30.0, -0.55, 0.0, 1.40, 30.00, 17.00,
   "AI-driven autonomous endpoint and cloud-security platform (Singularity).")
_c("OKTA", "Okta Inc.", "cybersecurity", 92.50, 1.13, 16 * B, None, 3_000_000,
   2.5 * B, 3.0, 0.20, 0.0, 1.25, 114.00, 70.00,
   "Identity and access-management platform securing workforce and customer logins.")
_c("CYBR", "CyberArk Software", "cybersecurity", 285.40, 1.34, 13 * B, 110.0, 700_000,
   0.9 * B, 5.0, 1.40, 0.0, 1.10, 320.00, 195.00,
   "Identity-security leader specializing in privileged-access management.")

# --- Biotech & Pharma ---
_c("LLY", "Eli Lilly & Co.", "biotech", 815.30, 1.42, 775 * B, 110.0, 3_000_000,
   40 * B, 22.0, 7.40, 0.6, 0.40, 972.00, 580.00,
   "Pharma leader behind GLP-1 blockbusters for diabetes and obesity (Mounjaro, Zepbound).")
_c("NVO", "Novo Nordisk", "biotech", 118.70, 0.91, 530 * B, 42.0, 6_000_000,
   40 * B, 35.0, 2.80, 1.0, 0.30, 148.00, 100.00,
   "Danish pharma dominating the GLP-1 obesity and diabetes market (Ozempic, Wegovy).")
_c("AMGN", "Amgen Inc.", "biotech", 295.40, 0.51, 158 * B, 30.0, 2_500_000,
   33 * B, 18.0, 9.80, 3.0, 0.60, 339.00, 255.00,
   "Biotech pioneer with a broad portfolio in inflammation, oncology and obesity.")
_c("GILD", "Gilead Sciences", "biotech", 72.10, 0.74, 90 * B, 22.0, 6_000_000,
   27 * B, 20.0, 3.20, 4.3, 0.30, 92.00, 62.00,
   "Antiviral and oncology biotech anchored by its HIV franchise and growing cell therapy.")
_c("REGN", "Regeneron Pharma.", "biotech", 905.20, 1.04, 98 * B, 25.0, 600_000,
   13 * B, 30.0, 38.50, 0.0, 0.50, 1210.00, 745.00,
   "Biotech behind Eylea and Dupixent with a deep antibody and genetics pipeline.")
_c("VRTX", "Vertex Pharma.", "biotech", 462.80, 0.83, 119 * B, 28.0, 1_200_000,
   10 * B, 30.0, 14.20, 0.0, 0.45, 519.00, 370.00,
   "Cystic-fibrosis franchise leader expanding into pain and gene-edited therapies.")
_c("MRNA", "Moderna Inc.", "biotech", 32.40, 2.21, 12.5 * B, None, 7_000_000,
   4.0 * B, -50.0, -8.50, 0.0, 1.30, 170.00, 28.00,
   "mRNA-platform biotech moving beyond COVID vaccines into oncology and rare disease.")

# --- Fintech ---
_c("V", "Visa Inc.", "fintech", 275.60, 0.61, 540 * B, 30.0, 6_000_000,
   35 * B, 53.0, 9.20, 0.8, 0.95, 290.00, 245.00,
   "Global payments network processing card transactions across 200+ markets.")
_c("MA", "Mastercard Inc.", "fintech", 470.30, 0.72, 435 * B, 36.0, 3_000_000,
   27 * B, 45.0, 13.00, 0.6, 1.05, 490.00, 395.00,
   "Global payments-technology network powering credit, debit and digital commerce.")
_c("PYPL", "PayPal Holdings", "fintech", 68.40, 1.13, 70 * B, 18.0, 12_000_000,
   31 * B, 14.0, 3.90, 0.0, 1.40, 87.00, 56.00,
   "Digital-payments platform spanning PayPal, Venmo and Braintree checkout.")
_c("XYZ", "Block Inc.", "fintech", 68.90, 2.04, 42 * B, 55.0, 9_000_000,
   24 * B, 4.0, 1.20, 0.0, 2.40, 99.00, 52.00,
   "Fintech behind Square seller tools and the Cash App consumer ecosystem.")
_c("COIN", "Coinbase Global", "fintech", 215.30, 4.52, 53 * B, 38.0, 8_000_000,
   5.0 * B, 30.0, 5.60, 0.0, 3.50, 280.00, 130.00,
   "Largest US crypto exchange for trading, custody and on-chain financial services.")
_c("SOFI", "SoFi Technologies", "fintech", 8.70, 3.04, 9.3 * B, 60.0, 45_000_000,
   2.3 * B, 8.0, 0.15, 0.0, 1.80, 12.00, 6.00,
   "Digital-first personal-finance platform for lending, banking and investing.")
_c("AFRM", "Affirm Holdings", "fintech", 38.50, 3.82, 12 * B, None, 9_000_000,
   2.3 * B, -10.0, -0.60, 0.0, 3.20, 52.00, 22.00,
   "Buy-now-pay-later lender embedding installment financing at online checkout.")

# --- Cloud & Software ---
_c("ORCL", "Oracle Corp.", "cloud", 142.80, 1.02, 395 * B, 38.0, 8_000_000,
   53 * B, 21.0, 3.80, 1.1, 1.05, 153.00, 99.00,
   "Enterprise database and applications giant scaling OCI cloud and AI infrastructure.")
_c("ADBE", "Adobe Inc.", "cloud", 510.40, 0.83, 228 * B, 38.0, 3_000_000,
   21 * B, 26.0, 13.40, 0.0, 1.30, 638.00, 433.00,
   "Creative and document-cloud software leader embedding Firefly generative AI.")
_c("SAP", "SAP SE", "cloud", 215.60, 0.62, 250 * B, 45.0, 1_500_000,
   34 * B, 14.0, 4.70, 1.0, 1.00, 230.00, 145.00,
   "European enterprise-software leader migrating customers to cloud ERP (S/4HANA).")
_c("NET", "Cloudflare Inc.", "cloud", 95.20, 2.31, 32 * B, None, 6_000_000,
   1.6 * B, 2.0, 0.10, 0.0, 1.60, 116.00, 65.00,
   "Connectivity-cloud platform delivering CDN, zero-trust security and edge compute.")
_c("DDOG", "Datadog Inc.", "cloud", 122.40, 1.73, 41 * B, 80.0, 4_000_000,
   2.6 * B, 8.0, 1.10, 0.0, 1.45, 168.00, 95.00,
   "Cloud-observability platform monitoring apps, infrastructure and security.")
_c("MDB", "MongoDB Inc.", "cloud", 248.70, 1.92, 18 * B, None, 2_000_000,
   2.0 * B, -5.0, -0.40, 0.0, 1.50, 410.00, 210.00,
   "Developer data platform behind the popular MongoDB Atlas managed database.")
_c("WDAY", "Workday Inc.", "cloud", 232.10, 0.92, 61 * B, 38.0, 2_000_000,
   8.0 * B, 8.0, 2.10, 0.0, 1.20, 295.00, 200.00,
   "Cloud HR and finance software suite for large enterprises.")

# --- Clean & Renewable Energy ---
_c("RUN", "Sunrun Inc.", "clean_energy", 14.60, 4.21, 3.2 * B, None, 9_000_000,
   2.3 * B, -10.0, -1.20, 0.0, 2.20, 22.00, 8.50,
   "Largest US residential-solar installer with a growing storage and subscription base.")
_c("SEDG", "SolarEdge Technologies", "clean_energy", 18.30, 3.51, 1.1 * B, None, 4_000_000,
   1.2 * B, -40.0, -5.00, 0.0, 2.00, 98.00, 10.00,
   "Solar-inverter and optimizer maker serving residential and commercial installers.")
_c("PLUG", "Plug Power Inc.", "clean_energy", 2.40, 5.04, 2.2 * B, None, 60_000_000,
   0.7 * B, -120.0, -1.40, 0.0, 2.40, 5.20, 1.60,
   "Green-hydrogen and fuel-cell company building electrolyzers and refueling networks.")
_c("BE", "Bloom Energy", "clean_energy", 12.80, 3.02, 2.9 * B, None, 7_000_000,
   1.3 * B, -10.0, -0.80, 0.0, 2.10, 19.00, 8.00,
   "Solid-oxide fuel-cell maker providing on-site clean power generation.")
_c("ORA", "Ormat Technologies", "clean_energy", 72.40, 0.92, 4.4 * B, 32.0, 500_000,
   0.8 * B, 14.0, 2.20, 0.4, 0.75, 88.00, 58.00,
   "Geothermal and energy-storage developer-operator of renewable baseload power.")
_c("CWEN", "Clearway Energy", "clean_energy", 27.50, 1.21, 3.3 * B, 28.0, 900_000,
   1.4 * B, 6.0, 0.95, 6.0, 0.85, 33.00, 22.00,
   "Owner-operator of US wind, solar and natural-gas clean-energy generation assets.")

# --- Defense & Aerospace ---
_c("LMT", "Lockheed Martin", "defense", 465.20, 0.51, 110 * B, 18.0, 1_200_000,
   69 * B, 9.5, 26.50, 2.7, 0.55, 510.00, 393.00,
   "World's largest defense contractor, prime on the F-35 and missile-defense systems.")
_c("RTX", "RTX Corp.", "defense", 118.60, 0.62, 158 * B, 22.0, 5_000_000,
   69 * B, 7.0, 5.20, 2.3, 0.85, 125.00, 88.00,
   "Aerospace-and-defense giant spanning Pratt & Whitney, Collins and Raytheon.")
_c("NOC", "Northrop Grumman", "defense", 478.30, 0.43, 70 * B, 18.0, 700_000,
   41 * B, 8.0, 25.40, 1.6, 0.60, 555.00, 425.00,
   "Defense prime in aeronautics, space and missile systems including the B-21 bomber.")
_c("GD", "General Dynamics", "defense", 285.70, 0.52, 78 * B, 20.0, 1_000_000,
   42 * B, 8.0, 13.60, 2.0, 0.70, 316.00, 240.00,
   "Aerospace-and-defense maker of Gulfstream jets, submarines and combat systems.")
_c("BA", "Boeing Co.", "defense", 178.40, 1.03, 110 * B, None, 6_000_000,
   78 * B, -8.0, -8.50, 0.0, 1.45, 267.00, 137.00,
   "Aerospace giant building commercial jets and defense, space and security systems.")
_c("LHX", "L3Harris Technologies", "defense", 235.60, 0.71, 44 * B, 21.0, 800_000,
   21 * B, 8.0, 11.20, 1.9, 0.70, 248.00, 185.00,
   "Defense-technology prime in communications, ISR, space and electronic warfare.")

# --- Banks & Financials ---
_c("JPM", "JPMorgan Chase", "financials", 215.40, 0.52, 615 * B, 12.0, 8_000_000,
   158 * B, 30.0, 17.50, 2.2, 1.10, 225.00, 165.00,
   "Largest US bank by assets, spanning consumer, commercial and investment banking.")
_c("BAC", "Bank of America", "financials", 42.30, 0.61, 325 * B, 13.0, 35_000_000,
   100 * B, 24.0, 3.25, 2.4, 1.30, 46.00, 33.00,
   "Diversified money-center bank with large consumer and global-markets franchises.")
_c("WFC", "Wells Fargo & Co.", "financials", 62.10, 0.72, 210 * B, 12.0, 15_000_000,
   82 * B, 22.0, 5.10, 2.5, 1.15, 68.00, 50.00,
   "Major US retail and commercial bank rebuilding after its asset-cap era.")
_c("GS", "Goldman Sachs", "financials", 480.20, 0.83, 155 * B, 14.0, 2_000_000,
   53 * B, 22.0, 34.00, 2.4, 1.40, 520.00, 380.00,
   "Premier global investment bank in trading, advisory and asset management.")
_c("MS", "Morgan Stanley", "financials", 102.50, 0.61, 165 * B, 16.0, 7_000_000,
   54 * B, 18.0, 6.40, 3.3, 1.35, 110.00, 80.00,
   "Investment bank and wealth-management leader with stable fee-based earnings.")
_c("C", "Citigroup Inc.", "financials", 63.40, 0.92, 120 * B, 11.0, 14_000_000,
   78 * B, 14.0, 5.80, 3.3, 1.40, 70.00, 50.00,
   "Global bank with leading treasury, trade and markets businesses across regions.")
_c("BLK", "BlackRock Inc.", "financials", 845.30, 0.71, 125 * B, 22.0, 600_000,
   19 * B, 31.0, 38.00, 2.4, 1.30, 905.00, 700.00,
   "World's largest asset manager, home of iShares ETFs and Aladdin risk software.")

# --- Healthcare ---
_c("UNH", "UnitedHealth Group", "healthcare", 525.60, 0.42, 485 * B, 22.0, 3_000_000,
   372 * B, 6.0, 23.50, 1.5, 0.55, 610.00, 436.00,
   "Largest US health insurer plus the fast-growing Optum care-services arm.")
_c("JNJ", "Johnson & Johnson", "healthcare", 152.30, 0.31, 367 * B, 15.0, 7_000_000,
   86 * B, 18.0, 9.90, 3.2, 0.55, 168.00, 143.00,
   "Diversified healthcare giant in pharmaceuticals and medical-technology devices.")
_c("ABT", "Abbott Laboratories", "healthcare", 113.80, 0.52, 198 * B, 32.0, 5_000_000,
   41 * B, 13.0, 3.50, 1.9, 0.75, 121.00, 99.00,
   "Diversified medical-device, diagnostics and nutrition company.")
_c("MDT", "Medtronic plc", "healthcare", 86.40, 0.41, 111 * B, 17.0, 6_000_000,
   32 * B, 12.0, 3.10, 3.2, 0.80, 91.00, 75.00,
   "Global medical-device leader in cardiac, surgical and diabetes technologies.")
_c("CVS", "CVS Health Corp.", "healthcare", 58.70, 0.61, 74 * B, 11.0, 8_000_000,
   358 * B, 1.5, 5.30, 4.3, 0.65, 83.00, 53.00,
   "Integrated health company spanning pharmacy, insurance (Aetna) and clinics.")
_c("ISRG", "Intuitive Surgical", "healthcare", 478.20, 1.04, 168 * B, 70.0, 1_500_000,
   8.0 * B, 27.0, 6.80, 0.0, 1.20, 520.00, 360.00,
   "Surgical-robotics leader behind the da Vinci minimally invasive systems.")
_c("TMO", "Thermo Fisher Scientific", "healthcare", 562.40, 0.52, 215 * B, 33.0, 1_200_000,
   43 * B, 15.0, 17.00, 0.3, 0.80, 610.00, 490.00,
   "Life-sciences instruments, reagents and lab-services leader serving research.")

# --- Consumer & Retail ---
_c("WMT", "Walmart Inc.", "consumer", 67.80, 0.51, 545 * B, 30.0, 14_000_000,
   665 * B, 2.5, 2.25, 1.2, 0.50, 70.00, 49.00,
   "World's largest retailer scaling e-commerce, advertising and marketplace.")
_c("COST", "Costco Wholesale", "consumer", 875.30, 0.62, 388 * B, 50.0, 2_000_000,
   254 * B, 2.9, 16.50, 0.5, 0.80, 920.00, 600.00,
   "Membership-warehouse retailer with loyal members and steady comp growth.")
_c("HD", "Home Depot Inc.", "consumer", 358.40, 0.41, 355 * B, 24.0, 3_000_000,
   152 * B, 9.8, 14.90, 2.4, 1.00, 396.00, 310.00,
   "Largest home-improvement retailer serving DIY and professional contractors.")
_c("NKE", "Nike Inc.", "consumer", 78.60, 0.72, 117 * B, 22.0, 8_000_000,
   51 * B, 11.0, 3.60, 1.7, 1.05, 123.00, 70.00,
   "Global athletic-footwear and apparel leader with a direct-to-consumer focus.")
_c("MCD", "McDonald's Corp.", "consumer", 292.50, 0.31, 210 * B, 24.0, 3_000_000,
   26 * B, 33.0, 12.20, 2.3, 0.65, 320.00, 245.00,
   "Global quick-service restaurant franchisor with strong brand and pricing power.")
_c("SBUX", "Starbucks Corp.", "consumer", 95.40, 0.82, 108 * B, 25.0, 8_000_000,
   36 * B, 11.0, 3.80, 2.4, 1.00, 116.00, 71.00,
   "Global coffee-house chain investing in loyalty, mobile ordering and China.")
_c("TGT", "Target Corp.", "consumer", 145.20, 0.61, 67 * B, 15.0, 4_000_000,
   107 * B, 4.0, 9.50, 3.0, 1.15, 181.00, 120.00,
   "Big-box retailer balancing discretionary and essentials with owned brands.")

# --- Communications & Media ---
_c("DIS", "Walt Disney Co.", "comms", 102.40, 0.92, 186 * B, 35.0, 9_000_000,
   91 * B, 5.0, 2.90, 0.9, 1.40, 123.00, 83.00,
   "Media-and-entertainment giant in streaming, parks, studios and sports (ESPN).")
_c("NFLX", "Netflix Inc.", "comms", 685.30, 1.31, 295 * B, 42.0, 3_000_000,
   38 * B, 22.0, 16.20, 0.0, 1.25, 700.00, 440.00,
   "Streaming-video leader scaling ad-supported tiers and a password-sharing crackdown.")
_c("CMCSA", "Comcast Corp.", "comms", 39.80, 0.41, 155 * B, 10.0, 14_000_000,
   122 * B, 13.0, 4.00, 3.0, 0.95, 47.00, 36.00,
   "Cable, broadband and media conglomerate (NBCUniversal, Peacock, Sky).")
_c("T", "AT&T Inc.", "comms", 18.90, 0.53, 135 * B, 8.0, 30_000_000,
   122 * B, 11.0, 2.30, 5.8, 0.65, 20.00, 15.00,
   "Telecom carrier focused on wireless and fiber broadband after media spinoffs.")
_c("VZ", "Verizon Communications", "comms", 41.60, 0.42, 175 * B, 9.0, 18_000_000,
   134 * B, 8.0, 4.50, 6.4, 0.45, 45.00, 30.00,
   "Wireless-and-broadband carrier with a large dividend and 5G investment cycle.")
_c("TMUS", "T-Mobile US", "comms", 198.30, 0.71, 233 * B, 23.0, 4_000_000,
   79 * B, 11.0, 8.40, 1.5, 0.55, 210.00, 150.00,
   "Wireless carrier leading in 5G with strong postpaid subscriber growth.")
_c("WBD", "Warner Bros. Discovery", "comms", 8.20, 1.52, 20 * B, None, 25_000_000,
   40 * B, -10.0, -1.60, 0.0, 1.50, 13.00, 6.50,
   "Media company combining Warner Bros. studios, HBO Max and Discovery networks.")

# --- Industrials ---
_c("CAT", "Caterpillar Inc.", "industrials", 348.60, 0.61, 168 * B, 16.0, 3_000_000,
   67 * B, 16.0, 21.50, 1.5, 1.10, 418.00, 290.00,
   "World's largest construction and mining-equipment maker with energy and rail units.")
_c("DE", "Deere & Co.", "industrials", 378.40, 0.52, 103 * B, 13.0, 2_000_000,
   55 * B, 16.0, 28.50, 1.4, 0.95, 420.00, 340.00,
   "Agricultural and construction-equipment leader investing in precision-ag tech.")
_c("HON", "Honeywell International", "industrials", 205.30, 0.41, 134 * B, 22.0, 3_000_000,
   38 * B, 15.0, 9.20, 2.0, 1.00, 220.00, 175.00,
   "Diversified industrial in aerospace, automation, building tech and materials.")
_c("UPS", "United Parcel Service", "industrials", 132.70, 0.51, 113 * B, 18.0, 4_000_000,
   91 * B, 7.0, 7.40, 4.6, 1.05, 165.00, 122.00,
   "Global parcel-logistics carrier balancing volume, pricing and automation.")
_c("MMM", "3M Co.", "industrials", 98.40, 0.62, 54 * B, 18.0, 4_000_000,
   33 * B, 12.0, 5.50, 2.9, 1.00, 110.00, 72.00,
   "Diversified industrial in safety, industrial, electronics and consumer products.")
_c("EMR", "Emerson Electric", "industrials", 108.50, 0.51, 62 * B, 24.0, 2_500_000,
   17 * B, 14.0, 4.50, 1.9, 1.15, 122.00, 90.00,
   "Industrial-automation and process-controls supplier for manufacturers.")
_c("ETN", "Eaton Corp.", "industrials", 312.80, 0.72, 124 * B, 32.0, 2_000_000,
   24 * B, 15.0, 9.80, 1.1, 1.10, 345.00, 220.00,
   "Power-management company benefiting from electrification and data-center demand.")


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


# The curated, hand-written headliners above are the "core" set that the worker
# keeps continuously fresh with live data. Everything added by the compact _q()
# loader below is catalog/breadth: it carries deterministic mock metrics and only
# pulls live data on demand when a user opens the symbol.
CORE_SYMBOLS: List[str] = list(COMPANIES.keys())


def _q(symbol, name, sector, mcap_b, *, country="United States",
       exchange="NASDAQ", pe=None, div=None, desc=None):
    """Register a catalog entry from a few inputs.

    All 16 display fields are derived deterministically from the symbol seed plus
    a market-cap hint (in USD billions), so hundreds of names can be added without
    hand-writing every metric and charts/screeners stay stable across restarts.
    """
    seed = _seed(symbol)

    def nxt(lo, hi):
        nonlocal seed
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        return lo + (seed / 0x7FFFFFFF) * (hi - lo)

    market_cap = mcap_b * B
    price = round(nxt(9.0, 480.0), 2)
    change_pct = round(nxt(-3.2, 3.4), 2)
    beta = round(nxt(0.55, 1.95), 2)
    net_margin = round(nxt(3.0, 36.0), 1)
    if pe is None:
        pe = round(nxt(11.0, 48.0), 1)
    eps = round(price / pe, 2) if pe and pe > 0 else round(price * 0.04, 2)
    revenue = round(market_cap * nxt(0.18, 0.95))
    shares = market_cap / price if price else 0
    volume = int(shares * nxt(0.002, 0.012))
    if div is None:
        coin = nxt(0.0, 1.0)
        div = round(nxt(0.0, 3.2), 2) if coin > 0.45 else 0.0
    hi = round(price * nxt(1.08, 1.55), 2)
    lo = round(price * nxt(0.52, 0.88), 2)
    if desc is None:
        desc = (f"{name} is a {country}-listed company in the "
                f"{SECTORS.get(sector, sector)} sector.")
    COMPANIES[symbol] = {
        "symbol": symbol, "name": name, "sector": sector, "price": price,
        "changePct": change_pct, "marketCap": market_cap, "peRatio": pe,
        "volume": volume, "revenue": revenue, "netMargin": net_margin,
        "eps": eps, "dividendYield": div, "beta": beta, "week52High": hi,
        "week52Low": lo, "description": desc, "country": country,
        "exchange": exchange,
    }


def _load(rows, *, country="United States", exchange="NASDAQ"):
    """Bulk-register (symbol, name, sector, mcap_b) tuples without clobbering
    any curated headliner already present."""
    for sym, nm, sec, mc in rows:
        if sym not in COMPANIES:
            _q(sym, nm, sec, mc, country=country, exchange=exchange)


def yahoo_symbol(symbol: str) -> str:
    """Translate an internal symbol to the symbol Yahoo Finance expects.

    Singapore (SGX) names are catalogued under their base code (e.g. ``D05``) but
    Yahoo requires the ``.SI`` suffix, so callers never have to type it."""
    s = (symbol or "").upper()
    c = COMPANIES.get(s)
    if c and c.get("exchange") == "SGX":
        return f"{s}.SI"
    return s


def top_symbols(limit: int = 80) -> List[str]:
    """Most-valuable names first (used to keep LLM prompts lean)."""
    ordered = sorted(COMPANIES.items(),
                     key=lambda kv: kv[1].get("marketCap", 0), reverse=True)
    return [s for s, _ in ordered[:limit]]


def resolve_symbol(text: str) -> Optional[str]:
    """Best-effort name/code -> symbol resolution (case-insensitive)."""
    if not text:
        return None
    t = text.strip()
    up = t.upper()
    if up in COMPANIES:
        return up
    low = t.lower()
    for sym, c in COMPANIES.items():
        if c["name"].lower() == low:
            return sym
    for sym, c in COMPANIES.items():
        first = c["name"].split()[0].lower()
        if len(first) > 2 and first == low:
            return sym
    return None


# ---------------------------------------------------------------------------
# Deep curated catalog. Compact (symbol, name, sector, market_cap_billions)
# tuples; metrics derived deterministically by _q(). The _load() guard keeps any
# curated headliner above from being overwritten.
# ---------------------------------------------------------------------------
_US: List[tuple] = [
    # Semiconductors
    ("TXN", "Texas Instruments", "semiconductors", 165), ("ADI", "Analog Devices", "semiconductors", 110),
    ("NXPI", "NXP Semiconductors", "semiconductors", 60), ("MCHP", "Microchip Technology", "semiconductors", 45),
    ("ON", "ON Semiconductor", "semiconductors", 30), ("MRVL", "Marvell Technology", "semiconductors", 60),
    ("KLAC", "KLA Corp.", "semiconductors", 95), ("LRCX", "Lam Research", "semiconductors", 95),
    ("AMAT", "Applied Materials", "semiconductors", 150), ("SWKS", "Skyworks Solutions", "semiconductors", 17),
    ("MPWR", "Monolithic Power Systems", "semiconductors", 38), ("GFS", "GlobalFoundries", "semiconductors", 28),
    ("QRVO", "Qorvo Inc.", "semiconductors", 10), ("LSCC", "Lattice Semiconductor", "semiconductors", 8),
    ("ARM", "Arm Holdings", "semiconductors", 130), ("SMCI", "Super Micro Computer", "semiconductors", 35),
    ("WOLF", "Wolfspeed Inc.", "semiconductors", 5), ("ALGM", "Allegro MicroSystems", "semiconductors", 6),
    ("AMKR", "Amkor Technology", "semiconductors", 9), ("ENTG", "Entegris Inc.", "semiconductors", 18),
    # AI / Tech hardware & IT services
    ("AAPL", "Apple Inc.", "ai_tech", 3300), ("IBM", "IBM Corp.", "ai_tech", 200),
    ("CSCO", "Cisco Systems", "ai_tech", 230), ("ANET", "Arista Networks", "ai_tech", 110),
    ("DELL", "Dell Technologies", "ai_tech", 90), ("HPQ", "HP Inc.", "ai_tech", 35),
    ("HPE", "Hewlett Packard Enterprise", "ai_tech", 25), ("ACN", "Accenture plc", "ai_tech", 220),
    ("UBER", "Uber Technologies", "ai_tech", 150), ("AI", "C3.ai Inc.", "ai_tech", 3),
    ("BBAI", "BigBear.ai Holdings", "ai_tech", 1), ("SOUN", "SoundHound AI", "ai_tech", 2),
    ("PSTG", "Pure Storage", "ai_tech", 18), ("NTAP", "NetApp Inc.", "ai_tech", 25),
    ("WDC", "Western Digital", "ai_tech", 22), ("STX", "Seagate Technology", "ai_tech", 22),
    ("JBL", "Jabil Inc.", "ai_tech", 15), ("EPAM", "EPAM Systems", "ai_tech", 12),
    ("CDW", "CDW Corp.", "ai_tech", 30), ("GLW", "Corning Inc.", "ai_tech", 35),
    ("APH", "Amphenol Corp.", "ai_tech", 80), ("TEL", "TE Connectivity", "ai_tech", 45),
    ("KEYS", "Keysight Technologies", "ai_tech", 28), ("FFIV", "F5 Inc.", "ai_tech", 12),
    # Cloud & software
    ("INTU", "Intuit Inc.", "cloud", 180), ("SHOP", "Shopify Inc.", "cloud", 110),
    ("ABNB", "Airbnb Inc.", "cloud", 90), ("DOCU", "DocuSign Inc.", "cloud", 12),
    ("TEAM", "Atlassian Corp.", "cloud", 50), ("ZM", "Zoom Video", "cloud", 22),
    ("HUBS", "HubSpot Inc.", "cloud", 30), ("TWLO", "Twilio Inc.", "cloud", 12),
    ("DBX", "Dropbox Inc.", "cloud", 9), ("BOX", "Box Inc.", "cloud", 4),
    ("GTLB", "GitLab Inc.", "cloud", 9), ("FROG", "JFrog Ltd.", "cloud", 4),
    ("ESTC", "Elastic N.V.", "cloud", 10), ("CFLT", "Confluent Inc.", "cloud", 9),
    ("ASAN", "Asana Inc.", "cloud", 4), ("MNDY", "monday.com", "cloud", 12),
    ("PCOR", "Procore Technologies", "cloud", 10), ("BILL", "BILL Holdings", "cloud", 7),
    ("U", "Unity Software", "cloud", 8), ("RBLX", "Roblox Corp.", "cloud", 30),
    ("DASH", "DoorDash Inc.", "cloud", 60), ("WIX", "Wix.com Ltd.", "cloud", 9),
    ("APP", "AppLovin Corp.", "cloud", 100), ("AKAM", "Akamai Technologies", "cloud", 14),
    ("VRSN", "VeriSign Inc.", "cloud", 20), ("DOCN", "DigitalOcean Holdings", "cloud", 4),
    ("GEN", "Gen Digital Inc.", "cloud", 18), ("ZI", "ZoomInfo Technologies", "cloud", 5),
    ("WDAY", "Workday Inc.", "cloud", 65),
    # Fintech
    ("HOOD", "Robinhood Markets", "fintech", 50), ("NU", "Nu Holdings", "fintech", 60),
    ("FOUR", "Shift4 Payments", "fintech", 8), ("GPN", "Global Payments", "fintech", 25),
    ("FIS", "Fidelity National Info", "fintech", 45), ("FI", "Fiserv Inc.", "fintech", 90),
    ("TOST", "Toast Inc.", "fintech", 18), ("UPST", "Upstart Holdings", "fintech", 6),
    ("ADYEY", "Adyen N.V.", "fintech", 50), ("JKHY", "Jack Henry & Associates", "fintech", 13),
    ("BR", "Broadridge Financial", "fintech", 25), ("FLYW", "Flywire Corp.", "fintech", 3),
    # Banks & financials
    ("USB", "U.S. Bancorp", "financials", 75), ("PNC", "PNC Financial Services", "financials", 75),
    ("TFC", "Truist Financial", "financials", 60), ("COF", "Capital One Financial", "financials", 60),
    ("SCHW", "Charles Schwab", "financials", 130), ("AXP", "American Express", "financials", 200),
    ("BK", "Bank of New York Mellon", "financials", 55), ("STT", "State Street Corp.", "financials", 28),
    ("NTRS", "Northern Trust", "financials", 20), ("FITB", "Fifth Third Bancorp", "financials", 28),
    ("HBAN", "Huntington Bancshares", "financials", 22), ("RF", "Regions Financial", "financials", 22),
    ("KEY", "KeyCorp", "financials", 18), ("CFG", "Citizens Financial", "financials", 20),
    ("MTB", "M&T Bank Corp.", "financials", 30), ("ALLY", "Ally Financial", "financials", 12),
    ("DFS", "Discover Financial", "financials", 35), ("SYF", "Synchrony Financial", "financials", 25),
    ("CMA", "Comerica Inc.", "financials", 8), ("ZION", "Zions Bancorporation", "financials", 8),
    ("RJF", "Raymond James Financial", "financials", 30), ("NDAQ", "Nasdaq Inc.", "financials", 40),
    ("ICE", "Intercontinental Exchange", "financials", 90), ("CME", "CME Group", "financials", 80),
    ("CBOE", "Cboe Global Markets", "financials", 22), ("TROW", "T. Rowe Price", "financials", 25),
    ("AMP", "Ameriprise Financial", "financials", 45), ("BEN", "Franklin Resources", "financials", 12),
    ("MSCI", "MSCI Inc.", "financials", 45),
    # Insurance
    ("PGR", "Progressive Corp.", "insurance", 145), ("ALL", "Allstate Corp.", "insurance", 50),
    ("TRV", "Travelers Companies", "insurance", 55), ("CB", "Chubb Ltd.", "insurance", 110),
    ("AIG", "American International Group", "insurance", 50), ("MET", "MetLife Inc.", "insurance", 55),
    ("PRU", "Prudential Financial", "insurance", 45), ("AFL", "Aflac Inc.", "insurance", 65),
    ("HIG", "Hartford Financial", "insurance", 35), ("CINF", "Cincinnati Financial", "insurance", 22),
    ("PFG", "Principal Financial", "insurance", 20), ("GL", "Globe Life Inc.", "insurance", 10),
    ("AON", "Aon plc", "insurance", 75), ("MMC", "Marsh & McLennan", "insurance", 110),
    ("WTW", "Willis Towers Watson", "insurance", 35), ("BRO", "Brown & Brown", "insurance", 30),
    ("AJG", "Arthur J. Gallagher", "insurance", 70), ("ACGL", "Arch Capital Group", "insurance", 40),
    ("EG", "Everest Group", "insurance", 18), ("RGA", "Reinsurance Group", "insurance", 14),
    ("UNM", "Unum Group", "insurance", 10),
    # Healthcare
    ("PFE", "Pfizer Inc.", "healthcare", 160), ("MRK", "Merck & Co.", "healthcare", 250),
    ("ABBV", "AbbVie Inc.", "healthcare", 320), ("BMY", "Bristol-Myers Squibb", "healthcare", 110),
    ("DHR", "Danaher Corp.", "healthcare", 190), ("SYK", "Stryker Corp.", "healthcare", 130),
    ("BSX", "Boston Scientific", "healthcare", 130), ("BDX", "Becton Dickinson", "healthcare", 65),
    ("EW", "Edwards Lifesciences", "healthcare", 45), ("ZBH", "Zimmer Biomet", "healthcare", 22),
    ("BAX", "Baxter International", "healthcare", 18), ("HCA", "HCA Healthcare", "healthcare", 90),
    ("CI", "Cigna Group", "healthcare", 95), ("ELV", "Elevance Health", "healthcare", 110),
    ("HUM", "Humana Inc.", "healthcare", 35), ("CNC", "Centene Corp.", "healthcare", 30),
    ("MOH", "Molina Healthcare", "healthcare", 18), ("DVA", "DaVita Inc.", "healthcare", 12),
    ("LH", "Labcorp Holdings", "healthcare", 18), ("DGX", "Quest Diagnostics", "healthcare", 18),
    ("IDXX", "IDEXX Laboratories", "healthcare", 40), ("ALGN", "Align Technology", "healthcare", 18),
    ("RMD", "ResMed Inc.", "healthcare", 35), ("IQV", "IQVIA Holdings", "healthcare", 35),
    ("MTD", "Mettler-Toledo", "healthcare", 28), ("WAT", "Waters Corp.", "healthcare", 22),
    ("A", "Agilent Technologies", "healthcare", 40), ("GEHC", "GE HealthCare", "healthcare", 38),
    ("COR", "Cencora Inc.", "healthcare", 45), ("MCK", "McKesson Corp.", "healthcare", 75),
    ("CAH", "Cardinal Health", "healthcare", 28), ("ZTS", "Zoetis Inc.", "healthcare", 80),
    ("DXCM", "DexCom Inc.", "healthcare", 30), ("PODD", "Insulet Corp.", "healthcare", 18),
    # Biotech
    ("BIIB", "Biogen Inc.", "biotech", 25), ("ALNY", "Alnylam Pharmaceuticals", "biotech", 35),
    ("BMRN", "BioMarin Pharmaceutical", "biotech", 14), ("INCY", "Incyte Corp.", "biotech", 14),
    ("EXAS", "Exact Sciences", "biotech", 12), ("NBIX", "Neurocrine Biosciences", "biotech", 14),
    ("SRPT", "Sarepta Therapeutics", "biotech", 12), ("RARE", "Ultragenyx Pharmaceutical", "biotech", 4),
    ("IONS", "Ionis Pharmaceuticals", "biotech", 6), ("UTHR", "United Therapeutics", "biotech", 18),
    ("HALO", "Halozyme Therapeutics", "biotech", 8), ("CRSP", "CRISPR Therapeutics", "biotech", 4),
    ("NTLA", "Intellia Therapeutics", "biotech", 2), ("BEAM", "Beam Therapeutics", "biotech", 2),
    ("ARWR", "Arrowhead Pharmaceuticals", "biotech", 3), ("ACAD", "Acadia Pharmaceuticals", "biotech", 3),
    ("JAZZ", "Jazz Pharmaceuticals", "biotech", 8), ("BPMC", "Blueprint Medicines", "biotech", 6),
    ("MRTX", "Mirati Therapeutics", "biotech", 3), ("RXRX", "Recursion Pharmaceuticals", "biotech", 3),
    ("VKTX", "Viking Therapeutics", "biotech", 5), ("MDGL", "Madrigal Pharmaceuticals", "biotech", 6),
    ("CYTK", "Cytokinetics Inc.", "biotech", 5), ("ROIV", "Roivant Sciences", "biotech", 8),
    # Consumer discretionary
    ("LOW", "Lowe's Companies", "consumer", 140), ("TJX", "TJX Companies", "consumer", 130),
    ("BKNG", "Booking Holdings", "consumer", 140), ("MAR", "Marriott International", "consumer", 75),
    ("HLT", "Hilton Worldwide", "consumer", 55), ("RCL", "Royal Caribbean Cruises", "consumer", 50),
    ("CCL", "Carnival Corp.", "consumer", 25), ("NCLH", "Norwegian Cruise Line", "consumer", 8),
    ("LULU", "Lululemon Athletica", "consumer", 35), ("ROST", "Ross Stores", "consumer", 50),
    ("DG", "Dollar General", "consumer", 30), ("DLTR", "Dollar Tree", "consumer", 22),
    ("BBY", "Best Buy Co.", "consumer", 18), ("ULTA", "Ulta Beauty", "consumer", 18),
    ("YUM", "Yum! Brands", "consumer", 38), ("CMG", "Chipotle Mexican Grill", "consumer", 80),
    ("DPZ", "Domino's Pizza", "consumer", 16), ("DRI", "Darden Restaurants", "consumer", 20),
    ("EBAY", "eBay Inc.", "consumer", 28), ("ETSY", "Etsy Inc.", "consumer", 7),
    ("CHWY", "Chewy Inc.", "consumer", 12), ("APTV", "Aptiv plc", "consumer", 18),
    ("LVS", "Las Vegas Sands", "consumer", 38), ("WYNN", "Wynn Resorts", "consumer", 10),
    ("MGM", "MGM Resorts", "consumer", 12), ("CZR", "Caesars Entertainment", "consumer", 8),
    ("EXPE", "Expedia Group", "consumer", 18), ("POOL", "Pool Corp.", "consumer", 14),
    ("GRMN", "Garmin Ltd.", "consumer", 30), ("ORLY", "O'Reilly Automotive", "consumer", 65),
    ("AZO", "AutoZone Inc.", "consumer", 50), ("TSCO", "Tractor Supply", "consumer", 30),
    ("KMX", "CarMax Inc.", "consumer", 12), ("DKNG", "DraftKings Inc.", "consumer", 18),
    ("RL", "Ralph Lauren", "consumer", 12), ("TPR", "Tapestry Inc.", "consumer", 12),
    ("DECK", "Deckers Outdoor", "consumer", 22), ("GPC", "Genuine Parts", "consumer", 18),
    # Consumer staples
    ("PG", "Procter & Gamble", "staples", 380), ("KO", "Coca-Cola Co.", "staples", 270),
    ("PEP", "PepsiCo Inc.", "staples", 230), ("MDLZ", "Mondelez International", "staples", 95),
    ("CL", "Colgate-Palmolive", "staples", 75), ("KMB", "Kimberly-Clark", "staples", 45),
    ("GIS", "General Mills", "staples", 38), ("KHC", "Kraft Heinz", "staples", 42),
    ("MO", "Altria Group", "staples", 95), ("PM", "Philip Morris International", "staples", 180),
    ("STZ", "Constellation Brands", "staples", 45), ("KDP", "Keurig Dr Pepper", "staples", 48),
    ("HSY", "Hershey Co.", "staples", 40), ("K", "Kellanova", "staples", 28),
    ("SYY", "Sysco Corp.", "staples", 38), ("ADM", "Archer-Daniels-Midland", "staples", 28),
    ("KR", "Kroger Co.", "staples", 40), ("KVUE", "Kenvue Inc.", "staples", 38),
    ("CHD", "Church & Dwight", "staples", 25), ("CLX", "Clorox Co.", "staples", 18),
    ("MKC", "McCormick & Co.", "staples", 20), ("HRL", "Hormel Foods", "staples", 16),
    ("TSN", "Tyson Foods", "staples", 22), ("CAG", "Conagra Brands", "staples", 14),
    ("CPB", "Campbell's Co.", "staples", 13), ("TAP", "Molson Coors Beverage", "staples", 12),
    ("BG", "Bunge Global", "staples", 14), ("EL", "Estée Lauder", "staples", 30),
    # Communications & media
    ("GOOG", "Alphabet Inc. (Class C)", "comms", 2100), ("SPOT", "Spotify Technology", "comms", 90),
    ("FOXA", "Fox Corp. (Class A)", "comms", 22), ("PARA", "Paramount Global", "comms", 8),
    ("NYT", "New York Times Co.", "comms", 9), ("OMC", "Omnicom Group", "comms", 18),
    ("IPG", "Interpublic Group", "comms", 12), ("TTD", "The Trade Desk", "comms", 55),
    ("ROKU", "Roku Inc.", "comms", 9), ("LYV", "Live Nation Entertainment", "comms", 22),
    ("WMG", "Warner Music Group", "comms", 16), ("EA", "Electronic Arts", "comms", 38),
    ("TTWO", "Take-Two Interactive", "comms", 28), ("MTCH", "Match Group", "comms", 9),
    ("PINS", "Pinterest Inc.", "comms", 25), ("SNAP", "Snap Inc.", "comms", 20),
    ("BIDU", "Baidu Inc.", "comms", 35), ("NWSA", "News Corp (Class A)", "comms", 16),
    ("FWONK", "Liberty Media Formula One", "comms", 18),
    # Telecom
    ("AMT", "American Tower", "telecom", 90), ("CCI", "Crown Castle", "telecom", 45),
    ("SBAC", "SBA Communications", "telecom", 25), ("LUMN", "Lumen Technologies", "telecom", 5),
    ("TDS", "Telephone & Data Systems", "telecom", 3), ("USM", "United States Cellular", "telecom", 5),
    ("IRDM", "Iridium Communications", "telecom", 3), ("GSAT", "Globalstar Inc.", "telecom", 3),
    ("FYBR", "Frontier Communications", "telecom", 8),
    # Industrials
    ("GE", "GE Aerospace", "industrials", 180), ("ITW", "Illinois Tool Works", "industrials", 75),
    ("PH", "Parker-Hannifin", "industrials", 80), ("ROP", "Roper Technologies", "industrials", 60),
    ("CMI", "Cummins Inc.", "industrials", 45), ("PCAR", "PACCAR Inc.", "industrials", 55),
    ("GWW", "W.W. Grainger", "industrials", 50), ("FAST", "Fastenal Co.", "industrials", 45),
    ("DOV", "Dover Corp.", "industrials", 28), ("IR", "Ingersoll Rand", "industrials", 38),
    ("AME", "AMETEK Inc.", "industrials", 42), ("XYL", "Xylem Inc.", "industrials", 30),
    ("IEX", "IDEX Corp.", "industrials", 16), ("NDSN", "Nordson Corp.", "industrials", 14),
    ("PNR", "Pentair plc", "industrials", 15), ("FTV", "Fortive Corp.", "industrials", 28),
    ("OTIS", "Otis Worldwide", "industrials", 40), ("CARR", "Carrier Global", "industrials", 60),
    ("JCI", "Johnson Controls", "industrials", 50), ("TT", "Trane Technologies", "industrials", 90),
    ("GNRC", "Generac Holdings", "industrials", 10), ("AOS", "A.O. Smith", "industrials", 12),
    ("WAB", "Wabtec Corp.", "industrials", 35), ("PWR", "Quanta Services", "industrials", 45),
    ("URI", "United Rentals", "industrials", 50), ("FERG", "Ferguson Enterprises", "industrials", 40),
    ("LII", "Lennox International", "industrials", 22), ("MAS", "Masco Corp.", "industrials", 16),
    ("ALLE", "Allegion plc", "industrials", 12), ("SWK", "Stanley Black & Decker", "industrials", 14),
    ("SNA", "Snap-on Inc.", "industrials", 18),
    # Transportation & logistics
    ("FDX", "FedEx Corp.", "transportation", 70), ("UNP", "Union Pacific", "transportation", 145),
    ("CSX", "CSX Corp.", "transportation", 65), ("NSC", "Norfolk Southern", "transportation", 55),
    ("CHRW", "C.H. Robinson Worldwide", "transportation", 12), ("JBHT", "J.B. Hunt Transport", "transportation", 18),
    ("EXPD", "Expeditors International", "transportation", 18), ("XPO", "XPO Inc.", "transportation", 16),
    ("KNX", "Knight-Swift Transportation", "transportation", 8), ("LSTR", "Landstar System", "transportation", 6),
    ("DAL", "Delta Air Lines", "transportation", 35), ("UAL", "United Airlines Holdings", "transportation", 18),
    ("AAL", "American Airlines Group", "transportation", 9), ("LUV", "Southwest Airlines", "transportation", 18),
    ("ALK", "Alaska Air Group", "transportation", 8), ("GXO", "GXO Logistics", "transportation", 6),
    ("MATX", "Matson Inc.", "transportation", 5), ("ZIM", "ZIM Integrated Shipping", "transportation", 3),
    ("ODFL", "Old Dominion Freight Line", "transportation", 40),
    # Materials & chemicals
    ("LIN", "Linde plc", "materials", 220), ("SHW", "Sherwin-Williams", "materials", 90),
    ("APD", "Air Products and Chemicals", "materials", 65), ("ECL", "Ecolab Inc.", "materials", 65),
    ("DD", "DuPont de Nemours", "materials", 35), ("DOW", "Dow Inc.", "materials", 38),
    ("PPG", "PPG Industries", "materials", 28), ("VMC", "Vulcan Materials", "materials", 35),
    ("MLM", "Martin Marietta Materials", "materials", 35), ("CTVA", "Corteva Inc.", "materials", 42),
    ("LYB", "LyondellBasell Industries", "materials", 30), ("IFF", "Intl. Flavors & Fragrances", "materials", 25),
    ("ALB", "Albemarle Corp.", "materials", 12), ("CE", "Celanese Corp.", "materials", 14),
    ("EMN", "Eastman Chemical", "materials", 12), ("CF", "CF Industries Holdings", "materials", 16),
    ("MOS", "Mosaic Co.", "materials", 9), ("FMC", "FMC Corp.", "materials", 8),
    ("AVY", "Avery Dennison", "materials", 18), ("PKG", "Packaging Corp. of America", "materials", 18),
    ("IP", "International Paper", "materials", 18), ("RPM", "RPM International", "materials", 16),
    ("AXTA", "Axalta Coating Systems", "materials", 8),
    # Metals & mining
    ("NEM", "Newmont Corp.", "metals_mining", 50), ("FCX", "Freeport-McMoRan", "metals_mining", 65),
    ("GOLD", "Barrick Gold", "metals_mining", 30), ("AEM", "Agnico Eagle Mines", "metals_mining", 40),
    ("WPM", "Wheaton Precious Metals", "metals_mining", 30), ("FNV", "Franco-Nevada", "metals_mining", 25),
    ("RGLD", "Royal Gold", "metals_mining", 9), ("KGC", "Kinross Gold", "metals_mining", 18),
    ("AU", "AngloGold Ashanti", "metals_mining", 18, ), ("AGI", "Alamos Gold", "metals_mining", 8),
    ("BTG", "B2Gold Corp.", "metals_mining", 4), ("HMY", "Harmony Gold Mining", "metals_mining", 6),
    ("PAAS", "Pan American Silver", "metals_mining", 8), ("HL", "Hecla Mining", "metals_mining", 4),
    ("CDE", "Coeur Mining", "metals_mining", 3), ("MP", "MP Materials", "metals_mining", 4),
    ("SCCO", "Southern Copper", "metals_mining", 90), ("X", "United States Steel", "metals_mining", 8),
    ("CLF", "Cleveland-Cliffs", "metals_mining", 6), ("STLD", "Steel Dynamics", "metals_mining", 22),
    ("RS", "Reliance Inc.", "metals_mining", 16), ("AA", "Alcoa Corp.", "metals_mining", 8),
    # Utilities
    ("DUK", "Duke Energy", "utilities", 90), ("SO", "Southern Co.", "utilities", 95),
    ("D", "Dominion Energy", "utilities", 48), ("AEP", "American Electric Power", "utilities", 50),
    ("EXC", "Exelon Corp.", "utilities", 38), ("XEL", "Xcel Energy", "utilities", 35),
    ("SRE", "Sempra", "utilities", 55), ("PEG", "Public Service Enterprise", "utilities", 42),
    ("ED", "Consolidated Edison", "utilities", 35), ("WEC", "WEC Energy Group", "utilities", 32),
    ("ES", "Eversource Energy", "utilities", 22), ("EIX", "Edison International", "utilities", 30),
    ("PCG", "PG&E Corp.", "utilities", 45), ("FE", "FirstEnergy Corp.", "utilities", 24),
    ("AEE", "Ameren Corp.", "utilities", 22), ("CMS", "CMS Energy", "utilities", 20),
    ("DTE", "DTE Energy", "utilities", 25), ("PPL", "PPL Corp.", "utilities", 25),
    ("CNP", "CenterPoint Energy", "utilities", 22), ("ATO", "Atmos Energy", "utilities", 22),
    ("NI", "NiSource Inc.", "utilities", 18), ("LNT", "Alliant Energy", "utilities", 16),
    ("EVRG", "Evergy Inc.", "utilities", 14), ("AES", "AES Corp.", "utilities", 9),
    ("NRG", "NRG Energy", "utilities", 18), ("VST", "Vistra Corp.", "utilities", 50),
    ("AWK", "American Water Works", "utilities", 28),
    # Real estate & REITs
    ("PLD", "Prologis Inc.", "real_estate", 110), ("EQIX", "Equinix Inc.", "real_estate", 90),
    ("PSA", "Public Storage", "real_estate", 60), ("O", "Realty Income", "real_estate", 50),
    ("WELL", "Welltower Inc.", "real_estate", 80), ("SPG", "Simon Property Group", "real_estate", 60),
    ("DLR", "Digital Realty Trust", "real_estate", 55), ("VICI", "VICI Properties", "real_estate", 32),
    ("CBRE", "CBRE Group", "real_estate", 45), ("AVB", "AvalonBay Communities", "real_estate", 30),
    ("EQR", "Equity Residential", "real_estate", 30), ("EXR", "Extra Space Storage", "real_estate", 35),
    ("INVH", "Invitation Homes", "real_estate", 22), ("MAA", "Mid-America Apartment", "real_estate", 18),
    ("ESS", "Essex Property Trust", "real_estate", 20), ("ARE", "Alexandria Real Estate", "real_estate", 20),
    ("VTR", "Ventas Inc.", "real_estate", 28), ("WY", "Weyerhaeuser Co.", "real_estate", 22),
    ("IRM", "Iron Mountain", "real_estate", 30), ("KIM", "Kimco Realty", "real_estate", 16),
    ("REG", "Regency Centers", "real_estate", 14), ("BXP", "BXP Inc.", "real_estate", 12),
    ("HST", "Host Hotels & Resorts", "real_estate", 12), ("UDR", "UDR Inc.", "real_estate", 14),
    ("CPT", "Camden Property Trust", "real_estate", 14), ("DOC", "Healthpeak Properties", "real_estate", 14),
    ("SUI", "Sun Communities", "real_estate", 16), ("ELS", "Equity LifeStyle Properties", "real_estate", 14),
    ("GLPI", "Gaming and Leisure Properties", "real_estate", 14), ("WPC", "W. P. Carey", "real_estate", 14),
    # Defense & aerospace
    ("HII", "Huntington Ingalls Industries", "defense", 9), ("LDOS", "Leidos Holdings", "defense", 22),
    ("AXON", "Axon Enterprise", "defense", 50), ("KTOS", "Kratos Defense & Security", "defense", 8),
    ("AVAV", "AeroVironment Inc.", "defense", 5), ("HWM", "Howmet Aerospace", "defense", 50),
    ("TDG", "TransDigm Group", "defense", 75), ("TXT", "Textron Inc.", "defense", 16),
    ("CW", "Curtiss-Wright", "defense", 14), ("BWXT", "BWX Technologies", "defense", 10),
    ("HEI", "HEICO Corp.", "defense", 40),
    # EV & auto
    ("STLA", "Stellantis N.V.", "ev_auto", 40), ("TM", "Toyota Motor Corp.", "ev_auto", 250),
    ("HMC", "Honda Motor Co.", "ev_auto", 50), ("RACE", "Ferrari N.V.", "ev_auto", 80),
    ("XPEV", "XPeng Inc.", "ev_auto", 12), ("PSNY", "Polestar Automotive", "ev_auto", 2),
    ("QS", "QuantumScape Corp.", "ev_auto", 4), ("CHPT", "ChargePoint Holdings", "ev_auto", 1),
    ("BLNK", "Blink Charging", "ev_auto", 1),
    # Robotics & automation
    ("FANUY", "Fanuc Corp.", "robotics", 18), ("OMRNY", "Omron Corp.", "robotics", 8),
    # Crypto & blockchain
    ("MSTR", "MicroStrategy Inc.", "crypto", 90), ("MARA", "MARA Holdings", "crypto", 6),
    ("RIOT", "Riot Platforms", "crypto", 4), ("CLSK", "CleanSpark Inc.", "crypto", 4),
    ("HUT", "Hut 8 Corp.", "crypto", 3), ("BITF", "Bitfarms Ltd.", "crypto", 1),
    ("BTBT", "Bit Digital", "crypto", 2), ("CIFR", "Cipher Mining", "crypto", 2),
    ("WULF", "TeraWulf Inc.", "crypto", 3), ("CORZ", "Core Scientific", "crypto", 5),
    ("IREN", "IREN Ltd.", "crypto", 4),
    # Space
    ("RKLB", "Rocket Lab USA", "space", 12), ("ASTS", "AST SpaceMobile", "space", 8),
    ("LUNR", "Intuitive Machines", "space", 2), ("RDW", "Redwire Corp.", "space", 2),
    ("PL", "Planet Labs PBC", "space", 2), ("BKSY", "BlackSky Technology", "space", 1),
    # Quantum computing
    ("IONQ", "IonQ Inc.", "quantum", 8), ("RGTI", "Rigetti Computing", "quantum", 3),
    ("QBTS", "D-Wave Quantum", "quantum", 2), ("QUBT", "Quantum Computing Inc.", "quantum", 1),
    ("ARQQ", "Arqit Quantum", "quantum", 1),
    # Clean & renewable energy
    ("BEP", "Brookfield Renewable Partners", "clean_energy", 16), ("BEPC", "Brookfield Renewable Corp.", "clean_energy", 12),
    ("NOVA", "Sunnova Energy", "clean_energy", 1), ("ARRY", "Array Technologies", "clean_energy", 1),
    ("SHLS", "Shoals Technologies", "clean_energy", 1), ("FLNC", "Fluence Energy", "clean_energy", 4),
    ("CSIQ", "Canadian Solar", "clean_energy", 1), ("JKS", "JinkoSolar Holding", "clean_energy", 1),
    ("NXT", "Nextracker Inc.", "clean_energy", 6),
    # Energy (oil & gas)
    ("PSX", "Phillips 66", "energy", 55), ("MPC", "Marathon Petroleum", "energy", 60),
    ("VLO", "Valero Energy", "energy", 45), ("EOG", "EOG Resources", "energy", 70),
    ("DVN", "Devon Energy", "energy", 28), ("FANG", "Diamondback Energy", "energy", 50),
    ("HES", "Hess Corp.", "energy", 45), ("HAL", "Halliburton Co.", "energy", 28),
    ("BKR", "Baker Hughes Co.", "energy", 38), ("WMB", "Williams Companies", "energy", 65),
    ("KMI", "Kinder Morgan", "energy", 55), ("OKE", "ONEOK Inc.", "energy", 55),
    ("LNG", "Cheniere Energy", "energy", 50), ("TRGP", "Targa Resources", "energy", 35),
    ("EQT", "EQT Corp.", "energy", 22), ("AR", "Antero Resources", "energy", 9),
    ("APA", "APA Corp.", "energy", 8), ("CTRA", "Coterra Energy", "energy", 20),
    ("OVV", "Ovintiv Inc.", "energy", 12), ("PR", "Permian Resources", "energy", 14),
    ("RRC", "Range Resources", "energy", 9), ("CHRD", "Chord Energy", "energy", 8),
]

# --- Singapore Exchange (SGX). Catalogued under base code; .SI added on demand.
_SGX: List[tuple] = [
    ("D05", "DBS Group Holdings", "financials", 70), ("O39", "Oversea-Chinese Banking (OCBC)", "financials", 48),
    ("U11", "United Overseas Bank (UOB)", "financials", 38), ("Z74", "Singtel", "telecom", 38),
    ("S68", "Singapore Exchange (SGX)", "financials", 9), ("J36", "Jardine Matheson Holdings", "financials", 12),
    ("C6L", "Singapore Airlines", "transportation", 14), ("C52", "ComfortDelGro Corp.", "transportation", 4),
    ("S58", "SATS Ltd.", "transportation", 3), ("S59", "SIA Engineering", "transportation", 2),
    ("S08", "Singapore Post (SingPost)", "industrials", 2), ("BN4", "Keppel Ltd.", "industrials", 9),
    ("BS6", "Yangzijiang Shipbuilding", "industrials", 7), ("5E2", "Seatrium Ltd.", "industrials", 5),
    ("V03", "Venture Corp.", "ai_tech", 4), ("AWX", "AEM Holdings", "semiconductors", 1),
    ("S63", "ST Engineering", "defense", 12), ("U96", "Sembcorp Industries", "utilities", 8),
    ("F34", "Wilmar International", "staples", 15), ("Y92", "Thai Beverage", "staples", 9),
    ("D01", "DFI Retail Group", "staples", 3), ("OV8", "Sheng Siong Group", "staples", 2),
    ("E5H", "Golden Agri-Resources", "staples", 2), ("C07", "Jardine Cycle & Carriage", "consumer", 8),
    ("G13", "Genting Singapore", "consumer", 6), ("BSL", "Raffles Medical Group", "healthcare", 2),
    ("H02", "Haw Par Corp.", "healthcare", 2), ("9CI", "CapitaLand Investment", "real_estate", 10),
    ("C38U", "CapitaLand Integrated Commercial Trust", "real_estate", 12),
    ("A17U", "CapitaLand Ascendas REIT", "real_estate", 8), ("ME8U", "Mapletree Industrial Trust", "real_estate", 5),
    ("M44U", "Mapletree Logistics Trust", "real_estate", 5), ("N2IU", "Mapletree Pan Asia Commercial Trust", "real_estate", 5),
    ("BUOU", "Frasers Logistics & Commercial Trust", "real_estate", 4), ("AJBU", "Keppel DC REIT", "real_estate", 3),
    ("T82U", "Suntec REIT", "real_estate", 3), ("K71U", "Keppel REIT", "real_estate", 3),
    ("J69U", "Frasers Centrepoint Trust", "real_estate", 3), ("C2PU", "Parkway Life REIT", "real_estate", 2),
    ("C09", "City Developments", "real_estate", 4), ("H78", "Hongkong Land Holdings", "real_estate", 7),
    ("U14", "UOL Group", "real_estate", 4), ("TQ5", "Frasers Property", "real_estate", 3),
]

_load(_US)
_load(_SGX, country="Singapore", exchange="SGX")


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

# Live-source mapping for macro assets. Only symbols with a reliable, free,
# key-less Yahoo quote are listed here; everything else (US2Y/2Y10Y spread/TIPS
# breakeven/iron ore — no clean free intraday source) stays on the curated mock
# values above and is reported as such via the freshness badge. The values map
# the internal macro code to the symbol Yahoo's chart endpoint expects.
MACRO_YAHOO: Dict[str, str] = {
    "US10Y":  "^TNX",        # CBOE 10Y Treasury yield (quoted as a % level)
    "DXY":    "DX-Y.NYB",    # US Dollar Index
    "EURUSD": "EURUSD=X",
    "USDJPY": "JPY=X",
    "USDCNH": "CNH=X",
    "WTI":    "CL=F",        # WTI crude front-month future
    "GOLD":   "GC=F",        # Gold front-month future
    "COPPER": "HG=F",        # Copper front-month future
    "SPX":    "^GSPC",
    "NDX":    "^NDX",
    "EEM":    "EEM",
    "HSCEI":  "^HSCE",
    "CSI300": "000300.SS",
    "VIX":    "^VIX",
}


def macro_yahoo_symbol(symbol: str) -> Optional[str]:
    """Yahoo chart symbol for a macro asset, or None if it has no live source."""
    return MACRO_YAHOO.get((symbol or "").upper())


def macro_symbols() -> List[str]:
    """All macro asset codes with a live Yahoo source (for the ingest worker)."""
    return list(MACRO_YAHOO.keys())


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


# Human-friendly aliases → MACRO_ASSETS keys, used when a user asks to add/remove
# an asset from a macro dashboard by name (e.g. "iron ore", "EUR/USD", "the dollar").
MACRO_SYMBOL_ALIASES: Dict[str, str] = {
    "eur/usd": "EURUSD", "eurusd": "EURUSD", "euro": "EURUSD", "the euro": "EURUSD",
    "usd/jpy": "USDJPY", "usdjpy": "USDJPY", "the yen": "USDJPY", "yen": "USDJPY",
    "usd/cnh": "USDCNH", "usdcnh": "USDCNH", "cnh": "USDCNH", "yuan": "USDCNH", "renminbi": "USDCNH",
    "dxy": "DXY", "dollar index": "DXY", "us dollar index": "DXY", "the dollar": "DXY", "dollar": "DXY",
    "wti": "WTI", "crude oil": "WTI", "crude": "WTI", "oil": "WTI",
    "gold": "GOLD",
    "copper": "COPPER",
    "iron ore": "IRON", "iron": "IRON",
    "s&p 500": "SPX", "s&p500": "SPX", "s&p": "SPX", "sp500": "SPX", "spx": "SPX", "s and p": "SPX",
    "nasdaq 100": "NDX", "nasdaq": "NDX", "ndx": "NDX",
    "em equities": "EEM", "emerging markets": "EEM", "eem": "EEM",
    "csi 300": "CSI300", "csi300": "CSI300",
    "hang seng china enterprises": "HSCEI", "hscei": "HSCEI",
    "vix": "VIX", "volatility index": "VIX",
    "10y breakeven": "TIPS10Y", "breakevens": "TIPS10Y", "breakeven": "TIPS10Y", "tips": "TIPS10Y",
    "2y-10y spread": "US2Y10Y", "2y-10y": "US2Y10Y", "2y10y": "US2Y10Y", "2s10s": "US2Y10Y",
    "us 10y": "US10Y", "10-year": "US10Y", "10 year": "US10Y", "10y": "US10Y", "us10y": "US10Y",
    "us 2y": "US2Y", "2-year": "US2Y", "2 year": "US2Y", "2y": "US2Y", "us2y": "US2Y",
}

# MACRO_ASSETS["group"] (lowercase) → display label used by MACRO_THEMES groups.
MACRO_GROUP_LABELS: Dict[str, str] = {
    "rates": "Rates",
    "fx": "FX",
    "commodities": "Commodities",
    "equities": "Equities",
}


def resolve_macro_symbols(text: str) -> List[str]:
    """Extract macro asset symbols referenced in free text (by code or alias).

    Returns canonical MACRO_ASSETS keys, in order of appearance. Longer aliases are
    matched first and consumed so e.g. "2y-10y" does not also match "2y".
    """
    if not text:
        return []
    found: List[str] = []
    remaining = " " + text.lower() + " "
    for alias in sorted(MACRO_SYMBOL_ALIASES, key=len, reverse=True):
        pat = r"\b" + re.escape(alias) + r"\b"
        if re.search(pat, remaining):
            sym = MACRO_SYMBOL_ALIASES[alias]
            if sym not in found:
                found.append(sym)
            remaining = re.sub(pat, " ", remaining)
    up = " " + text.upper() + " "
    for sym in MACRO_ASSETS:
        if sym not in found and re.search(r"\b" + re.escape(sym) + r"\b", up):
            found.append(sym)
    return found


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


# ---------------------------------------------------------------------------
# Company Analytics: peer mappings, KPI correlations, catalysts
# ---------------------------------------------------------------------------

# symbol → list of 2–3 closest competitors
PEER_MAPPINGS: Dict[str, List[str]] = {
    "NVDA": ["AMD", "TSM", "INTC"],
    "AMD":  ["NVDA", "INTC", "TSM"],
    "INTC": ["AMD", "TSM", "AVGO"],
    "TSM":  ["NVDA", "AMD", "ASML"],
    "AVGO": ["QCOM", "TSM", "INTC"],
    "ASML": ["MU", "TSM", "INTC"],
    "MU":   ["NVDA", "AVGO", "TSM"],
    "QCOM": ["AMD", "AVGO", "INTC"],
    "XOM":  ["CVX", "COP", "OXY"],
    "CVX":  ["XOM", "COP", "SLB"],
    "COP":  ["XOM", "CVX", "OXY"],
    "SLB":  ["COP", "XOM", "CVX"],
    "NEE":  ["ENPH", "FSLR", "XOM"],
    "ENPH": ["FSLR", "NEE", "QCOM"],
    "FSLR": ["ENPH", "NEE", "COP"],
    "OXY":  ["XOM", "CVX", "COP"],
    "MSFT": ["GOOGL", "AMZN", "META"],
    "GOOGL":["MSFT", "META", "AMZN"],
    "META": ["GOOGL", "MSFT", "AMZN"],
    "AMZN": ["MSFT", "GOOGL", "META"],
    "PLTR": ["CRM", "NOW", "SNOW"],
    "SNOW": ["PLTR", "CRM", "NOW"],
    "CRM":  ["NOW", "MSFT", "SNOW"],
    "NOW":  ["CRM", "MSFT", "META"],
}

# Annual revenue growth % per ticker. FALLBACK-ONLY default: the live value is
# computed from the yfinance fundamentals snapshot (`revenueGrowth`) and stored
# on the fundamentals table; these curated figures are used only when no live
# data is available.
REVENUE_GROWTH: Dict[str, float] = {
    "NVDA": 122.4, "AMD": 18.1, "INTC": -8.7, "TSM": 28.4,
    "AVGO": 43.2,  "ASML": 9.5,  "MU":   61.3, "QCOM": 7.4,
    "XOM":  -6.2,  "CVX": -8.9,  "COP":  -4.1, "SLB":  12.7,
    "NEE":  9.3,   "ENPH": -52.1, "FSLR": 24.8, "OXY":  -9.4,
    "MSFT": 15.7,  "GOOGL": 13.8, "META": 22.1, "AMZN": 10.5,
    "PLTR": 27.0,  "SNOW": 32.9,  "CRM":  9.8,  "NOW":  22.3,
}

# KPI correlations: which fundamental metrics most closely track this stock's
# price. FALLBACK-ONLY default: when live OHLCV history exists the builder
# computes real rolling return correlations vs peers; these curated values are
# used only when live price series are unavailable.
KPI_CORRELATIONS: Dict[str, List[dict]] = {
    "NVDA": [
        {"metric": "Data Center Revenue YoY", "correlation": 0.94, "direction": "positive"},
        {"metric": "GPU Shipment Volume", "correlation": 0.89, "direction": "positive"},
        {"metric": "Net Margin Expansion", "correlation": 0.81, "direction": "positive"},
        {"metric": "EPS Beat vs Consensus", "correlation": 0.76, "direction": "positive"},
        {"metric": "10Y Treasury Yield", "correlation": -0.58, "direction": "negative"},
    ],
    "AMD": [
        {"metric": "Data Center Revenue YoY", "correlation": 0.86, "direction": "positive"},
        {"metric": "PC Shipment Volume", "correlation": 0.71, "direction": "positive"},
        {"metric": "EPS Estimate Revisions", "correlation": 0.68, "direction": "positive"},
        {"metric": "NVDA Relative Performance", "correlation": 0.65, "direction": "positive"},
        {"metric": "USD Index (DXY)", "correlation": -0.41, "direction": "negative"},
    ],
    "INTC": [
        {"metric": "PC Shipment Volume", "correlation": 0.72, "direction": "positive"},
        {"metric": "Foundry Revenue Growth", "correlation": 0.68, "direction": "positive"},
        {"metric": "Gross Margin Trend", "correlation": 0.65, "direction": "positive"},
        {"metric": "EPS vs Consensus", "correlation": 0.60, "direction": "positive"},
        {"metric": "Competitive Win Rate", "correlation": 0.55, "direction": "positive"},
    ],
    "TSM": [
        {"metric": "Advanced Node Utilization", "correlation": 0.91, "direction": "positive"},
        {"metric": "AI Chip Orders", "correlation": 0.87, "direction": "positive"},
        {"metric": "Capex Guidance", "correlation": 0.73, "direction": "positive"},
        {"metric": "USD/TWD Rate", "correlation": -0.49, "direction": "negative"},
        {"metric": "China Export Policy Risk", "correlation": -0.55, "direction": "negative"},
    ],
    "AVGO": [
        {"metric": "Networking Revenue YoY", "correlation": 0.83, "direction": "positive"},
        {"metric": "Custom ASIC Design Wins", "correlation": 0.78, "direction": "positive"},
        {"metric": "Software Revenue Mix", "correlation": 0.69, "direction": "positive"},
        {"metric": "Dividend Growth Rate", "correlation": 0.52, "direction": "positive"},
        {"metric": "Cloud Capex Cycle", "correlation": 0.74, "direction": "positive"},
    ],
    "ASML": [
        {"metric": "EUV Order Backlog", "correlation": 0.92, "direction": "positive"},
        {"metric": "China Revenue Exposure", "correlation": -0.61, "direction": "negative"},
        {"metric": "Leading-Edge Node Ramp", "correlation": 0.84, "direction": "positive"},
        {"metric": "Book-to-Bill Ratio", "correlation": 0.79, "direction": "positive"},
        {"metric": "EUR/USD Rate", "correlation": 0.44, "direction": "positive"},
    ],
    "MU": [
        {"metric": "DRAM ASP Trend", "correlation": 0.88, "direction": "positive"},
        {"metric": "HBM Capacity Sold", "correlation": 0.85, "direction": "positive"},
        {"metric": "AI Server Build Rate", "correlation": 0.80, "direction": "positive"},
        {"metric": "Inventory Overhang", "correlation": -0.72, "direction": "negative"},
        {"metric": "PC/Server Demand", "correlation": 0.64, "direction": "positive"},
    ],
    "QCOM": [
        {"metric": "Smartphone Unit Shipments", "correlation": 0.79, "direction": "positive"},
        {"metric": "Automotive Design Wins", "correlation": 0.71, "direction": "positive"},
        {"metric": "Licensing Revenue Stability", "correlation": 0.64, "direction": "positive"},
        {"metric": "China Handset Market Share", "correlation": 0.58, "direction": "positive"},
        {"metric": "Edge AI Adoption Rate", "correlation": 0.55, "direction": "positive"},
    ],
    "XOM": [
        {"metric": "Brent Crude Price", "correlation": 0.87, "direction": "positive"},
        {"metric": "Permian Basin Output", "correlation": 0.74, "direction": "positive"},
        {"metric": "Refining Crack Spread", "correlation": 0.62, "direction": "positive"},
        {"metric": "Buyback Yield", "correlation": 0.55, "direction": "positive"},
        {"metric": "US Dollar Index", "correlation": -0.48, "direction": "negative"},
    ],
    "CVX": [
        {"metric": "Brent Crude Price", "correlation": 0.84, "direction": "positive"},
        {"metric": "Permian Production Growth", "correlation": 0.70, "direction": "positive"},
        {"metric": "LNG Export Volume", "correlation": 0.61, "direction": "positive"},
        {"metric": "Capital Return Yield", "correlation": 0.57, "direction": "positive"},
        {"metric": "Natural Gas Price (HH)", "correlation": 0.48, "direction": "positive"},
    ],
    "COP": [
        {"metric": "WTI Crude Price", "correlation": 0.83, "direction": "positive"},
        {"metric": "Production Growth (BOE/D)", "correlation": 0.72, "direction": "positive"},
        {"metric": "Cost of Supply (breakeven)", "correlation": -0.65, "direction": "negative"},
        {"metric": "Variable Dividend Coverage", "correlation": 0.60, "direction": "positive"},
        {"metric": "Global E&P Capex Cycle", "correlation": 0.55, "direction": "positive"},
    ],
    "SLB": [
        {"metric": "Global Upstream Capex Spend", "correlation": 0.88, "direction": "positive"},
        {"metric": "International Rig Count", "correlation": 0.80, "direction": "positive"},
        {"metric": "Digital Revenue Growth", "correlation": 0.65, "direction": "positive"},
        {"metric": "WTI Price", "correlation": 0.72, "direction": "positive"},
        {"metric": "NOC Investment Cycle", "correlation": 0.60, "direction": "positive"},
    ],
    "NEE": [
        {"metric": "Utility Rate Base Growth", "correlation": 0.85, "direction": "positive"},
        {"metric": "Renewables Backlog", "correlation": 0.80, "direction": "positive"},
        {"metric": "10Y Treasury Yield", "correlation": -0.78, "direction": "negative"},
        {"metric": "IRA Tax Credit Value", "correlation": 0.70, "direction": "positive"},
        {"metric": "Power Demand Growth", "correlation": 0.60, "direction": "positive"},
    ],
    "ENPH": [
        {"metric": "Residential Solar Installations", "correlation": 0.89, "direction": "positive"},
        {"metric": "Channel Inventory Level", "correlation": -0.82, "direction": "negative"},
        {"metric": "European Demand Trend", "correlation": 0.72, "direction": "positive"},
        {"metric": "Battery Storage Attach Rate", "correlation": 0.65, "direction": "positive"},
        {"metric": "ITC Solar Tax Credit", "correlation": 0.58, "direction": "positive"},
    ],
    "FSLR": [
        {"metric": "US Utility Solar Bookings", "correlation": 0.91, "direction": "positive"},
        {"metric": "IRA Domestic Content Credit", "correlation": 0.84, "direction": "positive"},
        {"metric": "Module ASP Trend", "correlation": 0.73, "direction": "positive"},
        {"metric": "Backlog Conversion Rate", "correlation": 0.69, "direction": "positive"},
        {"metric": "Chinese Module Import Price", "correlation": -0.60, "direction": "negative"},
    ],
    "OXY": [
        {"metric": "WTI Crude Price", "correlation": 0.86, "direction": "positive"},
        {"metric": "Permian Basin Volumes", "correlation": 0.73, "direction": "positive"},
        {"metric": "Berkshire Accumulation", "correlation": 0.62, "direction": "positive"},
        {"metric": "Carbon Capture Progress", "correlation": 0.45, "direction": "positive"},
        {"metric": "Debt Paydown Pace", "correlation": 0.58, "direction": "positive"},
    ],
    "MSFT": [
        {"metric": "Azure Revenue Growth", "correlation": 0.93, "direction": "positive"},
        {"metric": "Copilot Seat Adoption", "correlation": 0.85, "direction": "positive"},
        {"metric": "Cloud AI Consumption", "correlation": 0.82, "direction": "positive"},
        {"metric": "Operating Margin Trend", "correlation": 0.74, "direction": "positive"},
        {"metric": "10Y Treasury Yield", "correlation": -0.52, "direction": "negative"},
    ],
    "GOOGL": [
        {"metric": "Search Revenue Growth", "correlation": 0.88, "direction": "positive"},
        {"metric": "YouTube Ad Revenue", "correlation": 0.80, "direction": "positive"},
        {"metric": "Google Cloud Growth", "correlation": 0.76, "direction": "positive"},
        {"metric": "Digital Ad Spend Index", "correlation": 0.83, "direction": "positive"},
        {"metric": "Gemini Model Adoption", "correlation": 0.65, "direction": "positive"},
    ],
    "META": [
        {"metric": "Daily Active Users (DAU)", "correlation": 0.85, "direction": "positive"},
        {"metric": "Ad Revenue per User (ARPU)", "correlation": 0.88, "direction": "positive"},
        {"metric": "AI Ad Ranking Efficiency", "correlation": 0.77, "direction": "positive"},
        {"metric": "Reels Monetization Rate", "correlation": 0.70, "direction": "positive"},
        {"metric": "Digital Ad Market Share", "correlation": 0.80, "direction": "positive"},
    ],
    "AMZN": [
        {"metric": "AWS Revenue Growth", "correlation": 0.91, "direction": "positive"},
        {"metric": "AWS Operating Margin", "correlation": 0.87, "direction": "positive"},
        {"metric": "eCommerce GMV Growth", "correlation": 0.68, "direction": "positive"},
        {"metric": "Prime Subscriber Count", "correlation": 0.62, "direction": "positive"},
        {"metric": "Advertising Revenue Growth", "correlation": 0.75, "direction": "positive"},
    ],
    "PLTR": [
        {"metric": "US Commercial Revenue Growth", "correlation": 0.93, "direction": "positive"},
        {"metric": "AIP Bootcamp Conversions", "correlation": 0.88, "direction": "positive"},
        {"metric": "Customer Count Growth", "correlation": 0.80, "direction": "positive"},
        {"metric": "Government Contract Value", "correlation": 0.65, "direction": "positive"},
        {"metric": "Rule of 40 Score", "correlation": 0.72, "direction": "positive"},
    ],
    "SNOW": [
        {"metric": "Net Revenue Retention (NRR)", "correlation": 0.90, "direction": "positive"},
        {"metric": "Product Revenue Growth", "correlation": 0.87, "direction": "positive"},
        {"metric": "Remaining Performance Obligation", "correlation": 0.78, "direction": "positive"},
        {"metric": "AI Workload Consumption", "correlation": 0.70, "direction": "positive"},
        {"metric": "Customer $1M+ Count", "correlation": 0.65, "direction": "positive"},
    ],
    "CRM": [
        {"metric": "Subscription Revenue Growth", "correlation": 0.85, "direction": "positive"},
        {"metric": "Remaining Performance Obligation", "correlation": 0.80, "direction": "positive"},
        {"metric": "Agentforce/Einstein Adoption", "correlation": 0.72, "direction": "positive"},
        {"metric": "Attrition / NRR Trend", "correlation": 0.68, "direction": "positive"},
        {"metric": "Enterprise Deal Velocity", "correlation": 0.63, "direction": "positive"},
    ],
    "NOW": [
        {"metric": "Subscription Revenue Growth", "correlation": 0.92, "direction": "positive"},
        {"metric": "Now Assist AI Seats", "correlation": 0.83, "direction": "positive"},
        {"metric": "Remaining Performance Obligation", "correlation": 0.80, "direction": "positive"},
        {"metric": "Operating Margin Expansion", "correlation": 0.74, "direction": "positive"},
        {"metric": "Net New ACV Growth", "correlation": 0.77, "direction": "positive"},
    ],
}

# Upcoming catalysts per ticker. FALLBACK-ONLY default: the builder sources real
# earnings/dividend dates from the live yfinance calendar feed (stored on the
# fundamentals table) and merges them ahead of these curated editorial events;
# this whole set is used as-is only when no live calendar data is available.
_TODAY = date.today()


def _dt(days: int) -> str:
    return (_TODAY + timedelta(days=days)).isoformat()


CATALYSTS: Dict[str, List[dict]] = {
    "NVDA": [
        {"event": "Q2 FY2026 Earnings", "date": _dt(18), "impact": "High",
         "description": "Street expects triple-digit data center revenue growth; beat magnitude will set near-term tone."},
        {"event": "GTC Developer Conference", "date": _dt(42), "impact": "High",
         "description": "Next-gen Blackwell roadmap details and software ecosystem announcements expected."},
        {"event": "US Export Control Review", "date": _dt(30), "impact": "High",
         "description": "BIS rule update could expand or tighten H20 chip restrictions to China."},
        {"event": "Hyperscaler Capex Reports", "date": _dt(10), "impact": "Medium",
         "description": "Cloud provider Q earnings will reveal GPU demand commitments for H2."},
    ],
    "AMD": [
        {"event": "Q2 2025 Earnings", "date": _dt(22), "impact": "High",
         "description": "MI300X ramp and data center GPU revenue trajectory will be key."},
        {"event": "Next Data Center GPU Launch", "date": _dt(55), "impact": "High",
         "description": "MI350 product launch expected to close gap with NVDA on inference workloads."},
        {"event": "PC Market Recovery Data", "date": _dt(14), "impact": "Medium",
         "description": "Gartner/IDC shipment data for Q2 will gauge client CPU recovery pace."},
    ],
    "INTC": [
        {"event": "Q2 2025 Earnings", "date": _dt(20), "impact": "High",
         "description": "Foundry progress and client/server revenue guidance will be central."},
        {"event": "18A Process Node Milestone", "date": _dt(60), "impact": "High",
         "description": "First commercial 18A wafer yields will determine credibility of the foundry turnaround."},
        {"event": "CHIPS Act Disbursement", "date": _dt(45), "impact": "Medium",
         "description": "Federal grant tranches tied to construction milestones could provide balance-sheet relief."},
    ],
    "TSM": [
        {"event": "July Revenue Monthly Report", "date": _dt(8), "impact": "High",
         "description": "Monthly sales figure provides earliest read on advanced node demand."},
        {"event": "Q2 2025 Earnings", "date": _dt(25), "impact": "High",
         "description": "Capex guidance update and N3/N2 utilization outlook will drive sentiment."},
        {"event": "Arizona Fab Ramp", "date": _dt(90), "impact": "Medium",
         "description": "N4P volume production start in Phoenix; geopolitical diversification read-through."},
    ],
    "AVGO": [
        {"event": "Q3 FY2025 Earnings", "date": _dt(28), "impact": "High",
         "description": "Custom ASIC design wins and networking revenue trajectory key to re-rating."},
        {"event": "AI Networking Product Event", "date": _dt(50), "impact": "Medium",
         "description": "Tomahawk/Jericho next-gen silicon launch for hyperscaler switch fabrics."},
    ],
    "ASML": [
        {"event": "Q2 2025 Earnings", "date": _dt(16), "impact": "High",
         "description": "Order intake and China revenue disclosure will be closely watched post-export curbs."},
        {"event": "High-NA EUV Volume Ramp", "date": _dt(75), "impact": "High",
         "description": "Intel and TSMC first High-NA EUV installations; pivotal for 2nm+ roadmaps."},
        {"event": "China Export Restriction Update", "date": _dt(35), "impact": "High",
         "description": "EU/US coordination on semiconductor equipment export policy."},
    ],
    "MU": [
        {"event": "Q3 FY2025 Earnings", "date": _dt(12), "impact": "High",
         "description": "HBM3E pricing and DRAM ASP trajectory will define earnings power for the cycle."},
        {"event": "HBM4 Product Launch", "date": _dt(65), "impact": "Medium",
         "description": "Qualification timeline with NVDA for GB300 platform a key data point."},
    ],
    "QCOM": [
        {"event": "Q3 FY2025 Earnings", "date": _dt(20), "impact": "High",
         "description": "Snapdragon X licensing and automotive design-win revenue will be scrutinized."},
        {"event": "Samsung Galaxy AI Cycle", "date": _dt(40), "impact": "Medium",
         "description": "On-device AI feature set for flagship Android launch could accelerate upgrade cycle."},
    ],
    "XOM": [
        {"event": "Q2 2025 Earnings", "date": _dt(15), "impact": "High",
         "description": "Permian output volumes and buyback cadence will be key; OPEC+ backdrop matters."},
        {"event": "OPEC+ Production Meeting", "date": _dt(22), "impact": "High",
         "description": "Quota decisions directly affect crude pricing and integrated-major earnings."},
        {"event": "Pioneer Integration Synergy Update", "date": _dt(50), "impact": "Medium",
         "description": "Cost synergy realization from the $60B Pioneer deal will boost FCF outlook."},
    ],
    "CVX": [
        {"event": "Q2 2025 Earnings", "date": _dt(17), "impact": "High",
         "description": "Hess acquisition synergies and Permian growth trajectory will set guidance tone."},
        {"event": "Hess Integration Milestone", "date": _dt(45), "impact": "Medium",
         "description": "Guyana block production ramp with ExxonMobil ROFR resolution pending."},
    ],
    "COP": [
        {"event": "Q2 2025 Earnings", "date": _dt(19), "impact": "High",
         "description": "Production guidance and variable dividend announcement are the primary catalysts."},
        {"event": "Marathon Oil Integration", "date": _dt(40), "impact": "Medium",
         "description": "Cost synergy timeline and asset disposition plan from the $22B merger."},
    ],
    "SLB": [
        {"event": "Q2 2025 Earnings", "date": _dt(14), "impact": "High",
         "description": "International services margin and digital revenue growth are key."},
        {"event": "Core AI Platform Launch", "date": _dt(35), "impact": "Medium",
         "description": "SLB's industrial AI platform for upstream operators — potential re-rating catalyst."},
    ],
    "NEE": [
        {"event": "Q2 2025 Earnings", "date": _dt(21), "impact": "High",
         "description": "Renewables backlog update and rate-base growth guidance are primary levers."},
        {"event": "Federal Rate Decision (FOMC)", "date": _dt(30), "impact": "High",
         "description": "Rate-sensitive utility; rate cut expectations drive discount rate re-pricing."},
        {"event": "FPL Rate Case Decision", "date": _dt(60), "impact": "Medium",
         "description": "Florida Public Service Commission ruling on Florida Power & Light rate increase."},
    ],
    "ENPH": [
        {"event": "Q2 2025 Earnings", "date": _dt(18), "impact": "High",
         "description": "Europe channel inventory sell-through and US attach rates are key watch items."},
        {"event": "IQ9 Microinverter Launch", "date": _dt(45), "impact": "Medium",
         "description": "Next-gen platform for higher-wattage panels; pricing premium supports margins."},
    ],
    "FSLR": [
        {"event": "Q2 2025 Earnings", "date": _dt(16), "impact": "High",
         "description": "Backlog conversion and Series 7 module ramp will set H2 revenue visibility."},
        {"event": "IRA Domestic Content Rule", "date": _dt(40), "impact": "High",
         "description": "Treasury guidance on domestic content adder directly impacts First Solar's advantage."},
    ],
    "OXY": [
        {"event": "Q2 2025 Earnings", "date": _dt(20), "impact": "High",
         "description": "Free cash flow generation and debt paydown progress will be the key metrics."},
        {"event": "DAC Plant Scale Decision", "date": _dt(60), "impact": "Medium",
         "description": "Stratos direct air capture facility commercial progress and credit offtake updates."},
    ],
    "MSFT": [
        {"event": "Q4 FY2025 Earnings", "date": _dt(24), "impact": "High",
         "description": "Azure growth rate and Copilot seat monetization are the primary revenue drivers."},
        {"event": "Microsoft Build Conference", "date": _dt(35), "impact": "Medium",
         "description": "Developer ecosystem updates for Azure OpenAI and Copilot SDK."},
        {"event": "EU Regulatory Review (Teams)", "date": _dt(50), "impact": "Low",
         "description": "DMA compliance assessment for bundling practices in enterprise software."},
    ],
    "GOOGL": [
        {"event": "Q2 2025 Earnings", "date": _dt(20), "impact": "High",
         "description": "Search revenue resilience vs. AI substitution and YouTube ad trends are key."},
        {"event": "Google I/O Product Keynote", "date": _dt(38), "impact": "Medium",
         "description": "Gemini 2.0 Ultra launch and Workspace AI product updates."},
        {"event": "DOJ Antitrust Remedy Ruling", "date": _dt(55), "impact": "High",
         "description": "Judge's remedy in search monopoly case could mandate structural changes."},
    ],
    "META": [
        {"event": "Q2 2025 Earnings", "date": _dt(19), "impact": "High",
         "description": "Ad revenue per user growth and Llama/open-source AI strategy will drive sentiment."},
        {"event": "Quest 4 Headset Launch", "date": _dt(48), "impact": "Low",
         "description": "Next-gen VR hardware could expand monetizable Reality Labs user base."},
        {"event": "EU Digital Markets Act Compliance", "date": _dt(35), "impact": "Medium",
         "description": "Mandatory interoperability requirements for WhatsApp under DMA."},
    ],
    "AMZN": [
        {"event": "Q2 2025 Earnings", "date": _dt(22), "impact": "High",
         "description": "AWS margin expansion and Trainium/custom silicon cost-out are primary catalysts."},
        {"event": "Prime Day 2025", "date": _dt(15), "impact": "Medium",
         "description": "Largest shopping event; provides read on consumer resilience and ad revenue."},
        {"event": "Bedrock Foundation Model Update", "date": _dt(40), "impact": "Medium",
         "description": "New model capabilities in Amazon Bedrock drive enterprise AI cloud attach."},
    ],
    "PLTR": [
        {"event": "Q2 2025 Earnings", "date": _dt(17), "impact": "High",
         "description": "US commercial revenue acceleration and Rule of 40 score are the defining metrics."},
        {"event": "AIP Bootcamp Schedule", "date": _dt(10), "impact": "Medium",
         "description": "Next cohort of enterprise AIP bootcamps signals pipeline velocity."},
        {"event": "DOD Contract Renewal", "date": _dt(55), "impact": "Medium",
         "description": "Maven Smart System and classified government program renewals provide revenue floor."},
    ],
    "SNOW": [
        {"event": "Q2 FY2026 Earnings", "date": _dt(21), "impact": "High",
         "description": "Net revenue retention trend and AI workload consumption are the key metrics."},
        {"event": "Snowflake Summit", "date": _dt(32), "impact": "Medium",
         "description": "Annual developer conference; Cortex AI product announcements could re-rate growth."},
    ],
    "CRM": [
        {"event": "Q2 FY2026 Earnings", "date": _dt(26), "impact": "High",
         "description": "Agentforce adoption data and professional services attach rate are key."},
        {"event": "Dreamforce 2025", "date": _dt(65), "impact": "Medium",
         "description": "Flagship customer conference; typically drives large enterprise deal announcements."},
    ],
    "NOW": [
        {"event": "Q2 2025 Earnings", "date": _dt(23), "impact": "High",
         "description": "Now Assist AI seat count and subscription CRPO growth are the headline metrics."},
        {"event": "Knowledge 2025 Conference", "date": _dt(40), "impact": "Medium",
         "description": "Annual conference; new industry AI workflow product launches expected."},
    ],
}


def get_peers(symbol: str) -> List[str]:
    """Return list of peer tickers for a given symbol."""
    return PEER_MAPPINGS.get(symbol.upper(), [])


def get_kpi_correlations(symbol: str) -> List[dict]:
    """Return the FALLBACK KPI correlation list for a given symbol.

    Used only when the builder cannot compute live rolling return correlations.
    """
    return KPI_CORRELATIONS.get(symbol.upper(), [])


def get_catalysts(symbol: str) -> List[dict]:
    """Return the FALLBACK catalyst list for a given symbol.

    The builder prefers real earnings/dividend dates from the live calendar feed
    and merges these curated editorial events behind them.
    """
    return CATALYSTS.get(symbol.upper(), [])


def get_revenue_growth(symbol: str) -> Optional[float]:
    """Return the FALLBACK annual revenue growth % for a given symbol.

    Used only when the live ``revenueGrowth`` snapshot is unavailable.
    """
    return REVENUE_GROWTH.get(symbol.upper())


def news_for(scope_type: str, scope: str, limit: int = 40) -> List[dict]:
    """scope_type: 'symbol', 'sector' or 'topic'. Returns curated news items."""
    items: List[dict] = []
    if scope_type == "topic":
        kws = [w for w in re.findall(r"[a-z0-9][a-z0-9\-]+", (scope or "").lower())
               if len(w) >= 3]
        if kws:
            scored = []
            for n in _NEWS:
                hay = (n["headline"] + " " + n["summary"]).lower()
                score = sum(1 for kw in kws if kw in hay)
                if score:
                    scored.append((score, n))
            scored.sort(key=lambda t: (-t[0], t[1]["days_ago"]))
            items = [n for _, n in scored]
        if not items:
            items = list(_NEWS)
    elif scope_type == "symbol":
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


# ----------------------------- earnings calendar -----------------------------
# Companies report quarterly. Each name's report day is derived deterministically
# from its symbol seed so the schedule is stable across restarts, while always
# rolling forward relative to today (no stale, hand-written dates). Timing
# (before/after market) and the consensus EPS estimate are likewise deterministic
# but fabricated-yet-plausible, consistent with the rest of this mock dataset.
_EARNINGS_EPOCH = date(2000, 1, 3)  # a Monday, fixes the cycle phase
_EARNINGS_CYCLE = 91  # ~ one fiscal quarter in days


def _earnings_report_date(symbol: str, today: date) -> date:
    """Next scheduled report date on or after ``today`` for ``symbol``."""
    offset = _seed(symbol) % _EARNINGS_CYCLE
    cycle_pos = (today - _EARNINGS_EPOCH).days % _EARNINGS_CYCLE
    delta = (offset - cycle_pos) % _EARNINGS_CYCLE
    report = today + timedelta(days=delta)
    # Earnings land on business days — nudge a weekend date to the next Monday.
    wd = report.weekday()
    if wd == 5:
        report += timedelta(days=2)
    elif wd == 6:
        report += timedelta(days=1)
    return report


def _earnings_timing(symbol: str) -> str:
    return "bmo" if (_seed(symbol) // 7) % 2 == 0 else "amc"


def _earnings_eps_estimate(company: dict) -> Optional[float]:
    eps = company.get("eps")
    if eps is None:
        return None
    factor = 0.90 + ((_seed(company["symbol"]) // 13) % 21) / 100.0  # 0.90..1.10
    return round((eps / 4.0) * factor, 2)


def _fiscal_quarter(report: date) -> str:
    """Plausible label for the just-reported fiscal quarter (~1 month prior)."""
    q_idx = (report.month - 2) // 3
    year = report.year
    if q_idx < 0:
        q_idx = 3
        year -= 1
    return f"Q{q_idx + 1} FY{year}"


def earnings_calendar(symbols: List[str], horizon_days: int = 30,
                      today: Optional[date] = None) -> List[dict]:
    """Build dated, sorted earnings rows for the given symbols within a horizon.

    Each row carries the report date/time, before/after-market timing, the
    consensus EPS estimate, the fiscal quarter, a live countdown (``hoursUntil``)
    and an ``imminent`` flag (reporting within the next 24 hours).
    """
    today = today or date.today()
    now = datetime.now()
    rows: List[dict] = []
    for sym in symbols:
        c = COMPANIES.get(sym.upper())
        if not c:
            continue
        report = _earnings_report_date(c["symbol"], today)
        days_until = (report - today).days
        if days_until > horizon_days:
            continue
        timing = _earnings_timing(c["symbol"])
        hour, minute = (8, 0) if timing == "bmo" else (16, 15)
        report_dt = datetime(report.year, report.month, report.day, hour, minute)
        hours_until = round((report_dt - now).total_seconds() / 3600.0, 1)
        rows.append({
            "symbol": c["symbol"],
            "name": c["name"],
            "sector": c["sector"],
            "sectorName": SECTORS.get(c["sector"], c["sector"]),
            "reportDate": report.isoformat(),
            "reportDateTime": report_dt.isoformat(),
            "timing": timing,
            "timingLabel": "Before Market Open" if timing == "bmo" else "After Market Close",
            "epsEstimate": _earnings_eps_estimate(c),
            "quarter": _fiscal_quarter(report),
            "daysUntil": days_until,
            "hoursUntil": hours_until,
            "imminent": 0 <= hours_until <= 24,
            "marketCap": c.get("marketCap"),
        })
    rows.sort(key=lambda r: r["reportDateTime"])
    return rows
