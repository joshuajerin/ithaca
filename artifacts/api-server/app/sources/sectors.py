"""Map a Yahoo/yfinance sector+industry to one of the terminal's internal
sector ids. New on-demand tickers are bucketed here so panels and sector filters
keep working coherently across the full thematic taxonomy (semiconductors,
energy, ai_tech, robotics, ev_auto, cybersecurity, biotech, fintech, cloud,
clean_energy, defense, financials, healthcare, consumer, comms, industrials).
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
    if "cyber" in ind or "security" in ind:
        return "cybersecurity"
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
    if "bank" in ind or "capital markets" in ind or "asset management" in ind \
            or "insurance" in ind or "financial" in s:
        return "financials"
    if "health" in s or "medical" in ind or "healthcare" in ind \
            or "hospital" in ind or "diagnostic" in ind or "life sciences" in ind:
        return "healthcare"
    if "solar" in ind or "renewable" in ind or "hydrogen" in ind \
            or "fuel cell" in ind or "geothermal" in ind:
        return "clean_energy"
    if "energy" in s or "oil" in ind or "gas" in ind or "utilit" in s:
        return "energy"
    if "communication" in s or "telecom" in ind or "media" in ind \
            or "entertainment" in ind or "broadcast" in ind:
        return "comms"
    if "software" in ind or "internet" in ind or "cloud" in ind:
        return "cloud"
    if "consumer" in s or "retail" in ind or "apparel" in ind \
            or "restaurant" in ind:
        return "consumer"
    if "industrial" in s or "machinery" in ind or "construction" in ind \
            or "freight" in ind or "logistics" in ind or "railroad" in ind:
        return "industrials"
    if "technology" in s:
        return "ai_tech"
    return INTERNAL_DEFAULT
