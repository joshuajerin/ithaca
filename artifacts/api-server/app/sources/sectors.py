"""Map a Yahoo/yfinance sector+industry to one of the terminal's internal
sector ids: semiconductors, energy, ai_tech. New on-demand tickers are bucketed
here so panels and sector filters keep working coherently.
"""
from __future__ import annotations

from typing import Optional

INTERNAL_DEFAULT = "ai_tech"


def map_sector(yf_sector: Optional[str], yf_industry: Optional[str]) -> str:
    s = (yf_sector or "").lower()
    ind = (yf_industry or "").lower()
    if "semiconductor" in ind or "semiconductor" in s:
        return "semiconductors"
    if "energy" in s or "oil" in ind or "gas" in ind or "solar" in ind \
            or "utilit" in s or "renewable" in ind:
        return "energy"
    if "technology" in s or "communication" in s or "software" in ind \
            or "internet" in ind or "semiconductor equip" in ind:
        return "ai_tech"
    return INTERNAL_DEFAULT
