"""Map a Yahoo/yfinance sector+industry to one of the terminal's internal
sector ids. New on-demand tickers are bucketed here so panels and sector filters
keep working coherently across the full thematic taxonomy (semiconductors,
energy, ai_tech, robotics, ev_auto, cybersecurity, biotech, fintech, cloud,
clean_energy, defense, financials, healthcare, consumer, comms, industrials,
staples, real_estate, materials, metals_mining, utilities, transportation,
insurance, telecom, crypto, space, quantum).
"""
from __future__ import annotations

from typing import Optional

INTERNAL_DEFAULT = "ai_tech"


def map_sector(yf_sector: Optional[str], yf_industry: Optional[str]) -> str:
    s = (yf_sector or "").lower()
    ind = (yf_industry or "").lower()

    # Most-specific industries first so themes win over broad GICS sectors.
    if "semiconductor" in ind or "semiconductor" in s:
        return "semiconductors"
    if "quantum" in ind:
        return "quantum"
    if "cyber" in ind or "security" in ind:
        return "cybersecurity"
    if "crypto" in ind or "blockchain" in ind or "bitcoin" in ind \
            or "digital currenc" in ind:
        return "crypto"
    if "space" in ind or "satellite" in ind or "rocket" in ind or "launch" in ind:
        return "space"
    if "auto manufacturer" in ind or "auto - " in ind or "automobile" in ind \
            or "vehicle" in ind:
        return "ev_auto"
    if "robot" in ind or "automation" in ind:
        return "robotics"
    if "aerospace" in ind or "defense" in ind or "defence" in ind:
        return "defense"
    if "biotech" in ind or "drug" in ind or "pharm" in ind:
        return "biotech"
    if "payment" in ind or "fintech" in ind or "credit services" in ind:
        return "fintech"
    if "insurance" in ind or "reinsurance" in ind:
        return "insurance"
    if "bank" in ind or "capital markets" in ind or "asset management" in ind \
            or "financial data" in ind or "mortgage" in ind \
            or ("financial" in s and "estate" not in s):
        return "financials"
    if "reit" in ind or "real estate" in s or "real estate" in ind:
        return "real_estate"
    if "health" in s or "medical" in ind or "healthcare" in ind \
            or "hospital" in ind or "diagnostic" in ind or "life sciences" in ind:
        return "healthcare"
    if "solar" in ind or "renewable" in ind or "hydrogen" in ind \
            or "fuel cell" in ind or "geothermal" in ind:
        return "clean_energy"
    if "utilit" in s or "utilit" in ind:
        return "utilities"
    if "energy" in s or "oil" in ind or "gas" in ind or "coal" in ind \
            or "pipeline" in ind:
        return "energy"
    if "gold" in ind or "silver" in ind or "copper" in ind or "mining" in ind \
            or "steel" in ind or "aluminum" in ind or "precious metal" in ind:
        return "metals_mining"
    if "chemical" in ind or "specialty chemical" in ind or "agricultural input" in ind \
            or "building materials" in ind or "paper" in ind or "packaging" in ind \
            or ("basic materials" in s and "gold" not in ind):
        return "materials"
    if "telecom" in ind or "communication equipment" in ind \
            or ("telecom" in s):
        return "telecom"
    if "communication" in s or "media" in ind or "entertainment" in ind \
            or "broadcast" in ind or "advertising" in ind or "publishing" in ind \
            or "gaming" in ind or "internet content" in ind:
        return "comms"
    if "software" in ind or "internet" in ind or "cloud" in ind:
        return "cloud"
    if "railroad" in ind or "airline" in ind or "trucking" in ind \
            or "freight" in ind or "logistics" in ind or "marine" in ind \
            or "airport" in ind or "integrated freight" in ind:
        return "transportation"
    if "beverage" in ind or "tobacco" in ind or "grocery" in ind \
            or "packaged food" in ind or "household" in ind or "personal product" in ind \
            or "confectioner" in ind or "farm product" in ind \
            or "consumer defensive" in s:
        return "staples"
    if "consumer" in s or "retail" in ind or "apparel" in ind \
            or "restaurant" in ind or "lodging" in ind or "leisure" in ind \
            or "travel" in ind or "resort" in ind:
        return "consumer"
    if "industrial" in s or "machinery" in ind or "construction" in ind \
            or "engineering" in ind or "conglomerate" in ind:
        return "industrials"
    if "technology" in s:
        return "ai_tech"
    return INTERNAL_DEFAULT
